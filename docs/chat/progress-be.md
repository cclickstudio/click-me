# 채팅 백엔드 워크트리 진행 로그 (feat/chat-be)

> §2 분할표 B행 — F5 · F6 · C1. 소유 범위 `backend/domain/chat/orchestrator.py`·`history.py`(·`retriever.py`).
> `api/routers/chat.py`·`api/main.py`·`kb/`·`frontend`·`core/models.py`는 손대지 않음.

## 진행

- ✅ **F5 — 랭체인 롱텀 메모리 점검·강화** (2026-06-25)
  - 점검: LTM 저장(`save_long_term_memory` sim/gen_input)·조회(`get_long_term_memory`)·주입(`_format_ltm`/`_format_brand`, advise_node preamble)·브랜드 프로파일(get/upsert)·실행기록 추론(`infer_profile_from_execution_history`)·10턴 요약(`summarize_and_compress`, 메시지 저장 경로에서 호출) 모두 배선·동작 확인.
  - 보강: 진입부 `get_long_term_memory(limit=3)`가 모든 memory_type 최신순 혼합이라, 시뮬/생성 반복 시 `session_summary`가 상위 3에서 밀려 멀티턴 요약이 누락되던 갭 → `session_summary` 미포함 시 별도 1건 조회해 prepend(orchestrator.py 진입부, 수술적).
  - 검증: ruff format/check 통과, `import api.main` OK, `_format_ltm` 병합·렌더 standalone 스모크 통과(요약 포함 확인).

- ✅ **F6 — 채팅 ↔ 매니지먼트 RAG 연결** (2026-06-25)
  - 점검: `management_node`가 이미 import-ready 서브에이전트(`build_management_agent`, `/management/assistant`)를 호출하고 `_mgmt_meta`로 답변+인용(citations)+used_tools+approval 게이트를 SSE meta로 전달함을 확인. classify가 "집행 후 실측 성과"를 management로 라우팅.
  - 보강: 풀모드 `management_node`가 `AskRequest`에 `thread_id`를 안 넘겨, 매 매니지 질문이 서브에이전트의 새 thread를 만들어 멀티턴 맥락이 끊기던 갭 → 채팅 세션 단위 `{session_id}:management` thread_id 고정(채팅 그래프 체크포인터와 네임스페이스 분리). 폴백 경로는 단발 키워드라 미변경.
  - 검증: ruff·`import api.main` OK, mock 모드 standalone 스모크 — 매니지 질의("예산 소진율") → 서브에이전트 경유 답변 + 인용(`live/live_budget`) + used_tools 생성, `thread_id` 수용 확인.

- ✅ **C1 — sim_result_node 죽은 경로 정리** (2026-06-25)
  - 확인: 프론트는 `[생성결과]`만 발신(`GenFormWidget.tsx:81`)해 `gen_result_node`는 살아있으나, `[시뮬결과]`는 어디서도 발신하지 않음(시뮬 완료는 프론트가 `sim_result` **위젯**을 직접 렌더). 따라서 `sim_result_node`는 진입 불가 죽은 경로.
  - 정리(수술적): classify의 `[시뮬결과]` 분기·`sim_result_node` 함수·그래프 노드 등록/route 매핑/END 엣지 제거. 이 노드 전용 헬퍼(`_SimResult`·`_SIM_RESULT_EXTRACT_SYSTEM`·`_TARGET_PI`·`_HIGH_REJECTION`·`_copy_advice`·`fetch_kobaco_benchmark` 지역 import)도 함께 제거(타 노드 미사용 확인). `gen_result_node`·개선 루프·approval 경로는 그대로.
  - 검증: ruff check 통과, 풀모드(개인 DB·OPENAI 키) 그래프 컴파일 성공 + 멀티턴 end-to-end 스모크(T1 advise / T2 management 서브에이전트 실측+인용) 정상 — 죽은 경로 제거 후 라우팅 무결.

## 인계 노트 (B행 완료)

- **완료**: F5(LTM session_summary 멀티턴 보강) · F6(매니지 서브에이전트 세션 thread_id 고정) · C1(sim_result_node 죽은 경로 제거). 커밋 3건(`7663987` F5 · `120d374` F6 · C1).
- **변경 파일**: `backend/domain/chat/orchestrator.py`만(소유 범위 내). `history.py`·`retriever.py`·`api/*`·`kb/`·`frontend`·`core/models.py` 미변경. 스키마 변경 없음.
- **검증 한계**: F5/F6 standalone·C1 풀모드 스모크까지. Preview 3계정 회귀는 통합(C4) 단계에서 수행 권장.
- **다음 시작점**: B행 잔여 ⬜ 없음. 머지는 §2-3 가이드(`feat/chat-doyeon`에 kb→be→fe 순). push는 요청 시에만(feat/chat-be 한정).
