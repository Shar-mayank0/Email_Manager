from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import requests
import streamlit as st
import streamlit.components.v1 as components


API_BASE = "http://localhost:8000"
REQUEST_TIMEOUT_SECONDS = 20
MINIMUM_PER_CATEGORY = 50
CATEGORIES = ["IMPORTANT", "BANKING", "INTERNSHIP", "PROMOTIONAL", "TRASH"]
HTTP = requests.Session()


def _api_get(path: str, params: dict[str, Any] | None = None) -> tuple[bool, Any, str | None]:
	url = f"{API_BASE}{path}"
	try:
		response = HTTP.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
		if not response.ok:
			return False, None, f"GET {path} failed ({response.status_code}): {response.text}"
		return True, response.json(), None
	except requests.RequestException as exc:
		return False, None, f"GET {path} request error: {exc}"


def _api_post(path: str, payload: dict[str, Any] | None = None) -> tuple[bool, Any, str | None]:
	url = f"{API_BASE}{path}"
	try:
		response = HTTP.post(url, json=payload or {}, timeout=REQUEST_TIMEOUT_SECONDS)
		if not response.ok:
			return False, None, f"POST {path} failed ({response.status_code}): {response.text}"
		return True, response.json(), None
	except requests.RequestException as exc:
		return False, None, f"POST {path} request error: {exc}"


def _fetch_email_detail(gmail_id: str, *, show_error: bool = False) -> dict[str, Any] | None:
	if "email_detail_cache" not in st.session_state:
		st.session_state.email_detail_cache = {}

	cache: dict[str, dict[str, Any] | None] = st.session_state.email_detail_cache
	if gmail_id in cache:
		return cache[gmail_id]

	ok, data, error = _api_get(f"/api/emails/{gmail_id}")
	if not ok:
		if show_error:
			st.warning(error)
		cache[gmail_id] = None
		return None
	if not isinstance(data, dict):
		cache[gmail_id] = None
		return None
	cache[gmail_id] = data
	return data


def _invalidate_email_cache(gmail_id: str | None = None) -> None:
	if "email_detail_cache" not in st.session_state:
		return
	cache: dict[str, dict[str, Any] | None] = st.session_state.email_detail_cache
	if gmail_id is None:
		cache.clear()
		return
	cache.pop(gmail_id, None)


def _render_review_queue_page() -> None:
	st.title("Review Queue")
	st.caption("Approve, correct, and teach rules from pending-review emails.")

	if "review_page" not in st.session_state:
		st.session_state.review_page = 1

	st.sidebar.markdown("### Review Filters")
	selected_categories = st.sidebar.multiselect("Category", CATEGORIES, default=[])
	min_confidence = st.sidebar.slider("Min confidence", 0.0, 1.0, 0.0, 0.01)

	page_controls = st.columns([1, 2, 1, 2])
	with page_controls[0]:
		if st.button("Previous", disabled=st.session_state.review_page <= 1):
			st.session_state.review_page = max(1, int(st.session_state.review_page) - 1)
			st.rerun()
	with page_controls[1]:
		page_input = st.number_input(
			"Page",
			min_value=1,
			value=int(st.session_state.review_page),
			step=1,
		)
		if int(page_input) != int(st.session_state.review_page):
			st.session_state.review_page = int(page_input)
			st.rerun()
	with page_controls[2]:
		sync_now = st.button("Sync now")
	if sync_now:
		ok, data, error = _api_post("/api/emails/sync", {})
		if not ok:
			st.error(error)
		else:
			_invalidate_email_cache()
			st.success(f"Sync complete: {data.get('new_emails', 0)} new, {data.get('processed', 0)} processed")
			st.rerun()

	params = {
		"status": "pending_review",
		"page": int(st.session_state.review_page),
		"per_page": 10,
	}
	if len(selected_categories) == 1:
		params["category"] = selected_categories[0]

	ok, payload, error = _api_get("/api/emails", params=params)
	if not ok:
		st.error(error)
		return

	emails = payload.get("emails", []) if isinstance(payload, dict) else []
	total = int(payload.get("total", 0)) if isinstance(payload, dict) else 0
	per_page = int(payload.get("per_page", 10)) if isinstance(payload, dict) else 10
	current_page = int(payload.get("page", st.session_state.review_page)) if isinstance(payload, dict) else int(st.session_state.review_page)

	filtered_emails: list[dict[str, Any]] = []
	for email in emails:
		category = str(email.get("category") or "").strip().upper()
		confidence_raw = email.get("confidence")
		try:
			confidence = float(confidence_raw) if confidence_raw is not None else 0.0
		except (TypeError, ValueError):
			confidence = 0.0

		if selected_categories and category not in selected_categories:
			continue
		if confidence < min_confidence:
			continue
		filtered_emails.append(email)

	start_index = (current_page - 1) * per_page + 1 if filtered_emails else 0
	end_index = start_index + len(filtered_emails) - 1 if filtered_emails else 0
	st.write(f"Showing {start_index}-{end_index} of {total} emails pending review")

	if not filtered_emails:
		st.info("No emails matched the current filters.")
		return

	for email in filtered_emails:
		gmail_id = str(email.get("gmail_id") or "")
		sender_name = str(email.get("sender_name") or "")
		sender_email = str(email.get("sender_email") or "")
		sender_domain = str(email.get("sender_domain") or "")
		subject = str(email.get("subject") or "")
		received_at = str(email.get("received_at") or "")
		labels = email.get("labels") or []
		category = str(email.get("category") or "")
		confidence = email.get("confidence")
		source = str(email.get("classification_source") or "")
		snippet = str(email.get("snippet") or "")

		expander_title = f"{sender_name or sender_email} | {subject[:80] or '(No Subject)'}"
		with st.expander(expander_title, expanded=False):
			st.markdown("---")
			st.write(f"FROM: {sender_name} <{sender_email}>")
			st.write(f"SUBJECT: {subject}")
			st.write(f"DATE: {received_at}")
			st.write(f"LABELS: {labels}")

			st.markdown("---")
			st.write(f"PREDICTED: {category} (confidence: {confidence}) [{source}]")
			st.write(f"REASONING: {snippet or 'No reasoning provided by API yet.'}")

			load_full_body = st.checkbox(
				"Load full body + HTML preview",
				value=False,
				key=f"load_full_{gmail_id}",
			)
			body_plain = snippet
			body_html = ""
			if load_full_body:
				detail = _fetch_email_detail(gmail_id, show_error=True)
				if detail:
					body_plain = str(detail.get("body_plain") or "")
					body_html = str(detail.get("body_html") or "")

			st.markdown("---")
			st.write("BODY:")
			st.text_area(
				label=f"body_{gmail_id}",
				value=body_plain,
				height=240,
				disabled=True,
				label_visibility="collapsed",
			)

			if body_html:
				st.write("HTML Preview:")
				components.html(body_html, height=320, scrolling=True)

			st.markdown("---")
			action_cols = st.columns([1, 2, 1, 1])

			with action_cols[0]:
				if st.button("Approve", key=f"approve_{gmail_id}"):
					ok_action, _, error_action = _api_post(f"/api/emails/{gmail_id}/action", {})
					if not ok_action:
						st.error(error_action)
					else:
						_invalidate_email_cache(gmail_id)
						st.success("Action applied")
						st.rerun()

			with action_cols[1]:
				selected_category = st.selectbox(
					"Select correct category",
					options=CATEGORIES,
					index=CATEGORIES.index(category) if category in CATEGORIES else 0,
					key=f"correct_category_{gmail_id}",
				)
				if st.button("Submit Correction", key=f"correct_{gmail_id}"):
					ok_feedback, _, error_feedback = _api_post(
						"/api/feedback",
						{"gmail_id": gmail_id, "correct_category": selected_category, "notes": ""},
					)
					if not ok_feedback:
						st.error(error_feedback)
					else:
						_invalidate_email_cache(gmail_id)
						st.success("Feedback submitted")
						st.rerun()

			with action_cols[2]:
				if st.button("Always Important", key=f"always_imp_{gmail_id}"):
					ok_rule, _, error_rule = _api_post(
						"/api/feedback/always-important",
						{"sender_email": sender_email},
					)
					if not ok_rule:
						st.error(error_rule)
					else:
						_invalidate_email_cache(gmail_id)
						st.success("Sender marked always important")
						st.rerun()

			with action_cols[3]:
				if st.button("Always Promotional", key=f"always_pro_{gmail_id}"):
					ok_rule, _, error_rule = _api_post(
						"/api/feedback/always-promotional",
						{"sender_domain": sender_domain},
					)
					if not ok_rule:
						st.error(error_rule)
					else:
						_invalidate_email_cache(gmail_id)
						st.success("Domain marked always promotional")
						st.rerun()


def _render_dataset_monitor_page() -> None:
	st.title("Dataset Monitor")
	st.caption("Track correction quality and fine-tuning readiness.")

	ok_feedback, feedback_payload, feedback_error = _api_get("/api/feedback", {"limit": 200, "offset": 0})
	if not ok_feedback:
		st.error(feedback_error)
		return

	feedback_items = feedback_payload.get("items", []) if isinstance(feedback_payload, dict) else []

	ok_rules, rules_payload, rules_error = _api_get("/api/rules")
	if not ok_rules:
		st.warning(rules_error)
		rules_items: list[dict[str, Any]] = []
	else:
		rules_items = rules_payload.get("items", []) if isinstance(rules_payload, dict) else []

	total_feedback = len(feedback_items)
	corrections_made = sum(
		1 for item in feedback_items if str(item.get("predicted") or "") != str(item.get("actual") or "")
	)
	approvals = total_feedback - corrections_made
	approval_rate = (approvals / total_feedback * 100.0) if total_feedback else 0.0

	unique_senders = {
		str(item.get("match_value") or "")
		for item in rules_items
		if str(item.get("match_type") or "") in {"sender_email", "sender_domain"}
	}

	metric_cols = st.columns(4)
	metric_cols[0].metric("Total Feedback", total_feedback)
	metric_cols[1].metric("Corrections Made", corrections_made)
	metric_cols[2].metric("Approval Rate", f"{approval_rate:.1f}%")
	metric_cols[3].metric("Unique Senders Learned", len([s for s in unique_senders if s]))

	st.subheader("Feedback Breakdown")
	resolve_subjects = st.toggle("Resolve email subjects (slower)", value=False)
	feedback_rows = _build_feedback_rows(feedback_items, resolve_subjects=resolve_subjects)
	if feedback_rows:
		st.dataframe(feedback_rows, use_container_width=True, hide_index=True)
	else:
		st.info("No feedback data yet.")

	st.subheader("Category Correction Heatmap")
	_render_correction_heatmap(feedback_items)

	st.subheader("Fine-tuning Readiness")
	actual_counts: dict[str, int] = {category: 0 for category in CATEGORIES}
	for item in feedback_items:
		actual = str(item.get("actual") or "").strip().upper()
		if actual in actual_counts:
			actual_counts[actual] += 1

	for category in CATEGORIES:
		count = actual_counts.get(category, 0)
		progress = min(count / MINIMUM_PER_CATEGORY, 1.0)
		ready_text = "Ready" if count >= MINIMUM_PER_CATEGORY else f"{count}/{MINIMUM_PER_CATEGORY}"
		st.write(f"{category}: {ready_text}")
		st.progress(progress)

	if st.button("Prepare JSONL Export"):
		with st.spinner("Building JSONL from feedback..."):
			st.session_state.feedback_jsonl_export = _export_feedback_as_jsonl(feedback_items)

	jsonl_payload = str(st.session_state.get("feedback_jsonl_export", ""))
	st.download_button(
		"📥 Export Feedback as JSONL (for fine-tuning)",
		data=jsonl_payload,
		file_name="training_data.jsonl",
		mime="application/json",
		disabled=(not jsonl_payload.strip()),
	)


def _build_feedback_rows(
	feedback_items: list[dict[str, Any]],
	*,
	resolve_subjects: bool,
) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	for item in feedback_items:
		gmail_id = str(item.get("gmail_id") or "")
		subject = gmail_id or "(unknown)"
		if resolve_subjects and gmail_id:
			detail = _fetch_email_detail(gmail_id, show_error=False)
			if detail:
				subject = str(detail.get("subject") or "(no subject)")

		date_str = _format_timestamp(item.get("timestamp"))
		rows.append(
			{
				"Email Subject": subject,
				"Predicted": str(item.get("predicted") or ""),
				"Corrected To": str(item.get("actual") or ""),
				"Confidence": item.get("confidence"),
				"Date": date_str,
			}
		)
	return rows


def _render_correction_heatmap(feedback_items: list[dict[str, Any]]) -> None:
	matrix: dict[str, dict[str, int]] = {
		pred: {actual: 0 for actual in CATEGORIES} for pred in CATEGORIES
	}

	for item in feedback_items:
		pred = str(item.get("predicted") or "").strip().upper()
		actual = str(item.get("actual") or "").strip().upper()
		if pred in CATEGORIES and actual in CATEGORIES:
			matrix[pred][actual] += 1

	headers = ["Predicted -> Actual", *CATEGORIES]
	data_rows: list[dict[str, Any]] = []
	for pred in CATEGORIES:
		row: dict[str, Any] = {"Predicted -> Actual": pred}
		for actual in CATEGORIES:
			row[actual] = "-" if pred == actual else matrix[pred][actual]
		data_rows.append(row)

	st.table(data_rows)


def _export_feedback_as_jsonl(feedback_items: list[dict[str, Any]]) -> str:
	lines: list[str] = []
	for item in feedback_items:
		actual = str(item.get("actual") or "").strip().upper()
		gmail_id = str(item.get("gmail_id") or "").strip()
		if not actual or not gmail_id:
			continue

		detail = _fetch_email_detail(gmail_id, show_error=False)
		if not detail:
			continue

		sender_name = str(detail.get("sender_name") or "")
		sender_email = str(detail.get("sender_email") or "")
		subject = str(detail.get("subject") or "")
		body_plain = str(detail.get("body_plain") or "")

		prompt = (
			f"From: {sender_name} <{sender_email}>\n"
			f"Subject: {subject}\n"
			f"Body: {body_plain}"
		)
		record = {"prompt": prompt, "completion": actual}
		lines.append(json.dumps(record, ensure_ascii=True))

	return "\n".join(lines)


def _format_timestamp(raw: Any) -> str:
	if raw is None:
		return ""
	text_value = str(raw)
	for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
		try:
			return datetime.strptime(text_value, fmt).strftime("%b %d")
		except ValueError:
			continue
	return text_value


def main() -> None:
	st.set_page_config(page_title="Email Intelligence Dashboard", layout="wide")
	st.sidebar.title("Navigation")
	page = st.sidebar.radio("Go to", ["📬 Review Queue", "📊 Dataset Monitor"])

	if page == "📬 Review Queue":
		_render_review_queue_page()
	else:
		_render_dataset_monitor_page()


if __name__ == "__main__":
	main()