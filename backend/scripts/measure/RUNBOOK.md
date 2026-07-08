# Runbook — 생성 기능 발표자료 측정 (3 스토리)

> 다음 세션이 그대로 실행하는 런북. HANDOFF.md의 후속판 — **4셀 매트릭스 + generate_after.py** 반영.
> 작업용 메모라 커밋 대상 아님. 모든 명령은 `backend/` 디렉터리에서.

## 발표 스토리 → 데이터

| 스토리 | 데이터 | 대표 수치 |
|---|---|---|
| 1. 오타율 (AI가 그림 → PIL 합성) | 4셀 `text_accuracy.csv` | 무결점 이미지 비율(쪼개기 불변) |
| 2. 자동 개선 루프 | 루프 SSE `quality_score` history | 반복별 우상향 곡선 |
| 3. openai vs gemini 종합 비교 | 오타율·대비비·QA·비용 실측 + 코드근거 정성축 | 비교표 (우리 제품 = gemini) |

## 매트릭스 (스토리 1·3 공용)

| | before (AI가 카피까지 그림) | after (현행 PIL 합성) |
|---|---|---|
| gemini | `out/before_gemini` | `out/after_gemini` |
| openai | `out/before_openai` | `out/after_openai` |

상품 3종(텀블러·이어폰·비타민) 고정, 셀당 15장(N=5) 목표. **공정성 — before는 after와 같은 이미지 모델**(gemini↔google_genai / openai↔gpt-image-1).

## 전제조건 체크리스트

- [ ] `.env` — `OPENAI_API_KEY`(생성+VLM 판정) · `GEMINI_API_KEY`(gemini 생성) · `DATABASE_URL` · `AWS_*`/`S3_BUCKET_NAME` · `LANGCHAIN_*`(비용 집계).
- [ ] `USE_MOCK=false` (목업이면 측정 무의미). generate_after가 use_mock=True면 경고 출력.
- [ ] 조직/프로젝트가 DB에 최소 1개 존재(generate_after가 프로젝트 미지정 시 기존 조직 아래 신규 생성).

## 실행 순서

```cmd
cd backend

:: ── 1) after 생성 (in-process, 서버 불필요) ──
:: (a) gemini 모드 — 우리 제품 (현재 .env 기본)
uv run python scripts\measure\generate_after.py --n 2
::   → 출력된 project_id 를 <PROJ_GEMINI> 로 기록
:: (b) openai 모드로 전환 후 재실행 (환경변수 오버라이드 — .env 파일은 안 건드림)
set GENERATOR_GEN_MODE=openai
uv run python scripts\measure\generate_after.py --n 2
::   → 출력된 project_id 를 <PROJ_OPENAI> 로 기록
set GENERATOR_GEN_MODE=gemini

:: ── 2) before 생성 (AI가 카피까지 그림, 두 provider) ──
uv run python scripts\measure\baseline_text_in_image.py --provider google_genai --n 5 --out scripts\measure\out\before_gemini
uv run python scripts\measure\baseline_text_in_image.py --provider openai       --n 5 --out scripts\measure\out\before_openai

:: ── 3) after 수집 (base 이미지 포함 → 대비비용) ──
:: (주의) --project-id는 --latest N 이 있어야 필터로 적용됨. N은 프로젝트 생성건보다 넉넉히.
uv run python scripts\measure\fetch_generation_images.py --latest 20 --project-id <PROJ_GEMINI> --out scripts\measure\out\after_gemini
uv run python scripts\measure\fetch_generation_images.py --latest 20 --project-id <PROJ_OPENAI> --out scripts\measure\out\after_openai

:: ── 4) Story 1: 오타율 (4셀 동일 VLM 판정 gpt-4o) ──
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\before_gemini
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\before_openai
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\after_gemini
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\after_openai
::   필요시 사람 감사 검수 — build_review_sheet.py --dir <각 dir> 로 review.html 생성

:: ── 5) Story 3 보조 지표 ──
uv run python scripts\measure\measure_contrast.py --dir scripts\measure\out\after_gemini
uv run python scripts\measure\measure_contrast.py --dir scripts\measure\out\after_openai
uv run python scripts\measure\export_qa_scores.py --project-id <PROJ_GEMINI>
uv run python scripts\measure\export_qa_scores.py --project-id <PROJ_OPENAI>
uv run python scripts\measure\export_langsmith_costs.py --days 1
::   비용은 모드별 시간대로 분리(각 모드 생성 직후 --days 1). 필요시 --name-contains 로 좁힘.

:: ── 6) Story 2: 자동 개선 루프 곡선 (서버 필요) ──
::   uv run uvicorn api.main:app --reload --port 8000
::   POST /api/generator/generations/loop  body: {product_name, product_description, target_audience, campaign_objective, max_iterations:3~5, project_id}
::   → GET /api/generator/generations/loop/{loop_id}/stream (SSE)
::   SSE "generated" 이벤트의 iteration·quality_score 를 수신 즉시 파일로 저장(인메모리라 서버 재시작 시 소실).
::   상품 3종 각각 1회 → 곡선 3개. A안(현행 QA점수) 그대로 확인.
```

## 주의 / 리스크

- **Story 2 지표 한계** — QA `quality_score`는 카피 규칙 3개(길이·CTA유무·중복)만 실채점, 나머지 4개는 1.0 고정 → 하한 ~0.57, **곡선 변동이 작을 수 있음**. 밋밋하면 B(시뮬 연동 `use_simulation=True`)/C(반복별 카피 변화 정성 병기)로 재논의.
- **비용** — 총 ~60장 생성($3~5) + 4셀 VLM 판정(이미지당 수백 토큰). `--limit`으로 시범 후 확대.
- **모드 전환** — `set GENERATOR_GEN_MODE=...`는 그 셸 세션에만 적용(환경변수 오버라이드). 끝나면 gemini로 원복. 커밋된 `.env`는 건드리지 않는다.
- **gemini 직렬화** — gemini 모드는 전역 세마포어=1이라 순차 생성 → 시간 오래 걸림(정상).
- 결과는 `scripts/measure/out/` 아래. git 미추적 권장.

## generate_after.py 요약

- 현행 파이프라인을 in-process 호출(`generator_service.start_generation`)해 after 표본 생성. 모드 분기는 시작 시 `settings.generator_gen_mode`를 읽음 → `GENERATOR_GEN_MODE` 바꿔 재실행.
- 인자: `--n`(상품당 생성 횟수, 기본 2) · `--project-id`(미지정 시 기존 조직 아래 측정 전용 프로젝트 신규 생성) · `--tag`(프로젝트 이름 태그) · `--product-set {sample,label}`(sample=SAMPLE_ADS 3종, label=라벨 실험용 오메가3·수분크림·프로틴바 3종) · `--product-images DIR`(각 상품 `<slug>.png`를 `store_temp_image`로 업로드해 `product_image_temp_key`에 주입 → 상품이미지 기반 생성).
- 상품 이미지 없이(`--product-images` 생략) 돌리면 0부터 순수 text-to-image(실험1). 지정하면 실험5(상품 이미지 라벨 보존).

---

## 실험 5 — 상품 이미지 업로드 시 라벨 텍스트 보존 (2026-07-08 실측 완료)

### 가설
오타는 "상품 이미지 위 글자를 AI가 다시 그릴 때" 발생. 라벨 텍스트가 또렷한 실물 상품컷 3종(오메가3·수분크림·프로틴바, `product_images/<slug>.png`)을 업로드해 openai·gemini가 라벨을 얼마나 보존하는지 측정.

### 실행 절차 (실제 돌린 명령)
```cmd
cd backend
:: 상품컷 준비 — scripts\measure\product_images\{오메가3,수분크림,프로틴바}.png (라벨 또렷)
:: 1) openai 모드 (누끼+마스크 인페인팅)
set GENERATOR_GEN_MODE=openai
uv run python scripts\measure\generate_after.py --product-set label --product-images scripts\measure\product_images --n 3 --tag withimg_openai
::   → project_id 9e2eb633-… (9/9 완료)
:: 2) gemini 모드 (원본 멀티모달 참조)
set GENERATOR_GEN_MODE=gemini
uv run python scripts\measure\generate_after.py --product-set label --product-images scripts\measure\product_images --n 3 --tag withimg_gemini
::   → project_id 578c9731-… (5/9 완료, 멀티모달 ~50% 실패)
:: 3) 수집 (--latest N 필수)
uv run python scripts\measure\fetch_generation_images.py --latest 30 --project-id 9e2eb633-… --out scripts\measure\out\withimg_openai
uv run python scripts\measure\fetch_generation_images.py --latest 30 --project-id 578c9731-… --out scripts\measure\out\withimg_gemini
:: 4) VLM 판정 — 상품 라벨은 element=other. 동시 실행 시 gpt-4o TPM 30k 429 → 단독+--concurrency 2 권장
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\withimg_openai --concurrency 2
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\withimg_gemini --concurrency 2
:: 5) 정성 검수 시트(감사 모드, VLM 프리필) — start …\review.html
uv run python scripts\measure\build_review_sheet.py --dir scripts\measure\out\withimg_openai
uv run python scripts\measure\build_review_sheet.py --dir scripts\measure\out\withimg_gemini
```

### 결과 수치

| 지표 | **gemini** (15장) | **openai** (27장) |
|---|---|---|
| 무결점 이미지 비율 | **93.3%** | 51.9% |
| 라벨(`기타`) exact | **100%** (69/69) | **73%** (105/144) — 오탈자31·깨짐5·잘림3 |
| 전체 결함율 | 1.8% | 18.7% |
| headline / cta (PIL) | 100% / 100% | 100% / 100% |

### 결론 (코드 주석과 정반대 — 실측으로 확인)
- **gemini가 라벨을 압도적으로 잘 보존**. 원본을 멀티모달로 직접 참조하기 때문(라벨 결함 0%).
- **openai는 라벨을 깨뜨림**. 누끼(`remove_background`)가 gpt-image-1로 상품을 재생성하며 라벨을 다시 그림 → base부터 깨진 채 들어감("INTERO Feel Complete" → "THUPNNG MOR. TEEGSLER" 류). 코드 주석의 "마스크로 픽셀 잠금·보존"은 실제로 성립 안 함(누끼 단계에서 이미 깨짐).
- **두 모드 공통**: PIL로 얹는 카피(headline·cta) 100% 무오타 → 실험1(오타율) 결론 그대로.
- **발표 함의**: "우리 제품 = gemini" 포지셔닝이 이 시나리오에서 강하게 뒷받침됨(상품이미지 업로드 시 gemini 라벨 보존 우위).

### 측정 뉘앙스 / 주의
- `기타(other)` exact는 "원본 라벨과 글자 일치"가 아니라 "**깨진/헛것 텍스트가 아닌가(읽히는가)**". 뷰어 체감 품질과 일치하는 지표. gemini는 라벨이 미세히 달라도 읽혀서 exact.
- 표본 비대칭 — gemini 15장(생성 실패↑) vs openai 27장. 라벨 인스턴스 수도 다름(69 vs 144). 비율 비교는 유효.
- 산출물: `scripts/measure/out/withimg_{openai,gemini}/`(git 미추적). 입력 상품컷은 `product_images/`(커밋됨).
