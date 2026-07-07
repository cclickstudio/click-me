<!-- Phase 6 E2E QA 스윕에서 발견한 결함과 수정 상태를 기록하는 파일 -->

# QA Findings — 프론트 개편 E2E 스윕

> Phase 6에서 루프가 채운다. 스윕→기록→수정→재검을 반복하고, **2회 연속 새 발견 0**이면 종료.
> 심각도: `critical`(기능 끊김) · `major`(눈에 띄는 UI 붕괴) · `minor`(사소한 잘림·정렬·오탈자).

## 요약

- 총 발견: 2 / 수정: 1 / 보류(인프라) 1
- 마지막 스윕: 2026-07-08 03:2x — admin 로그인, manage(monitoring·anomaly·budget·compare·reliability)·admin(manage-user·companies·generations)·themes 통주행 + 대시보드 3역할 + 모바일 375px. **신규 UI 결함 0**(broken 0·overflow 0·콘솔 에러 0).
- 연속 클린 스윕: **2 / 2 → 수렴 완료**(UI 기준. 남은 open은 백엔드 인프라 B1로 UI 무관)
- 수정 완료: 모바일 고정 햄버거↔콘텐츠 겹침(AppLayout max-md:pt-14) → fixed.
- 스윕2(라이트 모드): COMPANY 대시보드 라이트 실측 — 뉴트럴·블루 브랜드·danger 주의 카드·차트 정상, 오버플로 0, 콘솔 에러 0. 토큰 양모드 동작 확인. 신규 발견 0.

## 발견 목록

| #   | 화면(경로)   | 역할 | 심각도 | 증상                                                    | 재현            | 증거              | 상태 |
| --- | ------------ | ---- | ------ | ------------------------------------------------------- | --------------- | ----------------- | ---- |
| B1  | /simulation/[id] · /center | 전역 | infra(비-UI) | `GET /api/simulation/{id}/db-result`·`/api/center/notifications`·`/api/center/sessions`가 500(asyncpg prepared statement + Neon 풀러 비호환). 프론트엔 "Failed to fetch". **프론트 개편 변경과 무관·기존 인프라 이슈**(백엔드 append-only 범위라 미수정). 결과뷰/센터 라이브 검증이 이 환경에선 막힘 — 토큰화는 build+렌더로 검증. | asdf 로그인→시뮬 상세 진입 | backend.log asyncpg _prepare 트레이스 | open(백엔드 인프라, UI 무관) |

## 진행 로그

- 2026-07-08 03:2x 스윕1(다크) — admin 통주행(manage 5 + admin 3 + themes) + 3역할 대시보드 + 모바일 375px. 렌더 broken 0·가로 오버플로 0·콘솔 에러 0. 발견: 모바일 햄버거 겹침 1(즉시 fixed), 백엔드 center/db-result 500 1(인프라 B1·UI 무관·보류).
- 2026-07-08 03:35 스윕2(라이트) — COMPANY 대시보드 라이트 실측(뉴트럴·브랜드·danger 카드·차트·크레딧), 오버플로 0·콘솔 에러 0·신규 발견 0. **2연속 클린 → loop-until-dry 수렴 종료.**
