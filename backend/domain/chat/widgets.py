# 채팅 위젯 신호 — 프론트(meta.widget)가 의존하는 위젯들의 단일 출처(순수 함수)
"""tool/콜백이 상태에 적재할 `{"widget": ..., "source": ...}` 조각을 만든다.

프론트 ChatConversation은 meta.widget.type으로 분기해 폼·목록·카드를 렌더한다.
형태는 기존 orchestrator.py·deep_agent.py가 내보내던 것과 바이트 동일해야 한다(계약).
source는 프론트 배지·chat.py 카드 게이트 분기 키 — 위젯별 고정값을 함께 싣는다.
"""

from __future__ import annotations

# source 값 — 프론트/백엔드가 분기에 사용(고정).
SIMULATION = "simulation"
GENERATOR = "generator"
DEEP_AGENT = "deep-agent"


def sim_form(data: dict) -> dict:
    """시뮬 입력 폼 — data={ad_title, ad_content, product_category, ad_objective}."""
    return {"widget": {"type": "sim_form", "data": data}, "source": SIMULATION}


def gen_form(data: dict) -> dict:
    """생성 입력 폼 — product_name·product_description·target_audience·campaign_objective."""
    return {"widget": {"type": "gen_form", "data": data}, "source": GENERATOR}


def sim_list(items: list, mode: str = "read") -> dict:
    """시뮬 목록 — mode=read(보기)|select(개선 선택)|compare(2개 비교)."""
    return {
        "widget": {"type": "sim_list", "mode": mode, "data": {"items": items}},
        "source": SIMULATION,
    }


def gen_list(items: list, mode: str = "read") -> dict:
    """생성 목록 — mode=read|select."""
    return {
        "widget": {"type": "gen_list", "mode": mode, "data": {"items": items}},
        "source": GENERATOR,
    }


def gen_loop(loop_id: str, stream_url: str) -> dict:
    """자동 개선 루프 진행 카드 — 반복별 품질점수를 stream_url(SSE)로 관찰."""
    return {
        "widget": {"type": "gen_loop", "data": {"loop_id": loop_id, "stream_url": stream_url}},
        "source": GENERATOR,
    }


def gen_progress(generation_id: str, stream_url: str) -> dict:
    """단발 생성 진행 카드 — 채팅 즉시 실행 시 진행률·완료를 stream_url(SSE)로 관찰."""
    return {
        "widget": {
            "type": "gen_progress",
            "data": {"generation_id": generation_id, "stream_url": stream_url},
        },
        "source": GENERATOR,
    }


def report_ready(project_id: str | None, period: str) -> dict:
    """리포트 다운로드 버튼 — 실제 파일은 /api/chat/report. period=month|all."""
    return {
        "widget": {"type": "report_ready", "data": {"project_id": project_id, "period": period}},
        "source": SIMULATION,
    }


def batch_sim_form(prefill: dict | None = None) -> dict:
    """배치 시뮬 입력 폼(광고 2~4개 비교).

    prefill={ads:[{ad_title, ad_content, product_category}, ...]} 선택 — 제너레이터 후보를
    A/B로 프리필할 때 사용. 없으면 빈 폼(수동 입력, 기존 동작 불변).
    """
    widget: dict = {"type": "batch_sim_form"}
    if prefill:
        widget["data"] = prefill
    return {"widget": widget, "source": SIMULATION}


def create_campaign(prefill: dict) -> dict:
    """새 캠페인 생성 폼 — prefill={name?, objective?, total_budget_krw?}. source 고정."""
    return {
        "widget": {"type": "create_campaign", "data": {"prefill": prefill}},
        "source": DEEP_AGENT,
    }


def exec_from_sim(data: dict) -> dict:
    """시뮬 결과 집행 카드 — data={simulation_id, default_name, click_intent_rate,
    rejection_rate, link_url?, daily_budget_krw?, start_date?, end_date?}. source 고정."""
    return {"widget": {"type": "exec_from_sim", "data": data}, "source": DEEP_AGENT}


def campaign_action(action: dict) -> dict:
    """캠페인 조치 카드 — action={action, campaign_id?, campaign_name?, …}. source 고정."""
    return {
        "widget": {"type": "campaign_action", "data": {"action": action}},
        "source": DEEP_AGENT,
    }


def replace_creative_form(campaign_id: str = "", campaign_name: str = "") -> dict:
    """소재 교체 후보 picker 카드 — data={campaign_id, campaign_name}. source 고정.

    campaign_id/campaign_name 둘 다 비어도 카드가 캠페인 picker를 띄운다(빈 값 허용).
    """
    return {
        "widget": {
            "type": "replace_creative",
            "data": {"campaign_id": campaign_id, "campaign_name": campaign_name},
        },
        "source": DEEP_AGENT,
    }


def rebalance_action(proposal: dict) -> dict:
    """리밸런싱(transfer) 적용 확인 카드 — proposal=insights kind=transfer 제안 그대로.

    from/to 2개 payload라 campaign_action(단일 캠페인)과 분리한다. source 고정.
    """
    return {
        "widget": {"type": "rebalance_action", "data": {"proposal": proposal}},
        "source": DEEP_AGENT,
    }
