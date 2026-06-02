"""
SpamAgent – 수신 이메일을 스팸, 의심, 정상으로 분류합니다.
GPT-4o-mini를 사용하며 tool call을 강제합니다.
"""

from __future__ import annotations

from core.models import AgentContext, SpamResult, SpamLabel
from tools.schemas import SPAM_ANALYSIS_TOOL
from agents.base import BaseAgent

_SYSTEM = """당신은 이메일 스팸 탐지 전문가입니다.
이메일의 발신자, 제목, 본문을 분석하여 다음 중 하나로 분류하십시오:
  - spam     : 원치 않는 대량 메일, 피싱, 사기, 광고
  - suspect  : 스팸 신호가 있으나 합법일 가능성도 있는 경우
  - not_spam : 정상적인 개인 또는 업무용 커뮤니케이션

신중하게 판단하십시오: 높은 확신이 있을 때만 spam으로 표시하세요.
분석 결과는 반드시 'analyze_spam' 도구를 호출하여 반환하십시오."""


class SpamAgent(BaseAgent[SpamResult]):
    """LLM 툴 호출 아키텍처로 스팸을 감지합니다."""

    @property
    def name(self) -> str:
        return "SpamAgent"

    async def run(self, context: AgentContext) -> SpamResult:
        email = context.email
        user_prompt = (
            "아래 이메일을 스팸 신호 관점에서 분석하십시오:\n\n"
            + self._email_summary(email)
        )

        args = await self.llm.call_tool(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            tool_schema=SPAM_ANALYSIS_TOOL,
        )

        label_raw = str(args["label"]).strip().lower().replace(" ", "_")
        return SpamResult(
            email_id=email.id,
            label=SpamLabel(label_raw),
            confidence=float(args["confidence"]),
            reasoning=str(args["reasoning"]).strip(),
            indicators=args.get("indicators", []),
        )
