# 공통 오케스트레이터 Deep Agent 구현 및 매니지먼트 연결 루프 가이드

> **이 문서는 `/loop` 스킬의 실행 지시서다.**  
> 각 태스크를 순서대로 수행하고, 태스크마다 지정된 **백엔드·프론트엔드 테스트**를 모두 통과할 때까지 반복한다.  
> 모든 태스크의 테스트가 오류 없이 통과되면 루프를 종료한다.

---

## 루프 에이전트 행동 규칙

> **이 규칙은 루프 전체에 걸쳐 항상 적용된다.**

### 응답 대기 및 자율 진행

> **사용자가 자리를 비웠다. 어떤 상황에서도 사용자에게 묻지 않는다. 모든 판단을 스스로 내리고 끝까지 진행한다.**

- 불확실한 상황이 생기면 **가장 안전하고 보수적인 방향으로 즉시 판단하고 진행**한다. 대기하지 않는다.
- 막히면 다른 접근 방식을 시도한다. 사용자를 깨우지 않는다.
- 단, 아래 상황만 예외적으로 멈추고 작업 내역을 기록한 뒤 루프를 종료한다 (사용자가 깨어났을 때 확인할 수 있도록):
  - `core/models.py` ORM 변경이 필요한 경우 → `docs/management/BLOCKED.md`에 사유 기록 후 종료
  - 기존 API 계약을 **파괴적으로 변경**해야만 진행 가능한 경우 → 동일하게 기록 후 종료
  - 비용이 발생하는 외부 API를 실 데이터로 **대량(50건 이상)** 호출해야 하는 경우 → 동일하게 기록 후 종료

### 패키지 의존성 확인

새 라이브러리가 필요하면 먼저 이미 설치되어 있는지 확인한다. 없으면 추가한다.

```bash
# 백엔드 — pyproject.toml 확인 후 없으면 추가
cd backend && uv run python -c "import <패키지명>"
# 없으면: uv add <패키지명>

# 프론트엔드 — package.json 확인 후 없으면 추가
cd frontend && node -e "require('<패키지명>')"
# 없으면: pnpm add <패키지명>
```

### 커밋 전략

- 각 태스크가 테스트를 모두 통과하면 **태스크 단위로 커밋**한다.
- 커밋 메시지 형식: `add: deep agent 오케스트레이터 구현 (Task N)` (한국어, CLAUDE.md 컨벤션 준수)
- 여러 태스크를 한 커밋에 묶지 않는다 — 태스크별 원자적 커밋.
- 커밋 전 Ruff + tsc 통과 확인 필수.

### 기대값 불일치 시 처리

테스트 명령어가 오류 없이 실행됐지만 **응답 내용이 기대값과 다른 경우**, 아래 절차를 따른다.

1. **실제 응답 전체를 읽는다** — `jq` 또는 그대로 출력해서 어떤 값이 나왔는지 확인
2. **근본 원인을 찾는다** — 아래 패턴 참고

| 실제 응답 | 기대값 | 진단 방향 |
|---|---|---|
| `"source": "clio"` | `"source": "management"` | `intent.py` LLM 분류 실패 → GEMINI_API_KEY 확인, LLM 프롬프트 점검 |
| `citations: []` | `citations: [...]` 포함 | KB 미적재 → `ingest()` 재실행, DB 청크 수 확인 |
| `"source": "management"` | `"source": "clio"` | 과잉 분류 → intent 분류 프롬프트 조정 |
| `suggested_action` 없음 | `suggested_action` 포함 | management 서브에이전트의 Tier 판단 확인, `approval.py` 임계값 점검 |
| `hit_rate_at_5: 0.6x` | ≥ 0.80 (프로덕션 기준선) | 청크 크기 조정(`_chunk_markdown`) 후 재적재·재측정 |
| `faithfulness: 0.5x` | ≥ 0.70 (RAGAS 프로덕션 최소) | CRAG 재평가 강화 또는 KB 청크 내용 품질 재검토 |

3. **원인 파일을 수정하고 해당 테스트만 다시 실행한다** — 전체 태스크를 처음부터 재실행하지 않는다
4. **3회 시도 후에도 불일치가 계속되면** 멈추고 사용자에게 상황과 실제 응답값을 보고한다

### 예상치 못한 상황 처리

- **기존 코드가 설계와 다른 경우**: 설계 문서가 아닌 **실제 코드를 기준**으로 판단한다. 불일치가 있으면 실제 코드에 맞게 계획을 조정하고 진행한다.
- **테스트가 이미 실패 상태인 경우**: 내 변경과 무관한 기존 실패는 건드리지 않는다. 내 변경으로 새로 생긴 실패만 수정한다.
- **막히는 경우**: 같은 오류를 3회 이상 반복하면 접근 방식을 바꾼다. 동일한 시도를 반복하지 않는다.

### 사용량·시간 제한으로 중단된 경우 자동 재개

루프가 컨텍스트 한도·API 사용량 제한·세션 타임아웃으로 중단되면 아래 절차를 따른다.

**중단 직전 (한도 도달 감지 시)**

1. 현재 진행 중이던 Step을 완료 가능하면 완료하고 커밋한다
2. 커밋 메시지에 중단 지점을 명시한다: `add: deep agent Task 3 Step 2까지 완료 — 한도로 중단`
3. `ScheduleWakeup`을 호출해 제한이 풀릴 시간(통상 5~10분 후)에 자동 재개를 예약한다

```
ScheduleWakeup(
  delaySeconds=600,   # 10분 후 재개 (API 사용량 리셋 주기 감안)
  prompt="/loop docs/management/2026-06-27-deep-agent-오케스트레이터-구현.md",
  reason="API 사용량 한도로 중단 — Task N Step M에서 재개 예정"
)
```

**재개 시 — 진행 상황 파악 후 이어서 실행**

중단 후 재개되면 **Task 1부터 다시 시작하지 않는다**. 아래 순서로 어디까지 됐는지 확인한 후 첫 번째 미완성 태스크부터 이어간다.

```bash
# 1. 최근 커밋 확인 — 어느 태스크까지 완료됐는지
git log --oneline -10

# 2. 신규 파일 존재 여부 확인
ls backend/api/assistant/deep_agent.py 2>/dev/null && echo "Task3 완료" || echo "Task3 미완"
ls backend/domain/management/assistant/rag_eval.py 2>/dev/null && echo "Task2 완료" || echo "Task2 미완"

# 3. RAG 평가 결과 확인 (Task 2 완료 여부)
cd backend && uv run python -c "
import asyncio
from core.db import AsyncSessionLocal
from sqlalchemy import select, func
from core.models import ManagementKbEvalCase
async def check():
    async with AsyncSessionLocal() as db:
        n = (await db.execute(select(func.count()).select_from(ManagementKbEvalCase))).scalar()
        print(f'QA쌍 수: {n}')
asyncio.run(check())
"
```

확인 결과에 따라:
- 커밋에 "Task N 완료"가 있으면 → Task N+1부터 시작
- `deep_agent.py` 없으면 → Task 3부터
- `rag_eval.py` 없으면 → Task 2부터
- QA쌍 0건이면 → Task 2 Step 1부터
- 모든 파일 있고 커밋도 있으면 → `pytest` 돌려서 실패하는 테스트부터

**재개 후 첫 번째 액션**: 위 확인 결과를 한 줄로 요약하고 바로 해당 태스크를 진행한다. 사용자 확인 대기 없이 자율 진행한다.

---

### 완료 후 작업 요약 문서 작성

**모든 루프(Task 1~7)가 끝나면** 아래 경로에 작업 요약 MD를 작성한다.

```
c:\dev\click-me\docs\management\2026-06-27-deep-agent-구현-완료-보고.md
```

포함 내용:
- 태스크별 실제 변경 파일 목록 및 변경 내용 요약
- 새로 생성한 파일 목록
- 최종 테스트 결과 (Hit Rate@5, pytest 통과 수, 빌드 결과)
- 설계 대비 실제 구현에서 달라진 부분과 이유
- 발견한 기존 코드 이슈 및 처리 내역
- 다음 작업에서 이어받아야 할 미완성 항목 (있는 경우)

---

## 코드 사전 확인 규칙 (매 태스크·매 단계 공통 의무)

> **이 규칙은 모든 태스크의 모든 Step보다 우선한다. 코드를 한 줄이라도 수정하기 전에 반드시 수행한다.**

### 태스크 진입 시 — 전체 관련 코드 읽기

새 태스크를 시작하기 전에 아래를 순서대로 수행한다.

1. **변경 대상 파일 전체 읽기** — `Read` 도구로 해당 파일을 처음부터 끝까지 읽는다. 라인 수가 많으면 `offset`/`limit`으로 나눠 읽되 전부 확인한다.
2. **의존 파일 확인** — 변경 파일이 import하는 모듈, 변경 파일을 import하는 상위 파일을 `Grep`으로 찾아 읽는다.
3. **프론트엔드 연동 확인** — 백엔드 엔드포인트를 변경하면 `frontend/src`에서 해당 경로를 호출하는 파일을 `Grep`으로 찾아 타입·응답 구조 불일치 여부를 확인한다.
4. **DB 모델 확인** — 새 테이블/컬럼을 쓰면 `core/models.py`와 `docs/db-schema.md`를 읽어 이미 존재하는지 확인한다. 없으면 Alembic 마이그레이션이 필요하므로 사전에 공지한다.
5. **기존 테스트 확인** — `backend/tests/` 에서 관련 테스트 파일을 `Glob`·`Grep`으로 찾아 기존 테스트가 깨지지 않는지 확인한다.

### 단계(Step) 실행 중 — 즉시 검증

각 Step을 완료할 때마다 다음을 수행한다. 오류가 나면 다음 Step으로 넘어가지 않고 그 자리에서 수정한다.

- **Python 수정 후**: `cd backend && uv run ruff check <수정파일> --fix && uv run ruff format <수정파일>`
- **TypeScript 수정 후**: `cd frontend && pnpm tsc --noEmit` (타입 오류 0건 확인)
- **import 추가 후**: `cd backend && uv run python -c "import <모듈경로>"` (import 오류 없는지)
- **함수·클래스 추가 후**: 해당 함수만 단독 실행 또는 단위 테스트로 동작 확인
- **엔드포인트 추가 후**: 서버 재기동 → `curl` 또는 `http://localhost:8000/docs` 에서 라우터 등록 확인

### 로직 최적화 원칙

> **모든 로직은 최적화한다.** 단순히 동작하는 코드가 아니라, 빠르고 안전하고 간결한 코드를 작성한다.

구현 중 아래 기준을 항상 적용한다. 기존 코드를 읽을 때도 개선 가능한 부분이 보이면 함께 수정한다.

**1. 병렬화 가능한 I/O는 반드시 병렬 실행**
- `asyncio.gather()`로 묶을 수 있는 독립적인 async 호출은 순차 실행하지 않는다
- 예: `ask_management` + `ask_generator`가 동시에 필요하면 `gather()` 사용
- 예: KB 검색과 live 데이터 조회가 독립적이면 병렬로

**2. 불필요한 LLM 호출 제거**
- 이미 알고 있는 정보(state에 저장된 결과)를 다시 LLM에게 물어보지 않는다
- `MAX_ITER` 도달 전에 충분한 근거가 모였으면 즉시 종료 (불필요한 루프 금지)
- 의도 분류 결과를 캐시해 같은 질문에 재분류 호출하지 않는다

**3. DB 쿼리 최소화**
- N+1 쿼리 패턴 금지 — 루프 안에서 개별 DB 호출 대신 한 번에 조회
- 동일 세션 내 반복 조회는 세션 state에 캐시

**4. 중복 코드 제거**
- 3줄 이상 반복되는 패턴은 함수로 추출
- 기존 유틸리티(`retriever.py`, `tools.py` 등)를 재사용하고 새로 만들지 않는다

**5. 응답 크기 최소화**
- SSE meta에 프론트가 실제로 사용하는 필드만 포함 (불필요한 debug 데이터 제외)
- KB 인용은 중복 제거 후 전달 (`retriever._dedup` 패턴 준수)

**6. 오류 처리 경량화**
- `except Exception: pass` 패턴 금지 — 오류를 삼키면 디버깅이 불가능
- 치명적이지 않은 오류(기억 회수 실패, 웹검색 실패 등)는 `best-effort` 패턴으로 로그만 남기고 진행
- 치명적인 오류(DB 연결 실패, 핵심 의존성 오류)는 명확한 에러 메시지와 함께 상위로 전파

### 수정 금지 원칙

아래 파일·패턴은 이 루프에서 **절대 수정하지 않는다**. 관련 변경이 필요하면 루프를 멈추고 사람에게 알린다.

- `core/models.py` — ORM 모델 (Alembic 마이그레이션 필요, 단독 PR)
- `domain/management/execution/executor.py` — 실행 엔진 (멱등·감사 로직)
- `domain/management/approval.py` — 승인 정책 단일원천
- `domain/management/contracts/` — 공용 스키마·enum
- `api/main.py`의 `include_router` 순서 — append-only, 순서 변경 금지

---

## 전체 아키텍처 맥락

```
채팅 공통 오케스트레이터 (Deep Agent)
    ├── 매니지먼트 서브에이전트   ← 이 루프의 담당 범위
    ├── 제너레이터 서브에이전트   ← 별도 담당자가 독립 구현
    └── 시뮬레이터 서브에이전트   ← 별도 담당자가 독립 구현
```

- **공통 오케스트레이터**: LangGraph 기반 Deep Agent. 사용자 질문을 받아 의도를 파악하고 적절한 서브에이전트를 호출·조합해 최종 답변을 만든다. 각 서브에이전트에 상태를 직접 들고 다니지 않고 필요한 컨텍스트만 넘긴다.
- **서브에이전트 3종**: 제너레이터·시뮬레이터·매니지먼트는 각각 **독립적으로 구현**되어 오케스트레이터에 도구(tool)로 붙는다. 서브에이전트끼리는 직접 의존하지 않는다.

### 서브에이전트 간 의존성 금지 원칙

> **서브에이전트는 서로를 모른다.** 매니지먼트가 제너레이터를 import하거나 직접 호출하는 코드는 절대 작성하지 않는다.

**허용되는 통신 경로:**
```
서브에이전트 A → 오케스트레이터 → 서브에이전트 B
```

**금지되는 통신 경로:**
```
서브에이전트 A → 서브에이전트 B  (직접 호출 금지)
```

**구체적 금지 사항:**
- `domain/management/` 안에서 `domain/generator/` 또는 `domain/simulation/`을 import 금지
- `domain/generator/` 안에서 `domain/management/` import 금지
- 서브에이전트가 다른 서브에이전트의 결과를 직접 받아 처리하는 코드 금지
- 서브에이전트가 오케스트레이터의 `_OState`를 직접 참조하는 코드 금지

**정보 전달이 필요한 경우:**
- 매니지먼트 결과를 제너레이터에 넘겨야 할 때 → 오케스트레이터가 `sub_results["management"]`를 꺼내 `ask_generator(management_context=...)` 인자로 전달
- 서브에이전트는 자신이 받은 인자만 알고, 그것이 어디서 왔는지 모른다

**검증 방법 (태스크 완료 시마다 실행):**
```bash
# 매니지먼트가 다른 도메인을 import하는지 확인
cd backend && grep -rn "from domain.generator\|from domain.simulation\|import domain.generator\|import domain.simulation" domain/management/
# 결과: 0건이어야 함

# 제너레이터가 매니지먼트를 import하는지 확인
cd backend && grep -rn "from domain.management\|import domain.management" domain/generator/
# 결과: 0건이어야 함
```
- **이 루프의 담당 범위**: **채팅 전체 연결 총괄** — 공통 오케스트레이터 Deep Agent 구현 + 매니지먼트·제너레이터·시뮬레이터 서브에이전트를 오케스트레이터에 붙이는 작업 전부. 각 서브에이전트의 내부 구현은 각 담당자가 독립적으로 완성하고, **오케스트레이터 연결(인터페이스 통일·SSE 흐름·HITL 전달)은 이 루프 담당자가 총괄한다.**
- **담당자**: 채팅 오케스트레이션 총괄 + 매니지먼트 서브에이전트 소유 (감지·진단·승인·reader.py). 제너레이터·시뮬레이터 서브에이전트 내부는 각 담당자에게 인터페이스 계약(`SubagentRequest` / `SubagentResult`)만 전달하고 내부 구현은 위임한다.

---

## 멘토링 피드백 반영 사항

> 아래는 멘토링에서 받은 피드백을 구조화한 것이다. 각 태스크 구현 시 이 내용을 기준으로 삼는다.

### 1. LangGraph 자유도 — 러프하게 유지

- 워크플로우를 정교하게 짤수록 예상 못한 유즈케이스에서 동작하지 않는다
- 오케스트레이터는 노드를 최소화하고 LLM이 스스로 판단하도록 자유도를 높게 유지
- **딥에이전트(act-first + 동적 루프)** 패턴으로 구현 → 현재 설계 방향 유지 ✅

### 2. 데이터 소스 분리 원칙

| 데이터 유형 | 도구 |
|-------------|------|
| 사내 데이터, 잘 변하지 않는 정책·플레이북 | RAG (pgvector) |
| 빠르게 변하는 트렌드·최신 정보 | Tavily 웹검색 |

→ Tavily 이미 연동됨 ✅. KB 문서가 오래됐을 때 web_search로 보강하는 현재 로직 유지.

### 3. RAG 평가 먼저 — LLM as Judge 이전에 선행 필수

**순서**: RAG 정확도 개선 → LLM as Judge (에이전트 응답 평가) 순서로 진행.  
LLM as Judge(faithfulness)는 최종 발표 자료의 정량 지표로 사용.

**RAG 평가 방법**:
- 청크 데이터를 기반으로 질문 데이터 생성 (오래 걸림 → 1회 생성 후 DB 저장)
- 생성한 질문으로 쿼리 → 해당 청크가 결과에 포함되는지로 평가

**평가 지표 2종**:
- **Hit Rate@k** (k=5): top-k 결과 중 정답 청크가 하나라도 있으면 정답. 전체 평균
- **MRR (Mean Reciprocal Rank)**: 정답이 1위=1.0, 2위=0.5, k위=1/k. 상위에 있을수록 점수가 높음. 검색 품질의 순위 정확도를 측정

**CRAG 비용 고려**:
- CRAG(자기교정 검색)는 LLM 재평가 호출이 추가되므로 비용·실행 시간이 올라감
- 현재 `search_kb` 내부에 CRAG-lite 구현 중 → RAG 평가로 Hit Rate가 충분히 높으면 CRAG 비용 줄이는 방향 검토

### 4. 키워드 의도분류 사용 금지 (크리티컬)

> **"키워드 방식은 의미 분석을 전혀 못하기 때문에 의도분류에 절대 사용하면 안 된다."**

현재 `intent.py`에 `_keyword_classify()` 폴백이 있고 `chat.py`의 `_is_management()`도 키워드 기반이다. **이를 LLM 시맨틱 분류로 대체해야 한다.**

- LLM API 키가 없는 경우: 키워드 폴백 대신 `Intent.ADVISE`로 기본값 처리 (CLIO 폴백)
- "프리퀀시 높으면 어떻게 해야 해?"처럼 키워드에 없는 질문도 manage로 분류되어야 함
- 이 작업은 **Task 4 (chat.py 수정)** 에 포함

### 5. HITL — 멘토 확인 완료, 개선 검토

> **"크리티컬한 결정에 human in the loop 구현은 아주 좋음"** — 멘토 확인.

현재 구현(Tier 기반 interrupt → `/chat/approve` 경로)은 유지. 추가 개선 가능성:
- 승인 대기 상태를 프론트에서 더 명확하게 표시 (현재는 SSE meta의 `requires_approval` 플래그만)
- 승인 만료(TTL) 시 사용자에게 알림
- 승인 없이 자동 처리 가능한 Tier 0 액션의 범위 검토

---

## 루프 목적

1. `api/assistant/` 오케스트레이터를 **단일 패스 → Deep Agent(LangGraph 루프)** 로 재설계
2. 매니지먼트 서브에이전트를 오케스트레이터에 **정식 연결** (현재 chat.py가 직접 호출하는 구조 수정)
3. KB 인제스터 startup 자동 연결 및 RAG 평가 시스템 구축
4. HITL(사람 승인) thread_id가 오케스트레이터를 통해 프론트까지 흐르는지 검증

---

## 루프 종료 조건

아래 조건을 **모두** 만족하면 루프를 종료한다.

- [ ] `uv run pytest tests/ -v` — 백엔드 전체 테스트 통과 (실패 0건)
- [ ] `pnpm build` — 프론트엔드 빌드 오류 없음
- [ ] 백엔드 서버 `uvicorn api.main:app --reload` 기동 시 오류 없음
- [ ] `POST /api/chat/complete` — 매니지먼트 질문에 실측+KB 인용 포함 응답 반환
- [ ] `POST /api/chat/complete` — "새 광고 만들어줘" 시 generator 슬롯필링 작동
- [ ] `POST /api/chat/approve` — HITL thread_id 수신 후 실행 성공

---

## 환경 설정 확인 (태스크 시작 전)

각 태스크 실행 전에 다음을 확인한다. `.env`나 NeonDB 설정이 빠져 있으면 해당 항목을 먼저 보완한다.

```bash
# backend/.env 필수 항목
OPENAI_API_KEY=...          # KB 인제스터 + 매니지먼트 어시스턴트 LLM
GEMINI_API_KEY=...          # 오케스트레이터 분류기 + CLIO 폴백
TAVILY_API_KEY=...          # 웹검색 (없어도 빈 결과로 graceful 동작)
DATABASE_URL=...            # NeonDB postgresql+asyncpg://...

# 확인 명령어
cd backend && uv run python -c "from core.config import settings; print(settings.openai_api_key[:8])"
```

---

## Task 1: KB 인제스터 Startup 자동 연결

**목적**: `kb_ingest.py`는 완성됐지만 앱 기동 시 자동 실행되지 않음. `search_kb` 도구가 DB에서 빈 결과를 반환하는 원인.

### 변경 파일

- 수정: `backend/api/main.py` — lifespan에 `ingest()` 비차단 태스크 추가

### 사전 코드 확인 (구현 전 필수)

- [ ] `backend/api/main.py` 전체 읽기 — lifespan/startup 구조, 기존 import, asyncio 사용 여부 확인
- [ ] `backend/domain/management/assistant/kb_ingest.py` 전체 읽기 — `ingest()` 함수 시그니처·반환값 확인
- [ ] `backend/core/config.py` 읽기 — `settings.openai_api_key` 필드명 확인

### 구현 단계

- [ ] **Step 1**: `api/main.py`의 lifespan(또는 startup 이벤트)에 다음을 추가한다

```python
# OPENAI_API_KEY 있을 때만 — 없으면 KB 미적재 (search_kb는 빈 결과, 채팅은 graceful 동작)
if getattr(settings, "openai_api_key", None):
    try:
        from domain.management.assistant.kb_ingest import ingest  # noqa: PLC0415
        asyncio.create_task(ingest())  # 비차단: 서버 시작 안 막음
    except Exception as e:
        print(f"[startup] KB ingest 스킵: {e}")
```

- [ ] **Step 2**: 서버 기동 후 콘솔에 `적재 완료: N chunks` 로그 확인

### 테스트 — 오류 없을 때까지 반복

```bash
# 백엔드: 수동 적재 후 청크 수 확인
cd backend && uv run python -m domain.management.assistant.kb_ingest
# 기대: "적재 완료: N chunks (변경 없음 skip: M)"

# 백엔드: KB 검색 동작 확인
cd backend && uv run python -c "
import asyncio
from domain.management.assistant.retriever import KbRetriever
async def test():
    r = KbRetriever()
    hits = await r.keyword_search('CTR 최적화')
    print(f'hits: {len(hits)}, first: {hits[0][\"title\"] if hits else None}')
asyncio.run(test())
"
# 기대: hits >= 1

# 백엔드 전체 테스트
cd backend && uv run pytest tests/ -v
```

**이 태스크의 모든 테스트가 오류 없이 통과되면 Task 2로 진행한다.**

---

## Task 2: RAG 평가 시스템 구축

**목적**: KB 검색 품질(Hit Rate@k, MRR)을 숫자로 측정한다. 목표치(Hit Rate@5 ≥ 0.80) 미달 시 청크 크기·RRF 파라미터를 조정한다.

### 변경 파일

- 신규: `backend/domain/management/assistant/rag_eval.py`
- 수정: `backend/api/routers/management.py` — `/kb/eval/generate`, `/kb/eval/run` 엔드포인트 추가

### 사전 코드 확인 (구현 전 필수)

- [ ] `backend/core/models.py` 에서 `ManagementKbEvalCase` 모델 필드 전체 확인
- [ ] `backend/domain/management/assistant/retriever.py` 전체 읽기 — `KbRetriever.search()` 반환 구조(id 필드 이름 등) 확인
- [ ] `backend/api/routers/management.py` 에서 `/kb/` 관련 기존 엔드포인트 확인 (중복 방지)
- [ ] `backend/tests/management/` 에서 retriever 관련 기존 테스트 확인

### 구현 단계

- [ ] **Step 1**: `rag_eval.py` 신규 작성 — QA쌍 자동 생성 함수

QA쌍 생성 시 아래 프롬프트를 그대로 사용한다. 청크 제목 노출 없이 실제 마케터 질문 스타일로 생성되도록 조건을 명시한다.

```python
_QA_PROMPT = """\
아래는 Meta 광고 운영 지식베이스의 한 청크입니다.
마케팅 매니저가 실제로 물어볼 법한 질문 1개를 한국어로 생성하세요.
- 이 청크의 내용만으로 답할 수 있어야 합니다.
- 청크 제목이나 문서 이름을 질문에 직접 언급하지 마세요.
- "~는 무엇인가요?" 보다 "~하면 어떻게 해야 하나요?" 형태를 선호합니다.

[청크]
{chunk}

질문:"""

async def generate_qa_pairs(llm, limit: int = 50) -> int:
    """DB의 ManagementKbChunk를 순회하며 QA쌍 생성 후 ManagementKbEvalCase에 저장."""
    # 이미 QA쌍이 있는 chunk_id는 건너뜀 (멱등)
    # llm.ainvoke(_QA_PROMPT.format(chunk=chunk.chunk)) → 질문 텍스트
    # ManagementKbEvalCase(question=q, ground_truth_chunk_id=chunk.id) 저장
    ...
```

- [ ] **Step 2**: `rag_eval.py`에 Hit Rate@k + MRR 측정 함수 작성

```python
def hit_rate(retrieved_ids_per_q: list[list[str]], gt_ids: list[str], k: int) -> float:
    """k개 결과 중 정답 청크 ID가 하나라도 포함되면 1, 없으면 0. 전체 평균."""
    ...

def mrr(retrieved_ids_per_q: list[list[str]], gt_ids: list[str]) -> float:
    """정답이 1위=1.0, 2위=0.5, k위=1/k. 평균 역순위."""
    ...

async def evaluate(k: int = 5) -> dict:
    """저장된 QA쌍으로 Hit Rate@k + MRR 계산. 결과 dict 반환."""
    ...
```

- [ ] **Step 3**: `management.py`에 엔드포인트 추가

```python
POST /kb/eval/generate   # QA쌍 생성 (1회 실행, 오래 걸림)
GET  /kb/eval/run?k=5    # 현재 점수 출력
```

- [ ] **Step 3-1**: Context Precision 측정 추가

Hit Rate는 "정답 청크가 있냐"만 보지만, Context Precision은 "가져온 k개 중 쓸모없는 청크가 얼마나 있냐"를 본다. 두 지표를 함께 보면 노이즈 문제를 잡을 수 있다.

```python
def context_precision(retrieved_ids_per_q: list[list[str]], gt_ids: list[str]) -> float:
    """retrieved k개 중 정답 청크가 상위에 몰려 있을수록 높음. Average Precision과 동일."""
    # RAGAS Context Precision 공식: avg precision over binary useful verdicts per chunk
    ...
```

반환값에 포함: `{"hit_rate_at_5": 0.82, "mrr": 0.71, "context_precision": 0.78, "n_cases": N}`

- [ ] **Step 3-2**: 개선 전후 스냅샷 저장

튜닝을 반복하면서 어떤 변경이 수치를 얼마나 올렸는지 추적한다. 발표 자료의 "개선 근거"가 된다.

```python
# evaluate() 결과를 매번 DB에 저장 (timestamp + 실험 설명)
# ManagementKbEvalRun(run_at, hit_rate, mrr, context_precision, note="청크 300→150 변경")
```

기록 형식 예시:

| 실험 | 청크 크기 | RRF_K | Hit Rate@5 | MRR | Context Precision | 비고 |
|---|---|---|---|---|---|---|
| 베이스라인 | 기본 | 60 | 측정 전 | 측정 전 | 측정 전 | Task 2 최초 실행 |
| Run 1 | 300 | 60 | ? | ? | ? | - |
| Run 2 | 150 | 60 | ? | ? | ? | 청크 축소 |
| Run 3 | 150 | 30 | ? | ? | ? | RRF_K 조정 |

### 테스트 — 오류 없을 때까지 반복

```bash
# QA쌍 생성 (백엔드 서버 기동 상태에서)
curl -X POST http://localhost:8000/api/management/kb/eval/generate

# 평가 실행
curl "http://localhost:8000/api/management/kb/eval/run?k=5"
# 기대 응답: {"hit_rate_at_5": 0.82, "mrr": 0.71, "n_cases": N}

# CLI 직접 실행도 가능
cd backend && uv run python -m domain.management.assistant.rag_eval --k 5

# 백엔드 전체 테스트
cd backend && uv run pytest tests/ -v
```

**튜닝 기준 및 수치 근거**:

| 지표 | 목표값 | 근거 출처 |
|---|---|---|
| Hit Rate@5 | ≥ 0.80 | ① Dextralabs 2025: "프로덕션 일반 유스케이스 기준 0.80 이상" ② getmaxim.ai: "도메인 특화 Precision@5 최소 0.70, 광범위 Recall@20 최소 0.80" ③ LlamaIndex 실측(OpenAI Embedding): Hit Rate 75.86% → 0.80은 그 위 한 단계 목표 ④ FAQ 챗봇 기준선: k=10에서 90% → k=5·도메인 특화는 0.80이 합리적 중간값 |
| MRR | ≥ 0.60 | ① LlamaIndex 실측(OpenAI Embedding): MRR 0.6206 — 실제 시스템 기준선 확인 ② Zilliz/Milvus: "정답이 상위에 위치할수록 MRR 증가 — 프로덕션에서 합리적으로 높은 값 목표" ③ MRR 0.60 = 정답이 평균 1.67위 이내. 공개 단일 임계값 없음 → LlamaIndex 실측 기준선으로 설정 |
| Faithfulness | ≥ 0.70 (프로덕션 최소) / ≥ 0.85 (발표용) | ① RAGAS 프로덕션 프레임워크(DEV Community): "faithfulness < 0.70 → 사람 검토 에스컬레이션" ② FaithJudge 논문(EMNLP 2025, arXiv:2505.04847): 최고 LLM 판사(o3-mini-high) 인간 동의율 84%, F1-macro 82.1% → 0.85가 발표용 상한 ③ MTRAG(IBM, TACL 2025, arXiv:2501.03468): 멀티턴 RAG에서 RAGAS Faithfulness가 인간 점수와 높은 상관 확인 |

- Hit Rate@5 < 0.80 → 청크 크기(`kb_ingest.py`의 `_chunk_markdown`) 조정 후 재적재·재측정
- MRR < 0.60 → `retriever.py`의 `_RRF_K` 값 조정 (현재 60, 낮출수록 상위 결과에 가중치 증가)
- Hit Rate가 충분히 높으면 `search_kb` 내 CRAG 재평가 호출 횟수 줄이는 방향 검토 (비용·속도 절감)
- LLM as Judge(faithfulness) 평가는 RAG Hit Rate ≥ 0.80 달성 **이후**에 진행

**이 태스크의 모든 테스트가 오류 없이 통과되면 Task 3으로 진행한다.**

---

## Task 3: Deep Agent 오케스트레이터 신규 구현

**목적**: 현재 `orchestrator.py`는 단일 패스 디스패처. LangGraph 루프 기반 Deep Agent로 교체한다.

### 변경 파일

- 신규: `backend/api/assistant/deep_agent.py` — Deep Agent LangGraph 그래프

### 사전 코드 확인 (구현 전 필수)

- [ ] `backend/api/assistant/orchestrator.py` 전체 읽기 — 현재 `run_turn()` 구조, `SubagentRequest`/`SubagentResult` 계약 확인
- [ ] `backend/api/assistant/contracts.py` 전체 읽기 — `Intent`, `SubagentRequest`, `SubagentResult`, `Action` 필드 전부 확인
- [ ] `backend/api/assistant/registry.py` 전체 읽기 — `Handler` 타입, 등록 방식 확인
- [ ] `backend/domain/management/assistant/graph.py` 전체 읽기 — `_State`, 노드 구조, `to_result()` 반환 타입 확인
- [ ] `backend/domain/management/assistant/contracts.py` 전체 읽기 — `AskRequest`, `AskResult` 필드 확인
- [ ] `backend/domain/generator/chat/` 디렉토리 읽기 — `SubagentResult` 반환 구조, `Action.ASK`/`TRIGGER` 처리 방식 확인
- [ ] `backend/api/assistant/wiring.py` 전체 읽기 — 기존 `build_assistant()` 패턴 확인 (새 함수가 일관된 패턴으로 작성되도록)
- [ ] LangGraph 버전 확인: `cd backend && uv run python -c "import langgraph; print(langgraph.__version__)"` — `StateGraph`, `add_messages`, `TypedDict` 임포트 경로 확인

### 구현 단계

- [ ] **Step 1**: `deep_agent.py` 신규 작성 — 3노드 LangGraph

```python
# 오케스트레이터 State
class _OState(TypedDict):
    messages: Annotated[list, add_messages]
    sub_results: dict          # {"management": {...}, "generator": {...}}
    iteration: int             # 루프 상한 MAX_ITER=3
    thread_id: str | None      # management HITL thread_id
    requires_approval: bool    # HITL 상태

# 노드 구조 (러프하게 — 3노드만)
# START → orchestrate → [route] → dispatch → orchestrate → END
```

- [ ] **Step 2**: `orchestrate` 노드 — act-first 규칙 구현

```python
async def orchestrate(state: _OState) -> dict:
    # act-first: 첫 iteration + (campaign_id 있거나 매니지먼트 키워드) → ask_management 즉시 호출
    # MAX_ITER 도달 → 도구 바인딩 해제, 최종 답만 생성
    # requires_approval=True → 도구 호출 없이 "승인 필요" 최종 답 생성
    ...
```

- [ ] **Step 3**: `dispatch` 노드 — 서브에이전트 호출 + 결과 처리

```python
async def dispatch(state: _OState) -> dict:
    # ask_management → AskResult 수신, thread_id/requires_approval 추출
    # ask_generator:
    #   action==ASK → 즉시 END 신호 (되묻기는 루프 없이 바로 전달)
    #   action==TRIGGER → 즉시 END 신호
    #   action==ANSWER → sub_results 저장 후 orchestrate 복귀
    ...
```

- [ ] **Step 4**: 서브에이전트 도구 정의

```python
@tool
async def ask_management(query: str, campaign_id: str | None = None) -> dict:
    """캠페인 현황·성과·예산·이상·KPI 관련 질문. 실측 데이터와 KB 정책 근거를 제공한다."""
    ...

@tool
async def ask_generator(query: str, management_context: str | None = None) -> dict:
    """광고 시안·카피 생성 요청. management_context로 성과 기반 개선 컨텍스트를 전달한다."""
    ...
```

- [ ] **Step 5**: `build_deep_agent_graph(llm, management_ask, generator_handler)` 팩토리 함수 작성

- [ ] **Step 5-1**: 제너레이터·시뮬레이터 mock 핸들러 작성

다른 담당자의 서브에이전트가 아직 `SubagentResult` 인터페이스를 맞춰 완성하지 않은 경우, mock 핸들러로 대체해 오케스트레이터 흐름 전체를 검증한다. mock은 `wiring.py` 안에 인라인으로 작성하고, 실 구현이 들어오면 한 줄 교체로 끝난다.

```python
# wiring.py — mock 핸들러 (실 구현 전까지만 사용)
async def _mock_generator(req: SubagentRequest) -> SubagentResult:
    return SubagentResult(
        intent=Intent.GENERATE,
        action=Action.ANSWER,
        text=f"[MOCK] 광고 시안 생성 완료 (query={req.query[:30]}...)",
        citations=[],
    )

async def _mock_simulator(req: SubagentRequest) -> SubagentResult:
    return SubagentResult(
        intent=Intent.SIMULATE,
        action=Action.ANSWER,
        text=f"[MOCK] 시뮬레이션 결과 반환 (query={req.query[:30]}...)",
        citations=[],
    )
```

mock 제거 기준: 해당 담당자가 `SubagentResult`를 반환하는 실 핸들러를 `wiring.py`에 등록하면 `_mock_*` 함수를 삭제하고 실 핸들러로 교체한다. **mock이 남은 채 커밋하지 않는다** — Task 6 QA에서 `grep -rn "_mock_"` 으로 잔존 여부 확인.

- [ ] **Step 6**: LangSmith 트레이싱 태그 추가

LangGraph 그래프 컴파일 시 `run_name`과 `tags`를 설정한다. `LANGCHAIN_TRACING_V2=true` 환경변수가 있을 때 자동 활성화된다.

```python
graph = builder.compile(checkpointer=MemorySaver())

# ainvoke 시 config로 트레이싱 메타 전달
config = {
    "run_name": "deep-agent-turn",
    "tags": ["deep-agent", "orchestrator", "management"],
    "metadata": {"session_id": session_id, "iteration_budget": MAX_ITER},
}
state = await graph.ainvoke(initial_state, config=config)
```

LangSmith에서 "deep-agent" 태그로 필터링하면 오케스트레이터 루프의 전체 트레이스를 볼 수 있다.

### 테스트 — 오류 없을 때까지 반복

```bash
# deep_agent.py import 오류 없는지 확인
cd backend && uv run python -c "from api.assistant.deep_agent import build_deep_agent_graph; print('OK')"

# 단위 테스트 (management mock으로 그래프 동작 확인)
cd backend && uv run pytest tests/ -k "deep_agent" -v

# 백엔드 전체 테스트
cd backend && uv run pytest tests/ -v
```

**이 태스크의 모든 테스트가 오류 없이 통과되면 Task 4로 진행한다.**

---

## Task 4: Wiring 수정 및 chat.py 오케스트레이터 일원화

**목적**: `api/assistant/wiring.py`에 `build_deep_agent()` 추가. `chat.py`가 management를 직접 호출하는 구조를 오케스트레이터 경유로 변경.

### 변경 파일

- 수정: `backend/api/assistant/wiring.py` — `build_deep_agent()` 추가
- 수정: `backend/api/routers/chat.py` — 오케스트레이터 일원화, ADVISE 폴백(Gemini) 유지

### 사전 코드 확인 (구현 전 필수)

- [ ] `backend/api/routers/chat.py` **전체 읽기** — `_get_assistant()`, `_is_management()`, SSE 스트리밍 구조, `record_turn()`, `_get_memory()` 호출 위치 모두 파악
- [ ] `backend/api/assistant/wiring.py` 전체 읽기 — 기존 `build_assistant()`, `_build_management_handler()` 패턴 확인
- [ ] `backend/domain/management/assistant/history.py` 읽기 — `record_turn()` 시그니처 확인 (SSE 응답 후 호출 로직 유지 여부)
- [ ] `backend/domain/management/assistant/memory_store.py` 읽기 — `recall()`/`remember()` 시그니처 확인
- [ ] `frontend/src` 에서 `/api/chat/complete` 를 호출하는 파일 Grep — SSE meta 구조(source, citations, thread_id 등) 의존 여부 확인
- [ ] `frontend/src` 에서 `requires_approval`, `thread_id` 를 읽는 코드 Grep — 필드명 변경 시 프론트 영향 범위 파악

### 구현 단계

- [ ] **Step 1**: `wiring.py`에 `build_deep_agent()` 추가

```python
def build_deep_agent(settings) -> Callable:
    """Deep Agent 오케스트레이터 조립 + 서브에이전트 도구 등록."""
    management_ask = build_management_agent(settings)
    generator_handler = build_generation_chat_agent(settings)
    llm = _build_classifier_llm(settings)  # Gemini Flash
    graph = build_deep_agent_graph(llm, management_ask, generator_handler)

    async def run(req: SubagentRequest) -> SubagentResult | None:
        state = await graph.ainvoke({...})
        return _to_subagent_result(state)  # None이면 ADVISE 폴백
    return run
```

- [ ] **Step 2**: `chat.py` 수정 — 오케스트레이터로 일원화

```python
# 변경 전
is_mgmt = await _is_management(body)
if is_mgmt:
    result = await _get_assistant()(AskRequest(...))
    ...
else:
    # Gemini CLIO

# 변경 후
result = await _get_orchestrator()(SubagentRequest(...))
if result is None:  # ADVISE — 광고와 무관한 일반 질문
    # 기존 Gemini CLIO 경로 (그대로 유지)
    ...
else:
    # 오케스트레이터 결과 SSE 스트리밍
    # meta에 source, citations, requires_approval, thread_id 포함
    ...
```

- [ ] **Step 3**: 기존 `_get_assistant()`, `_is_management()` 제거 (chat.py 정리)

- [ ] **Step 4**: **키워드 의도분류 제거 (멘토링 크리티컬 피드백)**

현재 `intent.py`의 `_keyword_classify()`와 `chat.py`의 `_is_management()`는 키워드 기반이다. 키워드 방식은 의미 분석을 전혀 못하므로 의도분류에 사용하면 안 된다.

```python
# 변경 전 — 금지 패턴
def _keyword_classify(text, registered):
    if any(k in text for k in _MANAGE_KW):  # "프리퀀시 높으면?" 같은 질문 못 잡음
        return Intent.MANAGE

# 변경 후 — LLM 시맨틱 분류만 사용
async def classify_intent(req, registered, llm=None):
    if llm is None:
        return Intent.ADVISE  # 키 없으면 CLIO 폴백 (키워드 분류 금지)
    return await _llm_classify(llm, req, registered)
```

- `_keyword_classify()` 함수는 삭제하거나 테스트 전용으로 격리
- LLM 없는 환경(키 미설정)에서는 `Intent.ADVISE` 기본값으로 CLIO가 처리
- "프리퀀시 높으면 어떻게 해야 해?", "ROAS가 뭐야?" 같은 질문도 LLM이 `manage`로 분류

- [ ] **Step 5**: SSE meta에 `thread_id`, `requires_approval` 포함 확인

### 테스트 — 오류 없을 때까지 반복

```bash
# 백엔드 서버 기동
cd backend && uv run uvicorn api.main:app --reload --port 8000

# 테스트 1: 매니지먼트 질문 (명시적 키워드)
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"현재 캠페인 현황 알려줘"}],"session_id":"test-1"}' \
  --no-buffer
# 기대: data: {"meta": {"source": "management", "citations": [...]}}

# 테스트 2: 매니지먼트 질문 (키워드 없음 — LLM 시맨틱 필수)
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"프리퀀시가 높으면 어떻게 해야 해?"}],"session_id":"test-semantic"}' \
  --no-buffer
# 기대: data: {"meta": {"source": "management", ...}} ← 키워드 방식이면 CLIO로 빠져버림

# 테스트 3: 생성 질문
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"새 광고 만들어줘"}],"session_id":"test-3"}' \
  --no-buffer
# 기대: data: {"meta": {"source": "generator", ...}}

# 테스트 4: 일반 질문 (CLIO 폴백)
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"안녕하세요"}],"session_id":"test-4"}' \
  --no-buffer
# 기대: data: {"meta": {"source": "clio", ...}}

# 키워드 분류 코드 완전 제거 확인
cd backend && grep -rn "_keyword_classify\|_MANAGE_KW\|_GENERATE_KW" api/assistant/intent.py
# 기대: 0건 (또는 테스트 전용으로만 존재)

# 백엔드 전체 테스트
cd backend && uv run pytest tests/ -v

# 프론트엔드 빌드 (타입 에러 없는지)
cd frontend && pnpm build
```

**이 태스크의 모든 테스트가 오류 없이 통과되면 Task 5로 진행한다.**

---

## Task 5: HITL thread_id 전달 종단 검증

**목적**: 매니지먼트 서브에이전트의 `interrupt(requires_approval=True)` 상황에서 thread_id가 오케스트레이터 → chat.py SSE meta → 프론트 `/chat/approve` 경로까지 정확히 흐르는지 확인.

### 변경 파일

- 확인/수정: `backend/api/assistant/deep_agent.py` — requires_approval + thread_id state 전달
- 확인/수정: `backend/api/routers/chat.py` — SSE meta에 thread_id 포함
- 확인: `frontend/src` — approve 버튼에 thread_id 사용 여부

### 사전 코드 확인 (구현 전 필수)

- [ ] `backend/domain/management/assistant/graph.py` 에서 `interrupt()` 호출 위치 확인 — `tools_node` 내 `requires_approval` 조건 재확인
- [ ] `backend/domain/management/assistant/agent.py` 에서 `_ask()` 함수가 `AskResult.requires_approval`·`AskResult.thread_id`를 반환하는 경로 추적
- [ ] `backend/api/routers/chat.py` 의 현재 SSE meta dict에 `thread_id` 키가 있는지 확인
- [ ] `frontend/src` 에서 `thread_id`·`requires_approval` 을 사용하는 컴포넌트 전체 Grep — 승인 버튼, approve API 호출 위치 모두 파악
- [ ] `backend/api/routers/chat.py` 의 `/approve` 엔드포인트 전체 읽기 — `thread_id` 파라미터 수신 및 처리 여부 재확인

### 구현 단계

- [ ] **Step 1**: `dispatch` 노드에서 management result의 `requires_approval=True` 감지 시 `_OState.requires_approval=True`, `_OState.thread_id` 저장 확인

- [ ] **Step 2**: `orchestrate` 노드에서 `requires_approval=True`면 추가 도구 호출 없이 종료 확인

- [ ] **Step 3**: chat.py SSE meta에 `requires_approval: true`, `thread_id: "mgmt-xxx"` 포함 확인

- [ ] **Step 4**: `POST /api/chat/approve`에 thread_id 전달 후 실행 성공 확인

### 테스트 — 오류 없을 때까지 반복

```bash
# HITL 시나리오: 캠페인 일시중지 요청 (Tier 0 — 자동 승인 범위)
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"캠페인 일시중지해줘"}],"session_id":"test-hitl"}' \
  --no-buffer
# 기대: meta에 suggested_action.action_type=PAUSE_CAMPAIGN 포함

# HITL 승인
curl -s -X POST http://localhost:8000/api/chat/approve \
  -H "Content-Type: application/json" \
  -d '{"action_type":"PAUSE_CAMPAIGN","campaign_id":"demo_campaign","approver_id":"test-user"}'
# 기대: {"status": "success" 또는 "mock_success", "execution_mode": ...}

# 백엔드 전체 테스트
cd backend && uv run pytest tests/ -v

# 프론트엔드 빌드
cd frontend && pnpm build

# 프론트 dev 서버 기동 후 채팅 화면에서 매니지먼트 질문 → 실측 데이터 응답 확인
cd frontend && pnpm dev
```

**프론트·백엔드 오류가 없고 위 curl 테스트가 모두 기대값을 반환하면 Task 6으로 진행한다.**

---

## Task 6: 설계 검토 및 품질 보강 (QA 역할)

**목적**: 모든 태스크 구현이 끝난 후, 전체 코드를 다시 읽고 설계에서 누락·부족한 부분을 찾아 보강한다. 이 태스크에서 너는 **최고의 QA 엔지니어**다. 단순히 테스트가 통과하는 것을 넘어, 실제 운영 시 발생할 수 있는 모든 엣지 케이스·누락·불일치를 찾아낸다.

### QA 점검 항목

- [ ] **설계 일관성 검토**: `deep_agent.py`의 State 필드가 `chat.py` SSE meta, 프론트 타입과 완전히 일치하는지 필드명·타입 하나하나 대조
- [ ] **엣지 케이스 탐색**:
  - 매니지먼트 + 생성 의도가 동시에 있는 질문 ("성과 낮은 캠페인 기반으로 새 광고 만들어줘") — 두 서브에이전트 모두 호출되는지
  - management 서브에이전트가 Meta API rate limit 오류 반환 시 오케스트레이터가 graceful 처리하는지
  - KB DB가 비어있을 때(인제스터 미실행) `search_kb`가 빈 리스트를 반환하고 채팅이 끊기지 않는지
  - `MAX_ITER` 도달 시 루프가 강제 종료되고 최종 답이 반환되는지
  - `thread_id`가 None인 상태에서 `/approve` 호출 시 안전하게 처리되는지
- [ ] **누락 기능 탐색**: 현재 `chat.py`에 있던 `record_turn()`, `_get_memory().remember()` 가 오케스트레이터 경유 후에도 정상 호출되는지 확인
- [ ] **프론트 타입 동기화**: 백엔드 SSE meta 구조 변경이 있으면 `frontend/src/lib/api.ts` 또는 관련 타입 파일을 찾아 동기화
- [ ] **Ruff + TypeScript 전체 정검**:

```bash
cd backend && uv run ruff check . --fix && uv run ruff format .
cd frontend && pnpm tsc --noEmit
```

- [ ] **미구현 TODO 탐색**: 새로 작성한 파일에서 `...` (Ellipsis), `# TODO`, `pass`, `raise NotImplementedError` 가 남아있는지 Grep으로 확인

```bash
# 미완성 코드 탐지
cd backend && grep -rn "\.\.\.\|# TODO\|raise NotImplementedError" api/assistant/deep_agent.py domain/management/assistant/rag_eval.py
```

- [ ] **Mock 잔존 확인**: 실 구현이 들어온 서브에이전트의 mock이 남아있으면 제거

```bash
# mock 핸들러 잔존 확인 — 실 구현 교체 전이면 남아있어도 OK, 교체 후엔 0건이어야 함
cd backend && grep -rn "_mock_generator\|_mock_simulator" api/assistant/wiring.py
```

- [ ] **설계 보완**: 위 점검에서 발견한 누락·불일치가 있으면 그 자리에서 수정 후 해당 태스크의 테스트를 재실행한다

### 테스트 — 오류 없을 때까지 반복

```bash
# 백엔드 전체
cd backend && uv run pytest tests/ -v

# 프론트 빌드
cd frontend && pnpm build

# 엔드-투-엔드 시나리오 (복합 의도)
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"성과 낮은 캠페인 기반으로 새 광고 만들어줘"}],"session_id":"test-e2e"}' \
  --no-buffer
# 기대: management 서브에이전트 먼저 호출(act-first) → 성과 데이터 → generator 호출

# Rate limit 폴백 시나리오 (mock 환경에서)
curl -s -X POST http://localhost:8000/api/chat/complete \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"캠페인 현황"}],"session_id":"test-ratelimit"}' \
  --no-buffer
# 기대: {"error":"rate_limited"} 반환 시에도 채팅 응답은 정상 반환
```

**모든 점검 항목이 통과되면 Task 6 완료 → Task 7로 진행한다.**

---

## Task 7: LLM as Judge — Faithfulness 평가 (발표 정량 지표)

**목적**: 에이전트 응답이 인용한 KB 근거와 얼마나 일치하는지(faithfulness) 측정한다. RAG Hit Rate ≥ 0.80 달성 후에만 진행한다. 결과는 최종 발표 자료의 정량 지표로 사용된다.

> **사전 조건**: `/api/management/kb/eval/run?k=5` 결과에서 `hit_rate_at_5 >= 0.80` 확인 후 이 태스크를 시작한다.

### 변경 파일

- 수정: `backend/domain/management/assistant/rag_eval.py` — `evaluate_faithfulness()` 함수 추가
- 수정: `backend/api/routers/management.py` — `GET /kb/eval/faithfulness` 엔드포인트 추가

### 구현 단계

- [ ] **Step 1**: `rag_eval.py`에 faithfulness 평가 함수 추가

```python
_FAITHFULNESS_PROMPT = """\
[질문]
{question}

[에이전트 응답]
{answer}

[참조 문서 (KB 인용)]
{context}

위 응답이 참조 문서의 내용에 근거하고 있으면 'faithful', 문서에 없는 내용을 단정하거나 hallucination이 있으면 'not_faithful'로 평가하세요.
응답: faithful 또는 not_faithful (한 단어만)"""

async def evaluate_faithfulness(llm, n: int = 30) -> dict:
    """저장된 QA쌍 n개를 에이전트에 질의 → faithfulness 측정.
    반환: {"faithfulness": 0.87, "n_cases": 30, "not_faithful_examples": [...]}
    """
    ...
```

- [ ] **Step 2**: `GET /kb/eval/faithfulness?n=30` 엔드포인트 추가

- [ ] **Step 3**: 결과 해석 기준

> 수치 근거: RAGAS 프로덕션 가이드 — 0.70 미만은 사람 검토 에스컬레이션 기준선. FaithJudge(EMNLP 2025) — 최고 성능 LLM 판사 기준 인간 동의율 84% → 0.85를 발표용 목표 상한으로 설정.

| Faithfulness | 판단 |
|---|---|
| ≥ 0.85 | 발표 자료에 "에이전트 응답 신뢰도 XX%" 그대로 기재 (FaithJudge 논문 기준 최고 등급) |
| 0.70~0.84 | 개선 여지 언급 + not_faithful 사례 원인 분석 후 재측정 |
| < 0.70 | 프로덕션 미달 (RAGAS 기준선) — CRAG 강화 또는 KB 청크 품질 재검토 필요 |

### 테스트 — 오류 없을 때까지 반복

```bash
# faithfulness 평가 실행
curl "http://localhost:8000/api/management/kb/eval/faithfulness?n=30"
# 기대 응답: {"faithfulness": 0.87, "n_cases": 30, "not_faithful_examples": [...]}

# 백엔드 전체 테스트
cd backend && uv run pytest tests/ -v
```

**이 태스크 완료 → 루프 최종 종료 체크리스트로 이동한다.**

---

## 루프 최종 종료 체크리스트

모든 항목이 체크되면 루프를 종료하고 커밋한다.

- [ ] `cd backend && uv run pytest tests/ -v` — 실패 0건
- [ ] `cd frontend && pnpm build` — 빌드 오류 0건
- [ ] `uvicorn api.main:app --reload` 기동 시 오류 없음, KB ingest 로그 출력
- [ ] `/api/chat/complete` — 매니지먼트 질문 → 실측+KB 인용 응답
- [ ] `/api/chat/complete` — 생성 질문 → generator 슬롯필링 응답
- [ ] `/api/chat/complete` — 일반 질문 → CLIO(Gemini) 응답
- [ ] `/api/management/kb/eval/run?k=5` — Hit Rate@5 ≥ 0.80
- [ ] `/api/chat/approve` — HITL thread_id 수신 후 실행 성공
- [ ] `/api/management/kb/eval/faithfulness?n=30` — faithfulness ≥ 0.70

---

## 참고: 관련 파일 경로

| 역할 | 경로 |
|------|------|
| Deep Agent 그래프 (신규) | `backend/api/assistant/deep_agent.py` |
| 오케스트레이터 Wiring | `backend/api/assistant/wiring.py` |
| 채팅 라우터 | `backend/api/routers/chat.py` |
| 매니지먼트 ReAct 그래프 | `backend/domain/management/assistant/graph.py` |
| KB 인제스터 | `backend/domain/management/assistant/kb_ingest.py` |
| RAG 평가기 (신규) | `backend/domain/management/assistant/rag_eval.py` |
| 앱 진입점(lifespan) | `backend/api/main.py` |
| 승인 정책 단일원천 | `backend/domain/management/approval.py` |
| 실행 엔진 | `backend/domain/management/execution/executor.py` |

---

## 평가 지표 목표 기준표

> 발표 자료 작성 시 이 표의 수치를 기준으로 Before/After를 기재한다.

| 지표 | 최소 (프로덕션) | 목표 (발표용) | 측정 위치 |
|---|---|---|---|
| Hit Rate@5 | 0.70 | **≥ 0.80** | `GET /kb/eval/run?k=5` |
| MRR | 0.55 | **≥ 0.60** | `GET /kb/eval/run?k=5` |
| Context Precision | 0.65 | **≥ 0.75** | `GET /kb/eval/run?k=5` |
| Faithfulness | 0.70 | **≥ 0.85** | `GET /kb/eval/faithfulness?n=30` |

개선 흐름 예시 (발표 슬라이드 포맷):

```
베이스라인 → 청크 크기 조정 → RRF_K 조정 → 최종
Hit Rate@5:        0.68  →     0.75       →    0.79    →  0.83 ✅
MRR:               0.51  →     0.57       →    0.62    →  0.64 ✅
Context Precision: 0.60  →     0.68       →    0.72    →  0.77 ✅
Faithfulness:      -     →     -          →    -       →  0.86 ✅  (RAG 목표 달성 후 측정)
```

---

## 평가 지표 참고 문헌

### RAG 검색 품질 (Hit Rate, MRR)

| 출처 | 핵심 내용 | URL |
|---|---|---|
| Dextralabs — Production RAG in 2025 | 프로덕션 기준 Hit Rate ≥ 0.80, 규제 산업 ≥ 0.90 | https://dextralabs.com/blog/production-rag-in-2025-evaluation-cicd-observability/ |
| getmaxim.ai — Complete Guide to RAG Evaluation 2025 | 도메인 특화 Precision@5 ≥ 0.70, Recall@20 ≥ 0.80 | https://www.getmaxim.ai/articles/complete-guide-to-rag-evaluation-metrics-methods-and-best-practices-for-2025/ |
| Medium — Evaluating RAG with LlamaIndex (실측 사례) | OpenAI Embedding 기준 Hit Rate 75.86%, MRR 0.6206 — 실제 기준선 | https://medium.com/@csakash03/evaluating-rag-with-llamaindex-3f74a35c53fa |
| Zilliz — MRR in RAG 문서 | MRR 개념 및 RAG 파이프라인 적용 방법 | https://zilliz.com/ai-faq/what-is-mean-reciprocal-rank-mrr-in-the-context-of-retrieval-evaluation-and-how-can-it-be-applied-to-gauge-how-well-a-rag-systems-retriever-finds-relevant-documents |
| Towards Data Science — MRR & AP in RAG (Part 2) | MRR 계산법, 한계, 대안 지표(AP) 비교 | https://towardsdatascience.com/how-to-evaluate-retrieval-quality-in-rag-pipelines-part-2-mean-reciprocal-rank-mrr-and-average-precision-ap/ |
| RAGAS 공식 문서 — Available Metrics | context_recall, context_precision, hit_rate 공식 정의 | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ |

### Faithfulness / LLM as Judge

| 출처 | 핵심 내용 | URL |
|---|---|---|
| DEV Community — Validate RAG Chatbot Outputs | faithfulness < 0.70 → 사람 검토 에스컬레이션 기준선 | https://dev.to/satyam_chourasiya_99ea2e4/how-to-validate-rag-based-chatbot-outputs-frameworks-tools-and-best-practices-for-reliable-2k1a |
| FaithJudge — arXiv 2505.04847 (EMNLP 2025) | 최고 LLM 판사(o3-mini-high) 인간 동의율 84%, F1-macro 82.1% | https://arxiv.org/abs/2505.04847 |
| MTRAG — arXiv 2501.03468 (IBM, TACL 2025) | 멀티턴 RAG 벤치마크. RAGAS Faithfulness가 인간 점수와 높은 상관 확인 | https://arxiv.org/abs/2501.03468 |
| Modulai — Evaluating RAG with synthetic data and LLM judge | QA쌍 합성 생성 → LLM judge 평가 실전 가이드 | https://modulai.io/blog/evaluating-rag-systems-with-synthetic-data-and-llm-judge/ |

### Context Precision / 개선 추적

| 출처 | 핵심 내용 | URL |
|---|---|---|
| RAGAS 공식 — Context Precision 정의 | "≥ 0.80이면 상위 랭킹 청크 대부분이 유용 — 노이즈 낮음" | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ |
| Superlinked — RAGAS 평가 실전 | Context Precision 0.9 = 노이즈 최소, Faithfulness 0.85 = 답변이 컨텍스트에 근거 | https://superlinked.com/blog/evaluating-retrieval-augmented-generation-ragas |
| Deepchecks — Answer Relevancy vs Faithfulness | 두 지표의 차이: 관련성(질문↔답) vs 근거성(컨텍스트↔답) | https://deepchecks.com/rag-evaluation-metrics-answer-relevancy-faithfulness-accuracy/ |

### 청크 크기 & RRF 튜닝 근거

| 출처 | 핵심 내용 | URL |
|---|---|---|
| ResearchGate — The Effect of Chunk Size on RAG Performance (2025) | 청크 크기 {150, 300, 600} 실험 — 작을수록 정밀도↑, 클수록 완전성↑. 최적값은 도메인마다 다름 | https://www.researchgate.net/publication/394594247_The_Effect_of_Chunk_Size_on_the_RAG_Performance |
| ELERAG RRF 케이스 스터디 | RRF 적용 후 MRR 0.622→0.742 향상. 베이스라인 대비 Exact Match·Recall·Precision 모두 개선 | https://qdrant.tech/blog/rag-evaluation-guide/ |
| RAGChecker — arXiv 2408.08067 | 세밀한 RAG 진단 프레임워크. 지표별 하이퍼파라미터 매핑(청크 크기→Context Recall, LLM 선택→Faithfulness) | https://arxiv.org/pdf/2408.08067 |

### 전체 RAG 평가 프레임워크

| 출처 | 핵심 내용 | URL |
|---|---|---|
| LabelYourData — RAG Evaluation 2026 (Enterprise) | 엔터프라이즈 RAG 평가 지표 종합 정리 | https://labelyourdata.com/articles/llm-fine-tuning/rag-evaluation |
| premai.io — RAG Evaluation Metrics, Frameworks & Testing 2026 | LlamaIndex·RAGAS·LangSmith 프레임워크 비교 | https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026/ |
| langcopilot.com — RAG Evaluation 101 (2026) | Recall@K·MRR·Faithfulness·RAGAS 실무 가이드 | https://langcopilot.com/posts/2025-09-17-rag-evaluation-101-from-recall-k-to-answer-faithfulness |
| Qdrant — Best Practices in RAG Evaluation | 검색 품질·생성 품질·운영 지표 종합 가이드. 개선 루프 설계 포함 | https://qdrant.tech/blog/rag-evaluation-guide/ |
