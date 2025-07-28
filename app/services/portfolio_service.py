from typing import Dict, Any, List, Literal
from uuid import UUID
from datetime import date, datetime, timezone
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, distinct
from sqlalchemy.orm import aliased
from app.db.models import OwnershipHistory, Unit, Owner, OwnershipTransfer

StatusFilter = Literal["current", "historical", "all"]

async def get_portfolio_data(
    db: AsyncSession,    
    owner_id: UUID,
    include_history: bool = False,
    from_date: date = None,
    to_date: date = None,
    status_filter: StatusFilter = None,
    )-> Dict[str, Any]:
    """
    Retrieves a comprehensive portfolio for a given owner.

    Args:
        db (AsyncSession): The database session.
        owner_id (UUID): The unique identifier for the owner.
        include_history (bool, optional): If True, includes historical records.
            Defaults to False. Deprecated in favor of `status_filter`.
        from_date (date, optional): The start date for filtering ownership records.
            Defaults to None.
        to_date (date, optional): The end date for filtering ownership records.
            Defaults to None.
        status_filter (StatusFilter, optional): Filter for ownership status
            ('current', 'historical', 'all'). Overrides `include_history`.
            Defaults to None.

    Raises:
        ValueError: If the owner is not found or an invalid `status_filter`
            is provided.

    Returns:
        Dict[str, Any]: A dictionary containing the full portfolio report.
    """

    # Base query
    query = select(OwnershipHistory, Unit).join(Unit, OwnershipHistory.unit_id == Unit.unit_id)\
        .where(OwnershipHistory.owner_id == owner_id)

    # Apply status filter
    if status_filter == "current":
        query = query.where(OwnershipHistory.is_current_owner == True)
    elif status_filter == "historical":
        query = query.where(OwnershipHistory.is_current_owner == False)
    else:
        pass

    # Apply date filter
    if from_date and to_date:
        query = query.where(
            or_(
                and_(
                    OwnershipHistory.ownership_start_date >= from_date,
                    OwnershipHistory.ownership_start_date <= to_date
                ),
                and_(
                    OwnershipHistory.ownership_end_date != None,
                    OwnershipHistory.ownership_end_date >= from_date,
                    OwnershipHistory.ownership_end_date <= to_date
                )
            )
        )
    result = await db.execute(query)
    history_records = result.all()


    current_ownership = []
    historical_ownership =[]

    # Portfolio value and metrics
    for history, unit in history_records:
        if history.is_current_owner:
            current_record={
                "unit_id": history.unit_id,
                "building_name": unit.building_name,
                "unit_number": unit.unit_number,
                "owner_id": history.owner_id,
                "purchase_price": history.purchase_price,
                "ownership_start_date": history.ownership_start_date,
                "ownership_end_date": history.ownership_end_date,
                "ownership_percentage": history.ownership_percentage
            }
            current_ownership.append(current_record)
        else:
            historical_record={
                    "unit_id": history.unit_id,
                    "building_name": unit.building_name,
                    "unit_number": unit.unit_number,
                    "owner_id": history.owner_id,
                    "purchase_price": history.purchase_price,
                    "purchase_currency": history.purchase_currency,
                    "ownership_start_date": history.ownership_start_date,
                    "ownership_end_date": history.ownership_end_date,
                    "ownership_percentage": history.ownership_percentage,
                    "is_current_owner": history.is_current_owner,
                    "financing_type": history.financing_type,
                    "title_deed_number": history.title_deed_number,
                    "registration_number": history.registration_number,
                    "transaction_type": history.transaction_type,
                    "transfer_reason": history.transfer_reason
                }
            historical_ownership.append(historical_record)
    total_current_value = 0.0
    total_current_value = sum([rec['purchase_price'] for rec in current_ownership])

    total_historical_value = 0.0
    total_historical_value = sum([rec['purchase_price'] for rec in historical_ownership])

    total_amount = total_current_value + total_historical_value

    portfolio_decrease = 0.0
    if total_current_value < total_amount:
        portfolio_decrease = ((total_amount-total_current_value)/total_amount)*100.0


    # ROI & holding period
    #rois, holding_days = [], []
    #for rec, _ in history_records:
    #    if rec.purchase_price and rec.ownership_end_date:
    #        duration = (rec.ownership_end_date - rec.ownership_start_date).days
    #        holding_days.append(duration)
    #        # Dummy ROI: just illustrative
    #        roi = ((rec.purchase_price * 1.1) - rec.purchase_price) / rec.purchase_price
    #        rois.append(roi)

    # Historical transfer summary
    trans_query = select(OwnershipTransfer).where(OwnershipTransfer.unit_id.in_(
        [rec['unit_id'] for rec in historical_ownership]
    ))
    if from_date and to_date:
        trans_query = trans_query.where(OwnershipTransfer.transfer_date.between(from_date, to_date))
    
    trans_result=await db.execute(trans_query)
    transfers = trans_result.all()

    transfers_summary=[]
    for trans in transfers:
        transfers_summary.append({
            "transfer_id": trans.transfer_id,
            "unit_id": trans.unit_id,
            "transfer_type": trans.transfer_type,
            "transfer_date": trans.transfer_date,
            "transfer_amount": trans.total_amount,
            "transfer_currency": trans.transfer_currency,
            "legal_reason": trans.legal_reason,
            "status": trans.status,
            "initiated_by": trans.initiated_by,
            "created_at": trans.created_at
        })


    print(transfers)

    # Joint ownership details
    joint_units = {}
    for rec, _ in history_records:
        unit_id = rec.unit_id
        co_owners_stmt = select(distinct(OwnershipHistory.owner_id)).where(
            OwnershipHistory.unit_id == unit_id,
            OwnershipHistory.owner_id != owner_id,
            OwnershipHistory.is_current_owner == True
        )
        co_owners_result = await db.execute(co_owners_stmt)
        co_owners = co_owners_result.all()
        if co_owners:
            joint_units[unit_id] = [str(o[0]) for o in co_owners]

        owner_portfolio = {
        "ownership_timeline": historical_ownership,
        "current_ownership": current_ownership,
        "portfolio_value": total_current_value,
        "portfolio_decrease": portfolio_decrease,
        "transactions_summary": {
            "total_transactions": len(history_records),
            "total_amount": total_amount,
        },
        "joint_ownerships": joint_units
    }
    return owner_portfolio
