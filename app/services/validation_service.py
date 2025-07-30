from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import OwnershipTransfer
from app.schemas.ownership_schema import ValidationRequest
from redis import Redis
from fastapi import HTTPException, status


async def transfer_validation(payload: ValidationRequest, db: AsyncSession, redis: Redis):
    trans_stmt=select(OwnershipTransfer).where(OwnershipTransfer.unit_id==payload.unit_id)
    trans_stmt=await db.execute(trans_stmt)
    transfer=trans_stmt.scalar_one_or_none()

    if not trans_stmt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")


    transfer