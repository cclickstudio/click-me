# 상품 이미지 픽셀 보존 합성 — 체크리스트

> 목표: 사용자가 올린 상품 이미지를 광고에 "변형 없이" 넣는다.
> 방식: 누끼(투명배경 추출) → 배경만 AI 생성 → 실제 상품 PNG를 PIL로 합성.

## 결정 사항

- 누끼: OpenAI gpt-image-2 edit + `background="transparent"` (새 의존성 X)
- 그림자: 없음 (상품 그대로 paste)
- 누끼는 후보 3종 공통이므로 **gather 전 1회**만 실행
- compose 모드는 더 이상 상품을 edit API reference로 넘기지 않음 → 배경 전용 생성 + 합성

## 작업

- [x] image_generator.py: `remove_product_background(bytes) -> bytes` 추가
- [x] image_generator.py: `_composite_product_pil` + `composite_product` 추가 (템플릿별 상품영역 배치)
- [x] image_generator.py: compose 분기 정리 — 배경 전용 프롬프트(`_COMPOSE_*` 교체)
- [x] candidate_gen.py: 누끼 1회 실행 + build() 안에서 composite_product → composite_logo
- [x] 단위 테스트: 합성(composite_product) 3종
- [ ] 실제 상품 이미지로 생성 1회 검증 (실 API 키 필요 — 사용자 확인)
- [x] Ruff 통과

## 템플릿별 상품 배치 영역 (텍스트 안 가리게)

- A: 상단 55% (텍스트는 하단 45%) → 상단 중앙
- B: 중앙 59% (텍스트는 top 22% / bottom 40%) → 중앙
- C: 우측 47% (텍스트는 좌측 패널 46%) → 우측 중앙
