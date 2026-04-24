import logging
from typing import Any, Literal, TypedDict

from sqlalchemy.orm import Session

from backend.config.constants import (
	CATEGORY_BANKING,
	CATEGORY_IMPORTANT,
	CATEGORY_INTERNSHIP,
	CATEGORY_PROMOTIONAL,
	CATEGORY_TRASH,
	CONFIDENCE_AUTO_ACT,
	CONFIDENCE_HUMAN_REVIEW,
)
from backend.core.policy.safety_checks import PolicyViolationError, run_safety_checks


logger = logging.getLogger(__name__)

ActionType = Literal[
	"label",
	"label_and_star",
	"label_and_archive",
	"human_review",
	"hold",
]


class ActionPlan(TypedDict):
	action_type: ActionType
	label_name: str | None
	reason: str


def determine_action(classification: dict[str, Any]) -> ActionPlan:
	"""Map classification output to an executable policy action plan."""
	category = str(classification.get("category") or "").strip().upper()
	confidence = _normalize_confidence(classification.get("confidence"))

	if category == CATEGORY_TRASH:
		return _plan(
			action_type="human_review",
			label_name=None,
			reason="TRASH category is never auto-acted; routed to human review.",
		)

	if confidence < CONFIDENCE_HUMAN_REVIEW:
		return _plan(
			action_type="hold",
			label_name=None,
			reason=(
				f"Confidence {confidence:.2f} is below review threshold "
				f"{CONFIDENCE_HUMAN_REVIEW:.2f}; holding for manual decision."
			),
		)

	if confidence < CONFIDENCE_AUTO_ACT:
		return _plan(
			action_type="human_review",
			label_name=None,
			reason=(
				f"Confidence {confidence:.2f} is below auto-act threshold "
				f"{CONFIDENCE_AUTO_ACT:.2f}; queued for human review."
			),
		)

	label_name = get_label_name_for_category(category)
	if label_name is None:
		return _plan(
			action_type="human_review",
			label_name=None,
			reason=f"Unknown category '{category}' cannot be auto-acted; routed to human review.",
		)

	if category == CATEGORY_BANKING:
		return _plan(
			action_type="label",
			label_name=label_name,
			reason="BANKING with high confidence; applying Banking label.",
		)

	if category == CATEGORY_IMPORTANT:
		return _plan(
			action_type="label_and_star",
			label_name=label_name,
			reason="IMPORTANT with high confidence; applying label and starring.",
		)

	if category == CATEGORY_INTERNSHIP:
		return _plan(
			action_type="label_and_star",
			label_name=label_name,
			reason="INTERNSHIP with high confidence; applying label and starring.",
		)

	return _plan(
		action_type="label_and_archive",
		label_name=label_name,
		reason="PROMOTIONAL with high confidence; applying label and archiving.",
	)


def evaluate(db: Session, email_dict: dict[str, Any], classification: dict[str, Any]) -> ActionPlan:
	"""Run safety checks and return an action plan that is safe to execute."""
	_ = db  # Policy evaluation currently does not need direct DB access.
	try:
		run_safety_checks(email_dict, classification)
		return determine_action(classification)
	except PolicyViolationError as exc:
		logger.warning(
			"Policy violation for email_id=%s (%s): %s",
			exc.email_id,
			exc.check_name,
			exc.reason,
		)
		return _plan(
			action_type="hold",
			label_name=None,
			reason=f"Policy violation ({exc.check_name}): {exc.reason}",
		)


def get_label_name_for_category(category: str) -> str | None:
	normalized = str(category or "").strip().upper()
	label_by_category = {
		CATEGORY_IMPORTANT: "EmailBot/Important",
		CATEGORY_BANKING: "EmailBot/Banking",
		CATEGORY_INTERNSHIP: "EmailBot/Internship",
		CATEGORY_PROMOTIONAL: "EmailBot/Promotional",
	}
	return label_by_category.get(normalized)


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


def _plan(action_type: ActionType, label_name: str | None, reason: str) -> ActionPlan:
	return {
		"action_type": action_type,
		"label_name": label_name,
		"reason": reason,
	}
