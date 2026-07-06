# 시뮬레이션 리포트/UI 고도화 체크리스트 (2026-07-03)

> 우선순위 순서(사용자 확정): 1 → 3 → 5 → 6 → 7. 4(LLM QA 기본 활성화)는 팀 의사결정 필요해 보류.

- [x] 1. KOBACO 벤치마크를 결과 리포트에 노출 (2026-07-03)
  - [x] 카테고리 매핑(SIM_CATEGORIES 15개 → kobaco_benchmarks.json 10개 키) — `kobaco_reference.py`
  - [x] 백엔드: aggregate.payload.kobaco_reference 추가(조회만, 값 병합·환산 금지)
  - [x] 프론트: `/simulation/[id]` 결과 화면에 참고 카드 추가
  - [x] 프론트: 채팅 `SimResultWidget`에도 반영
  - [x] 검증: 신규 단위테스트 4건 + 시뮬 도메인 전체 154 passed
- [x] 2. Individual 모드 페르소나 지정 선택 (2026-07-03)
  - [x] 백엔드: `PanelRepository.list_personas`(필터·페이지네이션) + `GET /api/simulation/panel/personas`
  - [x] 백엔드: `filter_personas`에 persona_id 정확 매칭 추가(age/gender 무시)
  - [x] 프론트: `/simulation` 타깃 설정 카드에 "패널에서 고르기" 목록 + 선택 상태 UI
  - [x] 검증: 신규 단위테스트 6건 + 실 DB 대상 curl 라운드트립(필터 포함) 확인
- [x] 3. 구매의도 분포 차트 (2026-07-03)
  - [x] `/simulation/[id]` 결과 화면엔 이미 있었음(확인만) — 채팅 `SimResultWidget`에 미니 막대로 추가
- [x] 4. 거부율 사유 분해 시각화 (2026-07-03)
  - [x] 결과 화면·채팅 위젯 둘 다 신규 — `reactions[].rejection_reason_tag` 클라이언트 집계(집계 서비스 변경 없음)
  - [x] 채팅은 좁은 폭 고려해 상위 3개만
- [x] 5. 신뢰구간 시각화 (2026-07-03)
  - [x] `/simulation/[id]`엔 이미 텍스트 표기 있었음(확인만) — 채팅 위젯 클릭 의향률 카드에 "95% CI" 서브텍스트 추가
  - [x] 검증: `tsc --noEmit` 통과, 임시 페이지로 스크린샷 확인(KOBACO·구매의도분포·거부사유분해 모두 정상 렌더)

각 항목 완료 시 프론트 `tsc --noEmit` + 관련 pytest, 브라우저 확인 가능한 변경은 Claude Preview로 검증.
