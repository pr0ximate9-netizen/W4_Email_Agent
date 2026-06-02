# 멀티 에이전트 이메일 어시스턴트

GPT-4o-mini 기반의 여러 AI 에이전트가 협업하여 이메일을 분석·분류·처리하는 프로덕션 수준의 Python 시스템입니다.

각 에이전트는 OpenAI의 Tool Calling(기능 호출)을 활용하여 구조화된 결과를 반환하며, 병렬 처리 및 Gmail 연동을 지원합니다.

---

# 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                           이메일 소스                               │
│                                                                     │
│   DummyEmailSource(JSON)      GmailEmailSource(OAuth 2.0)           │
│            └───────────────────┬───────────────────┘                │
└────────────────────────────────┼────────────────────────────────────┘
                                 │  list[Email]
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         이메일 집계기(Aggregator)                    │
│                                                                     │
│ asyncio.Semaphore(max_concurrent=5)                                 │
│      └──── 이메일별 Supervisor 생성 ────┘                           │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Supervisor (이메일 단위 처리)                    │
│                                                                     │
│  1단계 ── asyncio.gather() 병렬 처리 ─────────────────────────────  │
│                                                                     │
│       SpamAgent                 PriorityAgent                       │
│   (스팸 분석 도구)              (우선순위 분석 도구)                │
│                                                                     │
│  2단계 ── 순차 처리 ─────────────────────────────────────────────── │
│                                                                     │
│                  DecisionAgent                                      │
│               (의사결정 필요 여부 판단)                             │
│                                                                     │
│  3단계 ── 조건부 처리 ───────────────────────────────────────────── │
│                                                                     │
│                 AutoReplyAgent                                      │
│                  (자동 답장 생성)                                   │
│                                                                     │
│           ※ should_reply=True 인 경우에만 실행                     │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                                 ▼
                  EmailProcessingResult (Pydantic)
                                 │
               ┌─────────────────┴─────────────────┐
               ▼                                   ▼
          SQLite 데이터베이스                  콘솔 출력
            (aiosqlite)                     (요약 테이블)
```

---

# 프로젝트 구조

```text
email_assistant/
├── main.py
│   └── 프로그램 실행 진입점(CLI)
│
├── requirements.txt
├── .env.example
│
├── data/
│   └── dummy_emails.json
│       └── 테스트용 샘플 이메일 데이터
│
├── config/
│   └── settings.py
│       └── 환경변수 및 설정 관리
│
├── core/
│   ├── models.py
│   │   └── Pydantic 모델 정의
│   │
│   └── openai_client.py
│       └── 비동기 OpenAI 클라이언트
│
├── tools/
│   └── schemas.py
│       └── OpenAI Tool Schema 정의
│
├── agents/
│   ├── base.py
│   │   └── 공통 BaseAgent
│   │
│   ├── spam_agent.py
│   ├── priority_agent.py
│   ├── decision_agent.py
│   ├── auto_reply_agent.py
│   │
│   ├── supervisor.py
│   │   └── 에이전트 실행 오케스트레이션
│   │
│   └── aggregator.py
│       └── 이메일 일괄 처리
│
├── persistence/
│   └── database.py
│       └── SQLite 저장소
│
├── integrations/
│   └── email_sources.py
│       └── Dummy/Gmail 이메일 소스
│
└── tests/
    └── test_agents.py
        └── 단위 테스트
```

---

# 빠른 시작 (Quick Start)

## 1. 의존성 설치

```bash
pip install -r requirements.txt
```

---

## 2. 환경 설정

```bash
cp .env.example .env
```

`.env` 파일에 OpenAI API Key를 입력합니다.

```env
OPENAI_API_KEY=your_api_key
```

---

## 3. 더미 이메일 데이터로 실행

기본 실행:

```bash
python main.py
```

상세 로그 출력:

```bash
python main.py --verbose
```

DB 통계 확인:

```bash
python main.py --stats
```

---

## 4. 테스트 실행

API Key 없이도 테스트 가능합니다.

```bash
pytest tests/test_agents.py -v
```

---

# Gmail 연동 방법

## 1. Google Cloud 프로젝트 생성

Google Cloud Console에서 프로젝트를 생성합니다.

---

## 2. Gmail API 활성화

API 라이브러리에서 Gmail API를 활성화합니다.

---

## 3. OAuth 2.0 인증 정보 생성

애플리케이션 유형:

```text
Desktop App
```

으로 생성합니다.

---

## 4. credentials.json 다운로드

다운로드한 파일을 프로젝트 루트에 저장합니다.

```text
project/
├── credentials.json
```

---

## 5. .env 설정

```env
EMAIL_SOURCE=gmail

GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
```

---

## 6. 실행

```bash
python main.py
```

최초 실행 시 브라우저가 열리며 Gmail 접근 권한을 승인하게 됩니다.

인증 후 생성된 토큰은

```text
token.json
```

에 저장되어 이후 재인증 없이 사용할 수 있습니다.

---

## GitHub에 배포하기

간단한 순서로 프로젝트를 GitHub에 올릴 수 있습니다. 로컬에서 Git을 초기화하고 원격 저장소로 푸시하세요.

1) 로컬 Git 초기화 및 첫 커밋

```bash
git init
git add .
git commit -m "Initial commit: multi-agent email assistant"
git branch -M main
```

2) GitHub 원격 저장소 생성

GitHub 웹 UI에서 새 저장소를 만들거나 `gh` CLI를 사용하세요:

```bash
# 예: gh repo create <username>/<repo> --public --source=. --remote=origin --push
gh repo create YOUR_USER/YOUR_REPO --public --source=. --remote=origin --push
```

또는 수동으로 원격을 추가하고 푸시:

```bash
git remote add origin git@github.com:YOUR_USER/YOUR_REPO.git
git push -u origin main
```

3) CI 확인

위에서 추가한 GitHub Actions 워크플로(`.github/workflows/ci.yml`)가 푸시/PR 시 자동으로 테스트를 실행합니다. 실패하면 Actions 탭에서 로그를 확인하세요.


# 에이전트 구성

| 에이전트 | 역할 | 실행 방식 | 결과 |
|----------|------|-----------|------|
| SpamAgent | 스팸 여부 분석 | 병렬 처리 | SpamResult |
| PriorityAgent | 중요도 분석 | 병렬 처리 | PriorityResult |
| DecisionAgent | 의사결정 필요 여부 판단 | 순차 처리 | DecisionResult |
| AutoReplyAgent | 자동 답장 생성 | 조건부 실행 | AutoReplyResult |

---

# 주요 설계 원칙

## 1. Tool Calling 기반 구조

모든 에이전트는 OpenAI Function Calling을 사용합니다.

이를 통해:

- 구조화된 출력
- 타입 검증
- JSON 파싱 오류 감소

를 보장합니다.

---

## 2. Pydantic 기반 데이터 모델

다음 모든 객체는 Pydantic 모델로 정의됩니다.

- Email
- SpamResult
- PriorityResult
- DecisionResult
- AutoReplyResult
- Settings

데이터 유효성 검사는 입력 시점에 수행됩니다.

---

## 3. Clean Architecture

의존성 방향:

```text
core
 ↑
agents
 ↑
orchestrator
```

- core는 다른 계층을 알지 못함
- Agent는 core와 tools만 의존
- DB는 core만 의존

---

## 4. 독립적인 테스트 가능 구조

각 Agent는:

```python
AgentContext -> Result
```

형태로 동작합니다.

OpenAI Client는 의존성 주입(DI) 방식으로 전달되므로 Mock 객체로 쉽게 대체할 수 있습니다.

---

## 5. Gmail 전환 용이성

모든 이메일 소스는 다음 인터페이스를 따릅니다.

```python
fetch() -> list[Email]
```

따라서:

```text
DummyEmailSource
↓
GmailEmailSource
```

교체 시 환경 변수만 변경하면 됩니다.

---

## 6. 비동기(Async) 처리

다음 기술을 활용하여 성능을 최적화했습니다.

- asyncio.gather()
- AsyncOpenAI
- aiosqlite
- asyncio.Semaphore

이를 통해 대량 이메일 처리 시에도 효율적으로 동작합니다.

---

# 환경 변수 설정

| 변수명 | 기본값 | 설명 |
|----------|----------|----------|
| OPENAI_API_KEY | 없음 | OpenAI API Key |
| OPENAI_MODEL | gpt-4o-mini | 사용할 모델 |
| EMAIL_SOURCE | dummy | dummy 또는 gmail |
| PARALLEL_AGENTS | true | Spam/Priority 병렬 실행 여부 |
| MAX_CONCURRENT_EMAILS | 5 | 동시 처리 이메일 수 |
| ENABLE_AUTO_REPLY | false | 자동 답장 기능 활성화 |
| DB_PATH | email_assistant.db | SQLite DB 경로 |

---