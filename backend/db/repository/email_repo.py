import json
from typing import Any, cast

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.config.constants import CATEGORY_UNCLASSIFIED, STATUS_PENDING
from backend.db.models.email import Email


_GMAIL_ID_COL = cast(InstrumentedAttribute[str], Email.gmail_id)
_STATUS_COL = cast(InstrumentedAttribute[str], Email.status)
_RECEIVED_AT_COL = cast(InstrumentedAttribute[Any], Email.received_at)


def save_email(db: Session, email_dict: dict[str, Any]) -> Email:
	gmail_id = str(email_dict.get("gmail_id") or email_dict.get("email_id") or "").strip()
	if not gmail_id:
		raise ValueError("email_dict must include gmail_id or email_id")

	existing_email = get_email_by_gmail_id(db, gmail_id)
	if existing_email is not None:
		return existing_email

	email = Email(
		gmail_id=gmail_id,
		thread_id=str(email_dict.get("thread_id", "")),
		subject=str(email_dict.get("subject", "")),
		sender_raw=str(email_dict.get("sender_raw", "")),
		sender_name=str(email_dict.get("sender_name", "")),
		sender_email=str(email_dict.get("sender_email", "")),
		sender_domain=str(email_dict.get("sender_domain", "")),
		received_at=email_dict.get("received_at"),
		labels=json.dumps(email_dict.get("labels", [])),
		snippet=str(email_dict.get("snippet", "")),
		has_attachment=bool(email_dict.get("has_attachment", False)),
		body_plain=str(email_dict.get("body_plain", "")),
		body_html=str(email_dict.get("body_html", "")),
		category=str(email_dict.get("category", CATEGORY_UNCLASSIFIED)),
		confidence=email_dict.get("confidence"),
		classification_source=email_dict.get("classification_source"),
		status=str(email_dict.get("status", STATUS_PENDING)),
	)

	db.add(email)
	db.commit()
	db.refresh(email)
	return email


def get_email_by_gmail_id(db: Session, gmail_id: str) -> Email | None:
	return db.query(Email).filter(_GMAIL_ID_COL == gmail_id).first()


def get_pending_emails(db: Session, limit: int = 50) -> list[Email]:
	safe_limit = max(0, limit)
	return (
		db.query(Email)
		.filter(_STATUS_COL == STATUS_PENDING)
		.order_by(_RECEIVED_AT_COL.desc())
		.limit(safe_limit)
		.all()
	)


def get_all_emails(db: Session, limit: int = 50, offset: int = 0) -> list[Email]:
	safe_limit = max(0, limit)
	safe_offset = max(0, offset)
	return (
		db.query(Email)
		.order_by(_RECEIVED_AT_COL.desc())
		.offset(safe_offset)
		.limit(safe_limit)
		.all()
	)


def update_email_classification(
	db: Session,
	gmail_id: str,
	category: str,
	confidence: float,
	classification_source: str,
	status: str,
) -> Email | None:
	email = get_email_by_gmail_id(db, gmail_id)
	if email is None:
		return None

	editable_email = cast(Any, email)
	editable_email.category = category
	editable_email.confidence = confidence
	editable_email.classification_source = classification_source
	editable_email.status = status

	db.commit()
	db.refresh(email)
	return email
