# 매니지먼트 에이전틱 RAG — 메모리 설계 + eval 기반 품질 개선

- 날짜: 2026-06-24
- 상태: RAG·관측 인프라 **구현 완료**(검증: 매니지먼트 417 passed / 4 skipped) · 메모리(STM/LTM) **설계 확정**(구현 대기) · 품질 개선 **eval로 입증**
- 영역: `backend/domain/management/assistant/*`(graph·agent·retriever·checkpointer·history·kb_ingest), `backend/domain/management/evals/*`, `backend/core/models.py`, Alembic `019`·`020`, 프론트 `app/chat/page.tsx`

## 1. 배경 / 문제

매니지먼트 챗봇은 LangGraph ReAct + HITL 기반 에이전틱 RAG로, **숫자는 실측 도구(live_*), 해석·정책은 KB**에서 가져온다. 골격은 있었으나 운영급으로 가기엔 4가지 갭이 있었다.

- **검색 품질 미측정** — 벡터 단독 검색이 ROAS·PENDING_REVIEW 같은 정확 토큰을 놓치는지 알 수 없었다.
- **상태 비영속** — 체크포인터가 인메모리(MemorySaver)라 재시작 시 HITL 승인 대기·대화 맥락이 소실. 멀티턴도 매 요청 새 thread.
- **관측 부재** — 대화·도구·인용·피드백이 어디에도 안 쌓여 품질 회귀를 잴 수 없었다.
- **품질이 "감"** — "리랭커·CRAG를 넣어야 하나"를 수치 없이 판단하고 있었다.

## 2. 목표

- 검색·답변 품질을 **수치로 측정**하고, 개선을 **before/after로 입증**한다.
- 대화/HITL 상태를 **영속**하고, 모든 턴을 **관측 가능**하게 적재한다.
- "무엇을 넣을지(리랭커·CRAG·메모리)"를 **데이터로 결정**한다(감 금지).
- 단일 EC2·No-Redis·기존 테스트 무파손 제약을 지킨다.

## 3. 설계 결정

| 결정 | 선택 | 이유 |
|---|---|---|
| KB 검색 | **하이브리드(벡터+GIN 키워드, RRF 융합)** | 벡터가 놓치는 정확 토큰을 키워드가 보강. 점수 정규화 불필요. |
| 체크포인터 | **AsyncPostgresSaver(Neon)**, Windows는 MemorySaver 폴백 | 운영(Linux) 영속, 로컬(psycopg-async 비호환)은 즉시 폴백. |
| 메모리 저장소 | **STM=체크포인터 / LTM=전용 테이블(asyncpg)** | LangGraph PostgresStore는 psycopg라 Windows 폴백 → `history.py`와 동일 asyncpg로 일관·이식성. |
| 평가 judge | **Gemini Flash(환각 중심 채점)** | 측정대상(에이전트=OpenAI)과 분리. 저비용. "KB에 다 있어야"가 아니라 "환각·거짓·지어낸 수치"만 감점. |
| 측정 정밀도 | **eval 27케이스 + judge×3 평균 + 증분 JSONL 적재** | 단일 judge·소표본 노이즈 제거. 중단돼도 부분 결과 보존. |
| 리랭커/풀CRAG | **도입 보류(데이터 근거)** | 검색 recall@3=0.93 → 고칠 노이즈가 없음. 코퍼스 확대 시 재검토. |

## 4. 구현 — RAG·관측 인프라

### 4.1 지식·상태 스키마 (Alembic 019 / Neon 적용)
KB를 **문서/청크 2계층**으로 재구조화하고 관측·평가 테이블을 신설.
- `management_kb_documents`(테넌트·버전·출처·provenance) ← `management_kb_chunks`(임베딩 + `search_vector` GENERATED tsvector + GIN 인덱스).
- `management_chat_sessions`·`chat_messages`·`agent_runs`·`kb_feedback`·`kb_eval_cases`.

### 4.2 하이브리드 검색 (`retriever.py`)
`pgvector` 코사인 + `websearch_to_tsquery` 키워드를 **RRF**로 융합. 두 채널에 다 잡힌 청크가 상위로.

### 4.3 증분 적재 (`kb_ingest.py`)
`content_hash` 변경감지 — 변경된 문서만 재임베딩(자동수집의 핵심). 운영자 트리거 `POST /management/kb/refresh`.

### 4.4 멀티턴 + 영속 (`agent.py`·`checkpointer.py`·`chat.py`)
`thread_id = mgmt-{session_id}`로 세션 단위 멀티턴. AsyncPostgresSaver로 interrupt(HITL)·대화가 재시작에도 복구.

### 4.5 관측·피드백 (`history.py`·프론트 `chat/page.tsx`)
`record_turn`(세션·메시지·도구·인용·지연) + `record_feedback`(👍/👎·실패유형) best-effort 적재. 채팅 UI에 평가 버튼.

### 4.6 테넌트 격리 준비 (Alembic 020)
`kb_documents`·`kb_chunks` RLS 정책(global은 항상 보임, 테넌트는 `app.current_tenant` 일치 시). 현재 접속 롤이 BYPASSRLS라 **정책만 준비**(활성화는 전용 롤 + GUC, 멀티테넌트 시점).

## 5. eval 기반 품질 개선 (핵심)

> **핵심 성과 — 답변 충실도(faithfulness) 0.615 → 0.852 (+23.7%p).** 동일 judge·동일 측정으로 잰 before/after.

측정 대상=OpenAI gpt-4o-mini 에이전트, judge=Gemini Flash. **measure → try → revert → fix → re-measure** 루프.

### 5.0 답변 충실도(faithfulness) 측정 기준

"답이 그럴듯한가"가 아니라 **"환각 없이 근거에 충실한가"** 를 잰다.

- **감점**: 근거와 모순되는 내용, 사실 오류, **근거에 없는데 지어낸 구체 수치**(지출·CTR·ROAS 등). 숫자는 근거(실측)에 있을 때만 인정.
- **감점 아님**: KB에 명시 안 됐어도 **사실이고 합리적인 일반 광고 지식**(거짓이 아니면 OK). → 모든 문장이 KB에 있을 필요는 없음.
- **판정**: `faithful = 환각·사실오류·지어낸 수치가 없음`. score 1~5(5=환각 전무, 1=명백한 환각 다수).
- **집계**: judge(Gemini Flash) **×3 반복** — `faithful`은 과반(2/3) 투표, `score`는 평균. 에이전트는 temp 0이라 1회. n=27, 잔여 judge 표준편차 0.24(측정 안정).

### 5.1 검색 베이스라인 → 리랭커 기각
| 셋 | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| n=13(쉬움) | 0.92 | 1.00 | 0.96 |
| **n=28(패러프레이즈 포함)** | 0.78 | **0.93** | 0.85 |

recall@3=0.93 → **리랭커가 고칠 노이즈가 없음**을 수치로 확인하고 도입 보류.

### 5.2 Faithfulness — 무엇을 고칠지 데이터로 특정
1. **베이스라인(엄격 judge)**: 0.538. → 실패 사유 분석: ① judge 과엄격(맞는 일반조언도 감점) ② 행동버그(개념질문에 live 덤프, KB 미사용).
2. **Grounding 게이트 시도** → 3회 측정 모두 0.538, **개선 0 → revert**(지연만 추가하는 음성 결과).
3. **judge 재보정**(환각 중심) + **프롬프트 라우팅 수정**(개념질문→search_kb, live 덤프 금지).
4. **클린 before/after**(동일 judge): **0.615 → 0.852**.

| 단계 | faithful_rate | 판정 |
|---|---|---|
| 베이스라인(엄격 judge) | 0.538 | — |
| 라우팅 수정 후(n=13) | 0.846 | 큰 개선 |
| **정밀 측정(n=27·judge×3)** | **0.852** (평균 4.54/5, 잔여 std 0.24) | **개선 실재 확정** |

### 5.3 약점 추격 = 프롬프트 천장 입증
남은 약점 4건(빈도·CPM·예산소진·증상별, 전부 playbook 수치/조치 혼합)을 "인과·조치 근거 한정" 규칙으로 추격 → **빈도는 2.0→5.0 개선했으나 거절·구매의도가 5.0→회귀**. 순손해라 **revert**. **프롬프트 튜닝의 천장**(약점↔정상 트레이드오프)을 2라운드 측정으로 확정.

## 6. 메모리 설계 (STM/LTM — 구현 대기)

3-스토어 분리가 핵심: **STM(이 대화) ≠ LTM(누적 학습 사실) ≠ KB(큐레이션 지식)**.

| 층 | 메커니즘 | 상태 |
|---|---|---|
| STM(작업기억) | 체크포인터 thread state + **요약 압축 노드**(토큰·지연 상한) | 체크포인터 ✅ / 요약 노드 대기 |
| LTM(장기기억) | `management_memory`(tenant/user/campaign namespace, 임베딩, key 업서트, decay) — 턴 시작 recall 주입 / 턴 후 백그라운드 추출 | 설계 |
| KB(지식) | 하이브리드 RAG | ✅ |

원칙: **숫자는 LTM에 넣지 않는다**(실측은 항상 live tool). 정책·선호·결정만. 인용 시 `[기억]`/`[출처문서]` 구분.

## 7. 결과 / 수치

- 검색 recall@3 **0.93**(n=28) · faithfulness **0.852**(n=27·judge×3, 잔여 std 0.24) · 큰 win **0.615→0.852**.
- 매니지먼트 테스트 **417 passed**, ruff 통과, Alembic head=`020`(Neon 적용·정합).
- 신규 eval 모듈: `retrieval_eval.py`·`faithfulness_eval.py`(증분 적재) + 평가셋 시드(`kb_eval_cases`).

## 8. 한계 / 다음 레버

- **프롬프트로는 천장(0.852)** — 더 올리려면 ① KB 보강(약점은 KB 갭: CPM 원인·예산페이스 조치) ② 상위 모델(gpt-4o-mini 파라메트릭 누수).
- RLS는 정책만 준비(전용 롤·멀티테넌트 인증 전제).
- 자동수집 풀파이프라인은 증분 엔진까지만(웹 fetch·스케줄러는 소스 결정 후).

## 9. 엔지니어링 교훈 (포트폴리오 포인트)

1. **감 대신 측정** — 리랭커·CRAG·grounding 게이트를 모두 "넣기 전에 측정"해 **2개를 데이터로 기각**(과투자 방지).
2. **음성 결과도 결과** — grounding 게이트가 무효임을 측정으로 확인하고 되돌림(복잡도·지연 제거).
3. **측정 정밀도가 먼저** — 소표본·단일 judge 노이즈에 속지 않게 n 확대 + judge 평균 + 증분 적재로 신뢰구간 확보.
4. **천장 인지** — 같은 레버(프롬프트)로 트레이드오프가 반복되면 멈추고 레버를 바꾼다(KB/모델).
