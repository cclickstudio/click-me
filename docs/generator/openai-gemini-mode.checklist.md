# 작업 체크리스트 — 생성 모드 openai/gemini 재편 (모델 비교)

> ✅ **구현 완료** — config(`generator_gen_mode: openai|gemini`)·env.example·candidate_gen
> 분기·Gemini 동시생성(재시도 포함) 전부 반영 확인(2026-07). 아래 체크는 완료 기록.
> 계획과 달라진 점 2가지 — ① gemini 모드에서도 **누끼는 생성·S3 저장**한다(합성엔 미사용,
> 개선 모드 재사용 목적). ② **개선 모드(IMPROVE)는 gen_mode와 무관하게 항상 OpenAI 경로**
> (누끼 인페인팅). 배경·합의는 context-notes.md 참고.

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

- [x] `generator_gen_mode` 기본값 `"pipeline"` → `"openai"`, 주석 `openai | gemini`
- [x] 기존 `generator_multimodal_provider/model/image_model`(OpenAI Responses 전용) 제거
- [x] `generator_gemini_image_model` 신설 (예 `gemini-2.5-flash-image`)
- [x] openai 모드 모델 키 유지 확인 — `generator_image_model`, `generator_image_edit_model`

## ② Gemini 생성기 재구현 — pipeline/multimodal_generator.py

- [x] OpenAI Responses API → Gemini `generate_content` 기반으로 교체
- [x] 이미지+텍스트(카피 JSON) 동시 출력 수신·파싱(기존 `_parse_copy_json` 재사용)
- [x] 상품 이미지가 있으면 `inline_data`로 멀티모달 입력 추가 (시그니처에 `product_image_bytes` 추가)
- [x] aspect_ratio 매핑은 image_providers의 `_GEMINI_NATIVE_ASPECT_RATIO` 재사용
- [x] LangSmith usage 기록(`_record_genai_usage` 패턴) 유지

## ③ 분기 수정 — graph/nodes/candidate_gen.py

- [x] `multimodal` 변수 → `gemini`, 조건을 `if gemini:`(상품 유무 무관)로 변경
- [x] gemini 경로에 상품 이미지 bytes 전달(누끼 없이 원본)
- [x] 카피 배치(`generate_copies_batch`) 스킵 조건 갱신 — gemini면 항상 동시생성이라 배치 불필요
- [x] 누끼(`remove_product_background`) — 계획은 "openai+상품있음만"이었으나,
      **gemini 모드에서도 누끼를 만들어 S3 저장**하는 것으로 구현(합성엔 미사용,
      개선 모드 product_cutout 재사용 목적. candidate_gen.py 주석 참고)
- [x] 캐러셀 공통 배경(`_generate_carousel`)도 모드 분기(gemini면 Gemini로 배경 생성)

## ④ .env.example 갱신

- [x] `GENERATOR_GEN_MODE=openai`(주석 openai|gemini)
- [x] `GENERATOR_GEMINI_IMAGE_MODEL` 예시·교체 후보 주석(gemini-3-pro-image / gemini-3.1-flash-image / gemini-2.5-flash-image)
- [x] openai 모델 교체 후보 주석(gpt-image-1 / gpt-image-2)
- [x] 폐기된 multimodal 키 제거

## ⑤ 테스트

- [x] `tests/generator/` 영향 범위 확인 — image_providers · topology · 기존 multimodal 관련
- [x] Gemini 생성기 단위 테스트(mock 응답으로 이미지+카피 파싱·상품 입력 분기)
- [x] `cd backend && uv run pytest tests/generator -v` 통과

## 공통

- [x] 백엔드 .py 수정 → 커밋 전 Ruff (`uv run ruff format . && uv run ruff check . --fix`)
- [x] 세만틱 커밋 분리 — 설정/생성기/분기/테스트 단위
