from __future__ import annotations

import json
from datetime import datetime
from typing import Any, TypedDict, cast

from sqlalchemy import text
from sqlalchemy.orm import Session


class ActionLogEntry(TypedDict):
	id: int
	gmail_id: str
	action_type: str
	action_detail: dict[str, Any]
	success: bool
	timestamp: datetime
	undone: bool


def log_action(
	db: Session,
	gmail_id: str,
	action_type: str,
	action_detail: dict[str, Any],
	success: bool,
) -> ActionLogEntry:
	"""Write one Gmail action attempt into the action log table."""
	_ensure_action_log_table(db)

	normalized_gmail_id = str(gmail_id or "").strip()
	normalized_action_type = str(action_type or "").strip().lower()
	if not normalized_gmail_id:
		raise ValueError("gmail_id is required")
	if not normalized_action_type:
		raise ValueError("action_type is required")

	payload = action_detail if isinstance(action_detail, dict) else {"detail": action_detail}
	timestamp = datetime.utcnow()

	insert_result = db.execute(
		text(
			"""
			INSERT INTO action_log (
				gmail_id,
				action_type,
				action_detail,
				success,
				timestamp,
				undone
			)
			VALUES (
				:gmail_id,
				:action_type,
				:action_detail,
				:success,
				:timestamp,
				0
			)
			"""
		),
		{
			"gmail_id": normalized_gmail_id,
			"action_type": normalized_action_type,
			"action_detail": json.dumps(payload, default=str),
			"success": bool(success),
			"timestamp": timestamp,
		},
	)
	db.commit()

	row_id = int(getattr(cast(Any, insert_result), "lastrowid", 0) or 0)
	return {
		"id": row_id,
		"gmail_id": normalized_gmail_id,
		"action_type": normalized_action_type,
		"action_detail": payload,
		"success": bool(success),
		"timestamp": timestamp,
		"undone": False,
	}


def log_hold(db: Session, gmail_id: str, reason: str) -> ActionLogEntry:
	"""Record that no Gmail write occurred because policy routed this email to hold/review."""
	return log_action(
		db=db,
		gmail_id=gmail_id,
		action_type="hold",
		action_detail={"reason": str(reason or "").strip()},
		success=True,
	)


def get_action_log(db: Session, gmail_id: str) -> list[ActionLogEntry]:
	"""Return all action log entries for a Gmail message, oldest first."""
	_ensure_action_log_table(db)

	normalized_gmail_id = str(gmail_id or "").strip()
	if not normalized_gmail_id:
		return []

	rows = db.execute(
		text(
			"""
			SELECT id, gmail_id, action_type, action_detail, success, timestamp, undone
			FROM action_log
			WHERE gmail_id = :gmail_id
			ORDER BY timestamp ASC, id ASC
			"""
		),
		{"gmail_id": normalized_gmail_id},
	).mappings().all()

	entries: list[ActionLogEntry] = []
	for row in rows:
		action_detail_raw = row.get("action_detail")
		action_detail: dict[str, Any]
		if isinstance(action_detail_raw, str):
			try:
				parsed = json.loads(action_detail_raw)
			except (TypeError, ValueError, json.JSONDecodeError):
				parsed = {"raw": action_detail_raw}
			action_detail = parsed if isinstance(parsed, dict) else {"raw": parsed}
		else:
			action_detail = {}

		timestamp_value = row.get("timestamp")
		timestamp = timestamp_value if isinstance(timestamp_value, datetime) else datetime.utcnow()

		entries.append(
			{
				"id": int(row.get("id") or 0),
				"gmail_id": str(row.get("gmail_id") or ""),
				"action_type": str(row.get("action_type") or ""),
				"action_detail": action_detail,
				"success": bool(row.get("success")),
				"timestamp": timestamp,
				"undone": bool(row.get("undone")),
			}
		)

	return entries


def mark_undone(db: Session, action_log_id: int) -> bool:
	"""Mark one action log entry as undone after a successful undo action."""
	_ensure_action_log_table(db)

	if action_log_id <= 0:
		return False

	result = db.execute(
		text(
			"""
			UPDATE action_log
			SET undone = 1
			WHERE id = :id
			"""
		),
		{"id": int(action_log_id)},
	)
	db.commit()
	return int(getattr(cast(Any, result), "rowcount", 0) or 0) > 0


def _ensure_action_log_table(db: Session) -> None:
	"""Create the action_log table when migrations are not yet in place."""
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
