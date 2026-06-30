# Simulation 챗 어시스턴트 — 단기/장기 메모리 도입

> 작성 2026-06-30 · 도메인 `domain/simulation` (+ 공통부 `core/`) · 상태 설계 확정(구현 전)
> 작업자 브랜치(`feat/simulation-yeotaeho`)에서 먼저 구현 → 검증 후 팀(특히 management 팀) 제안

## 1. 배경 / 문제

현재 4-1(시뮬레이터)·4-2(매니지먼트)·4-3(생성) 세 챗 서브에이전트 중 매니지먼트만
멀티턴 단기기억(체크포인터)과 세션 넘는 장기기억(`ManagementMemory` →
`management_user_memory`)을 갖는다. Simulator는 완전 stateless ReAct 함수
([agent.py](../../../backend/domain/simulation/assistant/agent.py)·
[graph.py](../../../backend/domain/simulation/assistant/graph.py))라 매 호출이
독립적이고, 직전 대화·과거 시뮬 관련 대화 맥락을 전혀 활용하지 못한다.

목표는 매니지먼트가 이미 검증한 메모리 아키텍처(체크포인터 + 장기기억 테이블)를
시뮬레이션 챗 어시스턴트에도 **동일한 형태로** 도입하는 것. 페르소나 생성 로직은
이번 범위에 포함하지 않는다(별개 코드 경로, 회원님 담당 영역이지만 이 작업과 무관).

## 2. 공용 코드 재배치 — `build_checkpointer`를 `core/`로

체크포인터 빌더 [`build_checkpointer`](../../../backend/domain/management/wiring.py:122)는
이미 `domain/chat/orchestrator.py:873`이 가져다 쓰고 있다(챗 오케스트레이터는
도메인이 아니라 조정자라 예외로 봐도 무방). 그러나 이번에 `domain/simulation`이
**형제 도메인인 management의 내부 모듈을 직접 import**하면 CLAUDE.md의
"타 도메인 내부 직접 import 금지" 원칙을 깬다.

해결책 — 이 함수를 공통부로 승격한다.

- 신규 `core/checkpointer.py` — `build_checkpointer(settings)` + 기존
  `init_pg_checkpointer`/`close_pg_checkpointer`/`get_pg_checkpointer`
  ([domain/management/assistant/checkpointer.py](../../../backend/domain/management/assistant/checkpointer.py)
  전체)를 그대로 이동. Neon Postgres 풀·`AsyncPostgresSaver`·Windows 폴백 로직
  무변경(검증된 코드를 옮기기만 함).
- `domain/management/wiring.py::build_checkpointer`는 `core.checkpointer`를
  재-export하는 thin wrapper로 축소(다른 호출부 무수정).
- `domain/simulation/assistant/`는 `core.checkpointer`를 직접 import.

**이 부분은 공통부 변경**이므로 CLAUDE.md 규칙대로 **별도의 작은 단독 PR**로
먼저 올리고 팀(특히 management 팀)에 사전 공지한다. simulation 도메인 PR은
이 PR이 머지된 뒤 그 위에 얹는다.

## 3. 단기 메모리 — Simulation 챗 그래프에 체크포인터 적용

- `domain/simulation/assistant/graph.py`를 stateless 호출 함수에서
  `StateGraph(...).compile(checkpointer=...)` 형태로 전환(매니지먼트
  [assistant/graph.py](../../../backend/domain/management/assistant/graph.py) 패턴 미러).
- `core.checkpointer.build_checkpointer(settings)`를 그대로 사용 — 같은
  Neon `checkpoints` 테이블을 공유하지만 LangGraph 체크포인터는 `thread_id`로
  격리되므로 도메인 간 데이터가 섞이지 않는다(매니지먼트·챗 오케스트레이터와
  동일한 전제).
- thread_id는 시뮬 챗 세션 식별자(`session_id` 또는 `f"{session_id}:simulation"`
  네임스페이스 — 챗 오케스트레이터가 매니지먼트 호출 시 쓰는 패턴과 동일하게
  충돌 방지).

## 4. 장기 메모리 — `SimulationAssistantMemory`

매니지먼트의 `ManagementMemory`/`SqlMemoryStore`
([memory_store.py](../../../backend/domain/management/assistant/memory_store.py))를
그대로 미러링하되, 스코프만 `(tenant_id, user_id)` → **`project_id`**로 바꾼다
(기획서상 "프로젝트 = 캠페인 단위"이고, 기존 `chat_long_term_memory`도 project_id
스코프라 일관성 유지).

### 4.1 신규 테이블 (`core/models.py`)

```python
class SimulationAssistantMemory(Base):
    """시뮬레이션 챗 어시스턴트 — 프로젝트 단위 cross-session 장기기억."""

    __tablename__ = "simulation_assistant_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    mem_key: Mapped[str] = mapped_column(String(128))  # 멱등/식별 키
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- `project_id`는 `management_user_memory`와 달리 NULL 불가(시뮬은 항상 프로젝트
  컨텍스트 내에서 실행되므로 global/anon 네임스페이스 불필요).
- 인덱스: `(project_id, mem_key)` 복합 — upsert 조회·중복 제거용. `management_user_memory`엔
  명시 인덱스가 없으므로(현재 순차 스캔) 동일하게 인덱스 없이 시작하되, 운영 데이터
  늘어나면 후속 마이그로 추가.

### 4.2 Alembic 마이그레이션

- 새 revision 1개(`030_simulation_assistant_memory.py` 등, 직전 archive 최신은
  029) — `simulation_assistant_memory` 테이블 생성 + `docs/db-schema.md` 갱신.
- **DB 스키마 단독 변경 금지** 규칙대로 이 리비전은 사전 공지 후 진행한다(섹션 2의
  공통부 PR과 별개 — 마이그레이션은 simulation PR에 포함하되 리뷰 시 management/DB
  오너에게 명시적으로 알린다).

### 4.3 `domain/simulation/assistant/memory_store.py` (신규)

`ManagementMemory`/`SqlMemoryStore`/`_build_embedder`를 그대로 복사해 모델만
`SimulationAssistantMemory`로, 네임스페이스 키를 `(tenant_id, user_id)` → `project_id`
단일 값으로 교체한 `SimulationAssistantStore`/`SimulationMemory` 클래스. 동작 동일:

- `remember(project_id, key, value)` — 시맨틱 모드면 `value["fact"]`/`["note"]` 임베딩
  후 upsert(`project_id`+`mem_key` 키로 중복 제거).
- `recall(project_id, query=None, limit=5)` — query+임베더 있으면 코사인 top-k,
  없으면 `created_at DESC` recency 폴백.
- `build_memory_store(settings)` — mock이면 `InMemoryStore`(hermetic), 실모드면
  `SimulationAssistantStore` + OpenAI `text-embedding-3-small` 임베더(매니지먼트와
  동일 모델 — 임베딩 공간 호환 의미는 없지만 운영 비용·코드 일관성 측면에서 통일).

## 5. 그래프 통합 — `memory_context` 주입

매니지먼트 챗 노드가 `memory_context`를 시스템 프롬프트에 주입하는 패턴
([orchestrator.py](../../../backend/domain/chat/orchestrator.py):605-619)을 시뮬
서브에이전트에도 적용한다.

- `domain/simulation/assistant/graph.py` 호출 전, `SimulationMemory.recall(project_id, question)`
  결과를 포맷해 시스템 프롬프트 앞에 붙인다(매니지먼트의 `_format_ltm` 유사 헬퍼를
  시뮬 전용으로 작성 — `domain/chat/orchestrator.py`의 공용 포맷터를 가져다 쓰지 않고
  도메인 내부에 둔다. 챗 오케스트레이터 쪽 포맷터는 `chat_long_term_memory`용이라 스키마가 다름).
- 매 시뮬 챗 응답 후 의미 있는 사실(예: 반복 질문·사용자가 명시한 해석 선호)을
  `remember()`로 적재할지는 1차 구현에서는 **하지 않는다**(YAGNI — 우선 회수만 동작
  확인 후, 적재 트리거는 후속 이슈로 분리. 매니지먼트도 `remember` 호출 지점은
  별도 도구/노드로 명시적으로 트리거됨 — 자동 추출이 아님).

## 6. 제외 범위 (YAGNI)

- **HITL/propose_action** — 시뮬레이터는 읽기 전용 도메인(4-1)이라 실행 제안 개념이
  없음. 매니지먼트만의 차별점으로 유지, 이번 작업에서 추가하지 않는다.
- **RAG 하이브리드(RRF+CRAG-lite) 업그레이드** — 현재 `SimKbRetriever`(stateless
  벡터 검색)는 그대로 둔다. 요청 범위는 메모리뿐.
- **`remember()` 자동 트리거** — 섹션 5 참고, 회수만 우선 구현.
- **management_user_memory와의 통합/공유** — 두 테이블은 스코프(project vs
  tenant+user)가 달라 통합하지 않는다. 구조만 미러링.

## 7. 영향 파일

**공통부 PR**
- 신규 `core/checkpointer.py` — `domain/management/assistant/checkpointer.py` 전체 이동.
- `domain/management/wiring.py::build_checkpointer` — `core.checkpointer` 재-export로 축소.
- `domain/management/assistant/checkpointer.py` — 삭제(또는 deprecated re-export, 팀 합의 후 결정).

**simulation 도메인 PR**
- `domain/simulation/assistant/graph.py` — stateless → `StateGraph`+체크포인터 컴파일.
- 신규 `domain/simulation/assistant/memory_store.py` — `SimulationAssistantStore`/`SimulationMemory`.
- `domain/simulation/assistant/agent.py` 또는 graph 노드 — `memory_context` 조회·주입 연결.
- `core/models.py` — `SimulationAssistantMemory` 모델 추가.
- 신규 Alembic revision(`030_simulation_assistant_memory.py`).
- `docs/db-schema.md` — 신규 테이블 문서화.

**참조/무변경**: `domain/management/*`(checkpointer 이동 외 로직 무변경), `domain/chat/orchestrator.py`
(simulation_node 호출 시그니처 무변경 — `AssistantRequest`에 이미 `project_id`가 있어
추가 배선 불필요), 페르소나 생성 코드 전체.

## 8. 검증 계획

- **단위(hermetic)**
  - `SimulationMemory.remember`/`recall` — mock(InMemoryStore) 기준 upsert·recency 회수.
  - `core.checkpointer.build_checkpointer` — Windows 환경에서 MemorySaver 반환(기존
    `init_pg_checkpointer` Windows 분기 테스트 재사용/이동).
  - 그래프 컴파일 — checkpointer 주입 후 동일 thread_id로 2턴 호출 시 `state["messages"]`
    누적 확인.
- **라이브(실 키, mock 데이터)**
  - 턴1 질문 → 턴2 "그거 더 자세히" 같은 후속 질문이 직전 맥락을 참조하는지.
  - 같은 project_id로 다른 세션에서 재질문 시 `recall`이 과거 장기기억을 끌어오는지.
- `cd backend && uv run ruff format . && uv run ruff check .` + `uv run pytest tests/ -v`
  (특히 `tests/simulation`·`tests/management`의 checkpointer 관련 테스트가 이동 후에도
  통과하는지).

## 9. 리스크

- **`checkpoints` 테이블 공유** — management·simulation·chat 오케스트레이터가 같은
  Postgres 체크포인트 테이블을 쓰게 된다. thread_id 네임스페이스가 겹치면 상태가
  섞일 수 있음 — `f"{session_id}:simulation"` 같은 접두사 규칙을 문서화해 강제(현재
  챗 오케스트레이터도 매니지먼트 호출에 `:management` 접두사를 이미 쓰고 있어 선례
  일관).
- **공통부 PR 리뷰 지연** — `core/checkpointer.py` 이동은 management 팀 동의가
  필요해 simulation PR 착수가 지연될 수 있음. 완화: 먼저 작은 PR로 분리해 빠르게
  리뷰받고, simulation 쪽 작업은 그 사이 메모리 store/모델 설계까지 미리 진행.
- **임베딩 비용 증가** — 시뮬 챗에도 OpenAI 임베딩 호출이 추가됨(매니지먼트와 별도
  과금). 영향 작아 보이나 운영 모니터링 항목에 추가 권장.
