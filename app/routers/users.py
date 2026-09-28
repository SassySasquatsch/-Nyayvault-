import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_client_ip, log_audit, require_roles
from app.models import AuditAction, User, UserStatus
from app.schemas import UserCreate, UserCreatedOut, UserOut
from app.security import hash_password
from app.utils.signing import SigningError, generate_keypair

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserCreatedOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "Username already exists.")
    if db.query(User).filter(User.badge_id == payload.badge_id).first():
        raise HTTPException(400, "Badge ID already exists.")

    temp_password = payload.password or secrets.token_urlsafe(9)

    # Every user gets their own signing keypair at account creation, so any
    # forensic report, court order/judgment, or case-closure action they
    # later take can be non-repudiably attributed to them (see
    # app/utils/signing.py). If the 'cryptography' library isn't installed,
    # this degrades gracefully -- the account is still created without keys,
    # and every signing call site elsewhere skips signing rather than
    # failing the action or fabricating a signature.
    public_key_pem = private_key_encrypted_pem = None
    try:
        keypair = generate_keypair()
        public_key_pem = keypair.public_key_pem
        private_key_encrypted_pem = keypair.private_key_encrypted_pem
    except SigningError:
        pass

    user = User(
        full_name=payload.full_name,
        username=payload.username,
        badge_id=payload.badge_id,
        role=payload.role,
        state=payload.state,
        district=payload.district,
        unit=payload.unit,
        status=UserStatus.pending,
        hashed_password=hash_password(temp_password),
        public_key_pem=public_key_pem,
        private_key_encrypted_pem=private_key_encrypted_pem,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        action=AuditAction.user_create,
        detail=f"'{admin.username}' created new user '{user.username}' ({user.role.value})",
        user=admin,
        ip_address=get_client_ip(request),
    )
    return UserCreatedOut(user=UserOut.model_validate(user), temporary_password=temp_password)


@router.post("/{user_id}/approve", response_model=UserOut)
def approve_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found.")
    user.status = UserStatus.approved
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        action=AuditAction.approve,
        detail=f"'{admin.username}' approved '{user.username}'",
        user=admin,
        ip_address=get_client_ip(request),
    )
    return user


@router.post("/{user_id}/revoke", response_model=UserOut)
def revoke_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found.")
    user.status = UserStatus.pending
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        action=AuditAction.revoke,
        detail=f"'{admin.username}' revoked access for '{user.username}'",
        user=admin,
        ip_address=get_client_ip(request),
    )
    return user
