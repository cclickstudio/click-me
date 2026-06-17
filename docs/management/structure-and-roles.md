# ClickMe 광고 매니지먼트 — 폴더 구조 & 역할 분담 (확정)

문서 v1.3 · 목표 완료일 2026-07-08 · 쌍 문서: `설계문서_v1.1`, `PRD_v1.1`

> 실제 레포 기준 확정 폴더 구조와 A/B 균형 분담. 설계문서/PRD의 §9가 1~8절과 충돌하면 §9를 우선한다.

---

## 0. 현실 점검

- 레포 컨벤션은 **`backend/domain/<도메인>/`** (`simulation/`, `generator/`, `management/`). 설계문서의 `agents/agent-ad-management/` 경로는 무시.
- **영속성은 `core/`가 중앙 관리**: `core/db.py`(엔진·세션·`get_db()`), `core/models.py`(ORM, 멀티테넌트 `Organization→Project→Ad`), alembic. → 매니지먼트는 별도 영속성 레이어 없이 core에 얹는다.
- 발표일은 **7/8**로 통일.

---

## 1. 확정 폴더 구조

```
backend/domain/management/
├── __init__.py
│
├── contracts/                     # 🤝 공동 (변경은 양측 리뷰)
│   ├── schemas.py                 #   CampaignConfig, MetricsSnapshot, DeliveryEstimate,
│   │                              #   AnomalyEvent, DeliveryDiagnostics, ActionProposal(18필드), ActionResult
│   ├── enums.py                   #   ExecutionMode, ActionTier, CampaignState, AnomalyType, ProposalStatus
│   └── platform.py                #   AdPlatformReader / AdPlatformWriter (벤더 중립 Port)
│
├── adapters/                      # 외부 광고 플랫폼 어댑터 (contracts Port 구현체, 벤더별 격리)
│   ├── mock.py                    # 🅰 MockAdPlatform: 일중 곡선 + 노이즈 + 고장모드 + 시계(데모 트리거)
│   └── meta/                      # Meta 구현 (Should, stub로 시작)
│       ├── reader.py              # 🅰 Insights / estimate / 상태 조회
│       ├── writer.py              # 🅱 생성 / pause / 예산 / 미리보기
│       └── client.py              # 🅱 인증·토큰·HTTP 공통층 + 토큰 마스킹
│   # 플랫폼 추가 시 adapters/google/, adapters/tiktok/ 드롭인 — contracts·detection·execution 무변경
│
├── detection/                     # 🅰 감지·진단 슬라이스
│   ├── exposure_model.py          #   기대 노출 곡선 + 기준선 + estimate 캘리브레이션 (BASELINE_UNAVAILABLE)
│   ├── guardrails.py              #   INSUFFICIENT_DATA / DELIVERY_ANOMALY 분리 + grace + 2회 연속 관측
│   ├── deterministic_dx.py        #   결정론 진단 (심사·일정·예산·학습)
│   └── service/
│       └── detection_service.py   #   감지 파이프라인 → 결정론(1~3) → agent(4~6) → AnomalyEvent
│
├── execution/                     # 🅱 실행 슬라이스
│   ├── state_machine.py           #   내부 워크플로 상태 + 플랫폼 객체 스냅샷(부분 실패)
│   ├── executor.py                #   승인 후 7단계 재검증 + 멱등키 (지출 단일 경로)
│   ├── tier.py                    #   Tier 권한 + 예산 권한(remaining_authority, 90/95% 소프트캡)
│   ├── audit_log.py               #   감사 로그 — core.models 위에 append-only
│   └── service/
│       └── execution_service.py   #   ActionProposal 소비 → 승인 → executor 호출
│
├── agents/                        # 🧠 LLM 에이전트 — 각자 1개 (단일 파일)
│   ├── diagnosis.py               # 🅰 진단 agent (LangGraph)
│   └── regeneration.py            # 🅱 재생성 agent (LangGraph, 멀티툴)
│
└── evals/                         # 📏 평가
    ├── fixtures/                  #   🅰 고장모드 정답 / 🅱 광고 케이스
    ├── diagnosis_eval.py          # 🅰 진단 정확도
    ├── regeneration_eval.py       # 🅱 재생성 품질
    └── acceptance.py              # 🤝 PRD §9.5 완료조건 + §9.9 게이트

backend/api/routers/management.py  # 🤝 얇은 엔드포인트 (집행 / 감지실행 / 승인)
backend/core/models.py             # (기존 확장) 매니지먼트 테이블 추가 — §2
backend/core/config.py             # (기존 확장) management_execution_mode setting
```

**확정 결정사항**
- agents 는 `state/nodes/graph` 3분할이 아니라 **단일 파일 2개**. 300줄 초과 시 분할.
- **공용 harness 없음**. LangSmith 트레이싱은 env 설정으로 충족.
- **매니지먼트 내 영속성 레이어 없음**. 테이블은 `core/models.py`, 세션은 `core/db.py`.
- 모드 격리: 값은 `core/config.py` setting, enum 은 `contracts/enums.py`, 강제는 `executor` 분기.
- `adapters/`는 **외부 광고 플랫폼 전용**(DB·S3는 루트 `tools/`). `adapters/meta/*`는 stub로 시작, 데모는 `adapters/mock.py`로 성립. 벤더 교체 = `adapters/<vendor>/` 드롭인.

---

## 2. 영속성 — `core/`에 얹는다

| 무엇 | 어디 |
|---|---|
| DB 엔진·세션 | `core/db.py` (`get_db()`) 재사용 |
| 테이블(모델) | `core/models.py`에 추가 — 기존 `Ad`/`Project` 옆 |
| 마이그레이션 | `alembic/versions/` autogenerate 1회 |
| 저장/조회 호출 | `execution/audit_log.py`·`execution_service.py`에서 `core.models` import |

추가 테이블(안): `action_proposals`, `audit_events`(append-only), `execution_runs`, `idempotency_keys`.
정렬: 멀티테넌트(`Organization`) → `ActionProposal.tenant_id = organization_id`. 재생성 시안은 `Ad` 재사용 가능.

---

## 3. 역할 분담

핵심 원칙: **agent 1개 + eval 1개를 각자 소유**, **contracts 는 공동.**

### 🅰 담당자 A — 감지·진단 + 진단 평가
`adapters/mock.py`, `adapters/meta/reader.py` · `detection/*` · `agents/diagnosis.py` · `evals/diagnosis_eval.py`
→ AI 코어: 추론형 agent + 분류 정확도 eval. 목표 진단 정확도 ≥ 80% (PRD §5.2).

### 🅱 담당자 B — 실행·재생성 + 재생성 평가
`adapters/meta/writer.py`, `client.py` · `execution/*` · `core/models.py` 테이블 · `agents/regeneration.py` · `evals/regeneration_eval.py`
→ AI 코어: 멀티툴 agent + 품질 eval. 목표 재생성 개선율 ≥ 70% (PRD §5.2).

### 🤝 공동 (1일차 ~6/15)
`contracts/*` · `api/routers/management.py` · `evals/acceptance.py`

---

## 4. ActionProposal v1.1 + 실행기 7단계

필드 18종: `proposal_id, tenant_id, ad_account_id, target_object_ids, action_type, action_tier, evidence_metrics, metrics_as_of, hypothesis, confidence, expected_state_version, budget_before, budget_after, max_total_spend, expires_at, proposal_hash, approval_policy_version, status`

**승인 후 `executor.py` 7단계** (실패 시 `STALE_PROPOSAL` → 새 제안):
```
1) 만료·proposal_hash  2) 승인자 tenant·계정 권한  3) 현재 정책의 Tier 허용
4) expected_state_version 비교  5) 지출 후 총액 재계산  6) 멱등키 선점 후 호출
7) 응답·후속조회 감사 로그 기록
```
→ 생산자가 A든 B든, 실행은 반드시 이 단일 경로를 통과(불변).

---

## 5. import 경계 (import-linter CI 강제)

```
detection (A) ─┐                        ┌─ execution (B)
               ├──> contracts <─────────┤   └─ adapters/meta/client (B 소유)
agents/diagnosis (A)                    agents/regeneration (B)
```
- A·B 내부 패키지 상호 import 금지 → 유일 접점 `contracts`.
- 모든 지출은 `execution/executor.py` 단일 경로. agent 는 플랫폼 쓰기 API 직접 호출 금지(제안만).

---

## 6. 완료 게이트 — PRD §9.9 (A/B 분담)

| # | 테스트 | 소유 |
|---|---|---|
| 1 | 같은 멱등키 10회 → 실행 1건 | 🅱 |
| 2 | 만료·상태버전 변경 제안 Writer 도달 차단 | 🅱 |
| 3 | 타 tenant/계정 승인자 실행 불가 | 🅱 |
| 4 | Tier 3 무승인 거부 (모든 경로) | 🅱 |
| 8 | 토큰·민감값 로그 미노출 | 🅱 |
| 5 | 정상 fixture 오탐률 ≤5% | 🅰 |
| 6 | `delivery_estimate` 실패가 자동 pause 안 됨 | 🅰 |
| 7 | 부분 실패·재시도 결과가 감사 로그에 연결 | 🤝 |
| 9 | Meta 연결 없이 데모 전체 사이클 재현 | 🤝 |
| 10 | 발표 환경 동일 시나리오 3회 연속 성공 | 🤝 |

---

## 7. 스코프 (PRD §9)

- **Must(7/8)**: contracts · 실행모드 격리 · Mock 5고장모드 · 기대치·이상감지 · 결정론진단 · 진단 agent · ActionProposal · 승인·실행기 · 예산 가드레일 · 재생성 루프 · 감사 로그 · eval · 통합 데모.
- **Should**: Meta 인증/읽기/`delivery_estimate`/Preview/DRY_RUN 쓰기계약 · 발표 UI.
- **Won't(7/8 제외)**: 실돈 LIVE · 자동 Tier2 재배분 · 프로덕션 OAuth/멀티테넌시 · 통계적 A/B 승자판정 · 시뮬점수 자동교체 · 전환/ROAS · 다중 플랫폼 · 완전 상태 동기화.
- A/B는 `CREATIVE_COMPARISON`, 출력은 `INSUFFICIENT_DATA / DIRECTIONAL`까지. **예산 "하드캡" = 내부 권한 한도**(Meta 지출 절대상한 보장 아님).

---

## 8. 마일스톤 (목표 7/8)

| 기간 | 공동/플랫폼 | 🅰 감지·진단 | 🅱 실행·재생성 |
|---|---|---|---|
| 6/11~6/15 | contracts·실행모드·격리·CI + core 테이블 정의 | fixture·고장 카탈로그 | ActionProposal·감사이벤트 정의 |
| 6/16~6/22 | Mock 정상 게재·error 모델 | 기대모델·가드레일·결정론진단 | 상태머신·Tier·멱등 실행기 |
| 6/23~6/29 | Meta 읽기/estimate 계약검증 | 진단 agent·eval fixture | 재생성 agent·시뮬·미리보기·승인 재검증 |
| 6/30~7/3 | 오케스트레이터·UI 연결 | 오탐·지연 보정 | 실패 재시도·제안 만료·stale |
| 7/4~7/6 | 외부 API 동결 | eval 목표치 측정 | Tier 우회·멱등·예산 테스트 |
| 7/7~7/8 | 버그수정·리허설만 | 동일 | 동일 (데모 3회 연속 성공) |

---

## 9. 미해결 항목 (합의 필요)

- **Tier별 ActionProposal 생산자** 명문화 (안: A=Tier1~2 권고, B=Tier3 재생성).
- **오케스트레이터 소유자** — Tier 3 승인 UI 주인 미지정.
- `enums.py` `CampaignState` → `WorkflowStatus`+객체 스냅샷 분리 여부 (contracts 합의 때).
- PRD ⚠ 항목: 타겟 사용자 · 지원범위 4종 · 기본 테스트구조 · 제품지표 목표치 · 재생성 후보 수 상한(제안 3개).
