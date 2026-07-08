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

- 현행 파이프라인을 in-process 호출(`generator_service.start_generation`)해 after 표본 생성. 상품은 `baseline_text_in_image.SAMPLE_ADS` 재사용(before와 완전 동일). 상품 이미지 없이 0부터 생성.
- 모드 분기는 시작 시 `settings.generator_gen_mode`를 읽음 → `GENERATOR_GEN_MODE` 바꿔 재실행.
- 인자: `--n`(상품당 생성 횟수, 기본 2) · `--project-id`(미지정 시 기존 조직 아래 측정 전용 프로젝트 신규 생성) · `--tag`(프로젝트 이름 태그).
