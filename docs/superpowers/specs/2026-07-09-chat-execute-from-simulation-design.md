# 채팅 "시뮬 돌린 걸로 집행" 배선 — 설계 (2026-07-09)

> 채팅에서 "시뮬 돌린 걸로 집행 폼 띄워줘"라고 하면 시뮬 결과가 프리필된 from-simulation
> 집행 카드가 뜨도록 딥에이전트 도구·위젯·프론트 렌더를 배선한다.

## 배경 / 문제

캠페인 생성은 3갈래(직접 입력 `create-proposal` · 생성 시안 `from-candidate` · 시뮬 결과
`from-simulation`)인데, 채팅의 `create_campaign` 도구는 직접 입력 갈래만 배선돼 있다.
그래서 시뮬을 돌린 직후 "집행 폼 띄워줘"라고 해도 시뮬과 무관한 백지 폼이 뜬다.

- 채팅 폼은 `/create-proposal`로 제출돼 `created_campaigns.simulation_id`가 연결되지 않음
  → 성과 전후 비교(before-after)에 시뮬 예측이 붙지 않는 부수 손실.
- from-simulation 갈래는 프론트 `ExecuteFromSimulation` 컴포넌트(시뮬 결과 페이지
  `SimulationResultView.tsx` · 알림센터 `AlarmCenter.tsx`)에만 붙어 있고 채팅 도구가 없다.

## 요구사항 (사용자 확인)

1. **Meta 폼에 실제로 들어갈 값만** 시뮬에서 가져와 프리필한다. from-simulation 서버가
   소재 이미지·simulation_id 연결을 알아서 처리하므로, 시뮬에서 가져올 값은
   **캠페인 이름(시뮬 광고 제목)** 뿐이다. URL·예산·기간은 시뮬에 없는 값.
2. **채팅창에 내용이 있으면 그걸로** 한다.
   - 대상 시뮬 = 이 채팅 세션에서 돌린 시뮬(= 프로젝트 최근 완료 시뮬)을 자동 사용.
   - 사용자가 채팅에서 말한 예산·URL·기간은 LLM이 도구 파라미터로 추출해 프리필.

## 결정 사항

| 결정 | 선택 | 근거 |
|---|---|---|
| 도구 형태 | **신규 도구 `execute_from_simulation`** (create_campaign 확장 아님) | docstring 수준에서 라우팅이 갈려 오라우팅 위험↓, 기존 직접 입력 경로 무회귀 |
| 대상 시뮬 해석 | ① `simulation_id` 파라미터 → ② 최근 완료 시뮬 → ③ 안내문 폴백 | "채팅창에 있으면 그걸로" — 채팅에서 방금 돌린 시뮬이 곧 최근 완료 시뮬. sim_list select 재사용안은 계획 단계에서 기각(선택 시 "개선해줘" 고정 발화를 보내 개선 흐름으로 오라우팅) |
| 폼 UI | **기존 `ExecuteFromSimulation` 재사용** (신규 위젯 타입으로 임베드) | 이름 프리필·AI 이름 추천·게이트 경고·승인→집행 플로우 내장, 알림센터 임베드로 검증된 경로 |

## 데이터 흐름

```
사용자: "방금 시뮬 돌린 걸로 집행 폼 띄워줘. 예산 2만원, URL은 example.com"
  ↓ 딥에이전트 → execute_from_simulation 도구
    (발화에서 campaign_name·link_url·daily_budget_krw·start/end 추출, 없으면 빈 값)
  ↓ 대상 시뮬 해석: simulation_id 파라미터 → latest_completed_simulation_id(project_id)
    → 둘 다 없으면 안내문 폴백
  ↓ improve_context.fetch_improve_source 재사용 — 광고 제목 + click_intent_rate·rejection_rate
  ↓ 신규 위젯 exec_from_sim { simulation_id, default_name, click_intent_rate, rejection_rate,
                              link_url, daily_budget_krw, start_date, end_date } (평면 —
                              기존 create_campaign 위젯의 prefill 타입과 충돌 회피)
  ↓ 프론트: ChatConversation이 ExecuteFromSimulation 렌더 (AlarmCenter와 동일 임베드)
  ↓ 이후 기존 그대로: 게이트 판정 → /campaign-proposals/from-simulation → /approve
    → /execute → created_campaigns.simulation_id 연결 → before-after 예측 자동 연결
```

## 변경 파일

### 백엔드 (2파일)

- `backend/api/assistant/subagent_tools.py` — `execute_from_simulation` 도구 추가.
  - 파라미터: `simulation_id`·`campaign_name`·`link_url`·`daily_budget_krw`·`start_date`·
    `end_date` (전부 선택, 발화에 있는 값만 — 지어내기 금지).
  - docstring에 라우팅 경계 명시: "'시뮬 돌린 걸로/이 결과로 집행·캠페인 만들어' 발화 시
    호출. 시뮬과 무관한 새 캠페인 백지 생성은 create_campaign."
  - KPI 조회는 `improve_context.fetch_improve_source`와 동일한 raw SQL 결합
    (`simulation_aggregates.click_intent_rate`·`rejection_rate` + `ads.title`).
- `backend/domain/chat/widgets.py` — `exec_from_sim(data)` 위젯 함수 추가
  (source=MANAGEMENT).

### 프론트 (2파일)

- `frontend/src/components/manage/ExecuteFromSimulation.tsx` — 선택적 initial 프롭 추가
  (`initialLinkUrl`·`initialBudget`·`initialStartDate`·`initialEndDate`).
  기존 호출부(시뮬 결과 페이지·알림센터)는 프롭 미전달 시 현행과 동일 동작(무회귀).
- `frontend/src/components/chat/ChatConversation.tsx` — `exec_from_sim` 위젯 타입 렌더
  분기 추가(`WidgetSpec.data` 타입 확장 포함).

## 에러 처리

| 상황 | 처리 |
|---|---|
| 프로젝트에 완료 시뮬 없음 | 도구가 안내문 반환 ("아직 완료된 시뮬레이션이 없어요…") — run_improvement와 동일 패턴. 완료 시뮬이 없으면 목록도 비므로 sim_list 폴백은 무의미 + select 모드는 개선 흐름으로 오라우팅 |
| 시뮬 집계 없음(KPI null) | 도구가 안내문 반환 ("시뮬 집계가 아직 없어요") |
| 게이트 미달(클릭의향률·거부율) | 도구는 막지 않음 — 기존 컴포넌트의 amber 경고가 안내·집행 차단 |
| durable S3 이미지 아님 | 기존 from-simulation 422 메시지가 카드에 표시 |

## 테스트

- **백엔드 pytest** — 도구 단위: 시뮬 해석 3분기(파라미터/최근/폴백), 위젯 페이로드 구성,
  미완료 시뮬 안내문.
- **프론트** — `pnpm build` 통과 + 기존 호출부 무회귀(프롭 미전달 경로).
- **수동 시나리오 3종** — "시뮬 돌린 걸로 집행해줘"(기본) / "예산 2만원, URL ○○로
  집행"(발화 추출 프리필) / 완료 시뮬 없는 프로젝트(폴백).

## 하지 않는 것

- `create_campaign` 도구·위젯·직접 입력 카드 변경 없음.
- from-simulation 엔드포인트·집행 게이트·승인 플레인 변경 없음.
- 시뮬 목록에서 여러 건 비교 후 집행 같은 확장 UX 없음(YAGNI).
