from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from backend.config.constants import (
	CATEGORY_TRASH,
	CONFIDENCE_HUMAN_REVIEW,
	STATUS_ACTIONED,
	STATUS_PENDING_REVIEW,
)


RECENT_EMAIL_HOLD_WINDOW = timedelta(minutes=15)


class PolicyViolationError(Exception):
	def __init__(self, reason: str, email_id: str, check_name: str) -> None:
		self.reason = reason
		self.email_id = email_id
		self.check_name = check_name
		super().__init__(f"{check_name} failed for email '{email_id}': {reason}")


def run_safety_checks(email_dict: dict[str, Any], classification: dict[str, Any]) -> bool:
	"""Run hard safety checks before any automated Gmail action is executed."""
	classification.setdefault("gmail_id", _extract_email_id(email_dict))
	classification.setdefault("email_id", _extract_email_id(email_dict))

	_check_not_already_actioned(email_dict)
	_check_has_gmail_id(email_dict)
	_check_confidence_threshold(classification)
	_check_no_trash_action(classification)
	_check_received_recently(email_dict)
	return True


def _check_not_already_actioned(email_dict: dict[str, Any]) -> None:
	status = str(email_dict.get("status") or "").strip().lower()
	if status == STATUS_ACTIONED:
		raise PolicyViolationError(
			reason="Email is already actioned; refusing to apply actions twice.",
			email_id=_extract_email_id(email_dict),
			check_name="_check_not_already_actioned",
		)


def _check_has_gmail_id(email_dict: dict[str, Any]) -> None:
	gmail_id = str(email_dict.get("gmail_id") or "").strip()
	if not gmail_id:
		raise PolicyViolationError(
			reason="Missing gmail_id; Gmail API action cannot be executed.",
			email_id=_extract_email_id(email_dict),
			check_name="_check_has_gmail_id",
		)


def _check_confidence_threshold(classification: dict[str, Any]) -> None:
	email_id = _extract_email_id(classification)
	try:
		confidence = float(classification.get("confidence", 0.0))
	except (TypeError, ValueError):
		confidence = 0.0

	if confidence < CONFIDENCE_HUMAN_REVIEW:
		raise PolicyViolationError(
			reason=(
				f"Classification confidence {confidence:.2f} is below "
				f"human-review threshold {CONFIDENCE_HUMAN_REVIEW:.2f}."
			),
			email_id=email_id,
			check_name="_check_confidence_threshold",
		)


def _check_no_trash_action(classification: dict[str, Any]) -> None:
	email_id = _extract_email_id(classification)
	category = str(classification.get("category") or "").strip().upper()
	if category == CATEGORY_TRASH:
		classification["status"] = STATUS_PENDING_REVIEW
		raise PolicyViolationError(
			reason="TRASH classifications must go to human review; auto-action is disabled in v1.",
			email_id=email_id,
			check_name="_check_no_trash_action",
		)


def _check_received_recently(email_dict: dict[str, Any]) -> None:
	received_at = _coerce_datetime(email_dict.get("received_at"))
	if received_at is None:
		return

	now_utc = datetime.now(timezone.utc)
	received_utc = _to_utc(received_at)
	if now_utc - received_utc < RECENT_EMAIL_HOLD_WINDOW:
		raise PolicyViolationError(
			reason="Email was received within the last 15 minutes and is held for human review.",
			email_id=_extract_email_id(email_dict),
			check_name="_check_received_recently",
		)


def _extract_email_id(payload: dict[str, Any]) -> str:
	return str(
		payload.get("gmail_id")
		or payload.get("email_id")
		or payload.get("id")
		or "unknown"
	).strip() or "unknown"


def _coerce_datetime(value: Any) -> datetime | None:
	if isinstance(value, datetime):
		return value

	if isinstance(value, (int, float)):
		try:
			return datetime.fromtimestamp(float(value), tz=timezone.utc)
		except (TypeError, ValueError, OSError):
			return None

	if not isinstance(value, str):
		return None

	raw = value.strip()
	if not raw:
		return None

	try:
		return datetime.fromisoformat(raw.replace("Z", "+00:00"))
	except ValueError:
		pass

	try:
		return parsedate_to_datetime(raw)
	except (TypeError, ValueError):
		return None


def _to_utc(value: datetime) -> datetime:
	if value.tzinfo is None:
		return value.replace(tzinfo=timezone.utc)
	return value.astimezone(timezone.utc)
