# 발표용 측정 스크립트 (generator)

생성 기능 발표 자료의 "개발과정 → 수치 개선" 데이터를 만드는 스크립트 모음.
모두 **backend 디렉터리에서** 실행한다 (`.env` 필요 — OPENAI_API_KEY·DATABASE_URL·AWS·LANGSMITH).

| 스크립트 | 측정 대상 | 발표 스토리 |
|---|---|---|
| `baseline_text_in_image.py` | 구방식(AI가 텍스트까지 그림) 대조군 생성 | 오타율 before |
| `fetch_generation_images.py` | 현행 파이프라인 결과 수집 (최종+base 이미지, 카피, QA) | 오타율 after · 대비비 입력 |
| `measure_text_accuracy.py` | VLM 판정 — 오탈자·깨짐·잘림 비율 | PIL 텍스트 합성 전환 효과 |
| `measure_contrast.py` | 텍스트 오버레이 WCAG 대비비 | 가독성 개선(적응 색상) 효과 |
| `export_langsmith_costs.py` | 파이프라인 1회당 토큰·비용·지연 | 토큰 53% 절감 실측 보강 |
| `export_qa_scores.py` | QA 통과율·품질점수 (모드/템플릿/전략별) | 자동 개선 루프 품질 곡선 |

## 실험 1 — 오타율 (before vs after)

```cmd
cd backend
uv run python scripts\measure\baseline_text_in_image.py --n 5
uv run python scripts\measure\fetch_generation_images.py --latest 10
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\baseline
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\pipeline
```

- before(ai_text)와 after(pipeline)의 "무결점 이미지 비율"을 나란히 비교.
- 공정한 비교를 위해 앱에서 같은 상품(텀블러·이어폰·비타민)으로 생성해두면 좋다.
- gemini 대조군은 `--provider google_genai` 추가.

### 팀원 생성분과 분리 (DB 공유 환경)

`--latest`는 조직 전체 최신순이라 팀원 데이터가 섞일 수 있다. 세 가지 필터로 분리한다.

```cmd
uv run python scripts\measure\fetch_generation_images.py --latest 10 --login-id <내 로그인ID>
uv run python scripts\measure\fetch_generation_images.py --latest 10 --product-contains 텀블러
uv run python scripts\measure\fetch_generation_images.py --latest 10 --project-id <측정용 프로젝트 UUID>
```

- 가장 깔끔한 방법은 **측정 전용 프로젝트를 하나 만들어** 거기서만 생성하고 `--project-id`로 수집.
- `--generation-id <uuid>`로 특정 건만 집는 것도 가능 (생성 상세 URL `/generations/{id}`의 id).
- `export_qa_scores.py`도 동일한 `--login-id`/`--product-contains`/`--project-id` 필터 지원.

## 실험 2 — 텍스트 대비비 (가독성)

```cmd
uv run python scripts\measure\fetch_generation_images.py --latest 10
uv run python scripts\measure\measure_contrast.py --dir scripts\measure\out\pipeline
```

- base(텍스트 없는) 이미지가 함께 저장된 생성물만 측정 가능 (base 저장 이후 생성분).
- 개선 전 수치는 개선 커밋 이전 체크아웃 또는 floating/emotional 전략 외 템플릿과의
  전략별 비교(요약에 전략별 통계 출력)로 대신할 수 있다.

## 실험 3 — 토큰·비용

```cmd
uv run python scripts\measure\export_langsmith_costs.py --days 7
```

- 루트 런 1건 = 파이프라인 1회. 이름별 평균 토큰·비용·지연 출력.
- "토큰 53% 절감"(38dd58be) 옆에 "현재 1회 생성 = 토큰 X · $Y" 실측치로 보강.

## 실험 4 — QA 점수·개선 루프 곡선

```cmd
uv run python scripts\measure\export_qa_scores.py --days 30
```

- CSV를 created_at 순으로 보면 자동 개선 루프(CREATE→IMPROVE→IMPROVE)의
  iteration별 품질점수 상승 곡선을 그릴 수 있다.
- 채팅에서 "알아서 좋은 시안까지 뽑아줘"(improve_ad_iteratively)로 루프를 여러 번
  돌려 데이터를 쌓은 뒤 실행.

## 주의

- 이미지 생성 스크립트는 실비용이 발생한다 (gpt-image-1 medium 기준 장당 약 $0.03~0.07).
- VLM 판정(gpt-4o)도 이미지당 수백 토큰 비용 발생 — `--limit`으로 시범 판정 후 확대.
- 결과물은 `scripts/measure/out/` 아래에 쌓인다 (git 미추적 권장).
