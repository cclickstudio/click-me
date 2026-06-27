# 컨텍스트 노트 — 생성 모드 openai/gemini 재편

## 왜 이 작업을 하는가

`.env` 설정만으로 이미지 모델을 바꿔가며 **OpenAI 계열 vs Gemini 계열**의 광고 이미지
생성 결과를 비교하려는 것이 목적이다.

- 기존. `GENERATOR_GEN_MODE = pipeline | multimodal`. 그런데 `multimodal`은
  실제로 **OpenAI Responses API 전용**(`multimodal_generator.py`가 provider!=openai면
  `NotImplementedError`)이라 이름과 실제가 어긋났다.
- 변경. 모드를 provider 의미 그대로 **`openai | gemini`** 로 재정의한다.

## 확정 동작 매트릭스 (checklist.md와 동일)

| 포맷 | 모드 | 상품 | 이미지 동작 |
| --- | --- | --- | --- |
| single | openai | 있음 | 누끼+인페인팅(보존) |
| single | openai | 없음 | 0부터 생성 |
| single | gemini | 있음 | 상품 멀티모달 입력 참조 생성(보존X) |
| single | gemini | 없음 | 0부터 생성 |
| carousel | openai | — | 공통 배경 OpenAI |
| carousel | gemini | — | 공통 배경 Gemini |

## 핵심 결정 (사용자 합의)

1. **gemini + 상품있음** → 상품 이미지를 Gemini 멀티모달 입력으로 함께 넣어 참조 생성.
   픽셀 단위 보존은 보장하지 않는다(OpenAI식 누끼/마스크 인페인팅은 openai 모드 전용).
2. **gemini 카피** → 이미지+카피를 한 번의 호출로 동시 생성(기존 multimodal 구조 유지, provider만 Gemini).
3. **캐러셀 배경**도 모드에 따라 분기. 단 캐러셀 카피는 single과 달리 `carousel_copy`로 별도
   생성하므로, gemini 캐러셀은 "배경 이미지만 Gemini"이고 동시생성이 아니다.
4. **모드 식별자** env 값을 `openai | gemini`로 변경(`pipeline | multimodal` 폐기).
5. **텍스트는 두 모드 모두 PIL 합성 유지**. AI는 이미지에 글자를 그리지 않는다.
   gemini의 "카피 동시생성"은 카피 *문자열*을 같이 출력한다는 뜻이지, 글자를 그린다는 뜻이 아니다.

## env 키 구조 (확정)

```
GENERATOR_GEN_MODE=openai            # openai | gemini

# openai 모드 (교체 가능)
GENERATOR_IMAGE_MODEL=gpt-image-2        # 0부터 생성(images.generate)
GENERATOR_IMAGE_EDIT_MODEL=gpt-image-1   # 누끼/인페인팅(images.edit)

# gemini 모드 (교체 가능) — native가 한 모델로 이미지+텍스트를 내므로 키 1개
GENERATOR_GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
```

## 분기 지점 (candidate_gen.py)

- 현재. `multimodal = settings.generator_gen_mode == "multimodal"`
  → `if multimodal and product_cutout_bytes is None:` (gemini여도 상품 있으면 openai로 샜다)
- 변경 후. `gemini = settings.generator_gen_mode == "gemini"`
  → gemini면 상품 유무 무관 `generate_image_and_copy`(상품 bytes 전달).
  → openai면 기존 `generate_image`(상품있음=인페인팅 / 없음=0부터).
- 누끼(`remove_product_background`)는 **openai 모드 + 상품있음**일 때만 의미. gemini는
  원본 상품 이미지를 그대로 멀티모달 입력으로 쓰므로 누끼 단계 자체가 없다.

## 주의점 / 회귀 위험

- **openai 모드는 기존 동작 그대로** — 누끼/인페인팅/0부터 경로 회귀 없도록 유지가 1순위.
- Gemini 한 호출에서 이미지+JSON카피를 안정적으로 같이 주는지는 모델별 차이가 있어
  **런타임 검증 필요**. 안 주면 폴백 — 이미지만 Gemini, 카피는 텍스트 LLM(`generate_copies_batch`).
- 상품 이미지를 Gemini에 넣을 때 `inline_data`(mime+bytes). 누끼 안 한 원본 그대로.
- 기존 `multimodal_generator`의 OpenAI Responses 경로는 폐기. `.env.example`의 비활성
  multimodal 키들도 함께 정리.
- candidate_gen `build`의 카피 흐름 — gemini면 `generate_image_and_copy`가 `(image, copy)`를
  반환해 `batch_copies`를 쓰지 않고, openai면 `batch_copies` 사용. 기존 구조 유지.

## 런타임 검증 결과 (완료)

- `gemini-2.5-flash-image` 실 호출 검증 — 이미지(PNG, ~1.5MB)+카피(JSON)를 한 응답에 정상 반환 확인.
  응답 구조는 part0=카피 텍스트, part1=이미지(inline_data). 이미지엔 글자 없음(프롬프트 지시 준수).
- 단 간헐적으로 이미지를 빠뜨리거나(텍스트만) 503(과부하)을 냄 → `generate_image_and_copy`에
  재시도(`_RETRY_BACKOFF=[2,4,6]`, 503·이미지누락 흡수) 추가로 해결. 폴백(이미지만 Gemini + 카피
  별도 LLM)은 미채택 — 동시생성 유지(사용자 결정).
- 실제 운영 `.env`의 `GENERATOR_GEN_MODE`를 `gemini`로 바꿔야 파이프라인에서 gemini 모드가 활성화됨
  (현재 `.env`는 옛 값 `pipeline`으로 남아 있음).
