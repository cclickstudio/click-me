# checklist — Chat을 Deep Agent 방식으로 전환

> 전략: **흡수 통합**(우리 인프라 골격 유지 + Deep Agent 도구루프 흡수). 상세 근거는 [context-notes.md](./context-notes.md).
> 각 단계 끝에 검증 + 커밋. 백엔드 .py 수정 후 Ruff 먼저 제안.

---

## 1단계 — 분석·계획 ✅ (현재)

- [x] 우리 chat 백엔드 전수 분석 (orchestrator.py + chat.py 22 endpoints + SSE + 위젯 트리거)
- [x] Deep Agent 자산 전수 분석 (deep_agent 도구루프·SubagentRequest/Result·composer 카드·memory_store)
- [x] 프론트 위젯 UI 전수 분석 (14 위젯 + 16 chat API + SSE 파싱 + 플로팅/사이드바/알림)
- [x] management ours vs dev 차이 확인 → **ours가 LTM 완비, dev엔 없음**
- [x] alembic multiple heads 8지점 맵핑
- [x] context-notes.md · checklist.md 작성
- [x] **사용자 결정 확정** (2026-06-29): 흡수 통합 · management ours 유지 · meta.cards 프론트 렌더 포함
- [ ] 커밋: `add: chat Deep Agent 전환 1단계 분석·계획 문서`

---

## 2단계 — 백엔드 전환

- [x] `domain/chat/orchestrator.py`: classify에 `deep` intent + deep_node(주입된 deep_runner 호출). domain→api 역의존 회피 위해 deep_runner를 **포트로 주입**(api가 조립)
- [x] deep_node 결과(SubagentResult) → ChatAnswer.meta로 변환(source/label/engine setdefault, 실패·None은 advise 폴백)
- [x] **위젯 보존 전략 확정**: deep는 실제 시뮬/생성을 트리거하지 않음(조회·합성·제안만). 실행은 기존 위젯 경로(sim_form/gen_form)가 담당 → 위젯 100% 무변경
- [x] 단일 도메인·결정론 경로(시뮬/생성 실행·템플릿·리포트·비교·키워드)는 **무변경** 보존
- [x] 장기기억 배선: chat.py가 recall→memory_context 주입(ChatTurn), 턴 종료 remember(suggested_action 있을 때, 백그라운드)
- [x] management **ours 유지** — memory_store/recall 그대로, management_node에 memory_context 주입 + _mgmt_meta에 suggested_action 노출
- [x] meta.cards 합성(chat.py `_cards_from_meta` → composer.compose_turn 재사용) — 행동 제안 있을 때만
- [x] `api/assistant/wiring.py`: 깨진 `build_generation_chat_agent` import 제거(우리 generator 어댑트), `build_chat_deep_runner` 추가
- [x] chat.py 22 엔드포인트 유지(complete 내부 오케 호출만 deep 분기 + recall/cards/remember)
- [x] 검증: import OK + ruff OK + 관련 pytest 61 passed
  - ⚠️ dev 미정합 테스트 3종(test_chat_memory·test_crag·test_assistant_execute_flow)은 **baseline(1edaacc)부터 collection 에러**(우리 노선에 없는 심볼 import). 4단계에서 우리 함수명에 맞춰 정리.
- [ ] 커밋: `edit: chat 오케스트레이터 Deep Agent 도구루프 흡수 + 장기기억 배선`

---

## 3단계 — 프론트 전환

- [x] ChatConversation SSE 파싱이 deep 경로 meta를 기존대로 처리 — `kind='meta'`가 `data.meta`를 통째로 첨부해 **cards 자동 포함**(무변경). 영속도 백엔드가 meta 통째로 저장→복원 시 따라옴
- [x] meta.cards 렌더 신설: `ActionCards.tsx`(RESULT/REVIEW/ACTIONBAR). EVIDENCE는 기존 CitationChips와 중복이라 제외. ApprovalWidget 톤 따름(Toss 스타일·dark 대응)
- [x] SourceMeta에 `cards?: ActionCard[]` 추가, approval 앞에 `<ActionCards>` 렌더(assistant만)
- [x] 위젯 14개·기존 렌더 무변경(렌더 분기에 cards 한 줄만 삽입, 기존 경로 불변)
- [x] 검증: `tsc --noEmit` 0 에러 · ESLint 0 errors(ActionCards 깨끗, 기존 useEffect warning 1)
  - 곁가지 fix: 무관한 `dashboard/page.tsx` getToken 중복 import(baseline부터 build 차단) 제거 → **별도 커밋**으로 분리
  - ⏭ 카드 시각 e2e는 4단계로(백엔드 suggested_action 트리거에 실 데이터·키 필요 → 백엔드+프론트 동시 기동 시 종합 검증)
- [ ] 커밋: `add: 추천 조치 카드(meta.cards) 렌더`

---

## 4단계 — 마이그레이션·검증

- [ ] dev 미정합 테스트 정리: test_chat_memory(우리 `_recall_memory_context`/`_memory_ids`에 맞춰 재작성), test_crag·test_assistant_execute_flow(우리 management graph 심볼 대조 후 갱신/삭제)
- [ ] alembic 선형 재번호 (dev primary + feat 후행 삽입, 단일 head)
- [ ] 029(management_user_memory.embedding, M6) 적용
- [ ] `uv run alembic heads` → 단일 head 확인 / `alembic upgrade head` 통과
- [ ] 백엔드: import + ruff + pytest
- [ ] 프론트: tsc + build
- [ ] e2e: preview_* 로 실제 chat 띄워 — 자유질문·시뮬위젯·생성위젯·개선루프·멀티도메인(deep)·장기기억 회수 증거(스냅샷/로그)
- [ ] 커밋: `fix: alembic multiple heads 선형 재번호 + management_user_memory 적용`

### alembic 재번호 초안 (dev primary 기준)
```
018 → 019(landing_url,dev) → 020(chat_normalize,dev) → 021 → 022 → 023(brand_profiles)
    → 024(ad_templates,dev) → 025(clio_chunks,dev)
    → 026(chat_schema_convergence,feat) → 027(brand_kits,dev) → 028(last_read,feat)
    → 029(management_kb+state,feat) → 030(prefix_tables,dev)
    → 031(management_user_memory,dev) → 032(kb_rls,feat) → 033(user_memory_embedding,feat·M6)
```
※ 각 파일 down_revision 갱신으로 선형화. merge revision 불필요. 번호 충돌 파일명도 함께 재명명.

---

## 규칙 리마인더
- 백엔드 .py 수정 후 → Ruff 제안 → `cd backend && uv run ruff format . && uv run ruff check . --fix`
- PM: 프론트 pnpm / 백엔드 uv (교차 금지)
- 커밋: `타입: 한국어 설명` (add/edit/fix/delete), 단계마다
