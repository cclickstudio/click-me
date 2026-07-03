# DB 기반 고정 패널 조회 — 컨텍스트 노트

> 착수 전 합의된 결정과 근거. 선행 문서: `Persona/context-notes.md`(§3.6 고정 패널 원칙) · `Persona/checklist.md`(P8 영속화).

## 0. 문제

`wiring.build_panel_provider`는 로컬 JSON(`panel-v1.json`, gitignore)이 있으면 로드, 없으면 매 런마다
`PersonaSampler`로 **라이브 재샘플링**한다. 반면 `PanelRepository.create()`(쓰기 경로)는 이미
`version` UNIQUE 기준 idempotent 재사용 로직을 구현해뒀다 — **쓰기 경로만 있고 읽기 경로가 없는 상태**.

부작용:
1. JSON 캐시가 없는 환경(이 저장소 포함)에서는 매 런마다 새로 샘플링 → 서사(4-a) 빈 채.
2. `PanelSpec.seed` 기본값 0 덕에 "같은 size+target_filter"면 우연히 결정론적이지만,
   §3.6이 말하는 "하나의 고정 로스터(예 1000명)를 요청마다 필터링"과는 다르다 —
   size·target_filter 조합이 다른 두 런은 서로 다른 rng 소비량이라 겹치는 인물 집합이 아니다.
3. 로컬 JSON은 EC2 재배포 시 사라짐(gitignore) — 영속 저장소가 아니다.

## 1. 결정

- **DB(`panels`/`personas` 테이블)를 고정 패널의 단일 소스로 삼는다.** 로컬 JSON 메커니즘
  (`CachedPanelProvider`·`build_cli`·`save_panel`/`load_panel`)은 삭제하지 않고 유지 —
  기존 유닛테스트(`test_panel_builder.py`)가 순수 함수 단위로 이미 검증 중이고,
  DB 미구성 환경(로컬 개발/테스트)의 폴백으로 여전히 유효하다.
- **읽기 경로 신설**: `PanelRepository.get_by_version(version)` — Panel+Persona 조인 조회.
  없으면 `None` 반환(호출측이 폴백 판단).
- **`DbPanelProvider`**: `get_or_build(spec)`에서 DB 조회 → 있으면 §3.6 방식대로
  `filter_personas`로 부분집합 반환. 없으면 **기존 폴백 provider에 위임**(라이브 샘플러 또는
  JSON 캐시) — 요청 경로 안에서 신규로 1000명을 빌드하지 않는다(레이턴시 급증 방지).
- **`build_cli`가 DB에도 쓰도록 확장** — 오프라인 1회 실행으로 정식 베이스 패널(예 1000명)을
  만들어 DB에 심는다(기존 JSON 저장은 그대로 유지, DB 저장을 추가). 이게 §3.6이 원래
  의도한 "패널 빌드는 오프라인 1회" 흐름과 정합적이다.
- **`build_simulation_service`가 완료 런을 저장할 때 이미 `PanelRepository.create(version=...)`를
  호출**하므로, DB에 아직 해당 version이 없으면 (build_cli를 안 돌렸어도) 첫 런의 라이브 샘플
  결과가 자동으로 DB에 심어진다 — 다만 이 경우도 "1000명 베이스"가 아니라 "그 런의 size만큼"만
  저장되므로, 이후 다른 size/target_filter 요청은 여전히 커버리지 부족일 수 있다.
  **정식 커버리지를 원하면 `build_cli` 1회 실행이 여전히 권장.**

## 2. 스키마 갭 — `weight` 컬럼 누락

`contracts.Persona.weight`(§3.7 표본가중치, `PersonaSampler`가 stratified/raking 모드에서 계산)가
`domain/simulation/models.py`의 `Persona` ORM엔 컬럼이 없다(`PersonaReaction.weight`는 있음 — 반응
단계에서만 저장됨). 기본 `allocation="proportional"`·`rake_to_census=False`(둘 다 기본값)에서는
weight가 사실상 1.0(self-weighting)이라 당장 회귀는 없지만, DB 캐시 히트 후 재사용 시
weight가 스키마 기본값(1.0)으로 리셋되는 건 stratified/raking 모드를 켰을 때 잠재적 집계 왜곡이다.

**결정**: `personas.weight` 컬럼 추가(Alembic, `domain/simulation/` 소유 테이블이라 §협업규칙상
사전공지 불요 — `SIMULATOR_SCOPE.md`가 9테이블을 시뮬레이터팀 소유로 명시). 기본값 1.0.

**보류(비수정)**: `social_values_deep`·`social_economic`·원본 `persona_id`(문자열 ref)는 DB에
저장하지 않는다. 앞의 둘은 `Data_Collection.md` 기준 전 항목이 **항상 빈 dict**(데이터 미확보,
프레임워크만) — 잃을 값이 없다. `persona_id`는 DB 조회 시 `id`(UUID) 기반으로 합성 재구성
(`f"P_{id.hex[:8]}"`)해도 런 내 유일성·안정성은 보장된다.

## 3. 스코프 경계

- `core/models.py`·`docs/db-schema.md` 변경 없음(공통부 미터치).
- 분석팀 테이블(`토론*`·`진단`·`개선권고`·`보고서`) 무관.
- 마감 2026-07-08(6일 남음) 고려 — 요청 경로 레이턴시·리스크 최소화가 우선. 1000명 베이스
  자동 부트스트랩(라이브 요청 중 트리거) 같은 확장은 이번 스코프에서 제외.
