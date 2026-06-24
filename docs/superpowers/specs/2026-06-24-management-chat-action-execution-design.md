# 매니지먼트 챗 — 행동 제안·집행 브릿지 설계

| | |
|---|---|
| Date | 2026-06-24 |
| Domain | management (슬롯 🅱) |
| Branch | feat/management-boeun |
| Status | Draft (설계 합의) |

## 1. 목표

매니지먼트 챗 어시스턴트의 **행동 제안·실행** 경험을 고도화한다. 지금은 챗이 위험 액션을
"제안만" 말하고 끊긴다 — 사용자가 "응 해줘"라고 해도 실제 집행으로 이어질 경로가 없다.
이 설계는 챗의 제안을 **진짜 집행 가능한 `ActionProposal`로 연결**하되, 기존 승인/집행
플레인을 그대로 재사용하고, **자연어 승인과 실행 승인을 명확히 분리**한다.

### 검증 가능한 성공 기준
- 챗에서 위험 액션 제안 시, 응답 `meta`에 영속화된 `proposal_id` + **사람이 읽는 정규화 요약**이
  실려 온다.
- 그 `proposal_id`로 **기존** `/api/management/approve` → `/execute`가 그대로 동작한다.
- 채팅의 자연어 "응 해줘"는 **카드 표시/의도 확인까지만** — 절대 바로 집행하지 않는다.
- 집행 결과 시스템 메시지의 본문은 **서버가 `execution_runs`에서 조회해 생성**한다(프론트가 결과
  본문을 만들지 않는다).
- 제안 생성·실행 **양 시점 모두 권한 검사**를 통과한다.
- 어시스턴트 그래프는 executor/writer를 **직접 호출하지 않는다**(불변규칙 #1 유지).

## 2. 현재 상태 (As-Is)

- **챗 → ReAct 그래프** (`/api/chat` → `build_management_agent`): `graph.py`의 `propose_action`이
  가벼운 스텁 dict(`{action_type, campaign_id}`)와 `SuggestedAction`(tier·rationale)만 만든다.
  위험 Tier면 `interrupt()`로 멈추고 `requires_approval=True`+`thread_id`만 메타로 내려준다.
- **집행 플레인** (`/api/management/approve` → `/execute`): 완전한 18필드 `ActionProposal`을 받아
  3단계 검증 → `ApprovedAction` 발행 → executor 4단계 재검증 → 멱등 집행. 감사·멱등·TTL·해시
  변조 감지 완비. `/execute`는 이미 tenant 일치 검사 보유.
- **격차**: 챗의 `SuggestedAction`을 진짜 `ActionProposal`로 변환해 집행 플레인으로 넘기는
  브릿지가 없다. 챗 메타에 `proposal_id`·요약·권한·TTL 노출이 없다.

## 3. 접근 결정 — A안(브릿지) 채택

| | A. 브릿지 (채택) | B. 그래프 재개 (기각) |
|---|---|---|
| 방식 | 챗이 진짜 `ActionProposal` 생성·영속 → 기존 `/approve`·`/execute` 재사용 | interrupt된 그래프를 `Command(resume)`로 이어 집행 |
| 불변규칙 #1 | 준수 (집행은 executor 단일 경로) | **충돌** (집행이 챗 그래프 안에서 발생) |
| 인프라 재사용 | 멱등·감사·승인 100% 재사용 | 그래프 경로에서 재구성 필요 |
| 상태 영속 | `action_proposals` DB → 어디서나 재개 | PG 체크포인터 필수(현재 MemorySaver 폴백이라 요청 간 재개 깨짐) |
| 범위 | 중 (새 실행 코드 0) | 대 (PG 체크포인터 + 새 엔드포인트 + 규칙 회피) |

B는 더 복잡한 데다 CLAUDE.md 불변규칙 #1·graph.py 주석("어시스턴트는 writer/executor를
직접 부르지 않는다")과 정면 충돌한다. A로 확정한다. **그래프 `interrupt()`는 챗 내 "소프트
확인"용으로만 유지하고, 진짜 승인 게이트는 기존 `/approve`로 둔다.**

## 4. 아키텍처 (To-Be)

```
사용자 질문
  → 챗 ReAct 그래프 (live 도구 + search_kb 로 근거 수집)
  → [권한] propose-time authz 확인 (이 사용자가 이 캠페인 변경 제안을 받을 수 있나)
  → propose_action: 진짜 ActionProposal 조립 + finalize_proposal(해시) + 영속(action_proposals)
  → AskResult: proposal_id + ProposalSummary(정규화 요약) + expires_at
  → chat.py meta 로 SSE 전달
  → [프론트] 승인 카드 표시 (요약·위험도·TTL 카운트다운)
       │  자연어 "응 해줘" = 카드 강조/의도 확인까지만 (실행 아님)
       └ 명시적 버튼 클릭 → 기존 /api/management/approve → /execute
            → [권한] execute-time authz 재확인
            → executor 집행 (4단계 재검증 포함, 만료 제안은 STALE 차단)
       └ 프론트가 {proposal_id, run_id} 만 전달 → POST /api/chat/{thread}/sync-execution
            → 서버가 execution_runs 에서 실제 결과 조회 → 종료 시스템 메시지 생성·적재
```

핵심: 챗은 **제안서를 만들고 핸드오프만** 한다. 승인·집행·결과 기록은 서버 정본에서 담당.

## 5. 사람이 읽는 정규화 요약 (ProposalSummary)

승인 카드는 `proposal_id`만으로 부족하다. 사용자가 한눈에 이해할 정규화 요약을 제공한다.

```
액션:      캠페인 예산 감액 (DECREASE_BUDGET)
대상:      여름 프로모션 캠페인
변경 전:   일 ₩100,000
변경 후:   일 ₩80,000
이유:      최근 7일 CPA가 목표 대비 42% 초과
예상 영향: 지출 감소 · 전환량 감소 가능
위험도:    중간 (Tier 2)
만료:      30분 후 (2026-06-24 14:32 UTC)
```

**설계 결정 — `ProposalSummary`는 서버에서 조립하는 정규화 DTO(표현 계층)로 둔다.**
- 데이터는 이미 `ActionProposal`에 있다(action_type·target·budget_before/after·hypothesis·
  confidence·action_tier·expires_at). 별도 저장 필드 불필요 — `build_proposal_summary(proposal)`로
  파생.
- 한국어 라벨·"예상 영향" 프로즈 같은 표현은 정본 공유 계약(`contracts/ActionProposal`)에 박지
  않는다(계약은 데이터, 표현은 경계에서).
- 단 구조는 **정규화 스키마**로 고정(자유 텍스트 dict 금지): `action_label`·`target_name`·
  `before`·`after`·`reason`·`expected_impact`·`risk_level`·`expires_at`.

> 대안(영속 필드로 `ActionProposal`에 추가)을 원하면 **공유 계약 변경** = 별도 브랜치 + 🅰 양측
> 리뷰 + 골든샘플 갱신(관리 CLAUDE.md 불변규칙 #5). 현 권장은 파생 DTO.

## 6. 자연어 승인 ≠ 실행 승인

사용자가 채팅으로 "응 해줘"라고 해도 **바로 실행하지 않는다.**

| 신호 | 허용 동작 |
|---|---|
| 자연어 "응 해줘"/"그렇게 해" | 승인 카드 표시·강조 또는 **의도 확인까지만**. 실행 금지 |
| 명시적 승인 (버튼 → `/approve`+`/execute`) | 실제 집행. 강한 확인 UX(요약·위험도·TTL 재확인) 동반 |

- 그래프 `interrupt()`는 "소프트 확인"으로만 쓴다 — 집행 트리거가 아니다.
- 실행 경로의 단일 진실은 명시적 승인 API(`/approve`→`/execute`)뿐이다.

## 7. 권한 검사 — 제안 시점 + 실행 시점 (둘 다)

Meta 광고 계정은 권한이 섞인다: 읽기만 / 초안 생성 / 승인 / 실행 / 특정 브랜드·계정 한정.
따라서 한 시점만 막으면 안 된다.

- **제안 시점**: "이 사용자가 이 캠페인(계정/브랜드)에 대해 변경 제안을 받을 수 있나"를 확인.
  권한 없으면 제안 생성하지 않고 읽기 답변만.
- **실행 시점**: `/approve`·`/execute`에서 다시 확인. 기존 tenant 일치 검사에 더해 **승인/실행
  권한 등급**을 검증(읽기·초안 권한만 있는 사용자는 실행 불가).
- 권한 모델 출처는 단일 소스(`core/config.py` 또는 management 권한 헬퍼)로 두고 하드코딩 금지.

## 8. 제안 만료(TTL) UX + STALE 처리

- 제안은 `expires_at`(TTL) 보유. **카드에 남은 시간을 노출**한다("이 제안은 23분 후 만료됩니다").
- 광고 상태는 계속 변하므로 **오래된 제안 실행은 위험**. 만료/상태버전 불일치 제안은 executor
  4단계(낙관적 락)에서 STALE로 차단된다(기존 동작).
- 만료된 제안은 실행하지 않고 **"새로 분석해서 다시 제안"**으로 보낸다(기존 execution_service의
  제안 갱신 경로 재사용 — 새 proposal_id·갱신된 state_version·리셋 TTL·재계산 해시).

## 9. 저장 모델 — 대화/집행 분리, 링크로만 연결

| 저장소 | 테이블 | 진실의 범위 |
|---|---|---|
| 대화 기록 | `management_chat_sessions`/`_messages`/`_agent_runs` | "무슨 말이 오갔나" (append-only) |
| 집행 사실 | `action_proposals` → `approvals` → `execution_runs` | "제안·승인·집행 상태" (감사 정본) |
| 연결 | `management_agent_runs.proposal_id` (신규 컬럼 1개) | 대화 턴 ↔ 제안서 |

규칙.
- **집행 상태를 채팅 메시지 본문에 박지 않는다.** 메시지엔 서사 + `proposal_id`만. 상태(승인대기·
  승인됨·실행됨·만료)는 `action_proposals`/`approvals`/`execution_runs`에서 조회해 렌더.
- **집행 완료만 시스템 메시지로 영속**한다(`execution_runs.result_status`는 종료·불변이므로 안전).
  본문은 **서버가 execution_runs에서 조회해 생성**한다(§10 신뢰 경계).
- 채팅 기록 테이블엔 **벡터 컬럼 없음** — 관계형 그대로. 벡터(임베딩)는 KB 검색(`management_kb_chunks`)
  전용이며 대화 저장과 무관.

### 턴별 적재
1. **제안 턴**: 기존 `record_turn` 3테이블 적재 + `agent_runs.proposal_id` 링크. 진짜 제안서는
   제안 빌더가 `action_proposals`에 별도 적재.
2. **승인 순간**: 정본은 `approvals`. 편의상 기존 `agent_runs.approved_by`/`approved_at`에 미러링.
3. **집행 완료**: `role="system"` 메시지 1건(`proposal_id`·`run_id` 링크) append — 본문은 서버 생성.

## 10. 집행 결과 동기화 — 신뢰 경계

프론트가 임의 결과를 채팅에 주입하지 못하게 한다.

- 프론트는 `{proposal_id, run_id}`만 `POST /api/chat/{thread}/sync-execution`으로 전달.
- 서버가 (a) run_id가 해당 proposal·tenant·사용자 소유인지 검증, (b) `execution_runs`에서 **실제
  result_status를 조회**, (c) 그 값으로 시스템 메시지 본문 생성·적재.
- **"결과 본문"을 프론트가 만들어 보내는 구조는 금지.**

## 11. 변경 범위 (Touch Points)

| # | 파일 | 변경 |
|---|---|---|
| 1 | `assistant/graph.py` `propose_action` | 스텁 dict → 진짜 `ActionProposal` 조립(현재 예산 live/reader 조회, `budget_after`는 액션 파라미터, `finalize_proposal` 해시) + 영속. 시그니처에 `amount`/`pct` 추가. propose-time authz 게이트 |
| 2 | `assistant/` 새 헬퍼 | 제안 빌더(패턴은 `demo.build_sample_proposal` 참고, 기존 영속 경로 재사용) + `build_proposal_summary(proposal)` |
| 3 | `assistant/contracts.py` | `AskResult`에 `proposal_id`·`summary`(ProposalSummary)·`expires_at` 추가. `ProposalSummary` 정규화 스키마 신설 (assistant-local 계약 — 공유 `contracts/` 아님) |
| 4 | `api/routers/chat.py` | meta에 `proposal_id`·`summary`·`expires_at` 추가. `record_turn`에 `proposal_id` 전달 |
| 5 | `assistant/history.py` `record_turn` | `agent_runs` 적재 시 `proposal_id` 기록 |
| 6 | `core/models.py` + Alembic | `management_agent_runs.proposal_id VARCHAR(64)` 컬럼 1개 (공통부 — 단독 PR + 사전 공지) |
| 7 | `api/routers/chat.py` 신규 | `POST /api/chat/{thread}/sync-execution` — {proposal_id, run_id} 검증 후 execution_runs 조회 → 종료 시스템 메시지 생성 (§10) |
| 8 | `/approve`·`/execute` (또는 호출부) | execute-time authz 등급 검사 추가(읽기/초안 권한만이면 실행 거부) |
| 9 | (프론트, 도메인 밖 — 핸드오프) | 승인 카드(요약·위험도·TTL 카운트다운), 자연어≠실행 분리, {proposal_id,run_id}만 sync-execution 전달 |

**재사용(무변경)**: `approval.py`, `executor.py`, `/approve`·`/execute` 검증 로직, 멱등·감사 인프라.
**공유 `contracts/` 무변경**: `ActionProposal`은 *구성*만 하고 스키마는 안 건드린다.

## 12. 보조 — FB 개발자 문서 KB (선택)

FB 개발자 문서(심사 거절 코드·게재 상태·에러 레퍼런스)를 `management_kb_chunks`에 적재해
`search_kb` 근거로 활용. 제안 rationale·"왜 안 나가나" 설명의 출처로 인용. 기존 `kb_ingest.py`
파이프라인(마크다운→청크→임베딩→DB) 재사용. **본 작업과 독립**이며 우선순위 후순위.

## 13. 스코프 제외 (Non-Goals)

- **세션 간 시맨틱 채팅 메모리**(과거 대화를 의미로 검색): 후순위. 세션 내 멀티턴은 기존
  체크포인터로 이미 동작하므로 연속성 손실 없음.
- **B안(그래프 재개)** 및 PG 체크포인터 활성화.
- `ActionProposal` 영속 요약 필드(공유 계약 변경) — 현 권장은 파생 DTO(§5).
- 프론트 승인 카드 구현 상세(도메인 밖, 핸드오프 노트로만).

## 14. 테스트 (성공 기준 → 실패 테스트)

1. 위험 액션 제안 → `AskResult.proposal_id` 비어있지 않음 + `action_proposals`에 행 존재 +
   `summary`의 before/after·risk_level·expires_at 채워짐.
2. 그 제안서로 `validate_proposal` 통과(해시·만료·정책버전).
3. `/approve` → `/execute` 경로가 챗 생성 제안서로 정상 집행(executor 4단계 통과).
4. 같은 `proposal_id` 중복 승인/집행 10회 → 정확히 1회 실행(기존 멱등 게이트 #1 회귀).
5. 자연어 "응 해줘"만으로는 집행이 일어나지 않음(카드/확인 단계에서 멈춤).
6. 권한 없는 사용자: 제안 시점에 제안 미생성 / 실행 시점에 거부(둘 다).
7. 만료된 제안 실행 시도 → STALE 차단 + "다시 제안" 경로로 전환.
8. sync-execution: 위조 run_id(타 proposal·타 tenant) 거부, 정상 run_id는 execution_runs 값으로
   시스템 메시지 생성.
9. 폴백 모드(키 없음/mock)에서도 제안 생성이 깨지지 않음(또는 명확히 비활성).
