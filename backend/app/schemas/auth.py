"""Pydantic schemas for authentication, registration, password flows, and user sessions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.business import BusinessProfileResponse
from app.schemas.common import NormalizedEmail, OptionalCleanText
from app.schemas.saas import SubscriptionSummary, SupportContactResponse


class RegisterRequest(BaseModel):
    """Payload to register a new SaaS business user and profile (enters PENDING_APPROVAL)."""

    full_name: str = Field(min_length=2, max_length=160)
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str | None = Field(default=None, max_length=128)
    business_name: str = Field(min_length=2, max_length=160)
    phone: OptionalCleanText = Field(default=None, max_length=40)
    gstin: OptionalCleanText = Field(default=None, max_length=64)
    address: OptionalCleanText = Field(default=None, max_length=200)
    business_type: OptionalCleanText = Field(default=None, max_length=80)
    terms_accepted: bool = Field(default=True)

    @field_validator("full_name", "business_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Must contain at least 2 non-whitespace characters.")
        return cleaned

    @field_validator("gstin")
    @classmethod
    def normalize_gstin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    @model_validator(mode="after")
    def validate_registration_rules(self) -> "RegisterRequest":
        if self.confirm_password is not None and self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        if not self.terms_accepted:
            raise ValueError("You must accept the Terms & Conditions to register.")
        return self


class LoginRequest(BaseModel):
    """Payload to sign in with email and password."""

    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = Field(default=False)


class ForgotPasswordRequest(BaseModel):
    """Payload to request a password reset (processed via admin queue without leaking existence)."""

    email: NormalizedEmail
    reason: OptionalCleanText = Field(default=None, max_length=300)


class ChangeUserPasswordRequest(BaseModel):
    """Payload to change a user's own password (e.g. after admin password reset)."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangeUserPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class UserSummary(BaseModel):
    """Safe user profile returned to authenticated callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    email: str
    full_name: str
    phone: str | None = None
    role: str
    is_active: bool
    approval_status: str = "PENDING_APPROVAL"
    allow_self_activation: bool = True
    must_change_password: bool = False
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class AuthResponse(BaseModel):
    """Authenticated / pending session response including user, business, and subscription."""

    user: UserSummary
    business: BusinessProfileResponse
    subscription: SubscriptionSummary | None = None
    saas_support: SupportContactResponse | None = None
