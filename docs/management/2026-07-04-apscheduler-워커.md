# APScheduler 워커 — 매니지먼트 자동화 정리 (실제 구현 기준)

작성 2026-07-04 · 코드·NeonDB·프론트 3계층 라이브 검증 완료 기준 · 쌍 문서 [[2026-07-03-메모리-아키텍처-설계노트]]

> **한 줄.** APScheduler = "운영에서 켜면 스스로 도는 백엔드 에이전트 워커". **관측·감지·집계·기록은 워커가 자율**(agent 모드면 성과는 LLM 판단), **돈·게재 write(집행)는 워커 밖·사람 승인**. gen/sim은 레지스트리에 등록만 하면 붙는 확장 seam 마련.

---

## 1. 목적 & 원칙

- **① 스스로 도는 에이전트** — `MANAGEMENT_SCHEDULER_ENABLED`이 켜지면 인프로세스 `AsyncIOScheduler`가 간격마다 자율 발화(무SQS, 단일 EC2). 기본 **off**(dev/CI/test 안전).
- **② 사람 승인은 워커에 안 넣음** — executor(집행 write) 미배선(코드 import 0). Tier 2/3(소재교체·예산증감·게재시작)은 워커가 "감지·제안·알림"까지만.
- **③ 무승인·시간트리거 자동화는 워커가 판단** — 감지·진단·집계·기록·정상화. 성과 미달은 agent 모드에서 LLM(`diagnose_campaign`)이 판정.
- **원칙** — "관측은 자율, 집행은 사람 / 요청·입력 시점 로직은 요청 경로". 임계 수치는 지어내지 않고 `contracts/policy.py` 단일원천(휴리스틱 금지).

---

## 2. 현재 워커 구성 — 잡 3개 (`domain/management/scheduler.py`)

`start_scheduler(settings)` — `management_scheduler_enabled`일 때만 기동, 3개 잡 등록.

### 잡 ① `mgmt-scan` — 이상 스캔 (기본 60분, `management_scan_interval_minutes`)
`_job → run_scan(settings, sink, scanner, recorder=record_finding)`. 스캐너는 모드로 선택:

| 모드(`management_scanner_mode`) | 스캐너 | 커버리지 |
|---|---|---|
| `agent`(**기본**, §8) | `_agent_scanner` | 게재0 + **성과 진단(LLM)** + 소재 피로 + 계정(지갑·예산) |
| `rule` | `_default_scanner` | 게재0 + 계정(지갑·예산) |

**감지 룰 5종** (임계 = `contracts/policy.py`):

| 룰 | 판단 | 임계 | 스코프 | anomaly_type/rule |
|---|---|---|---|---|
| 게재 0 | 규칙 | 활성인데 impressions==0 | 캠페인 | no_delivery / zero_impressions |
| 성과 미달 | **에이전트**(규칙→INCONCLUSIVE시 LLM) | 목표 ROAS 대비 | 캠페인 | performance / (dx) |
| 소재 피로 | 규칙 | frequency ≥ 3.0 | 캠페인 | audience_fatigue / creative_fatigue |
| 지갑 소진 | 규칙 | 사용률 ≥ 95% / 80% | 계정 | wallet_depleted / warning |
| 월 예산 가드레일 | 규칙 | 런레이트 > 월 목표 | 계정 | budget_pace_over |

\+ **정상화 reconcile** — 정상 확인 캠페인(normals)으로 미해결 알림 auto_normal 해소.

### 잡 ② `mgmt-weekly-report` — 주간 리포트 (기본 주1회, `management_weekly_report_interval_minutes`=10080)
`run_weekly_report → insights.weekly_report`(읽기 전용 집계) → automation_runs 다이제스트.

### 잡 ③ `mgmt-rebalance` — 예산 리밸런싱 제안 (기본 일1회, `management_rebalance_interval_minutes`=1440)
`run_rebalance_report → insights.rebalance_proposal`(CPC 기반 저효율→고효율, 읽기 제안). 제안 있을 때만 automation_runs 적재(status=proposal). **실행(예산 이동)은 사람 승인(budget-commit) 유지** — 워커는 제안까지만.

### 발견 후 처리 (공통)
- **배달**: `build_notification_sink` → 채널=panel이면 **PanelNotificationSink(보은)** → `management_notifications`(벨) / reconcile.
  - 워커 tenant="global" → **계정 알림은 벨 skip(피드로만)**, 캠페인은 프로젝트 역추적 시 벨.
- **기록**: `record_finding` → **automation_runs**(actor=`auto`, 프론트 조회) + 프로젝트 역추적되면 **chat_execution_history**(롱텀).

---

## 3. 자동화 분류 (전체 목록 → 워커/요청/승인)

### 🟢 워커 자율 (시간 트리거만으로 의미)
백엔드 주기 스케줄러(본체) · 실 캠페인 이상 스캔(게재0) · 소재 피로 감지 · **성과 미달 진단(에이전트, 기본)** · 지갑/예산 가드레일 · 주간 리포트 · **예산 리밸런싱 제안(잡③)** · 자동 점검 결과 기록(actor=auto) · 정상화 reconcile.

### 🟡 워커 밖 — 요청·온디맨드 (특정 순간·입력·write)
| 자동화 | 왜 |
|---|---|
| 캠페인/모니터링 지표 새로고침(120초) | 브라우저 setInterval — 이상 감지가 아니라 **라이브 지표 뷰 새로고침**(워커가 대체 불가, 유지) |
| 월 예산 목표 설정 / 매출 기반 목표 계산 | 사용자 입력·계산기 |
| Meta 정책 자동 검증 / UTM 자동 부착 | 생성·변경 요청 시점 게이트/훅 |
| 캠페인 삭제·종료 동기화(reconcile) | per-org 로컬 write |
| 실지출 동기화 | per-org **크레딧 차감(재무 write)** — 스케줄 친화적이나 멱등·감사 필요 |
| 실행 이력 자동 기록 | executor 집행 성공 훅(워커 발견분은 record_finding 별도) |
| 시간축 에스컬레이션 | 조치 후 사다리(연속일 추적 갖춰지면 워커 확장 여지) |

### 🔴 워커 밖 — 사람 승인 (집행 write, Tier 2/3)
소재 교체(REPLACE_CREATIVE) · 예산 증감(INCREASE/DECREASE_BUDGET) · 크레딧 기반 게재 시작(ACTIVATE).

> 판단 기준: **자율 트리거(시간)만으로 의미 있으면 워커, 특정 순간(요청·입력·집행)에만 의미면 워커 밖.**

---

## 4. 채팅 연결 (라이브 검증)

채팅(딥에이전트) `ask_management` → 매니지먼트 어시스턴트 16 도구. 워커와 **같은 감지 로직**을 조회로 노출:
- 조회/검색: `live_campaigns·budget·detail·find_by_name·breakdown·creatives·targeting·leads·before_after·organic_compare` · `live_weekly_report` · `live_rebalance_proposal` · **`live_anomaly_scan`**(워커 스캔의 채팅 미러) · `search_kb` · `web_search`.
- 조치/상담: 딥에이전트 `create_campaign·manage_campaign·consult_anomaly·recall_history`(집행은 사람 승인 카드).
- 데이터 없거나 권한 없으면 지어내지 않고 정직 안내(예: Meta 리드=leads_retrieval 권한 한계).

---

## 5. 데이터 (NeonDB 실측)

| 테이블 | 역할 | 검증 |
|---|---|---|
| `automation_runs` | 워커 관측·집계 적재(운영·프론트 조회) | 스케줄러 자율 발화 시 `actor=auto` 행 적재 확인(wallet_depleted) |
| `management_notifications` | 알림 벨 — 캠페인 consult(보은) + **계정 alert(campaign_id=NULL·payload.kind=account)** | consult 1 + account 1 확인 |
| `chat_execution_history` | 롱텀 단일 기억(BM25) — 워커 발견분 actor=auto | 존재 |
| `management_audit_events` | 감사(모든 시도) — 기억과 분리 | 존재 |

**프론트 반영** — 이상감지 페이지 "서버 자동 점검 결과"가 automation_runs를 읽어 표시("화면 안 열어둬도 워커가 쌓아둠"). 알림 벨은 계정 alert[확인] + 캠페인 consult[상담하기].

---

## 6. 확장 seam — 제너레이터·시뮬레이터 붙이는 법

자동화는 도메인 파라미터로 일반화돼 있어 **등록만 하면** 같은 파이프라인(레지스트리·automation_runs·프론트 조회)에 붙는다.

1. **레지스트리 등록** — 도메인 모듈 로드 시 `core.automation.register_automation("generator"|"simulation", "<job>", interval_minutes=..., description=...)`. (management는 `anomaly_scan`·`weekly_report` 등록됨. gen/sim 현재 0건 = 대기.)
2. **잡 함수** — 각 도메인에 `run_*(settings)` 작성(관측·집계·읽기 위주, write면 사람 승인/요청 경로 원칙 준수).
3. **스케줄 배선** — 해당 도메인 스케줄러(또는 공용)에서 `add_job`. management 패턴(`start_scheduler`) 참고.
4. **적재** — `core.automation.record_automation_run(domain="generator", ...)`로 automation_runs에 남기면 프론트 `GET /automation/runs`가 자동 조회(도메인 필터).
5. **조회 API** — `api/routers/automation.py`의 `GET /runs`가 domain 파라미터로 이미 일반화.

> 원칙은 동일 — **관측·집계·기록은 워커 자율, 사람 승인 필요한 집행은 워커 밖.**

---

## 7. 운영 스위치 & 기본값

| 설정 | 기본 | 운영 권장 |
|---|---|---|
| `MANAGEMENT_SCHEDULER_ENABLED` | off | 운영에서 on |
| `MANAGEMENT_SCANNER_MODE` | **agent**(§8 기본화) | agent |
| `MANAGEMENT_SCAN_INTERVAL_MINUTES` | 60 | 운영 정책대로 |
| `MANAGEMENT_REBALANCE_INTERVAL_MINUTES` | 1440(일1회) | 운영 정책대로 |
| `MANAGEMENT_DEFAULT_TARGET_ROAS` | None(성과 진단 생략) | 목표 설정 시 성과 판정 활성 |
| `MANAGEMENT_NOTIFY_CHANNEL` | panel | panel |
| `MANAGEMENT_READER_MOCK` | (env) | false=실 Meta / true=데모 하니스 |

---

## 8. 정합 항목 현황

**완료(2026-07-04, "무승인 자율 100%"):**
- ✅ **agent 모드 기본화** — `management_scanner_mode` 기본 `agent`. 워커 켜면 성과는 에이전트(LLM) 판정.
- ✅ **프론트 자동 스캔 → 워커 결과 읽기 전환** — 이상감지 페이지 클라 10분 자동 스캔 루프 제거, 진입 스냅샷 + "서버 자동 점검 결과"(automation_runs) 읽기 + 수동 버튼. 상시 감지는 워커.
- ✅ **리밸런싱 제안 워커 잡화** — 잡③ `mgmt-rebalance`(읽기 제안, 실행은 사람 승인).

**남음(별도 설계):**
- **reconcile / 실지출 sync** — 무승인이나 per-org write → 멀티org 순회 + (sync는) 멱등·감사 안전장치 후 워커 편입 검토.
- 참고: 캠페인/모니터링 120초 폴링은 감지가 아닌 라이브 지표 뷰 새로고침이라 유지(워커 대체 불가).

---

## 9. 왜 agent 판단인가 — 이득과 방어

> §8에서 agent 모드를 기본화한 근거. 규칙만 도는 워커(`_default_scanner`) 대비 에이전트 스캐너(`_agent_scanner` → `diagnose_campaign`)가 주는 이득과, 그 리스크를 배선으로 막은 지점을 함께 박제한다.

### 이득 4가지

| # | 이득 | 규칙만으로 못 하는 이유 | 근거 |
|---|---|---|---|
| ① | **맥락 이상 포착** | 규칙은 단일 필드 임계 초과(impressions==0·frequency≥3.0)만 봄. 실제 성과 저하는 ROAS·CPC·빈도가 얽힌 복합 신호라 임계선 하나로 못 걸림 | `_agent_scanner` 성과 미달 판정 |
| ② | **행동 가능한 진단 산출** | 규칙은 `zero_impressions` 라벨만 던짐. agent는 가설·확신도·source를 함께 내 승인 카드(ActionProposal)의 근거가 됨 — 감지에서 안 끊기고 제안까지 연결 | `scheduler.py:240-249`(hypothesis·confidence·source) |
| ③ | **룰 증식 억제** | 새 이상 패턴마다 규칙·예외를 더하면 룰 테이블이 비대. LLM이 미인코딩 패턴을 흡수 — 값싼 결정론(게재0·피로)만 규칙으로 남기고 애매한 성과 판정만 위임 | 규칙/LLM 하이브리드 구성 |
| ④ | **상시 백그라운드 판단** | 요청 경로가 아닌 워커라 지연이 UX 무영향, 간격 통제로 LLM 비용 예측 가능, "화면 안 열어둬도 서버가 쌓아둠"(automation_runs) | 잡① 주기 실행 |

### 리스크 방어 (장점만 취하고 비결정성은 배선으로 차단)

| 리스크 | 방어 | 근거 |
|---|---|---|
| LLM 비결정·환각 | 규칙이 먼저 결정론 판정, **INCONCLUSIVE일 때만** LLM 보강(additive) | `diagnose_campaign`(규칙→LLM) |
| 목표 없이 지어내기 | `target_roas` 없으면 성과 진단 **자동 생략**(휴리스틱 금지) | `scheduler.py:197-198`·`231` |
| LLM이 돈·게재를 움직임 | 워커는 executor 미배선 — **감지·진단·알림·기록까지만**, 집행은 사람 승인 | §2 원칙 ②·§3 🔴 |
| LLM 실패가 스캔 마비 | 실패 시 규칙 스캐너로 **폴백**(org 스코프는 전역 폴백 억제) | `scheduler.py:186-194` |

> 한 줄. **임계값이 못 보는 복합·맥락 이상을 잡고, 라벨이 아니라 가설·확신도라는 행동 가능한 진단을 상시 백그라운드로 생산** — 그걸 "규칙 우선·LLM 보강·집행은 사람" 게이트로 감싸 비결정성 리스크 없이 취한다.
