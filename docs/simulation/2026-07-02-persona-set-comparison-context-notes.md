# 3-모드 분석 UX — Persona Set(세그먼트 비교) 컨텍스트 노트

> 선행 문서: `Persona/AD_Simulator_Improvement_Notes.md`(P1-3) · `SIMULATOR_REMAINING_TASKS.md`(A-1).

## 0. 스코프 확정 — Individual은 백엔드 변경 없음

`SimulationRunRequest.sample_size`는 이미 `ge=1`이라 `sample_size=1`이 기존 `/run`·`/`(비동기)
엔드포인트로 바로 된다. "Individual 모드"는 프론트가 이 값을 프리셋으로 보내고, 응답을 집계 차트
대신 1인 서사 뷰로 렌더링하는 문제 — **백엔드 변경 불필요**. 이번 작업 범위는 **Persona Set(세그먼트
비교)만**이다.

## 1. 문제

`run_graph.py`는 광고 해석(`interpret_ad`) → 패널 로드 → 반응 fan-out → 집계를 **하나의
target_filter**에 대해서만 수행하는 선형 그래프다. 세그먼트별(예 "20대 여성" vs "40대 남성")로
비교하려면 지금은 `/run`을 세그먼트 수만큼 각각 호출해야 하는데, 그러면:
1. **광고 해석(VLM)이 세그먼트마다 다시 실행** — 비용 낭비 + LLM 비결정성으로 세그먼트마다
   다른 해석이 나올 수 있어(같은 광고인데) 비교의 전제(같은 기준)가 깨질 위험.
2. 프론트가 N번 왕복해야 하고, 하나의 비교 결과로 묶어줄 곳이 없다.

## 2. 결정

- **광고 해석·루브릭은 1회만, 세그먼트별로 패널 로드→반응→집계만 반복.** `run_graph.py`의
  `interpret_ad` 노드 로직을 `interpret_and_score()` 순수 함수로 추출해 그래프 노드와 신규
  서비스가 공유(중복 금지).
- **그래프(LangGraph) 재사용 안 함, 서비스 레이어에서 직접 오케스트레이션.** 세그먼트마다
  그래프를 통째로 다시 컴파일/구동하는 것보다, 이미 있는 컴포넌트(interpreter·rubric·panel
  provider·reaction_graph·aggregator)를 그대로 재사용해 얇은 루프로 조립하는 게 더 단순하다
  (LangGraph의 Send map-reduce는 그래프 안에서 병렬 fan-out을 위한 것이지, 이 경우 세그먼트별
  `asyncio.gather`로 충분).
- **패널은 어제 배선한 DB 우선 조회를 그대로 탄다.** 세그먼트마다 다른 `target_filter`로
  `panel.get_or_build()`를 부르지만, 같은 `version`(기본 "panel-v1")의 **같은 고정 로스터에서
  부분집합만 다르게 뽑으므로** 세그먼트 간 비교가 "같은 모집단 안에서의 비교"로 성립한다 —
  DB 패널 조회 작업이 이 기능의 전제 조건이었던 셈.
- **영속화(DB 저장) 범위 밖.** 세그먼트 비교 결과는 이번 스코프에서 저장하지 않는다(단일
  시뮬레이션의 9테이블 저장 스키마가 "세그먼트 여러 개" 개념을 아직 모델링하지 않음 — 필요해지면
  별도 설계).

## 3. 스코프 경계

- `core/models.py`·`docs/db-schema.md` 변경 없음.
- 분석팀 테이블 무관.
- 새 엔드포인트는 `api/routers/simulation/router.py`에 추가(§협업규칙 — 자기 라우터 자유 수정).
