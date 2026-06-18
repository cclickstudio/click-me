# 조각 11 리포트 → PDF 직접 렌더(reportlab). html2pdf 변환 금지 — 백엔드에서 바이트 직접 생성.
#
# 입력은 토론 result dict(report·analysis·aggregate·topic·ad_analysis). 한글 폰트는 generator와
# 동일 폴백 체인(assets/fonts → Windows malgun → Linux noto)으로 1회 등록. 차트는 1차로 텍스트 막대.
from __future__ import annotations

import io
import logging
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("clickme")

# pdf_report.py = backend/domain/simulation/tools/debate/ → parents[4] = backend
_FONTS_DIR = Path(__file__).parents[4] / "assets" / "fonts"
_FONT = "ClickKR"
_FONT_BOLD = "ClickKR-Bold"
_FONTS_READY: tuple[str, str] | None = None

_ACCENT = colors.HexColor("#1a4d8f")
_GREY = colors.HexColor("#666666")
_LIGHT = colors.HexColor("#eef2f7")

# enum → 한글 라벨(보고서 렌더링용 — enums.py 주석의 표시 라벨과 동일 의도).
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
_DROP_REASON_KO = {
    "no_reason_to_explore": "더 알아볼 이유 없음",
    "price_concern": "가격 부담",
    "low_relevance": "관련성 낮음",
    "unclear_message": "메시지 불명확",
    "distrust": "불신",
    "other": "기타",
}


def _candidates(bold: bool) -> list[Path]:
    name = "NotoSansKR-Bold.ttf" if bold else "NotoSansKR-Regular.ttf"
    return [
        _FONTS_DIR / name,
        Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        Path(
            "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Bold.otf"
            if bold
            else "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf"
        ),
    ]


def _register_one(name: str, *, bold: bool) -> bool:
    for path in _candidates(bold):
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                return True
            except Exception:
                logger.exception("폰트 등록 실패 path=%s", path)
    return False


def _fonts() -> tuple[str, str]:
    """한글 TTF를 1회 등록하고 (regular, bold) 폰트명 반환. 못 찾으면 Helvetica 폴백(한글 깨짐)."""
    global _FONTS_READY
    if _FONTS_READY is not None:
        return _FONTS_READY
    has_regular = _register_one(_FONT, bold=False)
    has_bold = _register_one(_FONT_BOLD, bold=True)
    if has_regular:
        _FONTS_READY = (_FONT, _FONT_BOLD if has_bold else _FONT)
    else:
        logger.warning(
            "한글 폰트 미발견 — PDF 한글이 깨질 수 있음(assets/fonts에 NotoSansKR 추가)."
        )
        _FONTS_READY = ("Helvetica", "Helvetica-Bold")
    return _FONTS_READY


def _bar(ratio: float, width: int = 18) -> str:
    """0~1 비율을 텍스트 막대로(1차 차트). reportlab 그래픽 차트는 점진 도입."""
    filled = max(0, min(width, round(ratio * width)))
    return "█" * filled + "░" * (width - filled)


def _pct(x: float | None) -> str:
    return f"{(x or 0) * 100:.0f}%"


def render_report_pdf(result: dict) -> bytes:
    """토론 result dict(report·analysis·aggregate·topic·ad_analysis)를 §0~§5 PDF 바이트로 렌더."""
    font, font_bold = _fonts()
    report = result.get("report") or {}
    analysis = result.get("analysis") or {}
    aggregate = result.get("aggregate") or {}
    topic = result.get("topic") or {}
    ad = result.get("ad_analysis") or {}
    kpi = report.get("kpi") or {}

    body = ParagraphStyle("body", fontName=font, fontSize=10, leading=15)
    small = ParagraphStyle("small", fontName=font, fontSize=8.5, leading=12, textColor=_GREY)
    title = ParagraphStyle("title", fontName=font_bold, fontSize=18, leading=23, spaceAfter=2)
    h2 = ParagraphStyle(
        "h2",
        fontName=font_bold,
        fontSize=13,
        leading=17,
        spaceBefore=14,
        spaceAfter=5,
        textColor=_ACCENT,
    )
    headline = ParagraphStyle("headline", fontName=font_bold, fontSize=12, leading=17, spaceAfter=4)

    story: list = []

    def hr() -> None:
        story.append(Spacer(1, 3))
        story.append(HRFlowable(width="100%", thickness=0.6, color=_LIGHT))

    def section(label: str) -> None:
        story.append(Paragraph(escape(label), h2))

    def kv_table(rows: list[tuple[str, str]]) -> Table:
        data = [
            [Paragraph(f"<b>{escape(k)}</b>", small), Paragraph(escape(v), body)] for k, v in rows
        ]
        t = Table(data, colWidths=[42 * mm, 120 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, _LIGHT),
                ]
            )
        )
        return t

    def dist_table(rows: list[tuple[str, int, float]]) -> Table | Paragraph:
        """라벨·막대·수치 3열 분포 표(퍼널·구매의도·감정 공용). 빈 입력이면 안내 문구."""
        if not rows:
            return Paragraph("데이터 없음", small)
        data = [
            [
                Paragraph(escape(label), body),
                Paragraph(_bar(ratio), body),
                Paragraph(f"{cnt}명 ({_pct(ratio)})", small),
            ]
            for label, cnt, ratio in rows
        ]
        t = Table(data, colWidths=[40 * mm, 80 * mm, 42 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return t

    total_n = analysis.get("total_n") or 0

    # ── §0 헤더 ──
    story.append(Paragraph("광고 시뮬레이션 보고서", title))
    story.append(Paragraph("ClickMe — AI 가상 소비자 반응 예측", small))
    hr()
    header_rows: list[tuple[str, str]] = []
    if ad.get("detected_industry"):
        header_rows.append(("업종(감지)", str(ad["detected_industry"])))
    if topic.get("objective") or ad.get("detected_objective"):
        header_rows.append(
            ("광고 목적", str(topic.get("objective") or ad.get("detected_objective")))
        )
    if ad.get("detected_message"):
        header_rows.append(("핵심 메시지(감지)", str(ad["detected_message"])))
    header_rows.append(("페르소나 규모", f"{total_n}명 (QA 통과 응답)"))
    header_rows.append(("엔진", str(aggregate.get("engine_version") or "-")))
    story.append(kv_table(header_rows))

    # ── §1 결론 카드 ──
    section("§1. 결론")
    if report.get("headline"):
        story.append(Paragraph(escape(report["headline"]), headline))
    if report.get("plain_summary"):
        story.append(Paragraph(escape(report["plain_summary"]), body))
    story.append(Spacer(1, 4))
    ci = f"{_pct(kpi.get('ci_low'))} ~ {_pct(kpi.get('ci_high'))}"
    story.append(
        kv_table(
            [
                ("클릭 의향률 (95% CI)", ci),
                ("구매의도", f"{kpi.get('purchase_intent', 0):.2f} / 5"),
                ("신뢰도", f"{kpi.get('trust_avg', 0):.2f} / 5"),
                ("거부율", _pct(kpi.get("rejection_rate"))),
                ("브랜드 식별률", _pct(kpi.get("brand_recognition_rate"))),
            ]
        )
    )
    if kpi.get("variance_warning"):
        story.append(Paragraph("⚠️ 응답 분산 낮음 — 재시뮬레이션 권장.", small))

    # ── §2-1 AISAS 퍼널 ──
    section("§2-1. AISAS 퍼널")
    funnel = analysis.get("funnel") or []
    story.append(
        dist_table(
            [
                (_AISAS_KO.get(f["stage"], f["stage"]), f["passed"], f.get("pass_rate") or 0)
                for f in funnel
            ]
        )
    )
    bn = analysis.get("bottleneck")
    if bn:
        story.append(
            Paragraph(
                f"최대 이탈 구간: {_AISAS_KO.get(bn['from_stage'], bn['from_stage'])} → "
                f"{_AISAS_KO.get(bn['to_stage'], bn['to_stage'])} "
                f"(-{bn['dropped']}명, {_pct(bn.get('drop_rate'))})",
                small,
            )
        )

    # ── §2-2 구매의도 분포 ──
    section("§2-2. 구매의도 분포")
    pid = report.get("purchase_intent_dist") or {}
    labels = {1: "전혀 없음", 2: "낮음", 3: "보통", 4: "높음", 5: "매우 높음"}
    story.append(
        dist_table(
            [
                (
                    labels[i],
                    int(pid.get(i, pid.get(str(i), 0))),
                    (int(pid.get(i, pid.get(str(i), 0))) / total_n if total_n else 0),
                )
                for i in range(1, 6)
            ]
        )
    )

    # ── §2-3 신뢰·거부 분석 ──
    section("§2-3. 신뢰 · 거부 분석")
    rej = report.get("rejection") or {}
    story.append(
        Paragraph(
            f"거부율 {_pct(rej.get('rejection_rate'))} · 불신 {rej.get('distrust_count', 0)}명",
            body,
        )
    )
    by_rej = rej.get("by_rejection_reason_tag") or {}
    if by_rej:
        rc = rej.get("rejected_count") or sum(by_rej.values()) or 1
        story.append(dist_table([(_REJECTION_KO.get(k, k), v, v / rc) for k, v in by_rej.items()]))
    by_drop = report.get("by_drop_reason_tag") or {}
    if by_drop:
        story.append(Paragraph("이탈 사유", small))
        dn = sum(by_drop.values()) or 1
        story.append(
            dist_table([(_DROP_REASON_KO.get(k, k), v, v / dn) for k, v in by_drop.items()])
        )

    # ── §2-4 감정 반응 ──
    section("§2-4. 감정 반응")
    emo = report.get("emotion_dist") or {}
    en = sum(emo.values()) or 1
    story.append(dist_table([(_EMOTION_KO.get(k, k), v, v / en) for k, v in emo.items()]))

    # ── §2-5 브랜드 식별 ──
    section("§2-5. 브랜드 식별 (Fluency)")
    br = report.get("brand_recognition") or {}
    story.append(
        Paragraph(
            f"브랜드 식별률 {_pct(br.get('recognition_rate'))} "
            f"(식별 {br.get('recognized_count', 0)}명 / "
            f"미식별 {br.get('unrecognized_count', 0)}명)",
            body,
        )
    )
    pb = br.get("perceived_brands") or {}
    if pb:
        story.append(
            Paragraph(
                "인식한 브랜드/제품: " + ", ".join(f"{escape(k)}({v})" for k, v in pb.items()),
                small,
            )
        )

    # ── §4 크리에이티브 진단(루브릭) ──
    rubric = report.get("rubric_scores") or []
    if rubric:
        section("§4. 크리에이티브 진단")
        data = [[Paragraph("<b>항목</b>", small), Paragraph("<b>점수</b>", small)]]
        for s in rubric:
            data.append(
                [
                    Paragraph(escape(str(s.get("dimension", ""))), body),
                    Paragraph(f"{s.get('score', 0)} / 100", body),
                ]
            )
        t = Table(data, colWidths=[120 * mm, 42 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("BACKGROUND", (0, 0), (-1, 0), _LIGHT),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, _LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t)

    # ── §5 개선 권고 ──
    actions = report.get("ranked_actions") or []
    if actions:
        section("§5. 개선 권고 (우선순위)")
        for a in actions:
            story.append(
                Paragraph(f"<b>{a.get('rank', '?')}. {escape(str(a.get('action', '')))}</b>", body)
            )
            if a.get("expected_effect"):
                story.append(Paragraph(f"기대 효과: {escape(str(a['expected_effect']))}", small))
            story.append(Spacer(1, 3))

    # ── 페르소나 보이스(토론 인용) ──
    quotes = report.get("quotes") or []
    if quotes:
        section("페르소나 보이스")
        for q in quotes[:5]:
            who = f"{q.get('persona_name', '')} · {q.get('role', '')}"
            story.append(Paragraph(f"“{escape(str(q.get('text', '')))}”", body))
            story.append(Paragraph(escape(who), small))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "본 보고서는 가상 소비자 반응 기반 추정이며 실제 성과를 보증하지 않습니다. "
            "예측은 레인지로 해석하세요.",
            small,
        )
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="광고 시뮬레이션 보고서",
    )
    doc.build(story)
    return buf.getvalue()
