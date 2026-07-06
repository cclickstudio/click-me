# 시뮬레이션 결과 조회 API — 시뮬 팀 조율 문서

작성 2026-06-18 · 작성자 🅱(feat/management-boeun) · 대상 시뮬레이션 팀 리뷰
관련 정본 `docs/management/structure-and-roles.md` (§5 import 경계, §7 스코프, §9 contracts 합의)
관련 코드 `domain/simulation/repositories/simulation_repository.py` · `api/routers/simulation/router.py` · `domain/simulation/contracts/schemas.py`

> **목적** 이미 실행·영속화된 시뮬레이션 분석 결과를 **ad_id로 다시 조회**할 수 있는 공개 읽기 엔드포인트를 추가 요청한다.
> 현재 결과는 `simulation_aggregates`·`persona_debates`에 저장되지만 **다시 읽어올 경로가 없다**(write-only). 이 비대칭을 메우는 게 안건이다.
>
> 이 문서는 **(1) 왜 필요한가**, **(2) 제안 계약(엔드포인트·응답 스키마)**, **(3) 시뮬 팀이 정해줄 결정 항목**을 담는다. 매니지먼트는 이 API를 **HTTP로만** 소비한다(generator 연동과 동일 패턴, 타 도메인 내부 import 없음 — §5).

---

## 0. 배경 — 지금 무엇이 막혀 있나

시뮬 런 1회는 분석값을 DB에 저장한다.

- **정량 4-KPI** → `simulation_aggregates` (`click_intent_rate`·`ci_low/high`·`purchase_intent_avg`·`trust_avg`·`rejection_rate`·`effective_n`·`payload`·`engine_version`)
- **정성 토론/분석** → `persona_debates.final` (JudgeFinal: `headline`·`plain_summary`·`ranked_actions`)

그런데 공개 API는 **실행 중심**이고 결과 조회는 **인메모리 저장소**(`InMemorySimulationStore`, `wiring.py:135`)만 본다.

| 엔드포인트 | 한계 |
| --- | --- |
| `POST /api/simulation/run` | 실행해야만 결과를 받음(재실행 비용) |
| `GET /api/simulation/{run_id}/result` | **그 프로세스 메모리의 런만** 반환. 재시작·타 프로세스면 사라짐 |
| (없음) | **ad_id로 저장된 결과를 조회하는 경로가 전혀 없음** |

→ 결과적으로 `simulation_aggregates` 행은 쌓이지만 **읽는 소비자가 없다.** 매니지먼트뿐 아니라 프론트(이력 표시)·generator(개선 근거)도 같은 벽에 막힌다.

---

## 1. 왜 매니지먼트가 필요한가

매니지먼트 재생성 eval(`evals/regeneration_eval.py`)의 승률을 **진짜 시뮬 점수**로 채점하려 한다. 두 가지 길이 있다.

- **(가) 실행 녹화** — 후보를 `POST /run`으로 매번 돌려 점수 획득. 가능하지만 비용·비결정성.
- **(나) 저장값 재조회** — 이미 시뮬된 광고의 결과를 ad_id로 읽어 재사용. **재실행 0, 데이터 진짜.** ← 이 문서가 요청하는 길.

(나)가 제품 완성도 관점에서 옳다 — 저장된 분석값을 살아 있는 데이터로 만든다. 단 **읽기 엔드포인트가 시뮬 팀 영역**이라 합의가 필요하다.

---

## 2. 제안 계약

### 2.1 엔드포인트 (3개, 모두 DB 기반 읽기)

```
GET /api/simulation/ads/{ad_id}/aggregate            # 해당 광고의 최신 집계 1건 (없으면 404)
GET /api/simulation/ads/{ad_id}/aggregates           # 해당 광고의 모든 런 집계 목록 (이력)
GET /api/simulation/simulations/{simulation_id}/aggregate  # 특정 런의 집계 1건
```

선택(정성 분석까지 필요할 때, 후순위):

```
GET /api/simulation/ads/{ad_id}/analysis             # 최신 JudgeFinal (headline·plain_summary·ranked_actions)
```

### 2.2 응답 스키마 — `StoredAggregate` (신규 읽기 계약)

기존 `SimulationAggregate`(`contracts/schemas.py:148`)에 **식별자**만 덧댄 얇은 래퍼. 본문 필드는 그대로 재사용한다(계약 중복 금지).

```python
class StoredAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)  # §9.0 그라운드 룰

    # 식별자
    simulation_id: str
    ad_id: str
    organization_id: str | None = None
    sample_size: int
    created_at: datetime          # UTC-aware (§2 공통규칙)

    # 결과 (= SimulationAggregate 본문)
    click_intent_rate: float
    ci_low: float
    ci_high: float
    purchase_intent: float        # 컬럼 purchase_intent_avg, 계약 필드는 purchase_intent 유지
    trust_avg: float
    rejection_rate: float
    variance_warning: bool
    effective_n: float
    engine_version: str
    # payload(JSONB)는 무거워 기본 제외 — 필요 시 ?include=payload 로 옵트인 제안
```

### 2.3 골든 샘플 (§9.0 — 스키마마다 정상 1 + 경계 1)

`fixtures/contracts/stored_aggregate_normal.json`
```json
{
  "simulation_id": "11111111-1111-1111-1111-111111111111",
  "ad_id": "22222222-2222-2222-2222-222222222222",
  "organization_id": "33333333-3333-3333-3333-333333333333",
  "sample_size": 20,
  "created_at": "2026-06-18T09:00:00Z",
  "click_intent_rate": 0.182, "ci_low": 0.121, "ci_high": 0.244,
  "purchase_intent": 3.40, "trust_avg": 3.10, "rejection_rate": 0.0900,
  "variance_warning": false, "effective_n": 18.4, "engine_version": "agg-0"
}
```

`fixtures/contracts/stored_aggregate_edge_low_sample.json` (저표본 — CI 넓고 variance_warning=true)
```json
{
  "simulation_id": "44444444-4444-4444-4444-444444444444",
  "ad_id": "22222222-2222-2222-2222-222222222222",
  "organization_id": null,
  "sample_size": 3,
  "created_at": "2026-06-18T09:05:00Z",
  "click_intent_rate": 0.333, "ci_low": 0.020, "ci_high": 0.780,
  "purchase_intent": 2.67, "trust_avg": 2.50, "rejection_rate": 0.3333,
  "variance_warning": true, "effective_n": 2.4, "engine_version": "agg-0"
}
```

---

## 3. 시뮬 팀이 정해줄 결정 항목

- [ ] **D1. 다중 런 선택 정책** — 한 광고에 런이 여러 개면 `/aggregate`는 무엇을 최신으로 보나. `created_at` 최신? `engine_version` 필터 허용? (제안: 기본 `created_at` 최신, `?engine_version=` 옵션)
- [ ] **D2. 미존재 의미** — 시뮬된 적 없는 ad_id면 `404`인가 빈 응답인가. (제안: `/aggregate` 404, `/aggregates` 빈 배열)
- [ ] **D3. 정성 분석 노출 범위** — `/analysis`(JudgeFinal)까지 이번에 열까, 집계만 먼저 열까. (제안: 집계 먼저, 분석은 후순위)
- [ ] **D4. 스코프·인증** — `organization_id` 격리가 필요한가(타 조직 결과 차단). 현재 페이즈는 `/api/*` 프리픽스 수준이지만 read도 조직 필터를 받을지.
- [ ] **D5. payload 노출** — JSONB `payload`를 기본 제외 + `?include=payload` 옵트인으로 둘지.
- [ ] **D6. mock 런 포함 여부** — `use_mock=True`로 만든 런도 조회 대상인가(데모 데이터), 실 런만인가.
- [ ] **D7. 응답 계약 버전** — `StoredAggregate`에 `schema_version` 박고 보고 시 병기(§9.0).

---

## 4. 경계·영향 (낮은 리스크)

- **추가형(additive)** — 기존 `POST /run`·`/result` 흐름·쓰기 경로 **무변경**. 신규 읽기 엔드포인트만 추가하므로 깨질 것이 없다.
- **저장소** — `simulation_repository`에 `get_aggregate_by_ad(ad_id)` 류 **읽기 메서드 1~2개** 추가가 본체(`simulations` ↔ `simulation_aggregates` 조인). SQL은 repository에만(§기존 주석 규칙).
- **매니지먼트 측** — 시뮬 내부 import 0. `tools/`나 어댑터에서 HTTP로만 호출(`GET /api/simulation/ads/{ad_id}/aggregate`). 응답을 `StoredAggregate`로 파싱.
- **소유권** — 엔드포인트·repository·읽기 스키마는 **시뮬 팀 소유**. 매니지먼트는 응답 계약(`StoredAggregate`) 모양에만 의존.

---

## 5. 합의되면 매니지먼트가 할 일 (참고)

1. eval scorer를 (가)실행녹화 → (나)`StoredAggregate` 조회로 전환.
2. 승률 보고에 `ci_low/ci_high` 병기(신뢰구간) + engine_version·created_at 표기.
3. 조회 실패·미존재 시 폴백(기존 휴리스틱) 유지 — 외부 의존이 eval을 막지 않게.

> 요청 요약 — **"ad_id로 저장된 `SimulationAggregate`를 돌려주는 DB 기반 GET 엔드포인트"** 하나가 핵심이다. 나머지(목록·정성분석·payload)는 D3~D6에서 범위를 같이 정하면 된다.
