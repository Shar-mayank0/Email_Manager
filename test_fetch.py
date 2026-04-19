from __future__ import annotations

from pprint import pprint
import time
from backend.db.session import SessionLocal, engine, Base
from backend.db.models.email import Email
from backend.db.repository.email_repo import save_email
from backend.core.ingestion.gmail_client import get_gmail_service
from backend.core.ingestion.sync_manager import fetch_new_emails
from backend.core.classification.classifier_pipeline import classify_and_save
from backend.config.constants import SOURCE_LLM

# after saving emails to db, classify them:
import json

db = SessionLocal()
try:
    unclassified = db.query(Email).filter(Email.category == 'UNCLASSIFIED').all()
    print(f'Found {len(unclassified)} unclassified emails')
    for email in unclassified:
        email_dict = {c.name: getattr(email, c.name) for c in email.__table__.columns}
        if isinstance(email_dict.get('labels'), str):
            email_dict['labels'] = json.loads(email_dict['labels'])
        email_dict['email_id'] = email_dict['gmail_id']
        result = classify_and_save(db, email_dict)
        print(f'{result.subject[:45]} → {result.category} ({result.confidence}) [{result.classification_source}]')
        classification_source = str(result.classification_source or "")
        if classification_source == SOURCE_LLM:
            time.sleep(12)
finally:
    db.close()