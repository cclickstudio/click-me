# 컨텍스트 노트 — 생성 기능 채팅 연결

## 결론 (2026-07 기준)

1세대 설계(의도 분류 LLM → 레지스트리 디스패치 → 결정론 슬롯필링 되묻기)는
**통합 딥에이전트로 대체**됐다(`4c3e7c8`). 현재는 deepagents 기반 단일 에이전트가
CHAT_POLICY(시스템 프롬프트) + 도구 docstring으로 라우팅을 판단하고, 도구는
`api/assistant/subagent_tools.py`의 @tool들이다.

## 현재 아키텍처

```
POST /api/chat/complete (SSE, 선택적 JWT)
  → 통합 딥에이전트 (deep_agent_builder.py, CHAT_POLICY)
       ├ run_generation        발화 슬롯 추출 → gen_form 위젯(프리필 폼)
       ├ run_improvement       시뮬 기반 단발 개선 — 프리필 완비면 즉시 실행(gen_progress),
       │                        아니면 개선 폼. simulation_id 없으면 최근 완료 시뮬 자동 선택
       ├ improve_ad_iteratively 자동 개선 루프(generation_loop) → gen_loop 위젯
       ├ ask_generator          조회·조언 위임 → generator ReAct 그래프
       │                        (list_generations·get_generation_result·search_kb 하이브리드 RAG)
       └ list_my_generations    목록 → gen_list 위젯
  → 최종 상태의 widget/sub_meta를 _assemble_chat_meta가 SSE meta로 방출
```

- **실행 주체 분리 원칙**. 백엔드 도구는 위젯 신호만 적재하고, 실제 생성 실행은 프론트
  위젯(GenFormWidget)이 `api.generator.start`를 호출 — 단, `run_improvement`의 즉시 실행
  경로만 예외적으로 백엔드가 `start_improve_generation`을 직접 호출(gen_progress 카드)
- 1세대의 되묻기 루프는 **폼 위젯**이 대체 — 슬롯 수집·필수값 검증·프로젝트 선택을 폼이 담당
- started_event 핸드오프 개념은 유지됨 — gen_progress/gen_form 완료가 생성 SSE
  (`/api/generator/generations/{id}/stream`) 구독으로 이어짐

## 시뮬→제너 왕복 (개선 루프 HITL)

- 시뮬 완료 → `loopCtxRef`(ad_title·ad_content·ad_objective·**simulation_id**) 보관
- 승인 카드 수락(action=run_generator) → `/api/chat/approve`가 simulation_id 있으면
  `improve_gen_data_for_simulation`으로 **IMPROVE 폼 프리필**(KPI 요약·토론 리포트·
  원본 광고 키 재조회), 없으면 CREATE 폼 폴백(하위호환). MAX_LOOP(3턴) 서버 차단
- 생성 완료 → `[생성결과]` 콜백 → result_callback이 재시뮬 승인 카드 제안

## 현 코드 사실

- IMPROVE 필수 입력은 `simulation_summary` 하나. improve 재료(KPI aggregate·
  persona_debates.final·ads.asset_url)는 `api/assistant/improve_context.py`가
  simulation_id 하나로 raw SQL 재조회(도메인 경계 유지 패턴)
- CREATE 필수 슬롯. `product_name·product_description·target_audience` + `project_id`
- 채팅 인증은 선택적(`optional_user`) — 미로그인도 일반 질문 동작

## 남은 것 / 주의

- ~~gen_loop 위젯 프론트 렌더러 부재~~ → `GenLoopWidget` 신설로 해소(2026-07-05).
  루프 SSE는 이벤트를 처음부터 재생하므로 재구독만으로 복원, 완료 루프는 상태 조회로
  요약만 표시(onComplete 재발화 방지). 단 `_loops`가 인메모리라 서버 재시작 시 404 안내
- 채팅 IMPROVE는 `product_cutout_s3_key` 추적 불가(null 폴백) — DB 연결 조율 대상
- 구 `api/assistant/orchestrator.py`·`wiring.py`의 Orchestrator/_try_kb_advise는
  hallucination_eval 전용 레거시 — 정리 대상
