# 프론트 채팅 위젯(C) 진행 로그 — feat/chat-fe

> 워크트리 C(P5·N4·F10) 전용 진행 로그. tasklist.md §1 현황표·§5는 머지 시점에 통합(여기엔 직접 안 적음).
> 소유 범위: `frontend/src/components/chat/*` + F10 키워드 엔드포인트는 `backend/api/routers/chat.py`에 append-only.

## ✅ 완료

- ✅ **P5 — RAG 인용 표시 위젯** (2026-06-25)
  - 신규 `frontend/src/components/chat/CitationChips.tsx` — 전 도메인(시뮬·제너·매니지·CLIO) 어시스턴트 답변의 KB 인용을 칩(📄 출처파일›섹션)으로 렌더, 클릭 시 원문 chunk 펼침(토글). 실측(live) 근거는 초록 칩.
  - `ChatConversation.tsx` — 기존 management 전용 회색 텍스트 근거 블록(1318-1333)을 `<CitationChips>`로 교체, 모든 assistant 메시지에 적용.
  - `lib/api.ts` — `chat.kbChunk(source, title)` 추가.
  - 백엔드 append-only — `api/routers/chat.py`에 `GET /api/chat/kb-chunk?source=&title=` 추가(4개 KB 테이블에서 원문 조회, 읽기 전용). orchestrator.py·main.py·models.py 무수정. ruff 통과.
  - 검증(Claude Preview, USER doyeon): 시뮬 KB 질문→인용 칩 8개 렌더, 칩 클릭→원문 펼침(`simulation_glossary › 클릭 의향률` 등), 같은 칩 재클릭→닫힘, 새로고침→칩 8개 DB 복원·복원 후에도 펼침 동작, 다크모드 가독 양호, 콘솔 무에러, kb-chunk 200. company(yohan) 플로팅 챗에서도 동일 컴포넌트 렌더 확인(세션 스토리지 잔존으로 표시 섞임은 P5 무관). P5는 역할 분기 없는 순수 표시 컴포넌트라 역할 무관.
  - 미세 메모: management live "실측" 칩 경로는 기존 management 표시 로직을 그대로 보존·일반화한 것(회귀 없음). 캠페인 맥락 필요해 이번 Preview에선 live 칩 시각 재현은 생략, kb 칩은 전 도메인 재현 확인.

- ✅ **N4 — 선제적 말걸기 챗봇** (2026-06-25)
  - `ChatConversation.tsx`에 선제 알림 폴링 effect 추가 — 활성 세션이 있을 때 프로젝트의 **미열람 완료 시뮬 결과**를 감지해 챗봇이 먼저 "🔔 아직 확인하지 않은 시뮬레이션 결과가 있어요…" 메시지 + sim_result 위젯(KPI)을 주입(`appendWidgetMessages` 재사용). 세션 로드 3초 후 1회 + 60초 폴링(다른 화면에서 완료된 결과 캐치업).
  - 빈도 가드: 프로젝트당 20분 1회(`chat_proactive_last_*`) + 이미 알린 결과 id seen-set(`chat_proactive_seen_*`)로 중복 방지. 최근 48h 완료만 대상. 이미 세션에 떠 있는 sim id(N1 주입분)는 제외.
  - N2 연동: 주입 시 `onResultComplete` 호출 → 플로팅 닫혀 있으면 빨간 배지(`pushUnread`). 제너는 403 블로커라 보류, **시뮬 완료만** 대상(§2-2 준수).
  - 검증(Claude Preview, USER doyeon): 기존 세션 진입 3초 후 선제 메시지+sim_result(클릭의향률·구매의도·신뢰도·거부율) 자동 등장, 새로고침→DB 복원·가드로 중복 주입 없음(1건 유지), 대시보드(플로팅 닫힘)에서 선제 트리거→빨간 배지 "1"→열면 배지 0·메시지 표시, 콘솔 무에러. tsc·next lint 통과. (역할 분기 없는 ChatConversation 공용 로직 → 역할 무관.)

- ✅ **F10 — 해시태그·키워드 추천 위젯** (2026-06-25)
  - 신규 `frontend/src/components/chat/KeywordWidget.tsx` — 제품·카테고리·타깃·카피 입력 폼 → 추천 실행 → SNS 해시태그/키워드 칩 렌더(개별 클릭 복사 + 전체 복사). 복사 로직은 기존 `copyMessage`(F1/P10)와 동일 패턴.
  - 백엔드 append-only `backend/api/routers/chat.py` — `POST /api/chat/keywords`(gpt-4o-mini, JSON 응답: hashtags 12 + keywords 6). orchestrator/main/models 무수정. ruff 통과.
  - `lib/api.ts` — `chat.keywords` 추가. `ChatConversation.tsx` — `/키워드` 슬래시 커맨드 + `keyword_form` 위젯 렌더 분기 + 도움말 한 줄.
  - 검증(Claude Preview, USER doyeon): `/키워드`→폼 위젯 등장→4필드 입력→추천받기→해시태그 12칩+키워드 6칩 렌더, `POST /api/chat/keywords` 200(+CORS preflight 200), "다시 추천받기"/"전체 복사" 노출, 콘솔 무에러. tsc·next lint·ruff 통과.
  - 제약: Preview는 비-제스처 클립보드 호출을 차단(NotAllowedError)해 "복사됨 ✓" 피드백 자동 확인은 불가 — 복사 코드는 앱에 이미 출시된 동일 패턴이라 실제 사용자 클릭에선 동작.

---

## 인계 노트 (C 워크트리 — P5·N4·F10 전부 ✅)

- **브랜치** `feat/chat-fe`. 커밋 3건: P5(cce2b93)·N4(c9c9624)·F10(미커밋→이 노트와 함께 커밋). push는 요청 시에만.
- **신규 파일** `CitationChips.tsx`·`KeywordWidget.tsx`. **수정** `ChatConversation.tsx`(인용 칩 교체·N4 폴링·/키워드)·`lib/api.ts`(kbChunk·keywords).
- **백엔드 append-only**(`api/routers/chat.py`만): `GET /chat/kb-chunk`(P5 원문 조회)·`POST /chat/keywords`(F10). orchestrator/history·core/models.py·api/main.py **무수정**(§2-2 경계 준수). B 워크트리와 파일 충돌 없음.
- **머지 시** 현황표(§1)에서 P5·N4·F10 ⬜→✅ 반영(이 파일이 아닌 tasklist.md). 백엔드 chat.py에 추가한 2개 엔드포인트는 append라 머지 충돌 거의 없음.
- **주의/한계**:
  - N4는 §2-2대로 **시뮬 완료만** 대상(제너 403 보류). 제너 403 해제 시 generations도 동일 로직에 추가 가능.
  - N4 검증 중 doyeon 세션(5ecc56d8)에 선제 알림 테스트 메시지가 일부 남음(개인 DB 테스트 데이터, 무해).
  - F10 복사 피드백은 Preview 클립보드 제약으로 자동검증 미완(코드는 검증된 패턴).
  - `.claude/launch.json`(frontend, port 3000, autoPort:false) 생성함 — Preview 구동용.
