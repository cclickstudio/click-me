# 이상 감지 → 에이전트 선제 제안(remediation advisor) 설계

> 작성 2026-07-02, 브랜치 `feat/management-boeun`. 담당 🅱(보은).
> 목적: 이상 감지(🅰, 무변경)가 이상을 발견하면 **에이전트가 채팅으로 먼저 사용자에게 묻고**
> ("어떻게 하실래요?"), 선택에 따라 시뮬 재실행·시안 재생성·일시중지/예산 조정·관망으로
> 이어주는 대화형 조치 제안 경로를 신설한다.

---

## 1. 배경과 원칙

- 기존 재생성 경로(`/regenerate*` 라우터·`decide_action` 규칙표·selection HITL·job service·평가 5종·데모)는
  **유지**한다 — 게이트 #9(키 없이 재현)·CI가 걸려 있다. 사용처 없음 확인 후 삭제는 **추후 별도 PR**.
- 감지(🅰) ↔ 제안(🅱)의 접점은 `DiagnosisResult` 계약뿐 — detection·scheduler의 **기존 로직은
  수정하지 않으며**, 변경은 §9의 터치 포인트 3곳(도구 등록·주입·seam 분기)으로 한정한다.
  sink는 설계된 seam(`build_notification_sink`)에 어댑터만 꽂는다.
- push 채널은 기존 채팅 벨(N5, `/api/chat/notifications` — unread>0 세션 배지)을 그대로 쓴다.
  **프론트 작업 0줄** — 새 위젯·새 페이지 없음.
- 클라이언트가 넘긴 진단 데이터는 신뢰하지 않는다 — **진단은 항상 서버에서 재조회·재검증**한다.

## 2. 전체 흐름

```
스케줄러 스캔(기존 scheduler.py run_scan, 무변경) → 이상 발견
    ↓
ChatNotificationSink (신규 — NotificationSink seam 어댑터)
    ① advisor.consult(campaign_id): 서버에서 실측 재조회 + 진단 재검증
    ② 캠페인의 프로젝트를 찾아 알림 세션 확보(없으면 생성, 있으면 재사용)
    ③ 스팸 방지 판정(§5) 통과 시 assistant 단독 메시지 심기(append_widget_messages):
       "camp_1 CTR이 계속 떨어지고 있어요(품질 저하 추정, 확신 0.82).
        어떻게 하실래요? ① 새 시안 생성해 교체 ② 시뮬로 먼저 검증
        ③ 일시중지 ④ 관망"
    ↓
채팅 벨 배지 🔔 (기존 N5, 무변경) → 사용자가 열면 질문이 와 있음
    ↓
"1번 해줘" → 딥 에이전트 LLM이 주입된 컨텍스트(§4)를 읽고 기존 위젯 호출:
  run_generation(gen_form) / run_simulation(sim_form) / manage_campaign(campaign_action)
  지출 조치는 기존 campaign_action → /approve → /execute 경로 그대로 (HITL 불변식 유지)
```

보조 진입: 채팅에서 직접 "camp_1 성과 왜 이래?" → 딥 에이전트가 `consult_anomaly` 도구 선택
→ 같은 advisor로 합류(재검증 겸용 — "다시 확인하니 지금은 정상 범위예요" 가능).

## 3. 새 모듈 — `domain/management/remediation/` (🅱 소유)

| 파일 | 역할 |
|---|---|
| `contracts.py` | `RemediationOption(kind: platform\|spend\|observe, action, label, rationale, tool_hint)` · `ConsultResult(message, options, diagnosis_summary)`. **스키마 고정 계약** — action 어휘는 remediation 전용 enum(플랫폼 액션 `VERIFY_SIM` 등은 TIER_POLICY 밖이므로 별도 정의, spend 액션은 TIER_POLICY 키와 일치), `index`는 1부터 연속, `tool_hint`는 등록된 도구명만, `schema_version` 포함(계약 공통 규칙). 외부 의존 없음. |
| `advisor.py` | 두뇌. reader(org 스코프)로 실측 조회 → `diagnose_performance`(🅰 코드, **읽기 전용 호출**)로 진단 → anomaly_type별 옵션 풀(결정론 매핑) → 설명·어조는 LLM(gpt-4o-mini), LLM 실패 시 결정론 문구 폴백(채팅 안 죽음). |
| `chat_sink.py` | `ChatNotificationSink`. 세션 확보 + 스팸 방지 판정(§5) + `history.append_widget_messages`로 메시지·meta 심기. |

- `domain/management/wiring.py`의 `build_notification_sink` 분기 1줄(설정에 따라 ChatSink 반환) —
  management 소유 파일이라 조율 불필요. *(주의: 현재 `build_notification_sink`는 `notifications.py`에
  있음 — seam 위치를 유지하되 분기 추가는 notifications.py에서. 🅰 소유 여부 불명확 시 사전 공지.)*

## 4. 컨텍스트 왕복 — meta 저장 + 서버측 주입

문제: 요청 스키마 `ChatMessage`는 role+content뿐(`core/schemas.py:144`)이라 메시지 meta가
다음 턴 LLM에 도달하지 않는다. content 자연어에만 의존하면 "1번 해줘" 해석이 불안정.

해결: **DB를 source of truth로, 서버가 주입** (기존 `memory_context` 주입 패턴 재사용).

- consult 메시지 meta에 저장(`ChatMessage.meta` JSONB, 기존 컬럼):

```json
{
  "kind": "remediation_consult",
  "schema_version": 1,
  "campaign_id": "...", "org_id": "...",
  "diagnosed_at": "...", "anomaly_type": "quality_degraded", "confidence": 0.82,
  "options": [
    {"index": 1, "action": "REPLACE_CREATIVE", "tool_hint": "run_generation"},
    {"index": 2, "action": "VERIFY_SIM",       "tool_hint": "run_simulation"},
    {"index": 3, "action": "PAUSE_CAMPAIGN",   "tool_hint": "manage_campaign"},
    {"index": 4, "action": "OBSERVE",          "tool_hint": null}
  ]
}
```

- `chat_complete` 시작 시(메모리 주입 바로 옆) 세션의 `remediation_consult` meta를 조회,
  **아래 3조건을 모두 만족할 때만** "진행 중인 이상 조치 상담: campaign_id=…, 옵션표=…"
  문자열로 initial state에 주입한다. 낡은/무관한 컨텍스트가 대화를 오염시키지 않게 좁힌다.
  1. **TTL** — `diagnosed_at`이 유효시간 내(설정 `management_consult_context_ttl_hours`, 기본 24h).
  2. **근접성** — consult 메시지가 세션의 최근 K=10 메시지 안에 있음(대화가 다른 주제로 넘어갔으면 중단).
  3. **최신 1건만** — 세션에 consult가 여러 개면 가장 최근 것만(옵션표 충돌 방지).
  - "조치 실행됨 감지 시 중단"은 v1 제외 — 조치 완료가 채팅 세션에 신뢰성 있게 남지 않아
    (management `/execute`는 audit_events에만 기록) 판정 불가. TTL+근접성이 실질 커버.
- 진단은 영속되지 않으므로 `diagnosis_id` 대신 **`diagnosed_at` + anomaly_type + confidence 스냅샷**.

core 스키마 무변경 · 프론트 무변경 · chat.py에 조회+주입 몇 줄(공통부 최소 터치).

## 5. 스팸 방지 — 재통지 판정표

기존 신호만 사용: `ChatSession.last_read_at`(열람) · consult 이후 user 메시지 존재(응답) · cooldown.

```
스캔 틱에서 (campaign_id, anomaly_type) 이상 발견 시:
최근 consult 메시지 조회 (meta.kind=remediation_consult, 같은 campaign_id+anomaly_type)
├─ 없음                            → 통지 ✅
├─ 있음 + 세션 미열람               → 생략 (벨이 이미 떠 있음)
├─ 있음 + 열람 + cooldown 내        → 생략 (봤고, 생각할 시간)
└─ 있음 + 열람 + cooldown 경과 + 이상 지속
                                   → 후속 통지 ✅ (어조 변경: "…아직 계속되고 있어요")
```

- cooldown은 설정(`management_consult_cooldown_hours`, 기본 24h) — 하드코딩 금지(미확정 정책 단일 소스 규칙).
- 체크박스(명시적 확인 UI)는 **v2 보류** — 대화 응답 자체가 ack이며, v1에서 이중 확인 채널·새 위젯 비용 회피.
  meta.options 구조가 있어 나중에 얹을 자리는 마련됨.

## 6. 수동 스캔 트리거 (데모용) + 보호장치

스케줄러가 기본 off이므로 management 라우터에 "지금 스캔" 엔드포인트 1개 추가.
스케줄러의 `run_scan` 경로를 재사용해 **mock 모드에서도 동작**(기존 `/anomaly/scan`은 mock에서 빈 결과 — 미사용).

보호장치 4종.
1. **인증 + org 스코프** — `get_current_user` + `_require_org_id` 패턴. 자기 org만 스캔·통지.
2. **동시 실행 잠금** — org별 인프로세스 `asyncio.Lock`, 진행 중 재호출 409. (단일 EC2 전제)
3. **쿨다운** — 직전 수동 스캔 후 60초 내 재호출 429. 값은 설정.
4. **통지 이중 방어** — §5 dedup이 최종 방어선(스캔 반복 ≠ 통지 반복).

응답에는 §7-1의 배달 요약(`{scanned, delivered, skipped, failed}`)을 포함한다.
admin 전용 제한·분산 잠금은 v1 제외(현 인증 페이즈·단일 EC2 전제).

## 7. 캠페인→프로젝트 매핑 (확정)

벨(N5)은 project 귀속 세션에만 뜬다(`list_sessions(None)=[]`). 프로젝트는 팀 단위
공유(뷰어/에디터/오너)라 **오배정 = 기밀(성과·예산) 노출**이므로, 블라인드 폴백 없이
**결정론 역추적 → 실패 시 skip**으로 확정한다.

1. **AdCampaignLog 역추적** — `AdCampaignLog.campaign_id`(Meta ID) → `generation_id` →
   `AdGeneration.project_id`. (타 도메인 테이블 읽기는 SimPredictionReader 선례와 동일 성격.)
2. **생성 제안 링크 역추적** — create-proposal이 `evidence_metrics`에 `simulation_id`를
   기록(`management.py:1910`), `/from-generation`은 generation 링크 보유 → simulation/generation의
   `project_id`로 역추적. 플랫폼 경유 생성 캠페인 대부분 커버(simulations.project_id 존재는 구현 시 확인).
3. **실패 시 skip** — 채팅 통지 생략(§7-1 관측). 알림 유실 아님: 기존 `/manage/anomaly`
   페이지(pull)에서 여전히 확인 가능. 잘못된 프로젝트 배달(권한·히스토리 오염)보다 미배달이 낫다.

- **v2 옵션(보류)**: org 공용 관리 세션 — 현재 벨이 `selectedProject` 스코프 폴링
  (`FloatingChat.tsx:57`)이라 실효 없음. 프론트가 org 전체 폴링으로 전환할 때 재검토.

## 7-1. 실패 관측 (통지 실패가 조용히 사라지지 않게)

- 매핑 실패·메시지 저장 실패 시 **사용자 채팅에는 아무것도 표시하지 않는다.** 캠페인 1건의
  실패가 스캔 루프 전체를 중단시키지 않는다(기존 BLE001 관례).
- **composite sink**: `ChatNotificationSink`가 skip/실패 시 기존 `LogNotificationSink`로 위임.
  로그는 파싱 가능한 고정 스키마 —
  `{"event": "management.notify_skipped|notify_failed", "campaign_id": …, "reason": "no_project_mapping|append_failed|…"}`.
- **영속 이벤트 테이블은 v1 제외(YAGNI)** — audit_events 재사용은 반대: 감사 로그는 지출/실행
  전용이며 완료 게이트(#7)와 간섭 위험. 영속이 필요해지면 seam에 sink 추가로 해결.
- **수동/예약 관측**: `ChatNotificationSink`는 결과를 돌려주는 `deliver() -> DeliveryOutcome`
  을 갖고 `notify()`(Protocol, 시그니처 불변)는 이를 감싼다. 수동 스캔은 응답
  `{scanned_findings, delivered, skipped: [{campaign_id, reason}], failed: […]}` +
  `management.scan_summary` 집계 로그, 예약 실행은 건별 고정 스키마 이벤트 로그
  (`management.notify_*`)로 관측한다(스케줄러 무변경 원칙 — 틱 종료 훅 없음).

## 7-2. 열린 결정 (구현 중 확정)

- **`build_notification_sink` 소유권**: notifications.py가 🅰 소유로 판명되면 분기 추가 전 사전 공지.
- **simulations.project_id 존재 확인**: §7 체인 2의 커버리지 확정(없으면 1·3만으로 운영).

## 8. 안 하는 것 (YAGNI)

- 기존 `/regenerate*`·규칙표·selection·평가·데모 삭제(추후 별도 PR) · 새 위젯/새 UI/체크박스 ·
  SES/이메일/웹훅 · 진단 영속 테이블 · scheduler/detection 수정 · core 스키마 변경.

## 9. 공통부 터치 요약 (조율 대상)

| 파일 | 변경 | 성격 |
|---|---|---|
| `api/assistant/subagent_tools.py` | `consult_anomaly` 도구 1개 append | 위임만, 로직은 domain |
| `api/routers/chat.py` | remediation meta 조회+주입 몇 줄 | memory_context 패턴 옆 |
| `domain/management/notifications.py` | sink 분기 1줄 (§7 소유권 확인 후) | seam 활용 |

챗 담당 팀원에게 사전 공지 후 진행.

## 10. 테스트

- **advisor**: anomaly_type→옵션 풀 매핑(결정론) · LLM 폴백 경로 · 서버 재검증(이상 소멸 시 "정상" 응답) ·
  **options 스키마 고정 검증**(모든 anomaly_type 산출이 계약 준수 — enum 어휘·index 1부터 연속·
  tool_hint 등록 도구명·schema_version. LLM이 옵션 구조를 변형 못 함을 보장).
- **chat_sink**: 세션 생성/재사용 · 판정표 4분기(신규/미열람/쿨다운 내/후속) · meta 스키마 ·
  매핑 체인(역추적 성공/skip) · composite 폴백(실패 시 로그 이벤트) · 1건 실패가 루프 안 죽임.
- **주입 조건**: TTL 경과/근접성 밖/최신 1건만 — 3조건 각각 미충족 시 주입 안 됨.
- **수동 트리거**: **동시성 테스트**(같은 org 2요청 `asyncio.gather` 동시 발사 → 정확히 1건 통과·1건 409,
  타 org 동시 요청은 서로 안 막음) · 쿨다운(429) · org 스코프 · 배달 요약 응답 형태.
- **통합 1개**: run_scan에 ChatSink 주입 → 이상 → 세션에 consult 메시지+meta 존재 확인.
- 수동 검증: 스캔 트리거 → 벨 → 채팅 → "1번" → 위젯까지 Claude Preview로 확인.
