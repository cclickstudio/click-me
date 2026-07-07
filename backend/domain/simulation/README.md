# ClickMe 시뮬레이터 도메인 — 아키텍처 개요

> 집행 **전** 광고를 한국 AI 가상 소비자 패널에게 테스트해 반응을 예측하는 도메인.
> 핵심 원칙: **"숫자는 시뮬레이터가, 문장은 분석팀이."**
> 이 문서는 분석/리포트 팀원과 코딩 에이전트(LLM)에게 폴더 역할·플로우·팀 경계를 전달한다.

---

## 0. 팀 경계 — 분석/리포트 팀이 먼저 볼 것 ★

시뮬레이터는 **반응 생성 + 집계(숫자)** 까지 책임진다. 분석팀은 그 결과를 **읽어서** 토론·진단·권고·보고서(문장)를 만든다. 핸드오프는 **단방향**(시뮬레이터 → 분석팀).

| 시뮬레이터가 생산 (인터페이스 계약) | 어디에 | 분석팀 용도 |
| --- | --- | --- |
| `PersonaReaction` (페르소나 반응, §3.5) | `contracts/schemas.py` | 퍼널·구매의도·거부·감정 집계의 원천 |
| `SimulationAggregate` (집계 KPI) | `contracts/schemas.py` | 결론 카드·벤치마크 비교 |
| `RubricScore` (차원별 점수) | `contracts/schemas.py` | 크리에이티브 진단 입력 |

- **계약(스키마·enum)은 전부 `contracts/`에 있다.** 컬럼/태그 변경은 **양 팀 동시 합의**.
- 시뮬레이터는 분석팀 테이블(토론·진단·권고·보고서)을 **import·쓰기 하지 않는다.**
- 결과는 두 경로로 받을 수 있다 — ① 실행 결과 dict(`service`가 조립), ② DB(`repositories` + `models.py`).

---

## 1. 폴더 구조 & 역할 (큰 틀)

```
domain/simulation/
├── contracts/      팀 간 계약 — DTO 스키마 · enum(거부/감정/이탈 태그). 외부 의존 없음
├── data/           grounding 데이터 — 한국 통계 분포 JSON + 로더 (data/simulation/)
├── tools/          순수 빌딩블록 — 페르소나 속성 샘플링 · 고정 패널 · 집계 엔진 · Meta 도달성(reachability) (LLM 거의 없음)
├── adapters/       외부 연동 — 실 LLM 어댑터(Gemini 기본 + OpenAI 폴백·SSR 점수화) + mock(토론용)
├── graph/          오케스트레이션 흐름 정의 — LangGraph(전체 파이프라인 + 반응 유닛)
├── service/        실행 구동 — 그래프를 돌리고 진행률(SSE)·결과 관리
├── repositories/   영속화 — 9테이블 CRUD(SQL은 여기에만)
├── models.py       ORM 엔티티(PostgreSQL/SQLite 호환)
└── wiring.py       조립 유일 지점 — 어떤 구현체를 쓸지 여기서만 결정(mock ↔ 실연동)
```

**역할 한 줄 요약**
- `contracts` = 약속(무엇을 주고받나). `data` = 진짜 한국 데이터. `tools` = 숫자를 만드는 부품.
- `adapters` = 바깥 세계(LLM·저장소)와 닿는 곳. `graph` = 흐름. `service` = 그 흐름을 실행.
- `repositories`/`models` = DB. `wiring` = 부품 조립.

---

## 2. 데이터 플로우 (두 단계)

```
[A. 패널 빌드 — 광고와 무관, 최초 1회 · 캐시]
  data(한국 분포) → tools 샘플링(나이·성격·미디어·소비가치, 통계로만)
                  → adapters 서사 생성(LLM) → 고정 패널 캐시(panel-v1)
       ※ 다양성은 '데이터'가 강제하고, LLM은 마지막에 인물 서사만 입힌다(동질화 방지)

[B. 시뮬레이션 런 — 광고마다]
  광고 입력
     │
     ▼  (graph 가 오케스트레이션, service 가 구동)
  광고 해석(VLM) → 패널 로드 → 루브릭 평가 → 페르소나별 반응(QA 재시도) → 집계
     │                                                                      │
     └────────────────── 시뮬레이터 책임 ──────────────────────────────────┘
                                                                            ▼
                                              [핸드오프] 반응·집계·루브릭 → 분석팀
                                                                            ▼
                                                  토론 · 진단 · 권고 · 보고서 (분석팀)
```

- **A(패널)** 는 비싸서 1회만, 시뮬레이션마다 재생성하지 않는다. 캐시 대상은 프로필(서사)뿐, **반응은 매번 새로**.
- **B(런)** 의 출력이 0절의 계약(`PersonaReaction`·`SimulationAggregate`·`RubricScore`)이고, 그게 분석팀의 입력이다.

---

## 3. 의존 방향 & 핵심 규칙 (LLM이 코드 고칠 때 지킬 것)

```
service ──구동──▶ graph ──(노드가 호출)──▶ tools · adapters · repositories
                              ▲ 모든 구현체는 wiring 이 주입
```

1. **단방향 의존** — `service`는 `graph`를 돌리고, `graph` 노드는 주입받은 부품(`tools`/`adapters`)을 호출. 부품은 `service`를 모른다.
2. **wiring.py 가 유일한 조립점** — mock↔실 LLM·실 DB 교체는 **여기서만**. 다른 곳에 `MockXxx()`/`GeminiXxx()`를 직접 박지 않는다.
3. **계약으로만 교환** — 타 도메인(generator·management)·분석팀과는 `contracts` 스키마로만. 내부 모듈 직접 import 금지.
4. **숫자 vs 문장** — KPI 수치는 `tools`(집계 엔진)가 코드로 계산한다. LLM은 서사·진단 '문장'에만. 집계 수치를 LLM이 만들지 않는다.
5. **SQL은 `repositories`에만** — `service`는 "저장 지휘"만, CRUD/SQL은 repository.

---

## 4. 데이터 grounding 현황 (페르소나가 무엇에 근거하나)

| 속성 | 근거 | 상태 |
| --- | --- | --- |
| 나이·성별 | 행안부 주민등록(전국 5,109만) | ✅ real |
| 성격(OCEAN) | Nature 논문 5유형 factor score | ✅ real |
| 소비가치 | 대학내일20대연구소 | ✅ real |
| 미디어 행동 | KISDI 한국미디어패널 2024 raw(연령×성별·노출맥락) | ✅ real |
| 소득·학력 | KISDI 한국미디어패널 2024 raw(연령×성별) | ✅ real |
| 지역 | 행안부 주민등록 시도(17) 분포 | ✅ real |
| 인물 서사 | Gemini | ✅ real |

> **광고 해석·루브릭·반응은 실 LLM 연결 완료(P4 ✅, mock 폴백 없음).** `wiring.py`가 `GeminiAdInterpreter`·`GeminiRubricEvaluator`·`GeminiReactionEngine`을 연결하고, 반응은 GPT 폴백 체인(`SIMULATION_REACTION_FALLBACK`, 기본 ON)으로 503 내성을 확보한다. 반응·VLM 모델은 각각 `SIMULATION_REACTION_GEMINI_MODEL`·`SIMULATION_VLM_GEMINI_MODEL`로 교체 가능. `SIMULATION_SCORING=ssr`(opt-in)이면 구매의도·신뢰도를 SSR 임베딩 분포로 재산정한다.

> **Meta 전용 도달성 추출.** 제품이 Meta 광고만 취급 → 단계1 표본을 `인구 × 메타 침투율`로 추출(`persona_sampler.reachability_sampling`, `wiring`에서 ON). 표본이 메타 도달층(젊은 층)에 집중되며 self-weighting 유지. 모집단은 "메타(인스타/페북) 도달 가능 한국 소비자".
>
> **(2026-06-17, Tier2-A) reach 출처를 Meta 광고 관리자 실측 도달 분포로 확정.** 과거 KISDI 소셜피드 비중은 사실상 유튜브 영상 시청만 잡아 어긋났고, 그 뒤 쓰던 침투율(도달÷인구)도 **메타 추산치가 census 인구를 초과**해(복수계정 등) 1.0을 넘어 깨졌다. → `meta_reach.json`을 **메타 광고 관리자 '추산 잠재고객 규모' 실측 도달 분포**(`metric_type:reach_share`, 합≈1)로 교체하고, `reachability_sampling` ON이면 `_population_cells`가 이 분포를 **연령 marginal로 직접 사용(인구비중 곱 제거, `_reach_marginal`)**. 성별만 `male_ratio`로 분할. 메타 5세 구간→10년 밴드는 연수 비례 안분, 65+는 65-69/70+로 추정 분할. 지역 메타 접근성은 미반영(추후 고도화). KISDI reach는 노출맥락 선택에만 사용.

> **노출맥락은 소셜피드로만 한정(2026-06-16 수정).** `exposure_context`는 "이 광고를 본 경로"이며 Meta 전용이므로 **항상 소셜피드(SNS·동영상 @ 스마트폰/PC)** 만 선택한다. 샘플러는 노출후보(`exposure_candidates`)를 소셜 맥락만으로 빌드하고, 반응 어댑터(mock·gemini)는 소셜 후보가 없어도 **TV·신문 등 비소셜로 폴백하지 않는다** — 과거 고령층 셀에서 TV로 폴백돼 "메타 광고를 TV에서 봤다"는 모순이 발생하던 버그를 차단.

> **실행 결과에 `personas` 포함(2026-06-16).** `/run` 결과 dict는 `reactions`·`rubric_scores`·`aggregate`에 더해, 반응별 페르소나 속성 조회용 `personas`(나이·성별·지역·OCEAN·소비가치·미디어·사회경제·서사)를 함께 반환한다. 프론트 실행 화면(`/simulation/run`)이 이를 페르소나별로 표시.

---

## 5. 진입점 (분석팀 / LLM이 어디부터 보면 되나)

| 알고 싶은 것 | 볼 곳 |
| --- | --- |
| 주고받는 데이터 형태(필드·enum) | `contracts/schemas.py`, `contracts/enums.py` |
| 실행 결과 dict 구조 | `service/`(결과: `run_id`·`reactions`·`rubric_scores`·`aggregate`) |
| DB 테이블·저장 | `models.py`, `repositories/` |
| 무엇을 어떤 데이터로 grounding | `data/simulation/sources.md` |
| 페르소나 생성 전략·원칙 | `docs/simulation/Persona/` |

---

## 한 문장

**한국 실데이터로 페르소나를 만들고(`data`→`tools`), 광고에 반응시켜(`graph`+`adapters`) 숫자로 집계한 뒤(`tools` 집계), 그 계약(`contracts`)을 분석팀에 넘긴다 — 조립은 `wiring`, 실행은 `service`.**
