from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db, get_gmail_service, get_label_cache
from backend.config.constants import STATUS_ACTIONED, STATUS_PENDING_REVIEW
from backend.core.actions.action_logger import log_action, log_hold
from backend.core.actions.gmail_actions import apply_action_plan
from backend.core.actions.undo_manager import undo_latest_for_email
from backend.core.classification.classifier_pipeline import classify_and_save
from backend.core.ingestion.sync_manager import fetch_new_emails
from backend.core.policy.policy_engine import ActionPlan, evaluate, get_label_name_for_category
from backend.db.models.email import Email
from backend.db.repository import email_repo


router = APIRouter()


class EmailResponse(BaseModel):
	id: int
	gmail_id: str
	subject: str
	sender_name: str
	sender_email: str
	sender_domain: str
	received_at: datetime | None
	category: str
	confidence: float | None
	classification_source: str | None
	status: str
	snippet: str
	has_attachment: bool
	labels: list[str]
	body_plain: str | None = None

	model_config = ConfigDict(from_attributes=True)


class PaginatedEmailResponse(BaseModel):
	emails: list[EmailResponse]
	total: int
	page: int
	per_page: int
	has_next: bool


class ActionRequest(BaseModel):
	action_type: str | None = None


@router.get("", response_model=PaginatedEmailResponse)
def list_emails(
	status: str = Query(default=STATUS_PENDING_REVIEW),
	category: str | None = Query(default=None),
	page: int = Query(default=1, ge=1),
	per_page: int = Query(default=20, ge=1, le=200),
	db: Session = Depends(get_db),
) -> PaginatedEmailResponse:
	query = db.query(Email)
	if status:
		query = query.filter(Email.status == status)
	if category:
		query = query.filter(Email.category == category.strip().upper())

	total = query.count()
	offset = (page - 1) * per_page
	rows = query.order_by(Email.received_at.desc()).offset(offset).limit(per_page).all()

	emails = [_to_email_response(email) for email in rows]
	return PaginatedEmailResponse(
		emails=emails,
		total=total,
		page=page,
		per_page=per_page,
		has_next=(offset + len(emails)) < total,
	)


@router.post("/sync")
def sync_emails(
	db: Session = Depends(get_db),
	service: Any = Depends(get_gmail_service),
) -> dict[str, int]:
	fetched = fetch_new_emails(service)
	processed = 0
	for email_dict in fetched:
		email_repo.save_email(db, email_dict)
		classify_and_save(db, email_dict)
		processed += 1
	return {"new_emails": len(fetched), "processed": processed}


@router.get("/{gmail_id}", response_model=EmailResponse)
def get_email_detail(gmail_id: str, db: Session = Depends(get_db)) -> EmailResponse:
	email = email_repo.get_email_by_gmail_id(db, gmail_id)
	if email is None:
		raise HTTPException(status_code=404, detail="Email not found")
	return _to_email_response(email, include_body=True)


@router.post("/{gmail_id}/action")
def run_email_action(
	gmail_id: str,
	payload: ActionRequest,
	db: Session = Depends(get_db),
	service: Any = Depends(get_gmail_service),
	label_cache: dict[str, str] = Depends(get_label_cache),
) -> dict[str, Any]:
	email = email_repo.get_email_by_gmail_id(db, gmail_id)
	if email is None:
		raise HTTPException(status_code=404, detail="Email not found")

	email_dict = _to_email_dict(email)
	classification = {
		"category": str(cast(Any, email).category or ""),
		"confidence": _to_float(cast(Any, email).confidence),
		"source": str(cast(Any, email).classification_source or ""),
	}

	action_plan = evaluate(db, email_dict, classification)
	if payload.action_type:
		action_plan = _apply_action_override(action_plan, payload.action_type, classification)

	result = apply_action_plan(service, gmail_id, action_plan, label_cache)

	if action_plan["action_type"] in {"hold", "human_review"}:
		log_hold(db, gmail_id, action_plan["reason"])
	else:
		label_name = str(action_plan.get("label_name") or "")
		log_action(
			db,
			gmail_id,
			action_plan["action_type"],
			{
				"steps": result["steps"],
				"reason": result["reason"],
				"label_name": label_name,
				"label_id": label_cache.get(label_name, "") if label_name else "",
				"action_plan_reason": action_plan["reason"],
				"error": result["error"],
			},
			result["success"],
		)

	if result["success"] and action_plan["action_type"] not in {"hold", "human_review"}:
		email_repo.update_email_classification(
			db=db,
			gmail_id=gmail_id,
			category=str(cast(Any, email).category or ""),
			confidence=_to_float(cast(Any, email).confidence),
			classification_source=str(cast(Any, email).classification_source or ""),
			status=STATUS_ACTIONED,
		)

	return {"action_plan": action_plan, "execution": result}


@router.post("/{gmail_id}/undo")
def undo_last_action(
	gmail_id: str,
	db: Session = Depends(get_db),
	service: Any = Depends(get_gmail_service),
) -> dict[str, Any]:
	undo_result = undo_latest_for_email(db, service, gmail_id)
	return {"undo": undo_result}


def _to_email_response(email: Email, include_body: bool = False) -> EmailResponse:
	editable_email = cast(Any, email)
	body_plain = str(editable_email.body_plain or "") if include_body else None
	return EmailResponse(
		id=int(editable_email.id),
		gmail_id=str(editable_email.gmail_id or ""),
		subject=str(editable_email.subject or ""),
		sender_name=str(editable_email.sender_name or ""),
		sender_email=str(editable_email.sender_email or ""),
		sender_domain=str(editable_email.sender_domain or ""),
		received_at=editable_email.received_at,
		category=str(editable_email.category or ""),
		confidence=_nullable_float(editable_email.confidence),
		classification_source=(
			str(editable_email.classification_source)
			if editable_email.classification_source is not None
			else None
		),
		status=str(editable_email.status or ""),
		snippet=str(editable_email.snippet or ""),
		has_attachment=bool(editable_email.has_attachment),
		labels=email.get_labels(),
		body_plain=body_plain,
	)


def _to_email_dict(email: Email) -> dict[str, Any]:
	editable_email = cast(Any, email)
	return {column.name: getattr(editable_email, column.name) for column in email.__table__.columns}


def _nullable_float(value: Any) -> float | None:
	if value is None:
		return None
	return _to_float(value)


def _to_float(value: Any) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def _apply_action_override(
	action_plan: ActionPlan,
	override_action_type: str,
	classification: dict[str, Any],
) -> ActionPlan:
	normalized = override_action_type.strip().lower()
	if normalized not in {"label", "label_and_star", "label_and_archive", "human_review", "hold"}:
		raise HTTPException(status_code=400, detail=f"Unsupported action_type override '{override_action_type}'")

	if normalized in {"human_review", "hold"}:
		return {
			"action_type": cast(Any, normalized),
			"label_name": None,
			"reason": f"Manual action override requested: {normalized}",
		}

	category = str(classification.get("category") or "").strip().upper()
	label_name = get_label_name_for_category(category)
	if not label_name:
		raise HTTPException(status_code=400, detail="Cannot override to label action without a mappable category")

	return {
		"action_type": cast(Any, normalized),
		"label_name": label_name,
		"reason": f"Manual action override requested: {normalized}",
	}
