# 챗봇 개발 핸드오프

> 작성 2026-06-24 · 전체 20개 태스크 · 루프로 순차 진행

---

## 브랜치

```
feat/chat-doyeon  (작업 브랜치)
```

---

## 전체 태스크 현황

| # | 태스크 | 분류 | 상태 |
|---|--------|------|------|
| T01 | SSE envelope 표준화 | 토대 | ✅ |
| T02 | LangChain 숏텀 메모리 | 토대 | ✅ |
| T03 | 롱텀 메모리 기본 구현 | 토대 | ✅ |
| T04 | 개선 루프 컨트롤러 | 핵심 기능 | ✅ |
| T05 | 세션 요약 (10턴 자동) | 메모리 | ✅ |
| T06 | 브랜드 프로파일 메모리 | 메모리 | ✅ |
| T07 | 결과 패턴 학습 | 메모리 | ✅ |
| T08 | KOBACO 벤치마크 비교 | 인사이트 | ✅ |
| T09 | 프로젝트 패턴 분석 | 인사이트 | ✅ |
| T10 | 카피 개선 제안 구체화 | 인사이트 | ✅ |
| T11 | 배치 시뮬 | 실행 | ✅ |
| T12 | 템플릿 저장·재사용 | 실행 | ✅ |
| T13 | 채팅 기반 리포트 | 실행 | ✅ |
| T14 | /비교 명령어 | UX | ✅ |
| T15 | /도움말 명령어 | UX | ✅ |
| T16 | Quick Action 칩 버튼 | UX | ✅ |
| T17 | 로딩 스피너 위젯 | UX | ✅ |
| T18 | 프로액티브 푸시 | UX | ✅ |
| T19 | 채팅 내 결과 핀 | UX | ✅ |
| T20 | 라우팅 정확도 로그 | 품질 | ✅ |

---

## TASK 명세

### T01 — SSE envelope 표준화

**목표**: 모든 SSE 이벤트에 `kind` 이름표 추가

**현재 → 변경**
```
# 현재
{"meta": {...}}
{"token": "청크"}
{"done": true}

# 변경
{"kind": "meta",     "meta": {...}}
{"kind": "text",     "token": "청크"}
{"kind": "widget",   "widget": {...}}
{"kind": "approval", "approval": {...}}
{"kind": "done"}
```

**수정 파일**
- `backend/api/routers/chat.py` — generate() yield 포맷
- `frontend/src/components/chat/ChatConversation.tsx` — SSE 파싱 분기

---

### T02 — LangChain 숏텀 메모리

**목표**: raw tuple history → `ConversationBufferWindowMemory(k=6)`

**수정 파일**
- `backend/domain/chat/orchestrator.py`
  - session_id 키로 메모리 캐시 (서버 재시작 시 초기화, checkpointer는 별도)
  - 각 노드에서 `memory.load_memory_variables({})` 사용

---

### T03 — 롱텀 메모리 기본 구현

**목표**: 시뮬/생성 실행 입력값 DB 저장 → 다음 대화에 컨텍스트 주입

**DB 모델** (`backend/core/models.py`)
```python
class ChatLongTermMemory(Base):
    __tablename__ = "chat_long_term_memory"
    id: UUID PK
    project_id: UUID FK (nullable)
    user_id: UUID FK (nullable)
    memory_type: str  # "sim_input" | "gen_input" | "user_pref"
    content: JSONB
    created_at: datetime
```

**흐름**
1. simulation_node run → `sim_input` 저장
2. generator_node run → `gen_input` 저장
3. 오케스트레이터 진입 시 최근 3개 조회 → 시스템 프롬프트 앞 주입

**수정 파일**
- `backend/core/models.py` — 모델 추가
- `backend/alembic/versions/` — 마이그레이션 생성
- `backend/domain/chat/history.py` — `save_long_term_memory()`, `get_long_term_memory()`
- `backend/domain/chat/orchestrator.py` — 저장·조회·주입

---

### T04 — 개선 루프 컨트롤러

**목표**: 시뮬↔제너 왕복 최대 3회, 매 전환 HITL 수락/거절

**루프 상태** (session_id 키로 인메모리 보관)
```python
@dataclass
class LoopState:
    loop_count: int = 0          # 최대 3
    phase: str = "idle"          # idle | sim_done | gen_done | finished
    last_sim_id: str | None = None
    last_gen_id: str | None = None
    weak_reasons: list[str] = field(default_factory=list)
```

**흐름**
```
시뮬 결과 약함 (구매의도 < 3.5 OR 거부율 >= 30%)
  → loop_count < 3
    → kind: "approval" 이벤트 전송
      payload: {action: "run_generator", label: "개선 시안 만들기", reasons: [...]}
  → loop_count == 3 → 루프 종료 요약

수락 (POST /api/chat/approve {action: "run_generator", session_id})
  → generator_node 호출 (개선 모드, last_sim_id 컨텍스트 전달)
  → 완료 후 재시뮬 approval 이벤트

목표 도달 (구매의도 >= 3.5 AND 거부율 < 0.3)
  → "목표 도달. 최종 결과를 정리할게요." → finished
```

**수정 파일**
- `backend/domain/chat/orchestrator.py` — LoopState, approval 이벤트 emit
- `backend/api/routers/chat.py` — `POST /api/chat/approve`
- `frontend/src/components/chat/ChatConversation.tsx` — approval kind 처리
- `frontend/src/components/chat/ApprovalWidget.tsx` — 신규 (수락/거절 버튼 카드)

---

### T05 — 세션 요약 (10턴 자동)

**목표**: 대화 10턴 초과 시 앞 내용 자동 요약, 숏텀 메모리 압축

**흐름**
- `append_turn()` 호출 시 세션 메시지 수 체크
- 10턴 초과 → GPT-4o-mini로 이전 대화 요약 생성
- 요약을 `ChatLongTermMemory`에 `memory_type="session_summary"` 로 저장
- 오케스트레이터: 요약 있으면 full history 대신 요약 + 최근 4턴만 전달

**수정 파일**
- `backend/domain/chat/history.py` — `summarize_and_compress()`
- `backend/domain/chat/orchestrator.py` — 요약 활용 로직

---

### T06 — 브랜드 프로파일 메모리

**목표**: 프로젝트마다 브랜드 톤·타겟·카테고리 기억 → 매번 입력 안 해도 됨

**DB 모델** (`backend/core/models.py`)
```python
class BrandProfile(Base):
    __tablename__ = "brand_profiles"
    id: UUID PK
    project_id: UUID FK UNIQUE
    brand_name: str | None
    tone: str | None            # "친근한", "전문적인" 등
    target_audience: str | None # "20-30대 여성"
    product_category: str | None
    keywords: list[str]         # JSONB
    updated_at: datetime
```

**흐름**
- 채팅에서 "이 프로젝트 타겟은 20대 여성이야" → BrandProfile 자동 업데이트
- 오케스트레이터 진입 시 project_id로 조회 → 시스템 프롬프트 주입
- "브랜드 설정 보여줘" → 현재 BrandProfile 출력

**수정 파일**
- `backend/core/models.py`, 마이그레이션
- `backend/domain/chat/orchestrator.py` — 브랜드 프로파일 주입 + 업데이트 감지

---

### T07 — 결과 패턴 학습

**목표**: "이 프로젝트에서 거부율 높은 광고들의 공통점 찾아줘" 가능하게

**구현**
- `fetch_project_sim_patterns(project_id, limit=20)` 도구 추가
  - 최근 N개 시뮬 결과 조회
  - 약한 결과들(거부율 >= 30%)의 공통 패턴 추출 (카테고리, 목표, 카피 길이 등)
- 시뮬레이션 어시스턴트 도구로 등록

**수정 파일**
- `backend/domain/simulation/assistant/tools.py` — `fetch_project_sim_patterns`
- `backend/domain/simulation/assistant/agent.py` — 도구 등록

---

### T08 — KOBACO 벤치마크 비교

**목표**: 시뮬 결과를 업계 평균과 자동 대조 ("이 결과가 뷰티 카테고리 평균 대비 어때?")

**구현**
- `backend/data/kobaco_benchmarks.json` — 카테고리별 평균 KPI 데이터 (하드코딩으로 시작)
  ```json
  {"뷰티": {"purchase_intent": 3.2, "click_intent_rate": 0.22, "rejection_rate": 0.18}, ...}
  ```
- `fetch_kobaco_benchmark(category)` 도구 추가
- `sim_result_node`에서 결과 해석 시 벤치마크 자동 비교 후 멘트 추가
  - "뷰티 카테고리 평균(구매의도 3.2) 대비 +0.6"

**수정 파일**
- `backend/data/kobaco_benchmarks.json` — 신규
- `backend/domain/simulation/assistant/tools.py` — `fetch_kobaco_benchmark`
- `backend/domain/chat/orchestrator.py` — `sim_result_node` 벤치마크 인용

---

### T09 — 프로젝트 패턴 분석

**목표**: "이번 달 내 시뮬들 중 뭐가 제일 잘 나왔어?" 프로젝트 단위 요약

**구현**
- `fetch_project_summary(project_id, period="month")` 도구
  - 기간 내 시뮬/생성 집계: 평균 KPI, 최고/최저 결과, 자주 쓴 카테고리
- 시뮬레이션 어시스턴트 + 오케스트레이터 advise_node 도구로 등록

**수정 파일**
- `backend/domain/simulation/assistant/tools.py`

---

### T10 — 카피 개선 제안 구체화

**목표**: "약함" 판정 시 "개선하세요"가 아닌 구체적 방향 제시

**현재**: "결과가 약해요 — 거부율 32%. 개선 시안 만들어볼까요?"

**변경**: 약한 이유를 분석해서 구체적 제안 추가
```
결과가 약해요 — 거부율 32%.

원인 분석:
- 거부율이 높을 때는 주로 소구 방식이 너무 직접적이거나
  가격 언급이 과도한 경우예요.
- 이 광고는 "최저가 보장"을 전면에 내세웠는데, 이 표현이
  신뢰도를 낮출 수 있어요.

개선 방향:
- 가격 대신 '경험/감성' 소구로 전환
- 타겟(20대 여성)이 공감할 상황 묘사 추가

개선 시안 만들어볼까요? [수락] [거절]
```

**수정 파일**
- `backend/domain/chat/orchestrator.py` — `sim_result_node` 프롬프트 강화

---

### T11 — 배치 시뮬

**목표**: 광고 여러 버전을 한 번에 비교 시뮬

**구현**
- `POST /api/simulations/batch` — `ads: list[SimInput]` 받아서 복수 run_id 반환
- `SimulationService.start_batch()` — 순차 실행 (동시 실행 금지 정책 유지)
- 채팅에서 "이 두 광고 비교해줘" → `batch_sim_form` 위젯 (광고 2개 입력 폼)
- 완료 후 `batch_sim_result` 위젯 — KPI 나란히 비교 테이블

**수정 파일**
- `backend/domain/simulation/service/simulation_service.py`
- `backend/api/routers/simulate.py`
- `backend/domain/chat/orchestrator.py` — `batch_simulation_node`
- `frontend/src/components/chat/BatchSimWidget.tsx` — 신규

---

### T12 — 템플릿 저장·재사용

**목표**: 자주 쓰는 광고 설정 저장, "지난번 여름 캠페인 설정으로" 재사용

**DB 모델**
```python
class AdTemplate(Base):
    __tablename__ = "ad_templates"
    id: UUID PK
    project_id: UUID FK
    name: str              # "여름 캠페인", "뷰티 기본"
    template_type: str     # "sim" | "gen"
    content: JSONB         # 설정값
    created_at: datetime
```

**채팅 흐름**
- "이 설정 저장해줘" → 템플릿 이름 입력 → 저장
- "내 템플릿 보여줘" → 목록 위젯
- "여름 캠페인 템플릿으로 시뮬 돌려줘" → 자동 폼 채우기

**수정 파일**
- `backend/core/models.py`, 마이그레이션
- `backend/api/routers/chat.py` — templates CRUD
- `backend/domain/chat/orchestrator.py` — 템플릿 저장/로드 도구

---

### T13 — 채팅 기반 리포트

**목표**: "이번 달 시뮬 결과 PDF로 뽑아줘" 채팅에서 트리거

**구현**
- `generate_project_report(project_id, period)` 도구 — 기존 PDF 생성 기능 재사용
- 완료 후 `report_ready` 위젯 (다운로드 버튼) SSE로 전송

**수정 파일**
- `backend/domain/chat/orchestrator.py` — `generate_report` 도구 추가
- `frontend/src/components/chat/ReportWidget.tsx` — 신규 (다운로드 버튼 카드)

---

### T14 — /비교 명령어

**목표**: `/비교` 입력 시 시뮬레이션 2개 선택 → KPI 나란히 비교

**흐름**
- `/비교` → 목록 위젯 (선택 모드, 다중 선택)
- 2개 선택 → `comparison_result` 위젯 (KPI 비교 테이블)

**수정 파일**
- `backend/domain/chat/orchestrator.py` — `/비교` 명령어 감지 → compare 액션
- `frontend/src/components/chat/SimGenListWidget.tsx` — 다중 선택 모드 추가
- `frontend/src/components/chat/ComparisonWidget.tsx` — 신규

---

### T15 — /도움말 명령어

**목표**: `/도움말` 입력 시 사용 가능한 명령어 + 예시 프롬프트 표시

**내용**
```
/시뮬레이션  광고 반응 시뮬레이션 실행
/제너레이터  광고 시안 생성
/비교        시뮬레이션 2개 KPI 비교
/내역        최근 실행 목록
/도움말      이 화면

이렇게 말해도 돼요
  "이 광고 반응 예측해줘"
  "수분크림 광고 시안 만들어줘"
  "우리 캠페인 예산 소진율 알려줘"
  "저번 시뮬보다 이번 게 왜 낮아?"
```

**수정 파일**
- `frontend/src/components/chat/ChatConversation.tsx` — 명령어 감지 + 도움말 렌더

---

### T16 — Quick Action 칩 버튼

**목표**: 입력창 위에 자주 쓰는 명령 칩(chip) 표시, 클릭 시 자동 입력

**칩 목록**
```
[시뮬 돌리기]  [시안 만들기]  [내역 보기]  [비교하기]  [도움말]
```

**수정 파일**
- `frontend/src/components/chat/ChatConversation.tsx` — 칩 UI + 클릭 핸들러

---

### T17 — 로딩 스피너 위젯

**목표**: 백그라운드 시뮬/생성 진행 중 플로팅에 스피너 + 진행률 표시

**현재**: 진행 중 표시 없음

**변경**
- 시뮬/생성 실행 시 `kind: "progress"` 이벤트 주기적 전송
  ```json
  {"kind": "progress", "progress": {"label": "시뮬레이션 🔄", "pct": 62, "run_id": "..."}}
  ```
- 플로팅 챗봇에 진행 중 트레이 (스피너 + %) 표시
- 완료 시 "결과 보기" 버튼으로 전환

**수정 파일**
- `backend/api/routers/chat.py` — progress 이벤트 emit
- `frontend/src/components/chat/FloatingChat.tsx` — 진행 트레이 UI

---

### T18 — 프로액티브 푸시

**목표**: 백그라운드 시뮬 완료 시 챗봇이 먼저 알림 ("결과 나왔어요 — 구매의도 3.8")

**흐름**
- 시뮬 완료 이벤트 → 플로팅 챗봇 배지 (숫자 뱃지)
- 플로팅 클릭 시 → 완료 메시지 + 결과 위젯 자동 표시

**수정 파일**
- `frontend/src/components/chat/FloatingChat.tsx` — 배지 + 완료 메시지 push
- `frontend/src/components/chat/ChatController.tsx` — 완료 이벤트 수신

---

### T19 — 채팅 내 결과 핀

**목표**: 중요한 메시지 핀 고정, 세션 상단에 표시

**구현**
- 어시스턴트 메시지에 핀 버튼
- 핀된 메시지 → `ChatMessage.meta.pinned = true` DB 업데이트
- 세션 상단에 핀된 메시지 미리보기 표시

**수정 파일**
- `backend/domain/chat/history.py` — `pin_message()`
- `backend/api/routers/chat.py` — `PATCH /api/chat/messages/{id}/pin`
- `frontend/src/components/chat/ChatConversation.tsx` — 핀 버튼 + 상단 고정 UI

---

### T20 — 라우팅 정확도 로그

**목표**: 어떤 질문이 어느 도메인으로 라우팅됐는지 기록, 추후 eval에 활용

**구현**
- `classify` 노드 완료 시 `chat_messages.meta`에 `routing` 필드 추가
  ```json
  {"routing": {"intent": "simulation", "action": "run", "confidence": "high"}}
  ```
- 별도 로그 테이블 없이 기존 meta JSONB 활용

**수정 파일**
- `backend/domain/chat/orchestrator.py` — classify 결과 meta에 포함
- `backend/api/routers/chat.py` — persist 시 routing meta 전달

---

## 의존성 순서 (루프 실행 순)

```
T01 (envelope) ──┬── T02 (숏텀 메모리) ──┬── T04 (개선 루프)
                 └── T03 (롱텀 메모리) ──┘       │
                                                  ├── T10 (카피 개선 구체화)
T03 ──── T05 (세션 요약)                          └── T08 (KOBACO 벤치마크)
T03 ──── T06 (브랜드 프로파일)
T03 ──── T07 (결과 패턴 학습) ─── T09 (프로젝트 패턴 분석)
T04 ──── T11 (배치 시뮬)
T01 ──── T17 (로딩 스피너) ─── T18 (프로액티브 푸시)

독립 (언제든 가능):
  T12 (템플릿), T13 (리포트), T14 (/비교), T15 (/도움말),
  T16 (Quick Action), T19 (결과 핀), T20 (라우팅 로그)
```

---

## 핵심 파일 경로

```
docs/chat/architecture.md                              ← 전체 아키텍처 설계
docs/chat/handoff.md                                   ← 이 파일

backend/domain/chat/orchestrator.py                    ← 오케스트레이터 (LangGraph)
backend/domain/chat/history.py                         ← 세션/메시지 영속화
backend/api/routers/chat.py                            ← SSE 엔드포인트
backend/core/models.py                                 ← DB 모델
backend/core/schemas.py                                ← ChatRequest 등
backend/domain/simulation/assistant/tools.py           ← 시뮬 도구
backend/domain/generator/assistant/tools.py            ← 생성 도구

frontend/src/components/chat/ChatConversation.tsx      ← 메인 채팅 UI + SSE 파싱
frontend/src/components/chat/FloatingChat.tsx          ← 플로팅 챗봇
frontend/src/components/chat/ChatController.tsx        ← 전역 상태
frontend/src/components/chat/SimFormWidget.tsx
frontend/src/components/chat/GenFormWidget.tsx
frontend/src/components/chat/SimGenListWidget.tsx
```

---

## 개발 환경

```bash
# 백엔드
cd backend && uv run uvicorn api.main:app --reload --port 8000

# 프론트엔드
cd frontend && pnpm dev

# Ruff (백엔드 수정 후 반드시)
cd backend && uv run ruff format . && uv run ruff check . --fix

# Alembic (모델 추가 시)
cd backend && uv run alembic revision --autogenerate -m "설명"
cd backend && uv run alembic upgrade head
```

---

## 열린 질문

| 질문 | 상태 |
|------|------|
| 개선 루프 조기 종료 기준 | purchase_intent >= 3.5 AND rejection_rate < 0.3 로 임시 설정 |
| 플로팅 ↔ /chat 탭 세션 공유 여부 | 미결 |
| KOBACO 데이터 실제 출처 | 임시 하드코딩으로 시작, 추후 교체 |
| 배치 시뮬 동시 실행 정책 | 순차 실행 유지 (동시 시뮬 금지 정책 준수) |

---

## 진행 메모 (루프 구현 중 결정·이탈)

- **T01~T20 전부 완료** (2026-06-24). 마이그레이션 022·023·024 NeonDB 적용 완료. 백엔드 446개 테스트 import 정상, app 라우터 155개 로드 확인.
- **T11 배치 시뮬**: 경로는 명세(`/api/simulations/batch`) 대신 채팅 소유 `POST /api/chat/sim-batch`(순차 실행, 기존 run_simulation 재사용).
- **T13 리포트**: 프로젝트-기간 PDF 생성기가 없어 신규(`domain/chat/report.py`). 기존 Playwright 렌더 방식 재사용, Chromium 없으면 HTML 폴백. `GET /api/chat/report`.
- **T17/T18**: 진행 트레이·완료 배지는 `ChatController` 전역 상태로. FloatingChat은 접혀도 언마운트하지 않고 숨겨(백그라운드 실행·알림 유지).
- **T20**: 별도 로그 테이블 없이 classify 결과를 `chat_messages.meta.routing`(intent·action·confidence)에 영속.
- **공통 주의**: 풀 오케스트레이터 경로는 `use_mock=false` + OpenAI 키 필요. 현재 개발 환경은 `use_mock=true`라 슬래시·키워드 폴백만 동작 — 실연동 통합 테스트는 운영 환경에서 확인 필요.
- **(이전) T01~T10 완료**. 마이그레이션 022·023.
- **T02 숏텀 메모리**: LangChain 1.x에서 `ConversationBufferWindowMemory` 제거 → `langchain_core` 메시지로 동일 의미(k=6 윈도잉)의 `_WindowMemory` 자체 구현 (orchestrator.py 내부).
- **T06 브랜드 프로파일**: 명세는 `brand_profiles` 테이블이나 제너레이터 `BrandProfileRow`가 이미 사용 중 → 충돌 방지로 **`chat_brand_profiles`** 테이블·`ChatBrandProfile` 모델 사용.
- **T07/T09 도구 등록**: 명세는 `assistant/agent.py`라 했으나 실제 `@tool` 등록 지점은 `assistant/graph.py` → graph.py에 등록.
- **T04 approve**: `POST /api/chat/approve`는 오케스트레이터 run 분기를 합성 질문으로 재사용해 위젯 스트리밍.
