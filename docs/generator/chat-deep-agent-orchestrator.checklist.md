# 채팅 오케스트레이터(deep agent) — 체크리스트

> 경계 = 혼합(읽기·단발=툴 / 해석·다단계=서브에이전트). 배경은 context-notes.md.

## 공통 담당 (오케스트레이터, 단독 PR)

- [ ] `deepagents` 의존성 추가 (uv, 현재 미설치) + 버전 고정.
- [ ] `orchestrator.py` 교체 → `create_deep_agent(tools=[…], subagents=[…], model=…, instructions=…)`.
- [ ] deep agent 시스템 프롬프트 작성 — 역할, 추론 기반 툴/서브에이전트 선택(키워드 금지), 되묻기(ASK) vs 실행(TRIGGER) 판단, 핸드오프·승인 게이트 표면화.
- [ ] state 최소화 — `messages + todos`. 세션 컨텍스트(user_id/org_id/project_id/context_ad_id/available_projects)는 config 주입.
- [ ] 무한루프 가드 — 재귀 한도·todo 종료조건.
- [ ] `intent.py` 키워드 분류 삭제 / `chat.py` `_MGMT_KEYWORDS`·`_is_management` 삭제.
- [ ] `chat.py` 라우터 재작성 — deep agent `astream_events` → 기존 SSE(`meta/token/done`) 변환, 부수효과(`StartedEvent`/`requires_approval`)를 SSE 이벤트로, `record_turn`/`feedback` 유지.
- [ ] 프론트 `chat/page.tsx` — `started_event`(생성·시뮬 핸드오프) 처리 추가.
- [ ] `wiring.py` — 세 도메인 `build_*_tools`/서브에이전트 등록.

## 시뮬레이션 팀 (chat/ 비어있음 — 0부터)

- [ ] `domain/simulation/chat/` 신설.
- [ ] 읽기 툴 — `get_simulation_result`, KPI 4종 요약(클릭의향률·구매의도분포·신뢰도·거부율).
- [ ] (선택) 트리거 툴 `start_simulation` — 즉시 job_id/stream_url 반환.
- [ ] "시뮬 분석가" 서브에이전트 — 읽기툴 + KOBACO 비교·분포 해석 프롬프트.
- [ ] `build_simulation_tools(settings)` 노출.

## 생성 팀

- [ ] 슬롯필링 루프(`slot_agent.py`) 폐기 → `start_generation` 툴 하나(CREATE/IMPROVE).
- [ ] 툴은 즉시 `job_id/stream_url` 반환(블로킹 금지), `improve_context` 경로 유지.
- [ ] `build_generation_tools(settings)` 노출.

## 관리 팀 (거의 완성)

- [ ] `agent.py`를 서브에이전트로 노출(네이티브 그래프) 또는 `suggested_action` 반환 툴로 래핑.
- [ ] HITL interrupt가 deepagents `task` 안에서 전파되는지 검증 → 실패 시 승인을 approval 화면으로 분리.
- [ ] `build_management_subagent(settings)` 노출.

## 완료 기준

- [ ] 키워드 분기 0 — 라우팅이 전부 deep agent 추론.
- [ ] `pytest tests/assistant -v` 통과 + 신규 도메인 툴 테스트.
- [ ] 채팅에서 생성/시뮬 트리거 → 프론트가 stream_url 구독 동작.
