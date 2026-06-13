# 고정 패널 빌드·캐시·로드 (§3.6) — 샘플러(P2) + 4-a 서사 → 패널 1회 빌드, 런타임은 로드만
#
# A/B 비교 타당성·비용 구조의 전제: 시뮬레이션마다 재생성✗. 캐시 대상은 프로필(서사)뿐, 반응 아님.
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from domain.simulation.contracts.schemas import PanelSpec, Persona

# 서사 길이 QA 경계 — 빈/실패/과도 응답 제거(모순 프로필 게이트).
_QA_MIN_LEN = 10
_QA_MAX_LEN = 2000

# tools/panel/builder.py → domain/simulation/data/panels
_PANEL_DIR = Path(__file__).resolve().parents[2] / "data" / "panels"


def _qa_ok(narrative: str) -> bool:
    return _QA_MIN_LEN <= len(narrative.strip()) <= _QA_MAX_LEN


def filter_personas(personas: list[Persona], target_filter: dict | None) -> list[Persona]:
    """캐시 패널을 target_filter(gender/age_min/age_max)로 필터 — 동일 패널 부분집합."""
    tf = target_filter or {}
    gender = tf.get("gender")
    age_min = int(tf.get("age_min", 0))
    age_max = int(tf.get("age_max", 200))
    return [
        p
        for p in personas
        if (gender is None or p.gender == gender) and age_min <= p.age <= age_max
    ]


class PanelBuilder:
    """샘플러로 속성을 뽑고 narrator로 4-a 서사를 채워 패널을 빌드. 빌드 QA로 모순 프로필 제거."""

    def __init__(self, *, sampler, narrator) -> None:
        self._sampler = sampler
        self._narrator = narrator

    def build(self, spec: PanelSpec) -> dict[str, Any]:
        personas = self._sampler.sample(spec)
        built: list[dict] = []
        dropped = 0
        for p in personas:
            try:
                narrative = self._narrator.narrate(p)
            except Exception:
                narrative = ""
            if not _qa_ok(narrative):
                dropped += 1
                continue
            built.append(p.model_copy(update={"profile_narrative": narrative}).model_dump())
        return {
            "version": spec.version,
            "seed": spec.seed,
            "requested_size": spec.size,
            "size": len(built),
            "dropped_qa": dropped,
            "narrator": getattr(self._narrator, "version", "unknown"),
            "built_at": int(time.time()),
            "personas": built,
        }


def save_panel(panel: dict[str, Any], path: Path | None = None) -> Path:
    path = path or (_PANEL_DIR / f"{panel['version']}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(panel, f, ensure_ascii=False, indent=2)
    return path


def load_panel(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class CachedPanelProvider:
    """캐시된 패널을 로드만 — 시뮬레이션 런에서 재생성하지 않는다(§3.6, §7 금지).

    MockPanelProvider 와 동일한 get_or_build 시그니처. target_filter 로 동일 패널 부분집합 반환.
    """

    def __init__(self, path: Path) -> None:
        self._panel = load_panel(path)
        self._personas = [Persona(**d) for d in self._panel["personas"]]

    async def get_or_build(self, spec: PanelSpec) -> tuple[str, list[Persona]]:
        selected = filter_personas(self._personas, spec.target_filter)
        return self._panel["version"], selected
