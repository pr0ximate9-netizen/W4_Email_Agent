"""
DecisionAgent – 스팸 분석과 우선순위 평가를 바탕으로 추천 동작을 결정합니다.
병렬 분석 단계 이후에 실행됩니다.
"""

from __future__ import annotations

from core.models import (
    AgentContext,
    DecisionResult,
    DecisionAction,
    SpamLabel,
    PriorityLevel,
)
from tools.schemas import DECISION_TOOL
from agents.base import BaseAgent

_SYSTEM = """당신은 이메일 워크플로우를 조율하는 지능형 오케스트레이터입니다.
스팸 분석과 우선순위 평가를 바탕으로 가장 적절한 동작을 결정하십시오:
  - auto_reply  : 사용자를 대신해 자동 응답 전송
  - forward     : 다른 사람 또는 팀으로 전달
  - archive     : 보관함으로 이동 (처리 완료, 응답 불필요)
  - flag_review : 사람이 검토하도록 표시 (불확실하거나 민감한 경우)
  - delete      : 즉시 삭제 (확실한 스팸/정크)
  - ignore      : 받은 편지함에 유지, 별도 조치 없음

결정 규칙 (순서대로 적용):
1. 스팸 → confidence > 0.85면 delete, 아니면 flag_review
2. suspect → flag_review
3. critical priority → flag_review 또는 routine이면 auto_reply
4. high priority + not spam → auto_reply 또는 forward
5. medium / low priority → archive 또는 auto_reply

결과는 반드시 'make_decision' 도구를 호출하여 반환하십시오."""


class DecisionAgent(BaseAgent[DecisionResult]):
    """처리된 이메일에 대해 적절한 동작을 결정합니다."""

    @property
    def name(self) -> str:
        return "DecisionAgent"

    async def run(self, context: AgentContext) -> DecisionResult:
        email    = context.email
        spam     = context.spam_result
        priority = context.priority_result

        context_block = self._email_summary(email)

        if spam:
            context_block += (
                f"\n\n--- 스팸 분석 ---\n"
                f"레이블: {spam.label.value}  |  신뢰도: {spam.confidence:.0%}\n"
                f"이유: {spam.reasoning}\n"
                f"지표: {', '.join(spam.indicators)}"
            )

        if priority:
            context_block += (
                f"\n\n--- 우선순위 분석 ---\n"
                f"등급: {priority.level.value}  |  점수: {priority.score:.1f}/10\n"
                f"이유: {priority.reasoning}\n"
                f"태그: {', '.join(priority.tags)}"
            )

        user_prompt = (
            "아래 분석 내용을 바탕으로 어떤 조치를 취할지 결정하십시오:\n\n"
            + context_block
        )

        args = await self.llm.call_tool(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            tool_schema=DECISION_TOOL,
        )

        return DecisionResult(
            email_id=email.id,
            action=DecisionAction(args["action"]),
            reasoning=args["reasoning"],
            confidence=float(args["confidence"]),
            should_reply=bool(args.get("should_reply", False)),
            forward_to=args.get("forward_to"),
        )
