# 컨텍스트 노트 — 상품 이미지 픽셀 보존 합성

## 왜 이 작업을 하는가

기존 compose 모드는 `images.edit`에 상품 이미지를 **마스크 없이** 넘겨서, AI가
이미지 전체를 재생성 → 업로드한 상품과 결과물의 상품이 크게 달라지는 문제.
(프롬프트의 "PRODUCT IS PROTECTED"는 강제력 없는 텍스트일 뿐.)

해결: 실제 상품 픽셀을 그대로 paste. AI는 배경만 그린다.

## 핵심 흐름

```
상품 이미지
 → remove_product_background()   # gpt-image-2 edit, background=transparent → RGBA PNG (1회)
 → 배경 생성 (후보 3종 각각, 상품 없는 배경 + 텍스트)
 → composite_product()           # 템플릿 상품영역에 paste
 → composite_logo()              # 기존
 → S3
```

## 주의점

- 누끼를 AI(edit)로 하므로 추출 단계에서 상품이 미세하게 변형될 수 있음.
  부족하면 `rembg`(로컬, onnxruntime+u2net) 도입으로 전환.
- gpt-image-2 edit + `background="transparent"`는 PNG(alpha) 반환. b64_json 디코딩.
- 누끼 API 호출은 비용↑ → 반드시 후보 루프 밖 1회.
- multimodal 모드(`GENERATOR_GEN_MODE=multimodal`)는 product_image를 아예 안 씀 → 이번 작업 범위는 pipeline 모드. multimodal 합류는 후속.

## 합성 배치 (composite_product, _composite_logo_pil 패턴 차용)

- 상품을 상품영역 박스 안에 비율 유지로 contain → 박스 중앙 정렬.
- A: y중심 ~ 상단 27%, 폭 ~ 화면 60%
- B: y중심 ~ 화면 50%, 폭 ~ 화면 62%
- C: x중심 ~ 화면 75%, 폭 ~ 화면 42%
- 실제 값은 생성 결과 보고 미세조정.
