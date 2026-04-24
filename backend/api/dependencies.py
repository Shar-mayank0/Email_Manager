from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy.orm import Session

from backend.core.actions.gmail_actions import _label_cache
from backend.core.ingestion.gmail_client import get_gmail_service as build_gmail_service
from backend.db.session import SessionLocal


_gmail_service: Any | None = None


def get_db() -> Generator[Session, None, None]:
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


def get_gmail_service() -> Any:
	global _gmail_service
	if _gmail_service is None:
		_gmail_service = build_gmail_service()
	return _gmail_service


def get_label_cache() -> dict[str, str]:
	return _label_cache
