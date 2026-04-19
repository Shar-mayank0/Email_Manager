from typing import Any

from backend.config.constants import (
	CATEGORY_IMPORTANT,
	CATEGORY_PROMOTIONAL,
	SOURCE_RULE,
)


PERSONAL_LABEL = "CATEGORY_PERSONAL"
PROMOTIONAL_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_FORUMS"}
TRANSACTIONAL_GUARD_KEYWORDS = {
	"payment",
	"transaction",
	"credited",
	"debited",
	"imps",
	"upi",
	"statement",
	"otp",
	"failed attempt to access",
	"bank",
	"kotak",
	"nsdl",
	"nsdl cas",
}


def _build_match(category: str, reasoning: str) -> dict[str, str | float]:
	return {
		"category": category,
		"confidence": 1.0,
		"source": SOURCE_RULE,
		"reasoning": reasoning,
	}


def _normalize_labels(labels_value: Any) -> list[str]:
	if labels_value is None:
		return []

	if isinstance(labels_value, list):
		return [str(label) for label in labels_value]

	if isinstance(labels_value, tuple | set):
		return [str(label) for label in labels_value]

	if isinstance(labels_value, str):
		stripped = labels_value.strip()
		if not stripped:
			return []
		if stripped.startswith("[") and stripped.endswith("]"):
			inner = stripped[1:-1].strip()
			if not inner:
				return []
			parts = [part.strip().strip('"').strip("'") for part in inner.split(",")]
			return [part for part in parts if part]
		return [stripped]

	return [str(labels_value)]


def _is_transactional_or_security_email(email_dict: dict[str, Any]) -> bool:
	subject = str(email_dict.get("subject") or "").lower()
	body_plain = str(email_dict.get("body_plain") or "").lower()
	snippet = str(email_dict.get("snippet") or "").lower()
	combined = f"{subject}\n{snippet}\n{body_plain}"
	return any(keyword in combined for keyword in TRANSACTIONAL_GUARD_KEYWORDS)


def apply_rules(email_dict: dict[str, Any]) -> dict[str, str | float] | None:
	labels = _normalize_labels(email_dict.get("labels"))
	label_set = {label.upper() for label in labels}

	# Priority 1: if Gmail says personal, trust it.
	if PERSONAL_LABEL in label_set:
		return _build_match(CATEGORY_IMPORTANT, "Gmail label CATEGORY_PERSONAL matched important rule")

	# Guard: transactional/security-looking emails should be decided semantically by LLM,
	# not by broad promotional rules.
	if _is_transactional_or_security_email(email_dict):
		return None

	# Priority 2: promotions/forums labels map to promotional.
	if any(label in label_set for label in PROMOTIONAL_LABELS):
		return _build_match(
			CATEGORY_PROMOTIONAL,
			"Gmail promotional/forums label matched promotional rule",
		)

	# Priority 3: explicit unsubscribe signal in plain text body.
	body_plain = str(email_dict.get("body_plain") or "").lower()
	if "unsubscribe" in body_plain:
		return _build_match(
			CATEGORY_PROMOTIONAL,
			"Body contains unsubscribe indicator",
		)

	return None
