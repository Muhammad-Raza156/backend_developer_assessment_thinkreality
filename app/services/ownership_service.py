import logging
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_,func
from redis.asyncio import Redis
import json

from app.schemas.ownership_schema import TransferRequest
from app.db.models import (
    Unit, 
    Owner, 
    OwnershipHistory, 
    OwnershipTransfer, 
    TransferDocument, 
    AuditLog
)

logger = logging.getLogger(__name__)

async def process_transfer(payload: TransferRequest, db: AsyncSession, redis: Redis):
    """
    Processes a complete ownership transfer transaction for a real estate unit.

    This function orchestrates the entire transfer process within a single atomic
    database transaction. It performs the following steps:
    1.  Validates the existence of the unit and the consistency of the provided
        current ownership data against the database.
    2.  Calculates the new ownership distribution based on sellers and buyers.
    3.  Creates new owner records if any buyers are new to the system.
    4.  Expires the old ownership history records and creates new ones reflecting
        the final ownership state.
    5.  Records the transfer details, associated documents, and a comprehensive
        audit log entry.
    6.  Updates a Redis cache with the new ownership information upon successful
        completion of the database transaction.

    Args:
        payload (TransferRequest): The request payload containing all transfer details.
        db (AsyncSession): The asynchronous database session.
        redis (Redis): The asynchronous Redis client for caching.

    Raises:
        HTTPException: with status codes 404, 409, or 400 for various
                       validation failures (e.g., unit not found, ownership
                       mismatch, or invalid percentage distribution).

    Returns:
        str: The UUID of the first ownership transfer record created.
    """
    #Validate IDs, percentages, existing ownerships, documents
    async with db.begin():
        # Check if the unit exists
        unit_result= await db.execute(select(Unit).where(Unit.unit_id == payload.unit_id))
        unit = unit_result.scalar_one_or_none()
        if not unit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
        # Get current ownership state from the database
        stmt = select(OwnershipHistory).where(
            and_(OwnershipHistory.unit_id == payload.unit_id, OwnershipHistory.to_date.is_(None))
        )
        current_ownership_records = (await db.execute(stmt)).scalars().all()

        db_ownerships = {record.owner_id: record.ownership_percentage for record in current_ownership_records}

        if abs(sum(db_ownerships.values()) - 100) > 1e-9:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ownership percentages do not add up to 100%")

        payload_current_owner_ids = {owner.owner_id for owner in payload.current_owners}
        if payload_current_owner_ids != set(db_ownerships.keys()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provided current owners do not match database records.")            

        # Transactional Update Phase
        final_ownerships = db_ownerships.copy()

        # process sellers
        for seller in payload.current_owners:
            final_ownerships[seller.owner_id] -= seller.transfer_percentage

        new_owner_map = {} # Maps EID to Owner object
        for buyer_info in payload.new_owners:
            owner_result = await db.execute(select(Owner).where(Owner.emirates_id == buyer_info.emirates_id))
            owner = owner_result.scalar_one_or_none()
            if not owner:
                owner = Owner(
                    full_name=buyer_info.full_name,
                    emirates_id=buyer_info.emirates_id,
                    phone=buyer_info.phone,
                    owner_type=buyer_info.owner_type
                )
                db.add(owner)
                await db.flush()
            new_owner_map[buyer_info.emirates_id] = owner
            final_ownerships[owner.owner_id] = final_ownerships.get(owner.owner_id, 0) + buyer_info.ownership_percentage
        
        # Filter out any owners with 0% share
        final_ownerships = {owner_id: pct for owner_id, pct in final_ownerships.items() if pct > 1e-9}
        # Final check: Ensure the new total ownership is 100%
        if abs(sum(final_ownerships.values()) - 100.0) > 1e-9:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ownership transfer would result in a gap or overlap. Total must be 100%.")
        # 3. --- Database Record Creation ---

        # Expire old ownership records
        for record in current_ownership_records:
            record.to_date = func.now()
            db.add(record)
        
        # Create new ownersip records
        for owner_id, pct in final_ownerships.items():
            new_history = OwnershipHistory(
                unit_id=payload.unit_id,
                owner_id=owner_id,
                ownership_percentage=pct,
                from_date=func.now()
            )
            db.add(new_history)

        # Create Audit Trail
        first_transfer_id = None
        for seller in payload.current_owners:
            for buyer in payload.new_owners:
                buyer_owner_id = await db.execute(select(Owner.owner_id).where(Owner.emirates_id == buyer.emirates_id))
                new_transfer = OwnershipTransfer(
                    unit_id=payload.unit_id,
                    transfer_type=payload.transfer_type,
                    current_owner_id=seller.owner_id,
                    new_owner_id=buyer_owner_id.scalar_one(),
                    transfer_share=seller.transfer_percentage,
                    transfer_date=payload.transfer_date,
                    purchase_price=payload.purchase_price,
                    legal_reason=payload.legal_reason
                )
                db.add(new_transfer)
                await db.flush()
                if not first_transfer_id:
                    first_transfer_id = new_transfer.id

                # Add documents for this transfer
                for doc_meta in payload.documents:
                    db.add(TransferDocument(transfer_id=new_transfer.id, details={"document_url": doc_meta}))
        
        # Create a single, comprehensive audit log entry
        audit = AuditLog(
            action="ownership_transfer_initiated",
            description=f"Ownership transfer for unit {payload.unit_id} of type '{payload.transfer_type}'.",
            actor_id=payload.current_owners[0].owner_id,
            target_id=payload.unit_id,
            details=json.loads(payload.model_dump_json(exclude={'documents'}))
        )
        db.add(audit)

        # --- Prepare data for caching before the transaction commits ---
        all_final_owner_ids = list(final_ownerships.keys())
        if all_final_owner_ids:
            owners_result = await db.execute(
                select(Owner).where(Owner.owner_id.in_(all_final_owner_ids))
            )
            owners = owners_result.scalars().all()
            owner_map = {owner.owner_id: owner for owner in owners}

            cache_data = []
            for owner_id, percentage in final_ownerships.items():
                owner = owner_map.get(owner_id)
                if owner:
                    cache_data.append({
                        "owner_id": str(owner.owner_id),
                        "full_name": owner.full_name,
                        "emirates_id": owner.emirates_id,
                        "percentage": percentage,
                    })
            serialized_cache_data = json.dumps(cache_data)
        else:
            serialized_cache_data = "[]"
        
    # 4. --- Cache Storage ---
    try:
        cache_key = f"ownership:unit:{payload.unit_id}"
        await redis.set(cache_key, serialized_cache_data, ex=3600)  # Cache for 1 hour
        logger.info(f"Ownership data for unit {payload.unit_id} cached successfully.")
    except Exception as e:
        # Log cache error but don't fail the request, as the DB is the source of truth
        logger.error(f"Failed to cache ownership data for unit {payload.unit_id}: {e}")
    return str(first_transfer_id)