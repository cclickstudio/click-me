# 상품 이미지 보존 + 통합 — 체크리스트 (마스크 인페인팅)

> 목표: 올린 상품을 "변형 없이" + "장면에 자연스럽게" 광고에 넣는다.
> 방식: 누끼 → 상품을 캔버스에 배치+마스크 잠금 → AI가 주변 배경/그림자/텍스트 생성.

## 결정 사항

- 누끼: OpenAI gpt-image edit + `background="transparent"` (새 의존성 X)
- 통합: 마스크 인페인팅 (paste 아님) — 상품 보존 + 자연스러움 동시
- 누끼는 후보 3종 공통이므로 **gather 전 1회**만 실행
- 상품 이미지 있으면 **gen_mode 무관** 인페인팅 경로 (multimodal 한방 생성 미사용)

## 작업

- [x] image_generator.py: `remove_product_background()` 추가
- [x] image_generator.py: `_build_inpaint_base_and_mask()` + 배치 박스/`_place_product`
- [x] image_generator.py: compose 분기 → 마스크 인페인팅(edit + mask), 프롬프트 교체
- [x] candidate_gen.py: 누끼 1회 + 상품 있으면 인페인팅 경로 분기
- [x] 단위 테스트: base/mask 생성 3종 (test_inpaint_compose.py)
- [ ] 실제 상품 이미지로 생성 1회 검증 (실 OpenAI 호출 → 사용자 확인 후)
- [x] Ruff 통과

## 템플릿별 상품 배치 박스 (_COMPOSE_PRODUCT_BOXES)

- A: (0.14,0.06,0.86,0.52) 상단 / 텍스트 하단
- B: (0.16,0.20,0.84,0.74) 중앙 / 텍스트 상·하 밴드
- C: (0.52,0.16,0.96,0.84) 우측 / 텍스트 좌측 패널
