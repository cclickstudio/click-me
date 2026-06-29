# context-notes — Alembic 빈 DB 자립 실행 수리 (scratch, 커밋 제외)

## 문제

빈 Postgres에 `alembic upgrade head` → 004(`ALTER personas...`)에서 `relation "personas" does not exist`로 실패.
근본 원인: 시뮬 SimBase 테이블이 마이그레이션에 없음 + 001의 simulations·persona_responses가 구 v2.0 스키마(실 DB는 SimBase).

## 결정 (사용자 승인: 전체 정합)

신규 마이그레이션 1개 `003b` (down_revision=003), `004.down_revision: 003→003b`.
003b는 **라이브(alembic 024/025)에선 절대 실행 안 됨** — head 도달분만 실행. 빈 DB에서만 실행되며 그 시점 simulations/persona_responses는 001이 막 만든 v2.0(빈 테이블).

## 진실 소스

- 컬럼/타입/default/nullable/FK → `docs/db-erd.md` (introspection, alembic 024 기준)
- numeric 정밀도/컬럼 완전성 → `backend/domain/simulation/models.py` (SimBase ORM)
- additive 컬럼은 기존 마이그레이션이 추가 → 003b에선 제외(baseline):
  - 004: personas.socioeconomic, persona_responses.weight, simulation_aggregates.effective_n
  - 006: ad_analyses.detected_objective
  - 010: persona_responses.brand_recognized·perceived_brand, simulation_aggregates.brand_recognition_rate

## 체크리스트

- [ ] 003b 작성 (5테이블 신설 + simulations·persona_responses v2.0→SimBase 변환, 멱등)
- [ ] 004 down_revision 003→003b
- [ ] docker pgvector/pgvector:pg18 (port 55432, .env 절대 미사용 — DATABASE_URL 강제 override)
- [ ] 타깃이 빈 docker DB인지 확인(테이블 0개) 후 upgrade head
- [ ] introspection으로 7테이블(panels/personas/ad_analyses/rubric_scores/simulation_aggregates/simulations/persona_responses) == db-erd 검증
- [ ] ruff format/check
- [ ] docker 정리, scratch 파일 정리

## head 주의

repo head는 task가 말한 024가 아니라 **025**(`025_drop_unused_tables`, down_revision=024). 025는 19개 미사용 테이블 DROP(내 7테이블은 미포함). db-erd는 024 기준이라 025가 drop한 테이블은 upgrade head 후 부재 — 정상.
