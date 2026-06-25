# 채팅 백엔드 워크트리 진행 로그 (feat/chat-be)

> §2 분할표 B행 — F5 · F6 · C1. 소유 범위 `backend/domain/chat/orchestrator.py`·`history.py`(·`retriever.py`).
> `api/routers/chat.py`·`api/main.py`·`kb/`·`frontend`·`core/models.py`는 손대지 않음.

## 진행

- ✅ **F5 — 랭체인 롱텀 메모리 점검·강화** (2026-06-25)
  - 점검: LTM 저장(`save_long_term_memory` sim/gen_input)·조회(`get_long_term_memory`)·주입(`_format_ltm`/`_format_brand`, advise_node preamble)·브랜드 프로파일(get/upsert)·실행기록 추론(`infer_profile_from_execution_history`)·10턴 요약(`summarize_and_compress`, 메시지 저장 경로에서 호출) 모두 배선·동작 확인.
  - 보강: 진입부 `get_long_term_memory(limit=3)`가 모든 memory_type 최신순 혼합이라, 시뮬/생성 반복 시 `session_summary`가 상위 3에서 밀려 멀티턴 요약이 누락되던 갭 → `session_summary` 미포함 시 별도 1건 조회해 prepend(orchestrator.py 진입부, 수술적).
  - 검증: ruff format/check 통과, `import api.main` OK, `_format_ltm` 병합·렌더 standalone 스모크 통과(요약 포함 확인).
