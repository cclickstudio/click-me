# KB 워크트리(feat/chat-kb) 진행 로그

> §2 분할표 A행(R5·R6·R7, RAG/KB 적재) 전용. tasklist.md §1 현황표는 머지 시점에 일괄 반영.

- R5 ✅ — clio KB에 `meta_platform_policy.md`(Meta 인스타/페북 정책·형식·용어 41청크) 추가·인제스트. clio_kb_chunks 70→111. retriever 스모크 통과(전환 API 0.691·릴스 0.702, Meta 질의에 meta 청크 top).
- R6 ✅ — clio KB에 `marketing_terms.md`(광고·마케팅 지표·전략·애드테크 용어 92청크, 별도 테이블 없이 clio_kb 통합) 추가·인제스트. clio_kb_chunks 111→203. 기존 70·R5 41과 중복 회피. retriever 스모크 통과(ROAS 0.674·LTV/CAC 0.831, 용어 질의에 marketing 청크 top).
