# 매니지먼트 Meta 배치 insights — 캠페인 목록 N+1 호출 제거

> 작성일 2026-06-26 · 도메인 management(4-2) · 범위: 백엔드 어댑터·라우터

## 1. 배경 / 문제

캠페인 목록 화면(`/manage/campaigns`)을 한 번 그릴 때마다 Meta API를 **캠페인 수에 비례해 호출**한다. 캠페인 단건 삭제 직후 자동 전체 리로드(`load(true)`)와 120초 폴링이 겹치면 **Meta 요청 한도(rate limit)에 수 초 만에 도달**해 "Meta 요청 한도(일시) 도달" 배너가 뜬다.

### 현재 호출 구조 (N+1)

`_list_campaigns_real`(`api/routers/management.py:1051-1176`)이 캠페인마다 개별 insights를 조회한다.

| 단계 | 호출 | 횟수 |
| --- | --- | --- |
| 목록 | `GET /act_{id}/campaigns` | 1 (+페이징) |
| 광고세트 | `GET /act_{id}/adsets` | 1 |
| 계정 자금 | `GET /act_{id}` | 1 |
| 캠페인별 `maximum` 지표 | `GET /{campaign_id}/insights` | **N** |
| 활성 캠페인 `today` 지표 | `GET /{campaign_id}/insights` | **M** |
| 활성 캠페인 `last_7d` 지표 | `GET /{campaign_id}/insights` | **M** |

→ **1회 새로고침 = 3 + N + 2M 호출** (N=전체 캠페인, M=활성 캠페인).
예: 캠페인 20개·활성 10개 → 43호출. 120초 폴링 시 시간당 약 1,290호출.

### 왜 이렇게 되어 있었나 (배경, 추정)

의도된 N+1 설계가 아니라 자연스럽게 누적된 결과로 보인다.

- `get_metrics(campaign_id)`라는 **단일 엔티티 메서드가 가장 직관적인 첫 구현**이었다.
- 캠페인별 `_safe_meta` 격리로 **한 캠페인의 권한 거부가 다른 캠페인 표시를 깨지 않는** 실제 이점이 있었다.
- 운영 신호(`today`=소진율, `last_7d`=피로도)가 **나중에 덧붙어** 호출이 ×3으로 늘었다.
- 캠페인이 적을 땐 비용이 안 보였고, 캠페인이 늘며 병목이 되었다.

## 2. 목표 / 비목표

**목표**
- 캠페인 목록 조회의 Meta 호출 수를 **캠페인 수와 무관한 상수**로 만든다.
- 화면에 표시되는 모든 지표·계산 결과를 **현재와 100% 동일**하게 유지한다(회귀 없음).

**비목표 (이번 범위 아님)**
- 프론트 낙관적 삭제(전체 리로드 회피), client 캐시 무효화 범위 조정, rate-limit backoff/재시도 — 별도 후속.
- LLM/RAG·환각률과 무관(데이터 출처·값 불변이므로 정확성 주장 대상 아님).

## 3. 접근법 비교

| 안 | 방식 | 평가 |
| --- | --- | --- |
| **A. 계정 단위 `level=campaign` insights** | `GET /act_{id}/insights?level=campaign`가 모든 캠페인 행을 한 응답에 반환 | **채택.** 기간당 1호출. 코드에 선례(`get_account_spend`·`get_account_daily_spend`, `reader.py:710-729`) 존재 |
| B. Meta Batch API | N개 호출을 1 HTTP 요청에 묶음 | 탈락. Meta는 **배치 내 서브요청을 rate limit에 개별 집계** → 근본 해결 아님 |
| C. 비동기 insights job | 대용량 리포트용 폴링 잡 | 탈락. 이 규모엔 과한 복잡도 |

## 4. 설계 (안 A)

### 4-1. reader 배치 메서드 추가 — `adapters/meta/reader.py`

```python
async def get_metrics_by_campaign(
    self, since: datetime, date_preset: str = "maximum"
) -> dict[str, MetricsSnapshot]:
    ...
```

- `GET /act_{id}/insights`에 `level=campaign`, `fields=_INSIGHTS_FIELDS`, `date_preset`, `limit=500` 전달.
  - `level=campaign`이면 각 행에 `campaign_id`가 포함된다(매핑 키).
- `_all_campaign_rows`와 동일하게 **페이징 끝까지 순회**(`paging.cursors.after`)해 캠페인 25개 초과도 누락 없이 수집.
- 각 행 → `MetricsSnapshot` 변환은 **기존 `get_metrics`(`reader.py:253-306`)의 파싱 로직을 그대로 재사용**한다. 중복을 막기 위해 행 파싱부를 `_row_to_metrics(row, since) -> MetricsSnapshot` private 헬퍼로 추출하고, `get_metrics`와 신규 메서드 둘 다 이를 호출한다.
- 반환은 `{campaign_id: MetricsSnapshot}`.
- **미게재(데이터 없는) 캠페인은 응답 행이 없다** → dict에 키가 없다. 호출자가 0 스냅샷으로 폴백(현재 `get_metrics`의 빈 데이터 동작과 동일하게 impressions=0 등).

### 4-2. 라우터 N+1 루프 교체 — `api/routers/management.py:1083-1120`

- `maximum`: 캠페인별 `get_metrics` N회 → `get_metrics_by_campaign(since, date_preset)` **1회** 후 dict 룩업.
- `today` / `last_7d`: 활성 캠페인별 M회씩 → 각 **1회** 후 활성만 dict에서 룩업.
  - 기존 `elig`(활성 & 지표 권한 OK) 가드 유지 — 활성 캠페인이 없으면 today/last_7d 호출을 **생략**.
- `_safe_meta`는 **배치 호출 전체**를 감싼다.
- dict에 없는 캠페인 id는 0 스냅샷으로 폴백해 기존 출력 형태 유지.

### 4-3. 변경 후 호출 수

| | 그전 | 이 설계 |
| --- | --- | --- |
| 1회 새로고침 | 3 + N + 2M | **약 6 (상수)** |
| 캠페인 20개·활성 10개 | 43 | 약 6 |
| 시간당(120초 폴링) | 약 1,290 | 약 180 |

→ Meta 쿼터 **약 85~90% 절감**, 백엔드 동시 outbound 연결 **N분의 1**.

## 5. 데이터 흐름

```
_list_campaigns_real
 ├─ list_campaigns()          GET /campaigns (+페이징)
 ├─ get_account_funding()     GET /act_{id}
 ├─ get_metrics_by_campaign("maximum")   GET /act_{id}/insights?level=campaign   ← N개 한 응답
 ├─ (활성 있으면) get_metrics_by_campaign("today")    GET …?level=campaign
 ├─ (활성 있으면) get_metrics_by_campaign("last_7d")  GET …?level=campaign
 └─ 캠페인별 dict 룩업 → _real_summary(...) (계산 로직 불변)
```

## 6. 에러 / 엣지 처리

- **권한 거부** — 그전엔 캠페인별 `_safe_meta`로 한 캠페인만 `metrics_status="permission"`. 이 설계는 배치 한 덩어리라 **막히면 전체 지표가 permission으로** 떨어진다. 계정 insights 권한은 캠페인별로 갈리지 않고 균일하므로 **실질 영향은 사실상 없음**. (동작이 바뀌는 유일 지점 — 명시.)
- **미게재 캠페인** — insights 응답에 행 없음 → dict 미존재 → 0 스냅샷 폴백.
- **보관/삭제(ARCHIVED) 캠페인** — `date_preset=maximum` 계정 insights는 과거 게재분을 campaign_id 키로 그대로 반환 → "삭제됨 포함" 뷰의 과거 지표 유지.
- **페이징** — 캠페인 25개 초과 시 cursors.after로 끝까지 순회.

## 7. 부수 효과 (정직한 범위)

- **데이터 일관성 향상(부수)** — 그전엔 N개를 각각 다른 순간에 조회해 캠페인 간 미세한 시점 어긋남이 있었다. 이 설계는 **계정 단위 한 스냅샷**이라 모든 캠페인이 동일 쿼리 윈도로 측정돼 내부 정합이 좋아진다. (LLM 환각과 무관 — 스냅샷 일관성 차원.)
- **비용(달러)** — Meta API·EC2 egress 모두 무료~미미. 금전 절감은 사실상 없음. 이득은 **쿼터·서버 안정성**.

## 8. 테스트 / 검증

- `get_metrics_by_campaign`가 다행 응답을 `{campaign_id: snapshot}`로 정확히 매핑(페이징 포함).
- 추출한 `_row_to_metrics` 헬퍼로 **기존 `get_metrics` 출력이 100% 동일**함을 회귀 테스트로 고정.
- 미게재 캠페인 0 폴백, 권한 거부 시 전체 permission 표기.
- `cd backend && uv run pytest tests/ -v` 통과 + `uv run ruff format/check`.

## 9. 영향 파일

- `backend/domain/management/adapters/meta/reader.py` — `_row_to_metrics` 추출, `get_metrics_by_campaign` 추가.
- `backend/api/routers/management.py` — `_list_campaigns_real`의 N+1 루프 교체.
- (필요 시) management 테스트 — reader 매핑·라우터 결과 회귀.
