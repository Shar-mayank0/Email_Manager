from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config.constants import (
	CATEGORY_IMPORTANT,
	CATEGORY_PROMOTIONAL,
	CONFIDENCE_AUTO_ACT,
	SOURCE_MANUAL,
)
from backend.core.policy.policy_engine import ActionPlan, determine_action
from backend.db.repository import email_repo


HIGH_PRIORITY_RULE = 1000


def apply_override(
	db: Session,
	gmail_id: str,
	new_category: str,
	new_status: str,
) -> ActionPlan:
	"""Apply a user override and return the new action plan for execution."""
	normalized_gmail_id = str(gmail_id or "").strip()
	normalized_category = str(new_category or "").strip().upper()
	normalized_status = str(new_status or "").strip().lower()

	if not normalized_gmail_id:
		raise ValueError("gmail_id is required for apply_override")
	if not normalized_category:
		raise ValueError("new_category is required for apply_override")
	if not normalized_status:
		raise ValueError("new_status is required for apply_override")

	existing = email_repo.get_email_by_gmail_id(db, normalized_gmail_id)
	if existing is None:
		raise ValueError(f"Email with gmail_id '{normalized_gmail_id}' was not found")

	manual_confidence = 1.0
	updated = email_repo.update_email_classification(
		db=db,
		gmail_id=normalized_gmail_id,
		category=normalized_category,
		confidence=manual_confidence,
		classification_source=SOURCE_MANUAL,
		status=normalized_status,
	)
	if updated is None:
		raise ValueError(f"Failed to update email '{normalized_gmail_id}'")

	classification = {
		"category": normalized_category,
		"confidence": max(manual_confidence, CONFIDENCE_AUTO_ACT),
		"source": SOURCE_MANUAL,
	}
	return determine_action(classification)


def mark_always_important(db: Session, sender_email: str) -> dict[str, Any]:
	"""Persist a high-priority rule that always classifies a sender as IMPORTANT."""
	normalized_sender_email = str(sender_email or "").strip().lower()
	if not normalized_sender_email:
		raise ValueError("sender_email is required")

	return _upsert_rule(
		db=db,
		match_type="sender_email",
		match_value=normalized_sender_email,
		category=CATEGORY_IMPORTANT,
		priority=HIGH_PRIORITY_RULE,
	)


def mark_always_promotional(db: Session, sender_domain: str) -> dict[str, Any]:
	"""Persist a high-priority rule that always classifies a domain as PROMOTIONAL."""
	normalized_sender_domain = str(sender_domain or "").strip().lower().lstrip("@")
	if not normalized_sender_domain:
		raise ValueError("sender_domain is required")

	return _upsert_rule(
		db=db,
		match_type="sender_domain",
		match_value=normalized_sender_domain,
		category=CATEGORY_PROMOTIONAL,
		priority=HIGH_PRIORITY_RULE,
	)


def _upsert_rule(
	db: Session,
	match_type: str,
	match_value: str,
	category: str,
	priority: int,
) -> dict[str, Any]:
	"""Store or update a durable rule in the rules table."""
	_ensure_rules_table(db)

	now = datetime.now(timezone.utc).isoformat()
	existing = db.execute(
		text(
			"""
			SELECT id
			FROM rules
			WHERE match_type = :match_type AND match_value = :match_value
			LIMIT 1
			"""
		),
		{"match_type": match_type, "match_value": match_value},
	).fetchone()

	if existing is None:
		db.execute(
			text(
				"""
				INSERT INTO rules (
					match_type,
					match_value,
					category,
					priority,
					is_active,
					created_at,
					updated_at
				)
				VALUES (
					:match_type,
					:match_value,
					:category,
					:priority,
					1,
					:created_at,
					:updated_at
				)
				"""
			),
			{
				"match_type": match_type,
				"match_value": match_value,
				"category": category,
				"priority": priority,
				"created_at": now,
				"updated_at": now,
			},
		)
		db.commit()
		return {
			"match_type": match_type,
			"match_value": match_value,
			"category": category,
			"priority": priority,
			"created": True,
		}

	db.execute(
		text(
			"""
			UPDATE rules
			SET
				category = :category,
				priority = :priority,
				is_active = 1,
				updated_at = :updated_at
			WHERE match_type = :match_type AND match_value = :match_value
			"""
		),
		{
			"match_type": match_type,
			"match_value": match_value,
			"category": category,
			"priority": priority,
			"updated_at": now,
		},
	)
	db.commit()
	return {
		"match_type": match_type,
		"match_value": match_value,
		"category": category,
		"priority": priority,
		"created": False,
	}


def _ensure_rules_table(db: Session) -> None:
	# Ensure override persistence works even before full migrations are added.
	db.execute(
		text(
			"""
			CREATE TABLE IF NOT EXISTS rules (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				match_type TEXT NOT NULL,
				match_value TEXT NOT NULL,
				category TEXT NOT NULL,
				priority INTEGER NOT NULL DEFAULT 100,
				is_active INTEGER NOT NULL DEFAULT 1,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL,
				UNIQUE(match_type, match_value)
			)
			"""
		)
	)
	db.commit()
