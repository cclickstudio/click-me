# 채팅 "시뮬 돌린 걸로 집행" 배선 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 채팅에서 "시뮬 돌린 걸로 집행 폼 띄워줘" 발화 시 시뮬 결과(이름·KPI)가 프리필된 from-simulation 집행 카드가 뜨게 한다.

**Architecture:** 딥에이전트에 신규 도구 `execute_from_simulation`을 추가해 최근 완료 시뮬을 해석하고(`improve_context` 재사용), 신규 위젯 `exec_from_sim`으로 프론트에 신호를 보내면 ChatConversation이 기존 `ExecuteFromSimulation` 컴포넌트를 임베드한다(알림센터와 동일 패턴). 이후 게이트 판정→from-simulation→approve→execute는 기존 그대로.

**Tech Stack:** FastAPI + LangGraph @tool (backend/uv) · Next.js + TS (frontend/pnpm)

**Spec:** `docs/superpowers/specs/2026-07-09-chat-execute-from-simulation-design.md`

**전제 지식 (이 코드베이스 특이사항)**

- 백엔드 pytest는 **경로 인자 금지** — `cd backend && uv run pytest -k "<필터>" -q`만 사용. 경로를 주면 pyproject의 `testpaths=["../test/backend"]` 설정이 안 실려 ModuleNotFoundError 가짜 실패가 대량 발생한다.
- 테스트 파일은 `test/backend/`(레포 루트)에 있다. `backend/tests/`는 pycache만 남은 빈 껍데기.
- 백엔드 .py 수정 후 커밋 전 `cd backend && uv run ruff format . && uv run ruff check . --fix` 필수(CI가 ruff 검증).
- 커밋 컨벤션은 `타입: 한국어 설명` (add/delete/edit/fix). 새 .py 파일 첫 줄엔 한국어 헤더 주석.
- pnpm은 frontend 전용, uv는 backend 전용 — 교차 금지.

---

### Task 1: `exec_from_sim` 위젯 함수 (backend)

**Files:**
- Modify: `backend/domain/chat/widgets.py` (create_campaign 함수 아래, 90행 근처)
- Test: `test/backend/chat/test_widgets.py` (기존 파일에 테스트 추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/chat/test_widgets.py` 끝에 추가:

```python
def test_exec_from_sim_widget_shape():
    from domain.chat import widgets

    data = {
        "simulation_id": "sim-1",
        "default_name": "수분크림 광고",
        "click_intent_rate": 0.042,
        "rejection_rate": 0.08,
        "link_url": "https://example.com",
        "daily_budget_krw": 20000,
        "start_date": "2026-07-10",
        "end_date": None,
    }
    out = widgets.exec_from_sim(data)
    assert out["widget"]["type"] == "exec_from_sim"
    assert out["widget"]["data"]["simulation_id"] == "sim-1"
    assert out["source"] == "deep-agent"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest -k "exec_from_sim_widget" -q`
Expected: FAIL — `AttributeError: module 'domain.chat.widgets' has no attribute 'exec_from_sim'`

- [ ] **Step 3: 최소 구현**

`backend/domain/chat/widgets.py`의 `create_campaign` 함수 아래에 추가:

```python
def exec_from_sim(data: dict) -> dict:
    """시뮬 결과 집행 카드 — data={simulation_id, default_name, click_intent_rate,
    rejection_rate, link_url?, daily_budget_krw?, start_date?, end_date?}. source 고정."""
    return {"widget": {"type": "exec_from_sim", "data": data}, "source": DEEP_AGENT}
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest -k "exec_from_sim_widget" -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/widgets.py test/backend/chat/test_widgets.py
git commit -m "add: exec_from_sim 위젯 신호 — 시뮬 결과 집행 카드용"
```

---

### Task 2: `execute_from_simulation` 도구 (backend)

**Files:**
- Modify: `backend/api/assistant/subagent_tools.py` — `create_campaign` 도구(892행 근처) 아래에 도구 추가 + 1201행 근처 `return [...]` 리스트에 등록
- Create: `test/backend/chat/test_execute_from_simulation_tool.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/chat/test_execute_from_simulation_tool.py` 신규 생성 (`test_improve_tool.py`와 동일 스타일 — @tool 래퍼의 `.coroutine` 직접 호출, DB 미접근):

```python
# execute_from_simulation tool 골든 — improve_context 스텁으로 위젯 신호·안내 분기 검증(DB 미접근)
"""test_improve_tool.py와 동일하게 @tool 래퍼의 .coroutine으로 직접 호출한다."""

import pytest

from api.assistant import improve_context
from api.assistant.subagent_tools import build_chat_tools
from core.config import settings

_SRC = {
    "ad_title": "수분크림 광고",
    "ad_asset_url": "simulation/abc.png",
    "sample_size": 10,
    "aggregate": {
        "purchase_intent": 3.2,
        "rejection_rate": 0.08,
        "trust_avg": 3.5,
        "click_intent_rate": 0.042,
    },
    "plain_summary": None,
    "ranked_actions": [],
    "product_cutout_s3_key": None,
}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in build_chat_tools(settings)}


def _state(**kw):
    base = {
        "project_id": None,
        "session_id": "t",
        "user_id": None,
        "org_id": None,
        "messages": [],
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_emits_exec_card_with_sim_values(tools, monkeypatch):
    captured = {}

    async def _fake(sid, org_id=None):
        captured["sid"] = sid
        return dict(_SRC)

    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    cmd = await tools["execute_from_simulation"].coroutine(
        simulation_id="sim-1", state=_state(), tool_call_id="t1"
    )
    w = cmd.update["widget"]
    assert w["type"] == "exec_from_sim"
    assert w["data"]["simulation_id"] == "sim-1"
    assert w["data"]["default_name"] == "수분크림 광고"
    assert w["data"]["click_intent_rate"] == 0.042
    assert w["data"]["rejection_rate"] == 0.08
    assert captured["sid"] == "sim-1"


@pytest.mark.asyncio
async def test_utterance_values_prefill_and_override_name(tools, monkeypatch):
    async def _fake(sid, org_id=None):
        return dict(_SRC)

    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    cmd = await tools["execute_from_simulation"].coroutine(
        simulation_id="sim-1",
        campaign_name="7월 프로모션",
        link_url="https://example.com",
        daily_budget_krw=20000,
        start_date="2026-07-10",
        state=_state(),
        tool_call_id="t1",
    )
    d = cmd.update["widget"]["data"]
    assert d["default_name"] == "7월 프로모션"  # 발화 이름이 시뮬 제목보다 우선
    assert d["link_url"] == "https://example.com"
    assert d["daily_budget_krw"] == 20000
    assert d["start_date"] == "2026-07-10"
    assert d["end_date"] is None


@pytest.mark.asyncio
async def test_auto_selects_latest_completed_and_records_history(tools, monkeypatch):
    # project_id가 있으면 spawn_record_execution이 DB 백그라운드 적재를 시도하므로
    # 스텁으로 막고(DB 미접근 유지) 호출 계약(요청 기록)만 고정한다.
    from domain.chat import helpers

    recorded = {}

    async def _latest(project_id):
        return "sim-latest" if project_id == "p1" else None

    async def _fake(sid, org_id=None):
        return dict(_SRC) if sid == "sim-latest" else None

    def _record(project_id, feature_type, action, summary, payload):
        recorded["project_id"] = project_id
        recorded["action"] = action

    monkeypatch.setattr(improve_context, "latest_completed_simulation_id", _latest)
    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    monkeypatch.setattr(helpers, "spawn_record_execution", _record)
    cmd = await tools["execute_from_simulation"].coroutine(
        state=_state(project_id="p1"), tool_call_id="t1"
    )
    assert cmd.update["widget"]["data"]["simulation_id"] == "sim-latest"
    assert recorded["action"] == "execute_from_simulation_request"
    assert recorded["project_id"] == "p1"


@pytest.mark.asyncio
async def test_no_project_no_sid_guides(tools):
    cmd = await tools["execute_from_simulation"].coroutine(state=_state(), tool_call_id="t1")
    assert "widget" not in cmd.update
    assert "프로젝트" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_no_completed_sim_guides(tools, monkeypatch):
    async def _latest(project_id):
        return None

    monkeypatch.setattr(improve_context, "latest_completed_simulation_id", _latest)
    cmd = await tools["execute_from_simulation"].coroutine(
        state=_state(project_id="p1"), tool_call_id="t1"
    )
    assert "widget" not in cmd.update
    assert "시뮬레이션" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_null_kpi_guides(tools, monkeypatch):
    async def _fake(sid, org_id=None):
        return {**_SRC, "aggregate": {**_SRC["aggregate"], "click_intent_rate": None}}

    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    cmd = await tools["execute_from_simulation"].coroutine(
        simulation_id="sim-1", state=_state(), tool_call_id="t1"
    )
    assert "widget" not in cmd.update
    assert "집계" in cmd.update["messages"][0].content
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest -k "test_execute_from_simulation_tool" -q`
Expected: FAIL — `KeyError: 'execute_from_simulation'` (도구 미등록)

- [ ] **Step 3: 도구 구현**

`backend/api/assistant/subagent_tools.py`의 `create_campaign` 도구 정의 바로 아래에 추가 (내부 함수이므로 같은 들여쓰기 레벨, `@tool` 데코레이터):

```python
    @tool
    async def execute_from_simulation(
        simulation_id: str = "",
        campaign_name: str = "",
        link_url: str = "",
        daily_budget_krw: int = 0,
        start_date: str = "",
        end_date: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """'시뮬 돌린 걸로/이 시뮬 결과로 캠페인 집행해줘·집행 폼 띄워줘' 발화 시 호출.
        발화에 있는 값만 채우고 없으면 비운다(지어내기 금지). '방금/아까 돌린'이면
        simulation_id를 비워라(최근 완료 시뮬 자동 선택). 예산은 원 단위 정수
        ('2만원'=20000), 날짜는 YYYY-MM-DD. 시뮬과 무관한 새 캠페인 백지 생성은
        create_campaign, 기존 캠페인 조작은 manage_campaign. 호출 후 한 줄로만 안내하라."""
        sid = simulation_id or ""
        if not sid:
            project_id = state.get("project_id") or ""
            if not project_id:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "집행할 시뮬레이션을 찾을 프로젝트가 없어요. "
                                "프로젝트를 선택하거나 시뮬레이션을 지정해주세요.",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
            sid = await improve_context.latest_completed_simulation_id(project_id) or ""
        src = None
        if sid:
            src = await improve_context.fetch_improve_source(sid, org_id=state.get("org_id"))
        if src is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "아직 완료된 시뮬레이션이 없어요. 먼저 시뮬레이션을 돌리면 "
                            "그 결과로 캠페인을 집행할 수 있어요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        agg = src.get("aggregate") or {}
        cir, rej = agg.get("click_intent_rate"), agg.get("rejection_rate")
        if cir is None or rej is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "시뮬 집계가 아직 없어요(미완료). 시뮬레이션이 끝난 뒤 "
                            "다시 시도해주세요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        data = {
            "simulation_id": sid,
            "default_name": campaign_name or src.get("ad_title") or "",
            "click_intent_rate": cir,
            "rejection_rate": rej,
            "link_url": link_url or None,
            "daily_budget_krw": daily_budget_krw or None,
            "start_date": start_date or None,
            "end_date": end_date or None,
        }
        # 실행 히스토리 적재 — 폼 시점 = '요청' 기록(집행 확정은 executor가 별도 기록).
        helpers.spawn_record_execution(
            state.get("project_id"),
            "management",
            "execute_from_simulation_request",
            f"시뮬 기반 집행 요청(폼) 시뮬 {sid}",
            {"simulation_id": sid, "stage": "request"},
        )
        return Command(
            update={
                **widgets.exec_from_sim(data),
                "messages": [
                    ToolMessage(
                        "시뮬 결과로 캠페인 집행 카드를 준비했어요. 확인 후 집행해 주세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
```

같은 파일 끝의 `return [` 리스트에서 `create_campaign,` 바로 다음 줄에 등록:

```python
        create_campaign,
        execute_from_simulation,
        manage_campaign,
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest -k "test_execute_from_simulation_tool" -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 회귀 확인 (채팅 도구 전체)**

Run: `cd backend && uv run pytest -k "chat or tool or widget" -q`
Expected: 전부 PASS (기존 run_improvement·create_campaign 테스트 포함)

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/assistant/subagent_tools.py test/backend/chat/test_execute_from_simulation_tool.py
git commit -m "add: 채팅 execute_from_simulation 도구 — 시뮬 결과 프리필 집행 카드 신호"
```

---

### Task 3: `ExecuteFromSimulation` initial 프롭 (frontend)

**Files:**
- Modify: `frontend/src/components/manage/ExecuteFromSimulation.tsx:12-46`

- [ ] **Step 1: 프롭 추가**

시그니처를 다음으로 교체 (기존 4개 프롭 유지 + 선택 4개 추가):

```tsx
export function ExecuteFromSimulation({
  simulationId,
  defaultName,
  clickIntentRate,
  rejectionRate,
  initialLinkUrl,
  initialBudget,
  initialStartDate,
  initialEndDate,
}: {
  simulationId: string;
  defaultName?: string;
  clickIntentRate: number;
  rejectionRate: number;
  initialLinkUrl?: string; // 챗 발화에서 추출된 프리필(없으면 기존 기본값)
  initialBudget?: number;
  initialStartDate?: string; // YYYY-MM-DD
  initialEndDate?: string;
}) {
```

state 초기값 4줄을 다음으로 교체 (`ExecuteFromSimulation.tsx:40-43`):

```tsx
  const [linkUrl, setLinkUrl] = useState(initialLinkUrl ?? '');
  const [budget, setBudget] = useState(initialBudget ?? 10000);
  const [startDate, setStartDate] = useState(
    () => initialStartDate || new Date().toISOString().slice(0, 10)
  );
  const [endDate, setEndDate] = useState(initialEndDate ?? '');
```

- [ ] **Step 2: 무회귀 확인 (기존 호출부는 프롭 미전달)**

Run: `cd frontend && pnpm build`
Expected: 빌드 성공. 기존 호출부(`SimulationResultView.tsx:181`, `AlarmCenter.tsx:347`)는 새 프롭을 안 넘기므로 `?? 기본값` 경로로 현행과 동일.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/manage/ExecuteFromSimulation.tsx
git commit -m "edit: ExecuteFromSimulation에 선택적 initial 프롭 — 챗 발화 프리필 수용"
```

---

### Task 4: ChatConversation `exec_from_sim` 렌더 분기 (frontend)

**Files:**
- Modify: `frontend/src/components/chat/ChatConversation.tsx` — ① import 추가 ② `WidgetSpec.data` 타입 확장(187행 근처) ③ 렌더 분기 추가(1917행 근처, create_campaign 분기 앞)

- [ ] **Step 1: import 추가**

기존 import 블록(파일 상단, `@/components/manage` 경로 import 근처)에 추가:

```tsx
import { ExecuteFromSimulation } from '@/components/manage/ExecuteFromSimulation';
```

- [ ] **Step 2: WidgetSpec.data 타입 확장**

`WidgetSpec` 타입의 `data` 객체(187행 근처, `simulation_id?: string;` 아래)에 추가:

```tsx
    // exec_from_sim 위젯 — 시뮬 결과 집행 카드(챗 발화 프리필 포함)
    default_name?: string;
    click_intent_rate?: number;
    rejection_rate?: number;
    link_url?: string;
    daily_budget_krw?: number;
    start_date?: string;
    end_date?: string;
```

- [ ] **Step 3: 렌더 분기 추가**

`{/* 챗→매니지먼트 카드(재이식) — deep_agent의 create_campaign/manage_campaign 신호 */}` 주석(1917행 근처) 바로 위에 추가:

```tsx
                    {/* 시뮬 결과 집행 카드 — deep_agent의 execute_from_simulation 신호.
                        KPI 2종은 백엔드가 항상 채우는 계약 — 없으면 렌더하지 않는다(가짜 0%/100% 표시 방지). */}
                    {msg.meta?.widget?.type === 'exec_from_sim' &&
                      msg.meta.widget.data?.simulation_id &&
                      typeof msg.meta.widget.data.click_intent_rate === 'number' &&
                      typeof msg.meta.widget.data.rejection_rate === 'number' && (
                        <div className='mt-1'>
                          <ExecuteFromSimulation
                            simulationId={msg.meta.widget.data.simulation_id}
                            defaultName={msg.meta.widget.data.default_name}
                            clickIntentRate={msg.meta.widget.data.click_intent_rate}
                            rejectionRate={msg.meta.widget.data.rejection_rate}
                            initialLinkUrl={msg.meta.widget.data.link_url}
                            initialBudget={msg.meta.widget.data.daily_budget_krw}
                            initialStartDate={msg.meta.widget.data.start_date}
                            initialEndDate={msg.meta.widget.data.end_date}
                          />
                        </div>
                      )}
```

(백엔드는 KPI 없는 위젯을 내보내지 않으므로(도구의 null 가드) 렌더 조건에서 숫자 타입을 요구 — 계약이 깨지면 가짜 수치 대신 위젯 미표시로 드러난다. 다른 위젯들의 `simulation_id` 필수 검사와 동일 방식.)

- [ ] **Step 4: 빌드 + 린트 확인**

Run: `cd frontend && pnpm build`
Expected: 빌드 성공 (타입 에러 없음)

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/chat/ChatConversation.tsx
git commit -m "add: 챗 exec_from_sim 위젯 렌더 — 시뮬 결과 집행 카드 임베드"
```

---

### Task 5: 전체 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && uv run pytest -q`
Expected: 전부 PASS (기존 831+ 및 신규 7개)

- [ ] **Step 2: 프론트 린트 + 빌드**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과

- [ ] **Step 3: 수동 시나리오 (dev 서버, 가능한 경우)**

백엔드 `cd backend && uv run uvicorn api.main:app --reload --port 8000` + 프론트 `cd frontend && pnpm dev` 후 채팅에서:

1. "시뮬 돌린 걸로 집행 폼 띄워줘" → exec_from_sim 카드 + [이 광고로 캠페인 집행] 버튼, 모달 이름 = 시뮬 광고 제목.
2. "예산 2만원, URL은 https://example.com 으로 방금 시뮬 집행해줘" → 모달에 예산 20000·URL 프리필.
3. 완료 시뮬 없는 프로젝트에서 1번 발화 → "아직 완료된 시뮬레이션이 없어요" 안내문.
4. 회귀: "새 캠페인 만들어줘" → 기존 create_campaign 백지 폼(오라우팅 없음).

- [ ] **Step 4: 스펙·계획 문서 커밋 (미커밋분 있으면)**

```bash
git add docs/superpowers/specs/2026-07-09-chat-execute-from-simulation-design.md docs/superpowers/plans/2026-07-09-chat-execute-from-simulation.md
git commit -m "edit: 시뮬→집행 배선 스펙 정정(안내문 폴백·평면 위젯 데이터) + 구현 계획"
```
