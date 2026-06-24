# 멀티도메인 챗 오케스트레이션 설계

| | |
|---|---|
| Date | 2026-06-24 |
| Domain | 공통부 (cross-team) · 레퍼런스 구현은 management(🅱) |
| Branch | feat/management-boeun |
| Status | Draft (설계 합의) |

> ⚠️ 공통부 변경 — 이 설계의 "DomainAgent 공통 계약"·오케스트레이터는 세 팀(simulation·
> management·generator) 공유 영역이다. management가 레퍼런스 구현을 가지므로 **초안 주도**에
> 적합하나, 확정은 **팀 합의**가 필요하다(협업 규칙: 타 도메인 내부 import 금지, 교환은 계약으로만).

## 1. 목표

챗을 매니지먼트 단일 도메인에서 **시뮬레이터(4-1)·매니지먼트(4-2)·생성(4-3)을 한 창구에서
다루는 공통 오케스트레이터**로 확장한다. CLAUDE.md가 "후순위(미정)"로 둔 오케스트레이터 본체에
해당한다.

### 검증 가능한 성공 기준
- MVP는 **명시 신호(키워드/점수) 기반 라우팅**으로 올바른 도메인에 보낸다. **맥락 기반 라우팅은
  2단계 LLM 분류기에서 확장**(후속).
- 도메인 추가가 **Router 알고리즘 수정 없이 matcher/agent 등록**만으로 끝난다(개방-폐쇄).
- 모든 도메인이 **동일한 `ask(AskRequest) -> AskResult` 계약**으로 챗에 꽂힌다.
- 오케스트레이터가 도메인 **내부를 직접 import 하지 않는다**(계약으로만 교환).
- 명확한 질문은 추가 비용·지연 없이 처리된다(LLM 라우팅은 애매할 때만).

## 2. 현재 상태 (As-Is)

`api/routers/chat.py`의 `_is_management()` — 26개 키워드 substring 검사로 **매니지먼트 vs CLIO
이진 분기**. chat.py 주석에 "공통 오케스트레이터 본체 정해지기 전의 임시 연결"로 명시됨.

한계.
- **이진**이라 sim/gen을 못 더한다. 단어가 겹치면(`광고`·`성과`·`소재`) 분기 불가.
- **불린**이라 "둘 다 후보"를 표현 못 해 LLM 폴백에 넘길 수 없다.
- 키워드가 chat.py에 박혀 있어 도메인 팀이 자기 라우팅 신호를 소유하지 못한다(공통부 동시수정 충돌).
- 이미 over-routing 존재 — `광고`가 키워드라 일반 광고 질문도 매니지먼트로 끌려간다.

> 시뮬·생성은 현재 챗 서브에이전트가 **없다**(REST/파이프라인만). 그린필드.

## 3. 키워드 vs Supervisor — 비교

| 기준 | 키워드 라우팅 (현재) | Supervisor + 계약 (제안) |
|---|---|---|
| 도메인 확장 | 이진, 키워드 충돌 | N개 깔끔 |
| 맥락 의존 질문 | "이거 어때?" 놓침 | LLM 분류로 잡음 |
| 멀티도메인 질문 | 불가 | 분해 가능 |
| 지연/비용 | 0 | 라우팅 홉(+LLM 시 비용) |
| 결정성/테스트 | 결정론, 쉬움 | LLM은 비결정 → 오분류 새 실패모드 |
| 팀 병렬 작업 | 막힘(chat.py 공통부) | 계약만 맞추면 안 막힘 |

**평결** — 도메인이 1개면 키워드가 낫다(Supervisor는 순수 오버헤드). 멀티도메인으로 가면 키워드는
구조적으로 무너지고 Supervisor가 결정적으로 낫다. 목표가 멀티도메인이므로 Supervisor로 가되,
**키워드의 무비용·결정론 장점을 1단계로 흡수하는 하이브리드**로 설계한다.

## 4. 아키텍처 (To-Be) — 하이브리드 라우팅 + 공통 계약

```
사용자 질문
   │
   ▼
┌──────────────────────── Orchestrator ────────────────────────┐
│  1단계  Router.route(query) → RouteDecision                   │
│         (점수 매처 레지스트리 · 무비용 · 결정론)               │
│            ├ ambiguous=False → 도메인 확정 (대부분, 지연 0)    │
│            └ ambiguous=True  → 2단계 (candidates 힌트 전달)    │
│                                                               │
│  2단계  LLM 분류기  ※ 후속 — 지금은 자리만(KeywordMatcher만)   │
│         candidates로 후보 좁혀 분류 → 도메인 확정             │
└────────────────────────────┬──────────────────────────────────┘
                             ▼  domain
        ┌────────────┬───────┴────────┬──────────────┐
        ▼            ▼                ▼              ▼
   management    simulation       generator     clio (default)
   .ask(req)     .ask(req)        .ask(req)      Gemini 일반답변
   ✅ 구현됨     ⬜ 신규(계약)     ⬜ 신규(계약)
        └────────────┴────────────────┘
              동일 계약: DomainAgent.ask(AskRequest) -> AskResult
              (도메인 내부 자유 · 통합은 계약으로만 = 경계규칙 준수)
                             │
                             ▼
                  AskResult → SSE (경로별 shape, §8):
                    CLIO=token/done · mgmt A=card stream · 장기=공통 카드
```

## 5. 1단계 라우터 — 점수 매처 레지스트리

불린이 아니라 **점수(0.0~1.0)를 반환하는 매처**들을 레지스트리에 등록하고, 라우터가 비교해 최적
도메인을 고른다. 도메인 추가 = 매처 등록 한 줄(개방-폐쇄).

```python
# routing.py — 의도 라우팅: 도메인별 매처를 점수로 비교해 최적 도메인 선택
from dataclasses import dataclass
from typing import Protocol

class IntentMatcher(Protocol):
    domain: str
    def score(self, query: str) -> float: ...   # 0.0~1.0

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
    candidates: tuple[Candidate, ...]      # 점수 내림차순 전체 후보(폴백·디버그)

class Router:
    def __init__(self, matchers, default="clio"):
        self._matchers = list(matchers)     # 등록 순서 = tie 우선순위(이름 무관)
        self._default = default

    def route(self, query: str) -> RouteDecision:
        # 점수만 키로 안정 정렬 → 동점은 등록 순서 유지(domain 문자열에 의존 안 함)
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
        # 경쟁 도메인이 실제로 있을 때(runner>0)만 애매 판정
        ambiguous = runner > 0.0 and (top.score - runner) < 0.15
        return RouteDecision(top.domain, top.score, ambiguous, candidates)
```

설계 결정 3가지.
1. **tie-breaker 이름 독립** — `key=lambda c: c.score` + 안정 정렬. 동점은 등록 순서로 깨지며
   domain 문자열에 의존하지 않는다(이름 바꿔도 라우팅 불변).
2. **candidates 보존** — `RouteDecision`이 전체 후보·점수를 남겨 LLM 폴백·관측이 박빙 후보를
   그대로 받는다.
3. **ambiguous 정밀화** — `runner > 0.0`일 때만 애매. 단독 저점수 후보를 잘못 애매로 찍어 불필요한
   LLM 호출을 부르지 않는다.

### 라우터의 위치 — 현재 상태 vs 장기 목표 (분리)
- **현재 상태 (As-Is)**: `KeywordMatcher` 1개로 충분. 점수 1단계만으로 매니지먼트 vs CLIO 분기.
  LLM 분류·임베딩 매처는 미구현(인터페이스 자리만 둠).
- **장기 목표 (지향, 보장 아님)**: 도메인·신호 방식이 늘어도 변경을 "끼우는" 형태로 흡수하는 것을
  지향한다. `route() → RouteDecision` 인터페이스를 되도록 안정적으로 유지하려 한다 — 단, 실제
  요구가 바뀌면 라우터도 진화할 수 있다(불변 약속이 아니라 설계 의도).

### MVP 한계 — substring 과매칭
`KeywordMatcher`는 substring 기반이라 넓은 키워드(`광고`·`성과`)가 과매칭될 수 있다. 완화.
- 넓은 키워드는 **도메인별 키워드 목록에서 신중히 관리**(가능하면 좁은 어구로).
- 도메인 2개 이상 wired 후 **라우팅 로그 기반으로 조정**(오분류 사례 수집 → 키워드·임계 튜닝).
- 근본 개선은 2단계(임베딩/LLM 매처)로, 필요해질 때만.

## 6. 2단계 — LLM 폴백 (후속, 자리만)

`ambiguous=True`인 소수 질문만 LLM 분류기로 넘긴다. `candidates`를 힌트로 줘 후보를 좁힌다.
명확한 질문(대부분)은 1단계에서 끝나 비용·지연 0. **지금은 구현하지 않고 `IntentMatcher`
인터페이스의 확장 지점만 남긴다**(YAGNI).

## 7. DomainAgent 공통 계약

각 도메인이 챗에 꽂히는 단일 진입점. 내부 구현은 자유, 시그니처만 고정.

```python
class DomainAgent(Protocol):
    domain: str                                   # "management" | "simulation" | "generator"
    async def ask(self, req: AskRequest) -> AskResult: ...
```

- **A단계**는 `AskRequest`/`AskResult`의 **management-local shape을 레퍼런스**로 삼고, **B단계**에서
  공용 contracts로 **승격**한다(상세는 아래 "계약 승격 단계").
- management의 기존 `build_management_agent(settings)`는 **함수(클로저)를 반환**하므로 Protocol을
  그대로 만족하지 않는다. 얇은 **`ManagementDomainAgent` 어댑터**로 감싸 계약을 만족시킨다(기존
  함수는 무수정 — 수술적 변경).
- 라우팅 신호(키워드/임베딩)는 각 도메인이 자기 `IntentMatcher`로 소유하고 오케스트레이터에 등록.

```python
class ManagementDomainAgent:
    domain = "management"
    def __init__(self, ask):                       # ask: Callable[[AskRequest], Awaitable[AskResult]]
        self._ask = ask
    async def ask(self, req: AskRequest) -> AskResult:
        return await self._ask(req)

# 등록 — 기존 build_management_agent 결과를 감싸기만 한다(내부 무변경)
agent = ManagementDomainAgent(build_management_agent(settings))
```

**등록 위치 — composition root.** matcher/agent 등록은 **오케스트레이터 코어가 아니라 composition
root(API wiring/bootstrap)**에서 수행한다. 오케스트레이터 코어는 `DomainAgent`/`IntentMatcher`
Protocol과 **등록된 인스턴스만** 알며, `build_management_agent` 같은 도메인 내부를 직접 import 하지
않는다(기존 `wiring.py` Composition Root 패턴과 동일). 이로써 오케스트레이터는 도메인에 의존하지
않고, 도메인이 오케스트레이터 계약에 의존한다(의존성 역전).

### 계약 승격 단계 (A → B)
- **A단계**: `AskRequest`/`AskResult`를 **management-local에 둔 채 레퍼런스**로 삼는다.
  라우터·오케스트레이터를 이 shape으로 먼저 세운다(다른 팀 차단 없이 진행).
- **B단계**: 동일 shape을 **공용 contracts로 승격**한 뒤 sim/gen이 그것에 의존한다. 승격은
  공통부 변경 = 팀 합의 + 단독 PR(협업 규칙).

## 8. 응답 스트리밍 (AskResult → SSE)

선택된 도메인의 출력 형식을 오케스트레이터가 그대로 흘린다. 단계별 shape이 다르다.

| 경로 | SSE 이벤트 | 상태 |
|---|---|---|
| CLIO (default) | `token` … `done` | ✅ 현재 |
| management A단계 | `conclusion_delta` → `card_ready` → `final` | ⬜ 카드+Composer plan |
| 장기 목표 | `TurnEnvelope` 기반 공용 카드 SSE (전 도메인 공통) | 지향 |

- **현재 상태**: management도 아직 `token/done`(answer를 24자로 잘라 흘림). 결론+카드 SSE는 별도
  plan(`chat-card-composer`)에서 도입.
- **장기 목표 (지향, 보장 아님)**: 결론 + 타입카드(evidence/result/review/actionbar)를 담는
  `TurnEnvelope`를 공용 카드 봉투로 두고, 전 도메인이 같은 카드 SSE로 응답하게 한다.

## 9. 점진 마이그레이션 (한 번에 안 갈아엎음)

1. `routing.py` 신설 + 기존 `_MGMT_KEYWORDS`를 `KeywordMatcher("management", …)`로 이전.
   chat.py는 `_is_management()` → `Router.route()`로 교체(동작 동일, 회귀 없음).
2. `DomainAgent` 계약 확정(팀 합의) + management를 첫 구현체로 등록.
3. sim/gen이 각자 `ask()` 구현 시 매처 한 줄 + 구현체 한 줄로 등록.
4. 멀티도메인으로 애매 질문이 늘면 2단계 LLM 폴백 도입.

## 10. 스코프 제외 (Non-Goals)

- **2단계 LLM 분류기·임베딩 매처 구현** — 인터페이스 자리만. 도메인이 2개 이상 실제 생길 때.
- **가중치·우선순위 튜닝 파라미터** — 단순 점수로 시작.
- **sim/gen 서브에이전트 내부** — 각 팀 소유. 본 설계는 계약·오케스트레이터 경계까지만.
- **멀티도메인 질문 분해**(한 질문이 sim+mgmt 동시) — 후속. 우선 단일 도메인 라우팅부터.

## 11. 테스트 (성공 기준 → 실패 테스트)

1. 매니지먼트 키워드 질문 → `route().domain == "management"` (기존 동작 회귀).
2. 키워드 0개 질문 → default("clio").
3. 동점 후보에서 도메인 이름을 바꿔도 선택 결과 불변(tie-breaker 이름 독립).
4. 단독 저점수 후보 → `ambiguous == False`(불필요 폴백 차단).
5. 두 도메인 점수 박빙 → `ambiguous == True` + `candidates`에 둘 다 포함.
6. 매처 1줄 추가만으로 새 도메인 라우팅됨(라우터 코드 무수정).
7. `ManagementDomainAgent` 어댑터가 `DomainAgent` 계약(`domain` 속성 + `ask()->AskResult`)을 만족.
8. 오케스트레이터 코어가 `domain.management` 내부 모듈을 직접 import 하지 않는다(등록/bootstrap
   파일만 예외).
