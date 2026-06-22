# 조각 11 리포트 → PDF. Tailwind 대시보드 HTML을 Playwright(headless Chromium)로 렌더(서버 사이드).
#
# 프론트 html2pdf.js(클라이언트 캡처) 아님 — 서버 Chromium이 HTML을 PDF로 인쇄한다.
# 디자인: Tailwind Play CDN · grid 레이아웃 · 섹션별 카드 분리 · 상단 KPI 카드 strip · 강한 색 대비.
# 비전문가도 읽도록 모든 수치에 쉬운 해설을 붙인다. _build_html은 순수 함수(테스트·디버그용).
from __future__ import annotations

import logging
from html import escape

logger = logging.getLogger("clickme")

# ── 팔레트(강한 대비) ──
_BLUE, _INDIGO, _TEAL, _GREEN, _AMBER, _RED, _SLATE = (
    "#2563EB",
    "#4F46E5",
    "#0D9488",
    "#10B981",
    "#F59E0B",
    "#EF4444",
    "#64748B",
)

_AISAS_KO = {
    "attention": "주목",
    "interest": "흥미",
    "search": "탐색",
    "action": "행동",
    "share": "공유",
}
_EMOTION_KO = {
    "curiosity": "호기심",
    "delight": "만족",
    "empathy": "공감",
    "trust": "신뢰",
    "indifference": "무관심",
    "annoyance": "거부감",
    "distrust": "불신",
    "other": "기타",
}
_REJECTION_KO = {
    "irrelevant": "나와 무관",
    "offensive": "불쾌함",
    "overpriced": "비쌈",
    "overpromise": "과장된 표현",
    "distrust": "브랜드 불신",
    "ad_fatigue": "광고 거부감",
    "other": "기타",
}
_RUBRIC_KO = {
    "hook": "훅(첫 3초)",
    "message_clarity": "메시지 명료성",
    "message_alignment": "메시지 정합",
    "usp": "USP 전달",
    "visual_copy_fit": "비주얼-카피 정합",
    "cta_clarity": "행동 유도(CTA)",
    "target_fit": "타깃 적합성",
    "brand_memory": "브랜드 기억도",
    "category_alignment": "카테고리 정합",
    "objective_alignment": "목표 정합",
}
_STANCE = {
    "positive": (_GREEN, "긍정"),
    "neutral": (_SLATE, "중립"),
    "negative": (_RED, "부정"),
}
_GENDER_KO = {"M": "남성", "F": "여성"}

# 도넛 세그먼트 구분색(순환) — 인원 비중을 색으로 구분(클릭의향은 범례 텍스트로).
# 클릭의향 신호색을 쓰면 표본 적은 셀이 전부 회색이 돼 구분이 안 되므로 구분 팔레트 사용.
_DONUT_PALETTE = (
    "#3182F6",
    "#F59E0B",
    "#10B981",
    "#8B5CF6",
    "#EC4899",
    "#14B8A6",
    "#EF4444",
    "#64748B",
)

_CARD = "bg-white rounded-2xl border border-slate-200 shadow-sm break-inside-avoid"


def _pct(x) -> str:
    try:
        return f"{(x or 0) * 100:.0f}%"
    except (TypeError, ValueError):
        return "0%"


def _n(x) -> int:
    try:
        return round((x or 0) * 100)
    except (TypeError, ValueError):
        return 0


def _ival(d: dict, key: int, default: int = 0) -> int:
    return int(d.get(key, d.get(str(key), default)))


def _signal(score: float) -> str:
    return _GREEN if score >= 70 else _AMBER if score >= 50 else _RED


def _grade(s: float) -> tuple[str, str]:
    if s >= 80:
        return "A", "매우 좋음"
    if s >= 70:
        return "B", "좋음"
    if s >= 60:
        return "C", "보통"
    if s >= 50:
        return "D", "아쉬움"
    return "E", "재검토"


def _overall(kpi: dict, rubric: list) -> int:
    parts = [
        kpi.get("click_intent_rate", 0) or 0,
        (kpi.get("purchase_intent", 0) or 0) / 5,
        (kpi.get("trust_avg", 0) or 0) / 5,
        1 - (kpi.get("rejection_rate", 0) or 0),
        kpi.get("brand_recognition_rate", 0) or 0,
    ]
    if rubric:
        parts.append(sum((s.get("score", 0) or 0) for s in rubric) / (len(rubric) * 100))
    return round(sum(parts) / len(parts) * 100)


def _verdict(cir: float, rej: float) -> tuple[str, str, str]:
    if rej >= 0.4 or cir < 0.05:
        return (
            "재제작 권장",
            _RED,
            "거부 반응이 크거나 클릭으로 잘 이어지지 않아, 지금 그대로 내보내기엔 무리가 있어요.",
        )
    if cir >= 0.2 and rej < 0.2:
        return ("집행 권장", _GREEN, "전반적으로 반응이 좋아 지금 내보내도 큰 무리가 없어요.")
    return (
        "조건부 집행 권장",
        _AMBER,
        "가능성은 보이지만, '아쉬운 점'을 손보고 내보내는 걸 권해요.",
    )


def _bar(label: str, ratio: float, disp: str, color: str = _BLUE) -> str:
    w = max(0.0, min(1.0, ratio)) * 100
    return (
        '<div class="flex items-center gap-3 my-[5px]">'
        f'<span class="w-20 text-[11px] text-slate-700 shrink-0">{escape(label)}</span>'
        '<div class="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">'
        f'<div class="h-full rounded-full" style="width:{w:.1f}%;background:{color}"></div></div>'
        f'<span class="w-[78px] text-right text-[10px] text-slate-500 shrink-0">{escape(disp)}</span>'
        "</div>"
    )


def _kpi_card(value: str, label: str, exp: str, color: str) -> str:
    return (
        '<div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 border-t-4" '
        f'style="border-top-color:{color}">'
        f'<div class="text-[11px] font-bold text-slate-500">{escape(label)}</div>'
        f'<div class="text-[28px] font-extrabold leading-tight mt-1" style="color:{color}">'
        f"{escape(value)}</div>"
        f'<div class="text-[9.5px] text-slate-400 mt-1 leading-snug">{escape(exp)}</div></div>'
    )


def _section(num: str, title: str, color: str, body: str, *, tip: str = "") -> str:
    tip_html = (
        (
            f'<p class="text-[11px] leading-relaxed text-slate-500 bg-slate-50 '
            f'rounded-lg px-3 py-2 mb-3">{tip}</p>'
        )
        if tip
        else ""
    )
    num_html = (
        (
            f'<span class="w-7 h-7 rounded-lg text-white text-[12px] font-bold '
            f'grid place-items-center" style="background:{color}">{num}</span>'
        )
        if num
        else (
            f'<span class="w-1.5 h-5 rounded-full inline-block" style="background:{color}"></span>'
        )
    )
    return (
        f'<section class="{_CARD} p-5">'
        f'<div class="flex items-center gap-2.5 mb-1">{num_html}'
        f'<h2 class="text-[15px] font-bold text-slate-800">{escape(title)}</h2></div>'
        f"{tip_html}{body}</section>"
    )


# ── ReportView 신규 섹션 빌더(화면 SimulationReportView와 같은 데이터·구성) ──


def _objective_fit_block(of: dict) -> str:
    """캠페인 목표 달성 가능성 — 결정권자 1순위 판정(기존 PDF서 통째로 누락이던 것)."""
    grade = str(of.get("grade") or "")
    color = _GREEN if grade == "높음" else _AMBER if grade == "보통" else _RED
    score = of.get("score") or 0
    bars = "".join(
        _bar(
            str(c.get("label", "")),
            c.get("value") or 0,
            f"{_n(c.get('value'))}% ·가중 {_n(c.get('weight'))}%",
            _INDIGO,
        )
        for c in (of.get("contributions") or [])
    )
    body = (
        '<div class="flex justify-between items-end mb-2">'
        f'<span class="text-[12px] text-slate-600">목표 — {escape(str(of.get("objective") or "-"))}</span>'
        f'<span class="text-[24px] font-extrabold" style="color:{color}">{escape(grade)}'
        f'<span class="text-[11px] text-slate-400 font-normal ml-1">지수 {score}/100</span></span></div>'
        '<div class="h-2 rounded-full bg-slate-100 overflow-hidden mb-3">'
        f'<div class="h-full rounded-full" style="width:{score}%;background:{color}"></div></div>'
        f'<p class="text-[11.5px] text-slate-600 leading-relaxed mb-2">'
        f"{escape(str(of.get('rationale') or ''))}</p>{bars}"
    )
    if of.get("low_confidence"):
        body += '<p class="text-[10px] text-amber-600 mt-1">⚠ 표본이 적어 신뢰가 낮습니다.</p>'
    return _section(
        "",
        "캠페인 목표 달성 가능성",
        color,
        body,
        tip="결정권자가 가장 먼저 보는 판정 — 시뮬 신호 기반 상대 지수예요(실측 아님, exploratory).",
    )


def _confidence_block(c: dict) -> str:
    """전 섹션 공통 신뢰 배지 — 과신 방지(실측 환산 금지 문구 포함)."""
    label, col = {"high": ("신뢰 높음", _GREEN), "medium": ("신뢰 보통", _AMBER)}.get(
        str(c.get("level")), ("신뢰 낮음", _RED)
    )
    warns = "".join(
        f'<li class="text-[10px] text-slate-500 leading-relaxed">· {escape(str(w))}</li>'
        for w in (c.get("warnings") or [])
    )
    body = (
        '<div class="flex flex-wrap items-center gap-3 text-[11px]">'
        f'<span class="font-bold" style="color:{col}">● {label}</span>'
        f'<span class="text-slate-500">유효표본 {c.get("effective_n", 0)} / 총 '
        f"{c.get('total_n', 0)}명</span>"
        f'<span class="text-slate-500">신뢰구간 폭 {_pct(c.get("ci_width"))}</span></div>'
        f'<ul class="mt-1.5 space-y-0.5">{warns}</ul>'
    )
    return _section("", "신뢰도 안내", _SLATE, body)


def _segment_block(segs: list, num: str = "") -> str:
    """연령대×성별 세그먼트 — '누구에게 통하나'(우리 최대 차별점).

    표본이 작은 셀(유효표본 10 미만)은 1명짜리 100% 같은 과신을 막으려 비율을 색으로 단언하지
    않고 회색 처리한다. 인원 많은 셀부터 정렬하고, '얇음' 표시는 행 도배 대신 하단 범례 한 줄로.
    """
    ordered = sorted(segs, key=lambda s: s.get("n") or 0, reverse=True)
    has_thin = any(s.get("low_confidence") for s in ordered)
    rows = []
    for s in ordered:
        cir = s.get("click_intent_rate") or 0
        thin = bool(s.get("low_confidence"))
        # 얇은 셀은 비율을 색으로 단언하지 않는다(개별 셀 과신 방지)
        col = _SLATE if thin else (_GREEN if cir >= 0.3 else _AMBER if cir >= 0.15 else _RED)
        name_cls = "text-slate-400" if thin else "text-slate-700"
        mark = ' <span class="text-[9px] text-slate-300">ⓘ</span>' if thin else ""
        rows.append(
            '<tr class="border-t border-slate-100">'
            f'<td class="py-1.5 pr-2 {name_cls}">{escape(str(s.get("age_band", "")))} '
            f"{escape(_GENDER_KO.get(s.get('gender'), str(s.get('gender', ''))))}{mark}</td>"
            f'<td class="text-right px-2 text-slate-400">{s.get("n", 0)}</td>'
            f'<td class="text-right px-2 font-bold" style="color:{col}">{_pct(cir)}</td>'
            f'<td class="text-right px-2 text-slate-500">{(s.get("purchase_intent") or 0):.1f}</td>'
            f'<td class="text-right px-2 text-slate-500">{(s.get("trust_avg") or 0):.1f}</td>'
            f'<td class="text-right pl-2 text-slate-500">{_pct(s.get("rejection_rate"))}</td></tr>'
        )
    legend = (
        '<p class="text-[9.5px] text-slate-400 mt-2">'
        "ⓘ 회색 셀은 유효표본 10명 미만 — 비율은 경향 참고용이에요(개별 셀 단언 금지).</p>"
        if has_thin
        else ""
    )
    table = (
        '<table class="w-full text-[10.5px] border-collapse"><thead>'
        '<tr class="text-slate-400"><th class="text-left font-medium py-1 pr-2">세그먼트</th>'
        '<th class="text-right font-medium px-2">인원</th>'
        '<th class="text-right font-medium px-2">클릭 의향</th>'
        '<th class="text-right font-medium px-2">구매(5)</th>'
        '<th class="text-right font-medium px-2">신뢰(5)</th>'
        '<th class="text-right font-medium pl-2">거부율</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        + legend
    )
    # 도넛 — 조각 크기=인원 비중, 색=세그먼트 구분(클릭의향은 범례 텍스트로).
    total_seg = sum((s.get("n") or 0) for s in ordered) or 1
    stops, acc, legend_rows = [], 0.0, []
    for i, s in enumerate(ordered):
        n = s.get("n") or 0
        if n <= 0:
            continue
        cir = s.get("click_intent_rate") or 0
        col = _DONUT_PALETTE[i % len(_DONUT_PALETTE)]
        start = acc * 360
        acc += n / total_seg
        stops.append(f"{col} {start:.1f}deg {acc * 360:.1f}deg")
        nm = (
            f"{escape(str(s.get('age_band', '')))} "
            f"{escape(_GENDER_KO.get(s.get('gender'), str(s.get('gender', ''))))}"
        )
        legend_rows.append(
            '<div class="flex items-center gap-1.5 text-[10px]">'
            f'<span class="w-2 h-2 rounded-full shrink-0" style="background:{col}"></span>'
            f'<span class="text-slate-600 truncate">{nm}</span>'
            f'<span class="ml-auto text-slate-400 shrink-0">{n}명 · 클릭 {_pct(cir)}</span></div>'
        )
    donut = (
        '<div class="flex items-center gap-4 mb-3">'
        '<div class="shrink-0 w-[112px] h-[112px] rounded-full grid place-items-center" '
        f'style="background:conic-gradient({", ".join(stops)})">'
        '<div class="w-[64px] h-[64px] rounded-full bg-white grid place-items-center text-center">'
        f'<div><div class="text-[15px] font-extrabold text-slate-800">{total_seg}</div>'
        '<div class="text-[8px] text-slate-400">명</div></div></div></div>'
        f'<div class="flex-1 space-y-1">{"".join(legend_rows)}</div></div>'
    )
    return _section(
        num,
        "누구에게 통하나 — 연령대×성별",
        _INDIGO,
        donut + table,
        tip=(
            "같은 광고도 누가 보느냐에 따라 반응이 달라요. 인원 많은 셀부터 정렬했고, "
            "클릭 의향이 높은(초록) 셀이 실질 타깃입니다."
        ),
    )


def _message_block(m: dict, num: str = "") -> str:
    """메시지 수신 — 의도 메시지가 어떻게 받아들여졌나(화면·PDF 양쪽 소실 1순위였던 것)."""
    rr = m.get("resistance_rate") or 0
    body = ""
    if m.get("intended"):
        body += (
            f'<p class="text-[11.5px] text-slate-700 mb-2">의도 메시지 — '
            f"“{escape(str(m['intended']))}”</p>"
        )
    body += _bar("저항 반응", rr, _pct(rr), _RED if rr >= 0.3 else _SLATE)
    terms = m.get("resistance_terms") or {}
    if terms:
        body += (
            '<p class="text-[10px] text-slate-500 mt-1.5">저항 표현 — '
            + escape(", ".join(f"{k}({v})" for k, v in terms.items()))
            + "</p>"
        )
    for q in (m.get("resisted_quotes") or [])[:3]:
        body += (
            f'<div class="text-[10.5px] text-slate-600 bg-slate-50 rounded-lg '
            f'px-3 py-1.5 mt-1.5">“{escape(str(q))}”</div>'
        )
    return _section(
        num,
        "메시지가 의도대로 받아들여졌나",
        _AMBER,
        body,
        tip=(
            "광고가 던진 메시지가 소비자에게 어떻게 닿았는지 — "
            "과장·식상·무관심 같은 저항 표현 비율로 가늠합니다."
        ),
    )


def _build_html(result: dict) -> str:
    """ReportView dict → Tailwind 대시보드 HTML(Chromium 인쇄 입력). 순수 함수.

    result는 report_view(단일 소스)를 받는다 — report/analysis/aggregate/topic/debate에
    더해 objective_fit·segments·message_reception·confidence를 함께 그린다.
    (구버전 result도 호환: 신규 키 없으면 해당 섹션만 생략.)
    """
    report = result.get("report") or {}
    analysis = result.get("analysis") or {}
    aggregate = result.get("aggregate") or {}
    topic = result.get("topic") or {}
    ad = result.get("ad_analysis") or {}
    debate = result.get("debate") or {}
    kpi = report.get("kpi") or {}
    rubric = report.get("rubric_scores") or []
    total_n = analysis.get("total_n") or 0

    cir = kpi.get("click_intent_rate") or 0
    pi = kpi.get("purchase_intent", 0) or 0
    tr = kpi.get("trust_avg", 0) or 0
    rej = kpi.get("rejection_rate") or 0
    brr = kpi.get("brand_recognition_rate") or 0
    overall = _overall(kpi, rubric)
    grade, gtext = _grade(overall)
    ocolor = _signal(overall)
    vlabel, vcolor, vdesc = _verdict(cir, rej)
    # verdict 카드 본문 = 전문가용 진단(headline). 비전문가용(plain_summary)은 강약점 박스 끝으로.
    head = report.get("headline") or report.get("plain_summary") or vdesc
    blocks: list[str] = []

    # 본문 섹션 번호 — 존재하는 섹션만 1..N 연속(조건부 섹션이 빠져도 번호 점프 없음).
    # 상단 요약(헤더·KPI·종합판정·목표달성·신뢰도)은 번호를 매기지 않는다.
    _secn = 0

    def _sec() -> str:
        nonlocal _secn
        _secn += 1
        return str(_secn)

    # ── 헤더 밴드 ──
    metabits = []
    if ad.get("detected_industry"):
        metabits.append(f"업종 {ad['detected_industry']}")
    if topic.get("objective") or ad.get("detected_objective"):
        metabits.append(f"목적 {topic.get('objective') or ad.get('detected_objective')}")
    if ad.get("detected_message"):
        metabits.append(f"메시지 {ad['detected_message']}")
    blocks.append(
        '<div class="rounded-2xl p-6 text-white flex justify-between items-end shadow-md" '
        'style="background:linear-gradient(120deg,#0f1f3d,#1e3a8a 55%,#2563eb)">'
        '<div><div class="text-[25px] font-extrabold tracking-tight">광고 시뮬레이션 보고서</div>'
        f'<div class="text-[12px] text-blue-200 mt-1.5">집행 전, AI 가상 소비자 {total_n}명에게 '
        "미리 보여준 반응이에요</div>"
        + (
            f'<div class="text-[10px] text-blue-300 mt-2">{escape("  ·  ".join(metabits))}</div>'
            if metabits
            else ""
        )
        + "</div>"
        f'<div class="text-right text-[10px] text-blue-200 leading-relaxed shrink-0 ml-4">'
        f"엔진 {escape(str(aggregate.get('engine_version') or '-'))}<br>가상 소비자 {total_n}명</div>"
        "</div>"
    )

    # ── 상단 KPI 카드 strip (5개) ──
    blocks.append(
        '<div class="grid grid-cols-5 gap-3">'
        + _kpi_card(_pct(cir), "클릭 의향", f"100명 중 {_n(cir)}명이 눌러보고 싶어 했어요", _BLUE)
        + _kpi_card(f"{pi:.1f}", "구매의도 (5점)", "사고 싶은 마음의 정도", _INDIGO)
        + _kpi_card(f"{tr:.1f}", "신뢰도 (5점)", "광고를 얼마나 믿는지", _TEAL)
        + _kpi_card(
            _pct(rej),
            "거부율",
            f"{_n(rej)}명이 '싫다·스킵'. 낮을수록 좋아요",
            _RED if rej >= 0.3 else _SLATE,
        )
        + _kpi_card(_pct(brr), "브랜드 식별", f"{_n(brr)}명이 어느 브랜드인지 알아봤어요", _GREEN)
        + "</div>"
    )

    # ── 종합 판정(풀폭) — verdict(전문가 진단) + 한눈에 보는 결론(비전문가, 하단 가로) ──
    # 화면(SimulationReportView)과 동일 구조. 강약점 요약은 §진단 섹션(rubric)에 그대로 있다.
    deg = overall / 100 * 360
    plain = report.get("plain_summary") or ""
    plain_block = (
        (
            '<div class="mt-4 pt-3 border-t border-slate-100">'
            '<div class="text-[11px] font-extrabold text-blue-600 mb-1">🔎 한눈에 보는 결론</div>'
            f'<p class="text-[11px] text-slate-600 leading-relaxed">{escape(str(plain))}</p></div>'
        )
        if plain and plain != head
        else ""
    )
    blocks.append(
        f'<div class="{_CARD} p-5">'
        '<div class="flex items-center gap-5">'
        '<div class="shrink-0 text-center">'
        '<div class="w-[92px] h-[92px] rounded-full grid place-items-center" '
        f'style="background:conic-gradient({ocolor} {deg:.1f}deg,#e2e8f0 0)">'
        '<div class="w-[64px] h-[64px] rounded-full bg-white grid place-items-center '
        f'text-[26px] font-extrabold text-slate-800">{overall}</div></div>'
        f'<div class="text-[12px] font-extrabold mt-1.5" style="color:{ocolor}">'
        f"{grade}등급 · {gtext}</div>"
        '<div class="text-[9px] text-slate-400">종합 점수 / 100</div></div>'
        '<div class="flex-1"><span class="inline-block px-4 py-1.5 rounded-full text-white '
        f'font-extrabold text-[13px]" style="background:{vcolor}">{vlabel}</span>'
        f'<div class="text-[13.5px] font-bold text-slate-800 mt-2.5 leading-snug">'
        f"{escape(str(head))}</div>"
        f'<div class="text-[11px] text-slate-500 mt-1.5 leading-relaxed">{escape(vdesc)}</div>'
        "</div></div>"
        f"{plain_block}</div>"
    )

    # ── 목표 달성 가능성(결정권자 1순위) — verdict 바로 아래 ──
    of = result.get("objective_fit")
    if of:
        blocks.append(_objective_fit_block(of))

    blocks.append(
        '<div class="text-[10.5px] text-slate-500 bg-blue-50 rounded-xl px-4 py-2.5">'
        '💡 <b class="text-slate-700">읽는 법</b> — 위에서부터 <b>결론</b>(내보내도 될까) → '
        "<b>근거</b>(소비자 반응) → <b>진단·개선</b>(무엇을 고치나) 순서예요. "
        "바쁘면 위 카드만 봐도 됩니다.</div>"
    )

    # ── 신뢰도 안내(과신 방지) ──
    conf = result.get("confidence")
    if conf:
        blocks.append(_confidence_block(conf))

    # ── §2 퍼널 (풀폭) ──
    funnel_body = "".join(
        _bar(
            _AISAS_KO.get(f["stage"], f["stage"]),
            f.get("pass_rate") or 0,
            f"{_pct(f.get('pass_rate'))} ({f.get('passed', 0)}명)",
            _BLUE,
        )
        for f in analysis.get("funnel") or []
    )
    bn = analysis.get("bottleneck")
    if bn:
        funnel_body += (
            '<div class="mt-2.5 text-[10.5px] text-amber-700 bg-amber-50 rounded-lg px-3 py-2">'
            f"⬇ 여기서 가장 많이 빠졌어요 — <b>{_AISAS_KO.get(bn['from_stage'], bn['from_stage'])} → "
            f"{_AISAS_KO.get(bn['to_stage'], bn['to_stage'])}</b> 구간 {bn['dropped']}명 이탈"
            f"({_pct(bn.get('drop_rate'))}). 이 지점을 고치면 효과가 가장 큽니다.</div>"
        )
    blocks.append(
        _section(
            _sec(),
            "소비자 반응 — 어디서 새는가",
            _BLUE,
            funnel_body,
            tip=(
                "소비자가 광고를 만나 행동까지 가는 길이에요: <b>주목→흥미→탐색→행동→공유</b>. "
                "단계가 갈수록 자연히 줄지만, <b>갑자기 확 빠지는 구간</b>이 고쳐야 할 곳이에요."
            ),
        )
    )

    # ── 세그먼트 히트맵(누구에게 통하나) ──
    segs = result.get("segments") or []
    if segs:
        blocks.append(_segment_block(segs, _sec()))

    # ── 구매의도 | 감정 (2열) ──
    pid = report.get("purchase_intent_dist") or {}
    plab = {1: "전혀 없음", 2: "낮음", 3: "보통", 4: "높음", 5: "매우 높음"}
    pcol = {1: _RED, 2: _AMBER, 3: _SLATE, 4: _BLUE, 5: _GREEN}
    pi_body = "".join(
        _bar(plab[i], (_ival(pid, i) / total_n if total_n else 0), f"{_ival(pid, i)}명", pcol[i])
        for i in range(1, 6)
    )
    emo = report.get("emotion_dist") or {}
    en = sum(emo.values()) or 1
    emo_body = "".join(_bar(_EMOTION_KO.get(k, k), v / en, f"{v}명", _TEAL) for k, v in emo.items())
    blocks.append(
        '<div class="grid grid-cols-2 gap-3">'
        + _section(
            _sec(),
            "구매의도 분포",
            _INDIGO,
            pi_body,
            tip='"이 제품 사고 싶나?"를 5단계로 나눈 거예요.',
        )
        + _section("", "광고를 보고 든 느낌", _TEAL, emo_body)
        + "</div>"
    )

    # ── 메시지 수신(의도 vs 저항) ──
    msg = result.get("message_reception")
    if msg:
        blocks.append(_message_block(msg, _sec()))

    # ── 거부 사유 | 브랜드 식별 (2열) ──
    rb = report.get("rejection") or {}
    by_rej = rb.get("by_rejection_reason_tag") or {}
    rc = rb.get("rejected_count") or sum(by_rej.values()) or 1
    rej_body = (
        "".join(_bar(_REJECTION_KO.get(k, k), v / rc, f"{v}명", _RED) for k, v in by_rej.items())
        or '<div class="text-[11px] text-slate-400">거부 없음</div>'
    )
    br = report.get("brand_recognition") or {}
    brand_body = _bar(
        "기억함",
        br.get("recognition_rate") or 0,
        f"{br.get('recognized_count', 0)}명 ({_pct(br.get('recognition_rate'))})",
        _GREEN,
    ) + _bar(
        "기억 못 함",
        (br.get("unrecognized_count", 0) / total_n if total_n else 0),
        f"{br.get('unrecognized_count', 0)}명",
        _SLATE,
    )
    pb = br.get("perceived_brands") or {}
    if pb:
        brand_body += (
            '<div class="mt-2 text-[10px] text-slate-500">떠올린 브랜드 — '
            + escape(", ".join(f"{k}({v}명)" for k, v in pb.items()))
            + "</div>"
        )
    blocks.append(
        '<div class="grid grid-cols-2 gap-3">'
        + _section(_sec(), f"광고를 거부한 이유 ({_pct(rb.get('rejection_rate'))})", _RED, rej_body)
        + _section(
            "",
            "브랜드가 기억에 남았나",
            _GREEN,
            brand_body,
            tip='광고를 보고 <b>"어느 브랜드인지"</b> 알아봤는지예요(Fluency).',
        )
        + "</div>"
    )

    # ── §4 진단 (풀폭) ──
    if rubric:
        diag_body = "".join(
            _bar(
                _RUBRIC_KO.get(s.get("dimension"), s.get("dimension", "")),
                (s.get("score", 0) or 0) / 100,
                f"{s.get('score', 0)}/100",
                _signal(s.get("score", 0) or 0),
            )
            for s in rubric
        )
        blocks.append(
            _section(
                _sec(),
                "광고 자체의 완성도 진단",
                _AMBER,
                diag_body,
                tip=(
                    '항목별 100점 만점 채점이에요. <b class="text-emerald-600">초록</b>=좋음 · '
                    '<b class="text-amber-500">주황</b>=보통 · '
                    '<b class="text-red-500">빨강</b>=손봐야 함.'
                ),
            )
        )

    # ── 토론 참가자 소개 — 개선안·토론에 나오는 이름이 누구인지 먼저 정리(프로필·역할·최종 입장) ──
    # 현재(최근) 토론 기준(debate.participants). 화면 ParticipantRoster와 같은 의미·라벨.
    participants = debate.get("participants") or []
    if participants:
        prows = []
        for p in participants:
            utts = p.get("utterances") or []
            stance = (utts[-1].get("stance") if utts else "neutral") or "neutral"
            scol, slab = _STANCE.get(stance, (_SLATE, "중립"))
            prof = escape(str(p.get("persona_profile", "")))
            role = escape(str(p.get("role", "")))
            prof_html = f'<span class="text-[10px] text-slate-500">· {prof}</span>' if prof else ""
            role_html = (
                '<span class="text-[9.5px] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5">'
                f"{role}</span>"
                if role
                else ""
            )
            prows.append(
                '<div class="flex items-center gap-2 py-1.5 border-b border-slate-100 '
                'last:border-0 break-inside-avoid">'
                '<span class="font-bold text-[11px] text-slate-800">'
                f"{escape(str(p.get('persona_name', '')))}</span>"
                f"{prof_html}{role_html}"
                '<span class="ml-auto inline-block px-2 py-0.5 rounded-full text-white '
                f'text-[9.5px] font-bold shrink-0" style="background:{scol}">{slab}</span>'
                "</div>"
            )
        blocks.append(
            _section(
                "",
                "토론 참가자",
                _INDIGO,
                "".join(prows),
                tip="개선안과 토론에 나오는 이름이 누구인지 — 프로필·역할·토론 최종 입장을 먼저 정리했어요.",
            )
        )

    # ── §5 토론 (풀폭) — 주제 + 대표 인용 1~2 + 결론만(전문 생략, 분량 축소) ──
    # debates(누적 요약)가 있으면 토론마다 한 블록 — 토론을 더 할수록 항목이 늘어난다.
    debates_list = result.get("debates") or []
    if debates_list:
        dcards = []
        for dg in debates_list:
            qh = "".join(
                '<div class="rounded-lg bg-slate-50 border-l-4 px-3 py-2 my-1 break-inside-avoid" '
                f'style="border-color:{_STANCE.get(q.get("stance", "neutral"), (_SLATE, ""))[0]}">'
                f'<div class="text-[10.5px] text-slate-700">“{escape(str(q.get("text", "")))}”</div>'
                + (
                    '<div class="text-[9.5px] text-slate-500 mt-1 leading-snug">↳ 무엇에/왜 — '
                    f"{escape(str(q.get('reason', '')))}</div>"
                    if q.get("reason")
                    else ""
                )
                + '<div class="text-[9.5px] text-slate-400 mt-0.5">— '
                f"{escape(str(q.get('persona_name', '')))} · {escape(str(q.get('role', '')))}</div>"
                "</div>"
                for q in (dg.get("quotes") or [])[:2]
            )
            concl = []
            for c in dg.get("consensus") or []:
                concl.append(
                    '<div class="my-1 text-[11px]"><span class="inline-block px-2 py-0.5 '
                    'rounded text-white text-[9.5px] font-bold mr-2" '
                    f'style="background:{_GREEN}">다같이 동의</span>{escape(str(c))}</div>'
                )
            for d in dg.get("dissent") or []:
                concl.append(
                    '<div class="my-1 text-[11px]"><span class="inline-block px-2 py-0.5 '
                    'rounded text-white text-[9.5px] font-bold mr-2" '
                    f'style="background:{_AMBER}">의견 갈림</span>{escape(str(d))}</div>'
                )
            rr = dg.get("rounds_run") or 0
            dcards.append(
                '<div class="break-inside-avoid mb-3 pb-3 border-b border-slate-100 last:border-0">'
                '<div class="text-[11.5px] font-bold text-slate-800 mb-1.5">'
                f"{escape(str(dg.get('topic_headline', '')))}"
                f'<span class="text-[9.5px] font-normal text-slate-400 ml-1.5">{rr}라운드</span>'
                "</div>"
                f"{qh}{''.join(concl)}</div>"
            )
        blocks.append(
            _section(
                _sec(),
                "전문가·소비자 토론",
                _INDIGO,
                "".join(dcards),
                tip=(
                    "토론마다 주제와 대표 발언 1~2개, 결론만 추렸어요. "
                    "(토론을 더 할수록 항목이 늘어납니다. 전체 발언은 화면 토론 패널에서 볼 수 있어요.)"
                ),
            )
        )

    # ── §6 개선 권고 (풀폭) ──
    actions = (
        report.get("ranked_actions") or (debate.get("final") or {}).get("ranked_actions") or []
    )
    if actions:
        rec = []
        for a in actions:
            eff = (
                (
                    f'<div class="text-[10px] text-slate-500 mt-0.5">기대 효과: '
                    f"{escape(str(a['expected_effect']))}</div>"
                )
                if a.get("expected_effect")
                else ""
            )
            sp = a.get("supporting_personas") or []
            spx = (
                (
                    f'<div class="text-[10px] text-slate-500 mt-0.5">이렇게 말한 사람: '
                    f"{escape(', '.join(str(x) for x in sp))}</div>"
                )
                if sp
                else ""
            )
            rec.append(
                '<div class="flex gap-3 py-2.5 border-b border-slate-100 break-inside-avoid">'
                '<span class="w-6 h-6 rounded-full bg-blue-600 text-white text-[11px] font-bold '
                f'grid place-items-center shrink-0">{escape(str(a.get("rank", "?")))}</span>'
                f'<div><div class="font-bold text-[11.5px] text-slate-800">'
                f"{escape(str(a.get('action', '')))}</div>{eff}{spx}</div></div>"
            )
        blocks.append(
            _section(
                _sec(),
                "그래서, 무엇을 고치면 되나",
                _BLUE,
                "".join(rec),
                tip="효과가 큰 순서대로 정리한 개선 액션이에요.",
            )
        )

    if not debates_list:
        quotes = report.get("quotes") or []
        if quotes:
            qb = "".join(
                '<div class="rounded-lg bg-slate-50 border-l-4 border-slate-300 px-3 py-2 my-1.5">'
                f'<div class="text-[10.5px] text-slate-700">“{escape(str(q.get("text", "")))}”</div>'
                + (
                    '<div class="text-[9.5px] text-slate-500 mt-1 leading-snug">↳ 무엇에/왜 — '
                    f"{escape(str(q.get('reason', '')))}</div>"
                    if q.get("reason")
                    else ""
                )
                + '<div class="text-[9.5px] text-slate-400 mt-0.5">— '
                f"{escape(str(q.get('persona_name', '')))} · {escape(str(q.get('role', '')))}</div>"
                "</div>"
                for q in quotes[:2]
            )
            blocks.append(_section(_sec(), "소비자 목소리", _SLATE, qb))

    blocks.append(
        '<div class="text-[9px] text-slate-400 leading-relaxed pt-3 border-t border-slate-200">'
        "이 보고서는 실제 사람이 아니라 한국 인구·성격·미디어 통계로 만든 AI 가상 소비자의 반응을 "
        "모은 <b>예측 참고 자료</b>입니다. 실제 광고 성과를 보증하지 않으며, 수치는 정확한 값이 "
        "아니라 방향과 범위로 읽어 주세요.</div>"
    )

    body = '<div class="max-w-[820px] mx-auto space-y-4">' + "".join(blocks) + "</div>"
    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        "<script src='https://cdn.tailwindcss.com'></script>"
        "<script>tailwind.config={theme:{extend:{fontFamily:{sans:"
        "['Malgun Gothic','Noto Sans KR','Apple SD Gothic Neo','sans-serif']}}}}</script>"
        "<style>*{-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
        "html,body{background:#f1f5f9;}"
        "body{font-family:'Malgun Gothic','Noto Sans KR','Apple SD Gothic Neo',sans-serif;}</style>"
        "</head><body class='bg-slate-100 text-slate-900 px-8 py-3'>" + body + "</body></html>"
    )


def _strip_trailing_blank_pages(pdf: bytes) -> bytes:
    """분량이 페이지 경계를 미세 초과할 때 Chromium이 덧붙인 꼬리 빈 페이지를 제거한다.

    빈 페이지엔 body 배경(vector)만 있고 텍스트가 없다 — 마지막부터 텍스트 0인 페이지를 잘라낸다.
    실패해도 원본을 그대로 반환(다운로드 자체는 막지 않는다).
    """
    import io

    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(io.BytesIO(pdf))
        total = len(reader.pages)
        keep = total
        while keep > 1 and not (reader.pages[keep - 1].extract_text() or "").strip():
            keep -= 1
        if keep == total:
            return pdf
        writer = PdfWriter()
        for i in range(keep):
            writer.add_page(reader.pages[i])
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        logger.exception("빈 페이지 트림 실패 — 원본 PDF 반환")
        return pdf


def render_report_pdf(result: dict) -> bytes:
    """result → Tailwind HTML → Playwright(Chromium) PDF 바이트. 동기(라우터에서 to_thread).

    report_view(화면·PDF 공용 단일 소스)를 우선 소비한다 — 없으면 구버전 result로 폴백.
    """
    from playwright.sync_api import sync_playwright

    html = _build_html(result.get("report_view") or result)
    # 모든 페이지 상/하단에 '배경색 여백'을 만든다 — @page margin 영역(원래 흰색)을
    # header/footer 템플릿의 배경 띠로 덮는다. body 배경(#f1f5f9)과 같은 색이라 첫 페이지부터
    # 마지막까지 균일한 여백이 된다(margin 0이면 2페이지부터 콘텐츠가 가장자리에 붙던 문제 해결).
    band = (
        '<div style="background:#f1f5f9;width:100%;height:100%;margin:0;'
        '-webkit-print-color-adjust:exact;print-color-adjust:exact;"></div>'
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.wait_for_timeout(600)  # Tailwind Play CDN(JIT)이 DOM 스캔·스타일 주입할 시간
            pdf = page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=band,
                footer_template=band,
                margin={"top": "12mm", "bottom": "12mm", "left": "0mm", "right": "0mm"},
            )
        finally:
            browser.close()
    return _strip_trailing_blank_pages(pdf)
