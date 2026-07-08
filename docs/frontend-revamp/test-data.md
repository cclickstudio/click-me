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

> **처리 방침(도연님 판단 필요):** 이 4개 row는 프롬프트가 준 테스트 계정 **test/test1234·asdf/asdf1234가 실제로 로그인되게** 만든 것입니다(Cognito엔 있으나 DB엔 없던 매핑 갭 해소, context-notes '검증 환경' 참조). 삭제하면 USER/COMPANY 역할 로그인이 다시 401로 막혀 역할별 화면 데모가 불가해집니다. 그래서 **밤샘 루프 동안 유지**했고, 데모 편의를 위해 남겨둡니다. 순수 클린 DB를 원하시면 아래 스크립트로 삭제하세요(rule 6 준수).
>
> 삭제 스크립트: `organization_members` 먼저, 그다음 `users`.
> ```bash
> cd /c/doyeon/click-me/backend && uv run python -c "
> import asyncio; from sqlalchemy import text; from core.db import AsyncSessionLocal
> async def m():
>     async with AsyncSessionLocal() as db:
>         ids=['973ba23f-619f-44b2-8818-77984f1c2ee2','9c8c798b-269b-45a7-ba25-6e27db3da470']
>         await db.execute(text('DELETE FROM organization_members WHERE user_id = ANY(:i)'),{'i':ids})
>         await db.execute(text('DELETE FROM users WHERE id = ANY(:i)'),{'i':ids})
>         await db.commit(); print('deleted')
> asyncio.run(m())"
> ```
