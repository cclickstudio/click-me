# 발표용 측정 스크립트 (generator)

생성 기능 발표 자료의 "개발과정 → 수치 개선" 데이터를 만드는 스크립트 모음.
모두 **backend 디렉터리에서** 실행한다 (`.env` 필요 — OPENAI_API_KEY·DATABASE_URL·AWS·LANGSMITH).

| 스크립트 | 측정 대상 | 발표 스토리 |
|---|---|---|
| `baseline_text_in_image.py` | 구방식(AI가 텍스트까지 그림) 대조군 생성 | 오타율 before |
| `fetch_generation_images.py` | 현행 파이프라인 결과 수집 (최종+base 이미지, 카피, QA) | 오타율 after · 대비비 입력 |
| `measure_text_accuracy.py` | VLM 판정 — 카피 + 이미지 내 모든 텍스트 오탈자·깨짐·잘림 비율 | PIL 텍스트 합성 전환 효과 |
| `build_review_sheet.py` | 사람 직접 정성 검수용 HTML 시트 생성 (VLM과 동일 CSV 스키마) | VLM 판정 사람 교차검증 |
| `measure_contrast.py` | 텍스트 오버레이 WCAG 대비비 | 가독성 개선(적응 색상) 효과 |
| `export_langsmith_costs.py` | 파이프라인 1회당 토큰·비용·지연 | 토큰 53% 절감 실측 보강 |
| `export_qa_scores.py` | QA 통과율·품질점수 (모드/템플릿/전략별) | 자동 개선 루프 품질 곡선 |

## 데이터 출처와 사전 준비 (실행 전 필독)

측정 스크립트는 두 종류다 — **이미지를 직접 만드는 것**과 **이미 만들어진 것을 읽어오는 것**. 이 구분을 놓치면 "왜 after 이미지가 안 잡히지" 하고 헤맨다.

| 구분 | 스크립트 | 이미지 출처 | 사전 준비 |
|---|---|---|---|
| before(구방식) | `baseline_text_in_image.py` | 스크립트가 즉석 생성 | 없음 — 실행하면 바로 생성 |
| after(현행) | `fetch_generation_images.py` | **앱에서 이미 생성한 DB/S3 결과** | **앱에서 미리 생성해둬야 함** |
| 판정 | `measure_*.py` · `build_review_sheet.py` | 위 `out/` 디렉터리 | 위 수집·생성이 선행돼야 함 |

즉 **after(현행 파이프라인) 측정에서 `fetch`는 새로 만드는 게 아니라 DB·S3에서 다운로드만 한다.** 그래서 전체 순서는:

1. **앱에서 광고를 생성한다** — 프론트 `/generator` 화면(또는 채팅의 생성 요청). 생성이 **완료(`completed`)** 돼 `AdGeneration` 테이블·S3에 저장돼야 `fetch`가 집는다(진행 중·실패 건은 안 잡힘).
2. `fetch_generation_images.py`로 그 결과를 `out/pipeline`에 내려받는다(최종본 + 텍스트 없는 base + 카피·QA를 manifest에 동봉).
3. `measure_text_accuracy.py`(VLM) / `build_review_sheet.py`(사람)로 판정한다.

before(`baseline_text_in_image.py`)는 스크립트가 자체 프롬프트로 직접 생성하므로 앱 사전 생성이 필요 없다.

### 측정 전용 프로젝트 권장 (가장 깔끔)

DB가 팀과 공유라 `--latest`는 남의 생성분이 섞인다. **앱에서 측정 전용 프로젝트를 하나 만들어** 같은 상품 3종(텀블러·이어폰·비타민)을 각각 여러 번 생성한 뒤 `--project-id`로만 수집하면 깨끗하다(필터 상세는 아래 "팀원 생성분과 분리").

- before/after 공정 비교를 위해 **같은 상품**으로 맞춘다.
- 파이프라인 모드(openai/gemini)는 백엔드 `GENERATOR_GEN_MODE` 설정값 그대로 측정된다 — before의 `--provider`와 맞추려면 앱이 어떤 모드로 생성했는지 확인.
- 상품 이미지를 올려 생성하면(누끼+인페인팅) 상품 표면 텍스트가 픽셀 보존돼 헛것 텍스트가 줄고, 상품 이미지 없이 0부터 생성하면 상품 표면에 깨진 글자가 생길 수 있다 — 무결점 비율에 영향.

## 실험 1 — 오타율 (before vs after)

> 사전 준비 — after 측정 전에 **앱에서 측정용 광고를 생성**해둔다(위 "데이터 출처와 사전 준비" 참고).

```cmd
cd backend
:: before — 구방식(AI가 카피까지 그림) 대조군을 즉석 생성 → out\baseline
uv run python scripts\measure\baseline_text_in_image.py --n 5
:: after — 앱에서 만든 현행 파이프라인 결과를 다운로드 → out\pipeline
uv run python scripts\measure\fetch_generation_images.py --latest 10
:: 각각 VLM(gpt-4o)으로 오타·깨짐·잘림 판정 → 각 디렉터리에 text_accuracy.csv
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\baseline
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\pipeline
```

- 각 단계 산출물 — `baseline`/`pipeline` 디렉터리에 이미지 + `manifest.json`(기대 카피 동봉), 판정 후 `text_accuracy.csv` + 콘솔 요약(무결점 비율·전체 결함율·요소별 정확율).
- before(ai_text)와 after(pipeline)의 **"무결점 이미지 비율"·"전체 결함율"** 을 나란히 비교 → PIL 텍스트 합성 전환 효과.
- 공정한 비교를 위해 앱에서 같은 상품(텀블러·이어폰·비타민)으로 생성해두면 좋다.
- gemini 대조군은 `baseline_text_in_image.py`에 `--provider google_genai` 추가.
- **오타율 산정 범위** — 카피 3칸(headline/body/cta)뿐 아니라 이미지에 보이는 **모든 텍스트**
  (상품 라벨·로고·배경 문구·헛것 글자 등)를 각각 인스턴스로 판정한다. "전체 결함율"은 그
  모든 텍스트 기준이라, PIL 카피는 완벽해도 상품 표면 헛것 텍스트가 있으면 반영된다.

### 사람 직접 정성 검수 (VLM 교차검증, 감사 모드)

VLM(gpt-4o) 자동 판정 대신·과 함께, 사람이 눈으로 매기려면 검수 시트를 만든다. **VLM 판정을 먼저 돌려두면**, 검수 시트가 그 결과를 프리필해 사람이 **같은 인스턴스 경계 위에서 확인·수정**한다(감사 모드) → 행 단위로 VLM↔사람이 직접 비교된다.

```cmd
:: 앱 생성 → fetch → VLM 판정(text_accuracy.csv 생성) → 검수 시트 순
uv run python scripts\measure\fetch_generation_images.py --latest 10
uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\pipeline
uv run python scripts\measure\build_review_sheet.py --dir scripts\measure\out\pipeline
```

- `<dir>\review.html`이 생성된다 — 이미지를 통째로 인라인한 자체완결 파일이라 **그냥 브라우저로 연다**(서버·인터넷 불필요).
- **감사 모드** — 같은 디렉터리에 `text_accuracy.csv`가 있으면 자동 감지해 VLM의 카피 판정 + **기타 텍스트 분할·판정을 프리필**한다. 사람은 틀린 항목만 고치면 된다(백지로 매기려면 `--no-prefill`, 다른 CSV는 `--vlm-csv <경로>`).
- 이미지마다 카피 요소별(정확/오탈자/깨짐/잘림/누락) + "이미지 내 기타 텍스트"를 기록한다.
- 상단에 무결점 비율·전체 결함율이 실시간 집계되고, **"CSV 저장"** 으로 `review_by_human.csv`를 내려받는다.
- 이 CSV는 `text_accuracy.csv`와 **동일 스키마**라 VLM 판정과 나란히 비교·발표할 수 있다(감사 모드면 인스턴스 경계가 같아 행 단위 일치도 계산까지 가능).
- 검수 기록은 브라우저 localStorage에 자동 저장되어 새로고침·재열람 시 유지된다("전체 초기화"로 지우면 VLM 프리필 상태로 되돌아간다).

**기타 텍스트 셈 규칙(사람·VLM 공통)** — 시각적으로 구분되는 **텍스트 블록 1개 = 1인스턴스**(상품 라벨·배경·헛것 각각). 한 블록 안의 여러 단어·줄은 쪼개지 않고, 정상 렌더된 텍스트도 `exact`로 기록한다. 이 규칙 덕에 분모(전체 텍스트 수)가 사람·VLM 간 일관되어 결함율이 비교 가능하다. 다만 전체 결함율은 이 쪼개기에 민감하니 **발표 대표 수치는 무결점 이미지 비율**(쪼개기에 불변)을 쓴다.

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

> 사전 준비 — 실험 1과 동일하게 **앱에서 생성한 결과**를 `fetch`로 내려받아야 한다.

```cmd
:: 앱 생성분 다운로드(base 포함) → out\pipeline
uv run python scripts\measure\fetch_generation_images.py --latest 10
:: 텍스트 오버레이 영역의 WCAG 대비비 측정
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
