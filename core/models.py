"""
멀티 에이전트 이메일 어시스턴트 시스템을 위한 핵심 Pydantic 모델입니다.
이 모델은 모든 에이전트와 구성 요소에서 공유됩니다.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, EmailStr, field_validator
import uuid


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class SpamLabel(str, Enum):
    SPAM     = "spam"
    NOT_SPAM = "not_spam"
    SUSPECT  = "suspect"


class PriorityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class DecisionAction(str, Enum):
    AUTO_REPLY  = "auto_reply"
    FORWARD     = "forward"
    ARCHIVE     = "archive"
    FLAG_REVIEW = "flag_review"
    DELETE      = "delete"
    IGNORE      = "ignore"


class ProcessingStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class EmailSource(str, Enum):
    DUMMY = "dummy"
    GMAIL = "gmail"


# ─────────────────────────────────────────────
# Input / Raw email
# ─────────────────────────────────────────────

class Email(BaseModel):
    """Canonical email representation ingested from any source."""

    id:           str       = Field(default_factory=lambda: str(uuid.uuid4()))
    source:       EmailSource = Field(default=EmailSource.DUMMY)
    message_id:   Optional[str] = None           # Original provider message ID
    thread_id:    Optional[str] = None
    subject:      str
    sender:       str
    recipients:   list[str]
    body:         str
    html_body:    Optional[str] = None
    received_at:  datetime = Field(default_factory=datetime.utcnow)
    labels:       list[str] = Field(default_factory=list)
    raw_payload:  Optional[dict[str, Any]] = None  # Original provider payload

    @field_validator("recipients", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


# ─────────────────────────────────────────────
# Agent result models
# ─────────────────────────────────────────────

class SpamResult(BaseModel):
    email_id:   str
    label:      SpamLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning:  str
    indicators: list[str] = Field(default_factory=list)


class PriorityResult(BaseModel):
    email_id:   str
    level:      PriorityLevel
    score:      float = Field(ge=0.0, le=10.0)
    reasoning:  str
    tags:       list[str] = Field(default_factory=list)


class DecisionResult(BaseModel):
    email_id:     str
    action:       DecisionAction
    reasoning:    str
    confidence:   float = Field(ge=0.0, le=1.0)
    should_reply: bool  = False
    forward_to:   Optional[str] = None


class AutoReplyResult(BaseModel):
    email_id:    str
    generated:   bool
    subject:     str  = ""
    body:        str  = ""
    tone:        str  = "professional"
    skip_reason: Optional[str] = None


# ─────────────────────────────────────────────
# Aggregated pipeline result
# ─────────────────────────────────────────────

class EmailProcessingResult(BaseModel):
    """Final aggregated result written to the database."""

    id:            str = Field(default_factory=lambda: str(uuid.uuid4()))
    email_id:      str
    processed_at:  datetime = Field(default_factory=datetime.utcnow)
    status:        ProcessingStatus = ProcessingStatus.COMPLETED

    spam:      Optional[SpamResult]      = None
    priority:  Optional[PriorityResult]  = None
    decision:  Optional[DecisionResult]  = None
    auto_reply: Optional[AutoReplyResult] = None

    processing_time_ms: float = 0.0
    error:              Optional[str] = None

    @property
    def is_spam(self) -> bool:
        return self.spam is not None and self.spam.label == SpamLabel.SPAM

    @property
    def needs_attention(self) -> bool:
        return (
            self.priority is not None
            and self.priority.level in (PriorityLevel.CRITICAL, PriorityLevel.HIGH)
        )


# ─────────────────────────────────────────────
# Tool-call schemas (sent to OpenAI)
# ─────────────────────────────────────────────

class ToolCall(BaseModel):
    name:       str
    arguments:  dict[str, Any]


class AgentToolResult(BaseModel):
    tool_name: str
    result:    dict[str, Any]
    success:   bool = True
    error:     Optional[str] = None


# ─────────────────────────────────────────────
# Agent context passed through the pipeline
# ─────────────────────────────────────────────

class AgentContext(BaseModel):
    """Shared context object flowing through the supervisor."""

    email:          Email
    spam_result:    Optional[SpamResult]      = None
    priority_result: Optional[PriorityResult] = None
    decision_result: Optional[DecisionResult] = None
    reply_result:   Optional[AutoReplyResult] = None
    metadata:       dict[str, Any]            = Field(default_factory=dict)
