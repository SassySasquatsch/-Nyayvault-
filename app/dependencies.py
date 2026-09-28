from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditAction, AuditLog, User, UserStatus
from app.security import decode_access_token

# tokenUrl is documentation-only here since login is a JSON POST, not the
# OAuth2 form flow -- Swagger UI still renders the "Authorize" button fine.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    payload = decode_access_token(token)
    if not payload:
        raise credentials_error

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_error
    if user.status != UserStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending administrator approval.",
        )
    return user


def require_roles(*roles: str):
    """Dependency factory: require_roles('admin', 'io') -> 403 for anyone else."""

    def checker(user: User = Depends(get_current_user)) -> User:
        role_value = user.role.value if hasattr(user.role, "value") else user.role
        if role_value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of the following roles: {', '.join(roles)}.",
            )
        return user

    return checker


def log_audit(
    db: Session,
    *,
    action: AuditAction,
    detail: str,
    user: User = None,
    ip_address: str = None,
    case_id: str = None,
    document_id: str = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        role=(user.role.value if user and hasattr(user.role, "value") else (user.role if user else None)),
        ip_address=ip_address,
        action=action,
        detail=detail,
        case_id=case_id,
        document_id=document_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
