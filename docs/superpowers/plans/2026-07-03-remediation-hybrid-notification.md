# 이상 감지 알림 C안(하이브리드) 구현 계획 — 인덱스

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. **각 태스크는 하위 디렉터리의 개별 md 파일이 단독 실행 단위다** — 서브에이전트에게 해당 태스크 파일 + 이 인덱스의 "계약 스냅샷"만 주면 된다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이상 감지 알림을 채팅 세션 대신 알림 패널(테이블+API+SSE)로 배달하고, [상담하기] 클릭 시에만 채팅 상담에 진입시킨다. 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md`.

**Architecture:** `management_notifications` 테이블(Alembic 0005) + `PanelNotificationSink`(chat_sink 판정표 이식, 신호는 read_at/resolved_at) + 알림 REST 4본 + 인프로세스 SSE 브로커. 프론트는 상단 우측 벨/패널 + 채팅 옵션 버튼 위젯.

**Tech Stack:** FastAPI·SQLAlchemy(async)·Alembic / Next.js(TS)·Tailwind / pytest(fake 주입 단위 + `MANAGEMENT_DB_TEST=1` 옵트인 DB 통합).

**실행 규칙:**
- 백엔드 테스트 위치는 `test/backend/management/`(pytest testpaths가 `../test/backend`). 실행: `cd backend && uv run pytest ../test/backend/management/<파일> -v`.
- 백엔드 커밋 전 `cd backend && uv run ruff format . && uv run ruff check . --fix`. 프론트는 `cd frontend && pnpm lint && pnpm build`.
- 새 .py/.tsx 파일 첫 줄에 한국어 역할 주석. 타임스탬프는 UTC aware(naive 금지).
- 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지 — 읽기(import)만.
- 커밋은 태스크 파일에 명시된 파일만 add. 커밋 컨벤션 `타입: 한국어 설명`.

---

## 계약 스냅샷 (태스크 간 시그니처 정본)

서브에이전트는 자기 태스크 파일 + 이 섹션만으로 작업한다. 태스크 파일과 어긋나면 여기가 정본.

- **모델** — `ManagementNotification(core/models.py)`: `id·organization_id·project_id·campaign_id(str|None)·kind(str)·dedup_key(str)·payload(JSON)·read_at·resolved_at·resolution(str|None: ignored|actioned|auto_normal)·consult_session_id·last_notified_at·followup_count(int)·created_at`. 부분 유니크 `uq_mgmt_notif_open_dedup(organization_id, kind, dedup_key) WHERE resolved_at IS NULL`. 마이그레이션 `0005_management_notifications`, `down_revision="0004_generator_kb_search_vector"`.
- **panel_sink** — `KIND = "management.remediation_consult"` · `DedupRaceError(Exception)` · `PanelNotificationSink(settings, *, fallback, store=None, resolver=None, consult=None, clock=None, publish=None)` · `notify(tenant_id, title, body, *, meta=None)` · `deliver(...) -> DeliveryOutcome`(chat_sink의 dataclass 재사용: campaign_id, status: delivered|skipped|failed, reason, session_id) · `reconcile(normals: list[{tenant_id, campaign_id, anomaly_type}]) -> int` · `summary() -> {delivered, skipped[], failed[]}`. deliver 순서: campaign_id → resolver(fail-closed) → **판정(DB만: ignored→미열람 bell_pending→쿨다운)** → consult(힌트 없으면 consult 먼저 폴백) → INSERT/후속 UPDATE + publish. 후속 경로에서 consult가 normal이면 열린 행을 **즉시 auto_normal로 닫고 publish**(다음 스캔 reconcile 대기 없음). 후속 UPDATE = read_at NULL·payload 교체·followup_count+1·last_notified_at 갱신·created_at 보존. payload = `ConsultResult.to_meta(org_id)` + `campaign_name`·`message` 확장 필드.
- **store 포트(sink가 쓰는 부분)** — `has_ignored(org_id, kind, dedup_key) -> bool` · `open_state(org_id, kind, dedup_key) -> {id, read_at, last_notified_at} | None` · `insert(*, organization_id, project_id, campaign_id, kind, dedup_key, payload, now) -> id`(유니크 충돌 시 `DedupRaceError`) · `followup(notification_id, payload, now)` · `auto_resolve(org_id|None, kind, dedup_keys, now) -> 영향받은 org id 목록`.
- **store(API·consult가 쓰는 부분)** — `list_for_org(org_id, *, project_id=None, unread_only=False, include_resolved=False, limit=50, before=None, before_id=None) -> (items, org전체 unread수)`(정렬 (last_notified_at desc, id desc)·복합 커서 (before, before_id) — 동률 누락 방지, limit 최대 200) · `get(notification_id) -> dict|None` · `mark_read(org_id, ids, now) -> int`(WHERE org 필터 = bulk의 fail-closed — 타 org id는 무효, 404 아님) · `resolve(org_id, notification_id, resolution, now) -> bool` · `claim_consult_session(notification_id, session_id) -> bool`(CAS) · `release_consult_session(notification_id, session_id)`(보상 롤백).
- **broker** — `subscribe(org_id) -> asyncio.Queue(maxsize=8)` · `unsubscribe(org_id, q)` · `publish(org_id)`(가득 차면 신호 드랍 — 무손실). 모듈 전역 `_subscribers: dict[str, set[Queue]]`. 단일 프로세스 전제.
- **스캐너 계약** — 신형은 `(findings, normals)` 튜플 반환. finding meta에 `anomaly_type` 힌트 포함. normals = `[{tenant_id, campaign_id, anomaly_type}]`(성공 조회+정상만 — fail-closed). `run_scan`은 튜플/구형 list 모두 수용, normals 있고 `hasattr(sink, "reconcile")`면 호출. **수동 스캔(`/anomaly/notify-scan`)의 sink 생성도 채널 인지**(panel이면 PanelNotificationSink, 그 외 chat sink 유지 — org reader consult partial 주입 동일, Task 6 Step 4-1).
- **API(`/api/management`)** — `GET /notifications?project_id=&unread_only=&include_resolved=&limit=&before=&before_id=` → `{notifications: [...], unread_count}`(limit은 `Query(50, ge=1, le=200)` 검증) · `POST /notifications/read {ids}` → `{updated}` · `POST /notifications/{id}/resolve {resolution: ignored|actioned}` → `{resolved, resolution}`(404 fail-closed) · `POST /notifications/{id}/consult` → `{status: consult, session_id} | {status: normal, message} | {status: already_resolved, resolution}`(404/503) · `GET /notifications/stream` SSE(`data: {"event": "connected"|"changed"}`, 30초 `: keep-alive`, **`/{id}` 라우트보다 먼저 선언**). 라우터 모듈 seam: `_notification_store()` 팩토리·`_publish_org(org_id)` — 테스트가 monkeypatch.
- **consult_service** — `consult_notification(settings, notification_id, org_id, *, store, chat_store, consult, publish, now=None) -> dict | None`. None=404 · `{status:"unavailable"}`=503 · 나머지 200. 재클릭=이동 전용(재검증 없음, 세션 생존 확인·삭제 시 재실행) · read 동시 마킹(변화 시 publish) · 정상화=auto_normal resolve · CAS 승자만 심기·append 실패 시 release 후 unavailable · **CAS 패자는 알림 재조회로 승자가 확정한 세션을 반환**(find_or_create race 대비, 미확정이면 자기 세션 폴백). `chat_store` 포트: `find_or_create_session(project_id, title)` / `append_consult(session_id, content, meta)` / `session_exists(session_id)`. 세션 제목 `"⚠ 캠페인 이상 알림"`(chat_sink와 동일).
- **채팅 옵션** — `ChatRequest.option_select: dict | None`(core/schemas.py) = `{option_index, action, tool_hint, campaign_id, label}` · `build_option_instruction(sel) -> str`(remediation/context.py — meta 우선 매핑, 타이핑은 기존 recall 폴백) · `_persist(..., option_select=None)` → user_meta["option_select"].
- **설정 키(core/config.py)** — `management_notify_channel: str = "log"`(log|chat|panel — 기존 `management_chat_notify_enabled` bool 제거·이행 노트 필수) · `management_notify_sse_enabled: bool = True` · `management_consult_cooldown_hours`(24, 기존).
- **프론트** — `api.management.notifications.{list, read, resolve, consult}` + `export type ManagementNotification`(api.ts) · `useNotificationStream(enabled, onChange)`(fetch 스트리밍·지수 백오프) · `NotificationBell`(fixed top-3 right-4, org 전체 unread 배지, 패널 열람 시 bulk read) · `NotificationPanel(items, onRefetch, onClose)`(프로젝트 필터·상담하기/무시·타 프로젝트면 `selectProject` 후 `setActiveSessionId`+`setFloatingOpen(true)`) · `RemediationOptionsWidget({options, campaignId, onSelect(text, meta), onEtc})`(meta 동적 렌더 + [기타] 입력창 포커스).

## 태스크 (각 파일이 단독 실행 단위)

| # | 태스크 | 파일 |
|---|---|---|
| 0 | 준비 — dev 머지(0004)·팀 공지 | [task-00-prep.md](2026-07-03-remediation-hybrid-notification/task-00-prep.md) |
| 1 | 모델 + Alembic 0005 (⚠ core/models.py 공통부) | [task-01-model-migration.md](2026-07-03-remediation-hybrid-notification/task-01-model-migration.md) |
| 2 | 설정 일원화 + sink 채널 분기 | [task-02-config-sink-wiring.md](2026-07-03-remediation-hybrid-notification/task-02-config-sink-wiring.md) |
| 3 | SSE 인프로세스 브로커 | [task-03-broker.md](2026-07-03-remediation-hybrid-notification/task-03-broker.md) |
| 4 | PanelNotificationSink 판정표 + reconcile | [task-04-panel-sink.md](2026-07-03-remediation-hybrid-notification/task-04-panel-sink.md) |
| 5 | DbNotificationStore 영속 계층 | [task-05-notification-store.md](2026-07-03-remediation-hybrid-notification/task-05-notification-store.md) |
| 6 | 스캐너 anomaly 힌트 + run_scan reconcile | [task-06-scan-reconcile.md](2026-07-03-remediation-hybrid-notification/task-06-scan-reconcile.md) |
| 7 | 알림 API — 목록·bulk read·resolve | [task-07-notification-api.md](2026-07-03-remediation-hybrid-notification/task-07-notification-api.md) |
| 8 | consult 엔드포인트(상담 진입) | [task-08-consult-endpoint.md](2026-07-03-remediation-hybrid-notification/task-08-consult-endpoint.md) |
| 9 | SSE 스트림 엔드포인트 | [task-09-sse-stream.md](2026-07-03-remediation-hybrid-notification/task-09-sse-stream.md) |
| 10 | ChatRequest.option_select + meta 우선 매핑 (⚠ core/schemas.py 공통부) | [task-10-chat-option-select.md](2026-07-03-remediation-hybrid-notification/task-10-chat-option-select.md) |
| 11 | 프론트 API 클라이언트 + SSE 훅 | [task-11-frontend-api-hook.md](2026-07-03-remediation-hybrid-notification/task-11-frontend-api-hook.md) |
| 12 | 벨·패널 + AppLayout 장착 (⚠ 프론트 공통부) | [task-12-bell-panel.md](2026-07-03-remediation-hybrid-notification/task-12-bell-panel.md) |
| 13 | 옵션 버튼 위젯 + ChatConversation 연결 | [task-13-options-widget.md](2026-07-03-remediation-hybrid-notification/task-13-options-widget.md) |
| 14 | 전체 검증 + 문서 마감 | [task-14-finalize.md](2026-07-03-remediation-hybrid-notification/task-14-finalize.md) |

**의존 순서:** 0 → 1 → 2 → (3, 4) → 5 → 6 → (7, 8, 9) → 10 → 11 → 12 → 13 → 14. Task 4는 store를 fake로 테스트하므로 5보다 먼저 가능(wiring의 panel 분기 실검증은 5 이후). 백엔드(0~10)와 프론트(11~13)는 10 완료 후 병렬 가능.

## 사전 공지 체크리스트 (구현 시작 전)

- [ ] `core/models.py` + Alembic **0005** 신설 (Task 1)
- [ ] `core/schemas.py` ChatRequest 필드 1개 append (Task 10)
- [ ] `AppLayout.tsx` 벨 1줄 추가 — 프론트 담당 (Task 12)
- [ ] `MANAGEMENT_CHAT_NOTIFY_ENABLED` → `MANAGEMENT_NOTIFY_CHANNEL` 이행 (Task 2)

## 후속 과제 (이 계획 범위 밖 — 스펙 근거)

- 옵션 실행 여부의 영속 추적(위젯 체크가 세션 재로드에도 유지) — 1차는 로컬 상태만.
- 패널 프로젝트 필터의 서버 필터 전환 — 1차는 클라이언트 필터(의도된 선택: dedup 설계상 미해결 알림은 캠페인×이상유형당 1건이라 50건 초과가 비정상). API `project_id` 파라미터는 이미 있음.
- SSE 멀티워커 대응(외부 브로커) — 단일 EC2 확정 결정이라 보류.
- `budget_exhausted`·`quality_degraded` 스캔 신호 추가(현재 스캔은 no_delivery만 — 옵션 풀은 이미 존재).
