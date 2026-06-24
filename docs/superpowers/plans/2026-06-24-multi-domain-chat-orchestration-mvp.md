# 멀티도메인 챗 오케스트레이션 MVP 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗 라우팅을 chat.py의 `_is_management()` 이진 키워드 분기에서 **점수 매처 레지스트리(Router) + DomainAgent 계약 + composition root 등록** 구조로 교체한다(동작 보존, 도메인 추가는 등록 한 줄).

**Architecture:** 오케스트레이터 코어(`routing.py`·`contracts.py`·`registry.py`)는 Protocol과 등록된 인스턴스만 알고 도메인 내부를 import하지 않는다(의존성 역전). composition root(`bootstrap.py`)에서만 management를 import해 `ManagementDomainAgent` 어댑터로 감싸 등록한다. chat.py는 라우팅 판정과 에이전트 획득만 오케스트레이션으로 바꾸고 기존 카드 스트림(`_management_card_stream`)은 그대로 둔다.

**Tech Stack:** Python 3.12 · Pydantic v2 · pytest(`pytest-asyncio`) · uv · ruff.

설계 근거 — `docs/superpowers/specs/2026-06-24-multi-domain-chat-orchestration-design.md` (§5 Router · §7 계약/어댑터/composition root · §9 마이그레이션 · §11 테스트).

**Non-Goals (이 plan 밖):** 2단계 LLM 분류기·임베딩 매처, 공용 contracts 승격(B단계), sim/gen 도메인 에이전트, 멀티도메인 질문 분해. 전부 후속.

**현재 브랜치:** `feat/chat-boeun` (chat.py에 카드 스트림 `compose_turn`/`stream_turn` 이미 구현됨).

---

## File Structure

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `backend/api/orchestration/routing.py` | `IntentMatcher`·`KeywordMatcher`·`Candidate`·`RouteDecision`·`Router` (순수 로직) | 생성 |
| `backend/api/orchestration/contracts.py` | `DomainAgent` Protocol (도메인 import 없음) | 생성 |
| `backend/api/orchestration/registry.py` | `AgentRegistry` (domain→DomainAgent) | 생성 |
| `backend/api/orchestration/bootstrap.py` | composition root — `MGMT_KEYWORDS`·`ManagementDomainAgent`·`build_orchestration` | 생성 |
| `backend/api/orchestration/__init__.py` | 코어 공개 재노출(코어만 — bootstrap 제외) | 생성 |
| `backend/api/routers/chat.py` | 라우팅 판정·에이전트 획득을 오케스트레이션으로 교체 | 수정 |
| `backend/tests/orchestration/test_routing.py` | Router 점수·tie·ambiguous·default·candidates | 생성 |
| `backend/tests/orchestration/test_registry.py` | register/get | 생성 |
| `backend/tests/orchestration/test_bootstrap.py` | 어댑터 계약·build_orchestration 라우팅 | 생성 |
| `backend/tests/orchestration/test_import_purity.py` | 코어가 domain.management 미import (AST) | 생성 |
| `backend/tests/orchestration/test_chat_wiring.py` | chat `_resolve_domain` 판정 | 생성 |

---

## Task 1: Router 코어 (점수 매처 레지스트리)

**Files:**
- Create: `backend/api/orchestration/routing.py`
- Test: `backend/tests/orchestration/test_routing.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/orchestration/test_routing.py`:

```python
# Router 점수 라우팅 — 매칭·tie·ambiguous·default·candidates 검증
from api.orchestration.routing import Candidate, KeywordMatcher, Router


def _router_two():
    # 동점 검증용: 같은 키워드를 가진 두 도메인(등록 순서 zzz 먼저)
    return Router([KeywordMatcher("zzz", frozenset({"x"})), KeywordMatcher("aaa", frozenset({"x"}))])


def test_keyword_hit_routes_to_domain():
    r = Router([KeywordMatcher("management", frozenset({"캠페인", "예산"}))])
    d = r.route("이번 캠페인 예산 어때")
    assert d.domain == "management"
    assert d.score > 0.0


def test_no_hit_falls_back_to_default():
    r = Router([KeywordMatcher("management", frozenset({"캠페인"}))], default="clio")
    d = r.route("안녕하세요")
    assert d.domain == "clio"
    assert d.score == 0.0
    assert d.ambiguous is False


def test_tie_breaker_is_registration_order_not_domain_name():
    # 두 도메인 점수 동일 → 알파벳('aaa')이 아니라 등록 순서('zzz')가 이긴다
    d = _router_two().route("x")
    assert d.domain == "zzz"


def test_ambiguous_true_only_when_real_competitor():
    # 박빙 경쟁(점수 동일) → ambiguous True
    d = _router_two().route("x")
    assert d.ambiguous is True


def test_single_low_score_is_not_ambiguous():
    # 단독 저점수 후보는 ambiguous 아님(runner=0)
    r = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    d = r.route("캠페인")
    assert d.ambiguous is False


def test_candidates_preserved_in_decision():
    d = _router_two().route("x")
    assert d.candidates == tuple(sorted(d.candidates, key=lambda c: c.score, reverse=True))
    assert {c.domain for c in d.candidates} == {"zzz", "aaa"}
    assert all(isinstance(c, Candidate) for c in d.candidates)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_routing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.orchestration'`

- [ ] **Step 3: 최소 구현**

Create `backend/api/orchestration/routing.py`:

```python
# 의도 라우팅 — 도메인별 점수 매처를 비교해 최적 도메인 선택(1단계, 무비용·결정론)
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class IntentMatcher(Protocol):
    domain: str

    def score(self, query: str) -> float: ...


@dataclass(frozen=True)
class KeywordMatcher:
    domain: str
    keywords: frozenset[str]

    def score(self, query: str) -> float:
        low = query.lower()
        hits = sum(1 for k in self.keywords if k in low)
        return min(hits / 3, 1.0) if hits else 0.0


@dataclass(frozen=True)
class Candidate:
    domain: str
    score: float


@dataclass(frozen=True)
class RouteDecision:
    domain: str
    score: float
    ambiguous: bool
    candidates: tuple[Candidate, ...]


class Router:
    def __init__(self, matchers: list[IntentMatcher], default: str = "clio") -> None:
        self._matchers = list(matchers)
        self._default = default

    def route(self, query: str) -> RouteDecision:
        # 점수만 키로 안정 정렬 → 동점은 등록 순서 유지(domain 문자열 비의존)
        candidates = tuple(
            sorted(
                (Candidate(m.domain, m.score(query)) for m in self._matchers),
                key=lambda c: c.score,
                reverse=True,
            )
        )
        top = candidates[0] if candidates else None
        if top is None or top.score == 0.0:
            return RouteDecision(self._default, 0.0, False, candidates)
        runner = candidates[1].score if len(candidates) > 1 else 0.0
        ambiguous = runner > 0.0 and (top.score - runner) < 0.15
        return RouteDecision(top.domain, top.score, ambiguous, candidates)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_routing.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Ruff + 커밋**

```bash
(cd backend && uv run ruff format . && uv run ruff check . --fix)
git add backend/api/orchestration/routing.py backend/tests/orchestration/test_routing.py
git commit -m "add: 챗 오케스트레이션 점수 라우터(Router·KeywordMatcher)"
```

---

## Task 2: DomainAgent 계약 + 레지스트리

**Files:**
- Create: `backend/api/orchestration/contracts.py`
- Create: `backend/api/orchestration/registry.py`
- Test: `backend/tests/orchestration/test_registry.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/orchestration/test_registry.py`:

```python
# AgentRegistry — domain 문자열로 등록/조회
import pytest

from api.orchestration.registry import AgentRegistry


class _StubAgent:
    domain = "stub"

    async def ask(self, req):
        return req


def test_register_then_get_returns_agent():
    reg = AgentRegistry()
    agent = _StubAgent()
    reg.register(agent)
    assert reg.get("stub") is agent


def test_get_unknown_domain_returns_none():
    assert AgentRegistry().get("missing") is None


def test_duplicate_domain_registration_raises():
    reg = AgentRegistry()
    reg.register(_StubAgent())
    with pytest.raises(ValueError):
        reg.register(_StubAgent())


@pytest.mark.asyncio
async def test_registered_agent_ask_is_callable():
    reg = AgentRegistry()
    reg.register(_StubAgent())
    assert await reg.get("stub").ask("ping") == "ping"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.orchestration.registry'`

- [ ] **Step 3: 최소 구현**

Create `backend/api/orchestration/contracts.py`:

```python
# 오케스트레이터 ↔ 도메인 경계 계약 — 도메인 내부를 import하지 않는다(의존성 역전)
from __future__ import annotations

from typing import Any, Protocol


class DomainAgent(Protocol):
    domain: str

    async def ask(self, req: Any) -> Any: ...
```

Create `backend/api/orchestration/registry.py`:

```python
# 도메인 에이전트 레지스트리 — domain 문자열 → DomainAgent
from __future__ import annotations

from api.orchestration.contracts import DomainAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, DomainAgent] = {}

    def register(self, agent: DomainAgent) -> None:
        if agent.domain in self._agents:  # 중복 등록은 조용히 덮지 말고 명시적 실패
            raise ValueError(f"중복 도메인 등록: {agent.domain}")
        self._agents[agent.domain] = agent

    def get(self, domain: str) -> DomainAgent | None:
        return self._agents.get(domain)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_registry.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Ruff + 커밋**

```bash
(cd backend && uv run ruff format . && uv run ruff check . --fix)
git add backend/api/orchestration/contracts.py backend/api/orchestration/registry.py backend/tests/orchestration/test_registry.py
git commit -m "add: DomainAgent 계약 + AgentRegistry"
```

---

## Task 3: Composition root (bootstrap) + ManagementDomainAgent 어댑터

**Files:**
- Create: `backend/api/orchestration/bootstrap.py`
- Create: `backend/api/orchestration/__init__.py`
- Test: `backend/tests/orchestration/test_bootstrap.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/orchestration/test_bootstrap.py`:

```python
# bootstrap — 어댑터 계약 만족 + build_orchestration이 '등록'을 제대로 하는지(빌더는 stub)
import pytest

import api.orchestration.bootstrap as bootstrap
from api.orchestration.bootstrap import (
    MGMT_KEYWORDS,
    ManagementDomainAgent,
    build_orchestration,
)


def _patch_builder(monkeypatch):
    # 실제 management 에이전트 빌드를 우회 — composition root는 '등록'만 검증한다.
    # (실제 builder의 설정 필드 의존에서 테스트를 분리)
    async def _fake_ask(req):
        return req

    monkeypatch.setattr(bootstrap, "build_management_agent", lambda settings: _fake_ask)


@pytest.mark.asyncio
async def test_adapter_satisfies_domain_agent_contract():
    async def _ask(req):
        return f"ok:{req}"

    agent = ManagementDomainAgent(_ask)
    assert agent.domain == "management"
    assert await agent.ask("q") == "ok:q"


def test_build_orchestration_routes_management_keyword(monkeypatch):
    _patch_builder(monkeypatch)
    router, registry = build_orchestration(settings=object())
    assert router.route("이번 캠페인 예산 어때").domain == "management"
    assert registry.get("management") is not None
    assert registry.get("management").domain == "management"


def test_build_orchestration_non_keyword_is_default(monkeypatch):
    _patch_builder(monkeypatch)
    router, _ = build_orchestration(settings=object())
    assert router.route("안녕하세요").domain == "clio"


def test_mgmt_keywords_nonempty():
    assert "캠페인" in MGMT_KEYWORDS and len(MGMT_KEYWORDS) >= 10
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_bootstrap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.orchestration.bootstrap'`

- [ ] **Step 3: 최소 구현**

Create `backend/api/orchestration/bootstrap.py`:

```python
# 오케스트레이션 합성 루트 — 매처·도메인 에이전트 등록(여기서만 도메인 내부 import 허용)
from __future__ import annotations

from collections.abc import Awaitable, Callable

from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult

# 매니지먼트 라우팅 키워드(기존 chat.py에서 이전). 향후 도메인 소유로 분리 가능.
MGMT_KEYWORDS: frozenset[str] = frozenset(
    {
        "캠페인", "예산", "소진", "런레이트", "페이싱", "게재", "광고", "ctr",
        "roas", "cvr", "클릭률", "노출", "지출", "리드", "성과", "전환",
        "잔액", "일시중지", "멈춰", "증액", "감액", "소재", "예측대로", "매니지먼트",
    }
)


class ManagementDomainAgent:
    """기존 build_management_agent(함수 반환)를 DomainAgent 계약으로 감싸는 어댑터."""

    domain = "management"

    def __init__(self, ask: Callable[[AskRequest], Awaitable[AskResult]]) -> None:
        self._ask = ask

    async def ask(self, req: AskRequest) -> AskResult:
        return await self._ask(req)


def build_orchestration(settings) -> tuple[Router, AgentRegistry]:
    """라우터 + 레지스트리를 합성한다. 도메인 추가 = 여기 매처/에이전트 한 줄."""
    router = Router([KeywordMatcher("management", MGMT_KEYWORDS)])
    registry = AgentRegistry()
    registry.register(ManagementDomainAgent(build_management_agent(settings)))
    return router, registry
```

Create `backend/api/orchestration/__init__.py`:

```python
# 오케스트레이션 코어 공개 API — bootstrap(composition root)은 여기서 재노출하지 않는다(도메인 import 격리)
from api.orchestration.contracts import DomainAgent
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import (
    Candidate,
    IntentMatcher,
    KeywordMatcher,
    RouteDecision,
    Router,
)

__all__ = [
    "AgentRegistry",
    "Candidate",
    "DomainAgent",
    "IntentMatcher",
    "KeywordMatcher",
    "RouteDecision",
    "Router",
]
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_bootstrap.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Ruff + 커밋**

```bash
(cd backend && uv run ruff format . && uv run ruff check . --fix)
git add backend/api/orchestration/bootstrap.py backend/api/orchestration/__init__.py backend/tests/orchestration/test_bootstrap.py
git commit -m "add: 오케스트레이션 합성 루트 + ManagementDomainAgent 어댑터"
```

---

## Task 4: Import-purity 가드 (코어가 도메인 미import)

**Files:**
- Test: `backend/tests/orchestration/test_import_purity.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/orchestration/test_import_purity.py`:

```python
# 오케스트레이터 코어가 domain.management 내부를 직접 import하지 않음(등록/bootstrap만 예외)
import ast
import pathlib

_CORE = ("routing.py", "contracts.py", "registry.py")
_FORBIDDEN = "domain.management"


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(n.name for n in node.names)
    return mods


def test_core_modules_do_not_import_management():
    base = pathlib.Path(__file__).resolve().parents[2] / "api" / "orchestration"
    for name in _CORE:
        for mod in _imports(base / name):
            assert not mod.startswith(_FORBIDDEN), f"{name} imports {mod}"


def test_bootstrap_is_allowed_to_import_management():
    # 대조군 — bootstrap(composition root)은 도메인 import가 허용됨
    base = pathlib.Path(__file__).resolve().parents[2] / "api" / "orchestration"
    assert any(m.startswith(_FORBIDDEN) for m in _imports(base / "bootstrap.py"))
```

- [ ] **Step 2: 실패 확인 후 통과 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_import_purity.py -v`
Expected: PASS (2 passed) — 코어는 도메인 미import, bootstrap만 import. (만약 실패하면 코어에 새 도메인 import가 샌 것 → 제거.)

- [ ] **Step 3: Ruff + 커밋**

```bash
(cd backend && uv run ruff format . && uv run ruff check . --fix)
git add backend/tests/orchestration/test_import_purity.py
git commit -m "add: 오케스트레이터 코어 import-purity 가드 테스트"
```

---

## Task 5: chat.py 배선 — 라우팅 판정·에이전트 획득 교체

**Files:**
- Modify: `backend/api/routers/chat.py`
- Test: `backend/tests/orchestration/test_chat_wiring.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/orchestration/test_chat_wiring.py`:

```python
# chat._resolve_domain — 라우터 판정이 도메인 문자열을 돌려준다(에이전트 빌드 없이 주입)
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router


def test_resolve_domain_uses_router(monkeypatch):
    import api.routers.chat as chat

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    # monkeypatch로 주입 → 테스트 종료 시 자동 복원(전역 _orchestration 오염 방지)
    monkeypatch.setattr(chat, "_orchestration", (router, AgentRegistry()))

    assert chat._resolve_domain("이번 캠페인 예산?") == "management"
    assert chat._resolve_domain("안녕") == "clio"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/orchestration/test_chat_wiring.py -v`
Expected: FAIL — `AttributeError: module 'api.routers.chat' has no attribute '_resolve_domain'`

- [ ] **Step 3: chat.py 수정 — import 교체**

`backend/api/routers/chat.py` 14행 `from domain.management.assistant.agent import build_management_agent` 를 삭제하고, 17행 뒤에 다음을 추가:

```python
from api.orchestration.bootstrap import build_orchestration
```

(결과 import 블록 — `composer`·`contracts`·`history` import는 유지, `agent` import만 제거하고 `bootstrap` 추가.)

- [ ] **Step 4: chat.py 수정 — 키워드/획득 로직 교체**

`backend/api/routers/chat.py` 48–91행의 블록 전체(`# ── 최소 오케스트레이션 …` 주석부터 `_is_management` 함수 끝까지: `_MGMT_KEYWORDS`·`_assistant`·`_get_assistant`·`_is_management`)를 다음으로 교체:

```python
# ── 오케스트레이션: 점수 라우터 + 도메인 에이전트 레지스트리(합성은 bootstrap) ──
# 도메인 추가는 bootstrap.build_orchestration의 매처/에이전트 등록으로. 여기선 판정·획득만.
_orchestration = None


def _get_orchestration():
    global _orchestration
    if _orchestration is None:
        _orchestration = build_orchestration(settings)
    return _orchestration


def _resolve_domain(text: str) -> str:
    router, _ = _get_orchestration()
    return router.route(text).domain
```

- [ ] **Step 5: chat.py 수정 — generate() 분기 교체**

`backend/api/routers/chat.py`의 `generate()` 안 매니지먼트 분기(`if _is_management(last_message):` 블록)를 다음으로 교체:

```python
        # MVP 임시 분기 — sim/gen 도메인 에이전트 등록 전까지 management만 카드 스트림에 연결한다.
        # (도메인 추가 시 이 분기를 레지스트리 디스패치로 일반화)
        _, registry = _get_orchestration()
        domain = _resolve_domain(last_message)
        if domain == "management":
            agent = registry.get(domain)
            if agent is None:  # 정상 bootstrap이면 반드시 존재 — 없으면 설정 오류, 조용한 폴백 금지
                raise RuntimeError("management로 라우팅됐으나 에이전트 미등록 — bootstrap 설정 오류")
            async for chunk in _management_card_stream(
                question=last_message,
                session_id=body.session_id,
                ad_id=body.context_ad_id,
                assistant=agent.ask,
                record=_record_management_turn,
            ):
                yield chunk
            return
```

(나머지 CLIO 분기·`_management_card_stream`·`_record_management_turn`은 변경 없음.)

- [ ] **Step 6: 통과 확인 + 회귀 확인**

Run: `cd backend && uv run pytest tests/orchestration/ -v`
Expected: PASS (전체 orchestration 테스트 통과)

Run: `cd backend && uv run pytest tests/management/ -v`
Expected: PASS (기존 매니지먼트/카드 테스트 회귀 없음)

- [ ] **Step 7: Ruff + 커밋**

```bash
(cd backend && uv run ruff format . && uv run ruff check . --fix)
git add backend/api/routers/chat.py backend/tests/orchestration/test_chat_wiring.py
git commit -m "edit: chat.py 라우팅을 점수 라우터+레지스트리 오케스트레이션으로 교체"
```

---

## 최종 검증

- [ ] **전체 테스트**

Run: `cd backend && uv run pytest tests/orchestration/ tests/management/ -v`
Expected: 전부 PASS

- [ ] **Ruff 클린**

Run: `cd backend && uv run ruff check .`
Expected: `All checks passed!`

- [ ] **수동 확인(선택)** — 서버 기동 후 `/api/chat/complete`에 매니지먼트 키워드 질문 → 카드 SSE, 일반 질문 → CLIO `token/done` 인지 확인.

Run: `cd backend && uv run uvicorn api.main:app --reload --port 8000`
