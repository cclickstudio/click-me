# ClickMe 광고 매니지먼트 — 통합 문서 (구조 · 역할 · 계약 · 기능)

문서 v2.0 (통합본) · 2026-06-11 · 목표 완료일 **2026-07-08** · 쌍 문서: `설계문서_v1.1`, `PRD_v1.1`

> **이 문서가 단일 정본이다.** 기존 `광고매니지먼트_폴더구조_역할분담.md`, `clickme_management_폴더구조_변경안내.md`, `clickme_management_contracts_합의문서.md`, `AB_역할_세부기능_장단점.md`를 모두 흡수·대체한다.
>
> **v1.4 핵심 결정 요약**: ① 승인 플레인(`approval.py`) 신설 → 🅰 소유 (HITL 설계) ② executor에서 승인 로직 분리 → 🅱는 강제만 ③ `ApprovedAction` 계약 추가 (계약 2개 → 3개) ④ `meta/client.py`·core 테이블 → 공동 ⑤ ActionProposal 생산자 = 🅱 단독 ⑥ 오케스트레이터 = A/B 밖 별도 담당 ⑦ **폴더 구조 유지 — 새 폴더 0개.** 목적: **양쪽 모두 Agentic AI · Tool-use · HITL 경험 + 리스크 중간×2로 균등화.**

---

## 0. 현실 점검

- 레포 컨벤션은 **`backend/domain/<도메인>/`** (`simulation/`, `generator/`, `management/`). 설계문서의 `agents/agent-ad-management/` 경로는 무시.
- **영속성은 `core/`가 중앙 관리**: `core/db.py`(엔진·세션·`get_db()`), `core/models.py`(ORM, 멀티테넌트 `Organization→Project→Ad`), alembic. → 매니지먼트는 별도 영속성 레이어 없이 core에 얹는다.
- 발표일은 **7/8**로 통일.

**왜 contracts가 먼저인가**: import-linter로 A/B는 서로의 내부 패키지를 import하지 못한다 — **두 사람의 유일한 통신선이 `contracts`다.** contracts 변경 비용은 시간이 지날수록 곱으로 커진다(1일차 필드 수정 5분 → 2주차엔 양쪽 파서·픽스처·검증·감사로그 동시 수정). 따라서 **임계 경로 항목은 1일차에 필드까지 닫고**, 나머지는 v1으로 잡되 개정 시한을 박는다.

---

## 1. 확정 폴더 구조

> **폴더 구조 원칙**: v1.3 트리를 **그대로 유지**한다. 새 폴더 0개 — 추가는 루트 단일 파일 `approval.py` 1개뿐(agents 단일 파일 철학과 동일). 고장 주입(FaultMode/FaultConfig)·골든 샘플도 별도 파일/폴더 없이 기존 `enums.py`/`schemas.py`/`evals/fixtures/` 안에서 해결한다.

```
backend/domain/management/
├── __init__.py
│
├── contracts/                     # 🤝 공동 (변경은 양측 리뷰)
│   ├── schemas.py                 #   CampaignConfig, MetricsSnapshot, DeliveryEstimate,
│   │                              #   DiagnosisResult(A→B), ActionProposal(B→승인, 18필드),
│   │                              #   ApprovedAction(승인→실행 ★), ActionResult, FaultConfig(고장주입 ★)
│   ├── enums.py                   #   ExecutionMode, ActionTier(★0~3), CampaignState, AnomalyType(★고장 5종),
│   │                              #   ProposalStatus, FaultMode(★ — 🅱 테스트가 contracts 경유로 고장 주입)
│   └── platform.py                #   AdPlatformReader / AdPlatformWriter (벤더 중립 Port)
│
├── adapters/                      # 외부 광고 플랫폼 어댑터 (contracts Port 구현체, 벤더별 격리)
│   ├── mock.py                    # 🅰 MockAdPlatform: 일중 곡선 + 노이즈 + 고장모드 5종 + 시계(데모 트리거)
│   └── meta/                      # Meta 구현 (Should, stub로 시작)
│       ├── reader.py              # 🅰 Insights / estimate / 상태 조회
│       ├── writer.py              # 🅱 생성 / pause / 예산 / 미리보기
│       └── client.py              # 🤝 ★ 인증·토큰·HTTP 공통층 + 토큰 마스킹 (B단독→공동)
│   # 플랫폼 추가 시 adapters/google/, adapters/tiktok/ 드롭인 — contracts·detection·execution 무변경
│
├── detection/                     # 🅰 감지·진단 슬라이스
│   ├── exposure_model.py          #   기대 노출 곡선 + 기준선 + estimate 캘리브레이션 (BASELINE_UNAVAILABLE)
│   ├── guardrails.py              #   INSUFFICIENT_DATA / DELIVERY_ANOMALY 분리 + grace + 2회 연속 관측
│   ├── deterministic_dx.py        #   결정론 진단 (심사·일정·예산·학습 — LLM 안 부름)
│   └── service/
│       └── detection_service.py   #   감지 파이프라인 → 결정론(명확) → agent(INCONCLUSIVE만) → DiagnosisResult
│
├── approval.py                    # ★ 🅰 승인 플레인 단일 파일 — HITL 설계
│                                  #   Tier 정책 판정(0~1 자율 통과 / 2 비활성 / 3 사용자 라우팅)
│                                  #   승인·거절·만료(expires_at)·stale 판정·중복승인 멱등 → ApprovedAction 발급
│
├── execution/                     # 🅱 실행 슬라이스 (★ 승인 로직 제외 — ApprovedAction만 수신)
│   ├── state_machine.py           #   내부 워크플로 상태 + 플랫폼 객체 스냅샷(부분 실패)
│   ├── executor.py                #   승인 후 4단계 재검증 + 멱등키 (지출 단일 경로) — §4
│   ├── tier.py                    #   예산 권한(remaining_authority, 90/95% 소프트캡) + 사전 비용견적
│   ├── audit_log.py               #   감사 로그 — core.models 위에 append-only
│   └── service/
│       └── execution_service.py   #   ApprovedAction 소비 → executor 호출
│
├── agents/                        # 🧠 LLM 에이전트 — 각자 1개 (단일 파일)
│   ├── diagnosis.py               # 🅰 진단 agent (LangGraph, ★read-tool 4종 ReAct: metrics·상태·estimate·이력)
│   └── regeneration.py            # 🅱 재생성 agent (LangGraph, 멀티툴: 생성·시뮬·미리보기) → 모든 ActionProposal 생산
│
└── evals/                         # 📏 평가
    ├── fixtures/                  #   🅰 고장모드 정답 / 🅱 광고 케이스 (+ ★contracts 골든 샘플 JSON도 여기에)
    ├── diagnosis_eval.py          # 🅰 진단 정확도 (혼동행렬, 확신도 보정, tool 사용 효과)
    ├── regeneration_eval.py       # 🅱 재생성 품질 (시뮬 점수 승률, 가드레일 통과율, 도구실패 복구율)
    └── acceptance.py              # 🤝 PRD §9.5 완료조건 + §9.9 게이트

backend/api/routers/management.py  # 🤝 얇은 엔드포인트 (집행 / 감지실행 / 승인)
backend/core/models.py             # 🤝 ★ (기존 확장) 매니지먼트 테이블 — §2 (B단독→공동 설계)
backend/core/config.py             # (기존 확장) management_execution_mode setting
```

**확정 결정사항**
- agents 는 `state/nodes/graph` 3분할이 아니라 **단일 파일 2개**. 300줄 초과 시 분할.
- **공용 harness 없음**. LangSmith 트레이싱은 env 설정으로 충족.
- **매니지먼트 내 영속성 레이어 없음**. 테이블은 `core/models.py`, 세션은 `core/db.py`.
- 모드 격리: 값은 `core/config.py` setting, enum 은 `contracts/enums.py`, 강제는 `executor` 분기.
- `adapters/`는 **외부 광고 플랫폼 전용**(DB·S3는 루트 `tools/`). `adapters/meta/*`는 stub로 시작, 데모는 `adapters/mock.py`로 성립. 벤더 교체 = `adapters/<vendor>/` 드롭인.
- ★ **승인 플레인 = 루트 단일 파일 `approval.py`, 🅰 소유.** 새 폴더 없음. 승인의 "뇌"(정책·기록·만료)는 A, "입"(카드 표시·클릭 수신)은 오케스트레이터(별도 담당), "강제"(무승인 실행 물리 차단)는 B의 executor.
- ★ **ActionProposal 생산자 = 🅱 단독.** A는 지출성 제안을 만들지 않는다 — A의 산출 계약은 `DiagnosisResult`·`ApprovedAction` 2종.
- ★ **Mock 고장모드 5종**: 심사거절 · 심사지연 · 입찰패배 · 타겟협소 · 품질저하 (`AnomalyType`과 1:1, Mock telemetry에 정답 라벨 포함).
- ★ **고장 주입은 contracts 경유**: `FaultMode`(enums.py)·`FaultConfig`(schemas.py)로 정의 — 별도 파일 없이. 🅱는 이것만 import해 Mock 고장을 켠다(🅰 내부 import 금지 유지).

---

## 2. 영속성 — `core/`에 얹는다

| 무엇 | 어디 |
|---|---|
| DB 엔진·세션 | `core/db.py` (`get_db()`) 재사용 |
| 테이블(모델) | `core/models.py`에 추가 — 기존 `Ad`/`Project` 옆 (🤝 공동 설계) |
| 마이그레이션 | `alembic/versions/` autogenerate 1회 |
| 저장/조회 호출 | `approval.py`·`execution/audit_log.py`·`execution_service.py`에서 `core.models` import |

추가 테이블(안): `action_proposals`, `approvals`(★승인 기록), `audit_events`(append-only), `execution_runs`, `idempotency_keys`.
정렬: 멀티테넌트(`Organization`) → `ActionProposal.tenant_id = organization_id`. 재생성 시안은 `Ad` 재사용 가능.

---

## 3. 역할 분담 (균등 재분배)

핵심 원칙: **agent 1개 + eval 1개 + HITL 한 축씩을 각자 소유**, **contracts·인프라 세금은 공동.**

### 🅰 담당자 A — 감지·진단 + 승인 플레인(HITL 설계)
`adapters/mock.py`, `adapters/meta/reader.py` · `detection/*` · **`approval.py` ★** · `agents/diagnosis.py`(★read-tool) · `evals/diagnosis_eval.py`
→ AI 코어: **추론+tool-use agent** + 분류 정확도 eval + **HITL 설계**(Tier 라우팅·승인·만료). 목표 진단 정확도 ≥ 80% (PRD §5.2).
→ 산출 계약 2종: `DiagnosisResult`, `ApprovedAction`. **지출성 제안 생산 금지 · Writer 호출 금지.**

### 🅱 담당자 B — 실행·재생성 + 재생성 평가(HITL 강제)
`adapters/meta/writer.py` · `execution/*` · `agents/regeneration.py` · `evals/regeneration_eval.py`
→ AI 코어: **멀티툴 agent** + 품질 eval + **HITL 강제**(무승인 액션의 Writer 도달 물리 차단). 목표 재생성 개선율 ≥ 70% (PRD §5.2).
→ 산출 계약 2종: `ActionProposal`(★전량 B 생산), `ActionResult`. **A 내부 import 금지 · Writer 직접 호출 금지(executor 경유만).**

### 🤝 공동 (1일차 ~6/15)
`contracts/*`(스튜어드: 진단측 스키마=🅰 / 액션측 스키마=🅱 / 경계측=공동) · **`adapters/meta/client.py` ★** · **`core/models.py` 테이블 ★** · `api/routers/management.py` · `evals/acceptance.py` · CI 가드(import-linter)
공동 파일도 **구현 오너 1명 명시** — 회색지대 금지.

### 🚫 A/B 밖 — 오케스트레이터 (별도 담당)
사용자와 대화하는 **유일한 입**. 도메인 agent는 채팅에 직접 발화 금지(구조화 데이터만 반환). 경계: 오케스트레이터 = "입"(제안 카드 표시·클릭 수신), `approval.py` = "뇌"(정책 판정·기록·만료), `executor.py` = "강제".

**균형 요약(취업 키워드 기준)** — 두 사람 모두 다음 5종을 1사이클씩 경험:
| 키워드 | 🅰 | 🅱 |
|---|---|---|
| Agentic AI | 진단 ReAct agent | 재생성 멀티툴 agent |
| Tool-use | read-tool 4종(metrics·상태·estimate·이력) | 생성·시뮬·미리보기 툴 |
| **HITL** | 승인 루프 **설계**(라우팅·만료·정책) | 승인 **강제**(우회 차단) |
| Eval | 정확도·혼동행렬·확신도 보정 | 승률·가드레일·도구복구율 |
| 리스크 | 중간(승인 플레인 = 데모 임계 경로) | 중간(실행기 — 승인 분리로 축소) |

---

## 4. 계약 3개 + 승인·실행 파이프라인

```
[🅰 진단]              [🅱 제안]               [🅰 승인 플레인]           [🅱 실행기]
관측→tool→진단   →   복구agent→패키징   →   Tier라우팅→사용자승인   →   재검증→멱등→감사
      │                    │                       │                       │
 DiagnosisResult      ActionProposal          ApprovedAction           ActionResult
```

`ActionProposal` 필드 18종: `proposal_id, tenant_id, ad_account_id, target_object_ids, action_type, action_tier, evidence_metrics, metrics_as_of, hypothesis, confidence, expected_state_version, budget_before, budget_after, max_total_spend, expires_at, proposal_hash, approval_policy_version, status`

**승인 전 — `approval.py`(🅰) 3단계** (실패 시 REJECTED / EXPIRED):
```
1) 만료(expires_at)·proposal_hash 검증   2) 승인자 tenant·계정 권한
3) 현재 정책의 Tier 판정 — Tier 0~1 자율 통과 / Tier 2 비활성 / Tier 3 사용자 라우팅
   → 승인 시 ApprovedAction 발급 (approval_policy_version 포함, 중복승인은 멱등 처리)
```

**승인 후 — `executor.py`(🅱) 4단계** (실패 시 `STALE_PROPOSAL` → 새 제안):
```
4) ApprovedAction 유효성 재확인 (만료·정책버전)   5) expected_state_version 비교
6) 지출 후 총액 재계산 → 멱등키 선점 후 호출      7) 응답·후속조회 감사 로그 기록
```

→ 생산자가 누구든 **승인은 `approval.py`, 실행은 `executor.py` 단일 경로** — 두 관문 모두 우회 불가(불변). 4)의 이중 검증은 의도적 중복(defense in depth): 승인~실행 사이의 시간 갭 동안 상황 변경을 잡는다.

---

## 5. import 경계 (import-linter CI 강제)

```
detection (A) ──┐                        ┌── execution (B)
approval.py (A) ┼──> contracts <─────────┤
agents/diagnosis (A)                     agents/regeneration (B)
                 (adapters/meta/client = 🤝 공동)
```
- A·B 내부 패키지 상호 import 금지 → 유일 접점 `contracts`. (`approval.py`는 루트 단일 모듈이라 import-linter에 모듈 단위로 명시: contracts만 import 허용)
- 데이터 흐름은 전부 contracts 경유: `DiagnosisResult`(A→B) → `ActionProposal`(B→A 승인) → `ApprovedAction`(A→B 실행).
- 모든 지출은 `execution/executor.py` 단일 경로. agent 는 플랫폼 쓰기 API 직접 호출 금지(제안만). **LLM 출력이 직접 Writer를 호출하는 경로는 존재하지 않는다.**
- 도메인 agent는 채팅 직접 발화 금지 — 발화는 오케스트레이터(별도 담당)만.

**분배가 깨끗한지 판별하는 테스트**: *"A와 B가 서로의 코드를 한 줄도 안 읽고, 계약 3개만 mock해서 각자 eval·테스트를 통과시킬 수 있는가?"* — No면 어딘가 레이어로 잘랐다는 뜻, 그 지점을 contracts로 뺀다.

---

## 6. 완료 게이트 — PRD §9.9 (A/B 분담)

| # | 테스트 | 소유 |
|---|---|---|
| 1 | 같은 멱등키 10회 → 실행 1건 | 🅱 |
| 2 | 만료·상태버전 변경 제안 Writer 도달 차단 | 🤝 (만료 차단=🅰 approval, 상태버전=🅱 executor) |
| 3 | 타 tenant/계정 승인자 실행 불가 | 🤝 (판정=🅰 approval, 이중검증=🅱 executor) |
| 4 | Tier 3 무승인 거부 (모든 경로) | 🤝 (라우팅=🅰, 강제=🅱) |
| 5 | 정상 fixture 오탐률 ≤5% | 🅰 |
| 6 | `delivery_estimate` 실패가 자동 pause 안 됨 | 🅰 |
| 7 | 부분 실패·재시도 결과가 감사 로그에 연결 | 🤝 |
| 8 | 토큰·민감값 로그 미노출 | 🤝 (client.py 공동화) |
| 9 | Meta 연결 없이 데모 전체 사이클 재현 | 🤝 |
| 10 | 발표 환경 동일 시나리오 3회 연속 성공 | 🤝 |
| 11 | 승인 중복클릭·승인 후 만료 경합 처리 ★신규 | 🅰 |

---

## 7. 스코프 (PRD §9)

**v1 지원 범위 (좁게 간다, 의도적)**: 광고 형식 **이미지 단일** · 플랫폼 **Meta 단일(데모는 Mock 주력)** · 캠페인 목표 **트래픽(클릭)만** · 예산 **일일 고정 + 기간 지정**.

- **Must(7/8)**: contracts(계약 3종) · 실행모드 격리(`MOCK`/`DRY_RUN`/`SANDBOX_CONTRACT`/`LIVE`비활성) · Mock 고장 5종 · 기대치·이상감지 · 결정론진단 · 진단 agent · ActionProposal · **승인 플레인** · 멱등 실행기 · 예산 가드레일(90% 경고/95% 차단) · 재생성 루프 · 감사 로그 · eval(**일정 밀려도 안 자른다 — 발표 차별점**) · 통합 데모.
- **Should**: Meta 인증/읽기/`delivery_estimate`/Preview/DRY_RUN 쓰기계약("실제 API 계약 검증" 수준까지만) · 발표 UI. 막히면 1일 내 철수.
- **Won't(7/8 제외 — 못 한 게 아니라 안 하기로 결정)**: 실돈 LIVE · 자동 Tier2 재배분 · 통계적 A/B 승자판정 · 시뮬점수 자동교체(상관 미검증 — 발표에서 정직하게 공개) · 전환/ROAS · 다중 플랫폼 · 프로덕션 OAuth/멀티테넌시 · 완전 상태 동기화.
- A/B는 `CREATIVE_COMPARISON`, 출력은 `INSUFFICIENT_DATA / DIRECTIONAL`까지. **예산 "하드캡" = 내부 권한 한도**(Meta 지출 절대상한 보장 아님).

**발표에서 정직하게 말할 한계**: 시뮬 점수 ↔ 실제 성과 상관 미검증(로드맵만 제시) · v1은 Mock 기반 · 소액 예산이라 클릭 지표까지만 신뢰 · 60+ 연령 페르소나 데이터 약점. *"안 한 것"과 "못 한 것"을 구분해서 말하는 게 발표 전략이다.*

---

## 8. 마일스톤 (목표 7/8)

| 기간 | 공동/플랫폼 | 🅰 감지·진단·승인 | 🅱 실행·재생성 |
|---|---|---|---|
| 6/11~6/15 | **contracts 계약 3종**(Diagnosis·Proposal·Approved)·실행모드·격리·CI + core 테이블 정의(공동) | fixture·고장 카탈로그 5종 + 승인 정책 초안 | ActionProposal·감사이벤트 정의 |
| 6/16~6/22 | Mock 정상 게재·error 모델 | 기대모델·가드레일·결정론진단 + **★승인 플레인 스텁(동기 즉시승인)** | 상태머신·Tier·멱등 실행기 |
| 6/23~6/29 | Meta 읽기/estimate 계약검증 | 진단 agent(★tool-use)·eval fixture + **★승인 만료·stale·중복경합 고도화** | 재생성 agent·시뮬·미리보기 |
| 6/30~7/3 | 오케스트레이터·UI 연결 | 오탐·지연 보정 + 승인 경합 테스트 | 실패 재시도·stale 대응 |
| 7/4~7/6 | 외부 API 동결 | eval 목표치 측정 | Tier 우회·멱등·예산 테스트 |
| 7/7~7/8 | 버그수정·리허설만 | 동일 | 동일 (데모 3회 연속 성공) |

> ★**승인 플레인 운영 원칙 — 스텁 우선**: 1주차(6/16~)엔 `approval.py`를 "동기 즉시승인" 스텁으로 박아 전체 루프부터 관통시킨다. 만료·stale·중복승인 경합은 6/23 주에 고도화. (Mock으로 루프 먼저 돌리는 철학과 동일 — 합의 지연이 A를 블로킹하지 않게 `ApprovedAction` 계약만 1일차에 닫는다.)

운영 원칙: **Meta API가 하루 이상 막히면 그 작업은 중단하고 Mock 완성도로 인력 전환.** 외부 승인 기다리느라 Must를 희생하지 않는다.

---

## 9. contracts 합의 — 그라운드 룰 + 결정 항목

### 9.0 그라운드 룰 (먼저 동의)

- [ ] 모든 contracts 스키마는 `ConfigDict(extra="forbid", frozen=True)` — 합의 안 된 필드를 슬쩍 못 끼운다.
- [ ] 클래스 정의만으론 계약이 아니다. **스키마마다 골든 샘플 JSON 2~3개(정상 1 + 경계 1~2)를 `evals/fixtures/`에 같이 커밋** — 이 샘플이 eval 픽스처의 첫 버전.
- [ ] contracts 변경은 **절대 슬라이스 브랜치 안에서 하지 않는다.** 별도 `fix/contracts-vN` 브랜치 → 양측 리뷰 → main 머지 → 각자 리베이스.
- [ ] 픽스처/스키마에 **버전을 박는다(v1, v2)**. 점수 보고 시 항상 버전 병기.

### 9.1 ✅ 닫힌 결정 (재논의 불필요)

| 항목 | 결정 |
|---|---|
| ActionProposal 생산자 | **🅱 단독 생산.** 🅰는 `DiagnosisResult`·`ApprovedAction`만 — 지출성 제안 생산 금지. 근거: 제안 스키마 소유자가 한 명이어야 변경 비용 절반. Tier 1 자동조치는 규칙엔진의 자율 행동, Tier 2는 v1 비활성, Tier 3은 본질적으로 재생성(🅱) 영역 |
| 오케스트레이터 소유자 | **A/B 밖 별도 담당.** 도메인 agent는 채팅 직접 발화 금지 |
| `meta/client.py` 소유 | **🤝 공동** (인프라 세금 분산 + A reader도 사용 + import 경계 깔끔) |
| `core/models.py` 테이블 | **🤝 공동 설계** (DB 스키마 = 사실상 계약) |
| Mock 고장모드 | **5종**: 심사거절·심사지연·입찰패배·타겟협소·품질저하 |
| 승인 플레인 위치 | **루트 단일 파일 `approval.py`, 🅰 소유** — 폴더 구조 유지, 새 폴더 0개 |
| 고장 주입 경로 | `FaultMode`/`FaultConfig`를 **contracts 안에 정의** (별도 파일 없이) — 🅱는 이것만 import |

### 9.2 ⬜ 1일차(~6/15)에 반드시 닫을 결정 — 임계 경로

> 채워지지 않은 항목이 남으면 슬라이스 작업을 시작하지 않는다.

**D1 — `AnomalyType` 카탈로그** (A eval의 정답 라벨 공간 그 자체. Mock 고장모드 = AnomalyType = 진단 출력 = eval 정답, 넷이 같은 enum)

```python
class AnomalyType(StrEnum):
    REVIEW_REJECTED = "review_rejected"          # 심사 거절 (고장 5종)
    REVIEW_DELAY = "review_delay"                # 심사 지연 (고장 5종)
    BID_LOSS = "bid_loss"                        # 입찰 패배 (고장 5종 — 데모 중심축, agent 주 무대)
    AUDIENCE_TOO_NARROW = "audience_too_narrow"  # 타겟 협소 (고장 5종)
    QUALITY_DEGRADED = "quality_degraded"        # 품질 저하 (고장 5종)
    BUDGET_EXHAUSTED = "budget_exhausted"        # 예산 소진 (결정론 진단 영역)
    SCHEDULE_GAP = "schedule_gap"                # 일정 문제 (결정론)
    LEARNING_PHASE = "learning_phase"            # 학습 기간 (결정론)
    INCONCLUSIVE = "inconclusive"                # 규칙엔진 판단 불가 → agent로 (없으면 agent가 빈 껍데기)
```
- [ ] 카탈로그 확정  · 복수 라벨: [ ] 출력은 `list[AnomalyType]` 허용, 채점은 단일부터(권고)  □ 단일 고정

**D2 — `CampaignState`** (B 소유처럼 보이지만 A도 소비자 — "노출 0"이 이상인지는 상태에 달림)

```python
class CampaignState(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    ACTIVE = "active"
    ACTIVE_PENDING_REVIEW = "active_pending_review"  # 게재 중 변경분 비동기 심사
    PAUSED = "paused"
    ENDED = "ended"
```
- [ ] `ACTIVE_PENDING_REVIEW` 포함(권고 — 없으면 B 상태머신과 A 후속 감지 사이 구멍)
- [ ] `WorkflowStatus` + 객체 스냅샷 분리 여부: __________

**D3 — `ActionTier` 4단계 + HITL 게이트** (원칙: "줄이는 건 자율, 늘리는 건 승인")

```python
class ActionTier(IntEnum):
    TIER_0 = 0   # 지표 조회·리포트 (자율)
    TIER_1 = 1   # 악화 광고 끄기 — 지출 ↓ (자율 + 즉시 알림)
    TIER_2 = 2   # 예산 재배분 — 총액 불변 (v1 자동 실행 비활성)
    TIER_3 = 3   # 예산 증액·신규 집행·시안 교체 (항상 건별 사용자 승인)
```
- [ ] TIER_0 추가 확정  · HITL 필수 시작: [ ] Tier 3 무조건(권고)  □ Tier 2부터

**D4 — `ActionProposal` 세부** (필드 18종은 §4 참조)
- 멱등키: [ ] 제안자(agent) 발급, executor가 유일성 강제(권고) · 형식안: `{campaign_id}:{event_id}:{action_type}`
- `payload` 타입: [ ] 액션별 전용 모델(`PausePayload`/`BudgetPayload`) Union(권고 — dict로 열면 `extra="forbid"` 보호가 뚫림)  □ dict로 시작(개정 시한: ______)
- `expires_at` 만료 시간: ______분 (만료 없는 proposal은 시한폭탄)

**D5 — `DiagnosisResult` 구성** (A→B 단일 인터페이스)
`DiagnosisResult` = `AnomalyEvent`(감지) + `DeliveryDiagnostics`(진단)를 묶은 **버전드 래퍼**. 내부 분리는 유지 — 한 덩어리면 eval에서 "감지는 맞고 진단만 틀린" 케이스를 분리 측정 못 한다(`event_id`로 연결해 따로 채점).

```python
class AnomalyEvent(BaseModel):          # 감지의 출력
    event_id: str
    campaign_id: str
    anomaly_type: AnomalyType
    severity: float
    evidence: AnomalyEvidence           # ⚠ 정보 방화벽 — agent가 볼 수 있는 정보의 전부
    detected_at: datetime

class DeliveryDiagnostics(BaseModel):   # 진단(agent)의 출력
    event_id: str
    causes: list[AnomalyType]
    confidence: float                   # eval 확신도 보정의 측정 대상
    reasoning: str
```
- [ ] 래퍼 구성 확정 · `evidence` 포함 지표/기간/플랫폼 응답: __________ (🅱도 이해관계자 — 재생성 agent가 맥락으로 받음)

**D6 — `ApprovedAction`** (승인→실행 계약, ★신규)

```python
class ApprovedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str                 # 승인 자체의 ID (중복승인 멱등 키)
    proposal_id: str                 # 원 ActionProposal 참조
    approved_by: str                 # 승인자 (tenant·계정 검증 완료 상태)
    approval_policy_version: str     # 승인 시점 정책 버전 — executor가 재확인
    approved_at: datetime            # UTC aware
    valid_until: datetime            # 승인의 유효기한 (proposal expires_at과 별도)
```
- 의미론: [ ] 승인 = **실행 자격**(executor 4단계 재검증 통과 필요 — 권고. 안 닫으면 executor 책임 범위 분쟁)  □ 실행 보장
- [ ] 발급자: `approval.py`(🅰)만 발급, executor(🅱)는 검증만
- `valid_until` 기본값: ______분 (proposal `expires_at`보다 짧게 권고)

**D7 — `ActionResult`** (비동기 때문에 보기보다 어렵다)

```python
class ResultStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    SUBMITTED_PENDING_REVIEW = "pending_review"  # 실행은 했으나 결과 보류 — 없으면 Meta 비동기 심사에 일주일 안에 깨짐

class FailureReason(StrEnum):            # 자유 문자열 금지 — eval 기계 채점 위해
    TIMEOUT = "timeout"
    BUDGET_CAP_EXCEEDED = "budget_cap_exceeded"
    PLATFORM_ERROR = "platform_error"
    INVALID_TIER = "invalid_tier"
    # 추가: __________
```
- [ ] `SUBMITTED_PENDING_REVIEW` 포함 · [ ] `FailureReason` 목록 확정 (🅱의 도구 실패 복구율 eval이 이걸 따라간다)

**D8 — `platform.py` 포트 + 고장 주입**

```python
class AdPlatformReader(Protocol):
    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot: ...
    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate: ...
    async def get_state(self, campaign_id: str) -> CampaignState: ...

class AdPlatformWriter(Protocol):
    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult: ...
    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult: ...

class FaultMode(StrEnum):                # enums.py 안에 (별도 파일 없이)
    WRITE_TIMEOUT = "write_timeout"
    REVIEW_STUCK = "review_stuck"
    RATE_LIMITED = "rate_limited"
    # 🅱가 필요로 하는 모드 직접 추가: __________ (🅰가 혼자 정하면 🅱 테스트에 필요한 모드가 빠진다)

class FaultConfig(BaseModel):            # schemas.py 안에
    mode: FaultMode
    probability: float = 1.0
```
- [ ] 포트 확정 · [ ] 🅱 고장 시나리오 반영 확정

**D9 — `MetricsSnapshot` 시간 단위** (v1이지만 시간 단위만 1일차)
- [ ] **시간별(hourly)** 확정 — 🅰의 기대 노출 모델이 "일중 곡선"이라 일별이면 모델 불성립
- [ ] 모든 타임스탬프 UTC aware datetime (naive 금지) · [ ] 통화 KRW 정수 (float 금지)

**D10 — 기타**
- [ ] `approval.py` 300줄 초과 시 `approval/` 폴더 분할 (사전 합의해두면 그때 재논의 불필요)
- [ ] PRD ⚠ 항목: 타겟 사용자 · 지원범위 4종 · 기본 테스트구조 · 제품지표 목표치 · 재생성 후보 수 상한(제안 3개)

### 9.3 v1 잠금 (1주차 개정 허용) — 개정 시한을 적는다

| 항목 | v1 상태 | 개정 시한 |
|---|---|---|
| `AnomalyEvent.evidence` 세부 필드 | 초안 | ______ |
| `ActionProposal.payload` 전용 모델화 | dict 시작 가능 | ______ |
| `CampaignConfig` 세부 필드 | 초안 | ______ |

> "나중에"에 날짜가 없으면 그게 발표 전날이 된다. 반드시 시한을 박는다.

---

## 10. 브랜치 / CI 운영

```
main
 └── feat/management-contracts   ← 1일차, A·B 페어로 작성, 먼저 머지
      ├── feat/management-detection    (🅰)  ← contracts 머지 후 분기
      └── feat/management-execution    (🅱)  ← contracts 머지 후 분기
```

- [ ] **contracts 먼저 머지 → 그 다음 슬라이스 브랜치 분기.** 머지 전 슬라이스 작업 시작 금지.
- [ ] main 직접 푸시 금지, PR만. **CI 필수 통과 = ruff + pytest + import-linter.**
- [ ] import-linter를 `ci.yml`에 추가 — 경계 위반이 머지를 물리적으로 차단. **안 넣으면 경계는 문서일 뿐.**
- [ ] `.github/CODEOWNERS`로 공동 승인 강제:

```
/backend/domain/management/contracts/       @개발자A @팀원B
/backend/domain/management/detection/       @개발자A
/backend/domain/management/approval.py      @개발자A
/backend/domain/management/execution/       @팀원B
/backend/domain/management/adapters/meta/client.py  @개발자A @팀원B
```

- [ ] 짧은 브랜치 + 잦은 머지. 슬라이스 통째로 2주 들고 있지 않기.

---

## 11. A/B 세부 구현 기능 & 기능별 장단점

### 11.0 한눈 비교

| | 🅰 감지·진단·승인 | 🅱 실행·재생성 |
|---|---|---|
| 한 마디 | AI를 **측정하고, 사람 승인 루프를 설계**하는 사람 | AI를 **안전하게 행동시키고, 승인을 강제**하는 사람 |
| AI 색깔 | 추론 + read-tool ReAct + 분류 eval | 멀티툴 오케스트레이션 + 품질 eval |
| 백엔드 색깔 | 데이터·통계(모델·임계치) + 정책(승인) | 트랜잭션·신뢰성(멱등·상태머신) |
| 부담 성격 | 머리 아픈 **애매함** (모델링·정책) | 양 많은 **명확함** (엣지 케이스) |
| 인접 직무 | Applied Scientist, ML Eval, LLM App | Agent/Platform Engineer, Backend+AI |

### 11.1 🅰 기능별 체크리스트 + 장단점

**A-1. MockAdPlatform (`adapters/mock.py`) — ★★★**
- [ ] 일중 노출 곡선 + 노이즈 / [ ] 고장모드 5종 주입(정답 라벨 포함) / [ ] 데모 트리거 시계 / [ ] `FaultConfig` 수신
- **장**: 실계정 없이 전체 루프 검증(데모 성립의 토대). 고장 카탈로그 = eval 정답 라벨 공간.
- **단**: "현실적인" 곡선 설계에 정답 없음. 🅱 테스트도 여기 의존 → 품질 책임이 양쪽에 걸림.

**A-2. 감지·결정론 진단 (`detection/`) — ★★★★**
- [ ] 기대 노출 곡선 + 캘리브레이션 / [ ] INSUFFICIENT_DATA vs DELIVERY_ANOMALY 분리 + grace + 2회 연속 관측 / [ ] 결정론 진단(LLM 안 부름) / [ ] 파이프라인 → `DiagnosisResult` 발행
- **장**: "규칙으로 풀리면 규칙, LLM은 모호한 것만" 하이브리드 설계 — 비용·설명가능성 감각 증명(면접 최고 소재). 오탐 ≤5%는 정량 목표라 성과 증명 깔끔.
- **단**: 기대 노출 모델은 정답이 흐릿한 모델링 — A 최대 난관. 임계치가 Mock 품질에 의존하는 순환 구조.

**A-3. 승인 플레인 (`approval.py`) ★신규 — ★★★★**
- [ ] Tier 정책 판정(0~1 자율/2 비활성/3 라우팅) / [ ] `ApprovedAction` 발급 / [ ] 만료 집행 / [ ] stale 판정 / [ ] 중복승인 멱등 / [ ] **1주차 동기 즉시승인 스텁 → 6/23주 고도화**
- **장**: **HITL 설계 경험** — "어떤 액션이 자율이고 어떤 액션이 사람을 거치는가"를 코드로 박는 2026 채용 최고 키워드의 본체. 돈이 직접 안 움직여 실패해도 재승인으로 복구 가능.
- **단**: 비동기 함정(승인 대기 중 상황 변경, 중복 클릭 경합)이 본질. 데모 임계 경로 진입으로 A 리스크 상승(의도된 트레이드오프). `ApprovedAction` 1일차 미합의 시 블로킹.

**A-4. 진단 에이전트 (`agents/diagnosis.py`) — ★★★☆**
- [ ] LangGraph + read-tool 4종 ReAct(metrics/상태/estimate/이력) / [ ] INCONCLUSIVE 케이스만 수신 / [ ] 원인+확신도+근거 출력 / [ ] 정보 방화벽(evidence 밖 정보 추론 금지)
- **장**: Agentic + Tool-use 충족. "tool을 왜 썼는지 숫자로 설명" 가능(A-5 연계).
- **단**: tool 루프 지연·비용 — 호출 상한 필요. 결정론이 과하게 잡으면 agent가 빈 껍데기(핸드오프 튜닝 필요).

**A-5. 진단 평가 (`evals/diagnosis_eval.py`) — ★★★★**
- [ ] 분류 정확도/F1 + 혼동행렬(≥80%) / [ ] 확신도 보정 / [ ] 오탐률(≤5%) / [ ] tool 효과 측정 / [ ] 픽스처 버전 관리
- **장**: **취업 최강 무기** — "내 AI가 잘 작동함을 숫자로 증명". eval 역량이 시장에서 가장 희소·고평가.
- **단**: 확신도 보정은 측정 설계 자체가 어려움. 정답 라벨이 Mock에서 오므로 Mock 부실 = eval 무의미(자기 의존 사슬).

### 11.2 🅱 기능별 체크리스트 + 장단점

**B-1. 쓰기 어댑터 (`adapters/meta/writer.py`) — ★★☆**
- [ ] 생성/pause/예산/미리보기(stub 시작) / [ ] 모든 쓰기에 멱등키 / [ ] DRY_RUN 대응
- **장**: Port 구현이라 형태 명확. Mock 우선 전략 덕에 일정 리스크 낮음.
- **단**: Meta 실연동은 외부 승인 의존 — 하루 이상 막히면 철수. stub 단계 학습가치 제한적.

**B-2. 실행 슬라이스 (`execution/`) — ★★★★★**
- [ ] 상태머신(비동기 심사 보류 + 부분실패 스냅샷) / [ ] executor 4단계(§4) / [ ] tier.py(90/95% 캡) / [ ] append-only 감사 로그 / [ ] `ApprovedAction` 소비 service / [ ] 게이트 #1 멱등키 10회→1건
- **장**: 멱등성·재시도·비동기 상태관리 = 분산시스템·결제 면접 단골. "무승인 액션은 어떤 경로로도 Writer 도달 불가" = **HITL 강제** 스토리. 통과/실패가 명확해 디버깅 결정론적.
- **단**: 단일 장애점 — executor 버그 = 데모 정지(승인 분리로 범위 축소됐으나 본질 유지). 엣지 케이스 최다. `FaultMode` 1일차에 직접 안 채우면 자기 테스트 불가.

**B-3. 재생성 에이전트 (`agents/regeneration.py`) — ★★★★**
- [ ] LangGraph 멀티툴(생성+시뮬+미리보기) / [ ] `DiagnosisResult` 수신→복구 계획 / [ ] 후보 가드(최대 3·금지표현·점수 미달 제거) / [ ] **모든 `ActionProposal` 패키징** / [ ] tool 실패 재시도/폴백 / [ ] Writer 직접 호출 금지
- **장**: **멀티툴 agent = 가장 트렌디한 스킬.** "tool 실패 시 복구"까지 답하면 차원이 다름. 제안 스키마 단독 소유라 변경 비용 절반.
- **단**: 시뮬레이터(타 팀) 의존 — 인터페이스 변동 리스크. 생성 품질은 LLM 비결정성에 좌우 → eval 없인 개선 주장 불가.

**B-4. 재생성 평가 (`evals/regeneration_eval.py`) — ★★★★**
- [ ] 시뮬 점수 승률(개선율 ≥70%) / [ ] 가드레일 통과율 / [ ] tool-call 성공률 + schema 준수율 / [ ] 도구실패 복구율(`FailureReason` 기계 채점)
- **장**: "생성형 AI 품질 측정" 경험 — 품질 eval은 분류 eval보다 사례가 적어 차별화.
- **단**: 시뮬 점수 ↔ 실성과 상관 미검증(발표 공개 한계) — eval 근거에 단서가 붙음. 채점 기준이 분류보다 모호.

### 11.3 🤝 공동 기능

| 기능 | 체크리스트 | 장 / 단 |
|---|---|---|
| `contracts/*` (계약 3종+enum) | frozen 스키마 / 골든 샘플 / 버전 명기 / 변경은 별도 브랜치+양측 리뷰 | 협업 성패의 90%, "계약 주도 설계" 경험 / 1일차 합의 비용 큼(계약 3개) |
| `meta/client.py` ★ | 인증 토큰 흐름 / 토큰 마스킹 / HTTP 공통층 | 인프라 세금 분산, 양쪽이 인증 이해 / 공동 파일은 구현 오너 1명 명시 필수 |
| `core/models.py` 테이블 ★ | proposals·approvals·audit_events·execution_runs·idempotency_keys | DB 스키마 = 계약, 해석 충돌 예방 / alembic 조율 필요 |
| `api/routers/management.py` | 집행/감지실행/승인 얇은 엔드포인트 | 부담 적음 / 오케스트레이터와 API 경계 합의 필요 |
| `evals/acceptance.py` + CI 가드 | 게이트 11종 / import-linter 강제 | "경계를 빌드타임에 강제" — 시니어가 최고 평가 / 게이트 분담(§6) 숙지 필요 |

### 11.4 데모 1사이클 ↔ 기능 매핑

```
캠페인 집행(Mock·A-1)
 → Mock이 "입찰 패배" 고장 주입 (A-1, FaultConfig는 contracts)
 → DELIVERY_ANOMALY 감지 (A-2 guardrails)
 → 결정론 진단 시도 → INCONCLUSIVE (A-2)
 → 진단 agent: "원인은 입찰 패배, 확신도 N%, 근거는 이 지표" (A-4, read-tool)
 → 복구 agent: 새 시안 3개 + 시뮬 점수 + 미리보기 (B-3)
 → ActionProposal 패키징 (B-3) → 승인 플레인: Tier 3 → 사용자 라우팅 (A-3)
 → 사용자 승인 → ApprovedAction 발급 (A-3)
 → executor 4단계 재검증 → 멱등 실행 (B-2)
 → 감사 로그 전 과정 기록 확인 (B-2 audit_log)
```

→ 데모 실패 지점이 A(감지·진단·승인)와 B(제안·실행)에 **교차 분산** — 리스크 중간×2 설계의 근거.

### 11.5 남는 비대칭 (정직하게)

- **B의 executor는 여전히 가장 어려운 단일 컴포넌트**(★5). 승인 분리로 개수는 줄었지만 높이는 그대로 → 게이트 #7·#9·#10을 🤝로 두어 데모 실패 책임을 공동 분산.
- **A는 의존 사슬이 김** (Mock → 임계치 → eval). 1주차 Mock 품질이 A 전체 일정의 열쇠.
- 보강 포인트: A는 트랜잭션·동시성(승인 멱등 처리가 입문), B는 측정·모델링(품질 eval이 입문) — **재분배가 이 보강을 의도적으로 끼워 넣음.**

---

> §9의 모든 `□`가 채워지고 contracts 브랜치가 머지되면, 🅰/🅱는 각자 슬라이스 브랜치로 분기한다.
