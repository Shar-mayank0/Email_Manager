from __future__ import annotations

import base64
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from backend.config.settings import settings

SCOPES = [
	"https://www.googleapis.com/auth/gmail.readonly",
	"https://www.googleapis.com/auth/gmail.modify",
	"https://www.googleapis.com/auth/gmail.labels",
]


def get_gmail_service() -> Any:
	"""Return an authenticated Gmail API service object."""
	token_path = Path(settings.google_token_path)
	credentials_path = Path(settings.google_credentials_path)
	creds: Any = None

	if token_path.exists():
		creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

	if creds and creds.expired and creds.refresh_token:
		creds.refresh(Request())

	if not creds or not creds.valid:
		flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
		creds = flow.run_local_server(port=0)
		if creds is None:
			raise RuntimeError("OAuth flow did not return credentials.")
		token_path.parent.mkdir(parents=True, exist_ok=True)
		token_path.write_text(creds.to_json(), encoding="utf-8")

	return build("gmail", "v1", credentials=creds)


def fetch_email_ids(service: Any, max_results: int, query: str) -> list[str]:
	"""Fetch and return Gmail message IDs for the authenticated user."""
	response = (
		service.users()
		.messages()
		.list(userId="me", maxResults=max_results, q=query)
		.execute()
	)
	messages = response.get("messages", [])
	return [message["id"] for message in messages if "id" in message]


def fetch_email_by_id(service: Any, email_id: str) -> dict[str, Any]:
	"""Fetch one full Gmail message by message ID."""
	return (
		service.users()
		.messages()
		.get(userId="me", id=email_id, format="full")
		.execute()
	)


def parse_email(raw_email: dict[str, Any]) -> dict[str, Any]:
	"""Extract useful normalized fields from a raw Gmail API message."""
	payload = raw_email.get("payload", {})
	headers = payload.get("headers", [])

	header_map: dict[str, str] = {}
	for header in headers:
		name = str(header.get("name", "")).lower()
		if not name:
			continue
		header_map[name] = str(header.get("value", ""))

	sender_raw = header_map.get("from", "")
	sender_name, sender_email = _parse_sender(sender_raw)
	sender_domain = sender_email.split("@", 1)[1].lower() if "@" in sender_email else ""
	body_plain, body_html = extract_body(payload)

	return {
		"email_id": raw_email.get("id", ""),
		"thread_id": raw_email.get("threadId", ""),
		"subject": header_map.get("subject", ""),
		"sender_raw": sender_raw,
		"sender_name": sender_name,
		"sender_email": sender_email,
		"sender_domain": sender_domain,
		"received_at": header_map.get("date", ""),
		"labels": raw_email.get("labelIds", []),
		"snippet": raw_email.get("snippet", ""),
		"has_attachment": _has_attachment(payload),
		"body_plain": body_plain,
		"body_html": body_html,
	}


def extract_body(payload: dict[str, Any]) -> tuple[str, str]:
	"""Recursively extract decoded plain-text and HTML bodies from MIME parts."""
	plain_parts: list[str] = []
	html_parts: list[str] = []

	def _walk(part: dict[str, Any]) -> None:
		mime_type = str(part.get("mimeType", ""))
		data = part.get("body", {}).get("data", "")

		if mime_type == "text/plain" and data:
			decoded = _decode_base64url(str(data))
			if decoded:
				plain_parts.append(decoded)

		if mime_type == "text/html" and data:
			decoded = _decode_base64url(str(data))
			if decoded:
				html_parts.append(decoded)

		for child in part.get("parts", []) or []:
			_walk(child)

	_walk(payload)
	plain_text = "\n".join(plain_parts).strip()
	html_text = "\n".join(html_parts).strip()
	return plain_text, html_text


def _decode_base64url(data: str) -> str:
	"""Decode Gmail base64url-encoded body data with safe padding."""
	if not data:
		return ""
	padding = "=" * ((4 - len(data) % 4) % 4)
	encoded = f"{data}{padding}".encode("utf-8")
	return base64.urlsafe_b64decode(encoded).decode("utf-8", errors="replace")


def _parse_sender(sender_raw: str) -> tuple[str, str]:
	"""Split RFC-822 From header into sender name and sender email address."""
	sender_name, sender_email = parseaddr(sender_raw)
	return sender_name.strip(), sender_email.strip().lower()


def _has_attachment(part: dict[str, Any]) -> bool:
	"""Return True if any MIME part contains a non-empty filename."""
	filename = str(part.get("filename", "")).strip()
	if filename:
		return True

	for child in part.get("parts", []) or []:
		if _has_attachment(child):
			return True
	return False
