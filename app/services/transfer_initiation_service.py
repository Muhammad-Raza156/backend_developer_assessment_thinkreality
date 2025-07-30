import logging
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_,func, or_
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
        # check
        stmt=select(OwnershipTransfer).where(
            and_(OwnershipTransfer.unit_id==payload.unit_id, 
                 or_(OwnershipTransfer.status=="pending", OwnershipTransfer.status=="in_progress")))
        conflict_transfer=await db.execute(stmt)
        conflict_transfer=conflict_transfer.scalar_one_or_none
        if conflict_transfer:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Transfer for this property is already in process")
        
        # Check if the unit exists
        unit_result= await db.execute(select(Unit).where(Unit.unit_id == payload.unit_id))
        unit = unit_result.scalar_one_or_none()
        if not unit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
        # Get current ownership state from the database
        stmt = select(OwnershipHistory).where(
            and_(OwnershipHistory.unit_id == payload.unit_id, OwnershipHistory.ownership_end_date.is_(None))
        )
        current_ownership_records = await db.execute(stmt)
        current_ownership_records = current_ownership_records.scalars().all()
        print(len(current_ownership_records))
        print(current_ownership_records[0].owner_id, current_ownership_records[0].ownership_percentage)
        print(current_ownership_records[1].owner_id, current_ownership_records[1].ownership_percentage)

        if not current_ownership_records:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Current ownership for{payload.unit_id}  not found")
        

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
        

        # process buyers
        buyer_ownerships = {}
        for buyer in payload.new_owners:
            emirates_id = buyer.emirates_id
            stmt=select(Owner.owner_id).where(Owner.emirates_id==emirates_id)
            buyer_id=await db.execute(stmt)
            buyer_owner_id=buyer_id.scalar_one_or_none()
            
            buyer_ownerships[f"{buyer_owner_id}"] = buyer.ownership_percentage

        # calculate sum of  percentages  final ownerships and buyer ownerships and it shall be equal to 100.0 if not then raise error for gap 

        total_final_ownerships = sum(final_ownerships.values())+sum(buyer_ownerships.values())
        if abs(total_final_ownerships - 100) > 1e-9:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, 
                                detail="Ownership percentages do not add up to 100%")

        transfer_record = OwnershipTransfer(
            unit_id=payload.unit_id,
            transfer_type=payload.transfer_type,
            transfer_date=payload.transfer_date,
            total_amount=payload.purchase_price,
            transfer_currency="AED",
            legal_reason=payload.legal_reason,
            status="pending",
            initiated_by="system",
        )
        db.add(transfer_record)
        db.flush()

        transfer_documents=[]
        for doc in payload.documents:
            transfer_document = TransferDocument(
                transfer_id=transfer_record.transfer_id,
                document_type=doc.document_type,
                document_name=doc.document_name,
                file_path=str(doc.file_path),
                upload_date=doc.upload_date,
                uploaded_by=doc.uploaded_by,
                verification_status=doc.verification_status
            )
            db.add(transfer_document)
            db.flush()
            transfer_documents.append(transfer_document)


        # fetch transfer id for the transfer record added to database
        transfer_id = transfer_record.transfer_id

        payload_values=payload.dict()
        new_values={}
        for key, value in payload_values.items():
            if key =='sellers':
                new_values[key]=final_ownerships
            elif key=='buyers':
                new_values[key]=buyer_ownerships
            else:
                new_values[key]=str(value)
        print(new_values)


        # audit log record added
        audit_log = AuditLog(
            table_name="ownership_transfers",
            record_id=str(transfer_id),
            action="INSERT",
            old_values=None,
            new_values=new_values,
            changed_by="system",
            change_reason="Ownership transfer initiated",
            ip_address="127.0.0.1",
            user_agent="system"
        )
        db.add(audit_log)
        db.flush()
        # --- Prepare data for caching before the transaction commits ---
        # Ensure all data is serializable for Redis
        cache_record = {
            "transfer_id": transfer_id,
            "unit_id": str(payload.unit_id),
            "transfer_type": payload.transfer_type,
            "transfer_date": payload.transfer_date.isoformat(),
            "total_amount": payload.purchase_price,
            "transfer_currency": "AED",
            "legal_reason": payload.legal_reason,
            "status": "pending",
            "initiated_by": "system",
            # Storing remaining percentages for sellers
            "sellers": {str(owner_id): pct for owner_id, pct in final_ownerships.items()},
            # Storing new percentages for buyers
            "buyers": {str(owner_id): pct for owner_id, pct in buyer_ownerships.items()},
        }
        serialized_cache_data = json.dumps(cache_record)
        
    # 4. --- Cache Storage ---
    try:
        cache_key = f"ownership_transfer:unit:{payload.unit_id}"
        # The response from this function is built from the cache_record, so we add the full details back
        cache_record["documents"] = {str(doc.document_name): str(doc.file_path) for doc in transfer_documents}
        cache_record["audit_log_id"] = audit_log.log_id
        await redis.set(cache_key, serialized_cache_data, ex=3600)  # Cache for 1 hour
        logger.info(f"Ownership data for unit {payload.unit_id} cached successfully.")
    except Exception as e:
        # Log cache error but don't fail the request, as the DB is the source of truth
        print(f"An error occurred while caching ownership data: {str(e)}")
        logger.error(f"Failed to cache ownership data for unit {payload.unit_id}: {e}")
    db.commit()
    return cache_record