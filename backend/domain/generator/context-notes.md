# 컨텍스트 노트 — 상품 이미지 보존 + 자연스러운 통합 (마스크 인페인팅)

## 왜 이 작업을 하는가

1차 문제: 기존 compose는 `images.edit`에 상품을 **마스크 없이** 넘겨 전체 재생성
→ 상품이 크게 달라짐.
2차 문제(순수 합성 시도): 배경 따로 생성 + 실제 상품 paste → 픽셀은 보존되나
조명·그림자·원근 불일치로 "오려붙인" 부자연스러움.

최종 해결: **마스크 인페인팅**. 실제 상품을 캔버스에 배치하고 마스크로 잠근 뒤,
AI가 상품을 보면서 주변 배경·그림자·텍스트를 한 패스로 생성.
→ 상품 픽셀 보존 + 장면 통합의 자연스러움 동시 확보.

## 핵심 흐름

```
상품 이미지
 → remove_product_background()        # gpt-image edit, background=transparent → RGBA (1회)
 → _build_inpaint_base_and_mask()     # 상품을 템플릿 박스에 배치 → base + mask 생성
 → images.edit(image=base, mask=mask, prompt=인페인팅)  # 후보 3종 각각
 → composite_logo()                   # 기존
 → S3
```

## 마스크 규약 (중요)

OpenAI: 마스크의 **투명(alpha=0) 영역이 "수정될 곳"**.
→ 상품 실루엣 = 불투명(보존), 나머지 = 투명(배경/텍스트 생성).
`_build_inpaint_base_and_mask`에서 상품 알파를 마스크에 paste해 실루엣만 불투명화.

## 주의점

- 누끼를 AI(edit)로 하므로 추출 단계에서 상품이 미세 변형 가능 → 부족하면 `rembg`로 전환.
- 누끼 API 호출은 비용↑ → 반드시 후보 루프 밖 1회.
- 상품 이미지가 있으면 **gen_mode 무관**하게 인페인팅 경로(candidate_gen에서 분기).
  multimodal 한방 생성은 상품 보존 불가라 상품 있을 땐 안 씀.
- 마스크 경계에서 가끔 AI가 상품을 살짝 건드릴 수 있음(순수 재생성보다는 안정적).

## 상품 배치 박스 (_COMPOSE_PRODUCT_BOXES, 화면 비율)

- A: (0.14, 0.06, 0.86, 0.52) 상단 — 텍스트는 하단
- B: (0.16, 0.20, 0.84, 0.74) 중앙 — 텍스트는 상·하 밴드
- C: (0.52, 0.16, 0.96, 0.84) 우측 — 텍스트는 좌측 패널
- 실제 값은 생성 결과 보고 미세조정.

---

# 추가 컨텍스트 — 텍스트 렌더링을 PIL로 전환 (버그 ②③ 대응)

## 왜

- gpt-image가 한글 텍스트를 가장자리에서 잘리게 그리고(③), 상품 글자/제공 카피를
  흉내내다 깨뜨림(②). 확산 모델 텍스트 렌더링은 신뢰 불가.
- 해결: **AI는 텍스트를 그리지 않고**, 헤드라인/본문/CTA를 **PIL로 직접** 지정 zone에 렌더.
  → 잘림 물리적 불가 + 제공 카피 그대로 + 상품 글자는 마스크로 보존.

## 설계

```
이미지 모델 → 배경+상품만 (텍스트 없이)   # generate / inpaint 양쪽 프롬프트 "no text"
 → render_ad_text()  # pipeline/text_overlay.py, _TEXT_LAYOUT zone 비율 재활용
   - shrink-to-fit(폰트 자동축소) + 줄바꿈 + 가장자리 안전여백
   - 패널 배경 + CTA 버튼
 → composite_logo → S3
```

## 주의

- 한글 TTF 폰트를 repo에 번들 (assets/fonts/). 라이선스 OFL 계열(Pretendard/NotoSansKR).
- generate 모드(비compose)도 텍스트존 비우고 PIL로 그림 → 팀원 공유 경로라 영향 공지.
- _TEXT_LAYOUT(영문 디자인 지시)은 PIL zone 좌표로 재해석해 사용.
