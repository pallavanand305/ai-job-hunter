from __future__ import annotations

import base64
import re
import secrets
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.client import get_llm
from app.llm.prompts import CLASSIFY_SYSTEM, classify_prompt
from app.models import Application, ApplicationEvent, GmailMessage, Interview, Job, User

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
if settings.gmail_enable_send:
    SCOPES.append("https://www.googleapis.com/auth/gmail.send")
REDIRECT_URI = f"http://{settings.host}:{settings.port}/api/gmail/callback"
_PENDING_STATES: set[str] = set()

CATEGORY_KEYWORDS = {
    "interview": ["interview", "schedule a call", "available for a call", "meet with"],
    "assessment": ["assessment", "coding test", "hackerrank", "codility", "take-home", "challenge"],
    "rejection": ["unfortunately", "not moving forward", "other candidates", "regret to inform", "not selected"],
    "offer": ["offer letter", "job offer", "pleased to offer"],
    "recruiter_response": ["thank you for your application", "received your application", "reviewing your profile"],
}


def _libs_available() -> bool:
    try:
        import google.oauth2.credentials  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401

        return True
    except Exception:
        return False


def status() -> dict:
    token_path = Path(settings.google_token_file)
    return {
        "configured": settings.google_enabled,
        "libs_installed": _libs_available(),
        "read_only": not settings.gmail_enable_send,
        "scopes": list(SCOPES),
        "token_present": token_path.exists(),
        "redirect_uri": REDIRECT_URI,
        "credentials_path": settings.google_client_secrets,
        "hint": (
            "Place an OAuth client JSON at data/google_credentials.json, then run "
            "pip install google-api-python-client google-auth-oauthlib and connect Gmail."
        ),
    }


def _flow():
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_secrets_file(settings.google_client_secrets, scopes=SCOPES, redirect_uri=REDIRECT_URI)


def get_auth_url() -> str:
    if not settings.google_enabled:
        raise RuntimeError("Gmail not configured: missing data/google_credentials.json")
    if not _libs_available():
        raise RuntimeError("Install google-api-python-client and google-auth-oauthlib first")
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=secrets.token_urlsafe(32),
    )
    _PENDING_STATES.add(state)
    return url


def exchange_code(code: str, state: str | None = None) -> None:
    if not state or state not in _PENDING_STATES:
        raise RuntimeError("Invalid or missing OAuth state; start the Gmail connection again")
    _PENDING_STATES.discard(state)
    flow = _flow()
    flow.fetch_token(code=code)
    Path(settings.google_token_file).write_text(flow.credentials.to_json(), encoding="utf-8")


def _credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = Path(settings.google_token_file)
    if not token_path.exists():
        raise RuntimeError("Gmail token missing: connect Gmail first")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _service():
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=_credentials(), cache_discovery=False)


def send_email(to: str, subject: str, body: str) -> str:
    if not settings.gmail_enable_send:
        raise RuntimeError(
            "Gmail is connected read-only. Copy the approved outreach message and send it manually."
        )
    from email.mime.text import MIMEText

    service = _service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent.get("id", "")


def _decode_part(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")


def _extract_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if data and mime_type in {"", "text/plain"}:
        return _decode_part(data)
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_part(part["body"]["data"])
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    if data and mime_type == "text/html":
        from html import unescape

        return unescape(re.sub(r"<[^>]+>", " ", _decode_part(data)))
    return ""


def _heuristic_category(subject: str, body: str) -> str:
    haystack = f"{subject} {body}".lower()
    if any(k in haystack for k in CATEGORY_KEYWORDS["offer"]):
        return "offer"
    if any(k in haystack for k in CATEGORY_KEYWORDS["rejection"]):
        return "rejection"
    if any(k in haystack for k in CATEGORY_KEYWORDS["assessment"]):
        return "assessment"
    if any(k in haystack for k in CATEGORY_KEYWORDS["interview"]):
        return "interview"
    if any(k in haystack for k in CATEGORY_KEYWORDS["recruiter_response"]):
        return "recruiter_response"
    return "other"


def classify(sender: str, subject: str, body: str) -> dict:
    llm = get_llm()
    if llm.usable:
        data = llm.complete_json(
            CLASSIFY_SYSTEM,
            classify_prompt(sender, subject, body),
            default=None,
        )
        if isinstance(data, dict) and data.get("category"):
            return data
    category = _heuristic_category(subject, body)
    summary = re.sub(r"\s+", " ", body)[:400]
    return {
        "category": category,
        "company": None,
        "role": None,
        "interview_at": None,
        "summary": summary,
        "suggested_reply": "",
    }


def _match_application(db: Session, user: User, company: str | None, text: str) -> Application | None:
    applications = db.scalars(
        select(Application).where(Application.user_id == user.id).order_by(Application.id.desc())
    ).all()
    for application in applications:
        job = db.get(Job, application.job_id)
        if not job:
            continue
        if company and company.lower() in (job.company or "").lower():
            return application
        if company and (job.company or "").lower() in company.lower():
            return application
        if job.company and job.company.lower() in text.lower():
            return application
    return None


def sync_inbox(db: Session, user: User, max_results: int = 25) -> dict:
    service = _service()
    response = (
        service.users()
        .messages()
        .list(userId="me", q=settings.gmail_query, maxResults=max_results)
        .execute()
    )
    processed = 0
    updated = 0
    interviews = 0
    results = []
    processed_ids = set(
        db.scalars(
            select(GmailMessage.message_id).where(GmailMessage.user_id == user.id)
        ).all()
    )
    for ref in response.get("messages", []):
        message_id = str(ref.get("id") or "")
        if not message_id or message_id in processed_ids:
            continue
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = msg.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        sender = headers.get("from", "")
        subject = headers.get("subject", "")
        body = _extract_body(payload)[:12000]
        classification = classify(sender, subject, body)
        category = classification.get("category", "other")
        application = _match_application(db, user, classification.get("company"), f"{subject} {body}")
        if application and category in {"interview", "assessment", "rejection", "offer"}:
            mapping = {"interview": "interview", "assessment": "assessment", "rejection": "rejected", "offer": "offer"}
            target = mapping[category]
            from app.services.applications import transition

            try:
                transition(db, application, target, f"Gmail: {subject}")
                updated += 1
            except Exception:
                pass
            interview_at = classification.get("interview_at")
            if category == "interview":
                parsed = None
                if interview_at:
                    try:
                        parsed = datetime.fromisoformat(str(interview_at).replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        parsed = None
                db.add(
                    Interview(
                        application_id=application.id,
                        job_id=application.job_id,
                        scheduled_at=parsed,
                        kind="interview",
                        notes=subject,
                    )
                )
                db.commit()
                interviews += 1
        elif application:
            db.add(
                ApplicationEvent(
                    application_id=application.id,
                    status=application.status,
                    note=f"Email: {subject}",
                )
            )
            db.commit()
        db.add(
            GmailMessage(
                user_id=user.id,
                message_id=message_id,
                subject=subject[:1000],
                category=category,
                application_id=application.id if application else None,
            )
        )
        db.commit()
        processed_ids.add(message_id)
        processed += 1
        results.append(
            {
                "subject": subject,
                "from": sender,
                "category": category,
                "application_id": application.id if application else None,
            }
        )
    return {
        "processed": processed,
        "applications_updated": updated,
        "interviews_created": interviews,
        "messages": results,
    }
