# Deep-top 전환 대비 — Management 검증·대비 문서

> 목적. 팀원이 채팅 오케스트레이터를 **deep-top**(deep agent를 최상위 라우터로)으로 바꿔 올 때,
> management 트랙이 깨지지 않게 미리 구조를 기록하고 검증 체크리스트를 남긴다.
> deep-top **구현 방식이 미정**이라 "어느 방식이든 확인할 것"을 기준으로 적는다.
> 작성 시점 2026-06-30 (브랜치 `feat/management-boeun`). 마감 구현 07-08 / 발표 07-14.
> 관련 조율: [[generation-to-management-handoff-조율]] · 챗 캠페인 조치(트랙 H).

---

## 0. 한 줄 요약

사용자가 원하는 흐름 — **"새 캠페인 만들거야" → 인라인 생성 폼 → 채워서 제출 → "취소(좌)/승인(우)"
확인 → 집행 시 Meta 쓰기** — 은 UI·백엔드가 **이미 전부 구현돼 있다.** 유일하게 깨진 지점은
**채팅 발화가 그 카드까지 도달하는 라우팅**이고, 그건 deep-top이 통째로 해결하는 부분이다.

---

## 1. 현재 구조 (classify-top)

```
메시지 → classify(경량 LLM, gpt-4o-mini)가 도메인 1개로 분류
        → route → {management | simulation | generator | advise | deep} 잎 1개
        → 단일 도메인이면 그 노드가 직접 처리(deep 안 거침)
```

- 결정론 트리거(`orchestrator.py:579-584`): `_SIM_RUN_RE`→simulation, `_GEN_RUN_RE`→generator,
  `[생성결과]`→gen_result. **deep로 가는 결정론 트리거는 없음.**
- deep는 LLM이 `intent="deep"`로 분류할 때만 도달. 프롬프트 정의가
  "여러 도메인을 엮는 복합 요청"이고 **"단일 도메인이면 deep 금지"**(`orchestrator.py:101-103`).
- `deep_runner`는 정상 주입됨(`chat.py:62-69`, 키 있으면 살아있음).

### 깨지는 지점

"새 캠페인 만들거야"는 단일 management로 분류 → `management_node`가 `action` 무시하고
`mgmt(AskRequest)`만 호출(`orchestrator.py:605-619`) → ask 에이전트는 **텍스트만** 생성.
`create_campaign` 위젯은 **deep agent에만** 존재(`deep_agent.py` create_campaign 툴)하므로
영영 도달하지 못함. → 인라인 폼이 안 뜬다.

---

## 2. 이미 완성된 것 (deep-top 와도 건드리지 말 것)

캠페인 생성 카드 **전 흐름이 구현 완료**다. 라우팅만 닿으면 그대로 동작한다.

| 단계 | 구현 위치 |
|---|---|
| 인라인 생성 폼 | `ChatCreateCampaignCard.tsx` phase=`form` → `CampaignForm` |
| 제안 생성(미집행) | `createProposal` → `api.management.createCampaignProposal` → `/campaigns/create-proposal` |
| 확인 미리보기 + **취소(좌)/승인(우)** | `CreateProposalPreview.tsx:58-72` (Tier3 사람승인 배지 포함) |
| 승인+집행 | `approveAndExecute` → `/approve` + `/execute`(`management.py:347,460`) |
| 결과 카드 | phase=`done` (성공/심사중/실패) |

- deep agent 쪽 신호 툴도 존재: `create_campaign`·`manage_campaign`·`run_simulation`
  (각각 widget `create_campaign`/`campaign_action`/`sim_form` emit, `deep_agent.py:751-776`).
- 프론트 렌더러도 존재: `ChatConversation.tsx:1772`(create_campaign), 이하 campaign_action/budget.

### ⚠️ Meta 쓰기 조건

`/execute`는 **항상 Meta에 쓰지 않는다**(`management.py:469-481`).
- `use_mock=True` 또는 데모 제안(TENANT_ID 센티넬) → **DRY_RUN**(계약만 검증, 실제 쓰기 없음).
- **실제 Meta 쓰기 = `use_mock=False` + 로그인 org에 연결된 Meta 광고계정(토큰)** 일 때만.

---

## 3. deep agent의 ask vs run (분류 기준)

deep agent 도구는 dispatch 동작으로 두 부류(`deep_agent.py:dispatch`).

- **ask 류**(`ask_management`·`ask_simulation`·`ask_generator`) — 서브에이전트에 위임해 **정보 반환**,
  ToolMessage로 LLM에 되먹여 **루프 계속**. 읽기, 상태 변경 없음.
- **run/action 류**(`create_campaign`·`manage_campaign`·`run_simulation`) — 인자만 추출해 **state 신호**
  (create_prefill/campaign_action/sim_form) 세팅하고 **루프 즉시 종료**. widget으로 변환돼 폼·카드 렌더.
  **직접 집행 아님** — 사람에게 제어 이양(HITL). 실제 실행은 사람이 승인 → executor 경유.

> 핵심: deep에서 "run"은 *execute*가 아니라 *"폼/카드를 띄워 사람에게 넘긴다"*. HITL 불변식
> ("모든 spend는 executor 경유")과 충돌하지 않는다.

---

## 4. deep-top일 때의 흐름

```
메시지 → (classify 없음) → 바로 deep agent.run()
        → plan_node: 할일 분해(단순하면 빈 계획)
        → orchestrate: LLM이 도구 스펙 보고 도구 선택        ← 여기가 라우터
        → dispatch: 고른 도구 실행 (ask=위임·계속 / run=신호·종료)
        → _state_to_result → meta.widget/cards → chat.py SSE
```

"새 캠페인 만들거야"의 라우팅 근거가 **classify 프롬프트 → deep agent 내부**로 이동한다.
- 시스템 프롬프트 규칙(`deep_agent.py:42`): "새 캠페인 생성 요청 → create_campaign 호출"
- 도구 description(`deep_agent.py:86-90`): "사용자가 새 캠페인 만들어 달라 할 때 호출…"

→ orchestrate LLM이 이 스펙을 읽고 `create_campaign` 툴콜 → widget → 카드. **별도 분류 단계 없음**
(라우팅이 도구 선택과 한 몸).

---

## 5. classify ↔ deep agent 분류 지식 대조

deep-top은 "classify를 이식"이 아니라 **"분류 골격은 이미 deep에 있고, classify의 디테일·부수책임을
재배치"** 다. 골격은 `_SYS_ORCHESTRATOR`(`deep_agent.py:33-47`) + 도구 description에 존재.

| classify(`_CLASSIFY_SYSTEM`) 항목 | deep agent에 있나 | 비고 |
|---|---|---|
| management = 집행 후 운영·성과·예산 | ✅ | ask_management 규칙·desc |
| simulation = 집행 전 KPI·결과 해석 | ✅ | ask_simulation desc "집행 전" 명시 |
| generator = 시안·카피 생성 | ✅ | ask_generator |
| action(생성/조치/실행) | ✅ | create/manage/run 툴 |
| advise(일반 전략·잡담) | △ 암묵 | "충분하면 도구 없이 답"뿐, 명시 분기 아님 |
| **is_ad_domain (P12 과금 한도)** | ❌ | deep에 개념 부재 → 별도 게이트 필요 |
| 세밀 경계 규칙(KPI 정의=sim, 시안 집행=management, PDF·요약=ask 등) | ❌ 부족 | classify엔 디테일 多, deep엔 한 줄씩 |
| **list/select(목록·선택 위젯)** | ❌ | deep 도구에 없음 |

---

## 6. deep-top 설계 시나리오별 — management 확인 사항

팀원이 둘 중 어느 쪽으로 구현하든 검증 포인트가 다르다.

### 시나리오 A. 순수 deep-top (classify 완전 제거)
- 모든 발화 deep行. is_ad_domain·list/select·advise까지 deep 안에서 처리.
- **확인할 것**
  - [ ] "새 캠페인 만들거야"가 deep로 들어가 `create_campaign` 툴콜이 나는가.
  - [ ] P12 광고/비광고 한도 판정이 어디서 이뤄지는가(누락 시 과금 게이트 구멍).
  - [ ] campaign_action(pause/budget) widget도 같은 식으로 도달하는가.
  - [ ] 단순 발화("안녕")까지 plan+orchestrate 비용을 무는지(지연·비용).

### 시나리오 B. deep + 얇은 프리라우터 (classify 축소 잔존)
- "P12 판정 + 명백 트리거 fast-path + 잡담 즉답"만 남기고 나머지 deep.
- **확인할 것**
  - [ ] 프리라우터가 캠페인 생성/조치를 deep로 넘기는가(아니면 또 management로 샘).
  - [ ] 기존 `sim_form`/`gen_form` 결정론 트리거가 프리라우터에 보존되는가(이중 emit 충돌 주의).
  - [ ] management의 `suggested_action`(ACTIONBAR) 경로가 살아있는지/제거되는지.

### 공통 확인
- [ ] `meta.widget.type` 계약(create_campaign/campaign_action/sim_form)이 그대로 유지되는가
      (프론트 렌더러가 이걸로 분기 — `ChatConversation.tsx:1772~`).
- [ ] `_state_to_result`의 `source` 고정 규칙(create/manage=deep-agent, sim_form=simulation)이
      chat.py 카드 게이트(`_cards_from_meta`)와 안 어긋나는가.
- [ ] HITL 불변식(run 툴은 폼·카드만, 집행은 executor) 유지되는가.

---

## 7. management 미연결 인벤토리 (deep-top과 별개로 정리 대상)

검증 결과 실제 코드 갭은 ①②뿐. ③은 의도적, ④⑤는 갭 아님.

| # | 항목 | 실제 갭? | 근거 | 처리 |
|---|---|---|---|---|
| ① | ACTIONBAR(composer) 실행 버튼 죽음 | **O 레거시** | `composer.py:96-127` `wired:False` "실행 API 미연결(Plan 2)" — 하지만 `/approve`·`/execute` 존재하고 deep 카드 흐름이 이미 사용 | 제거 or 카드 흐름으로 통일 |
| ② | `start_regeneration`/`check_regeneration` | **O 죽은 래퍼** | `execution/assistant_tools.py:25,31` 호출처 0. 재생성 기능은 라우터로 배선됨(`/regenerate*`), 래퍼만 챗그래프 미연결 | 챗그래프 배선 or 삭제 |
| ③ | ask 그래프에 실행 도구 없음 | △ 의도적 | `graph.py:211-221` read+propose_action만. HITL 경계상 정상 | 유지 |
| ④ | 시뮬 예측 reader | X 데이터 의존 | `prediction_adapters.py:40-80` 실 SQL 조회, `wiring.py:84-95` 배선됨. None은 데이터/링크 없을 때 | 시뮬 링크 데이터 필요 |
| ⑤ | MockAdPlatform "stub" | X 코멘트 stale | `wiring.py:16` 코멘트와 달리 `mock.py:41-384` 풀 구현 | 코멘트 정리 |

> ①은 deep-top 방향(run을 deep 카드로 일원화)과 정확히 같은 선택지다. deep-top이 카드 흐름으로
> 통일하면 ①ACTIONBAR·②죽은 래퍼는 자연 소멸 후보.

---

## 8. deep-top 도착 전 임시방편(stopgap) — 선택

데모가 deep-top보다 먼저 필요하면, classify에 결정론 트리거만 5줄 추가해 즉시 뚫을 수 있다.
**deep-top 전환 시 제거될 임시 코드**임을 주석으로 명시한다.

```python
# orchestrator.py classify() — deep-top 전환 시 제거(임시): 캠페인 생성 발화를 deep로
_CAMPAIGN_CREATE_RE = re.compile(r"(새\s*)?(광고\s*)?캠페인\s*[을를]?\s*(만들|생성|추가|새로)")
if _CAMPAIGN_CREATE_RE.search(q):
    return {"intent": "deep", "action": "run", "confidence": "high", "is_ad_domain": True}
```

이러면 deep → `create_campaign` → widget → `ChatCreateCampaignCard` 인라인 → 폼 → 취소/승인 → 집행.
단 §2의 Meta 쓰기 조건(라이브 모드 + Meta 연결)은 별개로 충족돼야 실제 쓰기까지 간다.

---

## 9. 결론

- 원하는 캠페인 생성 흐름은 **이미 다 만들어져 있고, 막힌 건 라우팅 한 곳**이다.
- deep-top은 그 라우팅을 "classify 분류"에서 "deep 도구 선택"으로 옮겨 **문제 자체를 없앤다.**
- deep agent엔 **분류 골격이 이미 존재**하므로, 팀원 작업은 보통 "classify 디테일·부수책임(P12·
  list/select·advise·세밀 경계) 재배치"로 귀결된다.
- management 트랙은 §6 체크리스트로 **deep-top 도착 시 검증**하고, §7 ①②는 deep-top과 무관하게
  레거시 정리 대상으로 둔다.
