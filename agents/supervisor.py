"""
Supervisor 오케스트레이터.

파이프라인:
    1단계 (병렬): SpamAgent ║ PriorityAgent
    2단계 (순차): DecisionAgent
    3단계 (조건부): AutoReplyAgent
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Callable, Awaitable

from core.models import (
    Email,
    AgentContext,
    EmailProcessingResult,
    ProcessingStatus,
    SpamResult,
    PriorityResult,
    DecisionResult,
    AutoReplyResult,
)
from agents.spam_agent     import SpamAgent
from agents.priority_agent import PriorityAgent
from agents.decision_agent import DecisionAgent
from agents.auto_reply_agent import AutoReplyAgent
from config.settings import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()


class Supervisor:
    """
    단일 이메일에 대해 모든 에이전트를 조율합니다.
    병렬 및 순차 실행 모드를 모두 지원합니다.
    """

    def __init__(self) -> None:
        self._spam_agent    = SpamAgent()
        self._priority_agent = PriorityAgent()
        self._decision_agent = DecisionAgent()
        self._reply_agent   = AutoReplyAgent()
        self._hooks: list[Callable[[EmailProcessingResult], Awaitable[None]]] = []

    # Public API 
    def add_hook(
        self, hook: Callable[[EmailProcessingResult], Awaitable[None]]
    ) -> None:
        """Register a post-processing async hook (e.g. persistence layer)."""
        self._hooks.append(hook)

    async def process(self, email: Email) -> EmailProcessingResult:
        """Run all agents for *email* and return the aggregated result."""
        start = time.monotonic()
        context = AgentContext(email=email)
        result = EmailProcessingResult(
            email_id=email.id,
            status=ProcessingStatus.PROCESSING,
        )

        try:
            # Phase 1: parallel analysis 
            if settings.parallel_agents:
                spam_result, priority_result = await asyncio.gather(
                    self._spam_agent._safe_run(context),
                    self._priority_agent._safe_run(context),
                    return_exceptions=False,
                )
            else:
                spam_result     = await self._spam_agent._safe_run(context)
                priority_result = await self._priority_agent._safe_run(context)

            context.spam_result     = spam_result
            context.priority_result = priority_result

            missing = []
            if spam_result is None:
                missing.append("spam")
            if priority_result is None:
                missing.append("priority")
            if missing:
                raise RuntimeError(
                    f"Phase1 결과 누락: {', '.join(missing)}"
                )

            # Phase 2: decision
            decision_result = await self._decision_agent._safe_run(context)
            context.decision_result = decision_result
            if decision_result is None:
                raise RuntimeError("Phase2 결과 누락: decision")

            # Phase 3: conditional auto-reply
            reply_result: AutoReplyResult | None = None
            if (
                settings.enable_auto_reply
                and decision_result is not None
                and decision_result.should_reply
            ):
                reply_result = await self._reply_agent._safe_run(context)
                context.reply_result = reply_result

            # Aggregate 
            elapsed_ms = (time.monotonic() - start) * 1000
            result = EmailProcessingResult(
                email_id=email.id,
                status=ProcessingStatus.COMPLETED,
                spam=spam_result,
                priority=priority_result,
                decision=decision_result,
                auto_reply=reply_result,
                processing_time_ms=elapsed_ms,
            )
            logger.info(
                "이메일 %s 처리 완료 %.1f ms | spam=%s priority=%s action=%s",
                email.id,
                elapsed_ms,
                spam_result.label.value if spam_result else "n/a",
                priority_result.level.value if priority_result else "n/a",
                decision_result.action.value if decision_result else "n/a",
            )

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("Supervisor가 이메일 %s 처리를 실패했습니다: %s", email.id, exc, exc_info=True)
            result = EmailProcessingResult(
                email_id=email.id,
                status=ProcessingStatus.FAILED,
                error=str(exc),
                processing_time_ms=elapsed_ms,
            )

        # Run post-processing hooks
        for hook in self._hooks:
            try:
                await hook(result)
            except Exception as hook_exc:
                logger.error("후크 실행 실패: %s", hook_exc, exc_info=True)

        return result
