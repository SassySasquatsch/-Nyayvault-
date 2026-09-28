"""
Case Document Lifecycle -- a read-only *view*, not a new record.

Nothing in here is stored. A case's lifecycle is assembled on request from
data NyayVault already keeps:

  audit_logs -> who did what, and when (upload, view, download, verify, ...)
  documents  -> document name, SHA-256 of record, integrity status,
                blockchain tx hash
  users      -> actor names

This module is deliberately free of FastAPI / SQLAlchemy imports so it can be
unit-tested with plain objects. Authentication and RBAC live in
app/routers/lifecycle.py, which reuses the existing `require_roles`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

SCOPE_FULL = "full"            # judge / io: every recorded event for the case
SCOPE_DOCUMENTS = "documents"  # forensic: document-linked events only
SCOPE_SECURITY = "security"    # admin: everything + IP addresses (audit view)

# audit action -> lifecycle stage (the UI uses this for colour + the flow strip)
STAGE_BY_ACTION = {
    "case_create": "case",
    "case_close": "case",
    "upload": "upload",
    "view": "access",
    "access_denied": "access",
    "download": "sharing",
    "present": "court",
    "verify": "verification",
    "tamper": "verification",
    "sign": "verification",
    "signature_verify": "verification",
    "redact": "processing",
    "transcribe": "processing",
    "blockchain_anchor": "anchoring",
    "blockchain_anchor_failed": "anchoring",
    "report": "report",
    "forensic_report_upload": "report",
    "court_order_upload": "report",
}

# Only what the audit event itself asserts. A plain "view" says nothing about
# integrity, so it gets None rather than a made-up claim.
INTEGRITY_BY_ACTION = {
    "upload": "hash_recorded",
    "forensic_report_upload": "hash_recorded",
    "court_order_upload": "hash_recorded",
    "verify": "verified",
    "tamper": "tampered",
    "sign": "signed",
    "blockchain_anchor": "anchored",
    "blockchain_anchor_failed": "not_anchored",
}

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def scope_for_role(role: str) -> str:
    if role == "forensic":
        return SCOPE_DOCUMENTS
    if role == "admin":
        return SCOPE_SECURITY
    return SCOPE_FULL


def _val(x: Any) -> Any:
    """Enum -> its value; anything else unchanged."""
    return x.value if hasattr(x, "value") else x


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes (stored as UTC). Make them explicit
    so the browser doesn't misread them as local time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_versions(docs: Iterable[Any]) -> dict:
    """
    NyayVault has no document-version registry, and no modify/replace
    endpoint: re-uploading a corrected file simply creates a new Document row.
    So versions are *inferred*: within one case, documents that share a file
    name are numbered v1, v2, ... in upload order. Read-only, no schema change.

    Returns {doc_id: {version, version_count, supersedes_document_id,
                      same_content_as_previous}}.
    """
    groups: dict = {}
    for d in sorted(docs, key=lambda d: (_utc(d.uploaded_at) or _EPOCH, d.id)):
        groups.setdefault(d.name, []).append(d)

    out = {}
    for group in groups.values():
        for i, d in enumerate(group):
            prev = group[i - 1] if i else None
            out[d.id] = {
                "version": i + 1,
                "version_count": len(group),
                "supersedes_document_id": prev.id if prev else None,
                "same_content_as_previous": (
                    prev.hash_sha256 == d.hash_sha256 if prev else None
                ),
            }
    return out


def build_case_lifecycle(
    *,
    logs: Iterable[Any],
    docs: Iterable[Any],
    users_by_id: dict,
    viewer_role: str,
    document_id: Optional[str] = None,
) -> dict:
    """
    `logs` must already be in chronological order (oldest first) and limited
    to one case. Returns plain dicts; the router validates them against its
    response model.
    """
    docs = list(docs)
    scope = scope_for_role(viewer_role)
    docs_by_id = {d.id: d for d in docs}
    versions = compute_versions(docs)

    events = []
    for log in logs:
        doc_id = log.document_id
        if document_id and doc_id != document_id:
            continue
        if scope == SCOPE_DOCUMENTS and not doc_id:
            continue  # forensic: document lifecycle only, no case-level events

        action = _val(log.action)
        doc = docs_by_id.get(doc_id)
        ver = versions.get(doc_id, {})
        actor = users_by_id.get(log.user_id)

        stage = STAGE_BY_ACTION.get(action, "other")
        if action in ("upload", "forensic_report_upload") and ver.get("version", 1) > 1:
            stage = "version"  # same file name uploaded again -> new version

        events.append({
            "id": log.id,
            "timestamp": _utc(log.timestamp),
            "action": action,
            "stage": stage,
            "actor_name": actor.full_name if actor else None,
            "actor_role": log.role,  # role at the time of the action
            "detail": log.detail or "",
            "document_id": doc_id,
            "document_name": doc.name if doc else None,
            "version": ver.get("version"),
            "version_count": ver.get("version_count"),
            "supersedes_document_id": ver.get("supersedes_document_id"),
            "same_content_as_previous": ver.get("same_content_as_previous"),
            # NyayVault does not capture a reason for change today.
            "reason": None,
            "hash_sha256": doc.hash_sha256 if doc else None,
            "integrity_status": INTEGRITY_BY_ACTION.get(action) if doc else None,
            "current_status": _val(doc.status) if doc else None,
            "blockchain_tx_hash": doc.blockchain_tx_hash if doc else None,
            # IP addresses are security/audit information: admin only.
            "ip_address": log.ip_address if scope == SCOPE_SECURITY else None,
        })

    documents = [
        {
            "id": d.id,
            "name": d.name,
            "version": versions[d.id]["version"],
            "version_count": versions[d.id]["version_count"],
            "hash_sha256": d.hash_sha256,
            "status": _val(d.status),
            "blockchain_tx_hash": d.blockchain_tx_hash,
            "uploaded_at": _utc(d.uploaded_at),
        }
        for d in sorted(docs, key=lambda d: (_utc(d.uploaded_at) or _EPOCH, d.id))
    ]

    return {"scope": scope, "total": len(events), "documents": documents, "events": events}
