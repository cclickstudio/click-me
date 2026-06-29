# 채팅 기반 프로젝트 리포트 — 시뮬 집계를 HTML로 만들고 Playwright로 PDF 렌더(T13)
"""채팅에서 '이번 달 시뮬 결과 PDF로 뽑아줘'를 트리거하면 호출된다.

기존 PDF 파이프라인(Playwright Chromium 렌더)을 같은 방식으로 재사용한다. Chromium이 없으면
HTML 바이트로 폴백해 다운로드는 항상 가능하게 한다(best-effort).
"""

from __future__ import annotations

import asyncio
from html import escape

from domain.simulation.assistant.tools import fetch_project_summary

_PERIOD_LABEL = {"month": "이번 달", "all": "전체 기간"}


def _build_report_html(summary: dict, period: str) -> str:
    """프로젝트 시뮬 집계 → 간단한 스타일 HTML 리포트."""
    plabel = _PERIOD_LABEL.get(period, period)
    if summary.get("count", 0) == 0:
        body = (
            f"<p style='color:#64748b'>{escape(summary.get('note', '집계할 결과가 없어요.'))}</p>"
        )
    else:
        best = summary.get("best") or {}
        worst = summary.get("worst") or {}
        cnt = summary["count"]
        avg = summary["avg_purchase_intent"]
        bt, bv = escape(str(best.get("title", "—"))), best.get("purchase_intent", "—")
        wt, wv = escape(str(worst.get("title", "—"))), worst.get("purchase_intent", "—")
        body = (
            '<div class="grid">'
            f'<div class="card"><div class="label">분석한 시뮬</div>'
            f'<div class="val">{cnt}건</div></div>'
            f'<div class="card"><div class="label">평균 구매의도</div>'
            f'<div class="val">{avg}/5</div></div>'
            "</div>"
            "<h2>최고 / 최저</h2>"
            "<table>"
            "<tr><th>구분</th><th>제목</th><th>구매의도</th></tr>"
            f"<tr><td>최고</td><td>{bt}</td><td>{bv}/5</td></tr>"
            f"<tr><td>최저</td><td>{wt}</td><td>{wv}/5</td></tr>"
            "</table>"
        )
    css = (
        "body{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;"
        "padding:32px;color:#191F28;background:#fff;}"
        "h1{font-size:24px;margin-bottom:4px;}"
        ".sub{color:#8B95A1;font-size:13px;margin-bottom:24px;}"
        ".grid{display:flex;gap:12px;margin-bottom:20px;}"
        ".card{flex:1;border:1px solid #E5E8EB;border-radius:12px;padding:16px;}"
        ".label{color:#8B95A1;font-size:12px;}"
        ".val{font-size:26px;font-weight:800;margin-top:6px;}"
        "h2{font-size:16px;margin:20px 0 8px;}"
        "table{width:100%;border-collapse:collapse;font-size:14px;}"
        "th,td{text-align:left;padding:8px;border-bottom:1px solid #F2F4F6;}"
        "th{color:#8B95A1;font-weight:600;}"
    )
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f"<style>{css}</style></head><body>"
        "<h1>광고 시뮬레이션 리포트</h1>"
        f'<div class="sub">{escape(plabel)} · ClickMe 프로젝트 요약</div>'
        f"{body}</body></html>"
    )


def _html_to_pdf(html: str) -> bytes:
    """HTML → Playwright Chromium PDF(동기). 라우터에서 to_thread로 호출."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            pdf = page.pdf(
                format="A4", print_background=True, margin={"top": "10mm", "bottom": "10mm"}
            )
        finally:
            browser.close()
    return pdf


async def generate_project_report(
    project_id: str | None, period: str = "month"
) -> tuple[bytes, str, str]:
    """프로젝트 리포트 생성 → (바이트, media_type, 파일명). Chromium 없으면 HTML로 폴백."""
    summary = await fetch_project_summary(project_id or "", period)
    html = _build_report_html(summary, period)
    try:
        pdf = await asyncio.to_thread(_html_to_pdf, html)
        return pdf, "application/pdf", "clickme_report.pdf"
    except Exception as exc:  # noqa: BLE001 — Chromium 미설치 등 → HTML 다운로드로 폴백
        print(f"[chat] report pdf fallback(html): {exc!r}")
        return html.encode("utf-8"), "text/html; charset=utf-8", "clickme_report.html"
