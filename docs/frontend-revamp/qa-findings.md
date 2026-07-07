<!-- Phase 6 E2E QA 스윕에서 발견한 결함과 수정 상태를 기록하는 파일 -->

# QA Findings — 프론트 개편 E2E 스윕

> Phase 6에서 루프가 채운다. 스윕→기록→수정→재검을 반복하고, **2회 연속 새 발견 0**이면 종료.
> 심각도: `critical`(기능 끊김) · `major`(눈에 띄는 UI 붕괴) · `minor`(사소한 잘림·정렬·오탈자).

## 요약

- 총 발견: 0 / 수정: 0 / 보류: 0
- 마지막 스윕: (미실행)
- 연속 클린 스윕: 0 / 2

## 발견 목록

| #   | 화면(경로)   | 역할 | 심각도 | 증상                                                    | 재현            | 증거              | 상태 |
| --- | ------------ | ---- | ------ | ------------------------------------------------------- | --------------- | ----------------- | ---- |
| B1  | /simulation/[id] · /center | 전역 | infra(비-UI) | `GET /api/simulation/{id}/db-result`·`/api/center/notifications`·`/api/center/sessions`가 500(asyncpg prepared statement + Neon 풀러 비호환). 프론트엔 "Failed to fetch". **프론트 개편 변경과 무관·기존 인프라 이슈**(백엔드 append-only 범위라 미수정). 결과뷰/센터 라이브 검증이 이 환경에선 막힘 — 토큰화는 build+렌더로 검증. | asdf 로그인→시뮬 상세 진입 | backend.log asyncpg _prepare 트레이스 | open(백엔드 인프라, UI 무관) |

## 진행 로그

- (스윕/수정 이벤트를 여기 이어서 기록: 예 `2026-07-08 03:20 스윕1 — 라우트 42개, 발견 7 / commit abc123`)
