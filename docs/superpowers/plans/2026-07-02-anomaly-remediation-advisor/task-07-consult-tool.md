# Task 7: 보조 진입 — `consult_anomaly` 도구 (⚠ 공통부, 사전 공지)

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/api/assistant/subagent_tools.py` (`recall` 도구 정의 뒤, return 리스트 직전에 추가)

⚠ subagent_tools.py는 챗 공통부 — append-only 1개 도구 추가지만 챗 담당에게 사전 공지.
로직은 전부 domain(advisor) 위임, 여기는 얇은 래퍼만. 위젯 없음(ToolMessage 텍스트만) —
LLM이 결과를 읽고 필요 시 기존 위젯 도구를 이어서 호출한다.

- [ ] **Step 1: 도구 추가**

`recall` 도구 정의와 `return [` 사이에 추가:
```python
    # ───────────────────────── 매니지먼트 이상 상담 (위임: domain/management/remediation) ──
    @tool
    async def consult_anomaly(
        campaign_id: str = "",
        campaign_name: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """캠페인이 '왜 안 좋은지/이상 있는지/문제 없는지' 물으면 호출. 서버 실측으로
        재검증해 이상이면 조치 옵션을, 정상이면 정상 확인을 답한다. 이름만 알면 campaign_name."""
        from domain.management.remediation.advisor import (  # noqa: PLC0415
            consult,
            find_campaign_id,
        )

        cid = campaign_id or (
            await find_campaign_id(settings, campaign_name) if campaign_name else None
        )
        if not cid:
            text_out = "캠페인을 특정하지 못했어요. 캠페인 이름이나 ID를 알려 주세요."
        else:
            res = await consult(settings, cid)
            if res is None:
                text_out = "실측 조회에 실패해 지금은 확인할 수 없어요. 잠시 후 다시 시도해 주세요."
            else:
                text_out = res.message
                if res.options:
                    # 기계가독 매핑 — LLM이 번호→도구를 오매핑하지 않게 명시(meta 미영속의 보완).
                    mapping = ", ".join(
                        f"{o.index}={o.action.value}({o.tool_hint or '관망'})"
                        for o in res.options
                    )
                    text_out += f"\n\n[옵션-도구 매핑 · campaign_id={cid}] {mapping}"
        return Command(
            update={"messages": [ToolMessage(text_out, tool_call_id=tool_call_id)]}
        )
```

> 한계(의도된 결정): 도구 경로 consult는 meta를 영속하지 않는다 — 옵션이 직전 대화
> 텍스트에 있어 LLM이 자연히 읽고, meta를 심으면 sink의 전용 세션 dedup 체계와 어긋난다.
> 부작용: 도구 경로 상담은 벨 쿨다운에 안 잡혀 벨+채팅이 각각 올 수 있음(서로 다른 표면 — 허용).

그리고 return 리스트의 `manage_campaign,` 다음 줄에 `consult_anomaly,` 추가.

- [ ] **Step 2: 임포트 스모크 확인**

Run: `cd backend && uv run python -c "from api.assistant.subagent_tools import build_chat_tools; from core.config import settings; tools = build_chat_tools(settings); print([t.name for t in tools])"`
Expected: 목록에 `consult_anomaly` 포함, 예외 없음

- [ ] **Step 3: 커밋**

```bash
git add backend/api/assistant/subagent_tools.py
git commit -m "add: 채팅 consult_anomaly 도구 — 이상 재검증·조치 옵션 보조 진입(위임만)"
```
