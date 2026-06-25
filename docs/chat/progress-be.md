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
