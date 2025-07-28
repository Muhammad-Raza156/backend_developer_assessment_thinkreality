from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.database import get_db
from app.core.redis_client import get_redis
from app.schemas.ownership_schema import TransferRequest
from app.services.ownership_service import process_transfer
from app.services.portfolio_service import get_portfolio_data
from fastapi import Query
from uuid import UUID
from datetime import date 
from typing import Literal

StatusFilter = Literal["current", "historical", "all"]

router = APIRouter()

@router.post("/ownership/transfers/initiate")
async def initiate_transfer(
    payload: TransferRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    Initiates a new ownership transfer process.

    This endpoint receives a transfer request, validates it, and processes
    the entire transaction atomically. It handles changes in ownership percentages,
    creates records for new owners, updates ownership history, and logs the
    transaction for audit purposes.

    Args:
        payload (TransferRequest): The transfer request details, including unit ID,
            current owners (sellers), new owners (buyers), and transfer details.
        db (AsyncSession, optional): The database session dependency.
            Defaults to Depends(get_db).
        redis (Redis, optional): The Redis client dependency for caching.
            Defaults to Depends(get_redis).

    Raises:
        HTTPException:
            - 400 BAD REQUEST: If the provided ownership data is inconsistent,
              e.g., sellers don't match DB records or percentages don't add up.
            - 404 NOT FOUND: If the specified unit does not exist.
            - 409 CONFLICT: If the current ownership state in the database is
              inconsistent (e.g., percentages don't sum to 100%).
        HTTPException: 500 INTERNAL SERVER_ERROR for any other unexpected
            errors during the transfer process.

    Returns:
        dict: A dictionary with a "status" of "success" and the "transfer_id"
              of the newly created transfer record.
    """
    try:
        result = await process_transfer(payload, db, redis)
        return {"status": "success", "transfer_id": result}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An Internal Server Error Occurred")

@router.get("/owners/{owner_id}/portfolio")
async def get_owner_portfolio(
    owner_id: UUID, 
    include_history: bool = Query(False, description="Legacy parameter to include historical records. Use status_filter instead."),
    from_date: date = Query(None, description="Filter for records active on or after this date."), 
    to_date: date = Query(None, description="Filter for records active before this date."),
    status_filter: StatusFilter = Query(None, description="Filter for ownership status ('current', 'historical', 'all')."),  
    db: AsyncSession = Depends(get_db)):
    """
    Retrieves a comprehensive portfolio report for a specific owner.

    This endpoint provides a detailed view of an owner's assets, including:
    - A list of all current and/or historical property holdings.
    - The total estimated value of their current portfolio.
    - A summary of all past transactions (sales and purchases).
    - Performance metrics for each unit, such as ROI and holding periods.
    - Details of any joint owners for currently held properties.

    Args:
        owner_id (UUID): The unique identifier of the owner.
        include_history (bool, optional): If True, includes historical records.
            Defaults to False. This is a legacy parameter; `status_filter` is preferred.
        from_date (date, optional): Filters ownership records to those active on or after this date.
        to_date (date, optional): Filters ownership records to those active on or before this date.
        status_filter (StatusFilter, optional): Filters the portfolio list.
            Can be 'current', 'historical', or 'all'. Overrides `include_history`.
        db (AsyncSession, optional): The database session dependency.

    Raises:
        HTTPException: 404 NOT FOUND if the owner does not exist.
        HTTPException: 400 BAD REQUEST if an invalid `status_filter` is provided.
        HTTPException: 500 INTERNAL SERVER ERROR for any other unexpected errors.

    Returns:
        dict: A dictionary containing the full portfolio report.
    """
    try:
        portfolio = await get_portfolio_data(
            db=db,
            owner_id=owner_id,
            include_history=include_history,
            from_date=from_date,
            to_date=to_date,
            status_filter=status_filter
        )
        return portfolio
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    