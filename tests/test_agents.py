"""
Unit & integration tests for the multi-agent email assistant.

Run with:
    pytest tests/test_agents.py -v

Note: LLM calls are mocked so no API key is required for these tests.
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

# Fixtures

@pytest.fixture
def spam_email():
    from core.models import Email, EmailSource
    return Email(
        source=EmailSource.DUMMY,
        subject="CONGRATULATIONS! You won $1,000,000",
        sender="scammer@prize.xyz",
        recipients=["victim@example.com"],
        body="Click here to claim your prize: http://malicious.link/claim",
        received_at=datetime.utcnow(),
    )

@pytest.fixture
def legit_email():
    from core.models import Email, EmailSource
    return Email(
        source=EmailSource.DUMMY,
        subject="Q3 Budget Review – Urgent approval needed",
        sender="cfo@company.com",
        recipients=["ceo@company.com"],
        body="Hi, please review the Q3 budget projections and approve by EOD Friday.",
        received_at=datetime.utcnow(),
    )

@pytest.fixture
def agent_context_spam(spam_email):
    from core.models import AgentContext
    return AgentContext(email=spam_email)

@pytest.fixture
def agent_context_legit(legit_email):
    from core.models import AgentContext
    return AgentContext(email=legit_email)


# Helper: mock LLM tool response

def mock_tool_call(args: dict):
    """Return an async mock that simulates OpenAIClient.call_tool."""
    async def _inner(*a, **kw):
        return args
    return _inner


# Model tests

class TestEmailModel:
    def test_recipients_coercion(self):
        from core.models import Email, EmailSource
        e = Email(
            source=EmailSource.DUMMY,
            subject="Test",
            sender="a@b.com",
            recipients="single@example.com",  # string, not list
            body="hello",
        )
        assert isinstance(e.recipients, list)
        assert e.recipients == ["single@example.com"]

    def test_default_id(self):
        from core.models import Email, EmailSource
        e1 = Email(source=EmailSource.DUMMY, subject="s", sender="a@b.com",
                   recipients=["x@y.com"], body="b")
        e2 = Email(source=EmailSource.DUMMY, subject="s", sender="a@b.com",
                   recipients=["x@y.com"], body="b")
        assert e1.id != e2.id

    def test_email_processing_result_properties(self):
        from core.models import (
            EmailProcessingResult, SpamResult, SpamLabel,
            PriorityResult, PriorityLevel, ProcessingStatus
        )
        spam = SpamResult(email_id="1", label=SpamLabel.SPAM,
                          confidence=0.95, reasoning="test")
        priority = PriorityResult(email_id="1", level=PriorityLevel.CRITICAL,
                                  score=9.5, reasoning="test")
        r = EmailProcessingResult(
            email_id="1",
            status=ProcessingStatus.COMPLETED,
            spam=spam,
            priority=priority,
        )
        assert r.is_spam is True
        assert r.needs_attention is True


# SpamAgent tests

class TestSpamAgent:
    @pytest.mark.asyncio
    async def test_detects_spam(self, agent_context_spam):
        from agents.spam_agent import SpamAgent
        agent = SpamAgent()
        agent.llm.call_tool = mock_tool_call({
            "label": "spam",
            "confidence": 0.97,
            "reasoning": "Classic prize scam",
            "indicators": ["prize scam", "suspicious link"],
        })
        result = await agent.run(agent_context_spam)
        assert result.label.value == "spam"
        assert result.confidence == pytest.approx(0.97)
        assert len(result.indicators) == 2

    @pytest.mark.asyncio
    async def test_legit_email(self, agent_context_legit):
        from agents.spam_agent import SpamAgent
        agent = SpamAgent()
        agent.llm.call_tool = mock_tool_call({
            "label": "not_spam",
            "confidence": 0.98,
            "reasoning": "Legitimate internal email",
            "indicators": [],
        })
        result = await agent.run(agent_context_legit)
        assert result.label.value == "not_spam"

    @pytest.mark.asyncio
    async def test_agent_name(self):
        from agents.spam_agent import SpamAgent
        assert SpamAgent().name == "SpamAgent"

    @pytest.mark.asyncio
    async def test_safe_run_swallows_exceptions(self, agent_context_spam):
        from agents.spam_agent import SpamAgent
        agent = SpamAgent()
        async def boom(*a, **kw):
            raise RuntimeError("LLM unavailable")
        agent.llm.call_tool = boom
        result = await agent._safe_run(agent_context_spam)
        assert result is None  # error swallowed


# PriorityAgent tests

class TestPriorityAgent:
    @pytest.mark.asyncio
    async def test_critical_priority(self, agent_context_legit):
        from agents.priority_agent import PriorityAgent
        agent = PriorityAgent()
        agent.llm.call_tool = mock_tool_call({
            "level": "critical",
            "score": 9.5,
            "reasoning": "CEO approval needed by EOD",
            "tags": ["approval", "budget", "urgent"],
        })
        result = await agent.run(agent_context_legit)
        assert result.level.value == "critical"
        assert result.score == pytest.approx(9.5)
        assert "urgent" in result.tags

    @pytest.mark.asyncio
    async def test_low_priority_spam(self, agent_context_spam):
        from agents.priority_agent import PriorityAgent
        agent = PriorityAgent()
        agent.llm.call_tool = mock_tool_call({
            "level": "low",
            "score": 0.5,
            "reasoning": "Likely junk",
            "tags": [],
        })
        result = await agent.run(agent_context_spam)
        assert result.level.value == "low"

    @pytest.mark.asyncio
    async def test_agent_name(self):
        from agents.priority_agent import PriorityAgent
        assert PriorityAgent().name == "PriorityAgent"


# DecisionAgent tests

class TestDecisionAgent:
    @pytest.mark.asyncio
    async def test_delete_spam(self, agent_context_spam):
        from agents.decision_agent import DecisionAgent
        from core.models import SpamResult, SpamLabel
        agent = DecisionAgent()
        agent_context_spam.spam_result = SpamResult(
            email_id=agent_context_spam.email.id,
            label=SpamLabel.SPAM, confidence=0.97, reasoning="scam"
        )
        agent.llm.call_tool = mock_tool_call({
            "action": "delete",
            "reasoning": "High-confidence spam",
            "confidence": 0.95,
            "should_reply": False,
        })
        result = await agent.run(agent_context_spam)
        assert result.action.value == "delete"
        assert result.should_reply is False

    @pytest.mark.asyncio
    async def test_auto_reply_legit(self, agent_context_legit):
        from agents.decision_agent import DecisionAgent
        agent = DecisionAgent()
        agent.llm.call_tool = mock_tool_call({
            "action": "auto_reply",
            "reasoning": "High priority, requires acknowledgement",
            "confidence": 0.88,
            "should_reply": True,
        })
        result = await agent.run(agent_context_legit)
        assert result.should_reply is True
        assert result.action.value == "auto_reply"

    @pytest.mark.asyncio
    async def test_agent_name(self):
        from agents.decision_agent import DecisionAgent
        assert DecisionAgent().name == "DecisionAgent"


# AutoReplyAgent tests

class TestAutoReplyAgent:
    @pytest.mark.asyncio
    async def test_skips_when_no_reply_needed(self, agent_context_legit):
        from agents.auto_reply_agent import AutoReplyAgent
        from core.models import DecisionResult, DecisionAction
        agent = AutoReplyAgent()
        agent_context_legit.decision_result = DecisionResult(
            email_id=agent_context_legit.email.id,
            action=DecisionAction.ARCHIVE,
            reasoning="low priority",
            confidence=0.9,
            should_reply=False,
        )
        result = await agent.run(agent_context_legit)
        assert result.generated is False
        assert result.skip_reason is not None

    @pytest.mark.asyncio
    async def test_generates_reply_when_requested(self, agent_context_legit):
        from agents.auto_reply_agent import AutoReplyAgent
        from core.models import DecisionResult, DecisionAction
        agent = AutoReplyAgent()
        agent_context_legit.decision_result = DecisionResult(
            email_id=agent_context_legit.email.id,
            action=DecisionAction.AUTO_REPLY,
            reasoning="needs reply",
            confidence=0.9,
            should_reply=True,
        )
        agent.llm.call_tool = mock_tool_call({
            "subject": "Re: Q3 Budget Review",
            "body": "Hi, received your message. Will review and revert shortly.",
            "tone": "professional",
        })
        result = await agent.run(agent_context_legit)
        assert result.generated is True
        assert result.subject.startswith("Re:")

    @pytest.mark.asyncio
    async def test_skips_without_decision_context(self, agent_context_legit):
        from agents.auto_reply_agent import AutoReplyAgent
        agent = AutoReplyAgent()
        # No decision result attached
        result = await agent.run(agent_context_legit)
        assert result.generated is False

    @pytest.mark.asyncio
    async def test_agent_name(self):
        from agents.auto_reply_agent import AutoReplyAgent
        assert AutoReplyAgent().name == "AutoReplyAgent"


# Supervisor tests

class TestSupervisor:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, spam_email):
        from agents.supervisor import Supervisor
        from core.models import SpamLabel, ProcessingStatus

        supervisor = Supervisor()

        # Mock all sub-agents
        supervisor._spam_agent.llm.call_tool = mock_tool_call({
            "label": "spam", "confidence": 0.96,
            "reasoning": "scam", "indicators": ["prize"],
        })
        supervisor._priority_agent.llm.call_tool = mock_tool_call({
            "level": "low", "score": 0.5,
            "reasoning": "junk", "tags": [],
        })
        supervisor._decision_agent.llm.call_tool = mock_tool_call({
            "action": "delete", "reasoning": "spam", "confidence": 0.95, "should_reply": False,
        })

        result = await supervisor.process(spam_email)
        assert result.status == ProcessingStatus.COMPLETED
        assert result.spam is not None
        assert result.spam.label == SpamLabel.SPAM
        assert result.priority is not None
        assert result.decision is not None

    @pytest.mark.asyncio
    async def test_hook_is_called(self, legit_email):
        from agents.supervisor import Supervisor
        from core.models import ProcessingStatus

        supervisor = Supervisor()
        supervisor._spam_agent.llm.call_tool = mock_tool_call({
            "label": "not_spam", "confidence": 0.99, "reasoning": "ok", "indicators": [],
        })
        supervisor._priority_agent.llm.call_tool = mock_tool_call({
            "level": "high", "score": 7.5, "reasoning": "important", "tags": ["budget"],
        })
        supervisor._decision_agent.llm.call_tool = mock_tool_call({
            "action": "flag_review", "reasoning": "needs human review",
            "confidence": 0.8, "should_reply": False,
        })

        called_with = []
        async def hook(result):
            called_with.append(result)

        supervisor.add_hook(hook)
        await supervisor.process(legit_email)
        assert len(called_with) == 1
        assert called_with[0].status == ProcessingStatus.COMPLETED


# Aggregator tests

class TestAggregator:
    @pytest.mark.asyncio
    async def test_batch_processing(self, spam_email, legit_email):
        from agents.supervisor import Supervisor
        from agents.aggregator import Aggregator
        from core.models import ProcessingStatus

        supervisor = Supervisor()
        # Mock all agents uniformly
        for agent in [
            supervisor._spam_agent,
            supervisor._priority_agent,
            supervisor._decision_agent,
        ]:
            agent.llm.call_tool = mock_tool_call({
                "label": "not_spam", "confidence": 0.9, "reasoning": "ok", "indicators": [],
                "level": "medium", "score": 5.0, "tags": [],
                "action": "archive", "should_reply": False,
            })

        supervisor._spam_agent.llm.call_tool = mock_tool_call({
            "label": "not_spam", "confidence": 0.9, "reasoning": "ok", "indicators": [],
        })
        supervisor._priority_agent.llm.call_tool = mock_tool_call({
            "level": "medium", "score": 5.0, "reasoning": "ok", "tags": [],
        })
        supervisor._decision_agent.llm.call_tool = mock_tool_call({
            "action": "archive", "reasoning": "ok", "confidence": 0.8, "should_reply": False,
        })

        aggregator = Aggregator(supervisor=supervisor)
        stats = await aggregator.process_batch([spam_email, legit_email])

        assert stats.total == 2
        assert stats.completed + stats.failed == 2

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        from agents.aggregator import Aggregator
        agg = Aggregator()
        stats = await agg.process_batch([])
        assert stats.total == 0
        assert stats.completed == 0


# DummyEmailSource tests

class TestDummyEmailSource:
    @pytest.mark.asyncio
    async def test_returns_builtin_samples(self, tmp_path):
        from integrations.email_sources import DummyEmailSource
        src = DummyEmailSource(data_path=str(tmp_path / "missing.json"))
        emails = await src.fetch()
        assert len(emails) > 0
        for e in emails:
            assert e.subject
            assert e.sender
            assert isinstance(e.recipients, list)

    @pytest.mark.asyncio
    async def test_loads_custom_json(self, tmp_path):
        from integrations.email_sources import DummyEmailSource
        data = [
            {
                "subject": "Test email",
                "sender": "test@example.com",
                "recipients": ["user@example.com"],
                "body": "Hello world",
                "received_at": datetime.utcnow().isoformat(),
            }
        ]
        path = tmp_path / "emails.json"
        path.write_text(json.dumps(data))
        src = DummyEmailSource(data_path=str(path))
        emails = await src.fetch()
        assert len(emails) == 1
        assert emails[0].subject == "Test email"

    @pytest.mark.asyncio
    async def test_max_results_respected(self, tmp_path):
        from integrations.email_sources import DummyEmailSource
        src = DummyEmailSource(data_path=str(tmp_path / "missing.json"))
        emails = await src.fetch(max_results=3)
        assert len(emails) <= 3


# Database tests

class TestDatabase:
    @pytest.mark.asyncio
    async def test_upsert_and_retrieve(self, tmp_path, legit_email):
        from persistence.database import Database
        from core.models import EmailProcessingResult, ProcessingStatus, SpamResult, SpamLabel

        db = Database(db_path=str(tmp_path / "test.db"))
        async with db:
            await db.upsert_email(legit_email)
            result = EmailProcessingResult(
                email_id=legit_email.id,
                status=ProcessingStatus.COMPLETED,
                spam=SpamResult(
                    email_id=legit_email.id,
                    label=SpamLabel.NOT_SPAM,
                    confidence=0.99,
                    reasoning="clean",
                ),
            )
            await db.save_result(result)

            rows = await db.get_results_for_email(legit_email.id)
            assert len(rows) == 1
            assert rows[0]["spam_label"] == "not_spam"

    @pytest.mark.asyncio
    async def test_stats(self, tmp_path, spam_email, legit_email):
        from persistence.database import Database
        from core.models import (
            EmailProcessingResult, ProcessingStatus,
            SpamResult, SpamLabel, PriorityResult, PriorityLevel,
        )

        db = Database(db_path=str(tmp_path / "stats_test.db"))
        async with db:
            for email, label, level in [
                (spam_email, SpamLabel.SPAM, PriorityLevel.LOW),
                (legit_email, SpamLabel.NOT_SPAM, PriorityLevel.HIGH),
            ]:
                await db.upsert_email(email)
                r = EmailProcessingResult(
                    email_id=email.id,
                    status=ProcessingStatus.COMPLETED,
                    spam=SpamResult(email_id=email.id, label=label,
                                   confidence=0.9, reasoning="test"),
                    priority=PriorityResult(email_id=email.id, level=level,
                                           score=5.0, reasoning="test"),
                )
                await db.save_result(r)

            stats = await db.get_stats()
            assert stats["spam_spam"] == 1
            assert stats["spam_not_spam"] == 1
            assert stats["priority_high"] == 1
            assert stats["total_completed"] == 2
