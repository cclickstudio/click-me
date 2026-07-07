# Generator 통합 — UI 일원화 + 렌더링을 yunseop 방식으로 교체

> ✅ **완료된 계획 (2026-06-15, 역사 문서)** — 통합은 이 계획대로 완료됐고, 이후 다음이
> 추가로 달라졌다(2026-07 기준).
> - **개선 모드 전면 재설계**(`2c8b7eb`) — 이 문서의 "개선도 후보 3종 동일 흐름"은 폐기.
>   현재는 **단일 시안 1장**, 기존광고 이미지 미사용(텍스트 힌트만), 상품 누끼 인페인팅,
>   template=None 자유 레이아웃, 항상 OpenAI 경로. improve-mode-image.* 참고
> - 생성 모드 2원화 — `GENERATOR_GEN_MODE=openai|gemini` (openai-gemini-mode.* 참고)
> - 카드뉴스(carousel) 포맷, 플랫폼별 리레이아웃 렌더(`/candidates/{id}/render?platform=`),
>   브랜드 키트 CRUD, ZIP 다운로드, QA 품질점수 기반 후보 순위(G7) 추가
> - 채팅 연동 — gen_form/gen_progress/gen_result 위젯, 자동 개선 루프(generation_loop)
>
> 이하 본문은 통합 당시 계획 원문.

## Context

`feat/generator-yohan` + `feat/generator-yunseop` 머지로 두 광고 제너레이터가 한 코드베이스에 공존 중이다.
- **graph (yohan)**: LangGraph + SSE + DB + 후보선택 + 인스타게시 + Meta 광고집행. 렌더링은 `render/text_overlay.py` — 헤드라인 뒤에 **반투명 검정 plate(배경색 박스)** 를 깖.
- **pipeline (yunseop)**: 동기 generate/improve. 렌더링은 `pipeline/*` — **AI 인페인팅 + 그라디언트** 로 배경색 박스 없이 자연스럽게 합성. 로고 미지원.

목표: **단일 "전체 생성" 제너레이터**로 일원화한다. UI는 yunseop 레이아웃(좌측 폼 + 우측 세로 후보 + 클릭 시 모달)을 베이스로, graph의 기능(SSE·DB·선택·게시·광고집행·로고·팔레트·캐시)을 모두 살리고, **렌더링은 yunseop 방식(배경색 없음)** 으로 교체한다.

## 확정된 결정 (사용자 Q&A)

1. **graph(LangGraph) 기반 + yunseop 렌더링** — `domain/generator/graph/`의 LangGraph `StateGraph` 오케스트레이션(비동기 + SSE + DB + 선택/게시/광고집행)을 그대로 유지하고, candidate 노드의 *렌더링 내용물* 만 yunseop 방식으로 교체. yunseop의 동기 `generate_ad`/`improve_ad` + `/generate`·`/improve` 엔드포인트는 폐기.
2. **이미지 생성은 지금 gpt-image-1 구현 그대로 사용.** 별도 추상화 계층은 만들지 않는다(나중에 모델 교체 시 그때 처리). 현재 `AsyncOpenAI` 기반 `images.generate`/`images.edit` 코드를 유지.
3. **사이즈: 1080²(기본) / 1920×1080 / 1080×1920** 로 고정(UI + 최종 출력 치수). gpt-image-1은 1024/1536만 생성하므로, 생성 후 목표 치수로 center-crop→resize.
4. **인페인팅 항상 켜기** — 현재 gpt-image-1 `images.edit(mask=...)` 그대로 사용 (변종당 이미지 API 2회 = 비용·지연 인지함). 실패 시 원본 폴백(기존 동작).
5. **개선 모드도 생성 모드와 동일 흐름** (SSE + 후보 3종 + 모달 + DB) + 기존 입력(기존광고 S3키·시뮬요약·수정요청) 유지.

---

## 백엔드 변경

### 1. graph candidate 노드를 yunseop 렌더링 체인으로 재구성 — 핵심

`domain/generator/graph/nodes/candidate_gen.py`의 변종 생성 로직을 yunseop 파이프라인 모듈 체인으로 교체. 이미 `generator_service._build_variant`가 이 체인을 그대로 구현하고 있으므로 그 로직을 graph 노드로 이식한다.

변종당 단계 (모두 `pipeline/*` 기존 모듈 재사용, 이미지 생성은 현행 gpt-image-1 그대로):
1. `pipeline/image_generator.generate_image()` — 배경(텍스트 없음, safe-zone 프롬프트). gpt-image-1로 생성 후 목표 치수(1080²/1920×1080/1080×1920)로 보정(아래 4번)
2. `pipeline/image_analyzer.analyze_image()` — 밝기/무드 분석
3. `pipeline/copy_generator.generate_copy()` — 이미지에 맞는 카피(headline/body/cta)
4. `pipeline/text_inpainter.inpaint_text_zone()` — **항상 실행** (텍스트존 자연화, gpt-image-1 `images.edit`). 실패 시 원본 폴백
5. `pipeline/quality_checker.check_quality()` — 품질검증 (inpaint와 병렬)
6. `pipeline/text_compositor.composite_text()` — PIL 한글 합성 (배경색 박스 없음)
7. **로고 합성 추가** (아래 3번)
8. `tools/storage/s3.upload_bytes()` + `candidate_key()` 로 S3 저장 (graph 기존 방식 유지 — `_upload_to_s3`의 aioboto3 직접호출 대신 graph의 S3 헬퍼 사용)
9. `emit_progress()` 로 변종별 진행률 emit (SSE 유지)

→ yohan의 `render/text_overlay.py`(plate), `contracts/templates.py`(영역박스), `candidate_gen.py`의 `compose_ad_image`/`build_image_prompt`/내부 `generate_image`는 **사용 중단**.

### 2. 전략·템플릿 enum 정합

- graph strategy 노드(`graph/nodes/strategy.py`)가 출력하는 `strategy_type`을 `contracts/enums.AdStrategy` 값(`benefit`/`problem_solving`/`social_proof`/`fomo`/`emotional`)에 맞춘다. (yohan은 `problem_solution`을 썼음 → `problem_solving`으로 통일)
- 템플릿 매핑은 `pipeline/template_selector.select_template()` 재사용. graph template 노드는 이 매핑 결과(`TemplateType` A/B/C)를 쓰도록 정리. 글자 A/B/C는 양쪽 동일하므로 호환.

### 3. 로고 합성을 yunseop 렌더링에 추가

yunseop `composite_text`는 로고 미지원. yohan `text_overlay._paste_logo` 로직을 참고해 `pipeline/text_compositor.py`에 로고 paste 단계 추가(또는 합성 후 wrapper에서 paste). 배치: 템플릿별 안전 영역(상단 코너 기준) — 기존 safe-zone과 겹치지 않게. 로고 bytes는 `req["brand_logo_s3_key"]` 다운로드(graph 기존 로직 재사용).

### 4. 사이즈 1080 처리

- 목표 치수: 정사각 `1080x1080`(기본) / 가로 `1920x1080` / 세로 `1080x1920`.
- gpt-image-1 생성 사이즈 매핑: 1:1→`1024x1024`, 가로→`1536x1024`, 세로→`1024x1536`.
- 생성 후 PIL로 **목표 종횡비로 center-crop → 목표 치수로 resize** (가로 16:9 vs 생성 3:2 종횡비 차이 보정). 정사각은 1:1→1:1이라 단순 resize.
- `composite_text`는 목표 치수 캔버스 기준으로 동작하도록 리사이즈 후 텍스트 합성 순서 확인 (텍스트가 또렷하도록 합성은 최종 치수에서).

### 5. 개선(improve) 모드를 graph에 통합

- `contracts/schemas.GenerationCreateRequest`에 `mode: GenerationMode`(기본 create) + 개선용 필드(`existing_ad_s3_key`, `simulation_summary`, `fix_requests`) 추가.
- `graph/nodes/product_analysis.py`를 mode 분기: create=상품 분석, improve=시뮬요약·수정요청 기반 분석 컨텍스트 구성 (기존 `generator_service.improve_ad`의 `improvement_context` 로직 이식).
- strategy 노드는 improve일 때 `plan_strategies(..., improvement_context=...)` 경로 사용 (pipeline 모듈에 이미 있음).
- 나머지(SSE·후보3종·QA·explain·DB·선택·게시·광고집행)는 create와 동일 흐름 공유.

### 6. 카피 스키마 일원화

- `contracts/schemas.AdCopy`를 yunseop 구조(`headline`/`body`/`cta`)로 통일 (렌더링이 yunseop이므로). graph copy 노드 시스템 프롬프트도 3필드 기준으로 수정. QA는 `pipeline/quality_checker` 기준 사용.
- DB `copy` 컬럼은 JSONB라 구조 변경 자유. `get_detail` 반환·프론트 타입을 headline/body/cta로 맞춤.

### 7. 제거 (폐기)

- `domain/generator/service/generator_service.py`: `generate_ad`/`_generate_ad_inner`/`improve_ad`/`_improve_ad_inner`/`_build_variant`/`_to_strategy_plans`/`_upload_to_s3` (로직은 graph 노드로 이식되므로).
- `api/routers/generator.py`: `POST /generate`, `POST /improve` 엔드포인트.
- `contracts/pipeline_schemas.py`: 더 이상 안 쓰는 타입(`GenerateRequest`/`GenerateResult`/`ImproveRequest`/`GeneratedAdVariant`) 정리. 내부 파이프라인 타입(`ProductAnalysis`/`StrategyOutput`/`StrategyPlan`/`ImageAnalysis`/`AdCopy`/`QualityReport` 등)은 graph 노드가 계속 쓰므로 유지.
- `render/text_overlay.py`, `contracts/templates.py`: graph가 더 이상 호출 안 하면 삭제(또는 보류). 다른 참조 없는지 확인 후 제거.

---

## 프론트엔드 변경 — `frontend/src/app/generator/page.tsx`

단일 통합 페이지로 재작성. `PageMode = "graph" | "pipeline"` 토글 제거.

### 레이아웃 (yunseop 베이스)
- `grid grid-cols-5`: **좌측 폼(col-span-2)** + **우측 후보 세로 정렬(col-span-3)**.
- 상단에 **생성 모드 / 개선 모드 탭** (yunseop create/improve 스타일).

### 좌측 폼 — graph 기능 전부 유지
- 생성 모드: 제품명·설명·타겟·광고목적 (필수) + 선택(접기): **브랜드 컬러(팔레트 `<input type=color>` + hex 입력 둘 다)**, **브랜드 로고(파일 업로드, ≤2MB, 1024px 제한 — graph `handleLogoChange` 재사용)**, **톤앤매너(텍스트)**, **사이즈(1080 정사각 기본 + 가로/세로)**.
- 개선 모드: 제품명(선택) + 기존광고 S3키·시뮬요약(필수) + 수정요청 + 톤앤매너 + 사이즈.
- **브랜드 캐시**: `localStorage` clientId + `api.generator.brandProfile.get/save` 유지.

### 우측 — 진행 + 후보
- 생성 시작 → **SSE 진행률**(graph STAGES 체크리스트)을 우측 패널에 표시 (화면 전환 없이).
- 완료 → 우측에 **후보 3종 카드 세로 정렬** (yunseop `AdVariantCard` 스타일).
- 후보 카드 클릭 → **모달**(yunseop `AdDetailModal` 스타일, 화면 전환 X).

### 모달 — IG 게시 + Meta 광고집행 둘 다
- yunseop 모달 베이스에 graph의 **Meta 광고집행 패널**을 이식(현재 graph는 selected 화면에만 있음).
- 모달 열릴 때(또는 게시/집행 직전) `api.generator.select(generationId, candidateId)` 호출 → graph `publish_candidate`/`advertise_candidate`가 `selected_candidate_id` 검증을 통과하도록.
- 인스타 게시: `api.generator.publish` (DB 기반, graph). yunseop의 image_url 직접 publish는 폐기.
- Meta 광고집행: `api.generator.advertise` (예산·목적·타겟팅·기간, PAUSED 안내 문구 유지).

### API 클라이언트 — `frontend/src/lib/api.ts`
- `generator.start`에 mode + 개선 필드 전달 가능하도록 확장 (또는 `startImprove` 추가).
- `generate`/`improve` 직접 fetch 제거. 모든 호출을 graph 엔드포인트로.
- 타입(`frontend/src/lib/types.ts`): `GeneratorCandidate.copy`를 headline/body/cta로, SSE/Detail 타입 정리.

---

## 수정/생성/삭제 파일 요약

**수정**
- `backend/domain/generator/graph/nodes/candidate_gen.py` (yunseop 체인으로 재구성 — 핵심)
- `backend/domain/generator/graph/nodes/product_analysis.py`, `strategy.py`, `template_select.py` (mode 분기 + enum 정합)
- `backend/domain/generator/contracts/schemas.py` (GenerationCreateRequest에 mode/개선 필드, AdCopy 3필드)
- `backend/domain/generator/pipeline/text_compositor.py` (로고 합성 + 1080 리사이즈)
- `backend/domain/generator/service/generator_service.py` (sync 함수 제거)
- `backend/api/routers/generator.py` (/generate·/improve 제거)
- `frontend/src/app/generator/page.tsx` (단일 통합 재작성)
- `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`

**삭제(참조 확인 후)**
- `backend/domain/generator/render/text_overlay.py`
- `backend/domain/generator/contracts/templates.py`
- `backend/domain/generator/contracts/pipeline_schemas.py`의 미사용 요청/응답 타입

---

## 검증

1. **백엔드 기동**: `cd backend && uv run uvicorn api.main:app --reload --port 8000` — import 에러 없이 startup complete.
2. **Ruff**: `cd backend && uv run ruff format . && uv run ruff check . --fix` (CI 통과 선제).
3. **생성 모드 E2E**: 프론트 `/generator`에서 제품 입력 → SSE 진행률 표시 → 후보 3종 세로 표시 → 카드 클릭 모달 → 이미지에 **배경색 박스 없이** 텍스트가 그라디언트/인페인팅 위에 렌더된 것 확인 → 로고 합성 확인 → 사이즈 1080 확인.
4. **선택→게시→집행**: 모달에서 select 후 IG 게시(Mock 모드 정상), Meta 광고집행(PAUSED) 정상 동작 + DB 로그(`AdPublishLog`/`AdCampaignLog`) 적재.
5. **개선 모드 E2E**: 기존 S3키+시뮬요약 입력 → 동일 SSE/후보/모달 흐름 동작.
6. **회귀**: 폐기된 `/generate`·`/improve` 호출 잔존 없음(프론트/문서 grep), graph 엔드포인트만 사용.
7. **비용 주의**: 인페인팅 항상 켜짐 → 변종당 이미지 2회. OpenAI quota 충전 상태 선확인(이전 429 이력).

## 미해결/주의

- gpt-image-1 가로(3:2) vs 목표 1920×1080(16:9) 종횡비 차이 → center-crop 보정 필요(제품이 잘릴 수 있음, safe-zone 프롬프트로 완화).
- 인페인팅 항상 켜짐의 비용/지연 — 데모 전 quota 확인 필수.
- `render/text_overlay.py`·`templates.py` 삭제 전 타 모듈 참조 grep으로 재확인.
