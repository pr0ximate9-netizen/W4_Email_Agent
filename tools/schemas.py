"""
각 에이전트에서 사용하는 OpenAI 도구(function) 스키마입니다.
여기에 중앙에서 정의하여 변경 사항이 전체에 전파되도록 합니다.
"""

SPAM_ANALYSIS_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_spam",
        "description": (
            "이메일을 분석하여 스팸, 의심, 정상 중 하나인지 판단하세요. "
            "신뢰도 점수와 주요 지표를 반환하십시오."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "enum": ["spam", "not_spam", "suspect"],
                    "description": "스팸 분류 레이블",
                },
                "confidence": {
                    "type": "number",
                    "description": "분류 신뢰도 (0.0–1.0)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "결정에 대한 한 문장 설명",
                },
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "감지된 스팸/정상 신호 문구 또는 특징 목록",
                },
            },
            "required": ["label", "confidence", "reasoning", "indicators"],
        },
    },
}

PRIORITY_ANALYSIS_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_priority",
        "description": (
            "이메일의 업무 중요도를 평가하여 우선순위 레벨과 수치 점수를 할당하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "description": "이메일의 우선순위 레벨",
                },
                "score": {
                    "type": "number",
                    "description": "숫자형 우선순위 점수 0.0(최저) – 10.0(최고)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "부여된 우선순위에 대한 간단한 근거",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "내용 태그, 예: ['긴급', '고객', '청구서']",
                },
            },
            "required": ["level", "score", "reasoning", "tags"],
        },
    },
}

DECISION_TOOL = {
    "type": "function",
    "function": {
        "name": "make_decision",
        "description": (
            "스팸 및 우선순위 정보를 바탕으로 이메일에 취할 최적의 조치를 결정하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "auto_reply",
                        "forward",
                        "archive",
                        "flag_review",
                        "delete",
                        "ignore",
                    ],
                    "description": "이 이메일에 권장되는 조치",
                },
                "reasoning": {
                    "type": "string",
                    "description": "이 조치를 선택한 이유",
                },
                "confidence": {
                    "type": "number",
                    "description": "결정에 대한 신뢰도 (0.0–1.0)",
                },
                "should_reply": {
                    "type": "boolean",
                    "description": "자동 답장을 생성해야 하는지 여부",
                },
                "forward_to": {
                    "type": "string",
                    "description": "전달할 이메일 주소 (action이 'forward'인 경우)",
                },
            },
            "required": ["action", "reasoning", "confidence", "should_reply"],
        },
    },
}

AUTO_REPLY_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_reply",
        "description": "주어진 이메일에 대해 전문적인 자동 답장을 생성하세요.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "답장 제목 행 (보통 'Re: <원본 제목>')",
                },
                "body": {
                    "type": "string",
                    "description": "답장 이메일의 전체 본문 텍스트",
                },
                "tone": {
                    "type": "string",
                    "enum": ["professional", "friendly", "formal", "concise"],
                    "description": "답장의 어조",
                },
            },
            "required": ["subject", "body", "tone"],
        },
    },
}
