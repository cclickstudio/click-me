# 오늘 작업 체크리스트 (요한) — 생성 버그 3건 + 이미지생성 챗봇

> 우선순위 ① → ② → ③ → 챗봇. ②(PIL 텍스트)가 핵심축이며 ③ 일부를 흡수한다.
> 이전 작업(마스크 인페인팅)은 커밋 완료(d634cc8). context-notes.md 참고.

## ① 프로젝트 내역 누락 픽스 (빠름)

- [x] 원인: selectedProjectId가 React state-only → 이동·새로고침 시 null → project_id=null
- [x] ProjectContext: selectedProjectId localStorage 고정(sticky) + 복원
- [x] generator/page.tsx: 프로젝트 미선택 시 생성 차단 가드
- [x] 백엔드 start_generation: project_id=null 경고 로그
- [ ] 검증(런타임): 프로젝트 안에서 생성 → 내역 즉시 + 리로드 후 남는지 (사용자 확인)

## ② 상하 글씨 잘림 → PIL 직접 렌더링 (핵심)

- [ ] 한글 TTF 폰트 번들 (assets/fonts/, 예: Pretendard/NotoSansKR)
- [ ] pipeline/text_overlay.py: render_ad_text(image, copy, template, size) -> bytes
      - 템플릿별 zone(_TEXT_LAYOUT 비율 재활용)에 헤드라인/본문/CTA 그림
      - shrink-to-fit + 줄바꿈 + 가장자리 안전여백 → 잘림 물리적 불가
      - 패널 배경(반투명 다크/브랜드컬러) + CTA 버튼 모양
- [ ] 이미지 모델 프롬프트 "텍스트 없이"로 전환 (generate + compose 양쪽)
- [ ] candidate_gen: 이미지 생성 후 render_ad_text → composite_logo 순서
- [ ] 단위 테스트: zone 안에 텍스트가 들어가고 경계 안 넘는지

## ③ 제공 텍스트 우선 / 그림 텍스트 보존 (대부분 ②로 해결)

- [ ] 인페인팅 프롬프트: "상품 기존 글자/브랜딩 보존, 새 텍스트는 안 그림" 명시
- [ ] 카피가 제공 텍스트(product_name·description) 기준인지 확인 (product_analyzer 텍스트-only 확인됨)

## 챗봇 — 이미지생성 우선 연결 + 좋은광고 RAG (오늘)

- [ ] ⚠️ 윤섭과 RAG 조율 먼저: 코퍼스 문서 분담 + documents/embeddings 스키마 한 번에 합의 (DB 단독 PR + Alembic)
- [ ] "좋은 광고" 지식 코퍼스 정리 (강조 포인트·느낌 등)
- [ ] 이미지 생성 맥락에 챗봇 연결 (범위: 전체 아님, 이미지 생성 우선)

## 공통

- [ ] 백엔드 .py 수정 → 커밋 전 Ruff
- [ ] 기능별 세만틱 커밋 분리 (①/②/③/챗봇 따로)
