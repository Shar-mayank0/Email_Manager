from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError

from backend.core.ingestion.gmail_client import (
	fetch_email_by_id,
	fetch_email_ids,
	parse_email,
)

SYNC_STATE_PATH = Path(__file__).resolve().parents[3] / "sync_state.json"


def get_last_sync_token() -> str | None:
	"""Read and return the last saved Gmail history ID, or None on first run."""
	if not SYNC_STATE_PATH.exists():
		return None

	try:
		state = json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError):
		return None

	history_id = state.get("historyId")
	if history_id is None:
		return None
	return str(history_id)


def save_sync_token(history_id: str) -> None:
	"""Persist the latest successful Gmail history ID to local sync state."""
	SYNC_STATE_PATH.write_text(
		json.dumps({"historyId": str(history_id)}, indent=2),
		encoding="utf-8",
	)


def fetch_new_emails(service: Any) -> list[dict[str, Any]]:
	"""Fetch parsed emails using first-run unread mode or incremental history mode."""
	last_history_id = get_last_sync_token()
	email_ids: set[str] = set()
	latest_history_id: str | None = None

	if not last_history_id:
		email_ids.update(fetch_email_ids(service, max_results=50, query="is:unread"))
	else:
		page_token: str | None = None
		try:
			while True:
				request = service.users().history().list(
					userId="me",
					startHistoryId=last_history_id,
					historyTypes=["messageAdded"],
					pageToken=page_token,
				)
				response = request.execute()

				if response.get("historyId"):
					latest_history_id = str(response["historyId"])

				for history_item in response.get("history", []):
					for added in history_item.get("messagesAdded", []):
						message = added.get("message", {})
						message_id = message.get("id")
						if message_id:
							email_ids.add(str(message_id))

				page_token = response.get("nextPageToken")
				if not page_token:
					break
		except HttpError as exc:
			status_code = getattr(exc, "status_code", None)
			if status_code is None and getattr(exc, "resp", None) is not None:
				status_code = getattr(exc.resp, "status", None)

			if status_code == 404:
				email_ids.update(fetch_email_ids(service, max_results=50, query="is:unread"))
			else:
				raise

	parsed_emails: list[dict[str, Any]] = []
	for email_id in email_ids:
		raw_email = fetch_email_by_id(service, email_id)
		parsed_emails.append(parse_email(raw_email))
		raw_history_id = raw_email.get("historyId")
		if raw_history_id and (
			latest_history_id is None or int(raw_history_id) > int(latest_history_id)
		):
			latest_history_id = str(raw_history_id)

	if latest_history_id is None:
		profile = service.users().getProfile(userId="me").execute()
		profile_history_id = profile.get("historyId")
		if profile_history_id:
			latest_history_id = str(profile_history_id)

	if latest_history_id is not None:
		save_sync_token(latest_history_id)

	return parsed_emails
