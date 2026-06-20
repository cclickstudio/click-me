# Meta 소셜피드 도달성 — 셀 비중 산출·노출 후보 필터·샘플러 가중 반영 테스트 (LLM✗)
from __future__ import annotations

import random
from types import SimpleNamespace

from domain.simulation.adapters.gemini import reaction as gemini_reaction
from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.tools.reachability import (
    cell_social_reach,
    is_social_context,
    pick_social_exposure,
)
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler

_SNS = {"timeband": "저녁", "medium": "스마트폰/휴대폰", "activity": "SNS", "place": "집"}
_VIDEO = {"timeband": "저녁", "medium": "PC", "activity": "동영상/개인방송", "place": "집"}
_PAPER = {"timeband": "오전", "medium": "신문/잡지/책", "activity": "읽기", "place": "집"}
_TV = {"timeband": "저녁", "medium": "TV", "activity": "TV/방송시청", "place": "집"}


def test_is_social_context() -> None:
    assert is_social_context("SNS", "스마트폰/휴대폰")
    assert is_social_context("동영상/개인방송", "PC")
    assert not is_social_context("SNS", "TV")  # 매체가 비소셜
    assert not is_social_context("읽기", "스마트폰/휴대폰")  # 행위가 비소셜


def test_cell_social_reach_sums_social_share() -> None:
    cell = {"exposure": [{**_SNS, "p": 0.5}, {**_VIDEO, "p": 0.2}, {**_PAPER, "p": 0.3}]}
    assert cell_social_reach(cell) == 0.7  # 0.5 + 0.2 (신문 제외)


def test_cell_social_reach_none_without_data() -> None:
    assert cell_social_reach(None) is None
    assert cell_social_reach({"exposure": []}) is None


def test_pick_social_exposure_prefers_social_else_none() -> None:
    rng = random.Random(0)
    assert pick_social_exposure([_PAPER, _SNS, _TV], rng) == _SNS
    assert pick_social_exposure([_PAPER, _TV], rng) is None


def test_reaction_pick_exposure_uses_social_candidate() -> None:
    persona = SimpleNamespace(media_behavior={"exposure_candidates": [_PAPER, _SNS]})
    ctx = gemini_reaction._pick_exposure(persona, random.Random(1))
    assert "SNS" in ctx and "스마트폰/휴대폰" in ctx


def test_pick_exposure_never_falls_back_to_nonsocial() -> None:
    # Meta 전용 — 소셜 후보가 없어도 TV·신문 등 비소셜로는 절대 폴백하지 않는다(모순 차단).
    persona = SimpleNamespace(media_behavior={"exposure_candidates": [_PAPER, _TV]})
    ctx = gemini_reaction._pick_exposure(persona, random.Random(1))
    assert "TV" not in ctx and "신문/잡지/책" not in ctx


def _two_cell_sampler(*, sampling: bool) -> PersonaSampler:
    # 젊은 셀(소셜 0.8)·중년 셀(소셜 0.1), 인구 share 동일. ocean/consumption 은 실데이터 로드.
    population = {
        "bands": [
            {"age_band": "20-29", "share": 0.5, "male_ratio": 1.0},
            {"age_band": "50-59", "share": 0.5, "male_ratio": 1.0},
        ]
    }
    media = {
        "device_minutes": {"스마트폰/휴대폰": 100.0},  # 평면 폴백 안전망
        "cells": {
            "20-29|M": {
                "device_minutes": {"스마트폰/휴대폰": 100.0},
                "daily_media_minutes": {"mean": 200.0, "sd": 10.0},
                "exposure": [{**_SNS, "p": 0.8}, {**_PAPER, "p": 0.2}],
            },
            "50-59|M": {
                "device_minutes": {"신문/잡지/책": 100.0},
                "daily_media_minutes": {"mean": 200.0, "sd": 10.0},
                "exposure": [{**_SNS, "p": 0.1}, {**_PAPER, "p": 0.9}],
            },
        },
    }
    return PersonaSampler(population=population, media=media, reachability_sampling=sampling)


def test_reachability_sampling_skews_toward_high_reach_cells() -> None:
    # 추출분포가 인구×reach 로 바뀌어 표본이 도달성 높은 젊은 셀에 집중(손곡선 아님, 데이터 유도).
    on = _two_cell_sampler(sampling=True).sample(PanelSpec(size=400, seed=1))
    off = _two_cell_sampler(sampling=False).sample(PanelSpec(size=400, seed=1))
    young_on = sum(1 for p in on if p.age < 40) / len(on)
    young_off = sum(1 for p in off if p.age < 40) / len(off)
    assert young_on > young_off  # 도달성 샘플링이 젊은 층으로 치우침
    assert young_on > 0.7  # reach 0.8 vs 0.1 → 압도적 젊은
    assert abs(young_off - 0.5) < 0.1  # OFF — 인구 비례(반반)
    assert all(p.weight == 1.0 for p in on)  # self-weighting 유지(가중 아님)


def test_social_feed_reach_recorded_on_persona() -> None:
    personas = _two_cell_sampler(sampling=True).sample(PanelSpec(size=50, seed=2))
    young = [p for p in personas if p.age < 40]
    assert young, "젊은 셀 표본 없음"
    assert young[0].media_behavior["social_feed_reach"] == 0.8  # 투명성 위해 비중 기록
