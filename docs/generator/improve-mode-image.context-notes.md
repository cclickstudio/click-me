# 컨텍스트 노트 — 개선 모드 기존 광고 이미지 연결

## 왜 이 작업을 하는가

시뮬레이션은 (pull `7e1158d`로) 업로드 광고 이미지를 S3에 영속 저장하고 `ads.asset_url`에
s3_key를 기록한다. 그런데 generator **개선 모드(IMPROVE)** 는 `existing_ad_s3_key`를
받기만 하고 **이미지로 쓰지 않는다** — [product_analysis.py:24](backend/domain/generator/graph/nodes/product_analysis.py#L24)
에서 product_name 폴백 문자열로만 사용. 시뮬 요약·수정요청을 텍스트(`improvement_context`)로만
반영해 사실상 0부터 재생성한다. 기존 광고 이미지를 실제로 불러와 개선하도록 연결한다.

## 현황 (조사 결과)

- 시뮬 저장 — [ad_image_store.persist_ad_image](backend/domain/simulation/adapters/ad_image_store.py#L35)
  가 `simulation/{uuid}.{ext}`로 업로드 → `(presigned_url, s3_key)`. DB는 s3_key 우선 저장
  ([persistence.py:88](backend/domain/simulation/repositories/persistence.py#L88)).
- 시뮬 결과 조회는 **presigned URL**(`ad_asset_url`)만 노출 — s3_key 직접 노출 안 함
  ([simulation_repository.py:302](backend/domain/simulation/repositories/simulation_repository.py#L302)).
- openai `images.generate`는 이미지 입력 불가 → 기존 이미지 활용은 `images.edit`뿐.
  edit 경로는 [image_generator.py:521-560](backend/domain/generator/pipeline/image_generator.py#L521-L560)
  에 **이미 구현**돼 있으나 candidate_gen이 `original_image_bytes`를 안 넘겨 데드코드.
- gemini `generate_content`는 이미지를 멀티모달 입력으로 받음(이미 `generate_image_and_copy`가
  `product_image_bytes` 지원) → 개선은 그 입력에 기존 광고를 넣고 개선 프롬프트.
- chat 오케스트레이터(generate 어시스턴트)는 wiring만 있고 호출 라우터가 없어 `improve_context`
  경로는 현재 미작동(후순위). 그래서 현실적 트리거는 generator 라우터 직접 호출.

## 확정 결정 (사용자 합의)

1. openai 개선 = edit(직접 수정), gemini 개선 = 멀티모달 참조. **둘 다 구현**.
2. 범위 = **백엔드까지**(프론트 버튼 제외).
3. `existing_ad_s3_key` = s3 key **또는** http(s) URL 둘 다 로드(key→download_bytes, http→httpx).
   → 시뮬 결과의 presigned URL을 그대로 넘겨도 동작하므로 simulation 도메인 수정 없이 연결 가능.

## 구현 지점

- 이미지 로드/주입은 [generator_service.py:79-122](backend/domain/generator/service/generator_service.py#L79-L122)
  의 `product_image_bytes` 패턴을 그대로 따른다(start_generation에서 _tasks에 적재 → _run_pipeline에서 pop→state).
- 개선 모드 분기는 [candidate_gen.py](backend/domain/generator/graph/nodes/candidate_gen.py)의
  `gemini` 분기와 나란히. openai면 `generate_image(original_image_bytes=...)`, gemini면
  `generate_image_and_copy(reference_image_bytes=...)`.

## 주의점 / 회귀 위험

- 개선 모드는 `simulation_summary` 필수(스키마 validator) — 전달 시 시뮬 요약도 함께 와야 함.
- 기존 완성 광고에는 텍스트가 이미 박혀 있음 → edit 프롬프트는 "기존 텍스트 영역 비우고 배경 개선",
  카피는 PIL로 새로 합성(기존 PIL 합성 정책 유지). 텍스트 이중 노출 주의.
- 생성 모드(product_image_bytes, 누끼/인페인팅) 경로 회귀 없도록 — 개선 분기는 별도 입력으로 격리.
- simulation 결과의 s3_key 노출(더 견고한 전달)은 simulation 도메인 작업이라 **협업 조율 대상**.
  이번 범위에서는 generator robust 로드(key/URL)로 우회.

## 미해결 / 다음 단계

- 프론트 시뮬 결과 페이지 "개선 시안 생성" 버튼 연동(이번 범위 제외).
- simulation 결과 응답에 s3_key 노출(만료 없는 식별자 전달) — simulation 팀과 조율.
