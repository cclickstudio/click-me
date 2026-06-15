# 광고 매니지먼트 프론트엔드 설계 — 하이브리드 대시보드 + A/B 토글

작성: 2026-06-15 · 도메인: management(4-2) · 슬롯 균형: 🅰·🅱 동등

## Context

현재 `frontend/src/app/manage/page.tsx`는 하드코딩된 빈 스켈레톤(통계 "-", 빈 테이블, 비활성 버튼)으로 **백엔드 management 도메인과 전혀 연결돼 있지 않다.** 또한 테이블 컬럼에 "예상 CTR"이 있어 CLAUDE.md 금지사항(예측 CTR 실측 환산 금지)을 위반한다.

반면 백엔드 management 도메인은 풍부하다 — A(감지·진단·승인 플레인)와 B(재생성·실행·감사)의 전체 HITL 루프가 구현·테스트(92 passed)돼 있고, `GET /api/management/run`·`POST /api/management/approve` 두 엔드포인트가 노출돼 있다.

**목표**: management 프론트를 (1) 실제 광고 관리 제품처럼 보이는 **사용자 중심 대시보드**로 만들면서, (2) 7/8 발표·포트폴리오를 위해 **A/B 아키텍처(HITL 설계·강제, Agentic AI, 계약 기반 협업)를 토글로 드러낼 수 있게** 한다. A(감지·진단·승인)와 B(재생성·실행·감사)가 **동등하게 주목받도록** 화면 면적·시선 비중을 균형 있게 배분한다.

**스코프 결정**: 데모(#1)+포트폴리오(#3)를 단일 결과물로. 실운영 대시보드(#2, 라이브 데이터·DB 영속성·인증)는 합의문서 v1 스코프(Won't) 밖이므로 "확장 여지"로만 남긴다.

## 핵심 설계 결정

1. **레이아웃 = 균형 하이브리드 대시보드.** 상단 KPI 스트립 아래를 **좌우 동등한 2존**으로 나눈다 — 왼쪽 "측정·진단" 존(🅰: 큰 노출 추이 차트 + 진단 카드), 오른쪽 "개선·실행" 존(🅱: 재생성 후보 + 제안 + 실행). 두 존은 같은 면적·같은 테두리 비중. 그 아래 **승인(HITL)을 좌우를 잇는 다리(공동 클라이맥스)**로, 맨 아래 감사 타임라인(🤝). 순수 위젯 나열 금지 — A존·B존·승인 다리 세 초점.
2. **뷰 토글 = `사용자 보기`(기본) / `아키텍처 보기`.** 같은 데이터 흐름 위에 모드만 바뀐다. 사용자 보기엔 🅰/🅱·계약 이름이 안 보이고, 아키텍처 보기는 🅰/🅱 레인 + 계약 핸드오프(DiagnosisResult·ActionProposal·ApprovedAction·ActionResult) + 엔드포인트 라벨을 오버레이한다.
3. **데이터 흐름 = 감지→진단→재생성→제안→승인→실행→감사** 단일 사이클. "데모 실행" 트리거(고장 주입 선택)로 시작.
4. **백엔드 얇은 엔드포인트 3종 추가**(전부 B 소유 도메인에 위임): `POST /regenerate`, `POST /execute`, `GET /audit`. 결정론 폴백으로 API 키 없이 동작(발표 리허설 안정).

## 아키텍처

### 프론트엔드 (`frontend/src/`)

라우트 `app/manage/page.tsx` 전면 교체. 뷰 모드는 페이지 로컬 상태(`'user' | 'arch'`)로 충분(컨텍스트 불필요). 차트는 기존 `components/ui/DistributionChart.tsx`와 동일하게 **커스텀 SVG**(차트 라이브러리 추가 안 함).

신규 컴포넌트 (`components/manage/` 신설). 배치는 균형 2존 + 승인 다리 구조를 따른다:

| 영역 | 컴포넌트 | 역할 | 데이터 출처 |
|---|---|---|---|
| 상단 | `KpiStrip` | 활성 캠페인·오늘 노출·오늘 지출(₩)·이상 감지 수 | /run 집계 |
| **왼쪽 존 (🅰 측정·진단)** | `ImpressionTrendChart` | 시간별 기대 vs 실측 곡선 + 이상구간 음영 (크게) | /run `expected`·`snapshots`·`anomaly_hours` |
| 왼쪽 존 (🅰) | `SpendTrendChart` | 지출 추이 미니 막대 | /run `snapshots[].spend_krw` |
| 왼쪽 존 (🅰) | `DiagnosisCard` | 원인·확신도·결정론/agent 배지 | /run `diagnosis` |
| **오른쪽 존 (🅱 개선·실행)** | `CandidateCards` | 재생성 후보 3 + 시뮬점수 + 선택 배지 | /regenerate |
| 오른쪽 존 (🅱) | `ProposalCard` | action_type·Tier·예산 before▶after·만료 카운트다운 | /regenerate 또는 /run `proposal` |
| 오른쪽 존 (🅱) | `ExecutionResult` | executor 4단계 진행 + status·failure_reason | /execute |
| **가운데 다리 (🤝 승인)** | `ApprovalBridge` | Tier 판정·재라벨(1▶3)=A 설계 / 무승인 차단=B 강제 · [승인][거절] | /approve |
| 하단 (🤝) | `AuditTimeline` | append-only 이벤트 타임라인 | /audit |
| 전역 | `ViewModeToggle` + `ArchModeOverlay` | 사용자/아키텍처 토글 · 🅰/🅱·계약·엔드포인트 라벨 오버레이 | 토글 상태 |

존 컨테이너는 사용자 보기에서 "측정·진단 / 개선·실행"으로만 라벨하고, 아키텍처 보기에서 🅰/🅱·계약 핸드오프가 양쪽에 동시에 표시된다. 좁은 화면은 두 존을 세로 스택으로 반응형 처리.

`lib/api.ts`에 `management` 네임스페이스 추가:
```ts
management: {
  run: (fault: string) => request(`/management/run?fault=${fault}`),
  regenerate: (body) => request("/management/regenerate", { method: "POST", body }),
  approve: (body) => request("/management/approve", { method: "POST", body }),
  execute: (body) => request("/management/execute", { method: "POST", body }),
  audit: (runId) => request(`/management/audit?run_id=${runId}`),
}
```

### 백엔드 (`backend/`) — B 소유 도메인 위임

`api/routers/management.py`에 엔드포인트 3종 추가(라우터는 🤝 공동 — A와 한 줄 합의 후 append). 판정·실행 로직은 전부 `domain.management`에 위임, 라우터는 얇게.

- `POST /regenerate` — `agents/regeneration_tools.build_regeneration_agent()`로 agent 조립 → `RegenerationContext` 구성 → `propose(diagnosis, context)` → `ActionProposal`(REPLACE_CREATIVE + 후보) 반환. 입력은 /run이 준 `DiagnosisResult`.
- `POST /execute` — `execution/executor.Executor`를 인메모리 어댑터(`InMemoryIdempotencyStore`·인메모리 `AuditSink`·`tier.BudgetAuthority`·고정 `state_version_provider`)로 조립 → `execute(ApprovedAction, ActionProposal)` → `ActionResult` 반환.
- `GET /audit` — 위 `AuditSink`에 쌓인 이벤트 반환(데모는 인메모리; run_id로 필터). 또는 /execute 응답에 감사 이벤트를 포함해 엔드포인트를 줄이는 안도 가능.

무상태(stateless) 데모 원칙 유지: 프론트가 받은 `proposal`·`approved_action`을 그대로 되돌려보내고 `proposal_hash` 재검증으로 변조를 잡는다(기존 /approve와 동일 패턴).

## 데이터 흐름 (1 사이클)

```
[데모 실행 + 고장주입]
  → GET /run                → detection(곡선·이상구간) + DiagnosisResult        (🅰)
  → POST /regenerate(dx)    → ActionProposal(REPLACE_CREATIVE + 후보3·시뮬점수)  (🅱)
  → [사용자 승인]
  → POST /approve(proposal) → ApprovedAction (Tier 판정·재라벨)                  (🅰)
  → POST /execute(action)   → ActionResult (executor 4단계·멱등)                 (🅱)
  → GET /audit(run_id)      → append-only 이벤트 타임라인                        (🤝)
```

## 제약·준수사항 (CLAUDE.md)

- **"예측 CTR" 등 실측 스케일 환산 금지.** 차트는 노출·지출·이상감지만.
- 시뮬 점수 옆 상시 디스클레이머: "실제 성과 상관 미검증·참고용". 화면 하단에 "Mock 기반 데모" 명시.
- 금액은 KRW 정수, 타임스탬프 표기 일관.
- 신규 파일 첫 줄 한국어 헤더 주석. 프론트는 pnpm 전용(uv 금지).
- A 소유 파일(`detection/`·`approval.py`·`agents/diagnosis.py`)은 읽기만 — 수정 금지. 라우터 추가는 공동부라 사전 합의.

## 에러 처리

- 각 단계 로딩/에러 상태 표시. `/regenerate`가 후보 0개(전부 가드 탈락·tool 실패)면 "개선안을 만들지 못했어요" 빈손 상태로 안전 처리(agent가 `None` 반환).
- `failed to fetch`(origin/CORS) 회피: localhost 접속 기준, 비-localhost는 `NEXT_PUBLIC_API_URL` 설정 필요(별도 이슈).
- 거절 시 "무승인 액션은 어떤 경로로도 적용되지 않음" 안내(불변 규칙 #2 시연).

## 검증 (E2E)

1. 백엔드: 신규 3엔드포인트 pytest(또는 최소 curl로 /regenerate·/execute·/audit 200 확인) + 기존 `uv run pytest tests/management`(현재 92 passed) 유지.
2. 프론트: `pnpm lint && pnpm build` 통과.
3. 수동: 백엔드+프론트 기동, `/manage`에서 "데모 실행"(고장 bid_loss) → 전체 사이클 정상 흐름 → "아키텍처 보기" 토글 시 🅰/🅱·계약 오버레이 노출 확인.

## 향후 확장 (스코프 밖)

실운영(#2): core 5개 테이블·DB 영속성·인증 적용 후 라이브 데이터 연결. 다중 캠페인 목록·실제 Meta writer 연동.
