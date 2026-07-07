# 컨텍스트 노트 — 개선 모드(IMPROVE) 이미지 처리

## 결론 (2026-07 기준)

원래 계획(기존 광고 이미지를 openai `images.edit` / gemini 멀티모달 참조로 직접 수정)은
**폐기**됐다. `2c8b7eb` "광고 개선 모드 전면 재설계"에서 방향이 바뀌었다 —
**기존 광고를 편집하는 것이 아니라, 시뮬 피드백을 반영해 새로 생성**한다.

폐기 이유(재설계 커밋의 판단). 기존 완성 광고에는 텍스트가 박혀 있어 edit 시 텍스트
이중 노출·잔상 문제가 있고, 제품 일관성은 원본 광고가 아니라 **상품 누끼(컷아웃)** 를
재사용하는 편이 깨끗하다.

## 현재 아키텍처

```
IMPROVE 요청 (simulation_summary 필수, 나머지 옵션)
  ├─ classify_improvements(3-tier LLM 분류기)
  │    시뮬 요약 + plain_summary + improvement_direction + fix_requests
  │    → 이미지 반영 가능한 지시문 list[str] → improvement_context
  ├─ 더미 StrategyPlan(template=None) → select_templates 건너뜀 (conditional edge)
  └─ _generate_improve_candidate (단일 후보 1장, 항상 OpenAI)
       ├─ product_cutout_s3_key 있으면 S3 로드 → _IMPROVE_COMPOSE_TEMPLATE +
       │    _build_inpaint_base_and_mask → edit_with_mask (마스크 인페인팅)
       ├─ 없으면 template 폴백 경로
       └─ 카피는 PIL 합성 (AI 이미지에 글자 미생성 정책 유지)
```

- `existing_ad_s3_key`는 **이미지로 로드하지 않는다** — product_analysis의 제품명 폴백
  문자열 등 텍스트 힌트 전용. 스키마 주석에도 "bytes 로드 없이 텍스트 힌트로만" 명시
- IMPROVE 필수 입력은 `simulation_summary` 하나 (schemas.py validator)
- 누끼 출처. CREATE에서 상품 이미지 업로드 시 컷아웃을 S3 저장 → `get_detail`이
  `product_cutout_s3_key` 반환 → 개선 요청에 실어 재사용

## 진입 경로 (3개)

1. **generator 페이지 개선모드** — 시뮬 선택 → KPI 요약·토론 리포트·누끼 자동 로드 →
   실행. 결과 화면에 원클릭 재생성 버튼(같은 입력 재제출)
2. **채팅 승인 카드** — 시뮬 완료 후 "이 광고로 다시 생성" 수락 시 IMPROVE 폼 프리필
   (context.simulation_id → 백엔드 `api/assistant/improve_context.py`가 KPI·토론 재조회)
3. **채팅 자유 발화** — `run_improvement` 도구 ("아까 시뮬 결과로 개선해줘").
   프리필 완비 시 즉시 실행(gen_progress 카드), 아니면 개선 폼 폴백

## 주의점 (현행 유효)

- 채팅 경로는 `product_cutout_s3_key` 추적 불가(Simulation↔generation DB 연결 없음) →
  null 폴백으로 생성. 연결은 core/models 변경이라 팀 조율 필요
- 생성 모드(product_image_bytes·누끼 저장) 경로와 개선 분기는 입력이 격리돼 있어
  상호 회귀 없음
- 시뮬 결과는 presigned URL(`ad_asset_url`)만 노출 — s3_key 직접 노출은 simulation 팀
  조율 대상(채팅 improve_context는 URL이면 key 힌트를 버리고 진행)

## 히스토리

- 초기 계획(이 문서 구버전). existing_ad_bytes 로드 → openai edit / gemini 참조 재생성
- `2c8b7eb` 전면 재설계로 폐기 → 누끼 인페인팅 + 시뮬 피드백 신규 생성으로 전환
- 이후 추가. 원클릭 재생성 버튼, 채팅 IMPROVE 진입(run_improvement·승인 카드),
  improve_context 백엔드 빌더
