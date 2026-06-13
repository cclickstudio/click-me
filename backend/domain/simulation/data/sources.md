# 시뮬레이터 데이터 확보 — 현황 & 사용자 수집 가이드

> 페르소나 생성(단계1~3)에 쓰는 분포 데이터의 출처·상태와, **사용자가 직접 받아야 하는 raw**의 수집 절차.
> 상세 출처는 `docs/simulation/Data_Collection.md` 참조. 이 문서는 코드 레이어(`data/`)의 실제 적재 가이드.

## 현황 (`loader.data_status()`)

| 분포 | 상태 | 파일 | 비고 |
|---|---|---|---|
| 소비가치 응답률 | ✅ real(인용) | `distributions/consumption_values.json` | 대학내일20대연구소 공개 % |
| OCEAN 성격 | ✅ **real** | `distributions/ocean_age_bands.json` | 논문 Table 1 factor score mean·sd + 실 유형비율(PDF 추출 완료) |
| 인구 연령×성별 | ◔ **placeholder** | `distributions/population_age_sex.json` | 근사 fixture — 공식 CSV로 교체 필요 |
| 미디어 행동 | ◐ real(기기별 사용시간) / pending(시간대·성연령) | `distributions/media_behavior.json` | KISDI 2025 표4-71(PDF 추출). 시간대(표4-77)·교차는 추후 |
| 심층 소비심리(체면·동조) | ✗ **pending** | (없음) | MDIS 사회조사 raw 수동 다운로드 |

> 웹 자동수집은 정밀 수치마다 인증·JS·차단으로 막혀 **placeholder/pending**이 남았다. 아래가 네가 받아야 할 부분이다.

---

## 네가 수집해야 할 것 (우선순위 순)

### ① 인구 연령×성별 — 가장 쉬움, 가장 중요 (로그인 불필요)

단계1의 모집단. placeholder를 공식 데이터로 교체하면 인구 grounding이 바로 성립한다.

1. https://www.data.go.kr/data/15097972/fileData.do 접속 → **파일 다운로드**(로그인 불필요).
   - 대안: https://jumin.mois.go.kr/ageStatMonth.do (행정안전부, 연령별 인구현황 조회·다운로드).
2. 받은 표를 **`age_band,sex,count`** 3열 CSV로 정리(엑셀에서 연령대·성별로 합계).
   - 예: `20-29,M,3210000` / `20-29,F,2980000` …
   - 연령밴드는 `ocean_age_bands.json`과 맞추면 좋다(`14-19,20-29,30-39,40-49,50-59,60+`). 단순 `0-9…70+`도 허용.
3. `backend/domain/simulation/data/raw/population_age_sex.csv` 로 저장.
   - 로더가 CSV를 **자동 우선** 사용한다(placeholder 무시). gitignore라 커밋 안 됨.

### ② OCEAN 성격 — ✅ 완료 (논문 PDF Table 1 추출)

`raw/s41598-025-34511-4.pdf`의 **Table 1**(유형별 Big Five factor score mean·sd)과 유형별 표본수(실 비율)를 추출해 `ocean_age_bands.json`에 반영 완료. 성격은 표준화 factor score로 샘플링된다.

- ⚠️ **CC BY-NC-ND** — 수치 가공·상업 내장 시 법무 검토. 자기선택 편향 주석 유지(`bias_note`).
- (선택 정밀화) **연령밴드별 유형 비율**은 논문 미공개 — 확보 시 `type_proportions`를 밴드별로 분리하면 연령 조건성↑. 40대+는 BFI-K(N=1,038) 보완 여지.

### ③ KISDI 한국미디어패널 raw — 회원가입 필요 (단계2-β + exposure_context)

미디어·소비 행동 분포 + 미디어 다이어리(광고 노출 매체 맥락).

1. https://stat.kisdi.re.kr/ 회원가입 → 미디어통계포털.
2. **원시자료(raw)** 게시판: https://stat.kisdi.re.kr/kor/board/BoardList.html?board_class=BOARD35 에서 한국미디어패널조사 설문지·원시자료 다운로드.
3. raw를 `raw/`에 저장. "연령×성별×미디어 이용 패턴" 교차표를 계산해 `distributions/media_behavior.json` 생성(스키마는 착수 시 합의).
4. 미디어 다이어리는 `exposure_context`(시간대·매체) 후보로 우선 검토.

### ④ MDIS 사회조사 raw — 회원가입 필요 (단계3 심층 심리, 후순위)

체면·동조 등 깊은 변수. 마감 전엔 소비가치 3~4개로 충분(§7.5) → 여유 시.

1. https://mdis.kostat.go.kr/ 회원가입 → 공공용 사회조사 검색·다운로드(200레코드 제한은 미리보기뿐, 전체 무료).
2. 가치관 문항을 `distributions/social_values_deep.json`으로 정리(또는 전문가 prior로 보수적 설정).

### (선택) KOSIS OpenAPI 키 — 인구 자동화

①을 매월 자동 갱신하려면 https://kosis.kr 인증키 발급 → 시군구/성/연령 테이블 호출. 1회성이면 ① 파일로 충분.

---

## 적재 위치 요약

```
data/
├── distributions/         # 집계 분포(커밋됨) — 내가 채운 real + placeholder
│   ├── consumption_values.json   ✅
│   ├── ocean_age_bands.json      ◐ (트레이트는 ②로 교체)
│   └── population_age_sex.json   ◔ (①로 교체)
└── raw/                   # 사용자 다운로드(gitignore, 커밋 안 됨)
    ├── population_age_sex.csv     ← ①
    ├── (KISDI raw)                ← ③
    └── (MDIS raw)                 ← ④
```

> 우선순위: **① 인구 CSV** 하나만 넣어도 단계1 grounding이 성립한다. ②~④는 단계별로 추가.
