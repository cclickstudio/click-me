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

## 진행 예정

- ⬜ N4 — 선제적 말걸기 챗봇 (N1·N2 자산 재사용)
- ⬜ F10 — 해시태그·키워드 추천 위젯
