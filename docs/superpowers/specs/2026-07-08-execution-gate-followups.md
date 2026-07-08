# 집행 게이트 하드닝 — 후속 개선 항목 (adversarial review 산출)

> 2026-07-08 · management 도메인 · 브랜치 `feat/management-boeun`
> 배경: 오늘 "집행 게이트 하드닝"(승인 플레인 폐쇄 + 게이트 정본화 + launch_suggest) 작업을
> Codex + opus 적대 리뷰 3회로 검증한 결과, **CRITICAL 없음**. 핵심 3구멍(무인증 `/approve`·
> approver_id 클라이언트 수신·승인 위조)과 `org_demo` 센티넬 우회는 이번 작업에서 모두 닫혔다.
> 아래는 리뷰가 IMPORTANT/MINOR로 지적했으나 **선재이거나 낮은 위험**이라 이번 스코프에서
> 분리해 후속으로 남긴 항목이다. 우선순위·오너·근거를 함께 기록한다.

## 이번에 닫은 것 (참고)

| 구멍 | 조치 | 커밋 |
|---|---|---|
| `/approve` 무인증 | 로그인 + org 검증(`_require_org_id_write`) | `4f0d4ea7` |
| approver_id 클라이언트 수신 | 필드 제거 + 서버 `user.id` 주입 | `4f0d4ea7` |
| 승인 위조(원장 부재) | DB 원장 `management_approval_records` + `issue_approval` 단일 발행 + executor 게이트 #5(9필드 대조) | `210586e3`~`4f0d4ea7` |
| 집행 권장 게이트 TEST 해제 | settings 정본화(클릭≥1%·거부<20%) + `/exec-gate` | `8dc3f93a` |
| `org_demo` 센티넬 → live writer 도달 | 데모 executor DRY_RUN 강제 + 승인 execution_mode MOCK 핀(이중 봉인) | `631a193a` |

adversarial 검증: `org_demo` 봉인은 `_demo_executor`의 writer가 `_mode`로 실 전송을 차단
(토큰 유무 무관)하고, 게이트 #5가 execution_mode 불일치를 거부하는 이중 방어로 verified safe.

## 후속 항목

### F1 (Important) — activate/pause가 org-scoped writer를 쓰지 않음

**현상.** `api/routers/management.py`의 `activate_campaign`·`pause_campaign`은 executor를
`_get_executor()`(writer 인자 없음)로 얻는다. `_get_executor()`는 전역 settings 기반 writer를
빌드하므로, `use_mock=False`(실 연동)에서 이 두 경로는 **로그인 org의 연결 writer가 아니라
전역 Meta 크리덴셜**로 집행한다. 대조적으로 `/execute`(라인 ~886)와 `budget_commit`은
`_get_executor(await _require_writer(db, org_id))`로 org 스코프 writer를 주입한다.

**영향.** 승인 자체는 존재하므로(게이트 #5 통과) 위조는 아니다. 문제는 **멀티테넌트
크리덴셜 격리**가 이 두 경로에서 깨진다는 점 — 실 연동 시 org A의 사용자가 activate/pause를
전역 토큰으로 수행할 수 있다.

**왜 이번 스코프 밖.** activate/pause의 executor 선택 로직은 이번 작업 이전부터 존재하는
구조다(우리는 승인 발행만 `issue_approval`로 일원화). 현재 페이즈 `use_mock=True`라 전역
writer가 DRY_RUN이므로 실 위험 없음.

**픽스.** 두 핸들러의 `_get_executor()`를 `/execute`와 동일하게
`_get_executor(await _require_writer(db, org_id))`로 교체(단, 시연 센티넬 경로는 데모 executor
유지 — F1은 실 org 경로에만 해당). 오너: management. 우선순위: 실 연동(`use_mock=False`)
활성화 전 필수.

### F2 (Important) — activate_campaign이 승인 전에 writer.set_spend_cap 호출

**현상.** `activate_campaign`은 `issue_approval()`(승인 발행)·게이트 #5(executor 검증)보다
**먼저** `writer.set_spend_cap()`을 호출한다. 즉 "모든 지출성 write는 승인 후"라는 이번 작업의
불변식과 배치되는 write가 승인 앞단에 1건 있다.

**현재 차단 상태.** 그 LIVE 경로는 `ActivateRequest`에 존재하지 않는 `body.org_id`를 참조해
**먼저 AttributeError로 크래시**하므로 실제 set_spend_cap write가 도달하지 못한다. 이 선재
크래시가 언젠가 수정되면 승인 전 write가 되살아난다.

**왜 이번 스코프 밖.** set_spend_cap 호출 순서와 `body.org_id` 참조 모두 이번 작업이 만든
코드가 아니다(선재). 우리는 activate의 `approve()`→`issue_approval()` 교체만 했다.

**픽스.** (a) `body.org_id` → `_require_org_id_write`에서 얻은 org_id로 교정, (b)
`set_spend_cap()`을 `ACTIVATE_CAMPAIGN` 실행 경로(승인·게이트 통과 이후) 안으로 이동하거나,
승인 발급·검증을 writer 호출보다 앞에 두도록 순서 변경. 오너: management. 우선순위: F1과
함께(실 연동 전).

### F3 (Minor→Important 잠재) — consumed_at 미검사 리플레이

**현상.** executor 게이트 #5(`_verify_approval_record`)는 원장 레코드의 `consumed_at`을
거부 조건으로 쓰지 않는다. 소진(consume) 마킹은 관측·감사용이고, 재제출 차단은 전적으로
멱등 키(`build_idempotency_key`)에 의존한다(코드 주석 `c19cd504`에 명시).

**리뷰 우려.** 멱등 저장소가 소실되거나(인메모리 + 프로세스 재시작) 원장과 생명주기가
어긋나면, 이미 소진된 승인이 재실행될 수 있다.

**왜 즉시 수정 안 함(설계 상호작용 주의).** executor 흐름상 게이트 #5는 **멱등 재생(get_result)
보다 먼저** 실행된다. 게이트 #5에 `consumed_at` 거부를 그대로 넣으면, 정상적으로 멱등
재생(같은 결과 반환)을 기대하는 재제출까지 `UNAPPROVED_ACTION`으로 막혀 **멱등 재생이 깨지는
회귀**가 난다. 운영 배선은 `DbIdempotencyStore` + `DbApprovalStore`가 같은 DB라 동시 소실
가능성이 낮아 현재 실 위험은 제한적이다.

**픽스(설계 필요).** consumed 거부를 게이트 #5가 아니라 **멱등 재생 실패 이후** 지점에 두어,
"재생할 결과도 없는데 이미 소진된 승인"만 거부한다. 또는 멱등 저장소와 원장을 단일 트랜잭션
생명주기로 묶는다. 오너: management. 우선순위: 멱등 저장소를 인메모리에서 DB로 완전 전환하고
실 연동을 켜기 전 재검토.

### F4 (Minor) — InMemoryApprovalStore.put 중복 키 동작이 DB와 다름

`InMemoryApprovalStore.put`은 중복 approval_id를 **덮어쓰고**, `DbApprovalStore.put`은 PK
위반으로 **예외**를 던진다(포트 docstring은 fail-loud를 약속 — `8a6bfc8b`). approval_id가
uuid4라 실충돌은 없지만 mock↔실 동작 등가성이 깨진다. 픽스: 인메모리도 중복 시 예외.
오너: management. 우선순위: 낮음.

### F5 (Minor) — issue_approval store.put 실패가 500으로 노출

`/approve`는 `ApprovalIssueError`만 catch한다. 실 연동에서 `store.put`(DB write) 실패는
그대로 전파되어 500이 노출된다(위조·집행은 없어 안전하나 사용자 메시지가 불친절). 픽스:
store 예외를 잡아 위생 처리된 503 반환. 오너: management. 우선순위: 낮음.

### F6 (Minor, 거버넌스) — 교차 도메인 import를 core/tools로 승격

`domain/simulation/service/simulation_service.py`가 `domain.management.contracts.policy`의
`is_executable_verdict`/`exec_gate_thresholds`를 import한다. import-safe(순환 없음, 부수효과
없음)하고 규칙의 문자("contracts 경유 교환")는 만족하지만, 판정은 **스키마가 아니라 공유
로직**이고 이제 두 도메인이 쓴다. CLAUDE.md의 "공유 로직은 core/tools로" 정신에 맞춰
`is_executable_verdict`/`exec_gate_thresholds`를 `core`(예: `core/exec_gate.py`)로 옮기고
`management/contracts/policy.py`는 재-export하는 편이 낫다. 리뷰어들도 **single-source 보장이
현재 airtight하므로 리팩터는 별도 PR** 권장. 오너: management + simulation 합의. 우선순위: 낮음.

### F7 (Minor) — 후처리 훅이 완료 런을 FAILED로 뒤집을 여지

`_record_launch_suggestion`(및 선재 `_record_gen_suggestion`)은 시뮬 `_run`의 try 블록 안에서
`create_center_suggestion`의 자체 try/except **이전**에 `float(...)`를 수행한다. 이론상
비수치 aggregate가 오면 이미 `completed`를 emit한 런이 `FAILED`로 뒤집힐 수 있다(값은
model_dump float이라 실위험 낮음). 픽스: 세 후처리 훅을 각각 best-effort try/except로 감싼다.
오너: simulation. 우선순위: 낮음.

## 정리

- 즉시(실 연동 `use_mock=False` 활성화 전) 처리 권장: **F1, F2** (멀티테넌트 크리덴셜 격리·
  승인 전 write).
- 멱등 저장소 DB 전환과 함께: **F3**.
- 여유 시 정리: F4·F5·F6·F7.
- 이번 브랜치(`feat/management-boeun`)는 승인 플레인 폐쇄·게이트 정본화·센티넬 봉인까지
  완료 상태이며, 위 후속은 별도 브랜치/PR로 분리한다.
