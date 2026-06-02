"""
OpenAI client wrapper.
Handles retries, timeout, and structured tool-call execution.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from openai import APITimeoutError, RateLimitError

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OpenAIClient:
    """Thin async wrapper around the official OpenAI SDK."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout,
            max_retries=0,  # handled by tenacity below
        )
        self.model = settings.openai_model
        self._mock_mode = (
            not bool(settings.openai_api_key)
            or settings.openai_api_key.startswith("sk-dummy")
        )
        if self._mock_mode:
            logger.warning(
                "OpenAI API 키가 설정되지 않았습니다. 로컬 더미 분석 모드로 실행합니다."
            )

    # ── Core completion with retry ──────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        temperature: float = 0.2,
    ) -> Any:
        """Send a chat completion request and return the raw response."""
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self._client.chat.completions.create(**kwargs)
        logger.debug("OpenAI usage: %s", response.usage)
        return response

    # ── Helper: extract first tool call arguments ───────────────────────────

    async def call_tool(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_schema: dict,
    ) -> dict[str, Any]:
        """
        Force a single tool call and return its parsed arguments.
        Raises ValueError if the model does not call the expected tool.
        """
        if self._mock_mode:
            return self._mock_tool_call(
                tool_schema["function"]["name"],
                system_prompt,
                user_prompt,
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        response = await self.chat(
            messages=messages,
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": tool_schema["function"]["name"]}},
        )
        message = response.choices[0].message
        if not message.tool_calls:
            raise ValueError(f"Model did not call tool '{tool_schema['function']['name']}'")

        raw_args = message.tool_calls[0].function.arguments
        return json.loads(raw_args)

    # ── Helper: plain text completion ────────────────────────────────────────

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        if self._mock_mode:
            return self._mock_complete(user_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        response = await self.chat(messages=messages, temperature=temperature)
        return response.choices[0].message.content or ""

    def _mock_tool_call(
        self,
        function_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        if function_name == "analyze_spam":
            return self._mock_analyze_spam(prompt)
        if function_name == "analyze_priority":
            return self._mock_analyze_priority(prompt)
        if function_name == "make_decision":
            return self._mock_make_decision(prompt)
        if function_name == "generate_reply":
            return self._mock_generate_reply(prompt)
        raise ValueError(f"Unknown mock tool: {function_name}")

    def _mock_analyze_spam(self, prompt: str) -> dict[str, Any]:
        text = prompt.lower()
        spam_triggers = [
            "winner", "free", "cheap", "overdue", "prescription",
            "selected", "congratulations", "viagra", "server down",
            "urgent", "production server",
        ]
        suspect_triggers = [
            "invoice", "contract", "renewal", "signature",
            "meeting", "reschedule", "daily digest", "news",
        ]
        if any(word in text for word in spam_triggers):
            label = "spam"
            confidence = 0.95
            indicators = ["스팸 의심 단어"]
        elif any(word in text for word in suspect_triggers):
            label = "suspect"
            confidence = 0.68
            indicators = ["의심스러운 비즈니스 용어"]
        else:
            label = "not_spam"
            confidence = 0.95
            indicators = ["정상적인 이메일"]

        return {
            "label": label,
            "confidence": confidence,
            "reasoning": f"제목/본문에서 {label} 신호를 감지했습니다.",
            "indicators": indicators,
        }

    def _mock_analyze_priority(self, prompt: str) -> dict[str, Any]:
        text = prompt.lower()
        if "production" in text or "server down" in text or "urgent" in text and "server" in text:
            level = "critical"
            score = 9.4
        elif any(word in text for word in ["invoice", "overdue", "contract", "renewal", "deadline", "meeting", "reschedule", "request"]):
            level = "high"
            score = 7.6
        elif any(word in text for word in ["daily digest", "news", "newsletter", "update"]):
            level = "low"
            score = 2.5
        else:
            level = "medium"
            score = 5.0

        tags = []
        if "invoice" in text:
            tags.append("청구서")
        if "contract" in text:
            tags.append("계약")
        if "urgent" in text or "server" in text:
            tags.append("긴급")
        if "meeting" in text:
            tags.append("미팅")
        if not tags:
            tags.append("일반")

        return {
            "level": level,
            "score": score,
            "reasoning": f"메일 내용을 바탕으로 {level} 우선순위로 판단했습니다.",
            "tags": tags,
        }

    def _mock_make_decision(self, prompt: str) -> dict[str, Any]:
        spam = "not_spam"
        priority = "medium"
        if "label: spam" in prompt:
            spam = "spam"
        elif "label: suspect" in prompt:
            spam = "suspect"

        match = re.search(r"등급: (critical|high|medium|low)", prompt)
        if match:
            priority = match.group(1)

        if spam == "spam":
            action = "delete"
            should_reply = False
        elif spam == "suspect":
            action = "flag_review"
            should_reply = False
        elif priority in ("critical", "high"):
            action = "auto_reply"
            should_reply = True
        elif priority == "medium":
            action = "archive"
            should_reply = False
        else:
            action = "ignore"
            should_reply = False

        return {
            "action": action,
            "reasoning": f"스팸 및 우선순위 정보를 바탕으로 {action}을(를) 선택했습니다.",
            "confidence": 0.87,
            "should_reply": should_reply,
            "forward_to": None,
        }

    def _mock_generate_reply(self, prompt: str) -> dict[str, Any]:
        subject_match = re.search(r"제목: (.+)", prompt)
        subject = subject_match.group(1).strip() if subject_match else "문의사항"
        return {
            "subject": f"Re: {subject}",
            "body": (
                "안녕하세요. 이메일을 잘 받았습니다. 요청하신 내용을 검토하고 빠르게 회신드리겠습니다.\n\n"
                "감사합니다."
            ),
            "tone": "professional",
        }

    def _mock_complete(self, user_prompt: str) -> str:
        return "이것은 로컬 대체 응답입니다. 실제 OpenAI API가 없을 때 사용됩니다."
