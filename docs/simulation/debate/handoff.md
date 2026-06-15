# 작업 인수인계 노트 (세션 이어가기용)

> 노트북 세션을 집 데스크탑 새 세션에서 그대로 이어가기 위한 맥락 전체.
> 같은 디렉토리의 `pipeline-piece.md`(파이프라인 조각)와 `persona-debate-pipeline.md`(토론 설계)와 함께 읽을 것.

## 0. 프로젝트 한 줄

ClickMe — 집행 전 AI 가상 소비자에게 광고를 테스트하고 집행 후 성과를 추적하는 광고 전주기 플랫폼. 작업 브랜치 `feat/simulation-doyeon`. 지금 다루는 영역은 **시뮬레이터 도메인(`backend/domain/simulation/`)의 페르소나 토론 파이프라인**.

## 1. 전체 시뮬레이션 순서 (사용자 확정)

```
0 프로젝트 생성
1 광고 사용자 데이터 입력
2 데이터 파싱·전처리(광고 해석)
3 인구 분포·남녀 비율 고정
4 연령대별 성격·한국 정서(트렌드) 입력
5 페르소나 생성
6 타겟(설정 시 타겟 90% + 임의 10% / 미설정 시 합성 인구 100%)
7 반응 출력  ← 더미 5개가 여기
8 반응 분석        ← 토론 전 필수
9 수치 평균(KPI 확정)
10 페르소나 토론(LLM, 2~4턴, 토론자 6명 + 주최자 1명)
11 리포트 생성
```

## 2. 지금까지 한 작업 (요청 순서)

1. **프로젝트·시뮬레이션 도메인 파악** — 헥사고날 구조(contracts/adapters/graph/service/tools/wiring), LangGraph 2겹(run_graph + reaction_graph), 집계는 `BasicAggregator`(가중 부트스트랩 CI). 프론트(`api.ts`)가 구 `/api/simulate/*` 경로라 백엔드 `/api/simulation/*`와 불일치하는 문제 발견(별건, 미해결).
2. **`persona-debate-pipeline.md`(토론 설계) 검토** — 더미로 ①~⑤ 진행 가능한지 점검. ① 집계는 더미와 일치하나, ②(선발) 규칙에 모순·미정의가 있어 그대로 코딩하면 안 됨을 확인.
3. **선발 로직(②) 결정론화 — `persona-debate-pipeline.md` 수정 완료**:
   - 피벗 기준을 'stance 0에 가장 가까운'(→ 우연히 P-00009) 에서 **'신뢰-행동 갭'**(미전환자 중 trust 최고 → `trust − purchase_intent` 최대 → id순)으로 재정의. `stance_score`는 ③ 모델 배정 전용으로 분리.
   - 슬롯 **배타 배정**(우선순위 순, 이미 뽑힌 사람 제외) 명문화.
   - **슬롯6**(미온 다수 2) = 피벗과 trust 차 최대로 결정론화. **완주자** = `pick_representative`로 통일.
   - `stance_score`의 `stage_rank`에 `.get(stage, 1)` + AISAS 전 단계 매핑(미정의 `drop_stage` KeyError 방어).
   - 더미로 검증: 규칙대로 6명 선발 시 문서 표(P-00006/P-00011/P-00000/P-00013/P-00010/P-00009)와 정확히 일치 확인.
4. **토론 DB 테이블 재설계** — NeonDB 실측 결과: 기존 `debate_sessions`·`debate_statements`·`debate_results` 전부 0행이고 우리 6인·다라운드 토론과 구조 불일치(1:1·2인대립). 그래서:
   - 신설(`simulations` 1:N): `persona_debates` / `persona_debate_participants` / `persona_debate_utterances`. (SQL은 `docs/db-schema.md` v3.1에 반영)
   - 기존 `debate_*` 3개 DROP 쿼리 제공. `persona_id`는 더미 문자열·실 UUID 둘 다 받게 VARCHAR(50).
   - `docs/db-schema.md` 갱신(버전·목록 30개·Full Schema·관계도), `backend/api/routers/projects.py`의 삭제 SQL을 새 테이블로 교체(테이블 DROP 시 깨짐 방지).
5. **더미 5개 구조 통일** — `reaction-dummy1~5.json`(사이다/몬스터/칸쵸/다우니/삼성세탁기, 반응 수 10/20/28/40/18). dummy3/4/5에 `mismatch_detail.category`(declared=과자/생활/가전)와 `rubric` `category_alignment`를 dummy1/2와 동일 구조로 추가. 5개 전부 구조 일치 검증 완료. **이 더미는 7번(반응 출력) = 반응+집계까지 끝난 상태**.
6. **파이프라인 조각화** — 7번(더미) 다음의 8(반응 분석)→9(수치 평균)→10(토론)→11(리포트)을 stream으로 묶는 조각 분해. → `pipeline-piece.md` 작성.

## 3. 핵심 결정 (결론)

- **선발(②)** — 피벗 = 신뢰-행동 갭(캠페인 목표에서 파생). `stance_score`는 모델 배정 전용. 배타 배정·슬롯6·완주자 규칙 전부 결정론. (상세 = `persona-debate-pipeline.md`)
- **토론(④/10)** — 토론자 **6명 + 주최자(Judge) 1명**, **2~4턴 유동**(churn·dispersion 게이트, MIN 2/MAX 4). 토론자 엔진 Haiku 2(피벗 포함)/GPT 2/Gemini 2, Judge=Opus. (사용자가 한때 "5명·2턴"이라 했으나 **철회 — 6명·2~4턴이 최신·확정**.)
- **DB** — 새 3테이블, `simulations` 1:N(`UNIQUE` 없음), `ON DELETE CASCADE`. `persona_id` VARCHAR.
- **더미** — 7번 반응 출력. 토론 전 **8(반응 분석) 단계 필수**(바로 토론 금지).
- **구현 순서** — 결정론 조각(8·9·10-a·10-b) 먼저 → stream 골격 → LLM 토론(10-c)·리포트(11).
- **persona_name** — 더미는 factory를 안 거쳤으니 조각 10-b(배정) 시점에 결정론 부여.

## 4. 확인·미해결 사항

- [ ] 위 **CREATE(persona_debate*) / DROP(debate_*) SQL을 실제 NeonDB에 적용했는지** 확인. (권장: CREATE 먼저 → DROP 나중. Alembic 마이그레이션으로 하는 게 팀 규칙에 맞음.)
- [ ] **미커밋 변경 커밋·push** — `docs/db-schema.md`, `backend/api/routers/projects.py`, `backend/domain/simulation/dummy/*`, `docs/simulation/debate/persona-debate-pipeline.md`, 본 `docs/simulation/debate/*`. (커밋 2~3개로 분리 제안: 토론 테이블 재설계 / 더미·선발 / 파이프라인 문서)
- [ ] 프론트 `api.ts`의 `/api/simulate/*` 경로 불일치(별건).
- [ ] 토론 인원 6명은 `persona-debate-pipeline.md`의 6슬롯과 일치. 만약 추후 5명으로 바꾸면 슬롯6 제거 필요(현재는 6명 유지).

## 5. 다음 할 일 (바로 착수)

**조각 8(반응 분석)부터 코드로 구현한다.** 순서:
1. 조각 8 — `reactions[]` → AISAS 퍼널·병목·이탈/거부/불신/감정 분해·소비자 그룹. (결정론)
2. 조각 9 — 4대 KPI 수치 확정(더미 `aggregate`와 일치 검증) + 토론 주제 생성. (결정론)
3. 조각 10-a/10-b — 선발 6명 + 모델·이름 배정 + `persona_debates` DB행 생성. (결정론)
4. 더미 5개로 1~3 전부 검증.
5. stream(SSE) 골격 연결 후, 조각 10-c(LLM 토론, 2~4턴)·11(리포트)을 얹는다.

## 6. 핵심 파일

| 무엇 | 경로 |
| --- | --- |
| 토론 설계(선발·배정·라운드 규칙) | `docs/simulation/debate/persona-debate-pipeline.md` |
| 파이프라인 조각(8~11) | `docs/simulation/debate/pipeline-piece.md` |
| DB 스키마(v3.1, 새 토론 테이블) | `docs/db-schema.md` |
| 더미 5개 | `backend/domain/simulation/dummy/reaction-dummy1~5.json` |
| 시뮬 도메인 코드 | `backend/domain/simulation/` (service·graph·tools·adapters·wiring) |
| 프로젝트 삭제 SQL(토론 테이블 참조) | `backend/api/routers/projects.py` |
