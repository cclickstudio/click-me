# 예측↔실측 연결 토대 설계 (C안, 2026-06-22)

> **Goal:** 성과비교 탭의 "집행 전(시뮬 예측)" 슬롯에 진짜 시뮬 결과가 붙도록, 캠페인과 시뮬을 잇는 **연결 키를 영속화**하고 `SimPredictionReader`를 실구현해 `wiring`을 교체한다. 이번 단계는 *토대*만 — 키만 박히면 어디서 박혔든 예측이 자동으로 실측 옆에 붙는다.
> **선행 논의:** 이 대화의 추적 결과 — 슬롯(`creative_ad_id`)과 시뮬 키(`simulations.ad_id`)가 서로 다른 id 공간이고, **둘을 이어주는 쓰기 경로가 없어** 예측이 영원히 "연결 대기"로 남는 구조.
> **연계:** `from-simulation` 핸드오프는 **이미 구현됨**(`tests/management/test_from_simulation.py`). 제안의 `evidence_metrics["simulation_snapshot"]["simulation_id"]`에 시뮬 id를 담지만 `CreatedCampaign`에 영속하지 않는다 — 본 토대의 영속 코드가 그 키도 함께 읽으면 경로 1이 이번 단계에서 살아난다(§7 참고).

---

## 1. 범위

**v1 포함 (1-b — 살아있는 토대)**
- `CreatedCampaign.simulation_id`(UUID, nullable) 신규 컬럼 + Alembic. (🤝 공유 DB — 사전 공지·양측 리뷰 대상)
- `SimPredictionReader` 실구현 — `simulation_id`로 `simulations`+`simulation_aggregates`를 **raw SQL**로 읽어 `PredictionSnapshot(source="sim")` 반환(없으면 `None`).
- `wiring.build_prediction_reader` 를 `MockPredictionReader` → `SimPredictionReader`로 교체.
- 조회 키 전환 — `PredictionReader` 포트와 호출부 2곳을 `creative_ad_id` 기반에서 **`simulation_id` 기반**으로 교체.
- **쓰기 경로 2개** — ① 기존 `POST /campaigns/create-proposal` 요청에 옵셔널 `simulation_id` 추가, ② 이미 구현된 from-simulation의 `simulation_snapshot.simulation_id`. `_record_created_campaign`이 두 키를 모두 읽어 `CreatedCampaign.simulation_id`로 영속. **새 UI 없음.**
- E2E 검증 — `simulation_id`가 들어온 캠페인(수동·from-simulation)은 before-after·assistant tools에서 실제 시뮬 예측이 연결되어 표시된다.

**다음 단계로 이연**
- 경로 2(UI) — 수동 캠페인 폼의 "내 시뮬 이력 선택" 드롭다운 + 시뮬 이력 조회 API.
- `objective_fit_score`·`grade` 실값 채움(시뮬 파생 지표 노출).
- **before-after / assistant 도구 엔드포인트의 org 인증·인가 정비(현재 무인증 — 후속 필수 이슈).** 본 토대의 reader org 대조는 예측 *노출* 방지용일 뿐, 엔드포인트 자체 인증을 대체하지 않는다.

**비범위**
- 시뮬 실행·KPI 산출 로직(시뮬 도메인) 변경.
- `creative_ad_id` 의미·동작 변경(아래 §2 그대로 유지).
- `CampaignConfig`(공유 contracts) 변경.

---

## 2. 핵심 결정

| 항목 | 결정 |
|---|---|
| 연결 키 단위 | **`simulation_id`(특정 시뮬 런)**. 한 광고를 여러 번 시뮬할 수 있어 "어떤 런의 예측인지"가 정확해야 함. from-simulation 핸드오프도 simulation_id 단위. |
| 컬럼 분리 | `creative_ad_id`(Meta 기존 광고 재사용, `String(64)`)는 **그대로 유지**. `simulation_id`(시뮬 결과 연결)는 **별도 신규 컬럼**. 한 컬럼 = 한 의미. |
| 경계 | management는 simulation 도메인 import 금지(import-linter). `SimPredictionReader`는 simulation 테이블을 **raw SQL로만** 읽음(from-simulation 설계와 동일). `core.models`의 `simulation_results`/`ads`는 실 시뮬 데이터 아님 → 사용 금지. |
| contracts 무변경 | `simulation_id`는 `CampaignConfig`(공유 contracts)에 넣지 않고 `ActionProposal.evidence_metrics`(자유 dict)의 **형제 키**로 흘림 → 골든샘플·양측 리뷰 불요. |
| 안전(org) | `get_prediction`에 캠페인의 `tenant_id`를 함께 넘겨 `simulations.organization_id`와 대조. 불일치면 `None`(타 org 예측 노출 차단). |
| 화면 무변경 | `PredictionSnapshot`·`BeforeAfter` DTO·프론트 변경 0. 슬롯 설계 의도대로 wiring 한 줄 + 키 매핑만. |

---

## 3. 아키텍처 & 소유권

```
[쓰기] POST /campaigns/create-proposal { …, simulation_id? }
      │  evidence_metrics["simulation_id"] = simulation_id   (campaign_config 형제 키)
      ▼
   /approve → /execute → _record_created_campaign
      │  CreatedCampaign{ simulation_id = evidence_metrics.get("simulation_id") }   ── 신규 영속
      ▼
[읽기] GET /compare/before-after  ·  assistant tools
      │  meta_campaign_id → CreatedCampaign{ simulation_id, tenant_id }
      ▼
   pred_reader.get_prediction(simulation_id, tenant_id)        ── wiring: Sim 주입
      │  SimPredictionReader: raw SQL (simulations ⋈ simulation_aggregates), org 대조
      ▼
   PredictionSnapshot(source="sim") | None  →  compute_before_after(예측 + 실측) → verdict
```

| 구성요소 | 작업 | 소유/조율 |
|---|---|---|
| `CreatedCampaign.simulation_id` 컬럼 + Alembic | 신규(DB) | 🤝 공유 `core/models.py` — **사전 공지 + Alembic + 양측 리뷰** |
| `SimPredictionReader` 실구현 | 변경 | management(comparison) |
| `PredictionReader` 포트 시그니처 | 변경 | management(comparison) |
| `wiring.build_prediction_reader` Mock→Sim | 변경 | management |
| `CreateCampaignRequest` + `simulation_id` | 변경 | management(라우터, 자기 소유) |
| `create_campaign_proposal` evidence_metrics 키 | 변경 | management |
| `_record_created_campaign` 영속 | 변경 | management |
| before-after 라우터 · assistant tools 매핑 | 변경 | management |

> `comparison/`(예측·before-after)는 분석 슬라이스라 Writer 비호출. 본 변경은 읽기+키 영속만 — 지출 경로 무관.

---

## 4. 데이터 모델

`core/models.py` `CreatedCampaign`(`__tablename__="created_campaigns"`):

```python
# 집행 전 시뮬 예측 연결용 — 이 캠페인이 어떤 시뮬 런(simulations.id)으로 집행됐는지(없으면 미연결).
simulation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
```

- `creative_ad_id`(Meta 재사용)와 **별도 컬럼**. 두 의미 분리.
- nullable·additive → 기존 행 영향 0.
- Alembic(017 스타일) — `ADD COLUMN IF NOT EXISTS created_campaigns.simulation_id UUID` / down은 `DROP COLUMN IF EXISTS`.
- 🤝 공유 DB라 사전 공지 + 양측 리뷰 필수(루트·management CLAUDE.md). FK는 걸지 않음(도메인 경계 — simulation 테이블로의 교차 FK 회피, 느슨 참조).

---

## 5. SimPredictionReader (raw SQL, 경계 준수)

`domain/management/comparison/prediction_adapters.py` 의 stub을 실구현으로 대체.

```python
class SimPredictionReader:
    """실 시뮬 예측 읽기 — simulation_id로 simulation_aggregates를 raw SQL 조회(도메인 경계).
    org 불일치/미완료/미존재는 None(연결 대기)."""

    def __init__(self, session_factory): ...

    async def get_prediction(
        self, simulation_id: str, tenant_id: str
    ) -> PredictionSnapshot | None:
        # UUID 파싱 실패 → None
        # SELECT s.ad_id, s.organization_id, s.completed_at,
        #        a.click_intent_rate, a.purchase_intent_avg, a.trust_avg, a.rejection_rate
        #   FROM simulations s JOIN simulation_aggregates a ON a.simulation_id = s.id
        #  WHERE s.id = :sid
        # 행 없음 → None (미완료/미존재 — aggregate 존재 = 완료로 간주)
        # s.organization_id != tenant_id → None (org 대조)
        # → PredictionSnapshot(ad_id=str(s.ad_id), …4대 KPI…,
        #     objective_fit_score=None, grade=None, as_of=s.completed_at or now, source="sim")
```

**필드 매핑** (`simulation_aggregates` → `PredictionSnapshot`):

| PredictionSnapshot | 출처 | 비고 |
|---|---|---|
| `ad_id` | `simulations.ad_id` | 참조용(키는 simulation_id) |
| `click_intent_rate` | `simulation_aggregates.click_intent_rate` | 0~1 |
| `purchase_intent` | `simulation_aggregates.purchase_intent_avg` | 1~5 (DB 컬럼명 `purchase_intent_avg`) |
| `trust_avg` | `simulation_aggregates.trust_avg` | 1~5 |
| `rejection_rate` | `simulation_aggregates.rejection_rate` | 0~1 |
| `objective_fit_score` | **None** | aggregates에 없는 파생값 — 다음 단계 |
| `grade` | **None** | objective_fit_score 종속 — 다음 단계 |
| `as_of` | `simulations.completed_at` (없으면 now) | UTC-aware |
| `source` | `"sim"` 고정 | 화면 태그 "실 시뮬" |

- `Numeric` → `float` 변환. KRW 아님(스케일 지표라 정수 강제 무관).
- `objective_fit_score=None`이면 화면은 "-" 표시(기존 `compare/page.tsx`가 `?? '-'` 처리).
- **세션** — wiring에서 `core/db` 세션 팩토리 주입. simulation 도메인 ORM 클래스 import 금지(테이블명·컬럼명 문자열 raw SQL).

`MockPredictionReader`는 시그니처만 맞춰 유지(데모/테스트 wiring 폴백). 해시 기반이라 `tenant_id` 무시, `simulation_id` 문자열로 동작.

---

## 6. 포트 · 호출부 전환

**포트** `comparison/ports.py`:
```python
class PredictionReader(Protocol):
    async def get_prediction(
        self, simulation_id: str, tenant_id: str
    ) -> PredictionSnapshot | None: ...
```

**호출부 2곳** — `creative_ad_id` 매핑은 **유지**(실측 `RealOutcome.creative_id` 귀속에 그대로 필요), **`simulation_id` 매핑을 따로 추가**:
- `api/routers/management.py` `compare_before_after` — 같은 `CreatedCampaign` 행 순회에서 `creative_by_meta`(기존, `_real_outcome`의 `creative_id`용)와 `sim_by_meta`(신규, `{meta_id: (simulation_id, tenant_id)}`)를 둘 다 만든다. 예측은 `get_prediction(sim_id, tenant_id)`, `simulation_id` 없는 행은 호출 생략 → prediction `None`.
- `domain/management/assistant/tools.py` `live_before_after` — 동일.

> ⚠ `_real_outcome(m, cid, creative_id)`의 세 번째 인자는 `RealOutcome.creative_id`(크리에이티브 귀속)라 **반드시 `creative_ad_id`를 유지**해야 한다. 예측 키(`simulation_id`)로 바꾸면 실측 귀속이 깨진다.

DTO(`PredictionSnapshot`·`BeforeAfter`) 무변경 → 프론트·assistant 응답 형태 동일.

---

## 7. 쓰기 경로 (최소 1개)

**`CreateCampaignRequest`** (`api/routers/management.py`, 자기 소유 DTO) — 필드 추가:
```python
simulation_id: str | None = None   # 이 캠페인이 연결될 시뮬 런(UUID 문자열). 없으면 예측 미연결.
```
- **UUID 형식 검증** — `Field(pattern=...)` 또는 파싱 가드. 잘못된 형식 422.
- **쓰기 시점 org 검증(방어 심층)** — `simulation_id`가 들어오면 `create_campaign_proposal`이 이미 가진 `org_id`로 raw SQL 대조(`SELECT 1 FROM simulations WHERE id=:sid AND organization_id=:org`). 없거나 타 org면 **422**(잘못된 링크를 영속하지 않음). 미전달이면 검증 생략. → 읽기 시점 org 대조(§5)와 **이중 방어**: 쓰기 때 한 번, 표시 때 한 번.

**`create_campaign_proposal`** — `evidence_metrics`에 형제 키 추가:
```python
evidence_metrics={
    "campaign_config": config.model_dump(mode="json"),
    "name": body.name,
    "simulation_id": body.simulation_id,   # 신규 — CampaignConfig 미변경(contracts 무변경)
}
```

**`_record_created_campaign`** — 영속(두 경로 모두 커버):
```python
em = proposal.evidence_metrics
sim_id = em.get("simulation_id") or (em.get("simulation_snapshot") or {}).get("simulation_id")
CreatedCampaign(
    ...,
    creative_ad_id=cfg.get("creative_ad_id"),
    simulation_id=sim_id,   # 신규 — 수동 create-proposal 키 + from-simulation snapshot 키 둘 다
)
```
- `evidence_metrics`는 `ActionProposal`의 자유 dict 필드(18필드 락 위반 아님 — 값 내부 키 추가).
- **두 경로 커버** — ① 수동 create-proposal의 형제 키 `evidence_metrics["simulation_id"]`, ② 이미 구현된 from-simulation의 `evidence_metrics["simulation_snapshot"]["simulation_id"]`. 우선순위는 ①>②(수동이 명시값).
- 둘 다 없으면 `None` 영속 → 기존 "연결 대기" 동작 유지(회귀 없음).
- from-simulation은 이미 org 소유권·verdict를 검증해 simulation_id를 담으므로(§연계), 추가 검증 불요. 수동 경로만 §7 쓰기 시점 org 검증 적용.

---

## 8. 에러 · 엣지

| 상황 | 처리 |
|---|---|
| `simulation_id` 형식 오류(요청) | 422 |
| `simulation_id` 미존재/타 org (쓰기 시점) | 422 (잘못된 링크 영속 거부) |
| `simulation_id` 미전달 | `None` 영속 → prediction None(연결 대기) |
| simulation_id가 가리키는 시뮬 없음 | reader `None` |
| aggregate 행 없음(미완료) | reader `None` |
| 시뮬 org ≠ 캠페인 tenant | reader `None`(노출 차단) |
| reader DB 조회 실패 | reader `None` + 로그(실측은 계속 표시 — best-effort, 기존 패턴) |

> 규칙 — 예측 부재/불일치/실패는 전부 **`None`(연결 대기)** 로 흡수. 예측이 없다고 실측 표시를 막지 않는다(기존 before-after의 best-effort 정신).

---

## 9. 테스트

**단위 — `SimPredictionReader`**
- aggregate 있는 `simulation_id` + 일치 tenant → 4대 KPI 정확 매핑(스케일·`purchase_intent_avg` 별칭), `source="sim"`, `objective_fit_score=None`.
- 미존재 simulation_id → None. aggregate 없음(미완료) → None.
- 시뮬 org ≠ tenant → None. UUID 형식 오류 → None.

**통합 — before-after**
- `simulation_id` 박힌 캠페인 → prediction(sim) + actual 짝, verdict 산출.
- `simulation_id` 없는 캠페인 → prediction None(연결 대기), 실측은 표시.

**E2E(쓰기 경로)**
- `_record_created_campaign` 단위 — `evidence_metrics["simulation_id"]`(수동) 영속 / `evidence_metrics["simulation_snapshot"]["simulation_id"]`(from-simulation) 영속 / 둘 다 없으면 None / 둘 다 있으면 수동 우선.
- create-proposal에 `simulation_id` 전달 → 제안 `evidence_metrics["simulation_id"]`에 실림(라우터 레벨).
- create-proposal `simulation_id` 미존재/타 org → 422(쓰기 시점 org 검증).

**회귀**
- `MockPredictionReader` 시그니처 변경 후 기존 테스트 그린(데모 wiring).
- `cd backend && uv run pytest tests/ -q` 전구간 그린.

---

## 10. 파일 구조

**변경**
- `backend/core/models.py` — `CreatedCampaign.simulation_id`(🤝 공유 DB·사전 공지).
- `backend/alembic/versions/0XX_created_campaign_simulation_id.py` — 마이그레이션(신규 파일).
- `backend/domain/management/comparison/prediction_adapters.py` — `SimPredictionReader` 실구현 + Mock 시그니처.
- `backend/domain/management/comparison/ports.py` — `PredictionReader.get_prediction` 시그니처.
- `backend/domain/management/wiring.py` — `build_prediction_reader` Mock→Sim(+세션 팩토리 주입).
- `backend/api/routers/management.py` — `CreateCampaignRequest.simulation_id`, `create_campaign_proposal` evidence_metrics, `_record_created_campaign` 영속, `compare_before_after` 매핑.
- `backend/domain/management/assistant/tools.py` — before-after 도구 매핑.

**신규(테스트)**
- `backend/tests/management/test_sim_prediction_reader.py`
- 기존 before-after 테스트에 `simulation_id` 케이스 추가.

---

## 11. 조율 항목 (착수 전)

1. **`core/models.py` `CreatedCampaign.simulation_id` 추가** — 공유 DB 변경. 사전 공지 + Alembic + 양측 리뷰(루트 CLAUDE.md §협업, management CLAUDE.md §Invariants 5). 단독 머지 금지.
2. **`comparison/` 변경 범위 확인** — 예측·before-after 슬라이스 소유 경계를 🅰와 확인(조직-광고 비교는 🅰 영역). 충돌 없도록 사전 합의.
3. **포트 시그니처 변경** — `get_prediction`은 management 내부 포트(contracts/ 아님)라 양측 계약 영향 없음. assistant tools 호출부 동시 수정.

---

## 12. 불변(이번 토대가 보장)

- `simulation_id`만 박히면 **진입 경로 무관**하게 예측이 실측 옆에 자동 연결(키 바인딩 = 자동화 대상).
- 예측 없음은 **정직하게 연결 대기** — 가짜 예측 생성 금지(CLAUDE.md 환산·과장 금지 원칙).
- `creative_ad_id` 의미·동작 무변경. contracts(`CampaignConfig`) 무변경. 프론트 무변경.
