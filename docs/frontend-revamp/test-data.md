<!-- 프론트 개편 중 삽입한 테스트용 데이터 추적 → 작업 후 삭제 체크리스트 (규칙 6) -->

# 테스트 데이터 추적 · 삭제 체크리스트

> 규칙 6: 넣은 테스트용 데이터는 위치·식별자를 여기 기록해뒀다가 작업 후 삭제한다.
> 커밋/작업 종료 전 이 표에 미삭제 항목이 없는지 확인한다.

| 날짜 | 위치(테이블/파일/DB) | 식별자(id·키·이름) | 목적 | 삭제됨? |
| --- | --- | --- | --- | --- |
| 2026-07-08 | Neon `users` | user_id `973ba23f-619f-44b2-8818-77984f1c2ee2` (login_id `test`, COMPANY) | Cognito `test`↔DB 매핑 갭 해소 — COMPANY 대시보드/역할 화면 검증 | ❌ |
| 2026-07-08 | Neon `organization_members` | member_id `9d5ad52e-9379-48fc-8ad9-879c32fe6bbd` (test→org 요한 ddfec494) | test COMPANY 조직 스코프 | ❌ |
| 2026-07-08 | Neon `users` | user_id `9c8c798b-269b-45a7-ba25-6e27db3da470` (login_id `asdf`, USER, team 461b5bed) | Cognito `asdf`↔DB 매핑 갭 해소 — USER 대시보드/역할 화면 검증 | ❌ |
| 2026-07-08 | Neon `organization_members` | member_id `1c5472bb-c2f9-434c-8ec0-7896fa52ab76` (asdf→org 요한 ddfec494) | asdf USER 조직 소속 | ❌ |

> 삭제 스크립트(종료 시): 위 user_id 2건과 member_id 2건을 DELETE. `organization_members` 먼저, 그다음 `users`.
> `uv run python -c "..."` 로 `DELETE FROM organization_members WHERE user_id IN (...); DELETE FROM users WHERE id IN (...)"`.
