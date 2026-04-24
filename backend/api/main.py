from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.dependencies import get_gmail_service
from backend.api.routes import analytics, emails, feedback, rules
from backend.core.actions.gmail_actions import ensure_labels_exist
from backend.db.session import Base, engine


app = FastAPI(title="Email Intelligence Bot", version="1.0.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:3000"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
	Base.metadata.create_all(bind=engine)
	service = get_gmail_service()
	ensure_labels_exist(service)


app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(rules.router, prefix="/api/rules", tags=["rules"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])


@app.get("/health")
def health() -> dict[str, str]:
	return {"status": "ok"}
