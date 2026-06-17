# ClickMe 광고 매니지먼트 — 합의문서 v2.1(안)

작성: 2026-06-12 · 합의 시한: **2026-06-15 (contracts 머지일)** · 발표일: **2026-07-08**
당사자: 담당자 🅰 / 담당자 🅱 · 입회: 멘토(권장)

> **목적**: 통합문서 v2.0과 v1.3 사이의 버전 충돌을 종결하고, 1일차에 닫아야 할
> 계약(contracts)·역할 배정·절차를 한 문서에서 확정한다.
> 표기 규칙 — `[확정]` = 양측 합의 완료 항목 / `[안]` = 본 문서가 제안하는 초안 / `[빈칸]` = 합의 세션에서 채울 항목.

---

## 0. 정본(Single Source of Truth) 선언 — [빈칸: 양측 서명 필요]

- [ ] **통합문서 v2.0을 정본으로 한다.** v1.3은 폐기하고 레포에서 `docs/archive/`로 이동한다.
- [ ] v2.0의 핵심 결정 7개를 재확인한다:
  ① 승인 플레인 `approval.py` 신설(🅰 소유) ② executor에서 승인 로직 분리(🅱는 강제만)
  ③ 계약 3종(`ApprovedAction` 추가) ④ `meta/client.py`·core 테이블 공동
  ⑤ `ActionProposal` 생산자 = 🅱 단독 ⑥ 오케스트레이터 = A/B 밖 별도 담당 ⑦ 새 폴더 0개
- [ ] 이후 v2.0 결정을 되돌리는 변경은 **별도 브랜치 + 양측 리뷰 + 사유 명기** 없이는 무효.

**근거(기록용)**: 승인/실행 분리는 executor 단일 장애점을 축소하고(defense in depth),
A/B 리스크를 중간×2로 균등화한다. 되돌리면 executor가 승인 포함 7단계로 비대해져
데모 정지 리스크가 한 사람에게 집중된다.

---

## 1. 역할 배정 — [빈칸: 6/13까지 확정]

🅰/🅱는 **슬롯**이며 사람이 아니다. 슬롯 정의(소유 파일·계약·게이트)는 v2.0 §3을 그대로 따른다.

| 슬롯 | 담당자 | 확정일 |
|---|---|---|
| 🅰 감지·진단 + 승인 플레인(HITL 설계) | ____________ | 6/13 |
| 🅱 실행·재생성 + 재생성 평가(HITL 강제) | ____________ | 6/13 |

**배정 기준(우선순위 순) — [안]**
1. **일정 리스크 최소화**: ★5 컴포넌트(executor)와 최난도 모델링(기대 노출 모델)을
   각각 가장 빨리 완성할 수 있는 사람에게 배정한다. 기존 실무·프로젝트 경험과의
   중복도를 1차 근거로 한다.
2. **학습 목표**: 1로 결정이 안 날 때만 적용한다.
3. 6/13까지 합의 실패 시 **멘토가 1의 기준으로 배정**하고 양측은 따른다.

**배정과 무관하게 보장되는 것(v2.0 §3 균형표)**: 양측 모두 agent 1개 + eval 1개 +
HITL 한 축 + tool-use를 소유한다. 배정 결과로 이 균형이 깨지는 수정 제안은 받지 않는다.

---

## 2. 계약(Contracts) — 데이터 스키마

> 위치: `backend/domain/management/contracts/schemas.py` · 모든 모델 Pydantic v2, `frozen=True`
> 공통 규칙 — [확정 제안]: 타임스탬프는 **UTC aware datetime**(naive 금지) ·
> 통화는 **KRW 정수**(float 금지) · 모든 계약에 `schema_version: str` 포함 ·
> 골든 샘플 JSON을 `evals/fixtures/contracts/`에 계약당 최소 2개(정상/경계) 커밋.

### 2.1 `DiagnosisResult` (🅰 → 🅱) — 스튜어드: 🅰

v1.3의 `AnomalyEvent` + `DeliveryDiagnostics`를 단일 계약으로 통합한다.

| 필드 — [안] | 타입 | 비고 |
|---|---|---|
| `diagnosis_id` | str (uuid) | |
| `tenant_id` | str | `organization_id` 정렬 |
| `campaign_id` | str | |
| `anomaly_type` | AnomalyType | 고장 5종과 1:1 |
| `source` | Literal["deterministic","agent"] | 결정론/agent 경로 구분 |
| `hypothesis` | str | 원인 가설 (agent 산출 시) |
| `confidence` | float (0~1) | 결정론 경로는 1.0 |
| `evidence_metrics` | dict | 근거 지표 스냅샷 — **이 밖의 정보로 추론 금지(정보 방화벽)** |
| `metrics_as_of` | datetime (UTC) | |
| `status` | Literal["CONFIRMED","INCONCLUSIVE"] | INCONCLUSIVE만 agent로 라우팅됨 |
| `schema_version` | str | "1.0" |

- [ ] 필드 확정 (1일차)

### 2.2 `ActionProposal` (🅱 단독 생산 → 승인 플레인) — 스튜어드: 🅱

**필드 18종 — [확정: v1.3/v2.0 동일, 변경 없음]**

`proposal_id, tenant_id, ad_account_id, target_object_ids, action_type, action_tier,
evidence_metrics, metrics_as_of, hypothesis, confidence, expected_state_version,
budget_before, budget_after, max_total_spend, expires_at, proposal_hash,
approval_policy_version, status`

- 🅰는 지출성 제안을 생산하지 않는다(산출 계약은 `DiagnosisResult`·`ApprovedAction` 2종만).
- [ ] `payload` 전용 모델화 여부 — v1은 dict 허용, 개정 시한: ______ (§5)

### 2.3 `ApprovedAction` (승인 플레인 🅰 → executor 🅱) — 스튜어드: 경계측 = 공동 ★1일차 필수

**미합의 시 🅰 전체가 블로킹되는 최우선 안건.**

| 필드 — [안] | 타입 | 비고 |
|---|---|---|
| `approved_action_id` | str (uuid) | |
| `proposal_id` | str | 원 제안 참조 |
| `proposal_hash` | str | executor 재검증용 (제안 변조 감지) |
| `tenant_id` | str | |
| `approver_id` | str \| Literal["AUTO"] | Tier 0~1 자율 통과 시 "AUTO" |
| `action_tier` | ActionTier | |
| `approved_at` | datetime (UTC) | |
| `expires_at` | datetime (UTC) | 승인 자체의 만료 (제안 만료와 별개) |
| `approval_policy_version` | str | 승인~실행 갭 사이 정책 변경 감지 |
| `expected_state_version` | str | 제안에서 승계 — executor 5)단계 비교용 |
| `execution_mode` | ExecutionMode | DRY_RUN / MOCK / LIVE 격리 |
| `schema_version` | str | "1.0" |

- [ ] 필드 확정 (1일차) · [ ] 중복 승인 멱등 키 = `proposal_id + approval_policy_version` 합의

### 2.4 `ActionResult` (🅱 → 감사·표시) — 스튜어드: 🅱

- [ ] v1 필드 초안 합의: `result_id, approved_action_id, status, platform_response_snapshot,`
  `failure_reason(FailureReason enum — 기계 채점용), executed_at, idempotency_key, schema_version`

### 2.5 `FaultConfig` (고장 주입 — 🅱가 contracts 경유로 Mock 고장을 켠다)

```python
class FaultConfig(BaseModel):
    mode: FaultMode
    probability: float = 1.0
```
- [ ] 🅱 시나리오 반영 확정 — §3.2의 FaultMode 빈칸과 함께 1일차에 닫는다.

### 2.6 기타 — [확정]

`CampaignConfig`, `MetricsSnapshot`, `DeliveryEstimate`는 v1 초안으로 시작하되:
- [ ] **`MetricsSnapshot` 시간 단위 = 시간별(hourly)** — 🅰 기대 노출 모델(일중 곡선)의 성립 조건. 1일차 확정.

---

## 3. 계약(Contracts) — Enum / Port

### 3.1 `enums.py`

| Enum | 값 — [확정] | 비고 |
|---|---|---|
| `ActionTier` | 0~3 | 0~1 자율 통과 / 2 비활성(7/8 스코프 제외) / 3 사용자 라우팅 |
| `AnomalyType` | 고장 5종 | 심사거절·심사지연·입찰패배·타겟협소·품질저하 — Mock 정답 라벨과 1:1 |
| `ExecutionMode` | DRY_RUN / MOCK / LIVE | 값은 `core/config.py`, 강제는 executor 분기 |
| `ProposalStatus` | — [빈칸] | DRAFT/PENDING/APPROVED/REJECTED/EXPIRED/EXECUTED/STALE [안] |
| `CampaignState` | — [빈칸] | `WorkflowStatus` + 플랫폼 스냅샷 분리 여부 1일차 결정 |
| `FaultMode` | WRITE_TIMEOUT, REVIEW_STUCK, RATE_LIMITED, **+ 🅱 추가분: ______** | 🅰 단독으로 채우지 않는다 — 🅱 테스트 시나리오 기준으로 🅱가 직접 추가 |

### 3.2 `platform.py` — [확정]

`AdPlatformReader` / `AdPlatformWriter` Protocol (벤더 중립 Port). 모든 Writer 메서드는
`idem_key` 필수 인자. 구현체는 `adapters/<vendor>/`에 드롭인 — contracts 무변경 원칙.

---

## 4. 불변 규칙 (Invariants) — [확정: 위반 = CI 차단 대상]

1. **모든 지출은 `executor.py` 단일 경로.** agent·서비스의 Writer 직접 호출 금지.
2. **무승인 액션은 어떤 경로로도 Writer에 도달 불가.** 승인의 뇌 = `approval.py`(🅰),
   강제 = executor(🅱), 입 = 오케스트레이터(별도 담당).
3. **A/B 내부 패키지 상호 import 금지.** 유일한 접점 = `contracts`. import-linter가 CI에서 물리 차단.
4. 승인 전 3단계(`approval.py`) / 승인 후 4단계(executor) 검증은 **의도적 중복**(defense in depth)
   — 어느 쪽도 "저쪽이 하니까"로 생략하지 않는다.
5. contracts 변경은 별도 브랜치 + 양측 리뷰 + 골든 샘플 갱신을 동반해야 머지된다.

---

## 5. v1 잠금 + 개정 시한 — [빈칸: 날짜를 반드시 채운다]

> "나중에"에 날짜가 없으면 그게 발표 전날이 된다.

| 항목 | v1 상태 | 개정 시한 |
|---|---|---|
| `DiagnosisResult.evidence_metrics` 세부 구조 | dict 초안 | ______ |
| `ActionProposal.payload` 전용 모델화 | dict 허용 | ______ |
| `CampaignConfig` 세부 필드 | 초안 | ______ |
| `ApprovedAction` — | **개정 불가(frozen)** | 1일차 확정 후 잠금 |

---

## 6. 절차 — 브랜치 / CI / 소유권 — [확정 제안]

```
main
 └── feat/management-contracts   ← 1일차(~6/15), A·B 페어 작성, 먼저 머지
      ├── feat/management-detection   (🅰)  ← contracts 머지 후 분기
      └── feat/management-execution   (🅱)  ← contracts 머지 후 분기
```

- contracts 머지 전 슬라이스 작업 시작 금지 · main 직접 푸시 금지(PR만)
- CI 필수 통과 = ruff + pytest + **import-linter**(경계 위반 물리 차단)
- `.github/CODEOWNERS` (담당자 확정 후 ID 기입):

```
/backend/domain/management/contracts/                @🅰 @🅱
/backend/domain/management/detection/                @🅰
/backend/domain/management/approval.py               @🅰
/backend/domain/management/execution/                @🅱
/backend/domain/management/adapters/meta/client.py   @🅰 @🅱
/backend/core/models.py                              @🅰 @🅱
```

- 공동 파일도 **구현 오너 1명 명시**(회색지대 금지): `meta/client.py` 오너 ______ ·
  `core/models.py` 매니지먼트 테이블 오너 ______ · `api/routers/management.py` 오너 ______

---

## 7. 영속성(DB) 합의 — [빈칸: 레포 `core/db.py` 엔진 확인 후 확정]

- [ ] **DB 엔진 명기**: ______ (이하 항목은 PostgreSQL 가정 — 다르면 1일차에 패턴 재합의)
- 테이블 5종은 `core/models.py`에 추가(🤝): `action_proposals`, `approvals`,
  `audit_events`, `execution_runs`, `idempotency_keys` · alembic autogenerate 1회

**핵심 보증의 DB 구현 패턴 — [안]**

| 보증 | 구현 | 연결 |
|---|---|---|
| 멱등키 선점 (executor 6단계) | `idempotency_keys.key` UNIQUE + `INSERT ... ON CONFLICT DO NOTHING` — 삽입 성공한 쪽만 호출 진행 | 게이트 #1 |
| 중복승인 멱등 (`approval.py`) | `approvals (proposal_id, approval_policy_version)` 복합 UNIQUE + ON CONFLICT (조회-후-삽입 금지) | P2 |
| stale 판정 | `UPDATE ... WHERE state_version = :expected` 낙관적 락 — 영향 행 0 = `STALE_PROPOSAL` | 게이트 #2 |
| append-only 감사 로그 | 7/8 스코프: 앱 레벨 insert-only (UPDATE/DELETE 코드 경로 없음) — DB 트리거/권한 강제는 Won't | 게이트 #7 |

**컬럼 타입 규칙 — [확정 제안]**
- 타임스탬프 = `TIMESTAMPTZ` (SQLAlchemy `DateTime(timezone=True)`) — §2 UTC aware 규칙의 물리적 짝
- 금액 = `BIGINT` KRW (float/NUMERIC 금지)
- `evidence_metrics`·`payload`·`platform_response_snapshot` = **JSONB** /
  판정·조인에 쓰는 검증된 신호(`status`, `action_tier`, `expires_at` 등) = **일반 컬럼 + 인덱스**
- enum 컬럼 = `VARCHAR` + 앱 레벨 검증 (PG native ENUM은 alembic 변경 비용 때문에 7/8 스코프에서 회피) — [안]

---

## 8. 완료 게이트 분담 — [확정: v2.0 §11.5 반영]

| # | 테스트 | 소유 |
|---|---|---|
| 1 | 같은 멱등키 10회 → 실행 1건 | 🅱 |
| 2 | 만료·상태버전 변경 제안의 Writer 도달 차단 | 🅱 |
| 3 | 타 tenant/계정 승인자 실행 불가 | 🅰(승인 단계) + 🅱(실행 단계) |
| 4 | Tier 3 무승인 거부 — 모든 경로 | 🅰(뇌) + 🅱(강제) |
| 5 | 정상 fixture 오탐률 ≤ 5% | 🅰 |
| 6 | `delivery_estimate` 실패가 자동 pause로 이어지지 않음 | 🅰 |
| 7 | 부분 실패·재시도 결과의 감사 로그 연결 | 🤝 |
| 8 | 토큰·민감값 로그 미노출 | 🤝 (`client.py` 공동화에 따름) |
| 9 | Meta 연결 없이 데모 전체 사이클 재현 | 🤝 |
| 10 | 발표 환경 동일 시나리오 3회 연속 성공 | 🤝 |

> v1.3의 "B 단독 5개 / A 단독 2개" 분담은 승인 분리(v2.0)에 따라 #3·#4·#8을 재배분했다.

---

## 9. 정책(Policy) 합의 — 스키마가 "형식"이면 정책은 "값"이다

> 원칙 — [확정 제안]: **정책 값과 판정 코드를 분리한다.** 값은 단일 소스
> (`contracts/policy.py` 상수 또는 `core/config.py`)에 두고, 판정은 `approval.py`,
> 집행은 executor가 한다. 같은 정책을 두 곳에 하드코딩하지 않는다.

### P1. Tier 매핑 정책 ★1일차 필수 — 미합의 시 🅱 제안이 전부 튕긴다

`action_type → ActionTier` 표는 **단일 정책표 1개**로만 존재한다.
🅱의 `ActionProposal.action_tier`는 "제안 라벨"이고, `approval.py`의 판정이 정본이다.
- [ ] 매핑표 확정 — [안]: 조회·미리보기=0 / pause·예산 감액=1 / 자동 재배분=2(비활성) /
  예산 증액·시안 교체(재생성)=3
- [ ] 라벨≠판정 불일치 시 처리 확정 — [안]: REJECTED가 아니라 **판정 Tier로 재라벨 후 진행**
  (단, 상향 재라벨은 감사 로그에 기록)

### P2. `approval_policy_version` 운영 정책

- [ ] 버전 보관 위치 확정 — [안]: `core/config.py` 단일 값
- [ ] 버전 상향(bump) 조건 확정 — [안]: P1 매핑표·P4 예산 한도 변경 시에만
- [ ] 구버전 in-flight 제안 처리 — [안]: executor 4)단계에서 `STALE_PROPOSAL` → 새 제안 (자동 승계 금지)

### P3. 만료·Stale 정책 (숫자를 박는다)

- [ ] `ActionProposal.expires_at` TTL — [안]: 일반 24h / 데모 모드 10분
- [ ] `ApprovedAction.expires_at` TTL — [안]: 일반 15분 / 데모 모드 5분
  (승인~실행 갭 방어가 목적이므로 제안 TTL보다 짧아야 한다 — 불변)
- [ ] stale 판정 = `expected_state_version` 불일치, 그 외 사유 추가 여부

### P4. 예산 권한 정책

- [ ] 데모 기본 `remaining_authority` 값 — ______ KRW
- [ ] 소프트캡 동작 확정 — [안]: 90% 도달=경고 로그 / 95%=Tier 자동 상향(자율→사용자 라우팅) /
  100%=차단(REJECTED)
- [ ] `max_total_spend` 산식 — [안]: `budget_after × 집행 예상일수` (계산 주체 = 🅱 제안 시점,
  검증 주체 = executor 6)단계)
- 하드캡 = **내부 권한 한도**이며 플랫폼 지출 절대상한 보장이 아님 — [확정: v1.3 §7 승계]

### P5. 재시도·멱등 정책

- [ ] 멱등키 산식 — [안]: `hash(approved_action_id + action_type + target_object_ids)`
- [ ] Writer 호출 재시도 — [안]: 최대 2회, 지수 백오프, `WRITE_TIMEOUT`은 재시도 /
  `RATE_LIMITED`는 대기 후 1회
- [ ] 부분 실패 처리 — [안]: 상태머신에 스냅샷 기록 후 **정지**(자동 롤백은 7/8 스코프 제외) → 게이트 #7 연결

### P6. Agent 운영 정책

- [ ] 진단 agent tool 호출 상한 — [안]: 1회 진단당 최대 6 호출 (초과 시 INCONCLUSIVE 반환)
- [ ] 재생성 후보 수 상한 — [안]: 3 (PRD ⚠ 항목 종결)
- [ ] 재현성: temperature·모델 버전 고정값 명기 — ______
- [ ] 금지표현 목록 오너 = 🅱 (재생성 가드) / 결정론→agent 핸드오프 임계치 조정권 = 🅰 단독
  (단, 게이트 #5 오탐률 ≤5% 준수 조건) — [빈칸: 양측 확인]

---

## 10. 합의 세션 체크리스트 (6/13~6/15)

**6/13 — 역할 배정 확정**
- [ ] §1 배정 기준으로 🅰/🅱 담당자 확정 (실패 시 멘토 배정)
- [ ] §0 정본 선언 서명

**1일차 contracts 페어 세션 (~6/15)**
- [ ] `ApprovedAction` 필드 확정 (최우선 — 미합의 시 🅰 블로킹)
- [ ] `DiagnosisResult` 필드 확정
- [ ] `FaultMode` 🅱 추가분 기입
- [ ] `MetricsSnapshot` hourly / UTC aware / KRW 정수 확정
- [ ] `ProposalStatus`·`CampaignState` 값 확정
- [ ] **P1 Tier 매핑표 + 라벨 불일치 처리 확정** (스키마와 동급 우선순위)
- [ ] P2~P5 정책 값(버전 운영·TTL·예산 한도·멱등키 산식) 기입
- [ ] P6 agent 운영 정책(호출 상한·후보 상한·재현성 고정값) 확정
- [ ] §7 DB 엔진 명기(`core/db.py` 확인) + 멱등/승인/낙관적 락 구현 패턴 합의
- [ ] §5 개정 시한 날짜 기입
- [ ] §6 공동 파일 구현 오너 기입 · CODEOWNERS ID 기입
- [ ] 골든 샘플 JSON 계약당 2개 커밋
- [ ] `feat/management-contracts` 머지 → 슬라이스 브랜치 분기

---

서명: 🅰 ____________ / 🅱 ____________ / 입회(멘토) ____________ · 일자: 2026-06-__
