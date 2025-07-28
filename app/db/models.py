from sqlalchemy import (
    Column, String, Float, ForeignKey, TIMESTAMP, Boolean, Date, Integer,
    CheckConstraint, func, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB 
from sqlalchemy.schema import Index
import uuid
from app.db.base import Base

class Unit(Base):
    __tablename__ = "units"
    unit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unique_key = Column(String, unique=True, nullable=False)
    building_name = Column(String, nullable=False)
    unit_number = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

class Owner(Base):
    __tablename__ = "owners"
    owner_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type = Column(String, nullable=False)
    full_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    date_of_birth = Column(Date)
    nationality = Column(String)
    company_name = Column(String)
    company_type = Column(String)
    trade_license_number = Column(String)
    phone_primary = Column(String)
    phone_secondary = Column(String)
    email = Column(String)
    emirates_id = Column(String, unique=True)
    passport_number = Column(String)
    visa_number = Column(String)
    address_line1 = Column(String)
    city = Column(String)
    country = Column(String)
    preferred_contact_method = Column(String)
    communication_language = Column(String)
    is_active = Column(Boolean, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    __table_args__ = (
        CheckConstraint("owner_type IN ('individual', 'corporate')", name="check_owner_type"),
        CheckConstraint(
            "NOT (owner_type = 'individual' AND emirates_id IS NULL)",
            name="check_individual_owner_eid"
        ),
        CheckConstraint(
            "emirates_id IS NULL OR emirates_id ~ '^784-[0-9]{4}-[0-9]{7}-[0-9]{1}$'",
            name="check_emirates_id_format"
        ),
    )

class OwnershipHistory(Base):
    __tablename__ = "ownership_history"
    history_id = Column(Integer, primary_key=True)
    unit_id = Column(UUID(as_uuid=True), ForeignKey("units.unit_id"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("owners.owner_id"), nullable=False)
    ownership_start_date = Column(Date, nullable=False)
    ownership_end_date = Column(Date)
    ownership_percentage = Column(Float, nullable=False)
    is_current_owner = Column(Boolean, nullable=False)
    purchase_price = Column(Float)
    purchase_currency = Column(String(3))
    financing_type = Column(String)
    title_deed_number = Column(String)
    registration_number = Column(String)
    transaction_type = Column(String)
    transfer_reason = Column(String)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    __table_args__ = (
        CheckConstraint(
            'ownership_percentage > 0 AND ownership_percentage <= 100',
            name='ownership_percentage_check'
        ),
        Index('idx_ownership_history_unit_id', 'unit_id'),
        Index('idx_ownership_history_owner_id', 'owner_id'),
    )

class OwnershipTransfer(Base):
    __tablename__ = "ownership_transfers"
    transfer_id = Column(Integer, primary_key=True)
    unit_id = Column(UUID(as_uuid=True), ForeignKey("units.unit_id"), nullable=False)
    transfer_type = Column(String, nullable=False)
    transfer_date = Column(Date, nullable=False)
    total_amount = Column(Float)
    transfer_currency = Column(String(3))
    legal_reason = Column(String)
    status = Column(String)
    initiated_by = Column(String)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    __table_args__ = (
        CheckConstraint(
            'transfer_date <= CURRENT_DATE',
            name='transfer_date_not_in_future_check'
        ),
        Index('idx_ownership_transfers_unit_id', 'unit_id'),
    )

class TransferDocument(Base):
    __tablename__ = "transfer_documents"
    document_id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("ownership_transfers.transfer_id"), nullable=False)
    document_type = Column(String)
    document_name = Column(String)
    file_path = Column(String)
    upload_date = Column(Date)
    uploaded_by = Column(String)
    verification_status = Column(String)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    __table_args__ = (
        Index('idx_transfer_documents_transfer_id', 'transfer_id'),
    )

class AuditLog(Base):
    __tablename__ = "audit_logs"
    log_id = Column(Integer, primary_key=True)
    table_name = Column(String)
    record_id = Column(String)
    action = Column(String)
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    changed_by = Column(String)
    change_reason = Column(String)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    __table_args__ = (
        Index('idx_audit_logs_record_id', 'record_id'),
        Index('idx_audit_logs_changed_by', 'changed_by'),
    )