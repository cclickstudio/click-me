# 이상 감지 알림 C안(하이브리드) 설계 — 알림 패널 + 클릭 시 채팅 상담 진입

> 작성 2026-07-03, 담당 🅱. 상태: 설계 승인 완료, 구현 계획 대기.
> 배경: `docs/management/remediation-알림-채널-조율.md`에서 C안 채택.
> 파이프라인(스캔→advisor→resolver)은 구현·검증 완료 자산 재사용 — 이 스펙은 배달 채널만 다룬다.

---

## 0. 확정된 결정 사항

| 항목 | 결정 |
|---|---|
| 벨 위치 | 페이지 상단 우측 (B) — `AppLayout.tsx` 공통 영역, 팀 공지 필요 |
| 알림 스코프 | org 전체 + 패널에서 프로젝트 필터 |
| 상담 세션 | 프로젝트당 전용 세션("⚠ 캠페인 이상 알림") 재사용 — 현행 A안과 동일 |
| [무시] 재통지 | 완전 억제 (`resolution='ignored'`만 억제, `actioned`/`auto_normal`은 재발 시 재통지) |
| [상담하기] | 클릭 시점에 advisor 재검증 후 심기. **재클릭은 이동 전용(재검증 없음)** — §4 근거 |
| 옵션 선택 UX | 옵션 버튼(meta 동적 렌더, 3~4개+`[기타]`) + 자유 입력 병행. 버튼 라벨 "두고 보기(추가 조치 없음)" 반영 완료 |
| 구현 범위 | 백엔드 + 프론트 전부 (풀스택 1회) |
| 실시간 | REST 폴링 기반 + SSE 인프로세스 브로커 병행 |
| 마이그레이션 | **0005**, `down_revision = "0004_generator_kb_search_vector"` (dev 머지 선행) |
| 일반화 | 테이블은 management 스코프 유지, 단 kind 네임스페이스·campaign_id nullable로 후일 승격 저렴하게 |

## 1. 데이터 모델

`core/models.py` 추가 (공통부 — 사전 공지 + Alembic 0005).

```python
class ManagementNotification(Base):
    """운영 알림 — 이상 감지 consult 결과를 채팅과 분리 저장."""
    __tablename__ = "management_notifications"
    id: UUID PK
    organization_id: UUID FK(organizations)   # org 스코프 (벨 조회 기준)
    project_id: UUID FK(projects)             # 카드 프로젝트 라벨·필터
    campaign_id: str | None                   # remediation kind에서만 필수(코드 검증)
    kind: str                                 # "management.remediation_consult" — 도메인 프리픽스
    dedup_key: str                            # remediation: f"{campaign_id}:{anomaly_type}"
    payload: JSONB                            # ConsultResult.to_meta() (옵션표·schema_version)
    read_at: datetime | None                  # 열람 — 판정표 신호
    resolved_at: datetime | None
    resolution: str | None                    # ignored | actioned | auto_normal
    consult_session_id: UUID | None           # 상담 진입 세션 (재클릭 시 이동 전용)
    last_notified_at: datetime                # 쿨다운·정렬 기준 (후속 통지 시 갱신)
    followup_count: int = 0
    created_at: datetime                      # 최초 발생 시각 — 후속 통지에도 보존
```

- **부분 유니크 인덱스**: `(organization_id, kind, dedup_key) WHERE resolved_at IS NULL`
  — 미해결 알림은 dedup_key당 1행. 멀티워커 dedup을 DB 레벨에서 해결(후속 과제 목록의
  Codex 지적 해소). dedup_key에 anomaly_type이 들어가 같은 캠페인의 다른 이상 유형은
  충돌하지 않는다. fingerprint(지표값 해시)는 **넣지 않는다** — 지표는 틱마다 변해
  dedup 자체가 무너진다.
- **후속 통지 = INSERT가 아니라 기존 미해결 행 UPDATE** — `read_at=NULL`(배지 재점등),
  payload 최신 consult로 교체, `followup_count+=1`, `last_notified_at=now`,
  `created_at` 보존. 유니크 인덱스와 충돌 없음. 카드에 "N회째 알림" 표기 가능.
- 시각 전부 UTC aware(naive 금지).

## 2. API (`/api/management/notifications*`, 🅱 라우터)

라우터 선언 순서: `stream`을 `/{id}` 계열보다 먼저(향후 `GET /{id}` 추가 시 가로채기 방지).

```
GET  /notifications?project_id=&unread_only=&limit=50&before=
  → { notifications: [...], unread_count }
  - org 스코프(_require_org_id 재사용), project_id는 선택 필터
  - unread_count는 필터 무관 항상 org 전체 미해결·미열람 수 (벨 배지용)
  - 정렬·커서(before) 모두 last_notified_at desc — created_at은 최초 발생 표기용
  - limit 기본 50·최대 200, 기본 미해결만(resolved 포함은 query 옵트인)

POST /notifications/read              body: {ids: [...]}   # bulk — 단건도 같은 경로
POST /notifications/{id}/resolve      body: {resolution: "ignored"|"actioned"}
POST /notifications/{id}/consult      # §4
GET  /notifications/stream            # SSE — §5
```

- 권한: 4본 모두 알림의 `organization_id`와 로그인 org 대조, 불일치는 404(fail-closed).
- resolved 알림에 consult → **409 아닌 200 + `{status:"already_resolved", resolution}`**
  (다른 탭에서 이미 처리된 stale UI를 부드럽게 갱신).
- **read·resolve·consult 상태 변화 시에도 SSE publish** — 다른 탭·팀원 배지 동기화.

## 3. PanelNotificationSink + 스캔 연결

새 파일: `domain/management/remediation/panel_sink.py` · `broker.py` (🅱 소유).

`ChatNotificationSink`와 같은 뼈대 — NotificationSink 포트(`notify`), `deliver()`가
`DeliveryOutcome` 반환, `summary()` 포맷 동일 → **`/anomaly/notify-scan`·`scheduler.py`
무변경**. 실패 시 `LogNotificationSink` 폴백 + 고정 스키마 이벤트 로그 이식.

**deliver 순서 — 판정 선행, consult는 통지 확정 후** (skip 경로에서 reader I/O 절약)

```
campaign_id 없음 → skip(no_campaign_id)
resolver 실패    → skip(no_project_mapping)   [org fail-closed 동일]
판정 (DB 조회만 — finding meta의 anomaly_type 힌트로 dedup_key 선계산):
  (org, kind, dedup_key)에 resolution='ignored' 행 존재 → skip(ignored)   [완전 억제]
  미해결·미열람                          → skip(bell_pending)
  미해결·열람·last_notified_at 쿨다운 내 → skip(cooldown)
advisor.consult 재검증:
  실패 → skip(consult_failed) / 정상 → skip(verified_normal)
INSERT 또는 후속 UPDATE + SSE publish → delivered
```

- **finding 계약 확장**: 스캐너 finding meta에 `anomaly_type` 힌트 추가(신호별 결정적 —
  노출 0 → no_delivery). 스케줄러 기본 스캐너·수동 스캔 `_org_scanner` 양쪽 반영.
- **동시성 2중 방어**: chat_sink의 모듈 레벨 `asyncio.Lock`(dedup_key 단위) 유지 +
  유니크 인덱스 백스톱. 동시 INSERT 충돌은 `IntegrityError` → `skip(dedup_race)`.
  충돌 시 UPDATE 전환은 **하지 않는다** — race 창이 수 초라 payload 신선도 이득이 없고,
  미열람 행 payload 덮어쓰기는 판정표 우회다.
- **정상화 reconciliation**: 스캐너가 findings와 별도로 **"성공 조회 + 정상" 캠페인
  목록**을 반환하도록 계약 확장. 스캔 마지막에 그 목록의 dedup_key 미해결 알림을
  `auto_normal`로 resolve + publish. 조회 실패 캠페인은 무변경(fail-closed —
  "finding에 없음 ≠ 정상"). 이게 없으면 stale 알림을 [무시]로 치우게 되고, 완전 억제
  정책 때문에 미래의 진짜 재발 알림까지 막힌다.

**sink 선택 — Composition Root 일원화**

```python
# core/config.py
management_notify_channel: str = "log"   # log | chat | panel
management_notify_sse_enabled: bool = True
```

`build_notification_sink`가 channel로 분기. 기존 `management_chat_notify_enabled`(bool)는
제거하고 channel로 일원화 — 참조처(테스트·docs·.env 예시·검증 가이드) 전수 확인 후,
"기존 env `MANAGEMENT_CHAT_NOTIFY_ENABLED=true` → `MANAGEMENT_NOTIFY_CHANNEL=chat`"
이행 노트를 남긴다. A안(chat sink)은 코드 유지 — 폴백 카드.

## 4. consult 엔드포인트와 채팅 연결

```
① 알림 조회 + org 대조(404) + read_at IS NULL이면 read 마킹 동시 처리
   (이후 어느 경로로 끝나든 read 변화가 있었으면 publish — ②로 빠져도 배지 동기화)
② resolved → 200 {status:"already_resolved", resolution}
③ consult_session_id 있음 → 세션 존재 확인:
     살아 있음 → 200 {status:"consult", session_id}   (이동 전용)
     삭제됨   → consult_session_id 비우고 ④부터 재실행
④ advisor.consult 재실행(최신 재검증)
     실패 → 503 (알림 무변경, 재시도 가능)
     정상 → auto_normal resolve + publish → 200 {status:"normal", message}
⑤ 이상 지속 → 전용 세션 find_or_create (프로젝트당 1개, 제목 "⚠ 캠페인 이상 알림")
⑥ CAS: UPDATE … SET consult_session_id=:sid WHERE id=:id AND consult_session_id IS NULL
     승자 → append_widget_messages로 심기 (meta = 최신 ConsultResult.to_meta())
       심기 실패 → 보상 롤백(SET consult_session_id=NULL WHERE consult_session_id=:sid)
                  후 503 — 빈 세션 영구 안내 방지, 다음 클릭이 처음부터 재시도
     패자 → 심기 생략, 같은 session_id 반환
⑦ publish + 200 {status:"consult", session_id}
```

- 심기 로직은 `chat_sink.DbConsultStore`의 `find_or_create_session`·`append_consult`를
  공용 헬퍼로 추출해 chat sink와 consult 엔드포인트가 공유(중복 구현 금지).
- **재클릭 재검증 안 함(결정)** — "클릭 시 재검증"의 목적은 알림 생성↔첫 상담 시차 해소.
  재클릭은 진행 중 상담으로의 내비게이션이며, 매번 심으면 세션 스팸. 정상화는
  reconciliation이, 세션 내 최신 확인은 `consult_anomaly` 도구가 담당. row lock
  (SELECT FOR UPDATE)도 채택 안 함 — 외부 I/O(advisor) 동안 행 잠금을 붙드는 안티패턴,
  CAS로 충분.
- 이상 유형이 재검증에서 달라진 경우: 알림의 payload·dedup_key는 원본 유지, 상담
  메시지만 최신 결과로 심는다(알림 ≠ 상담 내용의 정본 분리).

**옵션 버튼 위젯** — 상담 메시지 meta를 `ChatConversation`이 감지해
`RemediationOptionsWidget` 렌더.

- 버튼은 meta 옵션 목록 그대로(하드코딩 금지, 3~4개 + `[기타]`).
- 버튼 클릭 = 정규화 사용자 메시지 전송 — 텍스트("1번(시뮬레이션으로 소재 점검)
  진행해줘") + meta `{kind:"remediation_option_select", option_index, action, tool_hint}`.
  백엔드는 meta 우선 매핑, meta 없는 일반 타이핑("1번 해줘")은 기존 컨텍스트 주입 폴백 —
  두 입력 공존.
- `[기타]` = 전송 없이 입력창 포커스 + placeholder 안내 교체.
- 실행된 옵션은 체크 표시(비활성화 안 함 — 후속 대화 뒤 다른 옵션 선택 가능). 1차
  범위에서는 위젯 로컬 상태만(세션 재로드 시 표시 소실 수용, 영속 추적은 후속).
- 통합 지점 검증 필요: `POST /chat/complete`가 사용자 메시지 meta를 수용하는지 —
  안 되면 요청 필드 소폭 추가(계획 단계에서 확인).

## 5. SSE — 인프로세스 브로커

- `broker.py`: `subscribe(org_id) → asyncio.Queue(maxsize=8)` / `publish(org_id)` /
  `unsubscribe`. 이벤트는 `{"event":"changed"}` 신호뿐 — 수신 측은 목록 refetch
  (payload 동기화 문제 원천 차단).
- **drop 정책**: `put_nowait` + `QueueFull`이면 새 신호 드랍. 큐가 가득 = 미소비 신호
  존재 = 깨어나면 refetch 1회로 병합되므로 무손실(주석으로 근거 고정).
- 연결 종료 시 `finally`에서 큐 등록 해제, 30초 heartbeat.
- **단일 프로세스 전제** — 모듈 주석 + `management_notify_sse_enabled` 설정으로 고정.
  멀티워커 배포 시 끄면 폴링만으로 동작(외부 브로커 추상화는 하지 않는다 — 단일 EC2
  인프로세스는 확정된 아키텍처 결정이고 폴링 폴백이 커버).
- 인증: EventSource 대신 채팅과 같은 fetch 스트리밍(Authorization 헤더).

## 6. 프론트

```
components/manage/notifications/
├─ NotificationBell.tsx      상단 우측 고정 벨 + 배지(unread_count, org 전체)
├─ NotificationPanel.tsx     드롭다운 — 카드 목록·프로젝트 필터·[상담하기][무시]
└─ useNotificationStream.ts  SSE 훅(fetch 스트리밍, 지수 백오프 재연결)
components/chat/
└─ RemediationOptionsWidget.tsx
```

- 벨 장착: `AppLayout.tsx` 메인 콘텐츠 우상단(공용 상단바 부재) — **프론트 공통 영역
  변경, 팀 공지**.
- `api.ts`에 `api.management.notifications` 계열 append-only 추가.
- 갱신 2중: SSE "changed" → refetch 기본 / SSE 꺼짐·연결 실패 중엔 N5처럼 라우트 전환
  시 refetch 폴백. 패널 열람 시 화면에 보인 카드 bulk read.
- [상담하기] 후 이동: org 전체 패널이라 타 프로젝트 알림 가능 — `project_id`가 현재
  선택과 다르면 프로젝트 전환 후 FloatingChat을 해당 세션으로 open
  (`ChatController.setActiveSessionId`). `{status:"normal"}`이면 이동 없이 카드
  자리에서 "다시 확인하니 정상이에요" + resolved 갱신.

## 7. 테스트

백엔드(pytest — chat_sink 테스트 패턴: fake store·clock 주입)

- panel_sink 판정표 전 분기: 신규/미열람/쿨다운/후속/ignored/dedup_race(IntegrityError).
- reconciliation: 정상 확인 캠페인만 auto_normal, 조회 실패 무변경(fail-closed).
- consult 전이표 전부: already_resolved 200 / 재클릭 이동 전용 / 정상→auto_normal /
  심기 실패→CAS 롤백→503→재시도 성공 / CAS 동시 요청 승자 1회 심기 / 삭제 세션 재생성.
- API: org 교차 404, 페이지네이션(last_notified_at 커서), unread_count 범위, bulk read.
- 브로커: publish→수신, QueueFull 드랍 후 refetch 신호 보존, 해제 정리.
- SSE: httpx ASGI 스트리밍으로 첫 이벤트·heartbeat.
- 마이그레이션: 부분 유니크 동작(중복 INSERT 거부) SQLite/PG 양쪽.

프론트: ESLint + build 게이트. 동작 검증은 구현 후 Claude Preview로 전체 플로우
(스캔 → 벨 → 패널 → 상담하기 → 옵션 버튼 → 위젯 실행) 실화면 확인.

## 8. 팀 조율 체크리스트

- [ ] `core/models.py` + Alembic **0005**(`down_revision="0004_generator_kb_search_vector"`) 사전 공지
- [ ] dev 머지(0004 확보) 후 구현 시작
- [ ] `AppLayout.tsx` 벨 추가 — 프론트 공지
- [ ] `MANAGEMENT_CHAT_NOTIFY_ENABLED` → `MANAGEMENT_NOTIFY_CHANNEL` 이행 노트 공유

## 9. 참고

- 채널 3안 비교·채택 근거: `docs/management/remediation-알림-채널-조율.md`
- 파이프라인 구현·검증: `docs/management/remediation-advisor-검증-가이드.md`
- 원 설계 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
