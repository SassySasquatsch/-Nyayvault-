from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_client_ip, get_current_user, log_audit
from app.models import AuditAction, User, UserStatus
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user or not verify_password(payload.password, user.hashed_password):
        log_audit(
            db,
            action=AuditAction.login_failed,
            detail=f"Failed sign-in attempt for username '{payload.username}'",
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if user.role != payload.role:
        log_audit(
            db,
            action=AuditAction.login_failed,
            detail=(
                f"'{user.username}' attempted to sign in as {payload.role.value} "
                f"but is registered as {user.role.value}"
            ),
            user=user,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Selected role does not match this account's registered role.",
        )

    if user.status != UserStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is pending administrator approval.",
        )

    token = create_access_token({"sub": user.id, "role": user.role.value})
    log_audit(
        db,
        action=AuditAction.login,
        detail=f"'{user.username}' signed in as {user.role_label}",
        user=user,
        ip_address=ip,
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    log_audit(
        db,
        action=AuditAction.logout,
        detail=f"'{user.username}' signed out",
        user=user,
        ip_address=get_client_ip(request),
    )
    return {"detail": "Signed out."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
