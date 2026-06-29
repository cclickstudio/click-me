# 처방(Remediation) 에이전트 설계 — 🅱 재생성 agent 재정의

> 작성 2026-06-17 · Role 🅱 (Execution & Regeneration) · 브랜치 `feat/management-boeun`
> 근거 문서: `docs/management/clickme_management_합의문서_v2.1안_2.md`,
> `backend/domain/management/CLAUDE.md`(개인 R&R), `docs/management/structure-and-roles.md`

## 배경·문제

`RegenerationAgent`(`agents/regeneration.py`)의 "agent다움"은 생성→가드→채점→패키징 루프였다.
그런데 실제 크리에이티브 생성은 이미 `CreativeGenerationTool` Protocol로 주입받는 구조이고
(`regeneration.py:62`), 현재 구현체 `LLMCreativeGenerator`(gpt-4o-mini 카피 생성,
`regeneration_tools.py:80`)는 generator 도메인(4-3)이 IMPROVE 모드로 이미 더 잘 하는 일을
중복한다.

이 생성을 generator로 갈아끼우면 🅱 재생성에 남는 것은 "가드 + max(score) + 제안 빌드"라는
결정론 배관뿐이다. 즉 **agent라 부를 추론이 사라진다.**

핵심 관찰: 지금 **"무슨 행동을 할지(`action_type`)"는 agent가 정하지 않는다.** 호출자
(라우터·데모)가 `RegenerationContext`에 하드코딩해 넘긴다(`management.py:173`·`:369`,
`management_demo.py:107`). 진단(원인, 🅰)과 크리에이티브 픽셀(generator)을 둘 다 떼고 나면,
🅱 영역에 남는 진짜 판단은 **"진단 → 어떤 remediation action을 어떤 파라미터로 처방할까"** 다.
이 자리가 비어 있다(아무도 reasoning을 안 한다). 여기를 agent로 채운다.

## HITL 모델 — 승인/거부 (확정)

사용자는 제안 카드를 **건별 승인/거부**한다(co-design 아님). 따라서 처방 결정과 제안 생산은
🅱 도메인 안의 제약된 agent가 하고, 챗봇(오케스트레이터)은 "입"으로서 카드 제시·클릭 수신만
한다. 이 선택의 근거:

- **정보 방화벽** — 제안 evidence는 "진단 evidence + 후보 점수만, 그 밖 정보로 추론 금지"
  (`regeneration.py:263`). 챗봇 자유 대화로 제안을 빚으면 재현·감사가 깨진다.
- **`ActionProposal` 생산자 = 🅱 단독** (불변식, CI 블록).
- **eval 게이트** — `regeneration_eval.py`는 진짜 agent를 fixture 진단에 돌려 채점한다(`:157`).
  자유 발화 챗봇은 fixture로 채점이 불가하다.

경계 요약:

| 책임 | 주인 |
|---|---|
| 행동 여부·사용자 의향 대화·카드 제시·클릭 수신 | 챗봇(오케스트레이터, A/B 밖) |
| 진단+의향 → 정책 바운드 제안 생산(티어·예산·근거·해시) | 🅱 RemediationAgent |
| 정책 판정·기록·만료 | 🅰 `approval.py` |
| 무승인 실행 물리 차단 | 🅱 `executor.py` |

사용자 의향은 챗봇이 `risk_appetite` **구조화 노브(enum)** 로만 주입한다 — 자유 텍스트
추론 경로 없음(방화벽 유지).

## 결정 사항

1. **개명** `RegenerationAgent` → `RemediationAgent`. 파일 `agents/regeneration.py`는 유지
   (내 소유), 클래스/타입명만 변경. 호출자(router·demo·tests·eval) 참조 일괄 업데이트.
2. **generator 연동 = 포트 노출.** generator 팀이 `CreativeGenerationTool` Protocol을 구현하는
   얇은 포트를 노출한다. 🅱은 generator 내부를 직접 import하지 않는다(도메인 경계 규칙).

## 아키텍처

### 1. action 선택 코어 (새 agent)

진단 agent(`diagnosis.py`)의 `_reason()` 패턴을 미러한다 — **`_decide_action()` 단일 LLM
교체점, 기본은 결정론 코어.** 이유: 게이트 #9(키 없이 데모 재현) + eval 채점성 + 방화벽.

입력: `DiagnosisResult` + `risk_appetite`(enum). 출력: 처방(action_type + 파라미터) 또는
무처방(None).

AnomalyType → action 매핑 (`policy.py`의 액션 공간 내):

| 진단 | 처방 | creative | 티어 | 비고 |
|---|---|---|---|---|
| QUALITY_DEGRADED / REVIEW_REJECTED | REPLACE_CREATIVE | ✅ generator | 3 | 건별 승인 |
| BID_LOSS / BUDGET_EXHAUSTED | risk knob → INCREASE_BUDGET \| PAUSE_CAMPAIGN | ❌ | 3 / 1 | 늘리면 승인, 끄면 자율 |
| AUDIENCE_TOO_NARROW | CREATE_CAMPAIGN(확장) | ✅ generator | 3 | 건별 승인 |
| LEARNING_PHASE / REVIEW_DELAY / INCONCLUSIVE | 무처방(빈손) | ❌ | — | 관망 |
| SCHEDULE_GAP | 무처방 | ❌ | — | RESCHEDULE 액션 부재 → 범위 밖 |

예산 사이징(INCREASE_BUDGET): `budget_before` + 정책 상한 내에서 `budget_after` 계산.
P4 예산 한도값은 하드코딩 금지 — `contracts/policy.py` 단일 소스.

### 2. LangGraph 재구성

```
decide ─┬─ "creative" → generate → guard → score → (생존?) → package → END
        ├─ "direct"   → package(크리에이티브 없음) → END   # 예산/끄기
        └─ "noop"     → END                                # 관망(빈손 복귀)
```

`generate`/`guard`/`score`/빈손 복귀 노드는 그대로 재사용. `decide`를 entry point로 추가하고
조건부 분기를 신설한다. `_package`는 "크리에이티브 없는 제안"(예산/끄기) 분기를 추가한다 —
이 경우 evidence는 진단 evidence만(후보 없음).

### 3. generator 포트 연동

generator의 `start_generation`은 async + DB영속 + SSE 백그라운드 서비스라 🅱의
`CreativeGenerationTool.generate()`(await로 후보 반환)와 임피던스가 맞지 않는다. 해결:

- generator 팀이 `CreativeGenerationTool` Protocol(= `generate(diagnosis, count) -> [후보]`)을
  구현한 포트를 노출. 내부에서 `GenerationCreateRequest(mode=IMPROVE, fix_requests=<진단>,
  simulation_summary=<근거>)` 호출 → 완료 대기 → 후보 N개를 `CreativeCandidate`로 매핑.
- 🅱은 그 포트를 `wiring.py`에서 주입만 한다. 포트 미구현 동안에는 기존
  `TemplateCreativeGenerator` 결정론 폴백 유지(게이트 #9·#10, CI·키 없는 데모).

### 4. 컨트랙트·호출자 변화 (전부 🅱 소유, `contracts/` 제외)

- `RegenerationContext`(→ `RemediationContext`):
  - **`action_type` 입력 제거** — 이제 agent가 결정.
  - **`risk_appetite` 추가**(enum).
  - **예산 상한 입력 추가** — INCREASE_BUDGET 사이징용(값 자체는 `policy.py`).
- 라우터 3엔드포인트: action_type 하드코딩 제거 → 진단 + risk_appetite만 전달.
  `api/routers/management.py`는 🤝 공동 + 오케스트레이터 오너 TBD → 변경 전 🅰와 한 줄 합의.
- `regeneration_eval.py`: 채점 대상에 **"올바른 action 선택"** 추가. 정답 라벨 =
  AnomalyType → expected action. 기존 후보 품질 채점은 creative 가지에서 유지.

## 정보 방화벽·불변식 영향

- 방화벽 유지: `_decide_action`은 진단 evidence + 구조화 노브만 읽는다. 챗봇 자유 텍스트 없음.
- `ActionProposal` 생산자 = 🅱 단독 유지(agent가 생산, 챗봇은 표시만).
- executor·approval·감사로그 경로 무변경 → 게이트 #1~#4·#7~#10 영향 없음.
- `contracts/ActionProposal`(18필드 locked) 무변경 — `action_type`은 이미 필드로 존재.

## 범위 밖 (YAGNI)

- 실 LLM 연결(`_decide_action`의 LLM 드롭인)은 후순위(P6 빈칸) — 결정론 코어로 데모.
- generator 실연동 = 포트 시그니처 합의 후. 그 전까진 Protocol + Template 폴백.
- REBALANCE_BUDGET 비활성 유지(7/8 스코프 제외). SCHEDULE_GAP용 RESCHEDULE 액션 미도입.

## 외부 합의 필요 (🤝)

| 항목 | 상대 | 내용 |
|---|---|---|
| generator 포트 시그니처 | generator 팀 | `CreativeGenerationTool` 구현·IMPROVE 매핑·완료 대기 방식 |
| `api/routers/management.py` 변경 | 🅰 / 오케스트레이터 | action_type 입력 제거에 따른 엔드포인트 시그니처 |

## 성공 기준

1. `RemediationAgent`가 `action_type` 입력 없이 진단+risk_appetite만으로 처방을 결정한다.
2. creative 가지는 generator 포트(또는 Template 폴백)로 후보를 받아 기존 가드·채점·패키징을 탄다.
3. 예산/끄기 가지는 생성·채점 없이 제안을 생산한다.
4. 무처방 진단은 빈손(None) 복귀한다.
5. `regeneration_eval`이 fixture 진단별 "올바른 action 선택"을 채점해 통과한다.
6. 키 없는 환경(CI·데모)에서 결정론 코어 + Template 폴백으로 재현 가능하다.
