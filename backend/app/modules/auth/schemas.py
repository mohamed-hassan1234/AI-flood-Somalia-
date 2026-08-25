from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    # A basic local@domain.tld shape, not EmailStr: this validates a lookup key against an
    # existing account, not a new address to be trusted for delivery. EmailStr rejects RFC 2606
    # reserved-use domains (e.g. the documented `*.development.invalid` seed accounts), which
    # would otherwise make the documented development seed accounts unable to authenticate.
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@'\";]+@[^\s@'\";]+\.[^\s@'\";]+$"
    )
    password: str = Field(min_length=12, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class PrincipalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    email: str
    display_name: str
    capabilities: list[str]
