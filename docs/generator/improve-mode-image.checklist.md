# 작업 체크리스트 — 개선 모드(IMPROVE) 이미지 처리

> ⚠️ **이 문서의 원래 계획(기존 광고 이미지를 openai edit / gemini 멀티모달로 직접 수정)은
> 폐기됐다** — `2c8b7eb` "광고 개선 모드 전면 재설계"에서 기존 광고 편집이 아니라
> **시뮬 피드백 기반 신규 생성**으로 전환. 아래는 현재 구현 기준 체크리스트.
> 배경·결정은 improve-mode-image.context-notes.md 참고.

## 현재 구현 (완료)

- [x] `existing_ad_bytes` 제거 — 기존 광고 이미지는 **로드하지 않음**. `existing_ad_s3_key`는
      텍스트 힌트로만 사용(product_analysis 폴백 문자열)
- [x] 3-tier 분류기 `classify_improvements` — 시뮬 결과(simulation_summary·plain_summary·
      improvement_direction) + 사용자 fix_requests → 이미지 지시문 list[str]
      ([improvement_guide.py](backend/domain/generator/pipeline/improvement_guide.py))
- [x] 개선 모드 = **단일 후보 1장**, 항상 OpenAI 경로, 더미 StrategyPlan(template=None)
      ([candidate_gen.py](backend/domain/generator/graph/nodes/candidate_gen.py) `_generate_improve_candidate`)
- [x] **상품 누끼 재사용** — CREATE 완료 시 컷아웃 S3 저장 → 개선 요청의
      `product_cutout_s3_key`로 재로드 → 마스크 인페인팅(edit_with_mask)
- [x] template=None 자유 레이아웃(`_IMPROVE_COMPOSE_TEMPLATE`) 전 파이프라인 폴백
- [x] 텍스트는 PIL 합성 유지(AI 이미지에 글자 미생성)
- [x] 프론트 개선모드 화면 — 기존광고·시뮬분석 readOnly 표시 + 누끼 미리보기 + 수정요청 입력,
      요청 바디에 `mode/simulation_summary/plain_summary/improvement_direction/fix_requests/
      product_cutout_s3_key` 전달 (existing_ad_s3_key는 바디 미포함)
- [x] 개선 결과 화면 **원클릭 재생성 버튼** (같은 입력 재제출, 새 시안이 교체)
- [x] **채팅 IMPROVE 진입** — `run_improvement` 도구 + 시뮬 완료 승인 카드가 IMPROVE 폼
      프리필(백엔드 improve_context가 simulation_id로 재료 조립)

## 남은 항목

- [ ] 채팅 경로의 `product_cutout_s3_key` 추적 — Simulation↔generation DB 연결이 없어
      채팅 IMPROVE는 누끼 없이(null 폴백) 생성. 연결하려면 모델 변경(팀 조율) 필요
- [ ] simulation 결과 응답에 s3_key 직접 노출(만료 없는 식별자) — simulation 팀 조율 대상
