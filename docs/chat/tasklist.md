# 채팅(4-4) 작업 태스크리스트 — 2026-06-24

> 브랜치 `feat/chat-doyeon`. 정본 설계 `docs/chat/architecture.md`, 직전 인계 `docs/chat/handoff-2026-06-24.md`.
> 이 문서는 **루프로 순차 진행**할 태스크 목록 + 각 태스크 명세 + 루프 프롬프트다.
> 새 세션에서 `/loop` 돌릴 때 이 파일을 읽고 상태 ⬜ 인 맨 위 태스크 하나를 완료 기준까지 끝내고 체크박스를 ✅ 로 갱신·커밋한다.

---

## 0. 전제 (세션 최초 1회만 — 통과하면 이후 반복은 생략)

> ★ 아래는 **루프 첫 반복에서 한 번만** 확인한다. DB·서버·폰트·로그인이 한 번 정상이면 그 상태가 세션 내내 유지되므로 **매 반복 재확인하지 않는다**(서버·Preview·로그인 세션 재사용). 중간에 실제로 깨졌을 때만(서버 다운·500·토큰 만료) 재확인한다.

- **DB는 개인 NeonDB** (`ep-soft-band-…`). 확인:
  `cd backend && uv run python -c "from core.config import settings;import re;print(re.search(r'@([^/]+)/',settings.database_url).group(1))"`
  → `ep-soft-band-…` 아니면 작업 중단하고 `.env` 고친다. (`ep-spring-wind-…` = 팀 DB, 금지)
- 백엔드 `cd backend && uv run dev.py`
- 프론트 `cd frontend && pnpm dev` (포트 3000 — CORS 3000만 허용)
- **폰트** `frontend/src/app/fonts/NotoSansKR-*.otf` 5종 없으면 프론트가 컴파일 실패(500). `.gitignore`로 빠져 있어 각자 로컬에 둬야 함.
- 백엔드 .py 수정 후 커밋 전: `cd backend && uv run ruff format . && uv run ruff check . --fix`
- 프론트 검증: `npx tsc --noEmit` + 변경 파일 `npx next lint --file <파일>`
- **테스트 계정(역할 3종)** — `/sign-in`에서 ID/PW로 로그인해 검증. ⚠️ 개인 DB 전용 테스트 계정(평문, 운영 반영 금지).

  | 역할 | ID | PW |
  | --- | --- | --- |
  | 어드민(ADMIN) | `admin` | `admin1234` |
  | 컴퍼니(COMPANY) | `yohan` | `yohan1234` |
  | 유저(USER) | `doyeon` | `fjdksla0852` |

  - USER `doyeon`에 프로젝트 `건도연`(id `8b33546d-e763-44fb-a222-6f02ba9a6707`) 있음.
- **★ 검증은 무조건 3계정(admin·company·user) 모두에서 돌린다.** 역할 게이팅(admin `/api/admin/*`·`/admin/*` 화면, company 조직 화면, user 일반)이 다르므로, UI/흐름 변경은 세 역할에서 각각 재현·캡처한다. 역할별로 다르면 진행 로그에 역할 표기.
- **토큰 주입(대안)**: 로그인 대신 토큰이 필요하면 `cd backend && uv run python -c "from core.auth import create_access_token; print(create_access_token('<user_id>','<ROLE>'))"` → `preview_eval`로 `localStorage.setItem('clickme_token','<토큰>')`. (doyeon id는 위 표/프로젝트 참고.)
- **검증은 Claude Preview로 브라우저를 직접 몰아서** 한다(스크린샷·콘솔·네트워크 확인). 사람 클릭에 의존하지 않는다.
- **Preview 검증 표준 절차(무인 루프 공용)**:
  1. `preview_start`로 `http://localhost:3000` 띄움(이미 떠 있으면 재사용).
  2. **로그인** — `/sign-in`에서 위 3계정 중 해당 역할로 `preview_fill`+`preview_click` 로그인(또는 토큰 주입 대안). UI/흐름 변경 검증은 **admin·company·user 3역할 각각 반복**.
  3. 흐름 조작은 `preview_click`/`preview_fill`, 상태 확인은 `preview_screenshot`·`preview_console_logs`·`preview_network`.
  4. 실패/에러는 콘솔·네트워크(`/api/*`)·백엔드 로그를 함께 캡처해 "5. 진행 로그"에 근거로 남긴다(역할별로 다르면 역할 표기).
- **★ QA 철저성 원칙(진짜 QA처럼 — "떴다"로 끝내지 말 것)**:
  - **비동기는 끝까지 기다린다.** 스피너가 돌면 완료까지 폴링·재요청하며 본다. 시뮬/제너는 완료까지(수십 초) 기다려 결과 위젯·KPI·후보 이미지가 실제로 나오는지 확인. "스피너 떴음"만으로 ✅ 금지.
  - **진행 중 상태도 직접 본다.** 실행 중에 **새로고침**해서 스피너/진행률이 복원되는지, 완료 후 새로고침해서 결과 위젯이 복원되는지 둘 다 캡처.
  - **영속성 확인.** 새로고침·세션 재진입 후에도 메시지/위젯/결과가 남는지.
  - **엣지·에러 유발.** 빈 입력·필수 누락·동시 실행·키 없음/한도·네트워크 끊김을 실제로 만들어 에러 카드·재시도가 도는지.
  - **다중 탭/표면.** 다른 탭/페이지에서 시작한 작업이 채팅에 반영되는지(N3 관련).
  - **콘솔 무에러.** 흐름 내내 `preview_console_logs`에 에러/경고 없는지 확인(있으면 그 자리에서 고침).
  - 위를 **3역할 각각** 반복. 체크리스트의 모든 항목을 실제로 재현한 뒤에만 ✅.
- 임베딩/생성은 OpenAI 키 필요(`OPENAI_API_KEY`). RAG 적재는 `text-embedding-3-small` 호출(비용 미미).

---

## 1. 전체 태스크 현황

> 권장 순서: **검증(V) → 위젯(W) → 제너통일(G) → 슬래시(S) → 폴리시(P) → 능동(N) → 견고함(X) → 랭스미스(L) → 기능(F) → RAG(R) → 정리(C)**.
> **S1(저비용 슬래시 4종)은 최우선 후보** — 위젯은 완성됐는데 진입점만 없어서, 슬래시 한 줄로 묻힌 기능이 살아남(프론트만, 백엔드 변경 거의 없음).
> 검증으로 머지 후 상태를 먼저 확정 → 핵심 위젯/통일로 흐름 완성 → **눈에 띄는 폴리시(P)로 "빛나게"** → 견고함 → 기능 → 정리. **랭스미스(L)·RAG(R)는 백엔드 세션에서 완료됨**(머지 반영, §5 학원 완료분 참조).
> 설계 원칙: **시뮬과 제너레이터를 같은 UX로** 간다 — 입력 위젯 → (입력 시 사라지고) 입력 확인 위젯 → 로딩 스피너 위젯 → 결과 요약 위젯, 그리고 status API로 새로고침에도 안 날아가게.
> **랭스미스(L) 작업 정본은 팀 기준 문서 `C:\Users\owner\Downloads\langsmith-guide.md`(ClickMe 팀 공통)** — Trace 이름·Node 이름·필수 Metadata/Tags·비용 기록 규칙. (L 전부 완료, 추가 트레이싱 시 참고.)
> 남은 ⬜는 임팩트 큰 것(V·G·P·F)부터 소진. 외부 블로커(제너 403)·타 팀 조율(S2·S5)은 ⬜로 유지.

> 완료(✅)분은 표에서 제거함 — 상세 명세·진행 로그는 git 로그 참조. 아래는 **남은 작업 + 그 의존(완료, dep 표기) + 새 작업(★)** 만 남긴다.

| #   | 태스크                                   | 분류   | 의존      | 상태 |
| --- | ---------------------------------------- | ------ | --------- | ---- |
| V1  | 시뮬 전체 흐름 검증 (dep)                | 검증   | —         | ✅   |
| V2  | 제너 직접 경로 검증 (dep)                | 검증   | —         | ✅   |
| S1  | 저비용 슬래시 4종 (dep)                  | 슬래시 | —         | ✅   |
| N1  | 직접 실행 완료→자동 개선 제안 (dep, 제너 경로 잔여) | 능동 | V1,V2 | ✅(시뮬)·⬜(제너) |
| N2  | 안읽음 빨간 뱃지 (dep)                   | 능동   | N1        | ✅   |
| G3  | 제너 결과 위젯(가로 이미지) (dep)        | 제너   | —         | ✅   |
| F5  | 랭체인 롱텀 메모리 (dep)                 | 기능   | —         | ✅   |
| L8  | 롱텀 메모리(실행기록 프로파일) (dep)     | 메모리 | —         | ✅   |
| ★N5 | 라우트 변경마다 알림 폴링 + 플로팅 챗 벨 버튼·알림 패널 | 능동 | N2 | ⬜ |
| ★N6 | 제너 전용 세션에 시뮬 선제 알림 오는 버그 수정 | 능동 | N4 | ⬜ |
| ★F13 | 채팅 세션 자동 제목(첫 user 메시지 LLM 요약) | 기능 | —      | ⬜   |
| ★G5 | 제너 필수 입력값 확실히 받기·검증(누락 차단·안내) | 제너 | V2 | ⬜ |
| ★G6 | /new 생성 직후 gen_form 재노출 라이브 글리치 수정 | 제너 | G3 | ⬜ |
| ★L9 | 롱텀 메모리(시뮬/제너 입력 기억→채팅 반영) 검증 | 검증 | F5,L8 | ⬜ |
| ★LOOP | 시뮬↔제너 양방향 개선 루프(최대 3턴) 구현·검증 | 핵심 | V2 | ⬜ |
| ★A1 | 인증·인가 일관 적용(chat/gen/sim/personas 라우트 소유권 검증) | 보안 | — | ⬜ |
| ★G7 | 제너 시안 5개+기대성과 순위(기획서 정합 — 현재 3개·순위 미흡) | 제너 | V2 | ⬜ |
| ★G8 | 상품 이미지 첨부 기반 생성 검증·연결(이미지 픽셀 잠금) | 제너 | V2 | ⬜ |
| ★V6 | PDF 리포트 생성 end-to-end 검증(Playwright) | 검증 | — | ⬜ |
| ★V7 | 동시실행 가드(sim·gen 슬롯) 검증 | 검증 | — | ⬜ |
| G1  | 제너 입력 확인 위젯(입력 위젯 교체)      | 제너   | V2        | ⬜   |
| G2  | 제너 로딩 스피너 위젯                    | 제너   | G1        | ⬜   |
| G4  | 제너 status API + 새로고침 복원          | 제너   | V2        | ⬜   |
| F8  | 시안 후보 선택 → 재시뮬(LOOP 일부)       | 기능   | V2,G3     | ⬜   |
| V3  | 개선 루프 경로 검증(LOOP 완료 후)        | 검증   | LOOP      | ⬜   |
| N3  | 채팅이 sim/gen status 동기화(타 탭)      | 능동   | G4        | ⬜   |
| N4  | 선제적 말걸기(제너 경로 잔여)            | 능동   | N1,N2     | ✅(시뮬)·⬜(제너) |
| S2  | /비교 캠페인 A/B (매니지 조율 — 보류)    | 슬래시 | S1        | ⬜   |
| S5  | /액션 매니지 조치 확장(매니지 조율 — 보류) | 슬래시 | —        | ⬜   |
| C4  | 전수 QA 후 push                          | 정리   | 전부      | ⬜   |

> **상태 메모(2026-06-25)** — 제너 403 **해소됨**(org 인증 완료, image_generation gpt-4o-mini/gpt-image-1 실호출 OK). V2 검증 완료. 워크트리(kb·be·fe) 통합 완료. 브랜치 `feat/chat-doyeon`.

---

## 1-A. 새 작업 명세 (★ — 집에서 진행)

### ★N5 — 라우트 변경마다 알림 폴링 + 플로팅 챗 벨 버튼·알림 패널

**목표** 마운트/언마운트에 의존하지 말고 **라우트가 바뀔 때마다** 해당 사용자(프로젝트)의 미확인 채팅 알림을 받아와 배지로 표시. `/chat` 탭은 프로젝트>세션 배지, **플로팅 챗봇은 좌측에 작은 벨 버튼**을 두고 배지를 띄운다.
**확정 방향(가장 사용자 친화 — 내 결정)** 플로팅 챗 벨은 **세션 선택기가 아니라 "알림 목록 패널"**. 벨 클릭 → 미확인 알림 리스트(프로젝트 › 세션 제목 › 미리보기 › 개수) → 항목 클릭 시 **해당 세션으로 이동(+읽음 처리)**. (세션을 직접 고르게 하지 않고, 알림을 보여주고 클릭으로 라우팅 — 가장 직관적.)
**구현**
- 백엔드: 세션별 미확인(마지막 열람 이후 새 메시지/선제 알림) 집계 — 예 `GET /api/chat/notifications?project_id=…` → `[{session_id, title, preview, unread_count}]`. last-read는 세션별로 저장(localStorage가 아닌 서버, 라우트·기기 무관 일관 위해).
- 프론트: `usePathname()` 변경 시 폴링하는 훅(언마운트 무관). 배지: `/chat`은 사이드바 세션 행, 플로팅은 벨 버튼. 벨 클릭 → 드롭다운 패널 → 항목 클릭 → `router.push('/chat/{pid}/{sid}')` + 읽음.
**완료 기준** 라우트 이동마다 미확인 알림 반영, 플로팅 벨 배지·패널→세션 이동·읽음 동작. (N6도 함께 해소될 수 있음 — 인라인 주입 대신 벨/배지 모델.)

### ★N6 — 제너 전용 세션에 시뮬 선제 알림 오는 버그 수정

**증상** 제너레이터만 돌린 채팅 세션인데 "확인하지 않은 시뮬레이션 결과가 있다"는 **선제 알림이 현재 열린 세션에 인라인 주입**됨(N4가 프로젝트 전체 미열람 시뮬을 현재 활성 세션에 주입하는 구조 잔재).
**방향** N5의 벨/배지 모델로 전환하면 "현재 세션에 무관한 시뮬 알림 인라인 주입"이 사라져 근본 해소. 독립 처리 시: 선제 시뮬 알림을 현재 세션 도메인과 무관하게 주입하지 않도록(또는 벨로만 노출) 가드.
**완료 기준** 제너 전용 세션에서 시뮬 선제 알림이 본문에 안 뜸. (N5와 연계.)

### ★F13 — 채팅 세션 자동 제목 (첫 user 메시지 LLM 요약)

**증상** 빈 화면 칩으로 새 채팅 열면 제목이 `새 채팅`이거나 첫 입력값이 그대로 제목이 됨.
**목표** 여느 LLM처럼 **첫 user 메시지를 보고 작업을 짧게 요약한 제목**을 생성(예: "수분크림 광고 시안 생성", "20대 타깃 시뮬 분석").
**구현** 세션의 첫 user 턴 직후(또는 첫 응답 후) gpt-4o-mini로 한 줄 제목 생성 → `ChatSession.title` 갱신(append-only, 한 번만). 위젯 트리거(시뮬/제너 폼)로 시작한 세션도 첫 의미 있는 입력 기준으로.
**완료 기준** 새 세션 제목이 첫 작업을 요약한 자연어로 자동 설정, 사이드바 반영.

### ★G5 — 제너 필수 입력값 확실히 받기·검증

**목표** 제너레이터가 **필수 입력값**(상품명·상품설명·타깃·저장 프로젝트 등)을 누락 없이 받아 실행되게. 누락 시 실행 차단 + 명확한 안내.
**구현** gen_form 필수 필드 검증(빈 값이면 "실행" 비활성·안내), 백엔드 `GenerationCreateRequest` 필수값 검증·422 메시지 정합. 어떤 값이 필수인지 폼·백엔드 일치.
**완료 기준** 필수 누락 시 실행 불가·안내, 모두 채우면 정상 생성. 빈 입력 엣지 케이스 Preview 확인.

### ★G6 — /new 생성 직후 gen_form 재노출 라이브 글리치 수정

**증상** `/new`에서 제너 **생성 직후(새로고침 전)** gen_form이 빈 폼(1/4)으로 잠깐 다시 보이고 gen_result 이미지 로딩이 지연됨. 새로고침하면 정상.
**원인 추정** 세션 생성 전환(shallow routing) 중 로컬 gen_form 위젯 재마운트 + gen_result가 아직 숨김 처리 전. (sim은 매끄러운데 gen 경로 차이 확인 필요.)
**완료 기준** 생성 직후 라이브로 gen_result 위젯이 자리에 표시되고 gen_form이 깜빡이지 않음(새로고침 불필요).

### ★L9 — 롱텀 메모리(시뮬/제너 입력 기억 → 채팅 반영) 검증

**배경** F5(롱텀 메모리)·L8(실행기록 기반 프로파일 추론)은 구현 완료(✅). 본 태스크는 **검증만**.
**목표** 사용자가 시뮬/제너를 돌릴 때 입력한 값(상품명·카테고리·타깃·브랜드 등)이 기억돼 다음 채팅 질을 올리는지 end-to-end 확인. LangGraph 체크포인터·`ChatLongTermMemory`·`ChatBrandProfile`·`infer_profile_from_execution_history` 경로가 실제로 채팅 컨텍스트에 주입되는지.
**완료 기준** 시뮬/제너 수 회 실행 후, **명시 언급 없이도** 채팅이 사용자의 브랜드·제품군·과거 입력을 인지한 응답. (안 되면 끊긴 지점 수정 — 그 경우 검증→구현 태스크로 승격.)

### ★LOOP — 시뮬 ↔ 제너 양방향 개선 루프 (최대 3턴)

**목표** 두 방향 개선 루프를 확실히 연결하고 **최대 3턴**으로 제한.
- **시뮬 → 제너(개선)**: 시뮬→토론→개선권고 → "개선 시안 만들기"로 제너(개선 모드)에 컨텍스트 전달.
- **제너(생성) → 시뮬**: 생성 결과(또는 F8 "이 후보로 시뮬") → 재시뮬 → 토론 → 다시 개선 제너 → … 최대 3턴.
**현황** 오케스트레이터에 `loop_count`·`MAX_LOOP`·`gen_result_node`(재시뮬 approval)·`run_generator`/`rerun_simulation` approval 경로 일부 존재. 양방향 연결·3턴 한도 enforce·UX 매끄러움을 완성·검증.
**완료 기준** 시뮬↔제너를 오가며 개선이 누적되고, 3턴 도달 시 더 이상 루프 제안 안 함(차단·안내). Preview로 왕복 검증. (V3 = 이 루프의 최종 검증, F8 = 제너→시뮬 진입점.)

### ★A1 — 인증·인가 일관 적용 (보안, 우선)

**증상** 라우트마다 인증이 들쭉날쭉. `projects.py`는 `get_current_user`+`_project_access_ok`(org/team/생성자) 소유권 검증이 있으나, **`chat.py`·`generator.py`·`api/routers/simulation/*`·`personas.py`는 인증·스코핑이 전혀 없음**(`Depends(get_db)`만). 즉 `GET /chat/sessions?project_id=…`·`/chat/sessions/{id}/messages`·생성/시뮬 조회·삭제가 **토큰 없이/타인 ID 추측으로 접근 가능**. (CLAUDE.md "JWT 미적용·점진 도입"의 실체 — 보안 구멍.)
**목표** projects 패턴을 chat/generator/simulation/personas에 일관 적용 — `get_current_user` 의존 + 해당 리소스(세션·생성·시뮬)의 프로젝트 소유권 검증(같은 org/team/생성자만). 또는 전역 인증 미들웨어 + 라우트별 인가.
**완료 기준** 비인증 요청 401, 타 프로젝트 리소스 403. 3역할 정상 흐름 회귀(자기 데이터는 그대로). (범위가 크면 chat부터 단계 적용.)

### ★G7 — 제너 시안 5개 + 기대성과 순위 (기획서 정합)

**증상** 기획서(CLAUDE.md)는 **개선 시안 5개 자동생성 + 기대성과 순위**인데, 코드는 **후보 3개**(`copy_generator.py:115`·`explain.py` "후보 3개")이고 순위 로직이 약함.
**목표** 후보 개수를 기획서대로(5개) 또는 사용자 확정 개수로 맞추고, **기대성과 순위**(예: 예측 반응·QA 기반 정렬·근거) 부여. 비용·시간(이미지 5장) 고려해 개수는 설정값으로.
**완료 기준** N개 시안 생성 + 순위/근거 표시(결과 위젯·상세). 개수 설정화. (개수만 늘릴지, 랭킹 로직까지 강화할지 범위 합의.)

### ★G8 — 상품 이미지 첨부 기반 생성 검증·연결

**목표** 채팅 gen_form에 **상품 이미지 첨부 시** 그 이미지를 기반으로(상품 픽셀 잠금 인페인팅 — `image_providers.py`에 edit/mask 존재) 생성되는지 검증·미연결 시 연결. V2에서 미검증으로 남긴 항목.
**완료 기준** 이미지 첨부→생성 시 상품 이미지가 반영된 시안. 미첨부와 결과 차이 확인.

### ★V6 — PDF 리포트 생성 end-to-end 검증

**목표** 시뮬/토론 결과의 **PDF 리포트**(백엔드 Playwright Chromium, `debate.py:161 /report.pdf`)가 끝까지 생성·다운로드되는지 검증(콜드·새로고침 진입의 saved report 폴백 포함). `/리포트`·report_ready 위젯 경로.
**완료 기준** 리포트 다운로드 → 유효 PDF(내용·KPI·근거). 콜드 진입에서도 saved report로 재조립.

### ★V7 — 동시실행 가드(sim·gen 슬롯) 검증

**목표** sim/gen 동시 실행 시도 시 차단·안내(`runningJobs` 슬롯)가 실제 동작하는지, 완료/에러 후 슬롯 해제되는지 검증. V2 미검증 항목.
**완료 기준** 진행 중 같은/다른 작업 동시 시도 차단, 완료·에러 시 정상 해제.

### 🔎 검토 필요 (보류 후보 — 의도 확인 후 태스크화)

> 코드 점검에서 드러난 더 큰/의도적일 수 있는 갭. 발표 범위·우선순위 확인 후 태스크로 승격할지 결정.

- **매니지먼트(4-2) 실연동** — `domain/management/wiring.py` `use_mock=True` 기본 → MockAdPlatform(reader)·DRY_RUN writer(실쓰기 없음). 즉 매니지먼트는 **데모 모드**. 실 Meta Ads API 연동(A-1)은 stub. 발표를 데모로 갈지, 실연동까지 갈지 확인.
- **시뮬 인구 데이터 grounding** — `simulation/data/loader.py` 인구·사회경제 분포가 **placeholder**(실 통계 미확보, `data_status()`로 투명 표기 중). KPI 신뢰도 위해 실 통계 수집 또는 리포트 표기 강화.
- **A/B 테스트 + YouTube RAG** — 기획서상 "UI 선반영, 실기능 최종 단계". YouTube RAG 실기능 미구현.
- **CD/배포** — `cd.yml` 틀만, `docker-build` ⏸(Secrets), EC2 배포 미진행.

---

## 2. 진행 메모

> 제너 403 해소·워크트리 통합 완료. `feat/chat-doyeon` 단일 브랜치. 권장 착수 순서(집): **G5(필수입력)·G6(글리치) → LOOP → F13(제목) → N5/N6(알림) → L9(검증) → G1·G2·G4·N3 → C4**. S2·S5는 매니지 조율로 보류.

### 2-1. 루프 프롬프트 (집에서 — 복붙)

```
/loop docs/chat/tasklist.md 를 읽어. 단일 브랜치(feat/chat-doyeon)에서 남은 ⬜를 끝까지 진행한다. 제너 403 해소됨(image_generation 실호출 OK). 매 반복:
1) 전제는 최초 1회만 — 개인 DB(ep-soft-band)·서버(8000/3000)·폰트·OPENAI_API_KEY·Preview 로그인. 통과 후 생략.
2) §1 표에서 의존 충족·⬜인 가장 위 1개. 권장 순서: G5→G6→LOOP→F13→N5→N6→L9→G1→G2→G4→F8→V3→N3→C4. S2·S5는 매니지 조율이라 건너뛴다. 명세는 §1-A(새 작업 ★)·§4(기존).
3) 끝까지 구현. 코드 변경 시 ruff/tsc/lint 통과. **검증은 "떴다"로 끝내지 말 것** — Claude Preview 직접 구동 + 바닥 사실 확인(DB 직접 조회·새로고침 복원·엣지/에러 유발·콘솔 무에러), admin·company·user 3역할 재현. 무엇을 검증했고 무엇은 안 했는지 명시.
- 제너는 이미지 생성이라 ~1~2분·비용 실호출 — 완료까지 대기, 불필요한 반복 자제.
- 버그 발견하면 그 자리에서 고치고 커밋. 완료 시 ✅ + 시맨틱 커밋(타입: 한국어).
- 한 반복 1태스크. 공유부(core/ 기존 컬럼·api/main.py·공용 tools/)는 append-only·시그니처 불변. push는 도연님 요청 시에만(main·--force 금지).
```

### 2-2. 보류 (타 팀 조율)

- **S2·S5** — 매니지먼트 도메인 조율 필요(타 팀 소유부). 채팅 측 라우팅·위젯 범위로만 가능, 내부 비교/조치 로직은 합의 후. 단독 진행 X.

---

## 3. 환경·아키텍처 메모 (조사 결과)

### RAG 적재 구조 (R1~R3 공통)

- 테이블: `simulation_kb_chunks` · `generator_kb_chunks` · `management_kb_chunks`(+부모 `management_kb_documents`). 컬럼 `source/title/chunk/embedding(vector 1536)/created_at`. 매니지는 메타(`document_id·tenant_id·chunk_index·heading_path·content_hash·embedding_model·embedding_dimensions`) 추가.
- **적재 = raw INSERT 아님.** 각 도메인 `backend/domain/<d>/assistant/kb/*.md`에 지식을 **`## 섹션`** 단위로 작성 → ingest 모듈이 섹션 1개=청크 1개로 임베딩 후 적재. **소스 파일명 기준 멱등**(재실행 시 같은 source 삭제 후 재적재).
- **R1~R3 내용 형식 = "용어 + 정의" 사전.** 각 항목 = `## 용어`(헤딩) + 1~2줄 정의(설명 포함, 단어 나열 ❌). 예: `## 클릭 의향률` → "AISAS Action 단계를 통과한 비율. 신뢰구간으로 표기하며 실측 CTR로 환산하지 않는다." **단어만 넣으면 RAG가 꺼내도 읽을 내용이 없어 무의미** — 반드시 정의 포함.
- **작성 주체 = loop(자동).** 사용자 직접 작성 X. 기획서(`CLAUDE.md`)·KPI 규칙·`docs/db-schema.md`·기존 kb `.md`를 근거로 loop가 도메인별 용어+정의를 생성. 출처 불명 수치 단정 금지(정의·원칙 위주).
- **라우팅 vs RAG**: "프롬프트에 용어 있으면 그 어시스턴트로" = **분류기(`_Intent`) 역할**(이미 KPI/정의 질문→해당 도메인 라우팅). kb_chunks는 그 뒤 **정의를 RAG로 답하는 근거**. 둘 다 용어+정의 사전으로 충족 — 별도 라우팅 장치 불필요.
- 임베딩 모델 `text-embedding-3-small`(1536차원). 실행:
  - `cd backend && uv run python -m domain.simulation.assistant.kb_ingest`
  - `… domain.generator.assistant.kb_ingest`
  - `… domain.management.assistant.kb_ingest`
- 현재 적재량: 시뮬 6 · 제너 7 · 매니지 17 청크(샘플 수준) → 목표 각 **~100(커버리지 우선, 패딩 금지)**. ※ kb_chunks는 **RAG 근거**(어시스턴트 `search_kb` 툴이 top-k=4 검색·인용, graph.py:57-66)지 분류용 아님. 분류는 LLM `_Intent`가 별도로 함. top-k=4라 주제만 덮으면 수백 개 불필요 — 잘 쓴 40~100개가 적정.
- **매니지먼트만** 신규 .md 추가 시 `kb_ingest.py`의 `_SOURCE_META`에 `(source_type, source_url)` 항목 추가 필요(`meta_official|internal_policy|benchmark|playbook`).

### 시뮬 입력(W1~W2 근거)

- 카테고리 마스터 `frontend/src/lib/simCategories.ts` → `SIM_CATEGORIES`(업종 대분류 → NICE 45류 `kinds`). 2단 드롭다운.
- `/simulation` 페이지(`frontend/src/app/(app)/simulation/page.tsx`)에 **이미** 2단 카테고리 셀렉트 + 광고목표 칩(+기타 직접입력) + 인구생성(allocation `proportional`·gender·segments·sample_size)이 구현됨 → 위젯으로 이식.
- `api.simulation.start`는 `product_category`(대분류 name) + `service_class`(NICE 류 id) + `ad_objective` + `sample_size`를 이미 받음(`frontend/src/lib/api.ts`). 백엔드 지원 확인됨.
- 현재 위젯 `frontend/src/components/chat/SimFormWidget.tsx`는 4단계(제품명/광고설명/카테고리+목표 자유텍스트/소비자수).

---

## 4. 태스크 명세

### V1 — 시뮬 전체 흐름 재검증 (머지 코드 기준)

**목표** dev 머지 후 코드로 채팅 시뮬 파이프라인이 끝까지 도는지 브라우저로 확정.
**검증(Claude Preview)**
- [ ] `/chat` → 시뮬 시작 → `sim_form` 입력 → 실행 → `sim_result`(KPI) 표시
- [ ] 토론 자동 시작 → `debate_stream` 실시간 발언 → 완료 후 "토론 요약 보기" → `debate_summary`
- [ ] 토론 종료 후 개선 제안(`ApprovalWidget`) 노출
- [ ] 새로고침 시 결과/토론/요약 위젯 DB 복원
- [ ] 머지로 들어온 `ocean_segments`가 결과/리포트에 반영
- [ ] 진행중 시뮬 새로고침 → RUNNING 스피너 복원(gpt-4o-mini로 라이브 확인)
**주의** 어제 검증은 머지 전. 콘솔/네트워크(`/api/simulation/*`,`/api/debate/*`,`/api/chat/*`)·백엔드 로그 같이 본다.

### V2 — 제너레이터 직접 경로 검증 ⭐

**목표** "🎨 시안 만들기"로 생성이 머지된 이미지 파이프라인에서 끝까지 도는지 확정.
**검증**
- [ ] "🎨 시안 만들기" 칩 → `gen_form` + 초기값 채워짐
- [ ] 4단계 폼 → 프로젝트 선택 → "광고 생성 실행" → 완료까지 도달
- [ ] 후보(헤드라인·전략) 인라인 표시 + "상세 보기" → `/generations/{id}` 로드
- [ ] "생성 결과 보기"(`msg.result`) 버튼 올바른 id로 이동 / 새로고침 후 잔존
- [ ] 이미지 첨부 후 생성 → 상품 이미지 업로드 반영
- [ ] 생성 실패(키 없음/한도) 시 에러 카드 + "다시 시도"
- [ ] 동시실행 가드("이미 진행 중") 차단
**근거** `GenFormWidget.tsx`, 머지된 `domain/generator/pipeline/*`·`graph/nodes/candidate_gen.py`. 외부 이미지 모델 키 의존 — 실패 시 메시지/폴백 확인.

### V3 — 개선 루프 경로 검증 ⭐⭐ (가장 위험)

**목표** 리팩토링 후 한 번도 안 돌린 시뮬→토론→개선생성→재시뮬 왕복 확정.
**검증**
- [ ] 시뮬→토론→"개선 시안 만들기" 수락 → `gen_form` → 생성 → `gen_result_node`가 "새 시안으로 재시뮬" 제안
- [ ] 왕복 카운트(`loop_count`, MAX 3) 동작 — 한도 도달 시 차단/안내
**근거** `DebateStreamWidget`의 `ApprovalWidget(run_generator)` → `POST /api/chat/approve`(loop_count+1) → 오케스트레이터 `generator_node`.

### V4 — 프론트 전역 스모크 ((app) Route Group 재구성)

**목표** dev가 전 라우트를 `(app)` 그룹으로 재구성 → 앱 전체 깨짐 없는지.
**검증**
- [ ] `/chat/*`가 `(app)/layout`(사이드바·패널) 안에서 정상 렌더(레이아웃 이중/누락 없음)
- [ ] 사이드바 "채팅" 하이라이트 유지
- [ ] 플로팅 채팅이 `/chat/*`에서 숨고 다른 화면에서 노출
- [ ] `/simulation/[id]`·`/generations/[id]` 상세 정상
- [ ] 대시보드·매니지먼트 등 dev 신규 화면 미파손

### V5 — 3계정 로그인 + 역할별 접근 스모크

**목표** 3역할 계정(§0 표)으로 각각 로그인되고, 역할 게이팅이 의도대로인지 확정. 이후 모든 검증의 3역할 반복 기준점.
**검증(Claude Preview, 각 역할)**
- [ ] `admin`/`admin1234` 로그인 → `/admin/*` 관리자 화면 접근 가능, 일반 화면도 정상
- [ ] `yohan`/`yohan1234`(COMPANY) 로그인 → 조직/컴퍼니 화면(`/company/*`·`/my-org` 등) 접근, admin 전용은 차단
- [ ] `doyeon`/`fjdksla0852`(USER) 로그인 → 일반 화면·`건도연` 프로젝트·`/chat` 정상, admin 전용 차단
- [ ] 각 역할에서 `/chat` 진입·기본 동작 확인(역할별 데이터 차이 메모)
**근거** 로그인 `/sign-in`, 역할 게이팅은 현재 `/api/admin/*` 프리픽스·프론트 라우트 기준(CLAUDE.md). 
**완료 기준** 3역할 로그인·접근 권한 표대로 동작, 역할별 차이 진행 로그에 기록.

### R1 — 시뮬 용어+정의 사전 (~100, loop 작성)

**목표** `simulation_kb_chunks`에 **시뮬 용어+정의 사전 ~100개**(각 항목 `## 용어` + 1~2줄 정의). 용어 예: 클릭 의향률·구매의도·신뢰도·거부율·신뢰구간·AISAS(Action)·KOBACO 베이스라인·OCEAN·페르소나·SSR·effective_n·variance_warning·목표적합도 등. **loop가 작성**(기획서 KPI 규칙 근거).
**방법**
1. `backend/domain/simulation/assistant/kb/`에 용어사전 `.md` 작성 — 각 항목 `## 용어` + 1~2줄 정의(설명 포함). 기존 `kpi_definitions.md` 스타일.
2. 주제별 파일로 분할(반복당 1파일 ~30~50항목): `kpi_glossary.md` · `aisas_terms.md` · `kobaco_terms.md` · `persona_ocean_terms.md` · `ssr_methodology_terms.md` · `confidence_terms.md` 등.
3. 작성 후 `cd backend && uv run python -m domain.simulation.assistant.kb_ingest` → 적재 로그 확인.
**완료 기준** 핵심 용어 커버(위 목록) + 각 항목이 **용어+정의**(단어 단독 금지) + `select count(*) from simulation_kb_chunks` ≥ 50(목표 ~100). 한국어, 기획서 KPI 규칙(점추정 단언·"예측 CTR" 환산 금지)과 모순 없게.
**주의** 출처 불명확한 수치 단정 금지 — 정의·원칙 위주.

### R2 — 제너 용어+정의 사전 (~100, loop 작성)

**목표** `generator_kb_chunks`에 **카피·크리에이티브 용어+정의 사전 ~100개**(각 `## 용어` + 1~2줄 정의). 용어 예: AIDA·PAS·FAB·헤드라인·서브카피·CTA·톤앤매너·후킹·가치제안(UVP)·소구점·A/B 변주·플랫폼 규격(메타/인스타/유튜브) 등. **loop가 작성.**
**방법** `backend/domain/generator/assistant/kb/`에 용어사전 `.md`(`copy_strategies.md` 스타일, `## 용어`+정의) → 반복당 1파일 → `uv run python -m domain.generator.assistant.kb_ingest`. 제안 파일: `copy_formula_terms.md` · `headline_terms.md` · `tone_terms.md` · `cta_terms.md` · `platform_terms.md`.
**완료 기준** 카피/크리에이티브 FAQ 주제 커버 + `select count(*) from generator_kb_chunks` ≥ 50(목표 ~100).

### R3 — 매니지 용어+정의 사전 (~100, loop 작성)

**목표** `management_kb_chunks`에 **운영·최적화 용어+정의 사전 ~100개**(각 `## 용어` + 1~2줄 정의). 용어 예: CTR·ROAS·CVR·CPC·CPM·CPA·입찰 전략·예산 배분·이상탐지·조치(증액/감액/타겟 교체)·성과 진단·채널 믹스·메타 광고 정책 등. **loop가 작성.** 기존 4문서(`kpi_measurement_rules`·`meta_ad_policy`·`optimization_playbook`·`remediation_actions`) 확장.
**방법** `backend/domain/management/assistant/kb/`에 `.md` 추가 → **`kb_ingest.py`의 `_SOURCE_META`에 신규 파일별 `(source_type, source_url)` 항목 추가**(공식 표준은 URL, 내부 작성물은 None) → `uv run python -m domain.management.assistant.kb_ingest`.
**완료 기준** 운영/최적화 FAQ 주제 커버 + `select count(*) from management_kb_chunks` ≥ 50(목표 ~100), 각 청크가 `management_kb_documents` 부모와 연결(document_id not null).

### R4 — CLIO 전용 KB (광고 일반 지식 RAG)

> 배경: CLIO = 채팅의 기본 탑재 GPT(분류기→어시스턴트→툴 흐름의 베이스 응답자). 광고 관련 **일반 지식** 질문을 CLIO가 RAG로 답하게 한다. 시뮬/제너/매니지 3개 도메인 KB와 별개의 **CLIO 전용 KB**.

**확정 설계(플랜 2026-06-25) — 조사 결과 반영**
- **CLIO 본체 = `advise_node`**(orchestrator.py:757-771). 분류기 `_Intent`(orchestrator.py:417-423)는 `intent: management|simulation|generator|advise`. `advise`로 라우팅되면 advise_node가 CLIO 응답 생성. **여기에 CLIO RAG·인용·한도가 붙는다.**
- **R4-1**: `core/models.py`에 `ClioKbChunk`(`SimulationKbChunk` 복제 — source/title/chunk/embedding(1536)/created_at) + **Alembic 마이그(021, down_revision=직전)**. **승인됨 2026-06-25** → 무인 진행, 단독 커밋·up/down 검증.
- **R4-2**: ingest = `domain/chat/kb_ingest.py`(simulation kb_ingest 복제, 대상만 `ClioKbChunk`, `_KB_DIR=domain/chat/kb/`). `.md` `## 섹션` 작성 후 `uv run python -m domain.chat.kb_ingest`.
- **R4-3 retriever**: `domain/chat/retriever.py`에 `ClioKbRetriever`(SimKbRetriever 패턴 — `text-embedding-3-small`, pgvector 코사인 top-k=4, `{source,title,chunk,score}` 반환). advise_node 진입 시 `_format_clio_kb(question)`로 검색 → preamble에 `[CLIO 지식베이스]` 섹션 주입(기존 `_format_brand`+`_format_ltm` 옆). 응답 `meta.citations`에 source/title 기록(P5 인용 칩과 연계).
- **P12-1 분류**: `_Intent`에 `is_ad_domain: bool` 추가 + `_CLASSIFY_SYSTEM`(orchestrator.py:55-90)에 판정 규칙. ★주의: `advise`는 "광고 일반 전략"(=광고 도메인)과 "잡담/비광고 업무"가 섞임 → **intent만으로 판정 불가, `is_ad_domain` 별도 불린 필수**. management/simulation/generator=true, advise 중 광고 일반=true·그 외=false.
- **P12-2 한도 저장(권장: 스키마 무변경)**: 비광고(`is_ad_domain=false`) 요청을 카운트. **1차 권장 = `ChatMessage.meta`에 `usage_type:"advice"` 플래그 저장 후 `COUNT`**(스키마 변경 없음 → 추가 게이트 회피). (대안 AdviceUsageRow 신규 테이블은 또 다른 스키마 게이트라 지양.) 한도값은 설정.
- **P12-3 가드/표시**: 한도 초과 시 advise 진입 전 차단 + 안내 meta. 프론트 progress bar("일반 업무 N/한도")는 카운트 조회 API로.
- **라우팅 충돌 주의**: CLIO RAG는 **advise(일반 지식)** 에만. 시뮬/제너/매니지로 분류된 건 각 도메인 RAG가 처리 — CLIO KB와 섞지 않는다.

#### R4-1 — `clio_kb_chunks` 테이블 + 마이그레이션 (승인됨 2026-06-25)

**목표** CLIO 전용 KB 청크 테이블 신설. 기존 `simulation_kb_chunks` 스키마와 동일 형태(`source/title/chunk/embedding(1536)/created_at`).
**구현** `core/models.py`에 `ClioKbChunk` 모델 추가 + **Alembic 마이그레이션(raw DDL 직접 X)**. **단독 커밋**(다른 변경과 안 섞기).
**주의** 사용자 승인 완료 → 무인 진행 OK. 단 신규 테이블 추가만(기존 모델 컬럼은 건드리지 않음).
**완료 기준** `clio_kb_chunks` 테이블 생성, `import api.main` OK, 마이그레이션 up/down 동작.

#### R4-2 — CLIO KB 광고 일반지식 적재 (~100, R4-1 의존)

**목표** 광고 전반의 일반 지식(광고의 정의·역사, 매체별 특성, 카피·크리에이티브 기초, 브랜딩, 퍼널/AARRR·AISAS, 타게팅, 측정지표 기초, 윤리·규제, 트렌드 등)을 **~100 청크(커버리지 우선)**. 도메인 KB(시뮬/제너/매니지)와 중복 회피 — CLIO는 **일반 지식**만.
**방법** `backend/domain/chat/clio/kb/`(또는 적절 위치)에 `.md` `## 섹션` 작성 → CLIO ingest 모듈 신설(`simulation/assistant/kb_ingest.py` 패턴 복제, 대상 테이블만 `ClioKbChunk`) → 실행. 반복당 .md 1파일.
**완료 기준** 광고 일반지식 FAQ 커버 + `select count(*) from clio_kb_chunks` ≥ 50(목표 ~100).

#### R4-3 — CLIO 응답에 CLIO RAG 연결 (R4-2 의존)

**목표** CLIO(기본 GPT) 응답 경로에서, 광고 일반 질문이면 `clio_kb_chunks` 검색 → 컨텍스트 주입 + 인용(P5와 연계). 분류기가 "광고 일반 지식" 의도로 분류 시 CLIO RAG 사용.
**구현** CLIO retriever(임베딩 `text-embedding-3-small`로 top-k) → 프롬프트에 근거 주입. 시뮬/제너/매니지 RAG와 라우팅 충돌 없게(그쪽은 도메인 작업, CLIO는 일반 지식).
**완료 기준** 광고 일반 질문에 CLIO가 KB 근거로 응답 + 인용 칩. Preview 확인.

### R5 — clio KB에 Meta(인스타/페북) 정책·용어 추가 적재

> 전제: `clio_kb_chunks` 테이블·ingest·retriever는 **이미 존재**(R4-1/R4-2/R4-3 완료, `advertising_general_knowledge.md` 70청크 적재됨). 따라서 **테이블 생성 불필요 — `.md` 추가 후 재인제스트만**.

**목표** CLIO(채팅 기본 어시스턴트)가 **Meta 플랫폼(인스타그램·페이스북) 광고 정책·용어**를 RAG로 답하도록 clio KB에 Meta 지식을 추가. 예: 광고 정책 위반 유형(금지 콘텐츠·과장 표현·개인 속성 타겟팅 제한)·광고 검수(review) 흐름·계정/픽셀·전환 API(CAPI)·Advantage+·광고 형식(피드/릴스/스토리/컬렉션)·도달·빈도·광고 게재 위치 등 **용어 + 1~2줄 정의**.
**방법**
1. `backend/domain/chat/kb/`에 `meta_platform_policy.md`(또는 주제별 `meta_ad_policy.md`·`meta_ad_formats.md`) 작성 — 각 항목 `## 용어/정책` + 1~2줄 정의(단어 나열 ❌). 기존 `advertising_general_knowledge.md` 스타일.
2. `cd backend && uv run python -m domain.chat.kb_ingest` 재실행 → **소스 파일명 기준 멱등**(같은 source 삭제 후 재적재)이라 기존 70청크 유지·신규 source만 추가.
**완료 기준** `select count(*) from clio_kb_chunks` 증가(Meta 항목 ~30~50 추가), `ClioKbRetriever`가 "인스타 광고 정책" 류 질문에 Meta 청크 top-k 반환. advise_node 응답에 Meta 근거+인용. Preview/스모크 확인.
**주의** **management KB에 이미 `meta_ad_policy`(집행 후 운영 관점)가 있음** — clio는 **채팅 일반 질의응답 관점**의 플랫폼 정책·용어로, 운영 조치(증액/감액)와는 분리. 출처 불명 수치 단정 금지(정책 원칙·정의 위주, 정확한 수치는 "공식 정책 참조" 표기).

### R6 — clio KB에 광고·마케팅 용어+정의 추가 적재 (~100)

> 사용자 결정: **별도 marketing 테이블을 만들지 않고 clio_kb에 통합**한다. clio_kb = CLIO 채팅 어시스턴트의 광고·마케팅 통합 KB(일반지식 + Meta 정책 + 마케팅 용어). 테이블·ingest·retriever·advise 연결은 **이미 존재**(R4 완료)하므로 **`.md` 추가 + 재인제스트만** — 신규 테이블/retriever/연결 불필요.

**목표** clio KB에 **광고·마케팅 개념/이론 용어+정의 사전 ~100개**(각 `## 용어` + 1~2줄 정의)를 추가해, CLIO가 "ROAS가 뭐야" 류 용어 질문에 KB 근거로 답하게 한다. 용어 예: STP·타게팅·포지셔닝·USP·퍼널(AARRR)·AISAS·CAC·LTV·ROAS·CPM/CPC/CPA·노출/도달/빈도·리타게팅·룩어라이크·브랜드 인지/고려/전환·A/B 테스트·어트리뷰션·CTR/CVR 정의 등. **loop가 작성**(기획서·일반 마케팅 표준 근거).
**방법**
1. `backend/domain/chat/kb/`에 마케팅 용어 `.md` 작성 — 각 항목 `## 용어` + 1~2줄 정의(단어 나열 ❌). 기존 `advertising_general_knowledge.md` 스타일. 주제별 분할 권장(반복당 1파일 ~30~50항목): `marketing_funnel_terms.md`·`metric_terms.md`·`targeting_terms.md` 등.
2. `cd backend && uv run python -m domain.chat.kb_ingest` 재실행 → **소스 파일명 기준 멱등**이라 기존 청크 유지·신규 source만 추가.
**완료 기준** 마케팅 핵심 용어 커버 + `select count(*) from clio_kb_chunks` 증가(마케팅 용어 ~100 추가), 각 항목이 용어+정의(단어 단독 금지). `ClioKbRetriever`가 용어 질문에 신규 청크 top-k 반환, advise_node 응답에 근거+인용. Preview/스모크 확인.
**주의** clio의 기존 `advertising_general_knowledge`(70청크)·R5 Meta와 **중복 항목 회피** — 같은 용어가 이미 있으면 새로 만들지 말고 보강. 출처 불명 수치 단정 금지(정의·원칙 위주). 단순성 우선(top-k=4라 잘 쓴 항목이 패딩보다 나음).

### R7 — 기존 3 KB(sim/gen/manage) 덤프·점검·보강

**목표** 코덱스(다른 세션)가 적재한 기존 3 KB의 현재 내용을 **덤프해 직접 확인**하고, 커버리지 빈 곳(누락 용어·얕은 정의)을 보강. 현재 적재량(머지 시점): 시뮬 69 · 제너 79 · 매니지 88 청크.
**방법**
1. **덤프**(테이블별로 `M`만 교체 — `SimulationKbChunk`/`GeneratorKbChunk`/`ManagementKbChunk`):
   ```
   cd backend && uv run python -c "
   import asyncio
   from sqlalchemy import select
   from core.db import AsyncSessionLocal
   from core.models import SimulationKbChunk as M
   async def main():
       async with AsyncSessionLocal() as db:
           rows = (await db.execute(select(M.source, M.title, M.chunk).order_by(M.source, M.title))).all()
           print('total', len(rows))
           for s, t, c in rows:
               print(f'[{s}] ## {t}\n  {c[:140]}')
   asyncio.run(main())
   "
   ```
2. 덤프로 **누락 주제·정의 부실 항목**을 식별 → 각 도메인 `kb/`에 보강 `.md`(또는 기존 파일 확장) 작성 → 해당 ingest 재실행(`domain.simulation.assistant.kb_ingest` 등, 멱등). 매니지 신규 .md는 `kb_ingest.py`의 `_SOURCE_META` 항목 추가 필요.
**완료 기준** 3 KB 덤프 결과를 진행 로그에 요약(테이블별 총량·주요 주제), 식별된 빈 곳에 용어+정의 보강(있을 경우), 보강 후 count 증가 확인. 보강할 게 없으면 "충분"으로 판정·기록(억지 패딩 금지).
**주의** 각 도메인 KB는 원소유 팀 자산 — 적재(추가)는 자유, **스키마/기존 청크 의미 훼손 금지**. 단순성 우선(top-k=4라 잘 쓴 항목이 수백 패딩보다 나음).

### W1 — 시뮬 위젯 카테고리 2단 셀렉트

**목표** `SimFormWidget`의 자유텍스트 카테고리를 `/simulation`과 동일한 **2단 셀렉트박스(업종 대분류 → NICE 류)**로 교체.
**구현** `SIM_CATEGORIES`(`@/lib/simCategories`) 사용. 선택값 → `start`에 `product_category`(대분류 name) + `service_class`(kind id) 전달. 기존 `category` 자유입력 상태 제거.
**완료 기준** 셀렉트로 대분류 고르면 하위 류 셀렉트 활성, 둘 다 선택 시 다음 진행. `tsc`·lint 통과. Preview로 동작 확인.

### W2 — 시뮬 위젯 5단계 재구성 (W1 의존)

**목표** 현재 4단계 → **5단계**: ①제품명 ②광고설명 ③**카테고리 설정**(W1의 2단 셀렉트) ④**광고 목표 칩**(`/simulation`의 목표 칩 + 기타 직접입력) ⑤**인구 생성**(sample_size + allocation/gender/segments).
**구현** `totalSteps=5`, step 인덱스 재배치. 목표 칩·인구생성 UI는 `/simulation/page.tsx`에서 패턴 이식(중복 로직은 작게 컴포넌트화 고려, 단 과설계 금지). `start` payload에 선택 반영. (광고 이미지는 기존대로 채팅 첨부 시 `initialImage`로만 사용, 별도 필수 단계 없음.)
**완료 기준** 5단계 진행·뒤로가기 정상, 실행 시 카테고리/목표/인구 옵션이 payload에 포함, 결과 정상. Preview 확인.

### W3 — 사용자 친화 보조 위젯

**목표** 입력·결과 가독성 개선용 보조 위젯(예: 카테고리 추천 칩, 입력 요약 미리보기, 단계 진행 인디케이터 개선). **범위는 W2 완료 후 실제 부족한 지점만** 좁게.
**완료 기준** 추가 위젯이 기존 흐름을 깨지 않고 Preview에서 동작. (과한 신규 추상화 금지 — CLAUDE.md 단순성 우선.)

### G1 — 제너 입력 확인 위젯 (입력 위젯 교체)

**목표** 시뮬과 동일하게, 사용자가 `gen_form`에 값 입력·실행하면 **입력 위젯이 사라지고 그 자리에 입력 확인 위젯이 올라오게**. 시뮬의 `SimInputWidget`(입력 요약) 패턴을 본떠 `GenInputWidget` 신규.
**구현** `GenFormWidget` 완료 시 `onGenComplete`/`onResult` 흐름에서 입력 요약(상품명·설명·타깃·목표·이미지 썸네일)을 별도 메시지 위젯으로 영속화. 결과 나온 `gen_form`은 시뮬처럼 **메시지째 숨김**(뒤에 결과 위젯 있으면 렌더 안 함).
**근거** 시뮬: `SimInputWidget`·`ChatConversation.handleSimComplete`→`appendWidgets(sim_input…)`. 제너도 같은 구조로.
**완료 기준** 제너 실행 후 입력 위젯 사라지고 입력 확인 위젯 표시, 새로고침 후에도 유지. Preview 확인.

### G2 — 제너 로딩 스피너 위젯 (G1 의존)

**목표** 제너 생성 진행 중 시뮬의 running phase처럼 **로딩 스피너 위젯**(진행률 바 + 단계 메시지 + 클릭 시 상세 이동). `SimFormWidget`의 running phase / 시뮬 로딩 위젯 패턴 이식.
**구현** `api.generator.stream`의 pct/message를 스피너 위젯에 바인딩. 클릭 시 `/generations/{id}`로.
**완료 기준** 생성 중 스피너·진행률 표시, 완료 시 결과 위젯으로 전환. Preview 확인.

### G3 — 제너 결과 요약 위젯 (이미지 3장 가로 스크롤, G1 의존)

**목표** 시뮬 `SimResultWidget`에 대응하는 `GenResultWidget` 신규 — **광고 시안 이미지 3장을 가로 스크롤**로 보여주고 **하단에 간략 요약**(헤드라인·핵심 전략·"상세 보기 →" `/generations/{id}`).
**구현** `api.generator.detail(gid)`로 후보 조회 → 가로 스크롤 캐러셀(이미지) + 하단 텍스트. 결과 위젯 메시지로 영속화(새로고침 복원). 인라인 표시는 이 위젯으로 대체.
**완료 기준** 이미지 3장 가로 스크롤 동작, 하단 요약·상세 링크 정상, 새로고침 후 복원. Preview 확인.

### G4 — 제너 status API + 새로고침 복원 (V2 의존)

**목표** 시뮬과 동일하게 제너도 **status API로 진행 상태 조회** → 새로고침해도 진행중 런이 안 날아가게 복원. 현재는 폼으로 리셋됨.
**구현**
- 백엔드: 시뮬 `GET /api/simulation/{run_id}/status`(`get_run_status`) 대응으로 **제너 status 엔드포인트**(`GET /api/generator/{generation_id}/status` 등) 확인/추가 — RUNNING/COMPLETED/FAILED + pct/stage 반환.
- 프론트: 시뮬의 `ACTIVE_SIM_KEY`+status 복원 패턴을 제너에 적용(`localStorage`에 진행중 generation_id 보관, 마운트 시 status 조회로 스피너/결과 복원).
**근거** 시뮬: `SimFormWidget`의 `useEffect`(`latest` 복원)·`api.simulation.status`. 제너 status 엔드포인트가 이미 있으면 재사용, 없으면 추가(도메인 내부라 OK, 단 스키마 변경은 아님).
**완료 기준** 생성 진행 중 새로고침 → status API로 스피너/진행률 복원, 완료 후 새로고침 → 결과 위젯 복원. Preview 확인.

## 4-S. 슬래시 커맨드 (S) — "위젯은 있는데 진입점이 없다"

> 핵심: 현재 슬래시는 5개(`/시뮬레이션`·`/제너레이터`·`/비교`·`/도움말`·`/위젯`)인데 위젯은 10개. **위젯 5개가 자연어로만 뜨고 슬래시 진입점이 없음**. 진입점만 붙이면 묻힌 기능이 즉시 살아남.
> 등록 위치: [ChatConversation.tsx:33](frontend/src/components/chat/ChatConversation.tsx) `slashCommands` 배열 + `runSlashCommand`. (※ `/위젯`은 C5에서 제거 예정 — S 작업 시 자동완성 목록에서 빠지는 것과 정합.)

### S1 — 저비용 슬래시 4종 (프론트만, 최우선) ⭐

**목표** 이미 완성된 위젯에 슬래시 진입점만 추가:

| 명령어 | 띄울 위젯 | 비고 |
| --- | --- | --- |
| `/배치` (별칭 `/AB`) | `batch_sim_form` | 광고 2개 동시 비교 시뮬 — **트리거가 전혀 없던 위젯**. "비교"에 정확히 부합 |
| `/리포트` | `report_ready` | PDF 다운로드. 현재 "리포트 뽑아줘" 자연어로만 |
| `/시뮬목록` | `sim_list` | 최근 시뮬 목록(조회/선택/비교 3모드 이미 지원) |
| `/시안목록` | `gen_list` | 최근 생성 시안 목록 |

**구현** `slashCommands` 배열에 4개 항목(+`/AB` 별칭) 추가 + `runSlashCommand`에서 해당 위젯 트리거. 백엔드 변경 거의 없음.
**완료 기준** 4개 커맨드 입력 시 해당 위젯 즉시 노출, 자동완성에 표시. tsc/lint·Preview 확인.

### S2 — /비교 캠페인 A/B 확장 (S1 의존)

**목표** 현재 `/비교`는 시뮬 2개 비교만(F12). **캠페인(매니지먼트) A/B 비교**를 추가.
**구현** management 비교 서비스([comparison_service.py](backend/domain/management/comparison/service/comparison_service.py)) 존재 → 채팅 라우팅 + 비교 위젯 연결. `/비교` 진입 시 시뮬/캠페인 비교 모드 선택.
**소유권 주의** management 도메인 연동 → 타 팀 소유부 호출. **읽기/서비스 호출 범위 내**로, 매니지먼트 내부 수정은 조율.
**완료 기준** `/비교`에서 캠페인 두 개 A/B 비교 위젯 표시. Preview 확인.

### S3 — /분석 (과거 성과 종합 요약)

**목표** 과거 시뮬·생성·캠페인 성과를 종합 요약하는 `/분석`.
**구현** orchestrator에 advise(요약) 라우팅 규칙 + 요약 위젯. 데이터는 기존 결과/실행 기록에서 집계.
**완료 기준** `/분석` 입력 시 종합 요약 위젯. Preview 확인.

### S4 — /추천 (목표·예산 → 전략/플랫폼 추천)

**목표** 목표·예산을 입력받아 전략/플랫폼을 추천하는 `/추천`.
**구현** 입력 폼 위젯 + advise 노드. (S3와 advise 라우팅 공유 가능.)
**완료 기준** `/추천` 입력 → 폼 → 추천 결과 위젯. Preview 확인.

### S5 — /액션 (매니지먼트 조치 종류 확장)

**목표** 매니지먼트 조치를 증액·감액 외 **타겟·크리에이티브 교체 등**으로 확장하는 `/액션`. HITL 승인 카드(`ApprovalWidget`)는 이미 있음 → 액션 종류만 확장.
**소유권 주의** management 조치 로직 연동 → 타 팀 소유부. 채팅 측 라우팅·승인 카드 범위로, 내부 실행 로직 변경은 조율.
**완료 기준** `/액션`에서 확장된 조치 종류 선택 → 승인 카드. Preview 확인.

### F1 — 메시지 액션 바 (복사·재생성·👍👎)

**목표** 어시스턴트 답변 말풍선에 복사/재생성/좋아요·싫어요 추가. 피드백은 `POST /api/chat/feedback`(머지로 백엔드 존재, 프론트 미연결)로 전송.
**완료 기준** 복사 동작, 재생성이 마지막 질문 재요청, 👍👎가 feedback 엔드포인트 호출(rating ±1). Preview 확인.

### F2 — 세션 사이드바 (목록·전환·삭제)

**목표** 프로젝트별 과거 채팅 세션 목록 UI. `GET/POST/DELETE /api/chat/sessions` 사용(이미 존재). URL 라우팅(`/chat/[pid]/[sid]`)과 연결.
**완료 기준** 세션 목록 표시·클릭 전환·삭제 동작, 현재 세션 하이라이트. Preview 확인.

### F5 — 랭체인 롱텀 메모리 점검·강화

**목표** 기존 롱텀 메모리(브랜드 프로파일·결과 패턴, `handoff.md` T03·T06·T07)가 머지 후 실제 동작하는지 점검하고 빈 곳 보강. `domain/management/assistant/checkpointer.py`·`domain/chat/*` 확인.
**완료 기준** 멀티턴에서 이전 컨텍스트(브랜드·과거 결과) 참조 확인, 끊긴 부분 수정. (스키마 변경 필요 시 멈추고 보고.)

### F6 — 채팅 ↔ 매니지먼트 RAG 연결 (R3 의존)

**목표** 채팅 오케스트레이터에서 매니지먼트 에이전틱 RAG 서브에이전트(`/management/assistant`, import-ready)를 툴로 호출 → "집행 후 성과" 질문에 채팅이 응답. (오케스트레이터 본체는 후순위지만 서브에이전트 연결은 기획서 범위.)
**완료 기준** 채팅에서 매니지먼트성 질문 시 서브에이전트 경유 답변 + 인용. Preview 확인.

### F7 — KPI 분포·신뢰구간 표현 점검 (V1 의존)

**목표** `SimResultWidget`이 KPI를 **분포/신뢰구간**으로 보여주는지 점검, 점추정 단언이면 분포 바·CI 밴드로 보강. 기획서 KPI 규칙(평균 단언 금지·분포 전체·"예측 CTR" 환산 금지) 준수.
**완료 기준** 4대 KPI가 규칙에 맞게 표기. Preview 확인.

### F8 — 시안 후보 선택 → 재시뮬 (V2 의존)

**목표** 생성된 광고 시안 후보 중 하나를 **사용자가 "이걸로" 선택**하면, 그 시안(헤드라인·카피·이미지)으로 바로 재시뮬을 돌려 개선 전후 KPI 비교. 개선 루프를 사용자 주도로.
**구현** `GenResultWidget`(G3)의 각 후보에 "이걸로 시뮬" 버튼 → 선택 후보를 시뮬 입력에 주입해 `api.simulation.start`. 결과는 기존 시뮬 파이프라인(결과/토론).
**완료 기준** 후보 선택 → 재시뮬 → 결과 위젯. Preview 확인.

### F10 — 해시태그·키워드 추천 위젯

**목표** 광고/시안 맥락에서 **추천 해시태그·키워드** 칩을 위젯으로 제시(SNS 광고 활용). 클릭 시 복사.
**구현** 카피·카테고리·타깃 기반으로 LLM에 키워드 추출 요청 → 칩 렌더(복사 가능). 채팅 액션/커맨드(`/키워드`)로도 트리거.
**완료 기준** 맥락 기반 키워드 10~15개 칩 표시·복사. Preview 확인.

### F11 — 채팅 검색 (세션·메시지, F2 의존)

**목표** 세션 사이드바(F2)에 검색창 → 과거 세션·메시지 텍스트 검색.
**구현** 프론트 필터(로드된 세션) 우선, 필요 시 백엔드 `GET /sessions` 확장(도메인 내부). 매칭 하이라이트.
**완료 기준** 키워드로 세션/메시지 필터·이동. Preview 확인.

### F12 — 시뮬↔시뮬 비교 위젯 (/비교 확장, V1 의존)

**목표** 두 시뮬 결과를 나란히 비교(4대 KPI 델타). 기존 `ComparisonWidget`·`/비교`(handoff T14) 확장.
**구현** 두 simulation_id 선택 → KPI 표/막대 비교 위젯. 개선 전후 또는 임의 두 런.
**S2와의 관계** F12 = 시뮬↔시뮬 비교, S2 = `/비교`의 캠페인(매니지먼트) A/B 비교. `/비교` 진입 시 두 모드를 함께 둔다.
**완료 기준** 두 런 KPI 나란히 + 차이 표시. Preview 확인.

### P1 — 모바일 반응형 (채팅·위젯·레이아웃)

**목표** `/chat`과 모든 채팅 위젯(`SimFormWidget`·`GenFormWidget`·결과/토론/요약 등)이 모바일 폭(~375px)에서 깨지지 않게. 사이드바·플로팅 채팅·패널 반응형.
**구현** Tailwind 반응형(`sm:`/`md:`) 보강 — 고정폭·grid-cols-2를 모바일에서 1열로, 가로 스크롤 위젯은 터치 스크롤, 폼 단계·칩 줄바꿈. `(app)/layout`의 사이드바는 모바일에서 드로어/숨김.
**완료 기준** Preview를 모바일 뷰포트(`preview_resize` 375x812)로 두고 `/chat` 핵심 흐름(시뮬·생성)이 가독·조작 가능. 데스크톱 회귀 없음.
**주의** 레이아웃은 dev가 `(app)`로 재구성한 공유부 — 사이드바/레이아웃 구조 변경은 최소·수술적으로, 의심되면 로그 남기고 채팅 위젯 내부 반응형부터.

### P2 — 전역 KST 시간 표시 (created_at 등)

**목표** 화면의 모든 시각(메시지·세션·시뮬/생성 created_at)을 **한국 시간(Asia/Seoul)**으로 표시. 현재 DB 값이 KST가 아님.
**구현(안전 경로 — DB 스키마 변경 없이)**
- 프론트 날짜 유틸 `formatKST(iso)` 신설 — `Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul', …})`. 타임스탬프 렌더를 전부 이 유틸 경유로.
- 백엔드가 datetime을 **UTC ISO8601(말미 `Z`)**로 직렬화하는지 점검 — naive datetime이면 UTC로 가정해 tz 부여 후 직렬화(스키마/시리얼라이저 레벨, 모델 컬럼 불변).
**완료 기준** 채팅·세션·결과의 시각이 KST로 표시(예: "2026-06-25 01:23"). Preview 확인.
**주의** "DB 저장값 자체를 KST로" 원하면 `core/models.py` 기본값·기존 행 마이그레이션(Alembic) 필요 → **공유 스키마라 단독 변경 금지**, ⬜ 유지·로그 후 사용자 확인. 표시 KST가 안전한 기본.

### P3 — 스트리밍 Stop/취소 버튼

**목표** 채팅 응답·시뮬·생성 SSE 진행 중 "중단" 버튼. 잘못 보낸/긴 요청 끊기.
**구현** 진행 중 `EventSource.close()` + 서버측 취소 가능하면 취소 요청. UI는 전송 버튼이 진행 중엔 "■ 중단"으로.
**완료 기준** 스트리밍 중 중단 클릭 → 즉시 멈춤·상태 정리. Preview 확인.

### P4 — 빈 상태 온보딩 + 퀵스타트 칩

**목표** `/chat` 첫 진입(메시지 0개) 시 어시스턴트 소개 + **퀵스타트 칩**("🧪 시뮬 돌리기"·"🎨 시안 만들기"·"📊 리포트"·"💡 매니지먼트 질문"). 칩 클릭 시 해당 흐름 트리거.
**구현** 빈 상태 컴포넌트 + 칩 → 기존 트리거(시뮬/생성/리포트)로. S1 슬래시·템플릿과 묶어도 됨.
**P14와의 관계** "이거 입력해보세요" 식 **예시 질문 프롬프트는 다시 넣지 않는다**(P14에서 제거). **액션 칩만** 둔다.
**완료 기준** 첫 화면에서 칩으로 핵심 흐름 시작. Preview 확인.

### P5 — RAG 인용 표시 위젯 (R1 의존)

**목표** 어시스턴트가 KB 기반으로 답하면 답변 아래 **인용 칩**(출처 파일 › 섹션 제목) 표시 → 신뢰도·근거 가시화. ("직감보다 나은 근거" 가치 직결.)
**구현** 매니지먼트는 이미 `citations`/`retrieved_chunks` 저장(`ManagementAgentRun`) — 응답에 실어 칩 렌더. 시뮬/제너 RAG도 retriever가 반환한 source/title를 응답 메타에 포함.
**완료 기준** KB 기반 답변에 인용 칩 표시, 클릭 시 원문 일부 노출(툴팁/펼침). Preview 확인.

### P6 — 위젯 등장 애니메이션 + 타이핑 커서

**목표** 위젯·메시지 등장 시 부드러운 fade/slide, 스트리밍 텍스트에 타이핑 커서. "살아있는" 느낌으로 데모 인상↑.
**구현** CSS transition/keyframes(또는 이미 있으면 framer-motion). 과한 모션 지양(접근성 `prefers-reduced-motion` 존중).
**완료 기준** 새 메시지/위젯이 부드럽게 등장, 스트리밍에 커서. Preview 확인.

### P7 — 다크모드 일관성 점검

**목표** 모든 채팅 위젯의 다크모드 클래스(`dark:`) 누락·대비 점검·보정. 위젯들엔 이미 `dark:` 클래스가 있으니 빠진 곳만.
**완료 기준** 라이트/다크 토글 시 전 위젯 가독·일관. Preview(다크) 확인.

### P8 — 입력창 강화 (멀티라인·슬래시 자동완성)

**목표** 채팅 입력창: 멀티라인(Shift+Enter 줄바꿈, Enter 전송), 슬래시 커맨드 입력 시 **자동완성 드롭다운**(S 그룹 커맨드 목록), 첨부 이미지 미리보기·제거.
**완료 기준** 멀티라인·자동완성·첨부 미리보기 동작. Preview 확인.

### P9 — 완료 토스트 + 상대시간 타임스탬프 (P2 의존)

**목표** 시뮬/생성 완료 시 토스트 알림. 메시지에 상대시간("방금 전"·"3분 전", KST 기준) 표시.
**완료 기준** 완료 토스트 표시, 메시지 hover/표시에 상대시간. Preview 확인.

### P10 — 결과 복사 버튼 (KPI·카피·헤드라인)

**목표** 시뮬 KPI 요약·생성 카피/헤드라인에 복사 버튼 → 클립보드. 실무 바로 활용.
**완료 기준** 각 결과 블록 복사 동작 + "복사됨" 피드백. Preview 확인.

### P11 — 자동 스크롤 + 스크롤-투-바텀 버튼

**목표** 새 메시지 시 하단 자동 스크롤(사용자가 위로 올렸으면 유지), 우하단 "맨 아래로" 버튼.
**완료 기준** 스트리밍 중 자연스러운 스크롤, 버튼 동작. Preview 확인.

### P12 — CLIO 사용량 한도 + progress bar (광고 질문 제외 가드)

> 배경: CLIO가 OpenAI(gpt)로 연결돼 있어 실서비스 전환해도 같은 gpt라 사용자가 우리 채팅을 **범용 챗봇**으로 계속 쓸 수 있다. **광고 관련 질문은 무제한**, **그 외 일반 업무는 한도**를 걸고 progress bar로 잔량을 보여준다.

#### P12-1 — CLIO 광고 vs 비광고 분류 (분류기 확장)

**목표** 기존 의도 분류기(프롬프트→분류기→어시스턴트 흐름)에 **광고 관련 / 비광고(일반 업무)** 판정 추가. 비광고만 한도 대상.
**구현** 분류기에 라벨 추가(광고 도메인 작업·광고 일반지식 = 무제한 / 그 외 = 한도). 오분류 보수적으로(애매하면 광고로).
**완료 기준** 대표 질문셋에서 광고/비광고 분류 동작, 분류 결과 로깅(X4와 연계). Preview/로그 확인.

#### P12-2 — 비광고 사용량 카운팅·한도 (백엔드, P12-1 의존)

**목표** 비광고 분류된 요청의 사용량(횟수 또는 토큰)을 사용자/세션 단위로 카운트하고 한도 설정. 초과 시 차단·안내.
**구현** 사용량 저장(가벼운 카운터 — 메모리/DB 중 도메인 내부 선택, 스키마 광범위 변경은 지양). 한도값은 설정으로. 광고 분류는 카운트 제외.
**완료 기준** 비광고 요청만 카운트 증가, 한도 도달 시 차단·메시지. 로그 확인.

#### P12-3 — 한도 progress bar 모니터링 UI + 초과 안내 (P12-2 의존)

**목표** 채팅 UI에 비광고 사용량 **progress bar**(예: "일반 업무 12/20") 노출, 초과 시 친절한 안내 + "광고 관련 질문은 무제한" 안내.
**완료 기준** progress bar 실시간 반영, 초과 안내 표시. Preview 확인.

### P14 — 빈 화면 중앙 추천 질문 메시지 제거

**목표** 채팅 빈 화면 중앙의 **추천 질문 메시지 제거**("이 광고의 예상 CTR을 분석해줘"·"20대 여성 타겟 광고 전략을 추천해줘"·"경쟁사 광고와 비교 분석해줘"·"광고 카피 개선 방법을 알려줘").
**구현** `ChatConversation.tsx:25` `quickPrompts` 배열과 그걸 렌더하는 빈 상태 블록 제거. 관련 죽은 변수/스타일 정리(수술적).
**P4와의 관계** P4(빈 상태 온보딩)는 **예시 질문 프롬프트를 다시 넣지 않는다** — 액션 칩(🧪 시뮬/🎨 생성/📊 리포트)만. 깔끔한 빈 상태 유지.
**완료 기준** 빈 화면에 추천 질문 메시지 안 보임, tsc/lint·Preview 확인.

### P13 — 다크모드 로딩 스피너 가시성 수정 (버그)

**목표** **현재 다크모드에서 로딩 스피너가 안 보이는 버그** 수정. 시뮬/제너/채팅의 스피너가 다크 배경에서 대비 부족(테두리·트랙 색이 배경과 동화).
**구현** 스피너의 `border`/`border-t` 색에 `dark:` 대비색 적용(예: 트랙 `dark:border-[#2D3748]`, 헤드 `dark:border-t-[#5B9DF9]` 등 충분한 대비). `SimFormWidget`의 running phase 스피너부터, 제너/공용 스피너까지.
**완료 기준** 라이트·다크 모두 스피너가 또렷이 보임·회전. Preview(다크) 확인.

## 4-N. 능동(N) — 카톡형 먼저 말 거는 챗봇

> 목표: 사용자가 채팅에 안 들어와도, 시뮬/제너 결과·기회를 챗봇이 **먼저 알려주고 개선을 제안**한다. 카톡처럼 안읽음 뱃지로 끌어당김. 기존 자산: 개선 제안 `ApprovalWidget`, 프로액티브 푸시(handoff `T18`), 플로팅 채팅 [FloatingChat.tsx](frontend/src/components/chat/FloatingChat.tsx), sim/gen status 엔드포인트(G4/F-status).

**확정 설계(플랜 2026-06-25) — 조사 결과 반영**
- **공통 핵심 — "활성 세션 적재" 경로**: 외부(전용 페이지·서버)에서 채팅에 메시지를 넣는 길은 `POST /api/chat/widget-messages`(→ `history.append_widget_messages(session_id, items)`). N1·N4 모두 이걸 씀. **빠진 고리 = "어느 세션에 넣나"**: 전용 페이지/트리거가 프로젝트의 채팅 세션을 알아야 함 → `GET /api/chat/sessions?project_id=…`로 최신 세션 선택(없으면 생성). 이 "프로젝트→활성 세션 해석" 헬퍼를 먼저 만든다.
- **N1 (직접 실행 → 자동 제안)**: `/simulation`·`/generator` 전용 페이지의 **완료 시점**(SSE completed/`setPhase('done')`)에 → 활성 세션 해석 → `appendWidgets`로 `sim_result`/`gen_result` + `ApprovalWidget(rerun_simulation/run_generator)` 메시지 주입. 채팅에서 돌린 경로와 동일 위젯 재사용. 변경: `app/(app)/simulation/page.tsx`·`app/(app)/generator(page)`, `lib/api.ts`(세션 해석), 백엔드는 기존 엔드포인트로 충분.
- **N2 (안읽음 뱃지) — 이미 구현됨**: [FloatingChat.tsx:76-80](frontend/src/components/chat/FloatingChat.tsx) 빨간 뱃지 + `unread`/`pushUnread()`/`clearUnread()` 존재. **신규 구현 아님 → "배선·검증"만**: N1/N4 메시지 주입 시 패널이 닫혀 있으면 `pushUnread()`가 실제로 불리는지(특히 다른 페이지/탭에서 도착한 경우) 확인·연결. (비용 대폭 하향.)
- **N3 (타 탭 status 동기화)**: 채팅이 진행 중 run_id/generation_id를 알면(localStorage `ACTIVE_SIM_KEY` 패턴) status 폴링 → RUNNING 스피너 / COMPLETED 결과 위젯. **시뮬 status는 있음**(`GET /api/simulation/{run_id}/status`). **제너 status 엔드포인트는 없음 → G4에서 추가 필수**(N3는 G4 의존). 변경: 채팅 측 폴링 훅 + 제너 status(G4).
- **N4 (선제적 말걸기)**: **현재 T18은 클라이언트 콜백 UI만**(서버 푸시·자동 주입 로직 없음). 트리거 규칙(실행 완료=N1, 방치된 진행건 알림, 미열람 결과)을 정의해 활성 세션에 메시지 주입(공통 경로) + 빈도 가드(스팸 방지, 세션당 일정 시간 1회). 서버 푸시 인프라(WebSocket)는 범위 밖 — **폴링/이벤트 기반**으로 시작.
- **리스크**: 활성 세션이 여러 개일 때 어디 넣을지(최신 1개 규칙), 중복 주입 방지(동일 run_id 1회), 다른 탭에서의 unread 동기화(채팅 마운트 시 last-read 비교).

### N1 — 직접 실행(시뮬/제너) 완료 → 자동 개선 제안 (V1·V2 의존)

**목표** 채팅이 아닌 **전용 페이지(`/simulation`·`/generator`)에서 직접 돌려 결과가 나와도**, 챗봇이 자동으로 "개선하시겠어요?" 제안 메시지를 생성(채팅 세션에 적재).
**구현** 시뮬/제너 완료 이벤트(또는 status COMPLETED 감지)를 채팅 측이 받아 해당 프로젝트 세션에 개선 제안 메시지(`ApprovalWidget(run_generator/rerun_simulation)`)를 append. 채팅에서 돌린 경우와 동일한 개선 루프로 연결.
**완료 기준** `/simulation`·`/generator`에서 직접 실행 후, 채팅에 개선 제안 메시지가 자동으로 생김. Preview로 직접실행→채팅확인까지 검증(3역할).

### N2 — 안읽음 빨간 뱃지 배선·검증 (이미 구현됨, N1 의존)

**현황** 뱃지 UI·상태는 **이미 존재** — [FloatingChat.tsx:76-80](frontend/src/components/chat/FloatingChat.tsx) 빨간 뱃지(`bg-[#F04452]`, `9+`), `unread`/`pushUnread()`/`clearUnread()`(ChatController). 신규 구현 아님.
**목표** N1/N4가 메시지를 주입할 때 **패널이 닫혀 있거나 다른 페이지/탭에 있어도** 뱃지가 증가하도록 `pushUnread()` 호출을 연결. 채팅 진입 시 `clearUnread()`로 0.
**구현** N1/N4 주입 경로에서 패널 closed면 `pushUnread()` 호출. 다른 탭에서 도착한 경우, 채팅 마운트/폴링 시 last-read 대비 새 메시지 수로 `unread` 보정.
**완료 기준** 프로액티브 메시지 발생 시(다른 페이지 포함) 뱃지 숫자 증가, 채팅 열면 사라짐. Preview 확인.

### N3 — 채팅이 sim/gen status 동기화 (타 탭 진행, G4 의존)

**목표** 사용자가 시뮬/제너를 돌리다 **다른 탭/페이지로 이동**해도, 채팅이 **status를 받아와** 진행 중이면 로딩 스피너, 완료되면 기존 **결과 요약 위젯**을 보여줌.
**구현** 채팅이 진행 중 run_id/generation_id(localStorage/세션)를 알고 있으면 status 폴링(`/api/simulation/{id}/status`·제너 status[G4]) → RUNNING이면 스피너 위젯, COMPLETED면 결과 요약 위젯으로 전환. 표면(페이지) 바뀌어도 일관.
**완료 기준** 전용 페이지에서 시작 → 채팅 탭으로 이동 시 진행 스피너 표시, 완료 후 결과 요약 위젯 표시. 진행 중 새로고침에도 유지. Preview로 멀티탭/이동 검증.

### N4 — 선제적 말걸기 챗봇 (먼저 말 검, N1·N2 의존)

**목표** 사용자가 먼저 말 걸지 않아도 챗봇이 **먼저 말을 거는** 경험(카톡처럼). 트리거 예: 결과 나온 뒤 개선 제안(N1), 한동안 방치된 진행건 알림, 새 인사이트·다음 액션 추천.
**구현** 프로액티브 메시지 트리거 규칙 정의(이벤트 기반: 실행 완료·이상 신호·미열람 결과) → 세션에 메시지 생성 + N2 뱃지. 과하지 않게 빈도 가드(스팸 방지). 기존 프로액티브 푸시(T18) 인프라 확장.
**완료 기준** 정의된 트리거에서 챗봇이 먼저 메시지를 보냄(스팸 아님), 뱃지로 표시. Preview로 트리거 재현·검증.

### X1 — 에러 UX 통일 + 재시도 (sim/gen/chat)

**목표** 시뮬·생성·채팅의 에러 처리를 **공통 에러 카드 + 재시도**로 통일(현재 제각각). 사용자 친화 메시지(키 없음/한도/네트워크 구분).
**완료 기준** 세 흐름 모두 동일한 에러 카드·재시도 동작. Preview 확인(임의 실패 유발).

### X2 — SSE 자동 재연결 (backoff 재구독)

**목표** 스트리밍이 네트워크로 끊기면 지수 backoff로 자동 재구독(시뮬은 `onerror`에서 결과 조회만 함). 긴 시뮬/생성 중 일시 끊김 복구.
**완료 기준** 연결 끊김 후 자동 재시도·복구. (백엔드 status/재개와 연계.) Preview 확인.

### X3 — 동시실행 가드 통일 (sim·gen 슬롯)

**목표** `runningJobs`의 sim·gen 슬롯 관리를 일관화 — 진행 중 같은/다른 작업 동시 시도 시 명확히 차단·안내. 슬롯 누수(완료 후 미해제) 점검.
**완료 기준** 동시실행 시도 일관 차단, 완료/에러 시 슬롯 정상 해제. Preview 확인.

### X4 — 라우팅 분류 정확도 개선 + 로그

**목표** 오케스트레이터 의도 분류 오분류 보정("요약해줘"가 목록으로 새는 등). 분류 결과 로깅으로 추적(handoff T20 참고).
**완료 기준** 대표 질문 셋에서 오분류 감소, 분류 로그 남김. Preview/로그 확인.


## 5. 완료 작업

> 완료(✅) 태스크의 상세 명세·진행 로그는 git 로그 참조(이전 §5/§4-L 등). 남은/새 작업은 §1 표·§1-A·§4(부분)에 있다.
