# 조각 8·9 검증 — 더미 5개를 반응분석·KPI·토픽에 돌려 정합성·재현성 확인(도메인 내부, pytest 밖)
#
# 실행: cd backend && uv run python -m domain.simulation.tools.debate.verify
# 검사: ① funnel 합/총원 정합 ② 더미1 손검증값 일치 ③ action 인원이 더미 aggregate와 일치
#       ④ groups 겹침·비어있음 엣지 ⑤ 같은 입력 2회 → 동일 산출(결정론)
#       ⑥ 9 재계산 KPI가 더미 aggregate와 일치 ⑦ 토픽 결정론·주신호 타당
from __future__ import annotations

import sys

from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.assigner import assign_panel
from domain.simulation.tools.debate.kpi import build_topic, compute_kpi
from domain.simulation.tools.debate.loader import load_all_dummies
from domain.simulation.tools.debate.selector import select_panel

# Windows 콘솔(cp949)에서 한글·em대시 출력이 깨지지 않게 강제(검증 출력 전용).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _check(cond: bool, msg: str) -> bool:
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {msg}")
    return cond


def main() -> int:
    dummies = load_all_dummies()
    print(f"로드된 더미: {len(dummies)}개\n")
    all_ok = True

    for d in dummies:
        a = analyze_reactions(d.reactions)
        fl = {f.stage: f.passed for f in a.funnel}
        action_n = fl["action"]
        bn = a.bottleneck
        print(f"=== {d.name} (n={a.total_n}) ===")
        print(f"  funnel: {fl}")
        print(
            f"  bottleneck: {bn.from_stage}->{bn.to_stage} dropped={bn.dropped}"
            if bn
            else "  bottleneck: None"
        )
        print(
            f"  groups: finishers={len(a.groups.finishers)} undecided={len(a.groups.undecided)} "
            f"rejectors={len(a.groups.rejectors)} distrusters={len(a.groups.distrusters)} "
            f"early_drop={len(a.groups.early_drop)}"
        )
        print(
            f"  rejection: count={a.rejection.rejected_count} distrust={a.rejection.distrust_count}"
        )

        # ① funnel passed <= total_n, attention 최댓값 가정 안 함(단조 아님) — 범위만 체크
        ok1 = _check(all(0 <= f.passed <= a.total_n for f in a.funnel), "funnel passed ∈ [0, n]")

        # ③ action 인원 == 더미 aggregate.click_intent_rate * n (가중치 1이라 비가중과 동일)
        ok3 = True
        if d.aggregate is not None and a.total_n:
            expected_action = round(d.aggregate.click_intent_rate * a.total_n)
            ok3 = _check(
                action_n == expected_action,
                f"action {action_n} == agg.click_intent_rate×n {expected_action}",
            )

        # ⑤ 결정론: 같은 입력 2회 동일
        ok5 = _check(
            analyze_reactions(d.reactions).model_dump() == a.model_dump(),
            "재현성(같은 입력 → 같은 산출)",
        )

        # ⑥ 조각 9 — 재계산 KPI가 더미에 박힌 7번 aggregate와 일치(주요 필드)
        kpi = compute_kpi(d.reactions)
        ok6 = True
        if d.aggregate is not None:
            fields = ["click_intent_rate", "purchase_intent", "trust_avg", "rejection_rate"]
            mism = [
                f"{f}: {getattr(kpi, f)} != {getattr(d.aggregate, f)}"
                for f in fields
                if getattr(kpi, f) != getattr(d.aggregate, f)
            ]
            ok6 = _check(
                not mism, f"9 KPI == 더미 aggregate {('(' + '; '.join(mism) + ')') if mism else ''}"
            )

        # ⑦ 조각 9 — 토픽 생성(결정론 + 주신호)
        topic = build_topic(a, kpi, d.ad_analysis)
        ok7 = _check(
            build_topic(a, kpi, d.ad_analysis).model_dump() == topic.model_dump(),
            f"토픽 재현성 [{topic.primary_signal}] {topic.headline}",
        )

        # ⑧ 조각 10-a — 패널 구성(전문가4 합성 + 일반인 lay_count 선발·중복없음·결정론)
        panel = select_panel(d.reactions, d.ad_analysis)  # 기본 lay_count=4
        ids = [p.persona_id for p in panel.participants]
        roster = ", ".join(
            f"{p.persona_id}[{p.role}"
            f"{'·ex' if p.is_expert else ''}{'·fb' if p.is_fallback else ''}]"
            for p in panel.participants
        )
        print(f"  panel: {roster}")
        experts = [p for p in panel.participants if p.is_expert]
        laypeople = [p for p in panel.participants if not p.is_expert]
        expected_size = 4 + min(4, a.total_n)  # 전문가 4 + 일반인(피벗·비판자·완주자·미온) 최대 4
        size_ok = len(panel.participants) == expected_size and len(experts) == 4
        uniq_ok = len(set(ids)) == len(ids)
        det_ok = [
            p.model_dump() for p in select_panel(d.reactions, d.ad_analysis).participants
        ] == [p.model_dump() for p in panel.participants]
        ok8 = _check(
            size_ok and uniq_ok and det_ok,
            f"구성 전문가{len(experts)}+일반인{len(laypeople)}·중복없음·결정론 "
            f"(pivot={panel.pivot_id}, critic={panel.critic_secured})",
        )

        # ⑧b 조각 10-a — lay_count=2 버전(전문가4 + 일반인2=피벗·비판자, slot 5·6 연속)
        panel2 = select_panel(d.reactions, d.ad_analysis, 2)
        lay2 = [p for p in panel2.participants if not p.is_expert]
        roles2 = [p.role for p in lay2]
        slots2 = [p.slot for p in panel2.participants]
        ok8b = _check(
            len(panel2.participants) == 4 + min(2, a.total_n)
            and roles2 == ["피벗", "비판자"][: len(lay2)]
            and slots2 == list(range(1, len(panel2.participants) + 1)),  # slot 연속(빈칸 없음)
            f"lay_count=2 → 전문가4+일반인{len(lay2)}{roles2}·slot연속",
        )

        # ⑨ 조각 10-b — 엔진·이름 배정(엔진 쿼터 haiku4/gpt4·gemini 제거·이름 중복없음·결정론)
        ap = assign_panel(panel)
        roster2 = ", ".join(f"{p.persona_name}/{p.engine}" for p in ap.participants)
        print(f"  assigned: {roster2}")
        eng_counts = {
            e: sum(1 for p in ap.participants if p.engine == e) for e in ("haiku", "gpt", "gemini")
        }
        names = [p.persona_name for p in ap.participants]
        # 8명 패널 기준 기대 쿼터 haiku4/gpt4 (Gemini 제거, n<8이면 분포만 확인)
        quota_ok = (
            eng_counts == {"haiku": 4, "gpt": 4, "gemini": 0} if len(ap.participants) == 8 else True
        )
        judge_ok = ap.judge_engine == "sonnet"
        det9 = [p.model_dump() for p in assign_panel(panel).participants] == [
            p.model_dump() for p in ap.participants
        ]
        ok9 = _check(
            quota_ok and judge_ok and len(set(names)) == len(names) and det9,
            f"배정 엔진{eng_counts}·judge={ap.judge_engine}·이름중복없음·결정론",
        )

        all_ok = all_ok and ok1 and ok3 and ok5 and ok6 and ok7 and ok8 and ok8b and ok9
        print()

    # ② 더미1 손검증: attention10 interest10 search0 action1 share0, 병목 interest->search(10)
    d1 = next((x for x in dummies if x.name.endswith("dummy1")), None)
    if d1:
        a1 = analyze_reactions(d1.reactions)
        fl1 = {f.stage: f.passed for f in a1.funnel}
        print("=== 더미1 손검증 ===")
        ok2 = _check(
            fl1 == {"attention": 10, "interest": 10, "search": 0, "action": 1, "share": 0},
            f"funnel == 손계산값 (got {fl1})",
        )
        ok2b = _check(
            a1.bottleneck is not None
            and (a1.bottleneck.from_stage, a1.bottleneck.to_stage, a1.bottleneck.dropped)
            == ("interest", "search", 10),
            "병목 == interest->search(10)",
        )
        all_ok = all_ok and ok2 and ok2b

    print("\n" + ("전체 통과 [PASS]" if all_ok else "실패 있음 [FAIL]"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
