from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_
from app.db.models import OwnershipTransfer, TransferDocument, OwnershipHistory
from app.schemas.ownership_schema import ValidationRequest
from redis import Redis
from fastapi import HTTPException, status
import json


async def document_verfication(doc):
    # just a placeholder logic while in reality,
    #  there will be request made to an external service to verify document 
    verification_state=True
    return verification_state


async def transfer_validation(payload: ValidationRequest, db: AsyncSession, redis: Redis):
    async with db.begin():
        stmt=select(OwnershipTransfer).where(
            and_(OwnershipTransfer.unit_id==payload.unit_id,
                 or_(OwnershipTransfer.status=="pending", OwnershipTransfer.status=="in_progress")))
        result=await db.execute(stmt)
        transfer=result.scalar_one_or_none()

        if not transfer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending or in progress transfer found for this unit")


        transfer_id = transfer.transfer_id
        trans_doc_stmt=select(TransferDocument).where(TransferDocument.transfer_id==transfer_id)
        doc_result=await db.execute(trans_doc_stmt)
        transfer_documents=doc_result.scalars().all()
        if transfer_documents:
            for doc in transfer_documents:
                if doc.verification_status=="pending":
                    verification_state=await document_verfication(doc)
                    if not verification_state:
                        doc.verification_status = "not verified"
                        db.add(doc)
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document {doc.document_name} could not be verified.")
                    else:
                        doc.verification_status="verified"
                        db.add(doc)
                elif doc.verification_status=="not verified":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                                        detail=f"Document {doc.document_name} was previously marked as not verified.")
        
        unit_id=transfer.unit_id
        redis_key=f"ownership_transfer:unit:{unit_id}"
        cached_data_str = await redis.get(redis_key)

        if not cached_data_str:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer data not found in cache. Cannot complete validation.")
        
        try:
            data = json.loads(cached_data_str)
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse cached transfer data.")

        for seller_id, new_percentage in data["sellers"].items():
            stmt = select(OwnershipHistory).where(
                and_(
                    OwnershipHistory.unit_id == unit_id,
                    OwnershipHistory.owner_id == seller_id,
                    OwnershipHistory.is_current_owner == True
                )
            )
            result = await db.execute(stmt)
            existing_ownership = result.scalar_one_or_none()

            if not existing_ownership:
                # This indicates a data inconsistency. In a real system, this might be a critical error.
                print(f"Warning: No current ownership record found for seller {seller_id} and unit {unit_id}")
                continue

            if new_percentage > 0.0:
                # Seller still owns a share, update their percentage
                existing_ownership.ownership_percentage = new_percentage
                existing_ownership.transfer_reason = data.get("legal_reason", "Ownership percentage updated during transfer")
                db.add(existing_ownership)
            else: 
                # new_percentage is 0 or less
                # Seller sold their entire share, mark as historical owner
                existing_ownership.is_current_owner = False
                existing_ownership.ownership_end_date = data["transfer_date"]
                existing_ownership.transfer_reason = "Sold the property"
                db.add(existing_ownership)

        # --- Correctly INSERT new buyer records ---
        for buyer_id, percentage in data["buyers"].items():
            new_ownership = OwnershipHistory(
                unit_id=unit_id,
                owner_id=buyer_id,
                ownership_start_date=data["transfer_date"],
                ownership_percentage=percentage,
                is_current_owner=True,
                purchase_price=data.get("total_amount"),
                purchase_currency=data.get("transfer_currency", "AED"),
                transaction_type=data.get("transfer_type"),
                transfer_reason=data.get("legal_reason")
            )
            db.add(new_ownership)
        
        # --- Finalize the transfer ---
        transfer.status = "completed"
        db.add(transfer)

        # Clean up the cache
        await redis.delete(redis_key)
    return transfer
                   