from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_
from app.db.models import Owner, OwnershipTransfer, TransferDocument
from app.schemas.ownership_schema import InheritanceRequest
from redis import Redis
from fastapi import HTTPException, status

async def inheritance_distribution(payload: InheritanceRequest, db: AsyncSession, redis: Redis):
    
    deceased_owner_stmt=select(Owner).where(Owner.owner_id==payload.deceased_owner_id)
    deceased_owner_stmt=await db.execute(deceased_owner_stmt)
    deceased_owner=deceased_owner_stmt.scalar_one_or_none()
    if not deceased_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deceased owner not found")