from __future__ import annotations

import json
import time
from typing import Any, cast

from backend.config.constants import (
    CATEGORY_TRASH,
    CATEGORY_UNCLASSIFIED,
    STATUS_ACTIONED,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_PENDING_REVIEW,
)
from backend.core.actions.action_logger import log_action, log_hold
from backend.core.actions.gmail_actions import (
    _label_cache,
    apply_action_plan,
    ensure_labels_exist,
)
from backend.core.classification.classifier_pipeline import classify_and_save
from backend.core.ingestion.gmail_client import get_gmail_service
from backend.core.ingestion.sync_manager import fetch_new_emails
from backend.core.policy.policy_engine import evaluate
from backend.db.models.email import Email
from backend.db.repository import email_repo
from backend.db.session import Base, SessionLocal, engine


# ── 1. Bootstrap ──────────────────────────────────────────────────────────────

def bootstrap() -> Any:
    """Create all DB tables and Gmail labels, return authenticated service."""
    print("── Bootstrapping ──────────────────────────────────────")
    Base.metadata.create_all(bind=engine)
    print("  ✓ Database tables ready")

    service = get_gmail_service()
    print("  ✓ Gmail authenticated")

    labels = ensure_labels_exist(service)
    print(f"  ✓ EmailBot labels ready: {list(labels.keys())}")

    return service


# ── 2. Fetch & Save ───────────────────────────────────────────────────────────

def fetch_and_save(service: Any) -> int:
    """Fetch new emails from Gmail and save them to the DB."""
    print("\n── Fetching Emails ────────────────────────────────────")
    emails = fetch_new_emails(service)
    print(f"  Fetched {len(emails)} emails from Gmail")

    db = SessionLocal()
    saved = 0
    try:
        for email_dict in emails:
            result = email_repo.save_email(db, email_dict)
            if result:
                saved += 1
        print(f"  ✓ Saved {saved} new emails to DB")
    finally:
        db.close()

    return saved


# ── 3. Classify ───────────────────────────────────────────────────────────────

def classify_all() -> None:
    """Classify all unclassified emails using rule engine + LLM."""
    print("\n── Classifying Emails ─────────────────────────────────")
    db = SessionLocal()
    try:
        unclassified = (
            db.query(Email)
            .filter(Email.category == CATEGORY_UNCLASSIFIED)
            .all()
        )
        print(f"  Found {len(unclassified)} unclassified emails")

        for email in unclassified:
            editable = cast(Any, email)
            email_dict = {
                col.name: getattr(editable, col.name)
                for col in email.__table__.columns
            }
            email_dict["email_id"] = email_dict.get("gmail_id", "")

            # parse labels if stored as JSON string
            labels_raw = email_dict.get("labels")
            if isinstance(labels_raw, str):
                try:
                    email_dict["labels"] = json.loads(labels_raw)
                except (ValueError, json.JSONDecodeError):
                    email_dict["labels"] = []

            result = classify_and_save(db, email_dict)
            editable_result = cast(Any, result)

            # force TRASH to pending_review, never approved
            if str(editable_result.category or "").upper() == CATEGORY_TRASH:
                editable_result.status = STATUS_PENDING_REVIEW
                db.commit()

            source = str(editable_result.classification_source or "")
            print(
                f"  {str(editable_result.subject or '')[:40]:<40} "
                f"→ {editable_result.category} "
                f"({editable_result.confidence}) [{source}]"
            )

    finally:
        db.close()


# ── 4. Act ────────────────────────────────────────────────────────────────────

def act_on_approved(service: Any) -> None:
    """Apply Gmail actions to all approved emails."""
    print("\n── Acting on Approved Emails ──────────────────────────")
    db = SessionLocal()
    try:
        approved = (
            db.query(Email)
            .filter(
                Email.status == STATUS_APPROVED,
                Email.category != CATEGORY_UNCLASSIFIED,
                Email.category != CATEGORY_TRASH,
            )
            .all()
        )
        print(f"  Found {len(approved)} approved emails to act on")

        for email in approved:
            editable = cast(Any, email)
            gmail_id = str(editable.gmail_id or "").strip()
            if not gmail_id:
                print("  Skipping email with missing gmail_id")
                continue

            email_dict = {
                col.name: getattr(editable, col.name)
                for col in email.__table__.columns
            }
            classification = {
                "category": str(editable.category or "").upper(),
                "confidence": float(editable.confidence or 0.0),
                "source": str(editable.classification_source or ""),
            }

            # policy evaluation
            action_plan = evaluate(db, email_dict, classification)
            action_type = action_plan["action_type"]

            print(
                f"  {str(editable.subject or '')[:35]:<35} "
                f"→ {action_type:<20} | {action_plan['reason'][:40]}"
            )

            # execute Gmail action
            result = apply_action_plan(service, gmail_id, action_plan, _label_cache)

            # log the action
            if action_type in {"hold", "human_review"}:
                log_hold(db, gmail_id, action_plan["reason"])
            else:
                label_name = str(action_plan.get("label_name") or "").strip()
                log_action(
                    db,
                    gmail_id,
                    action_type,
                    {
                        "steps": result["steps"],
                        "reason": result["reason"],
                        "label_name": label_name,
                        "label_id": _label_cache.get(label_name, "") if label_name else "",
                        "error": result["error"],
                    },
                    result["success"],
                )

            # update status to actioned if Gmail call succeeded
            if result["success"] and action_type not in {"hold", "human_review"}:
                email_repo.update_email_classification(
                    db=db,
                    gmail_id=gmail_id,
                    category=str(editable.category or "").upper(),
                    confidence=float(editable.confidence or 0.0),
                    classification_source=str(editable.classification_source or ""),
                    status=STATUS_ACTIONED,
                )
                print(f"    ✓ Actioned | Gmail: {result['success']}")
            else:
                print(f"    ↷ Held/Reviewed | reason: {action_plan['reason'][:60]}")

    finally:
        db.close()


# ── 5. Summary ────────────────────────────────────────────────────────────────

def print_summary() -> None:
    """Print a breakdown of email statuses and categories."""
    print("\n── Summary ────────────────────────────────────────────")
    db = SessionLocal()
    try:
        from sqlalchemy import func
        status_counts = (
            db.query(Email.status, func.count())
            .group_by(Email.status)
            .all()
        )
        print("  Status breakdown:")
        for status, count in status_counts:
            print(f"    {str(status):<20} {count}")

        category_counts = (
            db.query(Email.category, func.count())
            .group_by(Email.category)
            .all()
        )
        print("  Category breakdown:")
        for category, count in category_counts:
            print(f"    {str(category):<20} {count}")
    finally:
        db.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    service = bootstrap()
    fetch_and_save(service)
    classify_all()
    act_on_approved(service)
    print_summary()


if __name__ == "__main__":
    main()