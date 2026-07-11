# 발표 대비 리밸런스 데모 패키지 — 실계정 데모 성립 + 알림 CTA + 발표 후 로드맵

> 2026-07-11 확정. 리밸런스 실집행 연결(같은 날 스펙) 완료 후, 발표(2026-07-14) 전 데모 성립과 후속 과제 순서를 확정한다.

## 0. 배경 / 결정 사항

- 리밸런스 배선은 완료됐으나 검증 결과 **실계정에선 제안이 발동하지 않는다** — 활성 캠페인 1개가 lifetime 예산(리밸런스는 daily 전용), daily 캠페인은 paused. transfer 발동 조건은 **활성 + 일예산 캠페인 2개 + 각각 최근 7일 클릭·지출 실측 + CPC 격차 1.2배 초과**.
- `.env`의 `MANAGEMENT_READER_MOCK=true`가 챗·워커 제안을 mock 캠페인 기반으로 만들고 있어, 카드 확인 시 라우터의 org 실 reader 검증(409)과 부정합 — 데모가 카드에서 끊긴다.
- **결정**: 실계정 데모(브레인스토밍 확정). 캠페인은 소액 신규 daily 2개. 발표 전 구현은 알림 CTA 1건만. 나머지 후속 과제는 발표 후 로드맵으로 순서만 확정.

## 1. 데모 셋업 런북 (D-3 ~ D-day)

### 1-1. 설정 전환 (D-3, 오늘)

```bash
# backend/.env — 이 두 줄만 변경 (git diff 없음 — .env는 미추적 로컬 파일)
MANAGEMENT_READER_MOCK=false        # 챗·워커가 실 reader를 보게
MANAGEMENT_EXECUTION_MODE=validate_only   # 리허설 동안 실변경 봉인
```

- `USE_MOCK=false`·`META_ACCESS_TOKEN`·`META_AD_ACCOUNT_ID`는 그대로.
- `MANAGEMENT_SCHEDULER_ENABLED=true` 유지 가능 — 리밸런스 워커 잡은 제안(읽기)만 하고 집행하지 않는다(HITL). 알림 CTA 데모에 오히려 필요.

### 1-2. 캠페인 셋업 (D-3)

- 플랫폼 `create_campaign` 플로우로 **소액 daily 신규 2개** 생성·게재 (각 ₩2,000~3,000/일, 일 합계 ≤ ₩6,000).
- **CPC 격차 1.2배 유도** — 타게팅을 의도적으로 비대칭으로: A는 광범위(저CPC 기대), B는 좁게(고CPC 기대). 소재도 품질 차이를 둬도 좋다.
- 기존 lifetime 활성·paused 캠페인은 **무변경**(리밸런스 적격 필터가 자동 제외).

### 1-3. 실측·발동 확인 (D-2 ~ D-1)

- 두 캠페인 모두 최근 7일 클릭 > 0, 지출 > 0 확인 (`/campaigns` 대시보드 또는 Meta 광고관리자).
- `GET /api/management/budget/rebalance-proposal` → `kind: "transfer"` 발동 확인.
- **validate_only 리허설 1회** — `/manage/budget` 적용 버튼(또는 챗 카드)으로 rebalance-commit 실행 → 결과 SUCCESS + Meta `execution_options=["validate_only"]` 통과 + **실예산 무변경**을 Meta 광고관리자에서 교차 확인. 이 성공 로그가 라이브 전환의 전제 조건.

### 1-4. 라이브 전환 가드 (D-day)

**전환 전제 (하나라도 미충족이면 전환 금지, 플랜 B로)**

1. 1-3의 validate_only 리허설 성공 기록 확보.
2. 당일 아침 transfer 제안 발동 재확인 (격차·실측은 매일 변한다).
3. 두 캠페인 일예산 합계가 의도 범위(≤ ₩6,000) 이내인지 확인.

**전환 절차**

1. `backend/.env`에서 `MANAGEMENT_EXECUTION_MODE=live` **한 줄만** 변경 — 변경 직후 파일을 눈으로 재확인(다른 줄 오염 금지).
2. 서버 재기동(설정은 기동 시 로드).
3. 실집행은 **데모 그 1회만** — 챗 "리밸런스 적용해줘" → 카드 확인 → 집행.
4. 집행 직후 Meta 광고관리자에서 양쪽 캠페인 일예산이 제안대로 반영됐는지 교차 확인(감액 먼저·증액 다음, 총액 불변).

**복귀 (발표 종료 즉시 — 체크리스트 마지막 항목, 담당: 본인)**

1. `MANAGEMENT_EXECUTION_MODE=dry_run` 복귀 + 서버 재기동.
2. 복귀 확인: 현재 제안 기준 정상 요청 1건을 보내 결과 스냅샷의 `mode`가 `dry_run`(실전송 없음)인지 확인 — 제안이 없으면 서버 로그의 기동 설정으로 갈음.
3. 데모 캠페인 2개 일시중지(과금 중단).

**금지 사항**

- live 상태로 자리 이탈·밤새 방치 금지.
- live 중 데모 외 추가 집행(재시도 포함) 금지 — 실패 시 그 자리에서 재시도하지 말고 dry_run 복귀 후 원인 확인(특히 `indeterminate` 응답이면 절대 재시도 금지, Meta 실측 확인 먼저).

### 1-5. 플랜 B (transfer 미발동 시)

- **B-1**: 당일 아침 CPC 격차 미달이면 한쪽 캠페인 타게팅·입찰을 조정해 오후 재확인 — 발표가 오후면 시도 가치 있음.
- **B-2**: 그래도 미발동이면 **kind=adjust 데모로 전환** — 활성 daily 1개만 남기고(다른 쪽 일시중지) 소진율 기준 증액/감액 제안 → 챗 `apply_rebalance`가 기존 campaign_action 카드로 폴백하는 경로 그대로 시연. 스토리는 "단일 캠페인 예산 최적화"로 서술 조정.
- **B-3**: 최후 수단 — `USE_MOCK=true` 전 구간 mock 데모(집행까지 mock 봉인). 실돈 임팩트는 없지만 흐름은 완결.

## 2. 알림 CTA — 워커 알림 → 챗 진입 (발표 전 유일한 코드 작업)

- **위치**: `frontend/src/app/(app)/manage/anomaly/page.tsx`의 workerRuns 카드(automation runs, management 도메인 렌더 지점).
- **분기**: `run.suggested_action === 'apply_rebalance'` — 이 문자열이 계약이며 백엔드(scheduler.py, 커밋 f6eee22a)가 이미 이 값을 기록한다. 다른 값·오타 확장 금지.
- **동작**: 기존 `suggested_action === 'REPLACE_CREATIVE'` → 제너레이터 링크 관례를 따르되, 챗 진입은 **기존 `clio:draft` 패턴 재사용** — 쿼리 파라미터·챗 페이지 변경 없음.
  ```tsx
  // onClick: 대시보드 CLIO 런처와 동일 패턴 (dashboard/page.tsx:219-227)
  sessionStorage.setItem('clio:draft', '리밸런스 적용해줘');
  router.push('/chat');
  ```
  ChatConversation이 **새 채팅이 열릴 때** draft를 1회 소비해 입력창에 싣는다(ChatConversation.tsx:382-392). **자동 전송하지 않는다** — 사용자가 전송·카드 확인을 직접 누르는 HITL 유지.
- **주의(흐름 한계)**: `/chat`은 ChatWorkspace가 뜨며, 우측 대화는 **프로젝트 선택 + "새 채팅" 클릭 전까지 마운트되지 않는다**(ChatWorkspace.tsx:68-75). 따라서 CTA 클릭 직후 프리필이 바로 보이는 게 아니라, 프로젝트 선택→새 채팅 후 보인다 — 기존 대시보드 CLIO 런처와 동일한 동작이며, 발표 전에는 이 동작을 그대로 쓴다(A안). draft 존재 시 새 채팅 자동 오픈(B안)은 대시보드 런처 UX까지 바꾸는 공용 변경이라 발표 후 폴리시로 미룬다(§3 로드맵).
- **문구**: "챗에서 리밸런스 적용하기 →".
- **테스트**: `pnpm build` + 렌더 분기(suggested_action 있는 run/없는 run) 확인. 백엔드 무변경.

## 3. 발표 후 로드맵 (순서 확정 — 각자 별도 브레인스토밍·스펙)

| 순서 | 과제 | 방향 | 비고 |
| --- | --- | --- | --- |
| 1 | ⑤ `/approve` 강화 | 서버 저장 제안을 proposal_id로 로드·클라이언트 제안 수용 제거, 카드/세션/사용자 결속 | **실돈 안전 최우선.** 범용 경로라 팀 사전 공지 필수(협업 규칙) |
| 2 | ② 동시성 가드 | 캠페인 단위 잠금(transfer-intent 키), budget-commit 포함 커밋 경로 전반 | 절대값 쓰기+drift가 창을 좁혀 현재는 저위험 |
| 3 | ③ saga outbox | Meta 호출 전 attempt 퍼시스트 + reconcile | executor 전반 선재 속성 |
| 4 | ④ 재무 원장 | 감사 마스킹 유지 + 암호화 원장(예산 변경 재구성용) | CLAUDE.md 보안 규칙과 병행 |
| 전달 | ⑥ simulation 스코핑 | 구현 아님 — org 스코핑 미결(D4) 전달 메모 작성해 simulation 팀 공유 | coord 문서 기반 |
| 폴리시 | 챗 draft 자동 오픈(B안) | clio:draft 존재 시 마지막/첫 프로젝트로 새 채팅 자동 오픈(자동 전송은 안 함) | 알림 CTA와 대시보드 런처 UX 동시 개선 — 공용 챗 워크스페이스 변경이라 발표 후 |

## 4. 성공 기준

- 발표 리허설(D-1)에서 "워커 알림 → CTA 클릭 → `/chat` 진입 → 프로젝트 선택 → 새 채팅(입력 프리필 확인) → 전송 → 리밸런스 카드 → 확인 → validate 통과" 전 구간이 이어진다(A안 — 프리필은 새 채팅 시점에 보이는 게 정상 동작).
- D-day live 집행 1회가 Meta 광고관리자 실측과 일치(감액→증액, 총액 불변).
- 발표 직후 dry_run 복귀가 체크리스트로 확인된다.
