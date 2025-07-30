from pydantic import BaseModel, Field, model_validator, HttpUrl
from typing import List, Optional, Literal, Dict
from datetime import date
from uuid import UUID


class DocumentInfo(BaseModel):
    document_type: str
    document_name: str
    file_path: HttpUrl
    upload_date: Optional[date] = None
    uploaded_by: Optional[str] = None
    verification_status: Optional[str] = "pending"

class OwnerData(BaseModel):
    full_name: str
    emirates_id: str = Field(
        ...,
        pattern=r"^784-[0-9]{4}-[0-9]{7}-[0-9]{1}$",
        description="Emirates ID in the format XXX-XXXX-XXXXXXX-X",
    )
    phone: str
    owner_type: Literal["individual", "corporate"]

class NewOwnerInfo(OwnerData):
    ownership_percentage: float = Field(..., gt=0, le=100)

class CurrentOwnerInfo(BaseModel):
    owner_id: UUID
    ownership_percentage: float = Field(..., gt=0, le=100)
    transfer_percentage: float  = Field(..., gt=0, le=100)

    @model_validator(mode="after")
    def check_transfer_is_not_more_than_current_ownership(self) -> "CurrentOwnerInfo":
        if self.transfer_percentage > self.ownership_percentage:
            raise ValueError(
                "Transfer percentage cannot be greater than ownership percentage"
            )
        return self

class TransferRequest(BaseModel):
    unit_id: UUID
    transfer_type: Literal[
        "purchase", "inheritance", "gift", "court_order", "corporate_restructuring"
    ]
    current_owners: List[CurrentOwnerInfo]
    new_owners: List[NewOwnerInfo]
    transfer_date: date
    purchase_price: float= Field(..., gt=0)
    legal_reason: str
    documents: List[DocumentInfo]

    @model_validator(mode="after")
    def check_percentages_balance(self) -> "TransferRequest":
        total_transfer_percentage = sum(
            owner.transfer_percentage for owner in self.current_owners
        )
        total_new_owner_percentage = sum(
            owner.ownership_percentage for owner in self.new_owners
        )

        # Use a small tolerance for float comparison
        if abs(total_transfer_percentage - total_new_owner_percentage) > 1e-9:
            raise ValueError(
                "Total percentage being transferred must equal the total percentage being acquired by new owners."
            )
        return self
    
class ValidationRequest(BaseModel):
    unit_id: UUID
    transfer_id: open[UUID]=None

class InheritanceRequest(BaseModel):
    unit_id: UUID
    deceased_owner_id: UUID
    transfer_type: str = "inheritance"
    ownership_percentage: float
    heirs: Dict[str, str]
    transfer_date: date
    legal_reason: str
    documents: List[DocumentInfo]