"""
Case Document Lifecycle -- read-only.

GET /api/cases/{case_id}/lifecycle[?document_id=...]

There is intentionally no POST / PUT / PATCH / DELETE here (FastAPI answers
405 for them): lifecycle history is a view over the append-only audit log
and the documents table, never a store of its own.

Access control = the app's existing RBAC (`require_roles`) plus ABAC
(app/abac.py): the caller's organisational scope must match the case's and,
for an IO, the case must be assigned to them. What differs by role, once
access is granted, is *how much* of the lifecycle they see
(see app/utils/lifecycle.py:scope_for_role):

  judge, io -> every recorded event for the case
  forensic  -> document-linked events only (evidence / forensic lifecycle)
  admin     -> everything, plus IP addresses (security/audit view)

Anyone else -- unauthenticated (401), pending accounts or any other role
(403) -- gets nothing.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.abac import Action, get_authorised_case
from app.database import engine, get_db
from app.dependencies import require_roles
from app.models import AuditLog, Case, User
from app.utils.lifecycle import build_case_lifecycle

router = APIRouter(prefix="/api/cases", tags=["lifecycle"])

# Same role codes the rest of the app uses; nothing new is introduced.
LIFECYCLE_ROLES = ("io", "forensic", "judge", "admin")


class LifecycleEvent(BaseModel):
    id: str                                   # audit log id
    timestamp: datetime
    action: str                               # existing AuditAction value
    stage: str                                # upload / access / version / ...
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None          # role code at the time
    detail: str = ""
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    version: Optional[int] = None             # inferred, see compute_versions()
    version_count: Optional[int] = None
    supersedes_document_id: Optional[str] = None
    same_content_as_previous: Optional[bool] = None
    reason: Optional[str] = None              # not captured by NyayVault today
    hash_sha256: Optional[str] = None
    integrity_status: Optional[str] = None    # what *this event* asserts
    current_status: Optional[str] = None      # document status right now
    blockchain_tx_hash: Optional[str] = None
    ip_address: Optional[str] = None          # admin only


class LifecycleDocument(BaseModel):
    id: str
    name: str
    version: int
    version_count: int
    hash_sha256: str
    status: str
    blockchain_tx_hash: Optional[str] = None
    uploaded_at: Optional[datetime] = None


class LifecycleOut(BaseModel):
    case_id: str
    case_number: str
    case_title: str
    viewer_role: str
    scope: str                                # full / documents / security
    read_only: bool = True
    total: int
    documents: list[LifecycleDocument]
    events: list[LifecycleEvent]


@router.get("/{case_id}/lifecycle", response_model=LifecycleOut)
def get_case_lifecycle(
    case_id: str,
    request: Request,
    document_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*LIFECYCLE_ROLES)),
):
    # RBAC (require_roles above) + ABAC: scope match and, for an IO, assignment.
    case = get_authorised_case(db, user, case_id, Action.CASE_LIFECYCLE, request=request)
    if document_id and document_id not in {d.id for d in case.documents}:
        raise HTTPException(404, "Document not found in this case.")

    q = db.query(AuditLog).filter(AuditLog.case_id == case.id)
    if document_id:
        q = q.filter(AuditLog.document_id == document_id)
    q = q.order_by(AuditLog.timestamp.asc())
    if engine.dialect.name == "sqlite":
        # SQLite's CURRENT_TIMESTAMP only has 1-second resolution, so e.g. an
        # upload and its follow-up event usually tie. rowid = insertion order.
        q = q.order_by(text("audit_logs.rowid ASC"))
    logs = q.all()

    user_ids = {l.user_id for l in logs if l.user_id}
    users_by_id = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )

    role_value = user.role.value if hasattr(user.role, "value") else user.role
    data = build_case_lifecycle(
        logs=logs,
        docs=case.documents,
        users_by_id=users_by_id,
        viewer_role=role_value,
        document_id=document_id,
    )
    return {
        "case_id": case.id,
        "case_number": case.number,
        "case_title": case.title,
        "viewer_role": role_value,
        "read_only": True,
        **data,
    }
