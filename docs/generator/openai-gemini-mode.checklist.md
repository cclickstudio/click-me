# 작업 체크리스트 — 생성 모드 openai/gemini 재편 (모델 비교)

> 목표. `GENERATOR_GEN_MODE`를 **openai/gemini** 2모드로 재정의하고, 각 모드의 이미지 모델을
> `.env`로 교체하며 두 계열(OpenAI vs Gemini)의 생성 결과를 비교한다.
> 배경·합의는 context-notes.md 참고.

## 목표 동작 매트릭스

| 포맷 | 모드 | 상품 | 이미지 동작 | 카피 |
| --- | --- | --- | --- | --- |
| single | openai | 있음 | 누끼+마스크 인페인팅(상품 픽셀 보존) | 별도 텍스트 LLM |
| single | openai | 없음 | 0부터 생성(`images.generate`) | 별도 텍스트 LLM |
| single | gemini | 있음 | 상품 이미지를 멀티모달 입력으로 참조 생성(보존X) | 동시 |
| single | gemini | 없음 | 0부터 생성(`generate_content`) | 동시 |
| carousel | openai | — | 공통 배경 OpenAI 생성(현행) | carousel_copy(별도) |
| carousel | gemini | — | 공통 배경 Gemini 생성 | carousel_copy(별도) |

> 공통. 이미지 안 글자는 AI가 그리지 않고 PIL(`render_ad_text`)로 합성 — 두 모드 동일.

## ① 설정 재편 — core/config.py

- [ ] `generator_gen_mode` 기본값 `"pipeline"` → `"openai"`, 주석 `openai | gemini`
- [ ] 기존 `generator_multimodal_provider/model/image_model`(OpenAI Responses 전용) 제거
- [ ] `generator_gemini_image_model` 신설 (예 `gemini-2.5-flash-image`)
- [ ] openai 모드 모델 키 유지 확인 — `generator_image_model`, `generator_image_edit_model`

## ② Gemini 생성기 재구현 — pipeline/multimodal_generator.py

- [ ] OpenAI Responses API → Gemini `generate_content` 기반으로 교체
- [ ] 이미지+텍스트(카피 JSON) 동시 출력 수신·파싱(기존 `_parse_copy_json` 재사용)
- [ ] 상품 이미지가 있으면 `inline_data`로 멀티모달 입력 추가 (시그니처에 `product_image_bytes` 추가)
- [ ] aspect_ratio 매핑은 image_providers의 `_GEMINI_NATIVE_ASPECT_RATIO` 재사용
- [ ] LangSmith usage 기록(`_record_genai_usage` 패턴) 유지

## ③ 분기 수정 — graph/nodes/candidate_gen.py

- [ ] `multimodal` 변수 → `gemini`, 조건을 `if gemini:`(상품 유무 무관)로 변경
- [ ] gemini 경로에 상품 이미지 bytes 전달(누끼 없이 원본)
- [ ] 카피 배치(`generate_copies_batch`) 스킵 조건 갱신 — gemini면 항상 동시생성이라 배치 불필요
- [ ] 누끼(`remove_product_background`)는 openai 모드 + 상품있음일 때만 실행되도록
- [ ] 캐러셀 공통 배경(`_generate_carousel`)도 모드 분기(gemini면 Gemini로 배경 생성)

## ④ .env.example 갱신

- [ ] `GENERATOR_GEN_MODE=openai`(주석 openai|gemini)
- [ ] `GENERATOR_GEMINI_IMAGE_MODEL` 예시·교체 후보 주석(gemini-3-pro-image / gemini-3.1-flash-image / gemini-2.5-flash-image)
- [ ] openai 모델 교체 후보 주석(gpt-image-1 / gpt-image-2)
- [ ] 폐기된 multimodal 키 제거

## ⑤ 테스트

- [ ] `tests/generator/` 영향 범위 확인 — image_providers · topology · 기존 multimodal 관련
- [ ] Gemini 생성기 단위 테스트(mock 응답으로 이미지+카피 파싱·상품 입력 분기)
- [ ] `cd backend && uv run pytest tests/generator -v` 통과

## 공통

- [ ] 백엔드 .py 수정 → 커밋 전 Ruff (`uv run ruff format . && uv run ruff check . --fix`)
- [ ] 세만틱 커밋 분리 — 설정/생성기/분기/테스트 단위
