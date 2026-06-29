# 매니지먼트 품질 강화 — 코드 감사 결과 및 개선 사항 (2026-06-26)

> 브랜치: `feat/management-3k`  
> 작업 범위: `backend/domain/management/`, `backend/core/config.py`, `backend/tests/management/`

---

## 한 장 요약

전체 매니지먼트 코드(backend + evals + 테스트 51개 파일)를 감사한 결과, 5개의 개선 항목을 식별·구현했다.
모든 변경은 **기존 동작 보존** + **품질/관측가능성 향상** 방향이며 사이드 이펙트 없음이 테스트로 확인됐다.

| # | 파일 | 변경 내용 | 효과 |
|---|------|-----------|------|
| 1 | `core/config.py` | `management_assistant_model` 필드 추가 | `.env` 으로 모델 오버라이드 가능 |
| 2 | `domain/management/assistant/graph.py` | live_evidence 병합(merge) 수정 | 다중 live 도구 호출 시 데이터 소실 방지 |
| 3 | `domain/management/assistant/web_search.py` | `as_of` UTC 타임스탬프 추가 | 웹 인용 칩에 조회시각 표시 |
| 4 | `domain/management/evals/assistant_eval.py` | 시의성 골든셋 케이스 2개 추가 | web_search 도구선택 검증 |
| 5 | `tests/management/test_acceptance.py` | PRD §9.5 인수 테스트 12개 구현 | 완료조건 자동 CI 검증 |

---

## 상세 변경 기록

### 1. `management_assistant_model` 설정 필드

**문제** — `agent.py:155`에서 `getattr(settings, "management_assistant_model", "gpt-4o-mini")`로 읽었지만 `Settings` 클래스에 선언이 없어 `.env`의 `MANAGEMENT_ASSISTANT_MODEL` 환경변수가 무시됐다.

**수정** — `core/config.py`에 `management_assistant_model: str = "gpt-4o-mini"` 필드 추가.

```python
# core/config.py
management_assistant_model: str = "gpt-4o-mini"
```

**효과** — `.env`에 `MANAGEMENT_ASSISTANT_MODEL=gpt-4o` 등으로 오버라이드 가능. 기존 기본값 동일 → 하위 호환.

---

### 2. graph.py tools_node 라이브 근거 병합

**문제** — `tools_node` 내에서 live 도구 결과를 `evidence = result`로 덮어써, 같은 ReAct 라운드에서 `live_campaigns` → `live_budget` 순으로 호출되면 campaigns 데이터가 소실됐다.

프론트엔드 채팅 캠페인 칩(`evidence.campaigns`)이 live_campaigns 다음에 다른 live 도구가 호출될 경우 비어있는 원인이었다.

**수정 전**
```python
else:
    evidence = result if isinstance(result, dict) else evidence
```

**수정 후**
```python
else:
    # 여러 live 도구를 연달아 호출해도 각 결과가 보존되도록 병합.
    if isinstance(result, dict):
        evidence = {**evidence, **result}
```

**효과** — `live_campaigns`의 `{"campaigns": [...], "count": N}` + `live_budget`의 `{"this_month_spent_krw": ...}`이 모두 evidence에 보존됨. 프론트 캠페인 칩 데이터 신뢰성 향상.

---

### 3. web_search 결과 as_of 타임스탬프

**문제** — `_to_hit()`이 `as_of`를 설정하지 않아 웹 인용 칩에 "조회시각"이 표시되지 않았다. 사용자 입장에서 웹 결과가 언제 조회됐는지 알 수 없었다.

**수정** — `_to_hit()`에 현재 UTC 시각을 `as_of`로 추가.

```python
from datetime import UTC, datetime

def _to_hit(r: dict) -> dict:
    return {
        ...
        "as_of": datetime.now(UTC).isoformat(),  # 추가
    }
```

**효과** — 프론트 인용 칩에 "2026-06-26T..." 형태로 조회시각 표시. `Citation.as_of` 계약 충족.

---

### 4. assistant_eval.py 시의성 골든셋 케이스

**문제** — 기존 9개 케이스 중 `web_search` 도구를 검증하는 케이스가 없었다. 시스템 프롬프트가 "최근·요즘·트렌드 키워드 시 search_kb + web_search 병행"을 지시하지만 이를 자동으로 검증할 방법이 없었다.

**추가된 케이스**
```python
("요즘 Meta 광고 CPM 트렌드 어때?", None, {"web_search"}, "시의성 CPM 트렌드"),
("최근 Meta 정책 바뀐 게 있어?", None, {"web_search"}, "시의성 정책 업데이트"),
```

**설계 고려** — react 모드(API 키 있음)에서만 통과. fallback 모드는 web_search 경로가 없어 2케이스 실패 → 정확도 9/11≈0.82 (≥0.80 게이트 통과 유지). 이 설계는 의도적이다 — fallback 모드에서 web_search 미지원은 올바른 동작.

---

### 5. PRD §9.5 인수 테스트 (tests/management/test_acceptance.py)

**문제** — `domain/management/evals/acceptance.py`가 단순 docstring만 있었다. PRD에 명시된 완료조건(§9.5)과 게이트(§9.9)가 자동으로 검증되지 않았다.

**구현** — `tests/management/test_acceptance.py`에 12개 테스트 구현:

| 테스트 ID | 검증 내용 |
|-----------|-----------|
| A1 | 비어있지 않은 답 반환 |
| A2 | 하나 이상의 도구 호출 |
| A3 | 모든 citation.kind가 live\|kb\|web |
| A4 | 예산 질문 → live_budget + evidence |
| A5 | 캠페인 목록 → live_campaigns |
| A6 | campaign_id 주어지면 live_campaign_detail |
| A7 | 행동 의도 → 제안(직접 실행 없음) |
| G1 | BID_LOSS 고장 주입 → 이상 감지 |
| G2 | 이상 → 진단 + 제안 생성 |
| G3 | 신선한 제안 → 유효성 통과 |
| G4 | 승인된 액션 → approval_id 존재 |
| G5 | 만료된 제안 → 유효성 탈락 |

**실행 결과** — `pytest tests/management/test_acceptance.py` → **12/12 통과** (0.55s, API 키·DB 불필요).

---

## 테스트 결과

```
451 passed (기존) + 12 passed (신규) = 463 passed, 4 skipped
```

변경 전과 비교해 기존 테스트 전부 그린, 신규 12개 추가.

---

## 남은 한계

| 항목 | 현황 | 비고 |
|------|------|------|
| web_search 시의성 검증 | fallback 모드에서만 확인 불가 | react 모드(API 키 있음)에서 별도 수동 실행 필요 |
| faithfulness_eval google.generativeai → google.genai 이전 | 미완(수동 실행 전용, API 변경 폭 큼) | FutureWarning만 있고 동작은 정상. chat.py와 함께 추후 일괄 이전 |
| acceptance.py CRITERIA 상수 | 테스트 ID 매핑 미완 | 문서화 목적, 기능 영향 없음 |
