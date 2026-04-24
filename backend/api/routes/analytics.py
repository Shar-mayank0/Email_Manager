from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.config.constants import STATUS_PENDING_REVIEW
from backend.db.models.email import Email


router = APIRouter()


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
	_ensure_feedback_table(db)

	total_emails = int(db.query(func.count(Email.id)).scalar() or 0)

	category_rows = (
		db.query(Email.category, func.count(Email.id))
		.group_by(Email.category)
		.all()
	)
	by_category = {str(category or "UNCLASSIFIED"): int(count or 0) for category, count in category_rows}

	status_rows = db.query(Email.status, func.count(Email.id)).group_by(Email.status).all()
	by_status = {str(status or "unknown"): int(count or 0) for status, count in status_rows}

	feedback_total = int(db.execute(text("SELECT COUNT(*) AS c FROM feedback")).scalar() or 0)
	feedback_correct = int(
		db.execute(text("SELECT COUNT(*) AS c FROM feedback WHERE predicted = actual")).scalar() or 0
	)
	accuracy_estimate = (feedback_correct / feedback_total) if feedback_total else 0.0

	pending_review_count = int(
		db.query(func.count(Email.id)).filter(Email.status == STATUS_PENDING_REVIEW).scalar() or 0
	)

	return {
		"total_emails": total_emails,
		"by_category": by_category,
		"by_status": by_status,
		"accuracy_estimate": round(accuracy_estimate, 4),
		"pending_review_count": pending_review_count,
	}


@router.get("/confidence-distribution")
def confidence_distribution(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
	bucket_edges = [i / 10 for i in range(0, 11)]
	bucket_counts: dict[str, int] = {f"{bucket_edges[i]:.1f}-{bucket_edges[i + 1]:.1f}": 0 for i in range(10)}

	rows = db.query(Email.confidence).filter(Email.confidence.isnot(None)).all()
	for (confidence_raw,) in rows:
		try:
			value = float(confidence_raw)
		except (TypeError, ValueError):
			continue

		if value < 0.0:
			value = 0.0
		if value > 1.0:
			value = 1.0

		index = min(int(value * 10), 9)
		key = f"{bucket_edges[index]:.1f}-{bucket_edges[index + 1]:.1f}"
		bucket_counts[key] += 1

	return [{"range": bucket_range, "count": count} for bucket_range, count in bucket_counts.items()]


@router.get("/category-trend")
def category_trend(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
	rows = (
		db.query(func.date(Email.received_at), Email.category, func.count(Email.id))
		.filter(Email.received_at.isnot(None))
		.group_by(func.date(Email.received_at), Email.category)
		.order_by(func.date(Email.received_at))
		.all()
	)

	trend: dict[str, dict[str, int]] = defaultdict(dict)
	for date_value, category, count in rows:
		date_key = str(date_value or datetime.utcnow().date())
		category_key = str(category or "UNCLASSIFIED")
		trend[date_key][category_key] = int(count or 0)

	items: list[dict[str, Any]] = []
	for date_key, categories in trend.items():
		items.append({"date": date_key, "categories": categories})

	return items


def _ensure_feedback_table(db: Session) -> None:
	db.execute(
		text(
			"""
			CREATE TABLE IF NOT EXISTS feedback (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				gmail_id TEXT NOT NULL,
				predicted TEXT NOT NULL,
				actual TEXT NOT NULL,
				confidence REAL NOT NULL DEFAULT 0,
				notes TEXT,
				timestamp DATETIME NOT NULL
			)
			"""
		)
	)
	db.commit()
