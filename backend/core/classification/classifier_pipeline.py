from typing import Any

from sqlalchemy.orm import Session

from backend.config.constants import (
	CONFIDENCE_AUTO_ACT,
	CONFIDENCE_HUMAN_REVIEW,
	STATUS_APPROVED,
	STATUS_PENDING,
	STATUS_PENDING_REVIEW,
)
from backend.core.classification.llm_classifier import classify_with_llm
from backend.core.classification.rule_engine import apply_rules
from backend.db.models.email import Email
from backend.db.repository import email_repo


def _normalize_confidence(value: Any) -> float:
	try:
		confidence = float(value)
	except (TypeError, ValueError):
		return 0.0

	if confidence < 0.0:
		return 0.0
	if confidence > 1.0:
		return 1.0
	return confidence


def classify_email(email_dict: dict[str, Any]) -> dict[str, Any]:
	result = apply_rules(email_dict)
	if result is None:
		result = classify_with_llm(email_dict)

	normalized = dict(result)
	confidence = _normalize_confidence(normalized.get("confidence"))
	normalized["confidence"] = confidence

	if confidence >= CONFIDENCE_AUTO_ACT:
		status = STATUS_APPROVED
	elif confidence >= CONFIDENCE_HUMAN_REVIEW:
		status = STATUS_PENDING_REVIEW
	else:
		status = STATUS_PENDING

	normalized["status"] = status
	return normalized


def classify_and_save(db: Session, email_dict: dict[str, Any]) -> Email:
	classification = classify_email(email_dict)
	gmail_id = str(email_dict.get("gmail_id") or email_dict.get("email_id") or "").strip()
	if not gmail_id:
		raise ValueError("email_dict must include gmail_id or email_id")

	updated = email_repo.update_email_classification(
		db=db,
		gmail_id=gmail_id,
		category=str(classification.get("category", "")),
		confidence=float(classification.get("confidence", 0.0)),
		classification_source=str(classification.get("source", "")),
		status=str(classification.get("status", STATUS_PENDING)),
	)
	if updated is not None:
		return updated

	created = email_repo.save_email(
		db,
		{
			**email_dict,
			"gmail_id": gmail_id,
			"category": classification.get("category"),
			"confidence": classification.get("confidence"),
			"classification_source": classification.get("source"),
			"status": classification.get("status"),
		},
	)
	return created
