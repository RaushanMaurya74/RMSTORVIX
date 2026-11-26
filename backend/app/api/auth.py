"""Authentication API endpoints (register, login, logout, password reset, current session)."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_authenticated_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangeUserPasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserSummary,
)
from app.schemas.business import BusinessProfileResponse
from app.services.auth_service import (
    authenticate_user,
    change_own_user_password,
    register_user_and_business,
    request_password_reset_notification,
    revoke_session,
)
from app.services.saas_service import build_subscription_summary, get_support_contact

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_session_cookie(response: Response, raw_token: str, *, remember_me: bool = False) -> None:
    settings = get_settings()
    max_age = 30 * 24 * 3600 if remember_me else settings.session_ttl_hours * 3600
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.effective_cookie_secure,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.effective_cookie_secure,
        path="/",
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new business owner in PENDING_APPROVAL + NOT_ACTIVATED state",
)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Create a pending-approval user, business profile, and scoped session."""
    user, business, raw_token = register_user_and_business(db, payload)
    _set_session_cookie(response, raw_token, remember_me=False)
    return AuthResponse(
        user=UserSummary.model_validate(user),
        business=BusinessProfileResponse.model_validate(business),
        subscription=build_subscription_summary(db, business=business, user=user),
        saas_support=get_support_contact(db),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in with email and password",
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Authenticate user credentials and issue a session cookie."""
    user, business, raw_token = authenticate_user(db, payload)
    _set_session_cookie(response, raw_token, remember_me=payload.remember_me)
    return AuthResponse(
        user=UserSummary.model_validate(user),
        business=BusinessProfileResponse.model_validate(business),
        subscription=build_subscription_summary(db, business=business, user=user),
        saas_support=get_support_contact(db),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Sign out and revoke the active session",
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke the server-side session and clear the session cookie."""
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    revoke_session(db, raw_token)
    _clear_session_cookie(response)
    return {"status": "logged_out"}


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request an administrator-assisted password reset",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Record a reset request notification for admins without leaking account existence."""
    request_password_reset_notification(db, payload)
    return {
        "message": (
            "If an account exists for that email address, your password reset request has "
            "been forwarded to the administrator."
        )
    }


@router.post(
    "/change-password",
    response_model=UserSummary,
    summary="Change the signed-in user's password",
)
def change_password(
    payload: ChangeUserPasswordRequest,
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> UserSummary:
    updated = change_own_user_password(db, user=current_user, payload=payload)
    return UserSummary.model_validate(updated)


@router.get(
    "/me",
    response_model=AuthResponse,
    summary="Return the currently authenticated user, approval state, and subscription",
)
def read_current_session(
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Return authenticated session context including approval and subscription state."""
    return AuthResponse(
        user=UserSummary.model_validate(current_user),
        business=BusinessProfileResponse.model_validate(current_user.business),
        subscription=build_subscription_summary(
            db, business=current_user.business, user=current_user
        ),
        saas_support=get_support_contact(db),
    )
