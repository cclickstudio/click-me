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

- [ ] `domain/chat/orchestrator.py`: classify에 `deep` intent 추가 + deep_node에서 build_deep_agent 루프 호출
- [ ] deep_node 결과(SubagentResult) → 우리 ChatAnswer.meta로 변환 (위젯/approval/cards 매핑)
- [ ] Deep Agent generator TRIGGER → meta.widget=gen_form, 시뮬 트리거 → meta.widget=sim_form 변환
- [ ] 단일 도메인·결정론 경로(시뮬/생성 실행·템플릿·리포트·비교·키워드)는 **무변경** 보존 확인
- [ ] 장기기억 배선: 턴 시작 recall→memory_context 주입 / 턴 종료 remember(백그라운드)
- [ ] management ours 유지 확정 (dev 전환 안 함) — memory_store/recall 경로 검증
- [ ] chat.py 22 엔드포인트 유지 확인 (complete/approve 내부 오케 호출만 deep 분기)
- [ ] 검증: 백엔드 import + `uv run ruff check` + `uv run pytest tests/ -v`
- [ ] 커밋: `edit: chat 오케스트레이터 Deep Agent 도구루프 흡수 + 장기기억 배선`

---

## 3단계 — 프론트 전환

- [ ] ChatConversation SSE 파싱이 deep 경로 meta(위젯·approval)를 기존대로 처리하는지 확인 (대부분 무변경 기대)
- [ ] (결정 시) meta.cards 렌더 신설: EVIDENCE/RESULT/REVIEW/ACTIONBAR 카드 컴포넌트
- [ ] suggested_action → 기존 ApprovalWidget/위젯으로 매핑 렌더
- [ ] 위젯 14개 기존 렌더 회귀 없음 확인
- [ ] 검증: `pnpm tsc --noEmit` + `pnpm build`
- [ ] 커밋: `add: 추천 조치 카드 렌더 + Deep Agent SSE 연결` (또는 edit)

---

## 4단계 — 마이그레이션·검증

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
