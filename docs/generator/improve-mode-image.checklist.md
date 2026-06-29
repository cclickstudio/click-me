# 작업 체크리스트 — 개선 모드 기존 광고 이미지 연결 (시뮬→개선)

> 목표. 시뮬레이션이 S3에 영속 저장한 기존 광고 이미지를 개선 모드(IMPROVE)가
> `existing_ad_s3_key`로 불러와 **openai=edit / gemini=멀티모달 참조**로 실제 활용한다.
> 배경·결정은 improve-mode-image.context-notes.md 참고.

## 확정 사항 (사용자 합의)

- openai 모드 개선 → 기존 이미지를 `images.edit`로 직접 수정(디자인 유지하며 개선). edit 경로는 이미 구현됨(데드코드 활성화).
- gemini 모드 개선 → 기존 이미지를 멀티모달 입력으로 참조해 재생성.
- 범위 = 백엔드까지. 프론트 "개선 버튼" 연동은 제외(다음 단계).
- 식별자 = `existing_ad_s3_key`에 **s3 key 또는 http(s) URL** 둘 다 허용 → key는 `download_bytes`, http는 `httpx`로 로드.
- 텍스트는 기존대로 PIL 합성 유지(AI 이미지엔 글자 미생성).

## ① 이미지 로드 + state 주입

- [ ] [state.py](backend/domain/generator/graph/state.py) — `existing_ad_bytes: bytes | None` 필드 추가
- [ ] [generator_service.py](backend/domain/generator/service/generator_service.py) `start_generation` — 개선 모드 + `existing_ad_s3_key`면 이미지 로드 → `_tasks[gen_id]["existing_ad_bytes"]`
  - s3 key → `download_bytes`, `http(s)://` → `httpx` 다운로드
  - 실패 시 경고 로그 + None(개선이 0부터 재생성으로 폴백)
- [ ] `_run_pipeline` — store에서 `existing_ad_bytes` pop → `initial_state` 주입(product_image_bytes 패턴과 동일)

## ② candidate_gen 개선 분기

- [ ] `existing_ad_bytes = state.get("existing_ad_bytes")`
- [ ] openai 모드 → `generate_image(original_image_bytes=existing_ad_bytes, ...)` → edit 경로
- [ ] gemini 모드 → `generate_image_and_copy(reference_image_bytes=existing_ad_bytes, ...)` (개선 프롬프트)
- [ ] 캐러셀 개선 모드 처리(공통 배경도 동일 분기 or 범위 명시)
- [ ] 생성 모드 상품 이미지(product_image_bytes) 경로 회귀 없음 확인

## ③ multimodal_generator (gemini 개선 입력)

- [ ] 기존 이미지를 멀티모달 입력으로 받되, `improvement_context` 있으면 "기존 광고 개선" 프롬프트로 분기
- [ ] 상품 이미지(생성) vs 기존 광고(개선) 입력 의미 구분 — 파라미터/프롬프트 정리

## ④ 전달 경로 (백엔드)

- [ ] generator가 `existing_ad_s3_key`를 key/URL 둘 다 로드(①에서 처리) → 프론트가 시뮬 결과의 presigned URL을 그대로 넘겨도 동작
- [ ] (협업) simulation 결과가 개선용 **s3_key**를 노출하도록 — simulation 도메인이라 **별도 조율**(generator 팀이 직접 수정 안 함). 우선 generator robust 로드로 presigned URL 수용.

## ⑤ 테스트

- [ ] `generator_service` 이미지 로드 단위 테스트(s3 key / http URL / 실패 폴백)
- [ ] `candidate_gen` 개선 분기(openai edit / gemini 멀티모달) — mock으로 호출 인자 검증
- [ ] `cd backend && uv run pytest tests/generator -v` 통과

## 공통

- [ ] 백엔드 .py 수정 → 커밋 전 Ruff (generator 범위 한정)
- [ ] 세만틱 커밋 분리 — state/로드 · candidate_gen 분기 · multimodal · 테스트
