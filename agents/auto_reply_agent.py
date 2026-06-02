"""
AutoReplyAgent – 상황에 맞는 전문적인 답장 초안을 생성합니다.
DecisionAgent가 should_reply=True로 설정한 경우에만 실행됩니다.
"""

from __future__ import annotations

from core.models import AgentContext, AutoReplyResult
from tools.schemas import AUTO_REPLY_TOOL
from agents.base import BaseAgent

_SYSTEM = """당신은 바쁜 임원을 대신해 이메일 답장을 작성하는 시니어 비서입니다.
명확하고 간결하며 전문적인 답변을 작성하십시오.
규칙:
  - 수신 이메일의 격식에 맞추세요
  - 필요한 경우를 제외하고 150단어 이내로 작성하세요
  - 과장하거나 민감한 정보를 공유하지 마세요
  - 적절한 맺음말로 마무리하세요
  - 결과는 반드시 'generate_reply' 도구를 호출하여 반환하십시오."""


class AutoReplyAgent(BaseAgent[AutoReplyResult]):
    """응답이 필요한 이메일에 대한 자동 답장 초안을 생성합니다."""

    @property
    def name(self) -> str:
        return "AutoReplyAgent"

    async def run(self, context: AgentContext) -> AutoReplyResult:
        email    = context.email
        decision = context.decision_result

        # 명시적으로 요청된 경우에만 생성합니다
        if decision is None or not decision.should_reply:
            return AutoReplyResult(
                email_id=email.id,
                generated=False,
                skip_reason="DecisionAgent가 답장을 요청하지 않았습니다",
            )

        priority_hint = ""
        if context.priority_result:
            priority_hint = (
                f"\n우선순위: {context.priority_result.level.value} – "
                f"{context.priority_result.reasoning}"
            )

        user_prompt = (
            f"이 이메일에 대한 답장을 작성하십시오.{priority_hint}\n\n"
            + self._email_summary(email)
        )

        args = await self.llm.call_tool(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            tool_schema=AUTO_REPLY_TOOL,
        )

        return AutoReplyResult(
            email_id=email.id,
            generated=True,
            subject=args["subject"],
            body=args["body"],
            tone=args.get("tone", "professional"),
        )
