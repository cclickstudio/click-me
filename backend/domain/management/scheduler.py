# 능동 매니지먼트 스케줄러 — 주기 이상 스캔 → 알림 (APScheduler 인프로세스, 무SQS)
"""기존 in-process asyncio 잡 패턴과 일관(단일 EC2). 기본 off — 운영에서만 켠다.

run_scan은 1회 스캔이고 scanner 주입으로 테스트 가능하다. 기본 스캐너는 보수적으로 빈 결과를
낸다 — detection 파이프라인이 fault 주입형 데모라, 실 캠페인 campaign-queryable 진단이 준비되면
여기 연결한다(seam). 통지는 NotificationSink(기본 로그)로만 나간다.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from core.automation import register_automation
from domain.management.notifications import NotificationSink, build_notification_sink

logger = logging.getLogger("clickme")

_Scanner = Callable[[object], Awaitable[list[dict]]]

# 공용 레지스트리에 매니지먼트 자동화 등록 — gen/sim도 같은 방식으로 붙는다(확장 seam).
register_automation(
    "management",
    "anomaly_scan",
    description="캠페인 게재0·소재피로·성과미달 + 계정 지갑·예산 가드레일 점검(에이전트 판단)",
)


async def _default_scanner(settings) -> list[dict]:
    """기본 스캐너 — 활성 캠페인 룰 점검(A계열: 게재 0 + 소재 피로). 발견분을 통지·기록.

    실측은 live_campaigns(reader)에서 — use_mock이면 mock, 실연동이면 Meta. ROAS 목표 대비 등
    심화 진단은 campaign-queryable 진단 정비 후 확장(seam).
    """
    from domain.management.assistant import tools as live_tools  # noqa: PLC0415
    from domain.management.contracts.policy import FATIGUE_FREQUENCY  # noqa: PLC0415

    data = await live_tools.live_campaigns(settings)
    if data.get("error"):
        return []  # 조회 실패(rate limit 등)는 통지 안 함 — 다음 틱에 재시도
    findings: list[dict] = []
    for c in data.get("campaigns", []):
        name = c.get("name") or c.get("campaign_id", "?")
        if c.get("impressions", 0) == 0:
            findings.append(
                {
                    "tenant_id": "global",
                    "title": f"게재 점검 — {name}",
                    "body": "활성 캠페인인데 노출이 0입니다. 심사·예산·타깃을 점검하세요.",
                    "meta": {"campaign_id": c.get("campaign_id"), "rule": "zero_impressions"},
                }
            )
        if (c.get("frequency") or 0) >= FATIGUE_FREQUENCY:
            findings.append(
                {
                    "tenant_id": "global",
                    "title": f"소재 피로 — {name}",
                    "body": f"빈도 {c.get('frequency')}회 — 도달 피로 구간, 소재 교체 검토.",
                    "meta": {"campaign_id": c.get("campaign_id"), "rule": "creative_fatigue"},
                }
            )
    findings.extend(await _account_rules_scan(settings))
    return findings


async def _account_rules_scan(settings) -> list[dict]:
    """계정 단위 룰(지갑 소진율·월 목표 가드레일) — 조회 실패는 빈 결과(다음 틱 재시도)."""
    import calendar  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from domain.management.contracts.policy import DEFAULT_MONTHLY_TARGET_KRW  # noqa: PLC0415
    from domain.management.wiring import build_reader  # noqa: PLC0415

    try:
        reader = build_reader(settings)
        funding = await reader.get_account_funding()
        month_spent = await reader.get_account_spend("this_month")
    except Exception:  # noqa: BLE001 — rate limit 등 조회 실패는 통지 안 함
        return []
    now = datetime.now(UTC)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    projection = (
        round(month_spent / now.day * days_in_month) if now.day and month_spent else month_spent
    )
    return account_rule_findings(
        spend_cap_krw=funding.spend_cap_krw or 0,
        amount_spent_krw=funding.amount_spent_krw or 0,
        projection_krw=projection or 0,
        target_krw=DEFAULT_MONTHLY_TARGET_KRW,
    )


def account_rule_findings(
    *, spend_cap_krw: int, amount_spent_krw: int, projection_krw: int, target_krw: int
) -> list[dict]:
    """계정 단위 룰 판정(순수 함수) — 지갑 사용률 95/80% + 런레이트의 월 목표 초과.

    금액 원값은 summary에 노출하지 않고 비율만 말한다(기밀 데이터 평문 최소화).
    """
    from domain.management.contracts.policy import (  # noqa: PLC0415
        WALLET_ALERT_PCT,
        WALLET_WARN_PCT,
    )

    findings: list[dict] = []
    if spend_cap_krw > 0:
        pct = round(amount_spent_krw / spend_cap_krw * 100)
        if pct >= WALLET_ALERT_PCT:
            findings.append(
                {
                    "tenant_id": "global",
                    "title": "지갑 거의 소진",
                    "body": f"충전 한도의 {pct}%를 사용했습니다. 충전이 필요해요.",
                    "meta": {"rule": "wallet_depleted", "pct": pct},
                }
            )
        elif pct >= WALLET_WARN_PCT:
            findings.append(
                {
                    "tenant_id": "global",
                    "title": "지갑 소진 주의",
                    "body": f"충전 한도의 {pct}%를 사용했습니다.",
                    "meta": {"rule": "wallet_warning", "pct": pct},
                }
            )
    if target_krw > 0 and projection_krw > target_krw:
        pace = round(projection_krw / target_krw * 100)
        findings.append(
            {
                "tenant_id": "global",
                "title": "월 예산 가드레일",
                "body": f"현재 페이스면 월 목표의 {pace}%까지 소진될 것으로 예상됩니다.",
                "meta": {"rule": "budget_pace_over", "pace_pct": pace},
            }
        )
    return findings


async def _agent_scanner(settings) -> list[dict]:
    """에이전트 판단 스캐너 — 캠페인별 성과 진단(규칙→INCONCLUSIVE시 LLM 재판정) + 결정론 센서.

    _default_scanner(순수 규칙)의 상위호환: 게재0·소재피로는 정책 정본 임계로 결정론 유지하되,
    성과 미달은 diagnose_campaign(에이전트)이 맥락으로 판단한다. 성과 목표(target_roas)가 없으면
    성과 진단은 자동 생략(휴리스틱 금지 — 목표를 지어내지 않는다) → 게재0·피로만.
    조회/조립 실패는 규칙 스캐너로 폴백(지장 없음). 임계·통지·기록 파이프라인은 그대로.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from domain.management.contracts.enums import CampaignState  # noqa: PLC0415
    from domain.management.contracts.policy import FATIGUE_FREQUENCY  # noqa: PLC0415
    from domain.management.detection.agentic_scan import diagnose_campaign  # noqa: PLC0415
    from domain.management.wiring import build_reader  # noqa: PLC0415

    try:
        reader = build_reader(settings)
        infos = await reader.list_campaigns()
    except Exception as exc:  # noqa: BLE001 — 조회/조립 실패 → 규칙 스캐너로 폴백(지장 없음)
        logger.warning("management 에이전트 스캔 준비 실패 → 규칙 폴백: %s", exc)
        try:
            return await _default_scanner(settings)
        except Exception as exc2:  # noqa: BLE001 — 폴백까지 실패해도 스캐너는 raise하지 않음
            logger.warning("management 규칙 폴백도 실패(빈 결과): %s", exc2)
            return []

    now = datetime.now(UTC)
    # 성과 미달 판정 목표 — 설정에 기본 목표가 있을 때만(없으면 None → 성과 진단 생략).
    target_roas = getattr(settings, "management_default_target_roas", None)
    findings: list[dict] = []
    for c in infos:
        name = c.name or c.campaign_id
        is_active = c.state == CampaignState.ACTIVE
        try:
            m = await reader.get_metrics(c.campaign_id, now)
        except Exception:  # noqa: BLE001 — 캠페인 1건 실패가 전체 스캔을 막지 않게
            continue
        # 결정론 센서 — 게재 0(활성인데 노출 없음): 값싼 프리필터.
        if is_active and (m.impressions or 0) == 0:
            findings.append(
                {
                    "tenant_id": "global",
                    "title": f"게재 점검 — {name}",
                    "body": "활성 캠페인인데 노출이 0입니다. 심사·예산·타깃을 점검하세요.",
                    "meta": {"campaign_id": c.campaign_id, "rule": "zero_impressions"},
                }
            )
        # 에이전트 판단 — 성과 미달(목표 없으면 diagnose_campaign이 None 반환 → 생략).
        dx = await diagnose_campaign(
            reader, settings, c.campaign_id, {"roas": m.roas, "target_roas": target_roas}, m.as_of
        )
        if dx:
            findings.append(
                {
                    "tenant_id": "global",
                    "title": f"성과 진단 — {name}",
                    "body": dx.get("hypothesis") or "성과 이상 신호가 감지됐어요.",
                    "meta": {
                        "campaign_id": c.campaign_id,
                        "rule": dx.get("anomaly_type") or "performance_anomaly",
                        "confidence": dx.get("confidence"),
                        "source": dx.get("source"),
                        "status": dx.get("status"),
                    },
                }
            )
        # 결정론 센서 — 소재 피로(최근 7일 빈도, 정책 임계). live_campaigns엔 빈도가 없어
        # 여기서 실측(reader)으로 잡는다.
        if is_active:
            try:
                wk = await reader.get_metrics(c.campaign_id, now, date_preset="last_7d")
                freq = wk.frequency or 0.0
            except Exception:  # noqa: BLE001 — 피로 신호 실패는 조용히 건너뜀
                freq = 0.0
            if freq >= FATIGUE_FREQUENCY:
                findings.append(
                    {
                        "tenant_id": "global",
                        "title": f"소재 피로 — {name}",
                        "body": f"빈도 {freq:.1f}회 — 도달 피로 구간, 소재 교체 검토.",
                        "meta": {"campaign_id": c.campaign_id, "rule": "creative_fatigue"},
                    }
                )
    findings.extend(await _account_rules_scan(settings))
    return findings


async def record_finding(finding: dict) -> None:
    """자동 점검 발견 1건을 기록(best-effort) — 두 저장소.

    ① automation_runs(운영/프론트 조회): 프로젝트 귀속 안 돼도 남긴다(dedup으로 재통지 방지).
    ② chat_execution_history(롱텀 메모리): 캠페인→프로젝트 역추적이 될 때만(성공 수행만).
    """
    from core.automation import record_automation_run  # noqa: PLC0415
    from core.execution_log import record_execution  # noqa: PLC0415
    from domain.management.history_link import resolve_project_id  # noqa: PLC0415

    meta = finding.get("meta") or {}
    cid = meta.get("campaign_id")
    rule = meta.get("rule", "auto_scan_alert")
    project_id = await resolve_project_id([cid] if cid else [])

    # ① 운영 저장소 — 프론트 반영용(프로젝트 없어도 남김).
    await record_automation_run(
        domain="management",
        job_name=rule,
        title=finding.get("title", ""),
        body=finding.get("body", ""),
        project_id=project_id,
        payload={"actor": "auto", **meta},
        suggested_action=meta.get("suggested_action"),
        dedup_key=f"{cid}:{rule}" if cid else None,
    )

    # ② 롱텀 메모리 — 프로젝트 귀속(성공 수행)만.
    if project_id is None:
        return
    summary = f"자동 점검 {finding.get('title', '')} {finding.get('body', '')}".strip()[:500]
    await record_execution(
        project_id,
        "management",
        rule,
        summary,
        payload={"actor": "auto", **meta},
    )


async def run_scan(
    settings,
    sink: NotificationSink,
    *,
    scanner: _Scanner | None = None,
    recorder: Callable[[dict], Awaitable[None]] | None = None,
) -> int:
    """이상 스캔 1회 → 발견분을 sink로 통지 + recorder로 롱텀 메모리 기록. 통지 건수 반환.

    recorder 기본 None — 테스트·수동 호출은 DB 없이 hermetic. 스케줄러 잡만 record_finding 주입.
    """
    scan = scanner or _default_scanner
    findings = await scan(settings)
    for f in findings:
        await sink.notify(
            f.get("tenant_id", "global"),
            f.get("title", "anomaly"),
            f.get("body", ""),
            meta=f.get("meta"),
        )
        if recorder is not None:
            try:
                await recorder(f)
            except Exception as exc:  # noqa: BLE001 — 기록 실패가 스캔을 막지 않게
                logger.warning("management 스캔 기록 실패(무시): %s", exc)
    if findings:
        logger.info("management 스캔 — %d건 통지", len(findings))
    return len(findings)


_scheduler = None


def _scanner_for(settings) -> _Scanner | None:
    """설정 모드에 따른 스캐너 선택 — 'agent'면 에이전트 판단, 그 외(기본 'rule')는 규칙.

    None을 반환하면 run_scan이 _default_scanner(순수 규칙)를 쓴다.
    """
    mode = getattr(settings, "management_scanner_mode", "rule")
    return _agent_scanner if mode == "agent" else None


def start_scheduler(settings) -> bool:
    """settings.management_scheduler_enabled일 때만 기동. 기본 off → 테스트/CI/dev 안전.

    기동했으면 True, (비활성이라) 건너뛰었으면 False.
    """
    global _scheduler  # noqa: PLW0603
    if not getattr(settings, "management_scheduler_enabled", False):
        return False
    if _scheduler is not None:
        return True
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: PLC0415

    sink = build_notification_sink(settings)
    interval = getattr(settings, "management_scan_interval_minutes", 60)
    scanner = _scanner_for(settings)  # 모드에 따라 에이전트 판단 스캐너 또는 규칙(None)

    async def _job() -> None:
        try:
            await run_scan(settings, sink, scanner=scanner, recorder=record_finding)
        except Exception as exc:  # noqa: BLE001 — 잡 실패가 스케줄러를 죽이지 않게
            logger.warning("management 스캔 실패(무시): %s", exc)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_job, "interval", minutes=interval, id="mgmt-scan")
    _scheduler.start()
    mode = getattr(settings, "management_scanner_mode", "rule")
    logger.info("management 스케줄러 기동 — %d분 간격 · 스캐너=%s", interval, mode)
    return True
