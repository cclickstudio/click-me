# 시뮬레이션 파이프라인 조각 (반응 분석 → 토론 → 리포트)

> 전체 시뮬레이션을 단계(조각)로 쪼개 stream으로 묶어 단계별 처리하기 위한 분해도.
> 더미 5개(`backend/domain/simulation/dummy/reaction-dummy1~5.json`)는 **7번(반응 출력)에 해당** —
> 즉 반응 생성·집계까지 끝난 상태라, 우리가 짤 부분은 **8(반응 분석)부터**다.
> 토론 세부 규칙은 같은 디렉토리의 `persona-debate-pipeline.md` 참조.

## 전체 맵 (0 ~ 11) — 더미는 7번

```
0  프로젝트 생성
1  광고 사용자 데이터 입력
2  데이터 파싱·전처리(광고 해석)
3  인구 분포·남녀 비율 고정
4  연령대별 성격·한국 정서(트렌드) 입력
5  페르소나 생성
6  타겟(설정 시 타겟집중 90% + 임의 10% / 미설정 시 합성 인구 100%)
7  반응 출력  ←━━━ 더미 5개가 여기 (reactions[] + aggregate 포함)
──────────────── 여기부터 우리가 구현할 부분 ────────────────
8  반응 분석        ← 토론 전 필수. 바로 10으로 넘어가면 안 됨
9  수치 평균(KPI 확정) + 토론 주제 생성
10 페르소나 토론(LLM)
11 리포트 생성
```

> **핵심 원칙** — 숫자는 결정론(8·9), 해석은 LLM(10). 토론은 항상 실제 반응 데이터에 grounded.
> 조각 8·9·10-a·10-b는 LLM을 쓰지 않아 빠르고 결정론적(같은 더미 → 항상 같은 결과).
> LLM은 조각 10-c(토론)에서만 쓴다.

---

## 조각 8 — 반응 분석 (결정론, LLM✗)

더미의 `reactions[]`를 **구조적으로 분석**한다. 단순 평균이 아니라 "어디서·왜 새는가, 누가 어떤 무리인가".

| 분석 | 산출 |
| --- | --- |
| AISAS 퍼널 | 단계별 통과 인원·통과율, **최대 이탈 구간(병목)** |
| 이탈 분해 | `drop_stage`별 · `drop_reason_tag`별 분포 |
| 거부·불신 분해 | `rejected` 비율, `rejection_reason_tag`, `emotion=distrust` |
| 감정 분포 | `emotion_tag` 집계 |
| **소비자 그룹 식별** | 완주자/미온다수/거부자/불신자/초기이탈 분류 |

- **입력**: `reactions[]` (+ `rubric_scores`, `ad_analysis`)
- **출력**: `analysis` 객체 (funnel · bottleneck · breakdown · emotion_dist · groups)
- **stream**: `analysis_ready`
- ★ 여기서 나온 **groups가 조각 10-a 선발의 후보 풀**, **bottleneck이 토론 주제의 근거**가 된다.

---

## 조각 9 — 수치 평균 / KPI 확정 + 토론 주제 (결정론)

조각 8의 분석을 **수치 평균·비율로 확정**한다(순서 "9. 분석 결과는 수치 평균으로").

- 4대 KPI: 클릭 의향률(+신뢰구간) · 구매의도 평균+분포 · 신뢰도 평균 · 거부율 (+ `variance_warning`, `effective_n`)
- 더미에 `aggregate`로 이미 일부 있으니 **재계산해서 일치 검증**만 하면 된다.
- 이어서 **토론 주제(topic) 생성**: 8의 병목 + 9의 KPI + 캠페인 목표(`detected_objective`) → "신뢰 높은데 클릭 안 됨" 류 주제.
- **stream**: `kpi_ready` → `topic_ready`

> 8과 9의 분담 — **8 = 무엇이 문제인가(구조 분석), 9 = 그걸 숫자로(평균·비율)**. 둘 다 결정론.

---

## 조각 10 — 페르소나 토론 (LLM)

세 부분으로 쪼개진다. 토론 세부 규칙(선발 슬롯·모델 배정·라운드 동사·유동 게이트)은 `persona-debate-pipeline.md` 참조.

### 10-a 선발 (결정론, LLM✗)
- 조각 8의 groups에서 **토론 패널 6명** 선발(완주자·피벗·거부자·불신자·초기이탈·미온다수2).
- 피벗 기준 = **신뢰-행동 갭**(미전환자 중 trust 최고 → `trust − purchase_intent` 최대 → id순). `stance_score`(③ 배정 전용)와 분리.
- 슬롯 배타 배정(이미 뽑힌 사람 제외), 슬롯6 = 피벗과 trust 차 최대.

### 10-b 배정 (결정론, LLM✗)
- 입장순 정렬 후 엔진 교차 배정 — 토론자 6명 = Haiku 2(피벗 포함) / GPT 2 / Gemini 2, 주최자(Judge) = Opus.
- `persona_name`·`persona_profile` 결정론 부여(persona_id 기반). 더미는 factory를 안 거쳤으니 **여기서 이름 부여**.
- **DB**: `persona_debates` 1행 생성(= 토론 id) + `persona_debate_participants` 6행 저장.

### 10-c 토론 (LLM, 2~4턴 유동)
- 라운드마다 역할(동사)을 다르게 — R1[발산] 병렬 → R2[반박] 순차 → R3[검증] 순차. **2~4턴 유동**(churn·dispersion 게이트, MIN 2 / MAX 4).
- 주최자(Judge)가 라운드 사이 정리(`judge_log`) → 최종 요약(`final`).
- 매 라운드 발언을 `persona_debate_utterances`에 저장 → stream.
- **stream**: `round_1` · `round_2` · …(유동) · `judge_final`

---

## 조각 11 — 리포트 생성

**[9의 수치 KPI] + [8의 분석] + [10의 토론 결론·실제 발언 인용]** 을 조립한다.

- **입력**: analysis(8) · aggregate(9) · debate final + utterances(10)
- **stream**: `report_ready` → `completed`

---

## 전체 stream 흐름

```
더미 로드 → 8 analysis_ready → 9 kpi_ready·topic_ready
          → 10-a 선발 · 10-b 배정(DB 생성) → round_1 → round_2 → …(2~4) → judge_final
          → 11 report_ready → completed
   └──── 결정론(빠름: 8·9·10-a·10-b) ────┘ └──── LLM(느림, stream 흘림) ────┘
```

- 결정론 조각(8·9·10-a·10-b)은 순식간이라 묶어 처리해도 되고, **LLM 조각(10-c)만 라운드별로 잘게** stream을 흘려 토론 진행을 실시간 노출.
- 기존 `simulation_service`가 이미 SSE `progress` 이벤트를 흘리므로, 위 조각 이벤트를 그 뒤에 이어붙인다.

---

## 구현 순서 (권장)

1. **조각 8 → 9 → 10-a → 10-b**(결정론)을 먼저 코드로. LLM 없이 더미 5개로 즉시 검증.
2. stream 골격(SSE progress 이벤트) 연결.
3. 마지막에 **조각 10-c(LLM 토론)** 와 11(리포트)을 얹는다.
