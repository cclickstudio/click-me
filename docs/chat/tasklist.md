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
| ★N5 | 라우트 변경마다 알림 폴링 + 플로팅 챗 벨 버튼·알림 패널 | 능동 | N2 | ✅ |
| ★N6 | 제너 전용 세션에 시뮬 선제 알림 오는 버그 수정 | 능동 | N4 | ✅ |
| ★N7 | 새 채팅 진입 시 최근 시뮬/제너 기반 다음 단계 제안 | 능동 | V1,V2 | ⬜ |
| ★F13 | 채팅 세션 자동 제목(첫 user 메시지 LLM 요약) | 기능 | —      | ✅   |
| ★G5 | 제너 필수 입력값 확실히 받기·검증(누락 차단·안내) | 제너 | V2 | ✅ |
| ★G6 | /new 생성 직후 gen_form 재노출 라이브 글리치 수정 | 제너 | G3 | ✅ |
| ★L9 | 롱텀 메모리(시뮬/제너 입력 기억→채팅 반영) 검증 | 검증 | F5,L8 | ⬜ |
| ★LOOP | 시뮬↔제너 양방향 개선 루프(최대 3턴) 구현·검증 | 핵심 | V2 | ✅ |
| ★A1 | JWT 인증·인가 일관 적용(chat/gen/sim/personas 라우트 소유권 검증) | 보안 | — | ✅ |
| ★G7 | 제너 시안 3개에 기대성과 순위 부여 | 제너 | V2 | ✅ |
| ★AB | A/B 테스트 — 두 시안을 같은 패널로 시뮬·비교·승자 판정 | 핵심 | V1 | ✅ |
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
| X1  | 잘못 추가된 `click-me` 자기참조 gitlink 제거(깨진 서브모듈) | 정리 | — | ⬜ |
| X2  | G5 라이브 HTTP 422 왕복 재검증(백엔드 클린 재기동 후) | 검증 | G5 | ⬜ |
| C4  | 시뮬+채팅 전수 QA(대기업 QA 수준)·결함 리포트 후 push | 정리 | 전부 | ⬜ |

> **상태 메모(2026-06-25)** — 제너 403 **해소됨**(org 인증 완료, image_generation gpt-4o-mini/gpt-image-1 실호출 OK). V2 검증 완료. 워크트리(kb·be·fe) 통합 완료. 브랜치 `feat/chat-doyeon`.
>
> **세션 인계(2026-06-25 밤, 집)** — 다음 ⬜는 권장 순서상 **G6**(생성 직후 gen_form 깜빡임). 원인 가설: `ChatConversation.tsx` 렌더 key가 `key={i}`(인덱스)인데 낙관적 메시지엔 id가 없어(`Message.id`는 DB 영속분만), `/new` 세션 생성·refetch 시 GenFormWidget이 재마운트→내부 `phase`가 'form'(빈 폼 1/4)으로 리셋. sim 경로와 차이는 라이브로 확정 필요. **반드시 백엔드 클린 재기동 후 Claude Preview로 `/new` 제너 흐름 라이브 재현부터.**
> - **G5 완료(✅, a1fc34e)** — 단, **라이브 HTTP 422 왕복은 미검증**(단위 검증만 완료). 당시 8000에 좀비 프로세스가 점유·reload 불응으로 수정본을 못 올림. → **X2**로 분리(백엔드 클린 재기동 후 확인).
> - **환경 주의** — 8000 포트에 안 죽는 좀비(taskkill·--reload 불응) 이력 있음. 백엔드가 옛 코드를 들면 작업관리자에서 python.exe 종료 또는 재부팅 후 `uv run dev.py` 클린 재기동. 좀비 살아있으면 라이브 검증 무의미.
> - **LTM 미커밋 변경은 도연님이 `80c8264`로 커밋 완료** — 단 그 커밋에 잘못된 `click-me` 자기참조 gitlink(mode 160000, `.gitmodules` 없음)가 섞임 → **X1**로 제거 필요. 그 외 작업트리는 깨끗.

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

**✅ 완료(2026-06-26, N5·N6 함께)** 도연님이 **서버 저장(DB 마이그레이션) 승인** → 명세대로 server-side last-read로 구현.
- **DB(승인됨)** `chat_sessions.last_read_at`(nullable) 추가 — [027 마이그레이션](backend/alembic/versions/027_add_chat_session_last_read.py)·[models.py](backend/core/models.py). NULL이면 전체 미확인. (개인 DB에 alembic upgrade 027 적용 완료. 리포에 다중 head 잔재 있어 `upgrade 027`로 타깃.)
- **백엔드** [history.py](backend/domain/chat/history.py) `list_sessions`에 unread_count(마지막 열람 이후 assistant 메시지 수) 추가, `list_notifications`(unread>0 세션 {session_id,title,preview,unread_count}), `mark_session_read`. [chat.py](backend/api/routers/chat.py) `GET /chat/notifications`·`POST /chat/sessions/{id}/read`(소유권 검증).
- **프론트(N5)** api.ts notifications·markRead. [FloatingChat.tsx](frontend/src/components/chat/FloatingChat.tsx) — usePathname 변경마다 알림 폴링, 접힘 상태 좌측 **벨 버튼+배지**, 클릭 시 **알림 패널**(제목·미리보기·개수) → 항목 클릭 시 `router.push(/chat/{pid}/{sid})`+읽음. [ChatSessionSidebar.tsx](frontend/src/components/chat/ChatSessionSidebar.tsx) 세션 행 **미확인 빨강 배지**(활성 세션 제외). [ChatConversation.tsx](frontend/src/components/chat/ChatConversation.tsx) 세션 열람 시 markRead.
- **프론트(N6)** N4 선제 폴링(`runProactiveCheck`)에 **도메인 가드** 추가 — 세션 위젯이 gen만 있고 sim이 없으면(제너 전용) 즉시 return(시뮬 알림 본문 주입 안 함). sim/일반 세션은 종전대로.
- **검증(라이브 Preview, USER doyeon)** ① 백엔드 HTTP: notifications 64건·sessions unread_count·mark_read 후 unread 0. ② **벨/패널**: /dashboard에서 벨 배지 '9+', 패널 '미확인 알림(63)'·항목 64개(제목·미리보기·개수), **항목 클릭→세션 이동(/chat/.../8a3b9995)**·DB last_read_at 세팅·unread 0 확인. ③ **사이드바**: /chat 세션 행 빨강 배지 63개(활성 제외). ④ **N6 A/B 실증**: 가드·seen 초기화 후 — **제너 전용 세션(95850606)→시뮬 알림 주입 0**(guard 미세팅=게이트 early return), **시뮬 세션(8a3b9995)→주입 O**(guard 세팅). 같은 조건 대조로 게이트 정확 동작 확인. ⑤ 콘솔 에러 0·tsc/eslint/ruff 통과.
- **테스트 부산물** N6 positive control로 시뮬 세션(8a3b9995)에 선제 알림 1건 영속(무해, 그 세션은 원래 시뮬 알림 보유).

### ★N7 — 새 채팅 진입 시 최근 시뮬/제너 기반 다음 단계 제안

**목표** 사용자가 시뮬레이션이나 제너레이터를 돌린 뒤 **새 채팅**을 열면, 챗봇이 먼저 다음 단계를 제안한다. 가장 최근 활동이 **시뮬이면 "개선하시겠어요?"**(개선 시안 생성 유도), **제너면 "시뮬레이션 해보시겠어요?"**(반응 예측 유도). 시뮬↔제너 루프의 새-채팅 진입점.
**구현** 빈 채팅(messages 0) 진입 시 프로젝트의 최근 sim·gen 목록을 받아 created_at으로 가장 최근 활동을 판별 → 그 반대 방향을 제안하는 카드(웰컴 칩 위)를 띄운다. 클릭 시 해당 흐름(sim→`/제너레이터`·개선 모드, gen→`/시뮬레이션`) 시작. 최근 활동 없으면 카드 미표시(기존 웰컴 그대로).
**완료 기준** 시뮬 직후 새 채팅 → "개선" 제안 카드, 제너 직후 새 채팅 → "시뮬레이션" 제안 카드. 클릭 시 해당 폼/흐름 진입. 활동 없으면 미표시. Preview로 양방향 확인.

**✅ 완료(2026-06-26)** 프론트만([ChatConversation.tsx](frontend/src/components/chat/ChatConversation.tsx)). 빈 채팅(messages 0)·projectId일 때 `api.projects.simulations`·`generations` 최근 5건을 받아 created_at 최댓값을 비교 → `simTs>=genTs`면 'improve'(개선=제너 제안), 아니면 'simulate'(시뮬 제안). 둘 다 0이면 카드 미표시. 웰컴 칩 위에 제안 카드(클릭 시 sim→`/제너레이터`·gen→`/시뮬레이션` 슬래시 실행).
- **검증(라이브 Preview, USER doyeon)** 새 채팅 진입 → **"광고 시안을 만드셨네요 — 시뮬레이션 해보시겠어요?"** 카드 렌더(개인 DB의 최근 *영속* 활동이 제너 — AB sim-batch는 메모리 런이라 미영속이므로 제너가 최신, 로직 정확). **카드 클릭 → 웰컴 사라지고 sim_form 위젯(입력 4종) 진입** 확인. 콘솔 에러 0·tsc/eslint 통과.
- **부분 검증(정직 표기)** 'improve'(시뮬 최신→"개선하시겠어요?") 방향은 **코드 대칭으로 검증** — 동일 버튼의 삼항 분기(텍스트/아이콘/슬래시만 다름)이고 `/제너레이터`는 타 작업(G7·AB·웰컴 칩)에서 동작 확인됨. 영속 시뮬을 최신으로 만들려면 실 시뮬 1회가 필요해 라이브 픽셀은 미강제(로직·렌더 경로는 동일).

### ★F13 — 채팅 세션 자동 제목 (첫 user 메시지 LLM 요약)

**증상** 빈 화면 칩으로 새 채팅 열면 제목이 `새 채팅`이거나 첫 입력값이 그대로 제목이 됨.
**목표** 여느 LLM처럼 **첫 user 메시지를 보고 작업을 짧게 요약한 제목**을 생성(예: "수분크림 광고 시안 생성", "20대 타깃 시뮬 분석").
**구현** 세션의 첫 user 턴 직후(또는 첫 응답 후) gpt-4o-mini로 한 줄 제목 생성 → `ChatSession.title` 갱신(append-only, 한 번만). 위젯 트리거(시뮬/제너 폼)로 시작한 세션도 첫 의미 있는 입력 기준으로.
**완료 기준** 새 세션 제목이 첫 작업을 요약한 자연어로 자동 설정, 사이드바 반영.

**✅ 완료(2026-06-26)** 백엔드만([history.py](backend/domain/chat/history.py)). 기존 append_turn은 첫 user 발화 원문[:60]을 그대로 제목으로 썼는데, 이를 **gpt-4o-mini 요약 제목**으로 업그레이드.
- **비차단 설계** 응답 지연 0 — append_turn이 ① 즉시 원문[:60]을 fallback 제목으로 넣고 커밋 → ② 커밋 후 `_spawn_title_generation`으로 detached task를 띄워 LLM 요약(`_generate_session_title`)으로 비동기 교체. 커밋 후 스폰이라 백그라운드 task가 fallback을 정확히 읽어 교체(읽기 레이스 회피). LLM 실패·키없음·mock이면 fallback 유지, 사용자가 그새 직접 바꿨으면 안 덮음(title==fallback일 때만 갱신).
- **검증(라이브 Preview, USER doyeon)** 새 채팅에 "수분크림 광고 카피를 20대 여성 타깃으로 잘 쓰는 법 알려줘" 전송 → **DB 직접 조회**로 title이 원문이 아닌 **'20대 여성 수분크림 광고 카피'**(LLM 요약)로 설정 확인, 사이드바에도 그 제목 렌더, 콘솔 에러 0. ruff 통과. (기존 세션 제목은 불변 — 신규만 적용.)

### ★G5 — 제너 필수 입력값 확실히 받기·검증

**목표** 제너레이터가 **필수 입력값**(상품명·상품설명·타깃·저장 프로젝트 등)을 누락 없이 받아 실행되게. 누락 시 실행 차단 + 명확한 안내.
**구현** gen_form 필수 필드 검증(빈 값이면 "실행" 비활성·안내), 백엔드 `GenerationCreateRequest` 필수값 검증·422 메시지 정합. 어떤 값이 필수인지 폼·백엔드 일치.
**완료 기준** 필수 누락 시 실행 불가·안내, 모두 채우면 정상 생성. 빈 입력 엣지 케이스 Preview 확인.

**✅ 완료(2026-06-25)** 프론트만 수정(백엔드 검증은 이미 존재 — `GenerationCreateRequest.model_validator`가 create 모드 필수 3종 422, 라우터가 project_id 누락 400). 추가로 **422 메시지 정합 버그**를 발견·수정.
- `GenFormWidget.tsx`: 최종 "광고 생성 실행" 버튼을 `projectId`만이 아니라 **필수 4종(상품명·상품설명·타깃·저장 프로젝트) 전부**(`allValid`)로 가드. 최종 단계에 누락 항목 안내(`필수 항목을 입력해주세요: …`), 프로젝트 없음 시 안내문 추가. 단계별 "다음"은 기존대로 빈 값/공백 차단(`trim()`).
- `api.ts`: `request()`가 FastAPI 422의 **배열형 `detail`**(`[{loc,msg,type}]`)을 그대로 `new Error`에 넘겨 `[object Object]`로 깨지던 것을 `errDetail()`로 정규화(배열이면 `msg` 추출·join).
- **별건 버그 발견·수정(공유부 `api/main.py`)** 커스텀 422 핸들러 `JSONResponse(content={"detail": exc.errors()})`가 **`TypeError: Object of type ValueError is not JSON serializable`로 크래시**(model_validator의 `ValueError`가 pydantic v2 `ctx`에 직렬화 불가 객체로 섞임) → 응답이 CORS 헤더 없이 깨져 프론트는 "Failed to fetch"만 봄. `jsonable_encoder(exc.errors())`로 수정(라우터 등록·시그니처 불변, 핸들러 본문 버그 수정).
- **검증** ① 프론트 게이팅 **라이브 Preview(USER doyeon)** — 상품명 공백→"다음" 비활성(`trim` 적용), 4단계 모두 채우면 "광고 생성 실행" 활성·프로젝트 자동선택(건도연)·안내 미표시 확인(DOM). ② 백엔드 422 직렬화 버그·수정은 **단위 검증으로 결정적 확인** — `json.dumps(exc.errors())`는 `TypeError`, `jsonable_encoder(exc.errors())`는 한국어 메시지("생성모드 필수 필드 누락: product_name, product_description, target_audience") 담은 유효 JSON 생성. ③ 라이브 400(project_id 누락)은 브라우저 cross-origin 정상(메시지 수신).
- **미검증(환경 차단, 정직 표기)** 라이브 **HTTP 422 왕복**은 재현 못 함. 8000 포트를 세션 시작부터 점유한 3개 좀비 프로세스(PID 13048/11808/51812)가 taskkill·Stop-Process·--reload에 모두 불응 + 명령 실행 백로그 심함 → 실행 중 백엔드에 수정본을 못 올림(8001 대체 기동도 미기동). **수정본은 디스크에 반영·단위 검증 완료, 백엔드 클린 재기동 시 적용됨.** 사용자 백엔드는 그대로 동작 중(좀비는 세션 시작부터 존재, 내가 만든 것 아님). 3역할 중 USER만 라이브 확인(게이팅 로직은 역할 무관 동일 컴포넌트).

### ★G6 — /new 생성 직후 gen_form 재노출 라이브 글리치 수정

**증상** `/new`에서 제너 **생성 직후(새로고침 전)** gen_form이 빈 폼(1/4)으로 잠깐 다시 보이고 gen_result 이미지 로딩이 지연됨. 새로고침하면 정상.
**원인 추정** 세션 생성 전환(shallow routing) 중 로컬 gen_form 위젯 재마운트 + gen_result가 아직 숨김 처리 전. (sim은 매끄러운데 gen 경로 차이 확인 필요.)
**완료 기준** 생성 직후 라이브로 gen_result 위젯이 자리에 표시되고 gen_form이 깜빡이지 않음(새로고침 불필요).

**✅ 완료(2026-06-26)** 진짜 원인은 stale-closure 클로버였다. `handleGenComplete`가 `await appendWidgetMessages([gen_result])`로 결과 위젯을 붙인 직후 `handleSend("[생성결과]…")`를 부르는데, 생성 시작 시점에 캡처된 `handleSend` 클로저의 `const base = messages`가 **gen_result 추가 이전의 stale 스냅샷**이라 `setMessages(newMessages)`가 배열을 통째로 덮어써 gen_result를 지웠다 → gen_form 숨김 조건(뒤에 gen_result 있으면 숨김)이 false로 뒤집혀 gen_form이 다시 떴다(DB엔 남아 새로고침하면 정상). 시뮬은 `handleSimComplete`가 handleSend를 안 불러 무사.
- **수정**([ChatConversation.tsx](frontend/src/components/chat/ChatConversation.tsx)) `handleSend`에서 `const base = messages`(stale) → `const base = messagesRef.current`(라이브 ref), 추가는 `setMessages(prev => [...prev, userMsg])` 함수형 업데이트로 변경(동시 append 비클로버). 요청 바디용 `newMessages`는 라이브 base로 구성. deps에서 `messages` 제거(콜백 안정화). tsc·lint 통과.
- **검증(라이브 Preview, USER doyeon, /new)** MutationObserver로 완료 전환 구간 감시 → **빈 gen_form(1/4) 재노출 0회**(`everEmptyFormReshow:false`), gen_result 즉시 표시·유지(이미지 3장 1024² complete), 새로고침 후에도 복원, 콘솔 에러 0. **DB 직접 조회**로 세션 메시지 3건(gen_result 위젯 1·`[생성결과]` user 1·재시뮬 제안 1) 정확 영속 확인(중복·유실 없음).
- **미검증(정직 표기)** admin·company 역할은 별도 유료 이미지 생성을 돌리지 않음 — 수정은 ChatConversation 공유 컴포넌트의 **역할 무관 클라이언트 상태 로직**이라 코드 경로가 동일. USER 1회로 충분히 결정적 확인.

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

**✅ 완료(2026-06-26)** 양방향 연결·3턴 한도는 이미 배선돼 있었고(이전 세션의 미커밋 분 — `api.ts loopState`·`orchestrator.gen_result_node` 3턴 차단·`DebateStreamWidget` loopState 폴링·approval 숨김), 이번에 **개선 컨텍스트 손실 버그**를 잡아 "개선이 누적"을 실제로 성립시켰다.
- **버그(라이브 확정)** 토론 후 "개선 시안 만들기"(run_generator) 수락 시 `/approve`가 맥락 없는 합성 질문 "개선 시안 만들어줘"를 오케스트레이터 run 분기에 넘김 → LLM 추출기가 **엉뚱한 상품을 환각**(라이브 8000 확인: gen_form이 `product_name:"개선 시안 서비스", target:"중소기업 및 스타트업"`으로 채워짐). 직전 시뮬한 광고가 통째로 유실 → 루프가 "개선"이 아니라 무관한 새 생성이 됨.
- **수정** ① [chat.py](backend/api/routers/chat.py) `ApproveRequest.context`(additive) 추가 + `_gen_form_from_sim_context()` — run_generator 수락에 직전 시뮬 광고 맥락이 오면 LLM 추출을 건너뛰고 그 광고를 gen_form 초기값으로 옮긴다(product_name←ad_title, description←ad_content+개선근거, target은 시뮬에 없어 비움). ② [ChatConversation.tsx](frontend/src/components/chat/ChatConversation.tsx) `loopCtxRef`를 시뮬 완료 시 채우고(handleSimComplete), `handleApprove`가 run_generator일 때 `context`로 전송. rerun_simulation은 기존 경로 유지(빈 sim_form — gen 후보 prefill은 F8 몫).
- **검증(라이브 8000, 내 수정 직전)** ★3턴 한도 enforce 완전 동작 — run_generator 수락 시 loop_count 1→2→3 증가, rerun_simulation은 비증가(sim_form), 4번째 run_generator는 `loop_done:true`로 차단("개선 루프 완료", 위젯 없음). 양방향 위젯 라우팅(run_generator→gen_form, rerun_simulation→sim_form)·환각 버그 모두 라이브 확인.
- **검증(수정 후)** `_gen_form_from_sim_context` 순수 로직 단위검증(실광고 prefill·근거 join·빈 컨텍스트 방어·빈 근거 필터 4케이스 정상). ruff/tsc/eslint 5개 파일 전부 통과.
- **검증(라이브 HTTP 왕복, 재부팅 재기동 후 2026-06-26)** ✅ 닫음 — context 포함 `/approve`(run_generator)에 한글 광고 맥락(UTF-8 바디)을 보내 **HTTP 200 + gen_form이 실제 광고로 prefill** 확인: `product_name:"제로콜라 여름 한정판"`, `product_description:"설탕 0, 칼로리 0…\n\n개선 방향: 신뢰도가 낮음 / 타깃 메시지 약함"`, `target_audience:""`(설계대로 사용자 입력 대기), `loop_count` 1로 증가. 동일 세션에서 **context 없는** 요청은 옛 환각(`product_name:"개선 시안 서비스"`) 재현 → context 분기가 정확히 갈림을 대조 확인. (당시 8000 좀비는 chat.py reload가 트리거 — 재부팅으로 해소.)
- **잔여(미검증)** **Preview UI 왕복**(시뮬→토론→수락→gen_form 자동 prefill 화면)은 미확인 — preview_start가 외부 기동된 3000을 인수 못 함(포트 점유 거부). 코드 경로는 라이브 HTTP로 결정적 확인됨. 풀 시뮬→제너→재시뮬 UI 왕복은 **V3**(실 시뮬/제너 실행 포함)에서.

### ★A1 — JWT 인증·인가 일관 적용 (보안, 우선)

**증상** 라우트마다 인증이 들쭉날쭉. `projects.py`는 `get_current_user`+`_project_access_ok`(org/team/생성자) 소유권 검증이 있으나, **`chat.py`·`generator.py`·`api/routers/simulation/*`·`personas.py`는 인증·스코핑이 전혀 없음**(`Depends(get_db)`만). 즉 `GET /chat/sessions?project_id=…`·`/chat/sessions/{id}/messages`·생성/시뮬 조회·삭제가 **토큰 없이/타인 ID 추측으로 접근 가능**. (CLAUDE.md "JWT 미적용·점진 도입"의 실체 — 보안 구멍.)
**목표** projects 패턴을 chat/generator/simulation/personas에 일관 적용 — `get_current_user` 의존 + 해당 리소스(세션·생성·시뮬)의 프로젝트 소유권 검증(같은 org/team/생성자만). 또는 전역 인증 미들웨어 + 라우트별 인가.
**완료 기준** 비인증 요청 401, 타 프로젝트 리소스 403. 3역할 정상 흐름 회귀(자기 데이터는 그대로). (범위가 크면 chat부터 단계 적용.)

**✅ 완료(2026-06-25)** 공용 인가 헬퍼 `core/access.py` 신설(`assert_project_access`·`assert_session_access`·`assert_message_access`·`assert_simulation_access`·`assert_generation_access` — projects.py 패턴 분리, 미존재 404·권한없음 403). 토큰이 흐르는 모든 데이터 엔드포인트에 `get_current_user`+소유권 적용:
- chat.py: sessions(목록/생성/메시지/삭제)·widget-messages·pin·advice-usage·result-summary·sim-batch·complete·approve·templates·keywords·feedback·kb-chunk·image 업로드.
- simulation/router.py: start/run(+project 검증)·status/result/analysis(로그인)·db-result(+시뮬 소유권). generator.py: create(+project 검증)·detail·download-zip·select·publish(+생성 소유권), 글로벌 목록은 admin 전용. personas.py: generate(+시뮬 소유권).
- 프론트 raw-fetch 5곳(`/chat/complete`×2·`/approve`·`/sim-batch`·`/download-zip`)에 `Authorization: Bearer` 부착.
- **검증(라이브 HTTP, 실제 3역할 토큰)** 401(무토큰 4종)·403(USER doyeon·COMPANY yohan 타 조직)·200(본인·admin 전체)·404(미존재)·admin 전용 글로벌 목록(USER 403) 모두 통과. `/chat/complete` 무토큰 401·본인 200·타 조직 403. **Preview UI(doyeon)** 실채팅 흐름 회귀 없음(세션 생성·진입·메시지 전송 `/chat/complete` 200 스트리밍·widget-messages·db-result 200, 콘솔 무에러).
- **미적용(헤더 전달 불가, 의도적 보류·문서화)** EventSource 스트림(`/simulation/{run_id}/stream`·`/generator/.../stream`) — 토큰 헤더 불가, 시작/생성 시점에 소유권 검증. `<img>`/`<a>` 미디어 프록시(`*/image`·`candidates/{id}/render`·`/chat/report` 다운로드) — S3 프리픽스 가드. `/simulation/categories`는 공개(레퍼런스). brand-profile/logo/product-image는 x_client_id 키(프로젝트 리소스 아님).
- **별건 발견** `/simulation/categories`가 개인 DB(ep-soft-band)에서 500 — `relation "categories" does not exist`(categories/category_kinds/kinds 테이블 미시딩). A1과 무관한 개인 DB 시딩 누락(손대지 않은 엔드포인트).

### ★G7 — 제너 시안 3개에 기대성과 순위 부여 (확정: 3개 유지)

**현황** 후보 **3개**(`copy_generator.py:115`·`explain.py`)로 확정(기획서 5개 → 사용자 결정 3개). 순위 로직이 약함.
**목표** 3개 시안에 **기대성과 순위**(예측 반응·QA 기반 정렬 + 근거 한 줄) 부여 — 결과 위젯·상세 페이지에서 "추천 1순위" 등 표시.
**완료 기준** 3개 시안이 기대성과 기준으로 정렬·근거 표시. (개수는 3 유지, 순위/근거만 보강.)

**✅ 완료(2026-06-26)** DB 스키마 변경 없이(공유 core/models.py 불변) **조회 시 QA 신호로 순위 산출**. 이미지 모델은 예측 CTR을 못 내므로 **카피 품질(QA 7항목 평균) 기반 상대 순위**로 한정(실측 환산 아님 — 기획 준수).
- **백엔드** [generator_service.py](backend/domain/generator/service/generator_service.py) `_rank_candidates`/`_candidate_quality` — get_detail에서 후보별 `quality_score`(QA 7항목 평균)·`rank`(QA통과→점수→idx 안정정렬)·`performance_summary`(만점 강점 상위 2개 + 품질점수) 부여 후 기대성과순 정렬. 둘 다 사용하는 GenResultWidget·상세가 동시 수혜.
- **프론트** GenResultWidget(채팅)·상세 CandidateCard에 순위 배지(⭐/🏆 1순위 추천·N순위)·근거 한 줄 표시, rank순 정렬.
- **별건 버그 발견·수정(fix)** 상세 페이지([generations/[id]/page.tsx](frontend/src/app/(app)/generations/[id]/page.tsx))가 `/api/generator/generations/{id}`를 **토큰 없이 raw fetch** → A1로 인증이 붙은 뒤 **401로 상세 페이지 전체가 "불러올 수 없습니다"로 깨져 있었음**(A1 누락분, 모든 사용자 영향). Authorization 헤더 부착으로 수정.
- **검증(라이브 Preview, USER doyeon)** ① 백엔드 detail API HTTP 200·rank 1/2/3·summary 정상. ② **상세 페이지**: 401 수정 후 정상 로드, 배지 `🏆 1순위 추천/2순위/3순위`·`기대성과 CTA 명확 · 타깃 적합 · 품질 100점` 렌더. ③ **채팅 GenResultWidget**: 기존 [생성결과] 세션 열어 `⭐ 추천 1순위/2순위/3순위`·요약 렌더. ④ 콘솔 에러 0·tsc/eslint/ruff 통과. (이 생성은 3후보 QA 만점 동점이라 idx 안정정렬 — QA 차이 나면 순위 갈림.)

### ★AB — A/B 테스트 (두 시안을 같은 패널로 시뮬·비교·승자 판정)

**배경/현황** 기획서 "A/B UI 선반영" — **입력·비교 위젯 자산은 이미 있음**: `BatchSimWidget`(batch_sim_form, 광고 2개 동시 비교 시뮬)·`/배치`·`/AB` 슬래시(S1)·`ComparisonWidget`(F12, 시뮬 2개 4대 KPI 델타 비교). **빠진 "실기능" = 공정 비교 + 통계적 승자 판정**.
**목표** 두 광고 시안(A·B)을 **동일 페르소나 패널**로 시뮬레이션해 4대 KPI를 나란히 비교하고, **신뢰구간 겹침을 고려한 승자 판정**(A 우세 / B 우세 / 유의차 없음) + 근거 제시.
**설계(새 세션이 바로 구현하게 상세)**
1. **입력 — A/B 두 시안.** 소스 3종 지원: ① 수동 2개(batch_sim_form 재사용) ② 제너 생성 후보 중 2개 선택 ③ 기존 시뮬 2개 선택(F12 경로). 진입: `/AB`(이미 batch_sim_form 띄움) 또는 결과 위젯의 "A/B 비교" 액션.
2. **★공정 비교(핵심).** 두 시안을 **같은 페르소나 패널**(동일 표본·동일 OCEAN 분포)로 평가해야 비교가 유효. 현재 batch_sim이 2개 독립 시뮬(다른 표본)이면 교란 → **같은 패널 재사용 옵션**을 시뮬 백엔드에 추가(첫 시뮬의 personas를 두 번째에 주입, 또는 한 패널에 두 광고 노출). `domain/simulation`의 페르소나 생성·반응 경로 확인. 시그니처는 append-only, 기존 단일 시뮬 경로 불변.
3. **통계 비교.** 각 KPI(클릭의향률·구매의도·신뢰도·거부율)의 평균+신뢰구간(이미 산출됨, ci_low/ci_high)으로 A vs B **유의성** 판정 — CI 겹치면 "유의차 없음", 안 겹치면 우세 시안. 기획서 통계 정직성(점추정 단언 금지·분포 표기) 준수. 단순 평균 비교 ❌, CI 기반 ⭕.
4. **출력 위젯.** `ComparisonWidget`(F12) 확장 — 두 시안 4 KPI 나란히 + 델타 + **승자 배지**("클릭의향 A 우세(유의)"·"구매의도 차이 없음") + 한 줄 권고("A가 클릭의향에서 유의하게 높음 → A 권장"). 이미지 시안이면 썸네일.
5. **루프 연계.** 승자 시안을 LOOP(개선 루프)·F8(이 후보로 시뮬)로 이어갈 수 있게.
**기존 자산** `BatchSimWidget`·`ComparisonWidget`·`/배치`·`/AB`(ChatConversation runSlashCommand)·시뮬 결과 CI.
**완료 기준** 두 시안을 동일 패널로 평가 → 4 KPI CI 비교 → 유의 기반 승자 판정·권고 위젯 표시. **유의차 없으면 "차이 없음"으로 표기(무조건 승자 단언 금지).** Preview로 A/B 한 쌍 검증.
**소유권** 시뮬 도메인(자기). "동일 패널 재사용"만 백엔드 변경(append-only).

**✅ 완료(2026-06-26)** 핵심 발견 — **"동일 패널 재사용"은 백엔드 변경 불필요**(이미 충족). `PanelSpec.seed` 기본값 0이고 `load_panel`이 시드를 덮지 않으며 `PersonaSampler.sample`의 유일한 엔트로피가 `random.Random(spec.seed)`, persona_id도 `P-{idx}` 결정적 → **같은 spec이면 완전히 동일한 패널**. 배치 시뮬은 두 광고 모두 기본값(size 10·필터 없음·proportional)으로 호출 → 같은 패널. **실증**: 동일 spec 2회 샘플링이 persona_id·OCEAN·인구 전부 일치 확인(탐색 에이전트의 "독립 표본" 주장은 오류). 따라서 공정 비교는 구조적으로 성립, 남은 건 **통계 승자 판정 위젯**뿐.
- **구현(프론트만)** [BatchSimWidget.tsx](frontend/src/components/chat/BatchSimWidget.tsx) — ① 결과 표에 신뢰도(trust_avg) 추가(4 KPI 전부)·클릭 의향률에 CI(ci_low–ci_high) 동반 표기. ② `judgeWinner` — **클릭 의향률(유일한 CI 보유 KPI)의 CI 겹침**으로 유의성 판정: 겹치면 `유의차 없음`(tie), 분리되면 `우세(유의)`(win), CI 없으면 `참고용(유의성 판정 불가)`(weak), 한쪽 실패면 판정 없음. ③ `pointLead` — 작은 표본에서 클릭 의향률이 0/0로 겹쳐 'tie'만 나오는 한계 보완: 4지표 점추정 우세 개수를 **'참고(점추정)'로 명시**(유의성 아님) 별도 라인. ④ "같은 AI 소비자 패널로 평가" 주석·점추정 단언 금지 명시.
- **검증(라이브 HTTP + 로직)** ① `/api/chat/sim-batch` 2광고(강/약) 실행 → **HTTP 200**, 두 광고 모두 `ci_low/ci_high/trust_avg/effective_n` 포함 반환(같은 패널). ② 그 **실데이터**(둘 다 click 0·CI[0,0])를 `judgeWinner`에 통과 → `유의차 없음`(클릭 의향률 진짜 동일) + `참고: A_강력 3/4`(거부율 12.5% vs 100%·구매 2.25 vs 1.3 반영) — 정직·유용 둘 다 성립. ③ judgeWinner/pointLead 5케이스(실데이터·CI분리→승자·CI겹침→무승부·CI없음→참고용·한쪽실패→null) 전부 정상. ④ tsc/eslint 통과.
- **검증(라이브 Preview UI, 2026-06-26)** ✅ — 도연님이 3000을 양보→preview_start로 인수. USER doyeon 로그인→건도연 프로젝트→새 채팅→`/AB`→batch_sim_form 렌더→2광고(강/약) 입력→실행→완료 대기→**위젯 라이브 렌더 확인**: 🏆 A/B 판정 배너 `유의차 없음`(둘 다 click 0이라 정확), detail "신뢰구간이 겹쳐…", 점추정 라인 "참고(점추정): A_강력가 4개 지표 중 3개에서 앞서요", 4 KPI 표(클릭 의향률 0%+CI 0–0% 동반·구매 2.11 vs 1.10·신뢰 2.78 vs 2.30·거부 44% vs 90%), 동일 패널 주석까지 전부 표시. **콘솔 에러 0**. 스크린샷 증거 확보.
- **미구현(범위 밖, 명시)** 입력 소스 ②제너 후보 2개·③기존 시뮬 2개(F12 경로) 선택은 미연결(현재 batch_sim_form 수동 2광고만) — 별 위젯/플로우라 분리. 승자→LOOP/F8 이어가기 버튼도 미연결(F8 몫).

### ★V6 — PDF 리포트 생성 end-to-end 검증

**목표** 시뮬/토론 결과의 **PDF 리포트**(백엔드 Playwright Chromium, `debate.py:161 /report.pdf`)가 끝까지 생성·다운로드되는지 검증(콜드·새로고침 진입의 saved report 폴백 포함). `/리포트`·report_ready 위젯 경로.
**완료 기준** 리포트 다운로드 → 유효 PDF(내용·KPI·근거). 콜드 진입에서도 saved report로 재조립.

### ★V7 — 동시실행 가드(sim·gen 슬롯) 검증

**목표** sim/gen 동시 실행 시도 시 차단·안내(`runningJobs` 슬롯)가 실제 동작하는지, 완료/에러 후 슬롯 해제되는지 검증. V2 미검증 항목.
**완료 기준** 진행 중 같은/다른 작업 동시 시도 차단, 완료·에러 시 정상 해제.

### C4 — 시뮬+채팅 전수 QA (대기업 시니어 QA) 후 push

> 새 QA 세션에 그대로 써도 되는 완전 명세. 루프가 C4에 도달하면 이대로 수행한다.

**역할** 대기업에서 "이 사람 없으면 릴리스 못 한다"는 소리를 듣는 시니어 QA 엔지니어. 적대적이고 집요하다. 화면이 "떴다"는 통과가 아니다. 임무는 시뮬레이터(4-1)+채팅(4-4)에서 "뭐가 실제로 안 되는지"를 미세한 것 하나까지 찾아 증거와 함께 기록 — 통과 도장이 아니라 결함 발굴이 목표.

**절대 원칙 (어기면 QA 실패)**
1. **빈 값·누락·이상 징후를 절대 그냥 넘기지 마라.** 위젯이 빈 채로 뜨거나 값이 0/null/"-"/"준비 중"으로 멈추거나 스피너가 안 끝나거나 숫자가 안 맞으면 → 다음으로 넘어가지 말고 그 자리에서 멈춰 원인 규명(preview_console_logs·preview_network 응답본문·백엔드 로그·필요시 DB 직접 조회)해 "왜 비었는지" 확정·결함 기록.
2. **"떴다"로 끝내지 마라.** 비동기는 완료까지 폴링 대기(시뮬/제너 수십 초~분). 스피너만 보고 ✅ 금지. 결과 위젯·KPI·후보 이미지가 실제 값으로 채워졌는지 끝까지 본다.
3. **영속성·복원 반드시.** 진행 중 새로고침→스피너/진행 복원, 완료 후 새로고침→결과 복원, 세션 URL 직접 재진입→메시지·위젯 복원 셋 다.
4. **엣지·에러 직접 유발.** 빈/공백/초장문/특수문자 입력, 동시 실행(시뮬 도는 중 또 시뮬/제너), 네트워크 끊김(preview_eval offline 토글), 키 한도를 실제로 만들어 에러 카드·재시도·가드가 도는지. "에러 안 남"이 아니라 "에러를 우아하게 처리"가 정상.
5. **콘솔 무에러.** 흐름 내내 preview_console_logs에 error/warning 없어야. 하나라도 있으면 원인까지 기록.
6. **3역할 전부 반복.** admin·company·user 각각 로그인해 동일 흐름 재현. 역할 게이팅·자기 데이터 한정 확인. 역할별 차이는 역할 명시.

**전제 (최초 1회만)**
- **개인 DB 확인**: `cd backend && uv run python -c "from core.config import settings;import re;print(re.search(r'@([^/]+)/',settings.database_url).group(1))"` → `ep-soft-band-…` 여야 함. `ep-spring-wind-…`(팀 DB)면 중단·`.env` 고침.
- **서버는 도연님이 직접 띄워둠(프론트 3000·백 8000). 새 dev 서버/백그라운드 쉘 띄우지 말 것** — `preview_list`로 떠 있는 서버 재사용. 안 떠 있으면 직접 띄우지 말고 도연님께 알림.
- 폰트 `frontend/src/app/fonts/NotoSansKR-*.otf` 5종, `OPENAI_API_KEY` 필요(시뮬/제너/임베딩 실호출).
- **테스트 계정(개인 DB 전용, 평문)**: admin/admin1234, yohan/yohan1234(COMPANY), doyeon/fjdksla0852(USER). doyeon에 프로젝트 "건도연"(`8b33546d-e763-44fb-a222-6f02ba9a6707`).
- 로그인은 `/sign-in`에서 preview_fill+preview_click. 또는 토큰 주입: `create_access_token('<user_id>','<ROLE>')` → preview_eval로 `localStorage.setItem('clickme_token','<토큰>')`.
- **검증은 전부 Claude Preview(preview_*)로** 직접. 증거는 preview_screenshot·preview_console_logs·preview_network.
- DB 직접 조회: `AsyncSessionLocal`로 `chat_sessions`·`chat_messages`·`simulations`·`generations` 등 직접 확인.

**체크리스트 (미세한 것까지)**
- **A. 채팅 기본** — /chat 진입·빈상태 칩, SSE 토큰 스트리밍 끊김 없음·전송중 중복차단, 사이드바 목록/정렬/하이라이트·자동제목(F13 — "새 채팅"인 채면 결함), 세션 생성/삭제·라우팅 정합, 새로고침·URL 재진입 복원, 플로팅 챗 노출/숨김·알림 벨/배지(N5), 슬래시 전부 1회씩·잘못된 인자 처리, IME 조합중 Enter 오전송·Shift+Enter·초장문·빈 메시지 차단.
- **B. 시뮬 (채팅 내 + /simulation 둘 다)** — 입력 단계 진행/뒤로·카테고리/목표/인구 옵션·필수 누락 차단+안내, 실행→로딩→완료까지 대기→4대 KPI(클릭의향률·구매의도·신뢰도·거부율) 실제 값+CI/분포(점추정 단언·"예측 CTR" 환산 표기 있으면 기획 위반 결함), 토론 자동시작→스트림→요약·결과 직후 토론 동시 표시(타이밍), 개선 제안(Approval) 노출·수락, 진행중/완료후 새로고침 복원, 리포트 PDF 생성·다운로드·콜드 진입 saved 폴백, DB 직접 조회로 영속 대조.
- **C. 채팅 내 제너** — gen_form 필수값 누락 차단·안내(G5), 실행→완료 대기(이미지 ~1~2분 실비용)→후보 3개+헤드라인/전략·상세 이동, 생성 직후 gen_form 깜빡임/빈폼 재노출(G6)·gen_result 타이밍, 실패(키없음/한도/끊김) 에러 카드+재시도, 동시 실행 가드·완료/에러 후 슬롯 해제.
- **D. 메모리/RAG/능동** — 수 회 실행 후 명시 언급 없이 브랜드·제품군 인지(롱텀), 광고 용어 질문("ROAS가 뭐야" 등)→CLIO KB 근거+인용 칩, 제너 전용 세션에 시뮬 선제 알림 오염(N6).
- **E. 권한/게이팅(3역할)** — 비로그인/토큰 없음 보호 화면 차단, USER 타 프로젝트/조직 403·자기 데이터 정상, admin 전용 화면·API에 USER/COMPANY 차단.

**결함 처리** 발견 즉시 `docs/chat/qa-report-<날짜>.md`에 기록: 제목 / 심각도(S0 블로커·S1 심각·S2 보통·S3 사소) / 클릭 단위 재현 절차 / 기대 / 실제 / 증거(스크린샷·콘솔·네트워크 응답·DB 조회) / 추정 원인(파일:라인). **S3(한 줄 수정)만 그 자리 고치고 `fix:` 커밋**, S0~S2·불확실은 리포트만 하고 다음 진행(범위 폭주 방지). 추측 금지 — 재현·관찰한 것만, 못 한 검증은 "미검증" 명시.
**산출물(종료 시)** ① `docs/chat/qa-report-<날짜>.md`(결함 전체 심각도 정렬+역할별 차이). ② 채팅 요약: 검증 항목 수 / 결함 수(심각도별) / 즉시 고친 것 / 시뮬·채팅 각 실측 완성도 재평가(코드존재 아닌 "실제 통과" 기준) / 가장 위험한 결함 Top3.
**완료 기준** A~E 전 항목 3역할 재현·결함 리포트 작성·산출물 제출, S3 즉시 수정 반영. **그 뒤** 도연님 확인 받고 push.
**의존** 전부(구현 ⬜ 소진 후 마지막).

### X1 — 잘못 추가된 `click-me` 자기참조 gitlink 제거 (정리)

**배경** LTM 미커밋 변경은 도연님이 `80c8264`(add: 채팅 롱텀 메모리 임베딩)으로 정상 커밋함. 단 그 커밋에 **루트 `click-me`가 mode 160000(gitlink/서브모듈 참조)으로 섞여 들어감** — `.gitmodules`도 없고 자기 자신의 옛 머지 커밋(`bcdc6dd`)을 가리키는 **깨진 자기참조**(중첩 `click-me/`에서 `git add`가 오인). 클론·CI에서 서브모듈 에러 유발 가능.
**할 일** `git rm --cached click-me`로 인덱스의 gitlink 제거(작업트리 파일은 `--cached`라 안 건드림) → 루트에 물리 `click-me/` 디렉터리가 실제로 있으면 정체 확인 후 정리 → `edit: 잘못 추가된 click-me 자기참조 gitlink 제거` 커밋. `git ls-files -s click-me`가 비면 완료.
**완료 기준** `git ls-files | grep '^click-me'` 없음, `git status` 깨끗, 클론 시 서브모듈 경고 없음.

### X2 — G5 라이브 HTTP 422 왕복 재검증 (검증)

**배경** G5(✅ a1fc34e)에서 422 직렬화 버그를 단위 검증으로 확정·수정했으나, 당시 8000 좀비 프로세스로 **실행 중 백엔드에 수정본을 못 올려 라이브 HTTP 422 왕복은 미검증**으로 남김.
**할 일** 백엔드 클린 재기동(좀비 정리 후 `uv run dev.py`) → Preview에서 제너 필수값 누락 요청을 cross-origin으로 보내 **422 + 한국어 메시지("생성모드 필수 필드 누락: …") + CORS 헤더**가 정상 수신되는지 확인(이전엔 "Failed to fetch"였음). gen_form UI 게이팅(빈 값 차단)도 3역할 재확인.
**완료 기준** 라이브 422 응답이 한국어 메시지로 프론트에 도달(에러 카드 표기), 콘솔 무에러. (C4 전수 QA의 C 항목에도 포함되나 G5 직결이라 분리.)

### 🔎 결정된 보류 / 미정 (태스크 아님)

- **매니지먼트(4-2) = 데모로 확정** — `wiring.py` `use_mock=True`(MockAdPlatform·DRY_RUN writer) 그대로. 실 Meta Ads API 연동 안 함. 발표는 데모 모드.
- **CD/배포 = 보류 확정** — `cd.yml` 틀만, `docker-build` ⏸(Secrets), EC2 미진행. 지금 안 함.
- **YouTube RAG = 미정** — 기획서 "최종 단계", 실기능 미구현. 추후 결정.
- **G8(상품 이미지 첨부 생성) = 보류** — 이미지 픽셀 잠금 인페인팅 함수는 있으나 연결·검증은 나중에.
- **시뮬 인구 데이터 grounding = 미정** — `loader.py` 분포 일부 placeholder(`data_status()`로 투명 표기 중). 실 통계 수집은 추후.

---

## 2. 진행 메모

> 제너 403 해소·워크트리 통합 완료. `feat/chat-doyeon` 단일 브랜치. 권장 착수 순서(집): **A1(보안 우선) → G5·G6 → LOOP → AB → G7 → F13 → N5·N6 → L9 → V6·V7 → G1·G2·G4·N3 → C4* *. S2·S5·G8·CD·YouTube·매니지 실연동은 보류(매니지=데모 확정).

### 2-1. 루프 프롬프트 (집에서 — 복붙)

```
/loop docs/chat/tasklist.md 를 읽어. 단일 브랜치(feat/chat-doyeon)에서 남은 ⬜를 끝까지 진행한다. A1·G5는 완료(✅). 제너 403 해소됨(image_generation 실호출 OK).
★ 서버는 도연님이 직접 띄워둠 — 프론트 3000(HMR), 백 8000(--reload). **새 dev 서버나 백그라운드 쉘을 띄우지 말 것.** 코드 변경은 reload/HMR로 자동 반영된다(ruff/tsc/lint 같은 1회성 명령은 실행 OK).
매 반복:
1) 전제는 최초 1회만 — 개인 DB(ep-soft-band)·폰트·OPENAI_API_KEY·Preview 로그인 확인. 서버는 이미 떠 있으니 기동/재기동하지 말 것. 통과 후 생략.
2) §1 표에서 의존 충족·⬜인 가장 위 1개. 권장 순서: G6→LOOP→AB→G7→F13→N5→N6→L9→V6→V7→G1→G2→G4→F8→V3→N3→X1→X2→C4. S2·S5·G8은 보류로 건너뛴다. 명세는 §1-A(새 작업 ★·X1·X2·C4)·§4(기존).
3) 끝까지 구현(코드 변경 시 ruff/tsc/lint 통과) → **태스크를 마칠 때마다 반드시 Claude Preview(preview_*)로 직접 테스트.** 떠 있는 3000/8000을 쓰고(preview_list로 기존 서버 재사용, 새로 띄우지 말 것), "떴다"로 끝내지 말 것 — 바닥 사실 확인(DB 직접 조회·새로고침 복원·엣지/에러 유발·콘솔 무에러), admin·company·user 3역할 재현. 무엇을 검증했고 무엇은 안 했는지 명시.
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

---

## 6. LangGraph 메모리 연결 (숏텀·롱텀·시맨틱) — 2026-06-26

> 이 섹션은 **이 프로젝트를 처음 보는 사람/LLM**이 바로 이어서 작업할 수 있도록 self-contained 하게 작성했다.
> 목표: 채팅 어시스턴트의 **숏텀 메모리(대화 맥락) + 롱텀 메모리(프로젝트 누적 지식)**를 LangGraph 오케스트레이터에 제대로 연결해 답변 품질을 올린다.
> (§0~§4의 환경·계정·실행 명령·협업 규칙을 그대로 따른다. 여기선 메모리 작업만 다룬다.)

### 6-0. 핵심 개념 (용어집)

- **LangGraph 오케스트레이터** — 채팅 한 턴을 `classify(의도분류) → route → 도메인 노드(management/simulation/generator/gen_result/advise)`로 처리하는 상태 그래프. 본체 `backend/domain/chat/orchestrator.py`의 `build_chat_orchestrator()` → `_ask_full()`.
- **체크포인터(checkpointer)** — LangGraph가 `thread_id`별로 그래프 상태(`messages` 등)를 저장·복원하는 장치. 다음 턴에 대화 맥락을 이어준다. `thread_id = 채팅 session_id`(매니지 서브에이전트만 `{session_id}:management`로 분리).
- **숏텀 메모리** — "지금 이 대화"의 맥락(최근 메시지 + 10턴 초과 시 요약).
- **롱텀 메모리** — 세션을 넘어 "이 프로젝트(project_id)" 단위로 누적되는 지식(과거 시뮬/생성 입력·사용자 선호·세션 요약).
- **시맨틱 검색** — 질문을 임베딩(`text-embedding-3-small`, 1536차원)해 의미가 가까운 항목을 pgvector 코사인 유사도로 top-k 조회(최신순 정렬과 대비).

### 6-1. 현재 메모리 아키텍처 (작업 시작 시점 상태)

| 종류 | 저장소 | 코드 | 상태 |
| --- | --- | --- | --- |
| 숏텀 — 대화 기록(영구) | `chat_messages` 테이블 | `domain/chat/history.py append_turn` (라우터 `chat.py _persist`가 매 턴 호출) | ✅ 동작. 진짜 영구 기록 |
| 숏텀 — 그래프 상태(캐시) | LangGraph 체크포인터 | `domain/management/assistant/checkpointer.py` | ✅ 단 **Windows 로컬=MemorySaver(휘발)**, 운영 Linux=AsyncPostgresSaver(Neon 영속) |
| 숏텀 — 대화 요약 | `chat_long_term_memory(memory_type=session_summary)` | `history.summarize_and_compress` | ✅ 10턴 초과 시 앞부분 LLM 요약 |
| 롱텀 — 실행 입력/프로파일 | `chat_long_term_memory` | `history.save_long_term_memory` · `infer_profile_from_execution_history` | ✅ sim/gen 실행 입력·프로파일 누적(`project_id` 있을 때만) |
| 롱텀 — **시맨틱 검색** | `chat_long_term_memory.embedding vector(1536)` | `history.search_long_term_memory` | ⚠️ **코드 완료, DB 마이그레이션·백필 미적용**(M1·M2) |
| 브랜드 프로파일 | `chat_brand_profiles` | `history.get/upsert_brand_profile` | ✅ 프로젝트별 톤·타깃·카테고리 기억 |
| 도메인 KB(RAG) | `*_kb_chunks`(pgvector) | `domain/*/assistant/retriever.py`, `domain/chat/retriever.py` | ✅ ReAct 도구 `search_kb`로 검색 |

**요청 한 턴 흐름** (메모리 주입 지점):
```
프론트 POST /api/chat/complete (SSE)
 → api/routers/chat.py chat_complete()  (ChatTurn 구성, SSE 스트리밍, _persist→append_turn 저장)
 → domain/chat/orchestrator.py _ask_full()
     · (단축 분기) /비교·리포트·템플릿·배치시뮬·브랜드설정 → 위젯 즉시 반환
     · ★메모리 주입: ltm = history.search_long_term_memory(project_id, question, k=4)   ← 시맨틱(완료)
                     + session_summary 보강 + brand = get_brand_profile(project_id)
     · LangGraph 그래프 ainvoke(thread_id = session_id)
         classify → route →
           ├─ advise_node     : ltm·brand·CLIO KB를 시스템 프롬프트에 주입 (★현재 메모리 쓰는 유일 노드)
           ├─ management_node : management 서브에이전트(별도 thread) — 메모리 미주입(M3 대상)
           ├─ simulation_node : 위젯/목록 or simulation 서브에이전트 — 메모리 미주입(M3 대상)
           ├─ generator_node  : 위젯/목록 or generator 서브에이전트 — 메모리 미주입(M3 대상)
           └─ gen_result_node : 생성결과 분석·재시뮬 제안
```

**핵심 파일 맵**
| 파일 | 역할 |
| --- | --- |
| `backend/domain/chat/orchestrator.py` | LangGraph 오케스트레이터. 메모리 주입 지점(`_ask_full` 진입부·`advise_node`·`_format_ltm`/`_format_brand`) |
| `backend/domain/chat/history.py` | 세션·메시지·롱텀메모리·브랜드·템플릿 영속화 + 요약 + **시맨틱 검색**(`_memory_text`·`_embed_memory`·`search_long_term_memory`) |
| `backend/domain/chat/retriever.py` | CLIO KB pgvector 검색기(시맨틱 검색의 본보기 패턴) |
| `backend/domain/chat/kb_ingest.py` | `EMBEDDING_MODEL = text-embedding-3-small` |
| `backend/domain/management/assistant/checkpointer.py` | LangGraph 체크포인터 싱글턴(PG/Memory 분기) |
| `backend/core/models.py` | ORM. `ChatLongTermMemory.embedding Vector(1536)` 추가됨 |
| `backend/alembic/versions/026_add_chat_ltm_embedding.py` | 임베딩 컬럼 마이그레이션(head 025 → 026) |

### 6-2. 이미 완료된 작업 (다시 하지 말 것)

롱텀 **시맨틱 검색 코드** 구현 완료(2026-06-26, 미커밋 상태일 수 있음 — `git status` 확인):
- `core/models.py` — `ChatLongTermMemory.embedding: Vector(1536)` nullable 컬럼.
- `alembic/versions/026_add_chat_ltm_embedding.py` — 임베딩 컬럼 추가(`CREATE EXTENSION vector` + `ADD COLUMN IF NOT EXISTS`).
- `history.py` — `_memory_text()`(직렬화), `_embed_memory()`(임베딩, 풀모드+키 best-effort), `search_long_term_memory()`(코사인 top-k, 임베딩/키 없으면 최신순 폴백), `save_long_term_memory()`에 임베딩 저장 추가.
- `orchestrator.py` `_ask_full` 진입부: `get_long_term_memory(limit=3)` → `search_long_term_memory(question, k=4)` 교체.
- Ruff 통과. (런타임 import 검증은 M0.)
- 참고 노트: `docs/chat/semantic-ltm.md`(이 섹션으로 흡수됨 — 중복이면 정리 가능).

### 6-3. 태스크 (M0~M6)

> 각 태스크: 목적 / 배경 / 대상 파일 / 단계 / 완료 조건 / 검증 / 의존 / 주의.
> 우선순위: 🔴 필수 · 🟡 품질 · 🟢 선택.

#### 🔴 M0. 시맨틱 검색 코드 런타임 검증
- **목적** 추가한 코드가 import·실행 단계에서 안 깨지는지 확인.
- **단계** `cd backend && uv run python -c "from domain.chat import history, orchestrator; from core import models; print(hasattr(history,'search_long_term_memory'), hasattr(models.ChatLongTermMemory,'embedding'))"` → `True True`.
- **완료 조건** import 성공 + 두 속성 존재.
- **주의** `uv` 첫 import는 LangChain 로딩으로 수십 초 걸릴 수 있음. **반드시 절대경로**(`cd /c/doyeon/click-me/backend`)로 — 작업 디렉토리가 리셋되면 `No module named 'domain'` 발생.

#### 🔴 M1. DB 마이그레이션 적용 (026)
- **목적** `chat_long_term_memory.embedding` 컬럼을 실제 Neon DB에 생성. 적용 전엔 저장·검색이 실패한다.
- **단계**
  1. `cd backend && uv run alembic heads` 로 head 확인.
  2. ⚠️ **이 프로젝트는 과거 병렬 브랜치로 리비전 번호가 일부 중복**(019·020·021 다수). `alembic upgrade head`가 *multiple heads* 에러를 낼 수 있다. heads가 2개 이상이면 체인 정리(또는 `alembic merge`) 먼저.
  3. 단일(`026`)이면 `uv run alembic upgrade head`.
  4. 우회(불가피 시): `CREATE EXTENSION IF NOT EXISTS vector; ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS embedding vector(1536);` (단 `alembic_version` 테이블과 어긋나지 않게).
- **완료 조건** `\d chat_long_term_memory`에 `embedding vector(1536)` 존재.
- **검증** 채팅에서 시뮬/생성 실행 → `SELECT memory_type,(embedding IS NOT NULL) FROM chat_long_term_memory ORDER BY created_at DESC LIMIT 5;` 신규 행에 임베딩 채워짐.
- **의존** M0. **협업 주의** DB 모델·마이그레이션은 공통부 — 사전 공지(CLAUDE.md 협업 규칙).

#### 🟡 M2. 기존 롱텀 메모리 행 임베딩 백필
- **목적** 마이그레이션 이전 행은 `embedding=NULL`이라 시맨틱 검색에서 빠진다. 과거 메모리도 검색되게 채운다.
- **대상** 일회성 스크립트 `backend/scripts/backfill_ltm_embedding.py`(신규).
- **단계** `embedding IS NULL` 행 조회 → `history._memory_text(memory_type, content)` 텍스트화 → 임베딩 → `UPDATE ... SET embedding`. 배치(예 100건)·실패 skip·재실행 멱등.
- **완료 조건** `SELECT count(*) FROM chat_long_term_memory WHERE embedding IS NULL;` 0(의도적 제외분 제외).
- **검증** 과거에 다룬 주제를 질문 → 관련 과거 메모리가 top-k에 등장.
- **의존** M1.

#### 🟡 M3. 메모리 주입 범위를 도메인 노드로 확대
- **목적** 현재 롱텀 메모리(`state["ltm"]`)는 `advise_node`에서만 주입(`_format_ltm`). 시뮬·생성·매니지 답변에도 같은 맥락을 주입해 전 영역 일관성 확보.
- **배경** 도메인 노드는 별도 서브에이전트(`AssistantRequest`/`AskRequest` 계약)를 호출 → 메모리를 넘기려면 계약/시그니처를 손봐야 한다.
- **대상** `orchestrator.py`(`simulation_node`·`generator_node`·`management_node`) · `core/assistant.py`(`AssistantRequest`) · `domain/management/assistant/contracts.py`(`AskRequest`) · 각 서브에이전트 `agent.py`/`graph.py`.
- **단계**
  1. `AssistantRequest`/`AskRequest`에 `memory_preamble: str | None`(기본 None → 하위호환) 옵션 필드 추가.
  2. 노드에서 `_format_ltm(state.get("ltm"))` + `_format_brand(state.get("brand"))`를 preamble로 전달.
  3. 서브에이전트가 preamble을 system 프롬프트 앞에 덧붙이도록 수정.
- **완료 조건** 시뮬/생성/매니지 답변이 과거 프로젝트 맥락(타깃·카테고리)을 반영. 기존 호출부 무수정으로도 동작(옵션 필드).
- **검증** 메모리가 쌓인 프로젝트에서 도메인 질문 → 답변에 맥락 반영. 기존 pytest 그린 유지.
- **의존** M1. **경계 주의** 서브에이전트는 각 팀 소유 → `contracts/` 스키마로만 교환, 도메인 내부 직접 import 금지(CLAUDE.md 협업 규칙).

#### 🟢 M4. 숏텀 체크포인터 로컬 영속화 (선택)
- **목적** Windows 로컬에서도 그래프 상태를 재시작 후 유지(현재 MemorySaver=휘발, 운영 Linux만 Neon 영속).
- **배경** psycopg-async가 Windows ProactorEventLoop와 비호환이라 로컬은 의도적으로 건너뜀. 단 `chat_messages` DB + 클라이언트 history 시드로 대화는 복원되므로 **실사용엔 문제 없음** → 선택.
- **대상** `domain/management/assistant/checkpointer.py`.
- **선택지** (a) 그대로 둔다(권장) (b) WSL2(Linux)에서 백엔드 실행 (c) `langgraph.checkpoint.sqlite AsyncSqliteSaver`로 로컬 파일 체크포인터 폴백 추가.
- **완료 조건** (선택 시) 로컬 재시작 후에도 같은 `session_id`로 그래프 맥락 복원.

#### 🟡 M5. 메모리 동작 테스트 추가
- **목적** 회귀 방지(시맨틱 검색·폴백·요약 경로).
- **대상** `backend/tests/`(기존 채팅 테스트 위치 확인 후 추가).
- **단계** ① `_memory_text` 직렬화 단위 테스트 ② `search_long_term_memory` 키 없음(use_mock) → 최신순 폴백 반환(임베딩 mock) ③ `save_long_term_memory` project_id 없으면 no-op, 있으면 적재(임베딩 mock).
- **완료 조건** `uv run pytest tests/ -v` 그린.
- **의존** M0.

#### 🟡 M6. 롱텀 메모리 end-to-end 검증 (기존 L9와 통합 가능)
- **목적** 시뮬/제너 입력이 기억돼 명시 언급 없이도 채팅에 반영되는지 Preview로 확인. (§1-A의 ★L9와 동일 취지 — 시맨틱 적용 후 재검증.)
- **단계** 프로젝트 선택 → 시뮬 1회·생성 1회 실행(롱텀 입력+임베딩 누적) → 10턴 이상 대화(`session_summary` 생성) → 과거 주제를 다시 질문 → 관련 메모리가 답변에 반영되는지 → DB에서 `embedding IS NOT NULL` 신규 행 확인.
- **완료 조건** 명시 언급 없이 브랜드·제품군·과거 입력 인지 응답. (안 되면 끊긴 지점 수정 후 재검증.)
- **의존** M1·M3.

### 6-4. 진행 체크리스트
- [ ] M0 런타임 import 검증
- [ ] M1 마이그레이션 026 적용
- [ ] M2 기존 행 임베딩 백필
- [ ] M3 도메인 노드 메모리 주입 확대
- [ ] M4 (선택) 로컬 체크포인터 영속화
- [ ] M5 메모리 테스트 추가
- [ ] M6 롱텀 메모리 E2E 검증
