# KB 워크트리(feat/chat-kb) 진행 로그

> §2 분할표 A행(R5·R6·R7, RAG/KB 적재) 전용. tasklist.md §1 현황표는 머지 시점에 일괄 반영.

- R5 ✅ — clio KB에 `meta_platform_policy.md`(Meta 인스타/페북 정책·형식·용어 41청크) 추가·인제스트. clio_kb_chunks 70→111. retriever 스모크 통과(전환 API 0.691·릴스 0.702, Meta 질의에 meta 청크 top).
- R6 ✅ — clio KB에 `marketing_terms.md`(광고·마케팅 지표·전략·애드테크 용어 92청크, 별도 테이블 없이 clio_kb 통합) 추가·인제스트. clio_kb_chunks 111→203. 기존 70·R5 41과 중복 회피. retriever 스모크 통과(ROAS 0.674·LTV/CAC 0.831, 용어 질의에 marketing 청크 top).
- R7 ✅ — 기존 3 KB 덤프·점검. SIM 69(KPI·방법론·통계) · GEN 79(카피공식·톤·플랫폼별) · MANAGE 88(운영지표·이상탐지·조치·정책). 세 KB 모두 핵심 주제를 용어+정의로 빠짐없이 커버, 명백한 누락 없음 → "억지 패딩 금지·top-k=4" 원칙에 따라 보강 없이 **충분 판정**(count 변동 없음). 신규 .md·코드 변경 없음.

---

## 인계 노트 (A행 R5·R6·R7 전부 완료)

- **clio KB(clio_kb_chunks)**: 70 → **203청크**. 구성 — `advertising_general_knowledge.md`(70, 광고 일반개념) · `meta_platform_policy.md`(41, R5 Meta 정책·형식·용어) · `marketing_terms.md`(92, R6 지표·전략·애드테크). 별도 marketing 테이블 미생성(사용자 결정대로 clio_kb 통합).
- **기존 3 KB**: 변경 없음(R7은 점검·충분 판정). SIM 69 · GEN 79 · MANAGE 88 유지.
- **건드린 파일**: `backend/domain/chat/kb/meta_platform_policy.md`(신규) · `backend/domain/chat/kb/marketing_terms.md`(신규) · 본 `progress-kb.md`. orchestrator/history/retriever .py · core/models.py · api/* · frontend 미수정(§2-2 경계 준수).
- **검증**: 각 단계 standalone로 `select count(*)` 증가 + `ClioKbRetriever.search` 스모크 통과. ingest는 소스 파일명 기준 멱등이라 재실행 안전.
- **머지 시 주의**: clio KB ingest 모듈(`domain/chat/kb_ingest.py`)·retriever는 R4에서 머지됨, 본 작업은 `.md`만 추가했으므로 B(채팅백엔드)와 파일 충돌 없음. 머지 후 `uv run python -m domain.chat.kb_ingest` 한 번 돌리면 203청크 재현.
- **push**: 도연님 요청 시에만(feat/chat-kb, --force·main 금지). 현재 미푸시.
- 커밋: R5 `475877e` · R6 `48dd185` · R7(본 커밋).
