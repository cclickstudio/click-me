# 3-모드 분석 UX — Persona Set(세그먼트 비교) 체크리스트

> 결정·근거는 `2026-07-02-persona-set-comparison-context-notes.md` 참조.
> Individual/Synthetic 모드는 백엔드 변경 불필요(§0) — 이 체크리스트는 Persona Set만 다룬다.

- [x] `graph/run_graph.py` — `interpret_ad` 노드 로직을 `interpret_and_score()` 순수 함수로 추출
      (그래프 노드·신규 서비스가 공유, 중복 제거)
- [x] `contracts/schemas.py` — `SegmentSpec`(label·target_filter·sample_size) 신설
- [x] `service/segment_comparison_service.py` — `SegmentComparisonService` 신설
  - [x] 광고 해석·루브릭 1회, 세그먼트별 패널 로드→반응(`asyncio.gather`)→집계 반복
  - [x] 세그먼트 내 개별 페르소나 반응 실패는 건너뜀(run_graph.react와 동일 정책)
- [x] `wiring.py` — `build_segment_comparison_service()` Composition Root 신설
      (기존 `build_simulation_service`와 동일 실 어댑터 재사용, DB 고정 패널 포함)
- [x] `api/routers/simulation/router.py` — `POST /compare-segments` 신설
      (ad 필드 + `segments` JSON 배열 → 세그먼트별 personas·reactions·aggregate 반환)
- [x] 테스트(`test_segment_comparison_service.py`, 전부 LLM✗ 스텁)
  - [x] 세그먼트 3개여도 광고 해석은 1회만 호출되는지
  - [x] 세그먼트별 `target_filter`가 실제로 적용되는지 + 반응/집계 개수 정합
- [x] `ruff format`·`ruff check` — 전체 clean
- [x] pytest — 164 passed / 3 skipped(실 LLM) / 0 failed
- [x] 라우터 모듈 로드 스모크 확인(`/compare-segments` 등록 확인)

## 스코프 밖(의도적으로 안 함)

- Persona Set 비교 결과의 DB 영속화 — 9테이블 스키마가 "세그먼트 여러 개" 개념을 아직
  모델링하지 않음. 필요해지면 별도 설계.
- 프론트엔드 UI(세그먼트 프리셋 선택·비교 뷰 렌더링) — 백엔드 API까지가 이번 스코프.
- Individual 모드 전용 응답 포맷(1인 서사 뷰) — 기존 `/run`(`sample_size=1`) 응답을
  프론트가 다르게 렌더링하면 되므로 백엔드 변경 없음.
