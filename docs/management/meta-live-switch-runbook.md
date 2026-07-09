# Meta LIVE 전환 런북

> 광고 매니지먼트(4-2)의 Meta 쓰기(pause·예산·소재교체·신규캠페인생성)를 실제 Graph API로
> 켜는 절차서. **평소엔 발동하지 않게 봉인돼 있고, 이 문서의 절차로만 푼다.**
> 작성 2026-06-17 · 갱신 2026-06-17(라우터 config-driven 리팩터 반영) · 도메인 `backend/domain/management`

> **⚠ 해결됨 (2026-06-17 이후)** — 아래 §0·§1-D·핵심(이중 출처)이 경고하는 "라우터가 승인 발급 시 항상
> `execution_mode=MOCK`을 실어 executor의 LIVE 차단 게이트가 무력화된다"는 위험은 이후 커밋에서 해결됐다.
> 현재 라우터는 `_resolved_execution_mode()`(`management.py:227`, settings 기반)를 승인 발급 시 실제로
> 실어 보내고(`management.py:3162,3303,3488` 근처 `/approve`), `_get_executor()`(`management.py:250-254`)도
> `_resolved_execution_mode() is LIVE`일 때만 `DEFAULT_ALLOWED_MODES`에 LIVE를 추가한다. 즉 이중 출처
> 버그는 없다 — 아래 §0·§1-D의 경고 서술은 그 시점의 스냅샷으로 읽을 것. 나머지 전환 절차(§2~§9)는
> 여전히 유효하다.

---

## 0. 안전 전제 (먼저 읽기)

- **현재 상태 = 봉인.** 기본 설정(`use_mock=True`)에서 Meta로 나가는 호출은 **0건**. reader=Mock,
  writer=DRY_RUN(미전송).
- **데모·발표 환경은 절대 건드리지 말 것.** LIVE 전환은 실제 집행이 필요한 순간에만.
- **라우터가 이제 config-driven이다** — `build_writer(settings)`/`build_reader(settings)`
  (`management.py:60,80`). 그래서 **이전 런북과 달리 LIVE 전환에 코드 수정이 거의 불필요**하고,
  대부분 `.env` 값으로 결정된다.
- ⚠️ **중요(아래 §1-D)** — executor의 "LIVE 차단" 게이트는 **현재 휴면 상태**다. 실제 봉인은
  `use_mock` + `management_execution_mode` + 토큰 세 가지(전부 `.env`)에 달려 있다.
- **반드시 VALIDATE_ONLY(validate_only)로 먼저 검증**한 뒤 LIVE로 간다.

---

## 1. 현재 봉인 게이트

| 게이트 | 위치 | 현재값 → 의미 |
|---|---|---|
| **A. `use_mock`** | `core/config.py:26` · `wiring.py:14,29` | `True`(기본) → reader=Mock, writer=`MetaAdsWriter(DRY_RUN)`(미전송). **Meta 접촉 0** |
| **B. `management_execution_mode`** | `core/config.py:95` · `writer.py:36` | `"dry_run"`(기본) → 전송 안 함. `use_mock=False`일 때 writer 실제 전송 모드를 이 값이 정함 |
| **C. writer 토큰 가드** | `adapters/meta/writer.py:43` | 전송모드여도 `meta_access_token` 없으면 client 미구성 → 합성결과 폴백, **네트워크 0** |
| **D. executor 허용모드 (⚠️ 휴면)** | `executor.py:53,231` · `management.py:131` | `DEFAULT_ALLOWED_MODES`에 LIVE 없음. **그러나** 라우터 `approve(...)`가 `execution_mode`를 안 넘겨 항상 **MOCK** 발급 → executor는 MOCK만 보고 통과시킴. **즉 이 게이트는 LIVE를 실제로 막지 못한다.** |

> **핵심 — 이중 출처**
> - executor 게이트(D)는 **`action.execution_mode`** 로 판정 → 라우터에선 항상 MOCK이라 LIVE 차단 안 됨.
> - writer 실제 전송(B,C)은 **`settings.management_execution_mode` + 토큰** 으로 판정.
> - **따라서 지금 실제로 Meta에 쓰기가 나가는 조건 = `use_mock=False` AND `management_execution_mode∈{validate_only,live}` AND 토큰 존재.** 전부 `.env`.

---

## 2. 모드 3단 의미

| 모드 | Meta 전송 | 실제 변경 | 용도 |
|---|---|---|---|
| `dry_run` (현재 기본) | ✕ (요청 빌드만) | ✕ | 로컬 파라미터·스키마 검증 |
| `validate_only` | ○ (`execution_options=["validate_only"]`) | ✕ | **Meta가 요청을 검증**만, 변경 없음 — LIVE 직전 안전 리허설 |
| `live` | ○ | ○ | 실제 집행 — 봉인 해제 시에만 |

`validate_only`는 Graph API 공식 옵션(`client.py:74`)이라, **실제 돈·변경 없이 "이 요청이
Meta에 통하는가"** 를 진짜로 확인할 수 있다. 그래서 LIVE 전에 반드시 거친다.

> **⚠️ `validate_only` 모드 ≠ Meta 샌드박스 '계정'** (이름 혼동 주의)
> - `validate_only`(우리 모드)는 **아무것도 안 만든다** — 요청만 검증.
> - **Meta 샌드박스 계정에서 실제로 캠페인을 만들어 보려면** → `live` 모드 + `META_AD_ACCOUNT_ID`를
>   샌드박스 계정 id로. `live`라도 계정이 샌드박스면 실돈·실게재 없이 객체만 생성된다.
> - **안전은 "모드"가 아니라 "계정이 샌드박스냐"에서 온다.** `live` + 실계정 id면 진짜 집행이니
>   `META_AD_ACCOUNT_ID`가 샌드박스 계정인지 반드시 먼저 확인.

---

## 3. 전환 절차 (단계적 — 이 순서를 지킬 것)

> 라우터가 config-driven이라 **아래 1·2단계는 `.env` 변경만으로 동작한다(코드 수정 불요).**
> `.env`는 프로젝트 루트 우선(없으면 `backend/.env`), gitignore 대상이라 커밋되지 않는다.

### 0단계 — 현재 (아무것도 안 바꿈)

`use_mock=True` → reader Mock, writer DRY_RUN. 네트워크 0.

### 1단계 — VALIDATE_ONLY (validate_only, 실변경 없이 Meta 검증)

`.env` 에 추가/변경.

```bash
META_ACCESS_TOKEN=<장기 액세스 토큰>
META_AD_ACCOUNT_ID=<광고계정 id, act_ 접두사 없는 숫자>
USE_MOCK=false
MANAGEMENT_EXECUTION_MODE=validate_only
# 선택
META_APP_SECRET=<appsecret_proof 쓸 경우>
META_GRAPH_API_VERSION=v23.0   # 기본값, 버전 고정 필요 시
```

**검증** — `/approve` → `/execute` 호출 후 결과의
`platform_response_snapshot.dry_run == true` 이고 `meta_response`가 채워졌는지 확인.
"요청이 Meta에 실제로 갔고, Meta가 검증만 했다"는 뜻.

### 2단계 — LIVE (실제 변경)

VALIDATE_ONLY에서 전 요청이 통과한 걸 확인한 **다음에만**. `.env` 한 줄만 바꾼다.

```bash
MANAGEMENT_EXECUTION_MODE=live
```

**검증** — `create_campaign`으로 캠페인 1개를 만들어 Meta Ads Manager에서 **`PAUSED` 상태로
존재**하는지 눈으로 확인. 결과 `dry_run == false` + `meta_response`에 생성된 id.

---

## 4. 변경 지점 요약

| 구분 | `.env` 키 | 1단계 VALIDATE_ONLY | 2단계 LIVE |
|---|---|---|---|
| 자격증명 | `META_ACCESS_TOKEN` | 설정 | 유지 |
| 자격증명 | `META_AD_ACCOUNT_ID` | 설정 | 유지 |
| 게이트 A | `USE_MOCK` | `false` | 유지 |
| 게이트 B | `MANAGEMENT_EXECUTION_MODE` | `validate_only` | `live` |

**코드 변경: 없음.** (라우터가 `build_writer`/`build_reader`로 config를 따른다.)

---

## 5. (선택) 봉인 강화 — executor 이중 게이트 복구

현재 executor의 LIVE 차단(§1-D)은 휴면이다. "config 실수 한 번으로 LIVE가 나가는" 위험을 줄이려면,
LIVE를 **의도적 코드 변경 없이는 불가능**하게 만들 수 있다. 필요 시에만.

```python
# api/routers/management.py
from domain.management.contracts.enums import ExecutionMode

# (a) approve가 settings 모드를 실제로 실어 발급 → executor가 진짜 모드를 보게
action = approve(body.proposal, body.approver_id,
                 execution_mode=ExecutionMode(settings.management_execution_mode))

# (b) Executor 허용모드에서 LIVE는 명시적으로 추가해야만 통과 (기본은 VALIDATE_ONLY까지만)
#     → LIVE 집행 시에만 allowed_modes=DEFAULT_ALLOWED_MODES + (ExecutionMode.LIVE,)
```

이렇게 하면 LIVE는 **env(`live`) + 코드(allowed_modes에 LIVE 추가)** 둘 다 필요 → 이중 게이트 복원.

---

## 6. ⚠️ create_campaign (신규 캠페인 생성) 전용 주의

- v1 구현은 **`objective=OUTCOME_TRAFFIC` + `status=PAUSED` 캠페인 객체 생성까지만** (`writer.py:80`).
  **생성 직후 자동 게재 안 됨** → 사람이 Meta Ads Manager에서 직접 켜야 노출.
- `CREATE_CAMPAIGN`은 정책상 **Tier 3 = 항상 사람 승인** (`AUTO_APPROVER` 불가, `executor.py:248`).

---

## 7. 사전 안전 체크리스트 (LIVE 직전)

- [ ] `META_ACCESS_TOKEN`이 **올바른 광고계정**의 토큰인가 (오계정 집행 방지)
- [ ] **VALIDATE_ONLY로 먼저** 전 액션이 통과하는 걸 확인했는가
- [ ] 예산 가드(90% 경고 / 95% 소프트캡 / 100% 하드캡, `executor.py`)가 살아있는가
- [ ] (선택) §5 봉인 강화를 적용해 executor 이중 게이트를 복구했는가
- [ ] 로그·예외에 **access_token 평문이 없는가** (마스킹 `client.py:18`, `mask_token`)

---

## 8. 롤백 (봉인 복구)

`.env` 한두 줄로 즉시 복구된다.

1. `USE_MOCK=true` (즉시 무력화 — reader Mock·writer DRY_RUN으로 복귀)
2. 또는 `MANAGEMENT_EXECUTION_MODE=dry_run`
3. 재기동 후 `/execute`가 `dry_run=true`로 돌아오는지 확인

---

## 9. 부록 — 관련 코드 색인

| 무엇 | 위치 |
|---|---|
| 모드 enum | `domain/management/contracts/enums.py` (`ExecutionMode`) |
| use_mock 분기 | `domain/management/wiring.py:13`(reader) · `:24`(writer) |
| 허용모드 상수 | `domain/management/execution/executor.py:53` (`DEFAULT_ALLOWED_MODES`) |
| 모드 차단 판정(휴면) | `domain/management/execution/executor.py:231` |
| writer 모드 분기·전송 | `domain/management/adapters/meta/writer.py:110` (`_dispatch`) · 토큰가드 `:43` |
| validate_only 부착 | `domain/management/adapters/meta/client.py:68` (`post`) |
| 토큰 마스킹 | `domain/management/adapters/meta/client.py:18` (`mask_token`) |
| config 게이트 | `backend/core/config.py:26`(`use_mock`) · `:95`(`management_execution_mode`) |
| 라우터 와이어링 | `backend/api/routers/management.py:56`(`_get_executor`) · `:131`(`approve`) |
| 스크립트(수동 실 호출) | `backend/scripts/meta_warmup.py` · `meta_review_probe.py` (둘 다 `.env` 자격증명 사용, GET 위주) |
