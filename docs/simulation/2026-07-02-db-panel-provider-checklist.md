# DB 기반 고정 패널 조회 — 체크리스트

> 결정·근거는 `2026-07-02-db-panel-provider-context-notes.md` 참조.

- [x] `domain/simulation/models.py` — `Persona`에 `weight`(Numeric, default 1.0) 컬럼 추가
- [x] Alembic 마이그레이션 — `personas.weight` 컬럼 추가(`0002_persona_weight`, 0001_baseline 뒤에 체인)
- [x] `repositories/panel_repository.py`
  - [x] `PanelRepository.create()` — persona INSERT에 `weight=p.weight` 반영
  - [x] `PanelRepository.get_by_version(version) -> tuple[uuid.UUID, list[Persona]] | None` 신설
        (Panel 조회 → 없으면 None, 있으면 personas JOIN → `contracts.schemas.Persona`로 역변환)
- [x] `DbPanelProvider` 신설(`tools/panel/db_provider.py`)
  - [x] `get_or_build(spec)`: DB 조회 → 히트 시 `filter_personas`로 부분집합 반환
  - [x] 미스 시 생성자에 주입된 폴백 provider(`CachedPanelProvider`/`PersonaSampler`)에 위임
- [x] `wiring.py`
  - [x] `build_panel_provider(settings, session_factory=None)` — DB 세션 있으면 `DbPanelProvider`
        우선(폴백은 기존 로직 그대로), 없으면 기존 로직 유지(회귀 0)
  - [x] `build_simulation_service`가 `build_panel_provider`에 `session_factory` 전달하도록 배선
- [x] `tools/panel/build_cli.py` — 빌드 후 DB 저장 추가(JSON 저장은 유지, 둘 다 실행)
- [x] 테스트
  - [x] `PanelRepository.get_by_version` 라운드트립(SQLite, `test_repositories.py`에 추가) — weight 왕복 보존 확인 포함
  - [x] `DbPanelProvider` 히트/미스 단위테스트(스텁 샘플러·스텁 폴백, LLM✗) — `test_db_panel_provider.py` 신설
  - [x] 기존 `test_panel_builder.py` 회귀 확인 — 변경 없이 그대로 통과
- [x] `cd backend && uv run ruff format . && uv run ruff check .` — 변경 파일·전체 모두 clean
- [x] `cd backend && uv run pytest`(simulation 스코프) — 162 passed, 3 skipped(실 LLM, RUN_LIVE_LLM=1 필요), 0 failed

## 남은 수동 단계 (선택)

- [ ] 실제 Neon DB에 `alembic upgrade head` 적용(0002 마이그레이션 반영) — 실 배포 전 필요
- [ ] `uv run python -m domain.simulation.tools.panel.build_cli --size 1000 --seed 0` 1회 실행 —
      실 GEMINI_API_KEY 비용 발생(서사 1000콜)이라 사용자 승인 후 별도 진행 권장.
      실행 안 해도 회귀는 없음 — 첫 실 시뮬레이션 런이 DB에 자동으로 `panel-v1`을 심고,
      이후 런부터 그 결과를 재사용(§3.6 원래 취지인 "1000명 베이스"보다는 좁은 커버리지).
