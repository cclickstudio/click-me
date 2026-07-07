# 시뮬레이터(4-1) 남은 작업 목록

> 문서의 상태 표기 + 실제 코드(`wiring.py`·`tools/`·`adapters/`)·데이터 파일을 대조해 정리한 시뮬레이터 도메인 한정 잔여 작업.
> 분석가 토론·RAG·벤치마크·진단/권고는 분석팀 소유라 제외(§경계 주의 참조). 최종 갱신 2026-07-06.

## 출처 약칭 범례

| 약칭 | 실제 파일 |
| --- | --- |
| IMPROVEMENT | `docs/simulation/Persona/AD_Simulator_Improvement_Notes.md` |
| GENERATION | `docs/simulation/Persona/PERSONA_GENERATION_STRATEGY.md` |
| COHORT_KNOWLEDGE | `docs/simulation/PERSONA_COHORT_KNOWLEDGE_STRATEGY.md` |
| COHORT_TIER3 | `docs/simulation/PERSONA_COHORT_TIER3_REALDATA_STRATEGY.md` |
| BATCH_API | `docs/simulation/BATCH_API_STRATEGY.md` |
| VLM | `docs/simulation/VLM_PER_PERSONA_VISION.md` |
| ANALYSIS | `docs/simulation/Persona/ANALYSIS_AGENT_STRATEGY.md` |
| Data_Collection | `docs/simulation/Persona/Data_Collection.md` |

(P1-3·P2-5 등은 해당 문서 §2 우선순위 번호. 예: IMPROVEMENT P2-4 = AD_Simulator_Improvement_Notes.md §2 P2의 4번)

## 2026-07-06 현행화 — 완료로 확인된 것

- **A-1 3-모드 UX ✅** — Individual(페르소나 지정 선택 포함)·Persona Set(세그먼트 비교 API + 3-모드 선택 UI)·Synthetic 완료(2026-07-03).
- **KOBACO 벤치마크 리포트 노출 ✅** — `aggregate.payload.kobaco_reference` + 결과 화면·채팅 위젯 참고 카드(2026-07-03). 값 병합·환산은 여전히 금지.
- **§3.6 DB 고정 패널 읽기 경로 ✅** — `PanelRepository.get_by_version` + `DbPanelProvider`(DB→JSON 캐시→라이브 샘플러 폴백), `personas.weight` 컬럼(Alembic 0002) 추가(2026-07-02).
- **반응 엔진 내성·유연화 ✅** — Gemini(모델 `SIMULATION_REACTION_GEMINI_MODEL`로 교체 가능) → GPT 폴백(`SIMULATION_REACTION_FALLBACK`, 기본 ON), fan-out 동시성 상한(`SIMULATION_MAX_CONCURRENCY`).
- **SSR 점수화 opt-in ✅** — `SIMULATION_SCORING=ssr`이면 반응 체인을 `SSRScoringReactor`로 감싸 구매의도·신뢰도를 임베딩 분포로 재산정(기본 OFF, 현행 LLM 정수 유지).
- **시뮬 어시스턴트 tool ✅** — `domain/simulation/assistant/`(ReAct + KB) 구현, 채팅 딥에이전트에 연결.
- 도메인 `README.md §4`의 "실 LLM 어댑터는 아직 mock" stale 표기는 정정 완료(2026-07-06).

---

## A. 발표 전 우선 후보 (마감 2026-07-08, 저비용·고효용)

| # | 작업 | 출처 | 상태 |
| --- | --- | --- | --- |
| 1 | **3-모드 분석 UX** — Individual(`sample_size=1` 심층 + 페르소나 지정 선택)·Persona Set(세그먼트 비교)·Synthetic(기본) | IMPROVEMENT P1-3 | ✅ 완료(2026-07-03) |
| 2 | **calibration / KOBACO 베이스라인 대비** — 구매의도를 KOBACO·공개조사와 방향·상대크기 비교(절대값 환산은 금지 유지) | IMPROVEMENT P2-5 | ✅ 데이터(2019 MCR 실측치) + 리포트 노출(`kobaco_reference` 참고 카드, 2026-07-03) 완료. 단 금융·가전·주거·여행만 "구매/교체 의향 비율" 문항, 나머지 업종은 TV광고 영향력으로 대체 참고. 값 병합·환산은 금지 유지 |
| 3 | **검증 데모 확대** — KOBACO/공개 한국 조사 1건 직접 대조(현재는 연령×반응 미스매치 방향성 1건뿐, `validation.py`) | IMPROVEMENT P2-7, GENERATION §5 | 부분 — #2와 동일 실데이터(2019 MCR) 확보됨, `validation.py`에 카테고리별 KOBACO 대조 로직 추가는 미착수 |
| 4 | **재현 모드 옵션** — seed 지정 시 모든 Gemini 콜에 base seed 주입(persona별 파생, 다양성 유지). | IMPROVEMENT P2-6 | 미착수(1회 구현 후 되돌림 2026-06-22) |
| 5 | **LLM QA 기본 활성화 검토 + 프롬프트 고도화** — `GeminiQaGate`는 opt-in(`SIM_LLM_QA`)으로 존재, 기본은 `RuleQaGate` | IMPROVEMENT P3-10 | 부분 |

## B. 데이터 확보가 게이트 (코드는 가벼움)

| # | 작업 | 출처 | 비고 |
| --- | --- | --- | --- |
| 6 | **OCEAN 연령밴드별 유형비율** — 현재 40대+도 20대와 동일 `type_proportions`. 연령×유형 교차표는 Nature 미수록(저자요청만). BFI-K 고령자 규준은 확보 완료(raw 저장)이나 직접주입 금지·정성 prior. → Data_Collection §단계 2-α | IMPROVEMENT P2-4 | 교차표 미공개 / BFI-K 확보됨 |
| 7 | **Meta reach — 70+만 추정(거의 완료)** — `meta_reach.json`은 Meta 광고관리자 실측으로 교체됨(`needs_real_values:false`). 65+의 65-69/70+ 분리만 60/40 추정. census 단순안분은 침투율 역행이라 부적절(2026-06-22 검토) | COHORT_KNOWLEDGE §9 | 70+ 정밀화(선택) |
| 8 | **지역 메타 접근성 보정** — 현재 지역은 순수 인구분포만(연령·성별만 reach 적용) | COHORT_KNOWLEDGE §9-(2) | 우선순위 낮음 |

## C. 발표 후 (Phase 2)

| # | 작업 | 출처 | 상태(2026-06-22) |
| --- | --- | --- | --- |
| 9 | **배치 API** — Phase A(코어: 공유 로직 추출·`GeminiBatchReactionEngine`) → B(인프로세스 폴러) → C(SQS 전환). 50% 비용 절감, 현재 전체 미구현(SQS는 설정만) | BATCH_API | 미착수 |
| 10 | **Tier 3 실데이터 인지율 주입** — `brand_awareness.json`(빈 값) + `tools/brand_awareness/lookup.py`, `interpret_ad`에서 룩업해 `structured_analysis.awareness_by_age` 부착(스키마 무변경) + 반응 프롬프트 `_awareness_lines` | COHORT_TIER3 | ✅ 프레임워크·폴백 / 데이터 게이트(갤럽·오픈서베이 계약) |
| 11 | **성격↔행동 IPF 결합분포**(옵션 3) + 외부 marginal raking | GENERATION §6 | ✅ 외부 raking(`tools/sampling/raking.py`, opt-in `rake_to_census`) + OCEAN→행동 경량 조건화 / 진짜 성격×행동 joint 보류(개인단위 연결 데이터 부재) |
| 12 | **40대+ OCEAN을 BFI-K로 전 연령 확장** / MDIS 풀 상관 매트릭스 (BFI-K 고령자 규준 raw 확보됨 — 정성 prior 활용) | GENERATION §6 | ✅ 40+ OSF 실데이터 주입 완료(유형비율·factor 평균, B-6) / MDIS 풀 상관행렬은 게이트(MDIS raw) |
| 13 | **단계3 한국 특화 심리 확장**(`social_values_deep` — 체면·동조·눈치) | IMPROVEMENT P3-9, GENERATION §6 | ✅ 프레임워크(Persona 필드·loader·샘플러·프롬프트, **값 비움**) / 데이터 게이트(MDIS raw + 척도 정의) |
| 14 | **Meta 브랜드 특정 침투율 보정** — 현재 generic 기준 → 인스타/페북 특정 | IMPROVEMENT §2.5, VLM/COHORT Tier2 | ✅ 프레임워크 + **IG/FB 연령 reach 실데이터 주입**(KOSIS SNS 1순위, `platform_specifics`) / 연령×성별 cross·정밀 침투율은 게이트(Meta 광고관리자) |
| 15 | **광고해석 VLM 입력 확장** — 단일 이미지 → 영상 썸네일/다중 프레임/A·B 소재 비교 | IMPROVEMENT P3-11 | 미착수 |
| 16 | **페르소나 Debate 검문소**(검문소 2 — 응답 분산 확대) / DeepPersona 5:3:2 stratified oversampling | GENERATION §4·§6 | 미착수 |

> **2026-06-22 프레임워크 패스(10·11·13·14)** — 5종 모두 실데이터가 게이트라 "코드 프레임워크 + graceful fallback"을 먼저 구현했다. 데이터 0 상태에선 현재 동작을 그대로 보존(회귀 0)하고, 사용자가 데이터를 주입하면 즉시 활성화된다. 데이터 수집 리스트·라이선스는 `Persona/Data_Collection.md` 참조. 12(40+ OCEAN)는 B-6에서 OSF 실데이터로 이미 해결, MDIS 상관행렬만 남았다.

## D. 구조/운영

| # | 작업 | 출처 |
| --- | --- | --- |
| 17 | **`domain/simulation/models.py`(로컬 SimBase) → `core/models.py` 병합 + Alembic 일원화** — 공통부라 사전 공지 + 협업 규칙 필요 | IMPROVEMENT P3-8 |

---

## 경계 주의 (분석팀 소유 — 위 목록 제외)

분석가 토론·처방 RAG(T1 ABCD/Meta/네이버·카카오)·업종 벤치마크 DB·진단/개선권고는
ANALYSIS 기준 **분석팀 소유**라 제외했다. 시뮬레이터가 산출하는 `intent_mismatch`·`mismatch_detail`·루브릭 정합점수는 이미 완료됐다.

## 권장 착수 순서 (A-1·A-2 완료 후 기준)

1. **A-3 (검증 데모 확대)** — 실데이터(2019 MCR)는 확보됨, `validation.py`에 카테고리별 KOBACO 대조 로직만 남음.
2. **A-4·A-5 (재현 모드·QA)** — 외부 데이터 없이 바로 구현 가능.
3. 나머지(B·C·D)는 데이터 확보·발표 후로.

> 핵심 원칙은 변함없다 — "숫자는 코드(집계), 문장·반응은 LLM", "다양성은 실데이터가 강제", "분포로 표기". 보완은 이 원칙 위에서만.
