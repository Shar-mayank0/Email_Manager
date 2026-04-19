import json
import re
import time
from typing import Any

from google import genai
from google.genai import types

from backend.config.constants import (
	ALL_CATEGORIES,
	CATEGORY_UNCLASSIFIED,
	SOURCE_LLM,
)
from backend.config.settings import settings


class LLMClassificationError(Exception):
	"""Raised when the LLM response is missing required classification fields."""


def _fallback(reasoning: str) -> dict[str, str | float]:
	return {
		"category": CATEGORY_UNCLASSIFIED,
		"confidence": 0.0,
		"source": SOURCE_LLM,
		"reasoning": reasoning,
	}


def _extract_retry_delay_seconds(error_text: str, default_wait: int = 60) -> int:
	patterns = [
		r"retryDelay\s*[:=]\s*([0-9]+)\s*s",
		r"retryDelay\"\s*:\s*\"?([0-9]+)s?\"?",
	]
	for pattern in patterns:
		match = re.search(pattern, error_text, flags=re.IGNORECASE)
		if not match:
			continue
		try:
			wait_time = int(match.group(1))
		except (TypeError, ValueError):
			continue
		if wait_time > 0:
			return wait_time

	return default_wait


def build_prompt(email_dict: dict[str, Any]) -> str:
	sender_name = str(email_dict.get("sender_name") or "")
	sender_email = str(email_dict.get("sender_email") or "")
	subject = str(email_dict.get("subject") or "")
	received_at = str(email_dict.get("received_at") or "")
	body_plain = str(email_dict.get("body_plain") or "")[:500]

	system_prompt = (
		'''You are an intelligent email classification assistant. Your job is to analyze 
emails and classify them into exactly one category based on their content, 
intent, and context.

## YOUR TASK

Given an email with sender information, subject, and body content, you must:
1. Understand the PRIMARY PURPOSE of the email
2. Identify WHO sent it and WHY
3. Assign exactly one category
4. Provide a calibrated confidence score
5. Give a concise reasoning

## CATEGORIES

### IMPORTANT
Emails that require the recipient's attention or action, or contain 
information personally relevant to them. This includes:
- Person-to-person communication (real humans writing to the recipient)
- Account security alerts (password expiry, suspicious login, 2FA)
- Service disruptions or maintenance affecting the recipient's active accounts
- Government or official institutional communication
- Developer alerts about the recipient's own projects (build failures, 
  domain issues, deployment alerts)
- Event confirmations, registrations, or invitations requiring a response
- Any email where ignoring it could have a real consequence

### BANKING
Emails directly related to financial accounts and transactions. This includes:
- Transaction confirmations (payments made, received, failed)
- Bank account statements and summaries
- Investment portfolio updates and statements
- OTP and verification codes for financial services
- Loan, credit card, or insurance notifications
- Tax-related financial documents
- Stock broker communications and trade confirmations

### INTERNSHIP
Emails related to career opportunities and professional development. 
This includes:
- Job application confirmations and status updates
- Interview invitations or scheduling
- Recruiter outreach with specific opportunities
- Internship or full-time offer letters
- Competitive programming contests with career relevance
- Hackathons with recruitment or prize components
- Professional certification completions

### PROMOTIONAL
Emails sent in bulk whose primary purpose is marketing, advertising, 
or content distribution. This includes:
- Product announcements and feature launches from companies
- Sales, discounts, and limited-time offers
- Weekly/monthly newsletters and digest emails
- Platform update emails from SaaS tools
- Community roundup emails (trending posts, top content)
- Re-engagement emails ("we miss you", "your account is inactive")
- Event announcements that are open to the general public
- Educational content emails from platforms (not personal to recipient)

### TRASH
Emails with no value to the recipient. This includes:
- Spam and unsolicited commercial email
- Phishing attempts
- Emails clearly sent to the wrong address
- Duplicate notifications already covered by another email
- Auto-generated system noise with no actionable content

## DECISION RULES

Apply these rules strictly when determining the category:

1. INTENT OVER SENDER: Classify based on what the email is trying to 
   accomplish, not who sent it. A bank can send a promotional email. 
   A newsletter platform can send an important account alert.

2. CONSEQUENCE TEST: Ask "what happens if the recipient ignores this?" 
   If the answer is "something bad or missed" → IMPORTANT. 
   If the answer is "nothing" → PROMOTIONAL or TRASH.

3. PERSONAL VS BULK: Was this email written for this specific recipient, 
   or is it the same email sent to thousands of people? 
   Personal → lean IMPORTANT. Bulk → lean PROMOTIONAL.

4. FINANCIAL SPECIFICITY: Only classify as BANKING if the email contains 
   specific financial data (amounts, account numbers, transaction IDs, 
   statement periods). Generic financial product marketing → PROMOTIONAL.

5. CAREER SPECIFICITY: Only classify as INTERNSHIP if it relates to a 
   specific opportunity or application for THIS recipient. 
   Generic "learn to code" or "top jobs this week" → PROMOTIONAL.

6. WHEN IN DOUBT: Between IMPORTANT and PROMOTIONAL, prefer IMPORTANT. 
   It is always better to surface something to the recipient than to 
   bury it. Between PROMOTIONAL and TRASH, prefer PROMOTIONAL unless 
   the email is clearly spam or phishing.

## CONFIDENCE SCORE GUIDE

Your confidence score must reflect genuine certainty, not optimism:

- 0.95 – 1.0 : Absolutely certain. The category is unambiguous.
- 0.85 – 0.94: Very confident. Strong signals, minor ambiguity.
- 0.70 – 0.84: Confident but some signals point elsewhere.
- 0.50 – 0.69: Uncertain. The email has mixed signals.
- Below 0.50 : Very uncertain. Flag for human review.

Do NOT default to high confidence. If the email is ambiguous, 
reflect that in your score. A score of 0.65 is an honest answer. 
A false 0.95 causes incorrect automated actions.

## OUTPUT FORMAT

Respond with ONLY a valid JSON object. No markdown, no code blocks, 
no explanation outside the JSON. The response must be parseable by 
Python's json.loads() directly.

{
  "category": "IMPORTANT | BANKING | INTERNSHIP | PROMOTIONAL | TRASH",
  "confidence": 0.0,
  "reasoning": "One concise sentence explaining the primary signal that 
  determined this classification."
}

## EXAMPLES

Email: Password expiry notice from a banking app
Output: {"category": "IMPORTANT", "confidence": 0.97, "reasoning": 
"Security alert about account access requiring immediate action."}

Email: Weekly digest of trending articles from a content platform  
Output: {"category": "PROMOTIONAL", "confidence": 0.92, "reasoning": 
"Bulk newsletter sent to all subscribers, no personal action required."}

Email: Transaction confirmation for a specific payment amount
Output: {"category": "BANKING", "confidence": 0.98, "reasoning": 
"Contains specific transaction amount and confirmation, directly 
financial in nature."}

Email: Application submitted confirmation from a job portal
Output: {"category": "INTERNSHIP", "confidence": 0.95, "reasoning": 
"Direct confirmation of a job application submitted by the recipient."}

Email: Promotional offer from a food delivery app during a cricket season
Output: {"category": "PROMOTIONAL", "confidence": 0.93, "reasoning": 
"Marketing email tied to a seasonal event, primary intent is driving 
orders not informing the recipient."}'''
	)

	user_prompt = (
		f"From: {sender_name} <{sender_email}>\n"
		f"Subject: {subject}\n"
		f"Date: {received_at}\n\n"
		f"{body_plain}"
	)

	return f"{system_prompt}\n\n{user_prompt}"


def _parse_and_validate_llm_response(response_text: str) -> dict[str, str | float]:
	try:
		payload = json.loads(response_text)
	except (TypeError, ValueError, json.JSONDecodeError) as exc:
		raise LLMClassificationError("LLM returned malformed response") from exc

	if not isinstance(payload, dict):
		raise LLMClassificationError("LLM returned malformed response")

	category = str(payload.get("category") or "").strip().upper()
	if category not in ALL_CATEGORIES:
		raise LLMClassificationError("LLM returned invalid category")

	confidence_raw = payload.get("confidence")
	if confidence_raw is None:
		raise LLMClassificationError("LLM returned malformed response")
	try:
		confidence = float(confidence_raw)
	except (TypeError, ValueError) as exc:
		raise LLMClassificationError("LLM returned malformed response") from exc

	if confidence < 0.0 or confidence > 1.0:
		raise LLMClassificationError("LLM returned malformed response")

	reasoning = str(payload.get("reasoning") or "").strip()
	if not reasoning:
		reasoning = "No reasoning provided"

	return {
		"category": category,
		"confidence": confidence,
		"source": SOURCE_LLM,
		"reasoning": reasoning,
	}


def classify_with_llm(email_dict: dict[str, Any]) -> dict[str, str | float]:
	try:
		api_key = str(settings.llm_api_key)
		configured_model = str(settings.llm_model)
		candidate_models = [
			configured_model,
			"gemini-2.5-flash",
			"gemini-2.0-flash",
		]
		# Keep order but remove duplicates/empties.
		seen_models: set[str] = set()
		model_names: list[str] = []
		for name in candidate_models:
			clean = name.strip()
			if not clean or clean in seen_models:
				continue
			seen_models.add(clean)
			model_names.append(clean)

		client = genai.Client(api_key=api_key)

		prompt = build_prompt(email_dict)
		max_retries = 3
		response = None
		last_error: Exception | None = None
		for model_name in model_names:
			for attempt in range(max_retries):
				try:
					response = client.models.generate_content(
						model=model_name,
						contents=prompt,
						config=types.GenerateContentConfig(
							temperature=float(settings.llm_temperature),
							response_mime_type="application/json",
						),
					)
					break
				except Exception as e:
					last_error = e
					error_text = str(e)
					is_rate_limited = "429" in error_text or "RESOURCE_EXHAUSTED" in error_text
					is_model_not_found = "NOT_FOUND" in error_text and "models/" in error_text

					if is_model_not_found:
						print(f"Model '{model_name}' unavailable, trying fallback model...")
						break

					if is_rate_limited and attempt < max_retries - 1:
						wait_time = _extract_retry_delay_seconds(error_text, default_wait=60)
						print(f"Rate limited. Waiting {wait_time}s before retry...")
						time.sleep(wait_time)
						continue
					raise

			if response is not None:
				break

		if response is None:
			if last_error is not None:
				raise last_error
			raise LLMClassificationError("LLM classification failed")

		response_text = str(getattr(response, "text", "") or "").strip()
		if not response_text:
			raise LLMClassificationError("LLM returned malformed response")

		return _parse_and_validate_llm_response(response_text)
	except LLMClassificationError as exc:
		message = str(exc).lower()
		if "invalid category" in message:
			return _fallback("LLM returned malformed response")
		if "malformed" in message:
			return _fallback("LLM returned malformed response")
		return _fallback("LLM classification failed")
	except Exception as e:
		print(f"LLM ERROR: {type(e).__name__}: {e}")
		# Never allow upstream pipeline crashes due to provider/network/runtime issues.
		return _fallback("LLM classification failed")
