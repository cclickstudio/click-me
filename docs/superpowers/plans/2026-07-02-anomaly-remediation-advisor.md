# 이상 감지 선제 제안(remediation advisor) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. **각 태스크는 하위 디렉터리의 개별 md 파일이 단독 실행 단위다** — 서브에이전트에게 해당 태스크 파일 + 이 인덱스의 "계약 스냅샷"만 주면 된다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이상 감지 시 에이전트가 채팅 벨(N5)로 먼저 사용자에게 묻고("어떻게 하실래요?") 조치 옵션을 제안하는 경로 신설. 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`.

**Architecture:** `domain/management/remediation/`(🅱 소유)에 advisor(진단 재검증+옵션)·chat_sink(세션 심기+스팸 방지)·resolver(캠페인→프로젝트)를 신설. 기존 코드 터치는 3곳뿐 — `notifications.py` sink 분기 1줄, `chat.py` 컨텍스트 주입 몇 줄, `subagent_tools.py` 도구 1개 append. detection·scheduler·프론트 무변경.

**Tech Stack:** FastAPI + SQLAlchemy(async) + pydantic v2 + pytest(asyncio). 커밋 컨벤션 `타입: 한국어 설명`. 모든 새 .py 첫 줄에 한국어 헤더 주석.

**실행 규칙:**
- 모든 명령은 `cd backend` 후 실행. 테스트: `uv run pytest <path> -v`.
- 각 태스크 커밋 전 `uv run ruff format . && uv run ruff check . --fix`.
- 타임스탬프는 UTC-aware(`datetime.now(UTC)`), naive 금지.
- 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지 — 읽기(import)만.

---

## 계약 스냅샷 (태스크 간 시그니처 정본)

서브에이전트는 자기 태스크 파일 + 이 섹션만으로 작업한다. 태스크 파일과 어긋나면 여기가 정본.

- **contracts** — `CONSULT_SCHEMA_VERSION = 1` · `ALLOWED_TOOL_HINTS = {run_generation, run_simulation, manage_campaign}` · `OptionKind(platform|spend|observe)` · `RemediationAction(REGENERATE_CREATIVE|VERIFY_SIM|PAUSE_CAMPAIGN|INCREASE_BUDGET|DECREASE_BUDGET|OBSERVE)` · `RemediationOption(index>=1, kind, action, label, rationale="", tool_hint=None)` · `ConsultResult(status: "anomaly"|"normal", campaign_id, campaign_name="", anomaly_type="", confidence=0.0, diagnosed_at="", message="", options=[])` — normal은 options 금지, anomaly는 options>=1+anomaly_type 필수, index 1부터 연속 · `ConsultResult.to_meta(org_id=None) -> dict(kind="remediation_consult", schema_version, campaign_id, org_id, diagnosed_at, anomaly_type, confidence, options[])`
- **advisor** — `consult(settings, campaign_id, *, reader=None, now=None) -> ConsultResult | None`(조회 실패=None) · `build_options(anomaly_type) -> list[RemediationOption]` · `find_campaign_id(settings, name, *, reader=None) -> str | None` · `OPTION_POOLS: dict[str, list]` · LLM은 `_polish(settings, intro)`로 인트로만, 옵션 블록은 `_render_options`(결정론) 고정
- **resolver** — `resolve_project(campaign_id, *, expected_org_id=None, session_factory=None) -> tuple[project_id, org_id] | None` — expected_org 불일치 시 None(fail-closed)
- **chat_sink** — `ChatNotificationSink(settings, *, fallback, store=None, resolver=None, consult=None, clock=None)` · `notify(tenant_id, title, body, *, meta=None) -> None` · `deliver(...) -> DeliveryOutcome(campaign_id, status: delivered|skipped|failed, reason=None, session_id=None)` · `summary() -> {delivered: int, skipped: [{campaign_id, reason}], failed: [...]}` · 모듈 레벨 `_delivery_locks` · store 포트: `find_or_create_session(project_id, title) -> (session_id, last_read_at)` / `latest_consult_at(session_id, campaign_id, anomaly_type) -> datetime|None` / `append_consult(session_id, content, meta)`
- **context** — `pick_consult_context(messages: list[(meta|None, created_at)] 최신순, *, now, ttl_hours, recent_k=10) -> str | None` · `recall_consult_context(session_id, settings) -> str | None`
- **설정 키(전부 getattr 기본값, core 무변경)** — `management_chat_notify_enabled`(False) · `management_consult_cooldown_hours`(24) · `management_consult_context_ttl_hours`(24) · `management_scan_manual_cooldown_seconds`(60)

## 태스크 (각 파일이 단독 실행 단위)

| # | 태스크 | 파일 |
|---|---|---|
| 1 | 고정 계약 — `remediation/contracts.py` | [task-01-contracts.md](2026-07-02-anomaly-remediation-advisor/task-01-contracts.md) |
| 2 | 두뇌 — `remediation/advisor.py` | [task-02-advisor.md](2026-07-02-anomaly-remediation-advisor/task-02-advisor.md) |
| 3 | 캠페인→프로젝트 resolver — `remediation/resolver.py` | [task-03-resolver.md](2026-07-02-anomaly-remediation-advisor/task-03-resolver.md) |
| 4 | 채팅 알림 sink — `remediation/chat_sink.py` | [task-04-chat-sink.md](2026-07-02-anomaly-remediation-advisor/task-04-chat-sink.md) |
| 5 | seam 분기 — `notifications.py` (⚠ 공통 성격 파일, 사전 공지) | [task-05-sink-wiring.md](2026-07-02-anomaly-remediation-advisor/task-05-sink-wiring.md) |
| 6 | 컨텍스트 왕복 — `remediation/context.py` + `chat.py` 주입 | [task-06-context-injection.md](2026-07-02-anomaly-remediation-advisor/task-06-context-injection.md) |
| 7 | 보조 진입 — `consult_anomaly` 도구 (⚠ 공통부, 사전 공지) | [task-07-consult-tool.md](2026-07-02-anomaly-remediation-advisor/task-07-consult-tool.md) |
| 8 | 수동 스캔 엔드포인트 + 보호장치 — `management.py` | [task-08-notify-scan-endpoint.md](2026-07-02-anomaly-remediation-advisor/task-08-notify-scan-endpoint.md) |
| 9 | 스펙 정합 + 전체 검증 | [task-09-finalize.md](2026-07-02-anomaly-remediation-advisor/task-09-finalize.md) |

---

## 사전 공지 체크리스트 (구현 시작 전)

- [ ] 챗 담당: `subagent_tools.py` 도구 1개 append + `chat.py` 주입 몇 줄 (Task 6·7)
- [ ] 🅰: `notifications.py` `build_notification_sink` 분기 1줄 (Task 5)

## 후속 PR 후보 (이 계획 범위 밖)

- 캠페인→프로젝트 체인 2(생성 제안 링크) — campaign_id↔proposal 연계 저장 위치 확인 후.
- 구경로(`/regenerate*`·규칙표·selection) 사용처 재확인 후 삭제 PR.
- 체크박스 명시 확인 UI(v2) · org 공용 관리 세션(프론트 org-wide 폴링 전환 시).
