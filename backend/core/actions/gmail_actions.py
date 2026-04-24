import logging
from typing import Any, TypedDict

from backend.core.policy.policy_engine import ActionPlan


logger = logging.getLogger(__name__)

EMAILBOT_LABELS = (
	"EmailBot/Important",
	"EmailBot/Banking",
	"EmailBot/Internship",
	"EmailBot/Promotional",
)

_label_cache: dict[str, str] = {}


class ActionExecutionResult(TypedDict):
	success: bool
	gmail_id: str
	action_type: str
	reason: str
	steps: list[dict[str, Any]]
	error: str | None


def ensure_labels_exist(service: Any) -> dict[str, str]:
	"""Ensure all EmailBot labels exist and return name -> id mapping."""
	try:
		response = service.users().labels().list(userId="me").execute()
		labels = response.get("labels", [])
	except Exception as exc:
		logger.exception("Failed to list Gmail labels during setup: %s", exc)
		return dict(_label_cache)

	existing: dict[str, str] = {}
	for label in labels:
		name = str(label.get("name") or "").strip()
		label_id = str(label.get("id") or "").strip()
		if name and label_id:
			existing[name] = label_id

	for label_name in EMAILBOT_LABELS:
		if label_name in existing:
			_label_cache[label_name] = existing[label_name]
			continue

		created_id = get_or_create_label(service, label_name, _label_cache)
		if created_id:
			_label_cache[label_name] = created_id

	return {name: _label_cache[name] for name in EMAILBOT_LABELS if name in _label_cache}


def get_or_create_label(service: Any, label_name: str, label_cache: dict[str, str]) -> str | None:
	"""Return a label ID from cache, or create the label and cache it."""
	cached_id = label_cache.get(label_name)
	if cached_id:
		return cached_id

	payload = {
		"name": label_name,
		"labelListVisibility": "labelShow",
		"messageListVisibility": "show",
	}

	try:
		created = service.users().labels().create(userId="me", body=payload).execute()
		label_id = str(created.get("id") or "").strip()
		if not label_id:
			logger.error("Created Gmail label '%s' but response did not include id", label_name)
			return None
		label_cache[label_name] = label_id
		return label_id
	except Exception as exc:
		logger.exception("Failed to get/create label '%s': %s", label_name, exc)
		return None


def apply_label(service: Any, gmail_id: str, label_id: str) -> bool:
	"""Apply a Gmail label to one message."""
	if not label_id:
		logger.error("Cannot apply empty label id to gmail_id=%s", gmail_id)
		return False

	try:
		service.users().messages().modify(
			userId="me",
			id=gmail_id,
			body={"addLabelIds": [label_id]},
		).execute()
		return True
	except Exception as exc:
		logger.exception("Failed to apply label_id=%s to gmail_id=%s: %s", label_id, gmail_id, exc)
		return False


def star_email(service: Any, gmail_id: str) -> bool:
	"""Star one Gmail message using system STARRED label."""
	try:
		service.users().messages().modify(
			userId="me",
			id=gmail_id,
			body={"addLabelIds": ["STARRED"]},
		).execute()
		return True
	except Exception as exc:
		logger.exception("Failed to star gmail_id=%s: %s", gmail_id, exc)
		return False


def archive_email(service: Any, gmail_id: str) -> bool:
	"""Archive one Gmail message by removing it from INBOX."""
	try:
		service.users().messages().modify(
			userId="me",
			id=gmail_id,
			body={"removeLabelIds": ["INBOX"]},
		).execute()
		return True
	except Exception as exc:
		logger.exception("Failed to archive gmail_id=%s: %s", gmail_id, exc)
		return False


def apply_action_plan(
	service: Any,
	gmail_id: str,
	action_plan: ActionPlan,
	label_cache: dict[str, str],
) -> ActionExecutionResult:
	"""Execute a policy action plan against Gmail with resilient failure handling."""
	action_type = str(action_plan.get("action_type") or "")
	reason = str(action_plan.get("reason") or "")
	result: ActionExecutionResult = {
		"success": True,
		"gmail_id": gmail_id,
		"action_type": action_type,
		"reason": reason,
		"steps": [],
		"error": None,
	}

	if action_type in {"human_review", "hold"}:
		result["steps"].append({"step": "noop", "success": True, "detail": action_type})
		return result

	if action_type not in {"label", "label_and_star", "label_and_archive"}:
		result["success"] = False
		result["error"] = f"Unsupported action_type '{action_type}'"
		result["steps"].append(
			{"step": "validate_action", "success": False, "detail": result["error"]}
		)
		return result

	label_name = str(action_plan.get("label_name") or "").strip()
	if not label_name:
		result["success"] = False
		result["error"] = "Action plan requires label_name for Gmail write operations"
		result["steps"].append(
			{"step": "resolve_label", "success": False, "detail": result["error"]}
		)
		return result

	label_id = label_cache.get(label_name)
	if not label_id:
		label_id = get_or_create_label(service, label_name, label_cache)

	if not label_id:
		result["success"] = False
		result["error"] = f"Unable to resolve label id for '{label_name}'"
		result["steps"].append(
			{"step": "resolve_label", "success": False, "detail": result["error"]}
		)
		return result

	label_ok = apply_label(service, gmail_id, label_id)
	result["steps"].append(
		{
			"step": "apply_label",
			"success": label_ok,
			"detail": label_name,
		}
	)

	if not label_ok:
		result["success"] = False
		result["error"] = f"Failed to apply label '{label_name}'"
		return result

	if action_type == "label_and_star":
		star_ok = star_email(service, gmail_id)
		result["steps"].append({"step": "star_email", "success": star_ok, "detail": "STARRED"})
		if not star_ok:
			result["success"] = False
			result["error"] = "Failed to star email"
		return result

	if action_type == "label_and_archive":
		archive_ok = archive_email(service, gmail_id)
		result["steps"].append(
			{"step": "archive_email", "success": archive_ok, "detail": "remove INBOX"}
		)
		if not archive_ok:
			result["success"] = False
			result["error"] = "Failed to archive email"

	return result
