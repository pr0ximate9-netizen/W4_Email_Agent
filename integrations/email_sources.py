"""
이메일 소스 통합 모듈.

Architecture:
  EmailSource (ABC)
    ├── DummyEmailSource   – dummy_emails.json에서 읽음 (Default)
    └── GmailEmailSource   – Gmail API(OAuth 2.0) 사용

sources 변경 : EMAIL_SOURCE=gmail in .env 설정 또는 --source gmail CLI 옵션
"""

from __future__ import annotations
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from core.models import Email, EmailSource as SourceEnum
from config.settings import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()


# Abstract base

class BaseEmailSource(ABC):
    @abstractmethod
    async def fetch(self, max_results: int = 20) -> list[Email]:
        """Fetch emails and return as canonical Email objects."""
        ...

    @property
    @abstractmethod
    def source_type(self) -> SourceEnum:
        ...


# 더미 소스 – JSON 파일

class DummyEmailSource(BaseEmailSource):
    """로컬 개발/테스트용 정적 JSON 데이터를 읽습니다."""

    def __init__(self, data_path: str | None = None) -> None:
        self._path = Path(data_path or settings.dummy_data_path)

    @property
    def source_type(self) -> SourceEnum:
        return SourceEnum.DUMMY

    async def fetch(self, max_results: int = 20) -> list[Email]:
        if not self._path.exists():
            logger.warning("더미 데이터 파일을 찾을 수 없습니다: %s – 내장 샘플 사용", self._path)
            return self._builtin_samples()[:max_results]

        raw = json.loads(self._path.read_text(encoding="utf-8"))
        emails: list[Email] = []
        for item in raw[:max_results]:
            try:
                emails.append(
                    Email(
                        source=SourceEnum.DUMMY,
                        message_id=item.get("message_id"),
                        thread_id=item.get("thread_id"),
                        subject=item["subject"],
                        sender=item["sender"],
                        recipients=item.get("recipients", [item.get("to", "user@example.com")]),
                        body=item["body"],
                        received_at=datetime.fromisoformat(
                            item.get("received_at", datetime.utcnow().isoformat())
                        ),
                        labels=item.get("labels", []),
                    )
                )
            except Exception as exc:
                logger.error("이메일 항목을 파싱하지 못했습니다: %s – %s", item, exc)

        logger.info("DummyEmailSource가 %d개의 이메일을 로드했습니다", len(emails))
        return emails

    # 내장 샘플 세트

    @staticmethod
    def _builtin_samples() -> list[Email]:
        now = datetime.utcnow()
        return [
            Email(
                source=SourceEnum.DUMMY,
                subject="Urgent: Server down – production outage",
                sender="ops-team@company.com",
                recipients=["cto@company.com"],
                body=(
                    "Hi,\n\nOur production servers have been down for 30 minutes."
                    " Customers are unable to access the platform. "
                    "We need immediate assistance. Please call the incident bridge now."
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="You've won $1,000,000! Claim now!!!",
                sender="noreply@prize-winner2024.xyz",
                recipients=["user@example.com"],
                body=(
                    "Congratulations! You have been selected as our lucky winner."
                    " Click here to claim your prize: http://suspicious-link.xyz/claim"
                    " Enter your bank details to receive your winnings immediately."
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="Q3 Sales Report – action required",
                sender="sales-manager@company.com",
                recipients=["ceo@company.com"],
                body=(
                    "Hi,\n\nPlease find attached the Q3 sales report."
                    " Revenue is up 12% YoY however churn increased by 3%."
                    " I need your sign-off on the revised forecast by Friday."
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="Meeting re-schedule request",
                sender="client.a@bigcorp.com",
                recipients=["account@company.com"],
                body=(
                    "Hello,\n\nCould we move our Thursday 2pm sync to Friday at 10am?"
                    " I have a conflict and don't want to miss the product update."
                    "\n\nThanks,\nClient A"
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="Weekly newsletter – Tech Digest",
                sender="digest@technews.io",
                recipients=["subscriber@example.com"],
                body=(
                    "This week in tech: OpenAI releases new model, "
                    "Google updates search algorithm, Apple announces new hardware."
                    " Unsubscribe: https://technews.io/unsub"
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="Invoice #4521 overdue – immediate payment required",
                sender="billing@supplier.com",
                recipients=["finance@company.com"],
                body=(
                    "Dear Finance Team,\n\nInvoice #4521 for $8,500 was due on 2024-11-01."
                    " Payment is now 30 days overdue."
                    " Please remit payment immediately to avoid service suspension.\n\n"
                    "Best regards,\nSupplier Billing Team"
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="Job application: Senior Software Engineer",
                sender="candidate@gmail.com",
                recipients=["hr@company.com"],
                body=(
                    "Dear Hiring Manager,\n\nI am writing to apply for the Senior"
                    " Software Engineer role posted on LinkedIn."
                    " I have 8 years of experience in Python and distributed systems."
                    " I have attached my resume for your consideration.\n\nBest,\nJohn Doe"
                ),
                received_at=now,
            ),
            Email(
                source=SourceEnum.DUMMY,
                subject="OFFER: Cheap Rx medications – no prescription needed",
                sender="pharma@spammail.biz",
                recipients=["target@example.com"],
                body=(
                    "Buy cheap meds online! No prescription needed!"
                    " Viagra, Cialis, Ozempic at 90% discount."
                    " Visit: http://cheaprx.biz/order – Limited time offer!"
                ),
                received_at=now,
            ),
        ]


# Gmail source (OAuth 2.0)

class GmailEmailSource(BaseEmailSource):
    """
    Gmail에서 실시간 이메일을 OAuth 2.0으로 가져옵니다.

    설정 단계:
      1. Google Cloud 프로젝트 생성 후 Gmail API 활성화
      2. OAuth 2.0 인증 정보 생성 (Desktop app)
      3. credentials.json 다운로드 후 GMAIL_CREDENTIALS_PATH 설정
      4. 첫 실행 시 브라우저에서 동의 화면이 열립니다.
         토큰은 이후 사용을 위해 GMAIL_TOKEN_PATH에 저장됩니다.
      5. .env에서 EMAIL_SOURCE=gmail 설정

    필요한 패키지: google-auth-oauthlib google-api-python-client
    """

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self) -> None:
        self._service = None

    @property
    def source_type(self) -> SourceEnum:
        return SourceEnum.GMAIL

    def _build_service(self):
        """Lazy-initialise the Gmail API service."""
        if self._service:
            return self._service

        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ImportError(
                "Gmail 의존성이 누락되었습니다. pip install google-auth-oauthlib google-api-python-client 를 실행하세요."
            ) from exc

        token_path = Path(settings.gmail_token_path)
        creds = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.gmail_credentials_path, self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    async def fetch(self, max_results: int = 20) -> list[Email]:
        import asyncio
        service = self._build_service()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync, service, max_results)

    def _fetch_sync(self, service, max_results: int) -> list[Email]:
        import base64

        result   = service.users().messages().list(
            userId="me", maxResults=max_results, labelIds=["INBOX"]
        ).execute()
        messages = result.get("messages", [])
        emails   = []

        for msg_meta in messages:
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_meta["id"], format="full"
                ).execute()
                email = self._parse_gmail_message(msg)
                emails.append(email)
            except Exception as exc:
                logger.error("Gmail 메시지를 파싱하지 못했습니다 %s: %s", msg_meta["id"], exc)

        logger.info("GmailEmailSource가 %d개의 이메일을 가져왔습니다", len(emails))
        return emails

    def _parse_gmail_message(self, msg: dict) -> Email:
        import base64

        headers = {h["name"].lower(): h["value"]
                   for h in msg["payload"].get("headers", [])}

        subject    = headers.get("subject", "(no subject)")
        sender     = headers.get("from", "unknown")
        to_raw     = headers.get("to", "")
        recipients = [r.strip() for r in to_raw.split(",") if r.strip()]
        date_str   = headers.get("date", "")

        try:
            from email.utils import parsedate_to_datetime
            received_at = parsedate_to_datetime(date_str) if date_str else datetime.utcnow()
        except Exception:
            received_at = datetime.utcnow()

        body = self._extract_body(msg["payload"])

        return Email(
            source=SourceEnum.GMAIL,
            message_id=msg.get("id"),
            thread_id=msg.get("threadId"),
            subject=subject,
            sender=sender,
            recipients=recipients or ["unknown"],
            body=body,
            received_at=received_at,
            labels=msg.get("labelIds", []),
            raw_payload={"id": msg["id"], "snippet": msg.get("snippet", "")},
        )

    def _extract_body(self, payload: dict) -> str:
        import base64

        def decode_part(data: str) -> str:
            try:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            except Exception:
                return ""

        mime_type = payload.get("mimeType", "")

        # Single-part
        if "data" in payload.get("body", {}):
            return decode_part(payload["body"]["data"])

        # Multi-part
        parts    = payload.get("parts", [])
        plain    = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
        html     = next((p for p in parts if p.get("mimeType") == "text/html"), None)
        selected = plain or html
        if selected and selected.get("body", {}).get("data"):
            return decode_part(selected["body"]["data"])

        return "(no body)"


# Factory

def get_email_source(source_override: str | None = None) -> BaseEmailSource:
    """Return the configured email source."""
    source = source_override or settings.email_source
    if source == "gmail":
        return GmailEmailSource()
    return DummyEmailSource()
