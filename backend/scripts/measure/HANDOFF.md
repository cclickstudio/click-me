# Handoff — 발표용 측정·검수 스크립트 실행

> 다음 세션이 이어받는 작업 인수인계. **before(구방식 AI가 카피까지 그림) vs after(현행 PIL 합성)**
> 오타율을 공정하게 측정하고, 사람 정성 검수(감사 모드)까지 돌리는 게 목표. 발표 자료용.
> 이 파일은 작업용 메모라 커밋 대상 아님(작업 끝나면 지워도 됨).

## 0. 지금 즉시 알아야 할 핵심 (⚠️ 전제조건 이슈)

- **앱은 현재 `GENERATOR_GEN_MODE=gemini`** → after(현행 파이프라인)는 **gemini-2.5-flash-image**로 그림을 그린다.
- **baseline(before) 기본값은 gpt-image-1(openai)** → 그대로 돌리면 "AI텍스트 vs PIL" 차이에
  **모델 차이(gpt-image-1 vs gemini)가 섞여 불공정**하다.
- **해결 — before를 반드시 `--provider google_genai`로 실행**해 gemini로 통일. (근거: `baseline_text_in_image.py`
  L124-128 → provider=openai면 `generator_image_model`, google_genai면 `generator_gemini_image_model`.)

## 1. 코드 현황 (아직 미커밋 — 이번에 만든/고친 것)

| 파일 | 상태 | 내용 |
|---|---|---|
| `scripts/measure/build_review_sheet.py` | 신규 | 사람 정성 검수 HTML 시트 생성기. 이미지 인라인 자체완결 `review.html`, **감사 모드**(VLM `text_accuracy.csv` 자동 감지 → 분할·판정 프리필), `--vlm-csv`/`--no-prefill`, localStorage 저장, 동일 CSV 스키마 내보내기 |
| `scripts/measure/measure_text_accuracy.py` | 수정 | VLM 판정을 카피 3칸 + **이미지 내 모든 텍스트(블록 단위 인스턴스)** 로 확장, `other_texts` 수집, `_summarize`에 "기타" 줄 + **전체 결함율** 추가 |
| `scripts/measure/README.md` | 수정 | 데이터 출처·사전 준비(앱 생성→fetch→측정)·감사 모드·기타 셈 규칙 문서화 |
| `pyproject.toml` | 수정 | `build_review_sheet.py` 임베드 HTML/JS 문자열 E501 per-file-ignore(기존 관행) |

- Ruff·구문·감사 모드 프리필 end-to-end 검증까지 완료(스크린샷으로 확인). **커밋만 남음**(아래 §6).
- 지난 세션의 데모 이미지/시트는 scratchpad(세션별 경로)에 있어 **이번 세션엔 없음**. 데모가 필요하면
  `render_ad_text`(text_overlay.py)로 배경+카피 합성해 재생성하면 됨(필수 아님).

## 2. 지표 정의 (측정 결과 해석 기준)

- **결함** = `exact`(정확) 외 전부 = 오탈자(typo)·깨짐(broken)·잘림(cut)·누락(missing).
- **무결점 이미지 비율** = 텍스트 인스턴스가 하나도 결함이 아닌 이미지 / (사람 시트: 완료 이미지 · VLM: 전체 이미지). **이미지 단위, 쪼개기에 불변 → 발표 대표 수치 권장.**
- **전체 결함율** = 결함 인스턴스 / 판정된 전체 텍스트 인스턴스(카피 3칸 + 기타). **텍스트 단위, 쪼개기에 민감.**
- **기타 텍스트 셈 규칙(A)** — 시각적으로 구분되는 **블록 1개 = 1인스턴스**(라벨·배경·헛것 각각). 한 블록 내
  여러 단어·줄은 안 쪼갬. 정상 렌더도 `exact`로 기록(분모를 사람·VLM 간 일치시켜 비교 가능).

## 3. 변인통제 프로토콜

독립변수 = **텍스트 렌더 방식**(before AI 그림 / after PIL)뿐. 나머지 통제:

1. **이미지 모델** — 앱 gemini(현재) → before `--provider google_genai`. (openai로 볼 거면 앱 `GENERATOR_GEN_MODE=openai`로 바꾸고 before는 기본 gpt-image-1.)
2. **상품 종류** — before 고정 3종(텀블러·이어폰·비타민, `SAMPLE_ADS`) ↔ after 앱에서 같은 3 상품명. 수집은 `--project-id`(측정 전용 프로젝트, 권장) 또는 `--product-contains`.
3. **상품 이미지 유무** — after를 **상품 이미지 없이 0부터 생성**(gemini 멀티모달 참조 배제) → before(순수 text-to-image)와 경로 일치.
4. **카피 텍스트(엄격)** — after 카피를 그대로 `baseline_text_in_image.py --manifest-in copy.json`(형식 `{name,headline,body,cta,scene}`)에 넣어 문구까지 동일화.
5. **사이즈·표본·판정기** — 둘 다 square, before `--n 5`(상품당 5장=15장)에 맞춰 after도 상품당 5장. 판정은 같은 `measure_text_accuracy.py`(VLM gpt-4o). 사람 검수는 감사 모드로 인스턴스 경계 통일.

## 4. 전제조건 체크리스트 (실행 전 확인)

- [ ] `.env` — `OPENAI_API_KEY`(판정 VLM gpt-4o 필수) · `GEMINI_API_KEY`(gemini 생성) · `DATABASE_URL` · `AWS_*`/`S3_BUCKET_NAME`.
- [ ] 앱 기동(`cd backend && uv run uvicorn api.main:app --reload --port 8000` / `cd frontend && pnpm dev`).
- [ ] **측정 전용 프로젝트** 생성 후 거기서 3종을 **상품 이미지 없이** completed로 생성.
- [ ] 현재 모드 = gemini 확인됨 → before는 `--provider google_genai` 확정.

## 5. 실행 순서 (현재 gemini 모드 기준, backend 디렉터리에서)

```cmd
cd backend
:: 0) 앱에서 텀블러·이어폰·비타민을 측정 전용 프로젝트에 상품이미지 없이 생성(사전 준비)
:: 1) before — 같은 gemini 모델로 AI가 카피까지 그리는 구방식
uv run python scripts\measure\baseline_text_in_image.py --provider google_genai --n 5
:: 2) after — 그 프로젝트 생성분만 수집
uv run python scripts\measure\fetch_generation_images.py --project-id <측정프로젝트UUID>
:: 3) 양쪽 동일 VLM 판정
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\baseline
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\pipeline
:: 4) 사람 감사 검수(VLM 판정 프리필 위에서 확인) — review.html을 브라우저로 열어 검수·CSV 저장
uv run python scripts\measure\build_review_sheet.py --dir scripts\measure\out\pipeline
uv run python scripts\measure\build_review_sheet.py --dir scripts\measure\out\baseline
```

- 비용 주의 — 이미지 생성 실비($0.03~0.07/장), VLM 판정도 이미지당 수백 토큰. `--limit`으로 시범 후 확대.
- 결과는 `scripts/measure/out/` 아래. git 미추적 권장.

## 6. 미결 / 다음 결정

- [ ] **커밋** — 아래 명령. (백엔드 .py 변경이므로 커밋 전 Ruff 이미 통과 확인됨. 변경 파일만 대상.)
- [ ] README에 §3 "변인통제" 정식 섹션 추가할지(제안됨, 미반영). 실행 순서 위에 두는 걸 권장.
- [ ] 실제 측정 1회 완주 → before/after 무결점 비율·전체 결함율 수치 확보.

```bash
git add backend/scripts/measure/build_review_sheet.py backend/scripts/measure/measure_text_accuracy.py backend/scripts/measure/README.md backend/pyproject.toml
git commit -m "add: 생성 오타율 사람 정성 검수 시트(감사 모드) + VLM 이미지 내 모든 텍스트 반영

- build_review_sheet.py 신규 — manifest+이미지를 자체완결 review.html로 생성(이미지 인라인, 서버 불필요)
- 감사 모드 — text_accuracy.csv 자동 감지해 VLM 분할·판정 프리필, 사람은 같은 인스턴스 경계서 확인·수정(행 단위 비교)
- 카피 요소별 + 이미지 내 기타 텍스트를 VLM과 동일 CSV 스키마로 내보내 교차검증
- measure_text_accuracy: 카피 외 모든 텍스트를 블록 단위 인스턴스로 판정 + 전체 결함율 집계
- README: 데이터 출처·사전 준비·감사 모드·기타 셈 규칙(블록 1개=1인스턴스) 명시
- pyproject: 검수 시트 임베드 HTML/JS 문자열 E501 per-file-ignore(기존 관행)"
```

## 7. 파일·설정 레퍼런스

- 측정 스크립트 — `backend/scripts/measure/*.py`, 가이드 `backend/scripts/measure/README.md`.
- 생성 설정 — `backend/core/config.py` L159-184(`generator_*`), 현재값은 `backend/.env`의 `GENERATOR_*`
  (gen_mode=gemini, gemini_image_model=gemini-2.5-flash-image, image_model=gpt-image-1, quality=medium).
- before 대조군 — `baseline_text_in_image.py`(SAMPLE_ADS 3종, `--provider`/`--model`/`--n`/`--manifest-in`).
- after 수집 — `fetch_generation_images.py`(`--latest`/`--project-id`/`--login-id`/`--product-contains`).
- VLM 판정 — `measure_text_accuracy.py`(→ `<dir>/text_accuracy.csv`).
- 사람 검수 — `build_review_sheet.py`(→ `<dir>/review.html`, 브라우저에서 `review_by_human.csv` 내보내기).
- 텍스트 합성 로직(참고) — `backend/domain/generator/pipeline/text_overlay.py`(`render_ad_text`).
