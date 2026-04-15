from __future__ import annotations

from pprint import pprint

from backend.core.ingestion.gmail_client import get_gmail_service
from backend.core.ingestion.sync_manager import fetch_new_emails


def main() -> None:
    service = get_gmail_service()
    emails = fetch_new_emails(service)
    for email in emails:
        print("PLAIN:", email['body_plain'][:200])
        print("DATE TYPE:", type(email['received_at']), email['received_at'])
        print("---")
    


if __name__ == "__main__":
    main()
