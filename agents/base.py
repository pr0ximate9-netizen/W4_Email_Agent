"""
모든 에이전트의 추상 기본 클래스입니다.
모든 에이전트는 `run()`과 `name`을 구현해야 합니다.
"""

from __future__ import annotations
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from core.models import Email, AgentContext
from core.openai_client import OpenAIClient

T = TypeVar("T")
logger = logging.getLogger(__name__)


class BaseAgent(ABC, Generic[T]):
    """
    모든 에이전트가 만족해야 하는 계약:
      - 고유한 `name` 선언
      - `run(context) -> T` 구현
      - `self.llm`을 통해 OpenAI에 접근
    """

    def __init__(self) -> None:
        self.llm = OpenAIClient()
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """에이전트 이름 식별자입니다."""
        ...

    @abstractmethod
    async def run(self, context: AgentContext) -> T:
        """에이전트를 실행하고 타입화된 결과를 반환합니다."""
        ...

    # Convenience helpers 

    def _email_summary(self, email: Email) -> str:
        """프롬프트용 이메일 요약 텍스트입니다."""
        return (
            f"발신자: {email.sender}\n"
            f"수신자: {', '.join(email.recipients)}\n"
            f"제목: {email.subject}\n"
            f"본문:\n{email.body[:2000]}"  # 최대 2,000자 제한
        )

    async def _safe_run(self, context: AgentContext) -> T | None:
        """시간 측정 및 예외 처리를 포함하여 안전하게 실행합니다."""
        start = time.monotonic()
        try:
            result = await self.run(context)
            elapsed = (time.monotonic() - start) * 1000
            self._logger.info("%s finished in %.1f ms", self.name, elapsed)
            return result
        except Exception as exc:
            self._logger.error("%s failed: %s", self.name, exc, exc_info=True)
            return None
