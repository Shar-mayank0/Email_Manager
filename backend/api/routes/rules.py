from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db


router = APIRouter()


class RuleCreateRequest(BaseModel):
	match_type: str
	match_value: str
	category: str
	priority: int = 100


class RuleToggleRequest(BaseModel):
	is_active: bool


@router.get("")
def list_rules(db: Session = Depends(get_db)) -> dict[str, Any]:
	_ensure_rules_table_schema(db)
	rows = db.execute(
		text(
			"""
			SELECT id, match_type, match_value, category, priority, match_count, is_active, created_at, updated_at
			FROM rules
			WHERE is_active = 1
			ORDER BY priority DESC, id DESC
			"""
		)
	).mappings().all()

	items = [dict(row) for row in rows]
	return {"items": items, "total": len(items)}


@router.post("")
def create_rule(payload: RuleCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
	_ensure_rules_table_schema(db)

	match_type = payload.match_type.strip()
	match_value = payload.match_value.strip().lower()
	category = payload.category.strip().upper()
	if not match_type or not match_value or not category:
		raise HTTPException(status_code=400, detail="match_type, match_value, and category are required")

	now = datetime.now(timezone.utc).isoformat()
	result = db.execute(
		text(
			"""
			INSERT INTO rules (
				match_type,
				match_value,
				category,
				priority,
				match_count,
				is_active,
				created_at,
				updated_at
			)
			VALUES (
				:match_type,
				:match_value,
				:category,
				:priority,
				0,
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
			"priority": int(payload.priority),
			"created_at": now,
			"updated_at": now,
		},
	)
	db.commit()

	created_id = int(getattr(result, "lastrowid", 0) or 0)
	return {
		"id": created_id,
		"match_type": match_type,
		"match_value": match_value,
		"category": category,
		"priority": int(payload.priority),
		"match_count": 0,
		"is_active": True,
	}


@router.patch("/{rule_id}/toggle")
def toggle_rule(rule_id: int, payload: RuleToggleRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
	_ensure_rules_table_schema(db)

	now = datetime.now(timezone.utc).isoformat()
	result = db.execute(
		text(
			"""
			UPDATE rules
			SET is_active = :is_active, updated_at = :updated_at
			WHERE id = :id
			"""
		),
		{
			"id": int(rule_id),
			"is_active": 1 if payload.is_active else 0,
			"updated_at": now,
		},
	)
	db.commit()

	if int(getattr(result, "rowcount", 0) or 0) == 0:
		raise HTTPException(status_code=404, detail="Rule not found")

	return {"id": int(rule_id), "is_active": payload.is_active}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
	_ensure_rules_table_schema(db)
	result = db.execute(
		text(
			"""
			DELETE FROM rules
			WHERE id = :id
			"""
		),
		{"id": int(rule_id)},
	)
	db.commit()

	if int(getattr(result, "rowcount", 0) or 0) == 0:
		raise HTTPException(status_code=404, detail="Rule not found")

	return {"deleted": True, "id": int(rule_id)}


def _ensure_rules_table_schema(db: Session) -> None:
	db.execute(
		text(
			"""
			CREATE TABLE IF NOT EXISTS rules (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				match_type TEXT NOT NULL,
				match_value TEXT NOT NULL,
				category TEXT NOT NULL,
				priority INTEGER NOT NULL DEFAULT 100,
				match_count INTEGER NOT NULL DEFAULT 0,
				is_active INTEGER NOT NULL DEFAULT 1,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL,
				UNIQUE(match_type, match_value)
			)
			"""
		)
	)

	# Backward compatibility with earlier rules schema without match_count.
	columns = db.execute(text("PRAGMA table_info(rules)")).mappings().all()
	column_names = {str(row.get("name") or "") for row in columns}
	if "match_count" not in column_names:
		db.execute(text("ALTER TABLE rules ADD COLUMN match_count INTEGER NOT NULL DEFAULT 0"))

	db.commit()
