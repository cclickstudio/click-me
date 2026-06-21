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

- [x] 한글 TTF 폰트 — Pretendard 이미 번들됨(assets/fonts/)
- [x] pipeline/text_overlay.py: render_ad_text — 템플릿별 zone, shrink-to-fit+줄바꿈, 패널+CTA버튼
- [x] has_text=False로 전환 — 생성/컴포즈/개선 全경로 텍스트 없는 프롬프트
- [x] multimodal_generator: 이미지에 텍스트 미생성(카피 JSON만), 텍스트존 비움
- [x] candidate_gen: 두 경로 모두 render_ad_text → composite_logo
- [x] 단위 테스트: 렌더·전템플릿·긴텍스트 shrink (test_text_overlay.py)
- [ ] 검증(런타임): 실제 생성으로 상하 잘림 없는지 (사용자 확인)

## ③ 제공 텍스트 우선 / 그림 텍스트 보존 (대부분 ②로 해결)

- [x] 인페인팅 프롬프트: "상품 기존 글자/로고/라벨 픽셀 보존, 배경에 새 텍스트 금지" 명시
- [x] 카피는 제공 텍스트 기준 확인 — product_analyzer 텍스트-only + ②로 AI 텍스트 미생성

## 챗봇 — 이미지생성 우선 연결 + 좋은광고 RAG (오늘)

- [ ] ⚠️ 윤섭과 RAG 조율 먼저: 코퍼스 문서 분담 + documents/embeddings 스키마 한 번에 합의 (DB 단독 PR + Alembic)
- [ ] "좋은 광고" 지식 코퍼스 정리 (강조 포인트·느낌 등)
- [ ] 이미지 생성 맥락에 챗봇 연결 (범위: 전체 아님, 이미지 생성 우선)

## 공통

- [ ] 백엔드 .py 수정 → 커밋 전 Ruff
- [ ] 기능별 세만틱 커밋 분리 (①/②/③/챗봇 따로)
