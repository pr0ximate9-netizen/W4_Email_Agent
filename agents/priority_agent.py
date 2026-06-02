"""
PriorityAgent – 이메일의 중요도를 점수화하고 순위를 매깁니다.
SpamAgent와 병렬로 실행됩니다.
"""

from __future__ import annotations

from core.models import AgentContext, PriorityResult, PriorityLevel
from tools.schemas import PRIORITY_ANALYSIS_TOOL
from agents.base import BaseAgent

_SYSTEM = """당신은 업무용 이메일을 분류하는 전문 비서입니다.
이메일의 중요도와 긴급도를 평가하여 다음 중 하나를 할당하십시오:
  - critical : 즉각 대응 필요 (SLA 위반, CEO, 장애, 법무)
  - high     : 당일 답변 필요 (고객 요청, 마감, 에스컬레이션)
  - medium   : 2~3일 내 대응 권장 (일반 문의, 보고서, 업데이트)
  - low      : 긴급하지 않음 (뉴스레터, 알림, FYI)

전체 중요도를 반영하는 0~10 점수를 부여하세요.
관련 태그도 추출하십시오 (예: ['청구서', '긴급', '고객']).
분석 결과는 반드시 'analyze_priority' 도구를 호출하여 반환하십시오."""


class PriorityAgent(BaseAgent[PriorityResult]):
    """이메일 중요도와 긴급도를 평가합니다."""

    @property
    def name(self) -> str:
        return "PriorityAgent"

    async def run(self, context: AgentContext) -> PriorityResult:
        email = context.email
        user_prompt = (
            "다음 이메일의 우선순위를 평가하십시오:\n\n"
            + self._email_summary(email)
        )

        args = await self.llm.call_tool(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            tool_schema=PRIORITY_ANALYSIS_TOOL,
        )

        level_raw = str(args["level"]).strip().lower().replace(" ", "_")
        return PriorityResult(
            email_id=email.id,
            level=PriorityLevel(level_raw),
            score=float(args["score"]),
            reasoning=str(args["reasoning"]).strip(),
            tags=args.get("tags", []),
        )
