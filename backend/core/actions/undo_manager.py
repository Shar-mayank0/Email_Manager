from __future__ import annotations

import json
import logging
from typing import Any, TypedDict, cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config.constants import STATUS_PENDING
from backend.core.actions.action_logger import mark_undone
from backend.db.repository import email_repo


logger = logging.getLogger(__name__)


class UndoResult(TypedDict):
	success: bool
	action_log_id: int
	gmail_id: str
	message: str


def undo_action(db: Session, service: Any, action_log_id: int) -> UndoResult:
	"""Undo one action_log entry by performing the reverse Gmail API operation."""
	_ensure_action_log_table(db)
	entry = _get_action_log_entry_by_id(db, action_log_id)
	if entry is None:
		return {
			"success": False,
			"action_log_id": int(action_log_id),
			"gmail_id": "",
			"message": "Action log entry not found",
		}

	gmail_id = str(entry.get("gmail_id") or "")
	action_type = str(entry.get("action_type") or "").strip().lower()
	action_detail = _parse_action_detail(entry.get("action_detail"))

	if bool(entry.get("undone")):
		return {
			"success": False,
			"action_log_id": int(entry.get("id") or action_log_id),
			"gmail_id": gmail_id,
			"message": "Action is already undone",
		}

	if not bool(entry.get("success")):
		return {
			"success": False,
			"action_log_id": int(entry.get("id") or action_log_id),
			"gmail_id": gmail_id,
			"message": "Cannot undo a failed action log entry",
		}

	undo_ok, undo_message = _reverse_action(service, gmail_id, action_type, action_detail)
	if not undo_ok:
		return {
			"success": False,
			"action_log_id": int(entry.get("id") or action_log_id),
			"gmail_id": gmail_id,
			"message": undo_message,
		}

	log_marked = mark_undone(db, int(entry.get("id") or action_log_id))
	if not log_marked:
		return {
			"success": False,
			"action_log_id": int(entry.get("id") or action_log_id),
			"gmail_id": gmail_id,
			"message": "Undo succeeded in Gmail but failed to mark action log as undone",
		}

	status_reset = _set_email_status_pending(db, gmail_id)
	if not status_reset:
		return {
			"success": False,
			"action_log_id": int(entry.get("id") or action_log_id),
			"gmail_id": gmail_id,
			"message": "Undo succeeded in Gmail but failed to reset email status to pending",
		}

	return {
		"success": True,
		"action_log_id": int(entry.get("id") or action_log_id),
		"gmail_id": gmail_id,
		"message": "Undo completed successfully",
	}


def undo_latest_for_email(db: Session, service: Any, gmail_id: str) -> UndoResult:
	"""Undo the latest successful non-undone action for a Gmail message."""
	_ensure_action_log_table(db)
	normalized_gmail_id = str(gmail_id or "").strip()
	if not normalized_gmail_id:
		return {
			"success": False,
			"action_log_id": 0,
			"gmail_id": "",
			"message": "gmail_id is required",
		}

	latest = db.execute(
		text(
			"""
			SELECT id
			FROM action_log
			WHERE gmail_id = :gmail_id
			  AND undone = 0
			  AND success = 1
			ORDER BY timestamp DESC, id DESC
			LIMIT 1
			"""
		),
		{"gmail_id": normalized_gmail_id},
	).mappings().first()

	if latest is None:
		return {
			"success": False,
			"action_log_id": 0,
			"gmail_id": normalized_gmail_id,
			"message": "No undoable action log entries found for this email",
		}

	return undo_action(db, service, int(latest.get("id") or 0))


def _reverse_action(
	service: Any,
	gmail_id: str,
	action_type: str,
	action_detail: dict[str, Any],
) -> tuple[bool, str]:
	label_name = _extract_label_name(action_detail)
	label_id = _resolve_label_id(service, label_name, action_detail)

	if action_type == "label":
		if not label_id:
			return False, "Cannot undo label action without resolvable label_id"
		return _modify_message(service, gmail_id, remove_label_ids=[label_id])

	if action_type in {"star", "star_email"}:
		return _modify_message(service, gmail_id, remove_label_ids=["STARRED"])

	if action_type in {"archive", "archive_email"}:
		return _modify_message(service, gmail_id, add_label_ids=["INBOX"])

	if action_type == "label_and_star":
		remove_ids = ["STARRED"]
		if label_id:
			remove_ids.append(label_id)
		return _modify_message(service, gmail_id, remove_label_ids=remove_ids)

	if action_type == "label_and_archive":
		remove_ids: list[str] = []
		if label_id:
			remove_ids.append(label_id)
		return _modify_message(service, gmail_id, add_label_ids=["INBOX"], remove_label_ids=remove_ids)

	if action_type in {"hold", "human_review"}:
		return False, "No Gmail action to undo for hold/human_review entries"

	return False, f"Unsupported action_type '{action_type}' for undo"


def _extract_label_name(action_detail: dict[str, Any]) -> str:
	label_name = str(action_detail.get("label_name") or "").strip()
	if label_name:
		return label_name

	steps = action_detail.get("steps")
	if isinstance(steps, list):
		for step in steps:
			if not isinstance(step, dict):
				continue
			if str(step.get("step") or "").strip() != "apply_label":
				continue
			detail = str(step.get("detail") or "").strip()
			if detail:
				return detail

	return ""


def _resolve_label_id(service: Any, label_name: str, action_detail: dict[str, Any]) -> str:
	label_id = str(action_detail.get("label_id") or "").strip()
	if label_id:
		return label_id

	if not label_name:
		return ""

	try:
		from backend.core.actions.gmail_actions import _label_cache
		cached_id = str(_label_cache.get(label_name) or "").strip()
		if cached_id:
			return cached_id
	except Exception:
		pass

	try:
		response = service.users().labels().list(userId="me").execute()
		for label in response.get("labels", []):
			if str(label.get("name") or "") != label_name:
				continue
			resolved = str(label.get("id") or "").strip()
			if resolved:
				return resolved
	except Exception as exc:
		logger.exception("Failed to resolve label_id for label_name=%s: %s", label_name, exc)

	return ""


def _modify_message(
	service: Any,
	gmail_id: str,
	add_label_ids: list[str] | None = None,
	remove_label_ids: list[str] | None = None,
) -> tuple[bool, str]:
	body: dict[str, Any] = {}
	if add_label_ids:
		body["addLabelIds"] = add_label_ids
	if remove_label_ids:
		body["removeLabelIds"] = remove_label_ids

	if not body:
		return False, "No reverse Gmail modification was generated"

	try:
		service.users().messages().modify(userId="me", id=gmail_id, body=body).execute()
		return True, "Gmail undo API call succeeded"
	except Exception as exc:
		logger.exception("Undo Gmail modify failed for gmail_id=%s: %s", gmail_id, exc)
		return False, f"Gmail undo failed: {exc}"


def _get_action_log_entry_by_id(db: Session, action_log_id: int) -> dict[str, Any] | None:
	if action_log_id <= 0:
		return None

	row = db.execute(
		text(
			"""
			SELECT id, gmail_id, action_type, action_detail, success, undone, timestamp
			FROM action_log
			WHERE id = :id
			LIMIT 1
			"""
		),
		{"id": int(action_log_id)},
	).mappings().first()

	if row is None:
		return None
	return dict(row)


def _parse_action_detail(raw: Any) -> dict[str, Any]:
	if isinstance(raw, dict):
		return raw

	if isinstance(raw, str):
		try:
			parsed = json.loads(raw)
		except (TypeError, ValueError, json.JSONDecodeError):
				return {}
		if isinstance(parsed, dict):
			return parsed

	return {}


def _set_email_status_pending(db: Session, gmail_id: str) -> bool:
	email = email_repo.get_email_by_gmail_id(db, gmail_id)
	if email is None:
		return False

	editable_email = cast(Any, email)
	editable_email.status = STATUS_PENDING
	db.commit()
	return True


def _ensure_action_log_table(db: Session) -> None:
	db.execute(
		text(
			"""
			CREATE TABLE IF NOT EXISTS action_log (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				gmail_id TEXT NOT NULL,
				action_type TEXT NOT NULL,
				action_detail TEXT NOT NULL,
				success INTEGER NOT NULL,
				timestamp DATETIME NOT NULL,
				undone INTEGER NOT NULL DEFAULT 0
			)
			"""
		)
	)
	db.commit()
