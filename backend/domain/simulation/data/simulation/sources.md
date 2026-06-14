# 시뮬레이터 데이터 확보 — 현황 & 사용자 수집 가이드

> 페르소나 생성(단계1~3)에 쓰는 분포 데이터의 출처·상태와, **사용자가 직접 받아야 하는 raw**의 수집 절차.
> 상세 출처는 `docs/simulation/Data_Collection.md` 참조. 이 문서는 코드 레이어(`data/`)의 실제 적재 가이드.

## 현황 (`loader.data_status()`)

| 분포 | 상태 | 파일 | 비고 |
|---|---|---|---|
| 소비가치 응답률 | ✅ real(인용) | `distributions/consumption_values.json` | 대학내일20대연구소 공개 % |
| OCEAN 성격 | ✅ **real** | `distributions/ocean_age_bands.json` | 논문 Table 1 factor score mean·sd + 실 유형비율(PDF 추출 완료) |
| 인구 연령×성별 | ✅ **real** | `raw/population_age_sex.csv` → `population_age_sex.json` 폴백 | 행안부 원본 CSV 적재(로더 자동 우선). 전국 5,109만 일치 |
| 미디어 행동 | ✅ **real** | `distributions/media_behavior.json` (빌드: `build_media_behavior.py`) | KISDI 2024 raw(d25v32) 연령×성별 교차 + 시간대 노출맥락. raw는 gitignore, 집계 JSON만 커밋 |
| 소득·학력 | ✅ **real** | `distributions/socioeconomic.json` (빌드: `build_socioeconomic.py`) | KISDI 2024 raw d25p_income(8구간)·d25school(6단계) 연령×성별. 구매의도 grounding 보강 |
| 심층 소비심리(체면·동조) | ✗ **pending** | (없음) | MDIS 사회조사 raw 수동 다운로드 |

> 웹 자동수집은 정밀 수치마다 인증·JS·차단으로 막혀 **placeholder/pending**이 남았다. 아래가 네가 받아야 할 부분이다.

---

## 네가 수집해야 할 것 (우선순위 순)

### ① 인구 연령×성별 + 지역 — ✅ 완료 (로그인 불필요)

단계1의 모집단. 행안부 원본 CSV 적재로 연령×성별 **및 시도(17개) 분포까지 real**.

- 출처: https://jumin.mois.go.kr (또는 공공데이터포털 https://www.data.go.kr/data/15097972/fileData.do).
- 저장 위치: `raw/population_age_sex.csv` (gitignore). 로더가 자동 우선 사용(placeholder 무시).
- 지원 포맷: ① 행안부 원본(행정동×성×1세별, cp949) — **시도(col 2)에서 `region_weights` 자동 산출**.
  ② 정규화 `age_band,sex,count`(이 포맷엔 지역 없음 → sampler 근사 폴백).
- 갱신 시: 같은 행안부 파일을 받아 동일 위치에 덮어쓰면 연령·성별·지역이 한 번에 갱신된다.

### ② OCEAN 성격 — ✅ 완료 (논문 PDF Table 1 추출)

`raw/s41598-025-34511-4.pdf`의 **Table 1**(유형별 Big Five factor score mean·sd)과 유형별 표본수(실 비율)를 추출해 `ocean_age_bands.json`에 반영 완료. 성격은 표준화 factor score로 샘플링된다.

- ⚠️ **CC BY-NC-ND** — 수치 가공·상업 내장 시 법무 검토. 자기선택 편향 주석 유지(`bias_note`).
- (선택 정밀화) **연령밴드별 유형 비율**은 논문 미공개 — 확보 시 `type_proportions`를 밴드별로 분리하면 연령 조건성↑. 40대+는 BFI-K(N=1,038) 보완 여지.

### ③ KISDI 한국미디어패널 raw — ✅ 완료 (단계2-β + exposure_context)

2024(25차) raw(`d25v32_row_KMP_csv.csv`, 8,411명·3일×96슬롯·15분) + 코드북 적재 완료.
`build_media_behavior.py`가 연령×성별 셀별 매체 사용시간 + (시간대·매체·행위·장소) 노출맥락을
`media_behavior.json`으로 산출(d25wt 가중). 슬롯1=00:00(저녁 피크·새벽 트로프로 확정).

- 다이어리 코드(매체·행위·장소·연결)는 `raw/_codebook/diary_codes.txt` 참조.
- 슬롯별 실신호는 `MA`(매체)/`AA`(행위)/`CA`(연결)/`p`(장소). `s`는 미디어이용 신호 아님(무시).
- 재생성: `uv run python -m domain.simulation.data.simulation.build_media_behavior`.
- (확장 여지) 연결방법(OTT/케이블 등) 노출 축, 동시이용(B축), 종단(zip d10~24)은 추후.

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
