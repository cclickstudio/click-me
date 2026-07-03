# 이상 감지 선제 알림 — 배달 채널 조율 (A: 채팅 세션 / B: 알림 패널 / C: 하이브리드)

> 작성 2026-07-02, 담당 🅱. 상태: **팀 조율 대기** (기능 스위치 `MANAGEMENT_CHAT_NOTIFY_ENABLED=false`로 봉인).
> **이행 노트(2026-07-03)**: 이 문서의 `MANAGEMENT_CHAT_NOTIFY_ENABLED`(bool)는 채널 설정
> `MANAGEMENT_NOTIFY_CHANNEL`(log|chat|panel)로 대체됐다. `true` → `chat`, `false` → `log`.
> 상세: `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification/task-02-config-sink-wiring.md`.
> 배경: 이상 감지 → 에이전트 선제 제안 파이프라인은 구현·E2E 검증 완료
> (`docs/management/remediation-advisor-검증-가이드.md` §9). 다만 실화면 확인 결과
> **"알림이 채팅 세션에 메시지로 심기는" 현행 UX가 원하는 방향이 아니라는 피드백**이 있어,
> 배달 채널 3안을 구현 수준으로 정리한다. 파이프라인 자체는 채널과 무관하게 재사용된다.

---

## 0. 전제 — 어느 안이든 재사용되는 것 (이미 구현·테스트 완료)

```
스캔(주기/수동) → advisor(서버 재검증+옵션 계약) → resolver(캠페인→프로젝트, org fail-closed)
                                                      → [배달 채널 ← 여기만 3안이 갈림]
```

| 자산 | 파일 | 채널 의존성 |
|---|---|---|
| 옵션 고정 계약 (`ConsultResult`·`RemediationOption`·schema_version) | `remediation/contracts.py` | 없음 |
| 재검증 + 옵션 풀 + 결정론 렌더러(LLM은 인트로만) | `remediation/advisor.py` | 없음 |
| 캠페인→프로젝트 역추적 (org fail-closed·soft-delete 가드) | `remediation/resolver.py` | 없음 |
| 수동 스캔 엔드포인트 (org 스코프·잠금 409·쿨다운 429·배달 요약) | `management.py` `/anomaly/notify-scan` | 없음 |
| `consult_anomaly` 챗 도구 (사용자가 먼저 물을 때) | `subagent_tools.py` | 없음 |
| 스팸 방지 판정표 **로직** (신규/미열람/쿨다운/후속) | `remediation/chat_sink.py` | **"열람" 신호의 출처만 채널별로 다름** |
| consult 컨텍스트 주입 ("1번 해줘" → 위젯 매핑) | `remediation/context.py` + `chat.py` | 채팅에서 대화가 이어질 때만 필요 — A·C에서 사용 |
| 배달 sink 교체 지점 (Composition Root) | `notifications.py` `build_notification_sink` | 여기서 A/B/C sink를 갈아끼움 |

즉 **3안의 차이는 "consult 결과를 어디에 저장하고, 사용자에게 어떻게 보여주고, 무엇으로
'읽음'을 판정하느냐"뿐**이다. 감지·검증·매핑·보호장치는 공통.

---

## 1. A안 — 현행: 채팅 세션 심기 + 벨(N5) 재사용

### 사용자 경험

```
이상 발견 → 프로젝트에 "⚠ 캠페인 이상 알림" 세션 자동 생성/재사용
→ 에이전트 메시지가 세션에 미리 와 있음 → 채팅 벨 🔔 배지(미열람 세션)
→ 사용자가 세션 열면: "트래픽 캠페인에 이상… 어떻게 하실래요? ①②③④"
→ "1번 해줘" → 같은 세션에서 위젯(sim_form 등) 렌더 → 진행
```

### 동작 방식 (구현 완료 상태)

- `ChatNotificationSink.deliver()`가 resolver로 프로젝트를 찾고, 그 프로젝트의 전용 세션
  (`⚠ 캠페인 이상 알림`)을 찾거나 만들어 `append_widget_messages`로 assistant 메시지를 심는다.
  meta에 옵션표(`remediation_consult`, schema_version=1)가 실린다.
- 벨은 기존 N5(`/api/chat/notifications`, `FloatingChat.tsx`가 **현재 선택 프로젝트** 스코프로
  폴링) 그대로 — 미열람 assistant 메시지가 있으면 배지.
- "읽음" = `chat_sessions.last_read_at` (세션 열람 시 자동 갱신) → 스팸 방지 판정표가 이걸로
  bell_pending/cooldown/후속 통지를 가른다.
- "1번 해줘" 시 `chat.py`가 세션의 consult meta를 DB에서 회수해 LLM 컨텍스트로 주입 →
  옵션 번호 → 도구(tool_hint) 정확 매핑.

### 추가 작업량: **0** (완료·검증됨)

### 장점
- 프론트 0줄 — 벨·채팅·위젯·읽음 처리 전부 기존 인프라.
- 알림과 대화가 한 공간 — "묻고 → 답하고 → 위젯으로 실행"이 끊김 없이 이어짐.
- 읽음/스팸 방지 신호가 자연스러움 (세션 열람 = 확인).

### 단점 (이번 피드백의 핵심)
- **시스템 알림이 대화 공간을 침범** — 채팅 목록에 시스템 생성 세션이 생기는 위화감.
- 알림만 모아 보는 뷰가 없음 — 여러 캠페인 이상이 쌓이면 세션 하나에 메시지가 누적.
- 벨이 채팅 벨과 겸용이라 "운영 알림"과 "대화 알림"이 구분 안 됨.
- 프로젝트를 선택하고 있어야 배지가 보임 (org 전체 알림 뷰 없음).

---

## 2. B안 — 별도 알림 시스템 (알림 테이블 + 패널 UI)

### 사용자 경험

```
이상 발견 → 상단(헤더/사이드바) 알림 아이콘 🔔에 배지
→ 클릭하면 알림 패널(드롭다운/드로어): 카드 목록
   ┌────────────────────────────────────┐
   │ ⚠ 트래픽 캠페인 — 노출 0 감지        │
   │ 심사·예산·타깃 문제 가능성            │
   │ [① 시뮬 점검] [② 새 시안] [③ 중지] [무시] │
   └────────────────────────────────────┘
→ 버튼 클릭 시 해당 기능으로 직행 (시뮬 페이지 / 생성 페이지 / 조치 확인 모달)
```

### 동작 방식 (신규 구현)

**DB — 알림 테이블 신설** (⚠ `core/models.py` 변경 = 사전 공지 + Alembic, 협업 규칙 §공통부-2)

```python
class ManagementNotification(Base):
    """운영 알림 — 이상 감지 consult 결과를 채팅과 분리 저장."""
    __tablename__ = "management_notifications"
    id: UUID PK
    organization_id: UUID FK  # org 스코프
    project_id: UUID FK       # 프로젝트 귀속(패널 필터)
    campaign_id: str          # 외부 캠페인 id
    kind: str                 # "remediation_consult" (확장 대비)
    payload: JSONB            # ConsultResult.to_meta() 그대로 (옵션표·schema_version)
    read_at: datetime | None  # 읽음 — 판정표의 "열람" 신호가 이걸로 바뀜
    resolved_at: datetime | None  # 조치됨/무시됨 (명시 확인 — v2 체크박스 요구의 정식 해법)
    created_at: datetime
```

**백엔드 — 신규 3요소** (전부 🅱 소유 영역 + 자기 라우터)

1. `remediation/panel_sink.py` — `PanelNotificationSink`: `deliver()`가 세션 대신
   `management_notifications`에 INSERT. **스팸 방지 판정표는 동일 로직**을 쓰되 신호만 교체:
   `last_read_at` → `read_at`, "같은 캠페인 미열람 consult 존재" → `read_at IS NULL AND
   resolved_at IS NULL` 행 존재. dedup은 `(org, campaign_id, kind, resolved_at IS NULL)`
   부분 유니크 인덱스로 DB 레벨 보강 가능(Codex 지적한 멀티워커 dedup도 이 김에 해결).
2. 알림 API (`management.py` 추가) — `GET /notifications?project_id=`(목록+미읽음 수) ·
   `POST /notifications/{id}/read` · `POST /notifications/{id}/resolve`(무시/조치됨).
3. `build_notification_sink` 분기 — 설정으로 A/B sink 선택(예:
   `management_notify_channel: chat | panel`).

**프론트 — 신규 2요소** (프론트 담당 조율 필요)

1. 알림 아이콘+패널 컴포넌트 — 헤더/사이드바에 배지, 클릭 시 카드 목록. payload의 옵션표로
   버튼 렌더(tool_hint → 라우팅: `run_simulation`→시뮬 페이지, `run_generation`→생성 페이지,
   `manage_campaign`→조치 확인 모달(기존 campaign_action 카드 재사용 가능성 검토)).
2. 폴링 or 라우트 전환 시 fetch (기존 N5 벨과 같은 패턴).

### 채팅 자산과의 관계
- `context.py` 주입·"1번 해줘" 흐름은 **사용 안 함** (대화가 아니라 버튼 클릭이므로).
  → 옵션 선택이 대화형이 아니게 됨 — "왜요?" "다른 방법은?" 같은 후속 질문 불가.
- `consult_anomaly` 챗 도구는 그대로 유효 (사용자가 먼저 물을 때).

### 예상 작업량: **대** — DB 마이그레이션(조율) + API 3본 + sink 1개 + 프론트 패널 신규
### 장점
- 알림과 대화의 완전한 분리 — 이번 피드백을 정면으로 해결.
- org/프로젝트 알림을 모아 보는 뷰 + `resolved_at`로 명시적 확인(체크박스 요구 충족).
- 멀티워커 dedup까지 DB 레벨로 해결 가능(부분 유니크 인덱스).
### 단점
- 작업량 최대 + `core/models.py` 조율 + 프론트 리소스 필요 (발표 7-14 일정 리스크).
- **대화형 상담이 사라짐** — "에이전트가 묻고 사용자가 답한다"는 원래 컨셉이 버튼 UI로 축소.
- 위젯 흐름(sim_form 프리필 등) 재사용이 어려워 각 버튼별 라우팅을 새로 설계해야 함.

---

## 3. C안 — 하이브리드: 알림 패널(요약) + 클릭 시 채팅 상담 진입

### 사용자 경험

```
이상 발견 → 알림 아이콘 배지 → 패널에 요약 카드
   ┌────────────────────────────────────┐
   │ ⚠ 트래픽 캠페인 — 노출 0 감지        │
   │ [상담하기]              [무시]        │
   └────────────────────────────────────┘
→ [상담하기] 클릭 → 채팅 열림 + 그 시점에 상담 메시지가 세션에 심김
→ "어떻게 하실래요? ①②③④" → "1번 해줘" → 위젯 → 진행 (A안의 대화 흐름 그대로)
→ [무시] 클릭 → resolved 처리, 재통지 억제
```

### 동작 방식 (신규 = B의 절반 + A의 재사용)

- **저장**: B와 동일한 `management_notifications` 테이블 — 단, 스캔 시점에는 **알림 레코드만**
  만들고 채팅 세션은 건드리지 않는다 (대화 공간 침범 없음).
- **[상담하기]** = `POST /notifications/{id}/consult` (신규, 🅱 라우터):
  payload(ConsultResult meta)를 그대로 `append_widget_messages`로 세션에 심고
  session_id 반환 → 프론트가 그 세션으로 이동. **A안의 심기·주입·"1번 해줘" 코드가 그대로
  재사용**되고, 심는 시점만 "자동"에서 "사용자 클릭"으로 바뀐다.
  (재검증 옵션: 클릭 시 advisor.consult를 다시 돌려 최신 상태로 갱신 — "다시 확인하니
  정상이에요" 응답도 가능.)
- **스팸 방지**: 알림 레코드 단에서 판정 (B와 동일 — read_at/resolved_at 기반). 세션 판정표는
  불필요해짐(심기는 사용자 클릭이므로 중복 심기 걱정 없음 — 같은 알림 재클릭 시 기존 세션 재사용).
- **[무시]** = `resolved_at` 마킹 → 쿨다운 지나도 같은 이상 재통지 억제(또는 후속만 허용 —
  정책 선택).

### 예상 작업량: **중** — B의 테이블/API/패널은 필요하되, 옵션 실행 UI(버튼별 라우팅·모달)를
새로 만들 필요가 없음 — 상담 진입 후는 검증 완료된 A 흐름.
### 장점
- 이번 피드백 해결(대화 공간 침범 없음) + **대화형 상담 컨셉 보존** — 둘 다 잡는 유일한 안.
- "묻고 답하는 에이전트"라는 발표 스토리 유지 + 알림은 알림답게.
- 심기가 사용자 클릭 시점이라 스팸/중복 문제가 구조적으로 축소.
- A 코드의 재사용률 최대 (chat_sink의 심기 로직 → consult 엔드포인트로 이동만).
### 단점
- B와 같은 조율 비용(테이블·프론트 패널)은 그대로 존재.
- 클릭 한 번이 추가됨(벨→패널→상담하기→채팅) — A보다 진입이 한 단계 김.

---

## 4. 비교표

| | A 채팅 세션 (현행) | B 알림 패널 | C 하이브리드 |
|---|---|---|---|
| 추가 작업량 | **0 (완료)** | 대 | 중 |
| 이번 피드백(대화 공간 침범) | ❌ 미해결 | ✅ 해결 | ✅ 해결 |
| 대화형 상담("1번 해줘"→위젯) | ✅ | ❌ 버튼으로 축소 | ✅ 유지 |
| 명시적 확인/무시 | ❌ (열람 추정만) | ✅ resolved_at | ✅ resolved_at |
| org/프로젝트 알림 모아보기 | ❌ | ✅ | ✅ |
| DB 조율 (`core/models.py`) | 불필요 | **필요** | **필요** |
| 프론트 신규 | 0 | 패널 + 버튼별 실행 UI | 패널(요약+버튼 2개)만 |
| 멀티워커 dedup | 인프로세스 잠금(후속 과제) | DB 유니크로 해결 가능 | DB 유니크로 해결 가능 |
| 발표(7-14) 일정 적합성 | 즉시 가능 | 빠듯 | 가능권 |

## 5. 🅱 추천과 근거

**C안 추천.** 근거는.
1. 피드백의 본질은 "알림은 알림답게"이지 "대화형 상담을 없애라"가 아님 — C만 둘 다 만족.
2. 검증 완료된 A 자산(심기·meta 주입·"1번 해줘"·위젯)의 재사용률이 가장 높음 — 새로 만드는
   건 테이블 1 + API 3 + 패널 카드 1종.
3. B에서 새로 설계해야 하는 "버튼별 실행 UI"는 사실상 채팅 위젯의 재발명 — 중복 투자.

일정이 급하면 **과도기 운용**도 가능: A를 데모 전용(스위치 on은 시연 때만)으로 쓰고,
C를 후속 PR로. 어느 쪽이든 파이프라인·계약은 그대로다.

## 6. 팀 결정 필요 항목

- [ ] 채널 방향: A 유지 / B / C (🅱 추천 C)
- [ ] (B·C 시) `management_notifications` 테이블 신설 — core/models.py 사전 공지 + Alembic 담당
- [ ] (B·C 시) 알림 아이콘 위치·패널 UX — 프론트 담당 협의 (기존 N5 벨과 병치? 통합?)
- [ ] (C 시) [상담하기] 진입 세션 정책 — 전용 세션 재사용(현행) vs 알림당 새 세션
- [ ] (C 시) 옵션 선택 UX — 번호 타이핑 vs **옵션 버튼** (🅱 추천 버튼). 버튼은 하드코딩이
  아니라 meta의 옵션 목록(`OPTION_POOLS`, anomaly_type별 3~4개·관망 항상 마지막)을 그대로
  렌더 + `[기타]` 추가. 예: no_delivery → `[① 시뮬 점검] [② 새 시안] [③ 일시중지] [④ 두고 보기] [기타]`.
  - 버튼 클릭 = 정규화된 사용자 메시지 전송(meta에 option_id 동봉) → 기존 `chat.py` 주입
    경로 재사용, LLM 해석 없이 tool_hint 정확 매핑. 도구 직접 실행(채팅 우회)은 B안
    "버튼별 실행 UI"의 재발명이라 비추천.
  - [기타] 클릭 = 전송 없이 채팅 입력창 포커스만 이동(placeholder 안내 문구 교체) —
    자유 입력이 항상 열려 있음을 명시해 B안식 "버튼 UI로 축소"를 방지.
  - 버튼은 1회용 비활성화하지 않고 consult 메시지에 유지(후속 대화 뒤 "그럼 1번" 가능),
    이미 실행한 옵션만 표시(체크 등) 처리.
- [ ] (C 시) [무시] 후 재통지 정책 — 완전 억제 vs 이상 지속 시 후속 1회 허용
- [ ] 발표(7-14) 데모는 어느 상태로? (A 스위치 온 데모 / C 완성 대기)

## 7. 참고

- 구현·검증 상세: `docs/management/remediation-advisor-검증-가이드.md`
- 설계 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
- 후속 과제 목록(멀티워커 dedup 등): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` §후속 PR 후보
