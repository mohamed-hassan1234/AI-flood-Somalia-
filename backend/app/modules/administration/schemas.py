from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.enums import Classification


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    organization_type: str = Field(min_length=3, max_length=80)


class OrganizationResponse(OrganizationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=256)


class UserResponse(BaseModel):
    # Plain str, not EmailStr: this projects an already-persisted account, not a new address
    # to validate. EmailStr would reject existing accounts on RFC 2606 reserved-use domains
    # (e.g. the documented `*.development.invalid` seed accounts) when merely reading them back.
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str
    active: bool


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    capabilities: list[str]


class MembershipCreate(BaseModel):
    user_id: UUID
    organization_id: UUID
    role_id: UUID
    classification_ceiling: Classification
    national: bool = False
    admin_unit_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def exactly_one_scope_mode(self) -> "MembershipCreate":
        if self.national == bool(self.admin_unit_ids):
            raise ValueError("Choose either national scope or one or more administrative units")
        if len(set(self.admin_unit_ids)) != len(self.admin_unit_ids):
            raise ValueError("Administrative scopes must be unique")
        return self


class MembershipResponse(BaseModel):
    id: UUID
    user_id: UUID
    organization_id: UUID
    role_id: UUID
    classification_ceiling: Classification
    active: bool
    national: bool
    admin_unit_ids: list[UUID]
