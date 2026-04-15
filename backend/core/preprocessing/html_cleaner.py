from __future__ import annotations

from bs4 import BeautifulSoup


def html_to_plain_text(html: str) -> str:
	"""Convert raw HTML content into plain text."""
	if not html:
		return ""

	soup = BeautifulSoup(html, "html.parser")
	return soup.get_text(separator=" ", strip=True)
