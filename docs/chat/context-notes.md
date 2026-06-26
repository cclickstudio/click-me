# 채팅 통합 — 컨텍스트 노트

> 목표: 이 브랜치(feat/generator-token-opt)에서 **시뮬·생성·관리를 한 채팅**으로. "말하는 챗"이 아니라 **행동하는 챗**(되묻고 → 잡을 돌리고 → 조치를 제안).

※ 내용은 현재 제 테스트 브랜치 기준으로 작성이 된겁니다.

## 🧭 설계 철학 — "에이전트를 넘어 AI 비서"

팀 지향점은 단순 응답/실행 에이전트가 아니라 **AI 비서**다. 차이 = **선제성(proactive)**. 사용자가 다음 행동을 일일이 지시하기 전에, 맥락을 읽고 **다음 단계를 먼저 제안**한다.

- 갈림길마다 기본값은 "비서답게 **먼저 제안**". (예: 시뮬 결과가 나오면 사용자가 안 물어도 "개선할까요?"를 자동으로 띄움.)
- 단 선제성이 강요가 되면 안 됨 — 제안은 하되 **실행·승인은 사용자**(특히 관리의 위험 조치는 HITL 승인 게이트 유지).
- 이 원칙이 향후 "여기서 먼저 제안 vs 기다림" 결정의 기본 기준.

## 🎯 목표 사용자 흐름 (사용자 정의 — 핵심 목표 흐름)

채팅창 하나에서 **시뮬 → 결과 → 개선 이미지 → 관리**까지 한 흐름으로.

1. 사용자: "시뮬레이션 하고 싶어"  → 교통정리 → **시뮬 담당**.
2. 이미지를 안 넣었으면 → **되묻기(ASK)** "광고 이미지를 넣어주세요".
3. 이미지 첨부 후 시작 → **작업시작(TRIGGER)** → 로딩(스트리밍) → 시뮬 결과.
4. 결과 보고 "이 광고 개선하고 싶어" → **생성 담당(개선모드)** 으로 바통터치 → 시뮬 결과를 받아 **개선 이미지 생성(TRIGGER)**.
5. 개선 시안이 나오면 "이걸로 캠페인 관리하고 싶어" → **관리 담당**으로 넘어가 예산·성과·집행 상태를 한 창에서 본다.
6. (별개) "새 광고 만들어줘" → 생성 담당이 필요한 데이터 되묻기 + **상품/로고 이미지는 선택 첨부**.

### 전체 사슬 — 시뮬 → 생성 → 관리 (3담당 릴레이)

세 담당이 **바통터치로 이어지는 한 줄**이 목표 그림이다. 채팅은 그 사이를 교통정리(오케스트레이터)가 잇는다.

```
[시뮬 담당]  광고 이미지 입력 → 반응 예측(4대 KPI)
     │  결과 요약 + 원본 이미지 s3_key 를 넘김(improve_context)
     ▼
[생성 담당]  개선모드 → 5개 전략 기반 시안 3개 생성·순위
     │  채택한 시안(이미지/메타)을 넘김
     ▼
[관리 담당]  집행 캠페인의 예산·성과·상태 관리(위험 조치는 HITL 승인)
```

- **단계마다 자동 제안(선제성)** — 시뮬 결과 끝에 "개선할까요?", 개선 시안 끝에 "이걸로 집행/관리할까요?"를 채팅이 **먼저 띄운다**. 실행·승인은 항상 사용자.
- **현재 상태** — 시뮬→생성 바통터치(`improve_context`) 설계는 잡혀 있고, 생성→관리 연결은 **관리 담당을 교통정리에 붙이기만** 하면 된다(아래 열린 질문). 즉 세 담당은 다 존재하고, 남은 일은 채팅 입구에서 잇는 연결.

### 이 흐름이 추가로 요구하는 것

- **채팅 내 이미지 첨부** — 시뮬은 광고 이미지가 있어야 돌고, 생성은 상품/로고 이미지를 **선택**으로 받음.
  - ✅ **생성용 이미지(로고·상품)** — 인라인 `AssetUploadCard`로 구현 완료(2026-06-26). 콘텐츠 슬롯·프로젝트 해결 후 카드가 채팅 안에 표시됨.
  - ⬜ **시뮬용 광고 이미지** — 아직 미구현. 시뮬 담당 등록(P2) 때 함께 설계 필요.
- **시뮬 → 생성(개선) 바통터치** — 시뮬 결과(요약 + 이미지 s3_key)를 생성 담당의 `improve_context`로 넘김. 생성 담당엔 개선모드가 이미 있음(slot_agent improve 분기). 시뮬 결과를 그 포맷으로 변환해 넘기는 연결만 필요.

### ✅ 결정된 사항

- **시뮬레이션은 광고 이미지가 필수.** 글(카피)만으로는 안 돌린다. 이미지 없으면 **무조건 되묻기(ASK "광고 이미지를 넣어주세요")**.
  - 이유: 그 광고 이미지가 시뮬의 입력이자 **개선모드의 참고자료**다. 시뮬 결과만으로는 개선 이미지를 못 만들고, 원본 이미지 + 시뮬 결과가 둘 다 있어야 개선이 가능.
  - 추가 설명: 사용자가 시뮬에 올린 **이미지 s3_key를 끝까지 보관**해, 개선 바통터치 때 `improve_context.s3_key`로 그대로 넘긴다(같은 이미지가 시뮬→개선 일관 추적).
- **개선 바통터치 = 자동 제안.** 시뮬 결과가 나오면 사용자가 안 물어도 채팅이 끝에 "개선할까요?"를 **먼저 띄운다**(AI 비서 선제성 원칙). 실행은 사용자가 수락할 때.
- **단계 순서 = P1 먼저.** 사용자 흐름(P2)이 작동하려면 라이브를 교통정리(오케스트레이터)에 연결하는 P1이 선행.

### 열린 질문 (결정 필요)

- 관리(management) 흐름은 사용자가 아직 로직 미파악 → 채팅 연결은 "이미 만들어진 관리 담당을 교통정리에 붙이기"만 하면 되므로 흐름 설계는 후순위.

## 🔀 "~~하고 싶어"가 담당에게 가는 길 (의도분류 → 디스패치)

사용자가 채팅에 "시뮬레이션 하고 싶어" / "광고 만들어줘" / "예산 얼마 남았어"처럼 쓰면, **어느 담당(에이전트)을 부를지**를 교통정리가 정한다. 핵심은 **LLM이 자유롭게 툴을 고르는 방식이 아니라, 의도를 한 번 분류한 뒤 사전 등록된 담당으로 곧장 넘기는 결정론 방식**이라는 점이다(단일 패스·G5).

흐름은 이렇다(`api/assistant/orchestrator.py` `run_turn`).

```
사용자 문장
   │
   ▼  ① 의도분류 classify_intent (intent.py)
   │     - 실모드: Gemini 1콜(구조화 출력) → GENERATE / MANAGE / ADVISE …
   │     - 폴백/테스트: 키워드 규칙(만들·생성→생성, 예산·성과·캠페인→관리)
   ▼  ② registry.get(intent) — 의도에 등록된 담당(handler) 꺼내기
   │     - 등록 없음(advise 등) → (intent, None) → 입구가 CLIO로 폴백
   ▼  ③ handler(req) 실행 — 그 담당이 ASK / TRIGGER / ANSWER 를 돌려줌
```

- **"툴을 부른다" = registry 디스패치.** intent별로 담당을 미리 등록(`wiring.build_assistant`)해 두고, 분류된 intent로 dict에서 꺼내 **한 번** 호출한다. LLM이 매번 어느 담당을 쓸지 추론·반복하지 않는다(예측가능·테스트가능).
- **분류 신호** — 실서비스는 Gemini가 분류(LangSmith 계측), 키 없거나 실패하면 키워드로 폴백해 **채팅을 끊지 않는다**. 키워드는 `generate`(만들·생성·시안…)를 먼저 보고, 그다음 `manage`(예산·성과·캠페인·ROAS…), 아니면 `advise`.
- **개선모드는 분류 생략** — `improve_context`가 실려 오면(시뮬→개선 바통터치) 의도분류를 건너뛰고 곧장 GENERATE로 간다.
- **현재 등록 상태** — GENERATE(생성)·MANAGE(관리)는 등록됨, **SIMULATE(시뮬)는 아직 미등록**(P2 빈 구멍). 그래서 "시뮬레이션 하고 싶어"는 지금은 시뮬 담당으로 안 가고 advise로 폴백된다 — 시뮬 키워드·등록을 추가하는 게 P2 과제.

## 현황 — 채팅 경로 (2026-06-26 기준 고도화 진행 중)

1. **라이브 엔드포인트** `api/routers/chat.py` `/complete` — 프론트가 실제로 부르는 곳.
   - 관리 키워드 → 관리 에이전트(멀티턴·HITL 유지), 그 외 → 오케스트레이터(생성 슬롯필링) → CLIO 폴백.
   - 관리 경로가 갖춘 것: `thread_id = f"mgmt-{session_id}"`(멀티턴 메모리·checkpointer), `record_turn`(DB 적재), 메타에 `requires_approval`·`thread_id`(HITL 승인 게이트).

2. **오케스트레이터** `api/assistant/` — intent 분류 → registry 디스패치(단일 패스, G5 루프 없음).
   - 계약: `core/assistant_contracts.py` — Intent(GENERATE/SIMULATE/MANAGE/RETRIEVE/ADVISE), Action(ASK/TRIGGER/ANSWER), SubagentRequest/Result, StartedEvent.
   - `wiring.build_assistant()`가 GENERATE(슬롯필링)+MANAGE(에이전틱 RAG) 등록. **라이브가 오케스트레이터를 호출하도록 연결 완료.**

## ⚠️ 함정 — 관리 패리티 회귀

오케스트레이터의 `wiring._build_management_handler`는 라이브 `chat.py` 관리 경로보다 **단순**하다.
- 빠진 것: `thread_id`(멀티턴), `record_turn`(DB 적재), latency 측정.
- 그냥 갈아끼우면 **관리 채팅의 멀티턴 메모리·로깅·HITL 메타가 사라진다.** P1에서 반드시 보존.

## 액션별 SSE 매핑 (전송계층 책임)

- `result is None`(ADVISE/미등록) → 기존 **CLIO(Gemini) 스트리밍** 폴백.
- `ANSWER` → meta + message 청크 스트리밍(관리 RAG 즉답). 관리면 record_turn.
- `ASK` → message를 질문으로 스트리밍(되묻기, 잡 없음).
- `TRIGGER` → meta + `started_event`(stream_url) 방출 → 프론트가 그 SSE를 구독. message는 "시작했어요" 확인.

## 서브에이전트 출력 모양 (확인됨)

- 생성: `domain/generator/chat/slot_agent.py` — 부족=ASK(되묻기), 이미지 없음=ASK(needs_assets 카드), 충족=TRIGGER + StartedEvent(`/api/generator/generations/{id}/stream`, domain=generator). 개선모드는 improve_context로 직행. **5개 전략 기반 시안 3개 생성·순위.**
- 관리: `domain/management/assistant/agent.py` `build_management_agent` → AskRequest(question, ad_id, thread_id) → answer/citations/used_tools/suggested_action/requires_approval/thread_id.

## ✅ 완료 — generator 채팅 고도화 (2026-06-26)

### 해결된 문제
- **키워드 버그** — `_MGMT_KEYWORDS`에 `"광고"`가 있어 "광고 만들어줘"가 관리로 새던 문제 → **제거 완료**.
- **JWT 연결** — `chat_complete`에 `optional_user` 의존성 추가. 로그인 사용자는 `user_id`가 `SubagentRequest`에 실려 들어감. "로그인 후 사용해주세요" 메시지 미노출.
- **project_provider 연결** — `_get_user_projects` 함수 추가 후 `run_turn`에 주입. 슬롯 충족 시 사용자 프로젝트 목록 자동 조회 → "어느 프로젝트에 저장할까요?" 되묻기 활성화.
- **이미지 키 전달 경로** — `ChatRequest` / `SubagentRequest`에 `product_image_temp_key` · `brand_logo_s3_key` 추가. `slot_agent`가 생성 트리거 시 이미지 키를 `GenerationCreateRequest`에 주입.
- **생성 이미지 인라인 카드** — 우측 상시 노출 패널 제거, 채팅 흐름 안에 `AssetUploadCard` 인라인 표시. `slot_agent`가 `needs_assets: true` 신호를 `meta`에 포함해 반환하면 프론트가 카드를 렌더링. "이미지 없이 진행" 선택 시 `skip_asset_prompt: bool` 필드로 재요청(세션 내 유지).

### 생성 이미지 모드 결정 방식
- `GenerationMode`는 `CREATE` / `IMPROVE` 두 가지만 존재 ("컴포즈 모드"는 별도 모드가 아님).
- 상품 이미지(`product_image_temp_key`) 유무로 파이프라인 내부 경로가 자동 분기:
  - **있음** → 누끼 제거 + 상품 배치(compose 경로) — `image_generator.py`가 처리.
  - **없음** → 일반 CREATE 경로.
- **인라인 카드 업로드 흐름 (2026-06-26 변경):**
  1. 사용자가 생성 요청 → 슬롯 채우기 → 프로젝트 해결.
  2. `slot_agent`가 로고 키 없으면 `Action.ASK` + `meta.needs_assets: true` 반환.
  3. 프론트가 `AssetUploadCard`를 채팅 메시지 아래 인라인으로 표시.
  4. "생성 시작" 클릭(로고 업로드 후) → 키 포함해 재요청 → TRIGGER.
  5. "이미지 없이 진행" 클릭 → `skip_asset_prompt: true` 포함 재요청 → `slot_agent`가 카드 단계 건너뜀 → TRIGGER.
- **주의**: `skip_asset_prompt`는 세션 내 유지(`skipAssets` state). 한 번 건너뛰면 같은 세션에서 다시 묻지 않음.
- 업로드 엔드포인트: `POST /api/generator/product-image` → `temp_key`, `POST /api/generator/logo` → `s3_key`.

## 빈 구멍 — SIMULATE (P2)

- registry에 SIMULATE 미등록, intent.py에 시뮬 키워드·LLM 설명 없음.
- 시뮬은 롱러닝 잡 → TRIGGER + StartedEvent(stream_url) 패턴(생성과 동일).

## 스트림 엔드포인트 (핸드오프 타깃)

- 생성: `GET /api/generator/generations/{generation_id}/stream` (SSE, `generator_service.stream_events`).
- 시뮬: P2에서 동일 패턴 엔드포인트 필요(있으면 재사용, 없으면 추가).

## 참조 파일

- 오케스트레이터: `api/assistant/{orchestrator,intent,registry,wiring,contracts}.py`
- 계약 정본: `core/assistant_contracts.py`
- 라이브 라우터: `api/routers/chat.py`
- 생성 챗: `domain/generator/chat/slot_agent.py`, `agent.py`
- 관리 챗: `domain/management/assistant/{agent,history}.py`

## 📖 용어 사전 (팀 공유용)

> 위 본문에 나오는 줄임말·약어 풀이. 처음 보는 용어가 있으면 여기서 찾으세요.

### 구조·역할

- **오케스트레이터 / 교통정리** — 채팅 한 턴을 받아 "어느 담당(생성·시뮬·관리)에게 넘길지"만 정하는 상위 라우터. `api/assistant/`. 직접 답을 만들지 않고 분류·전달만 한다.
- **서브에이전트 / 담당** — 실제 일을 하는 도메인별 에이전트(생성 담당·시뮬 담당·관리 담당). 오케스트레이터가 호출한다.
- **registry 디스패치** — intent(의도)별로 어느 서브에이전트를 부를지 미리 등록(registry)해 두고, 들어온 intent에 맞춰 한 번 호출하는 방식. dict로 분기한다고 보면 된다.
- **CLIO** — 채팅 AI 어드바이저의 이름(페르소나). Gemini 기반 일반 상담 응답을 가리킨다. 특정 담당으로 라우팅되지 않는 일반 질문은 CLIO가 받는다.
- **선제성 (proactive)** — 사용자가 지시하기 전에 다음 단계를 먼저 제안하는 성질("AI 비서"의 핵심).

### 동작 흐름·이벤트

- **Intent (의도)** — 사용자 요청의 종류. `GENERATE`(생성)/`SIMULATE`(시뮬)/`MANAGE`(관리)/`RETRIEVE`(조회)/`ADVISE`(일반 상담). 오케스트레이터가 이걸 분류한다.
- **Action** — 서브에이전트가 돌려주는 응답 유형. `ASK`(되묻기 — 정보 부족) / `TRIGGER`(작업 시작 — 롱러닝 잡 개시) / `ANSWER`(즉답).
- **단일 패스 (single pass)** — 오케스트레이터가 1턴에 딱 한 번만 판단하고 끝내는 구조(반복 루프 없음).
- **G5 / G5 루프** — 오케스트레이터 설계 목표 5번 = **"예측가능·테스트가능"**(`docs/generator/chat-orchestrator-spec.our-fit.md`). "최상위 라우팅은 결정론, 깊은 추론은 도메인 안에서". 따라서 "G5 루프 없음" = G5 원칙대로 **최상위에는 자율 루프를 두지 않는다**는 뜻. 루프는 서브에이전트 안에만 둔다.
- **폴백 (fallback)** — 라우팅 실패·미등록 등으로 전담 처리가 안 될 때 대신 타는 기본 경로. 여기서는 CLIO(Gemini) 스트리밍.
- **바통터치** — 한 담당의 결과를 다음 담당에게 넘기는 인계(예: 시뮬 결과 → 생성 개선모드).
- **HITL (Human In The Loop)** — AI가 작업을 수행하는 도중 사람이 개입해 검토·수정·승인하는 프로세스. AI 오류를 방지하고 신뢰성을 높이는 안전장치. 여기서는 관리 담당의 위험 조치(예산 변경·일시정지 등)에 적용되며, 사용자가 승인하기 전까지 실행을 보류한다.

### 기술·전송

- **멀티턴 (Multi-turn)** — 사용자와 AI가 여러 번 질문과 답변을 주고받으며 이전 대화의 맥락(Context)을 기억하고 연속으로 소통하는 방식. 관리 채팅이 `thread_id`·`checkpointer`로 이를 구현한다.
- **로깅 (Logging)** — 시스템 실행 과정, 오류, 사용자 행동을 파일이나 DB에 시간순으로 저장하는 작업. 디버깅·데이터 분석에 활용된다. 여기서는 `record_turn`이 대화 한 턴을 DB에 적재하는 것을 가리킨다.
- **SSE (Server-Sent Events)** — 서버가 클라이언트로 데이터를 한 방향으로 흘려보내는 스트리밍 방식. 채팅 토큰·로딩 진행을 실시간 전송할 때 쓴다.
- **StartedEvent / started_event / stream_url** — TRIGGER로 롱러닝 잡을 시작했을 때 방출하는 이벤트. 그 잡의 진행을 구독할 SSE 주소(`stream_url`)를 담아 프론트에 넘긴다.
- **잡 (job)** — 시간이 걸리는 백그라운드 작업(이미지 생성·시뮬레이션 등). "롱러닝 잡"은 즉답이 안 되는 오래 걸리는 작업.
- **슬롯필링 (slot filling)** — 작업에 필요한 정보(슬롯)를 하나씩 되물어 채우고, 다 차면 작업을 시작하는 결정론 방식. 생성·시뮬 담당이 쓴다.
- **에이전틱 RAG** — 검색(RAG)에 더해 LLM이 스스로 도구를 반복 호출하며 추론하는 자율 에이전트. 관리 담당이 이 방식(자율 루프).
- **thread_id / checkpointer** — 멀티턴 구현의 기술 수단. `thread_id`는 같은 대화 세션을 식별하는 키, `checkpointer`는 그 맥락을 저장하는 상태 저장소. 관리 채팅이 이전 대화를 기억하는 근거.
- **record_turn** — 대화 한 턴(질문·답변·도구·인용)을 DB에 적재하는 로깅 처리. 관리 경로에만 적용.
- **improve_context** — 시뮬 결과(요약 + 원본 이미지 `s3_key`)를 생성 개선모드로 넘길 때 담는 컨텍스트.
- **s3_key** — AWS S3에 저장된 이미지의 키(경로). 같은 이미지를 시뮬→개선까지 일관 추적하는 데 쓴다.
- **latency** — 응답에 걸린 시간(지연). 관리 경로가 측정하던 지표 중 하나.

### 주의어

- **패리티 회귀 (parity regression)** — 기능을 갈아끼우면서 **기존 기능이 누락돼 후퇴**하는 것. 여기서는 오케스트레이터로 바꿀 때 관리 채팅의 멀티턴·로깅·HITL 메타가 사라지는 위험.