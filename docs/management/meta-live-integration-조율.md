# Meta 연동 LIVE-ready — 🅰 조율 문서

작성 2026-06-16 · 작성자 🅱(feat/management-boeun) · 대상 🅰 리뷰
관련 정본 `docs/management/structure-and-roles.md` (§3 역할분담, §5 import 경계, §7 스코프, §9 contracts 합의)

> **목적** Meta 어댑터(reader·writer·client)를 "연결은 안 하되 LIVE 전환 시 바로 쓸 수 있는" 수준으로 채운다. 작업은 2개 PR로 분리한다.
> - **PR1 — 어댑터 LIVE-ready** 기존 루프(진단→승인→pause/예산/소재교체)를 실 Meta 호출 가능하게. 계약 변경 없음.
> - **PR2 — 신규 캠페인 생성(create_campaign)** 없던 캠페인을 새로 띄우는 능력 추가. **공동 계약 변경 필요 → 이 문서의 안건.**
>
> 이 문서는 **PR2의 계약 변경(아래 1번)**과 **게이팅 모델(아래 2번)**을 🅰가 검토·합의할 수 있도록 자세히 설명한다.

---

## 0. 선결정 (합의 완료)

- `adapters/meta/reader.py` 소유권 — **공동 전환 합의됨** (기존 🅰 단독 → 🤝). PR1에서 🅱가 구현하고 🅰가 리뷰. import 경계(§5)는 그대로 — reader는 `contracts`만 의존.

---

## 1. PR2 계약 변경 요청 (create_campaign)

### 1.1 왜 계약 변경이 필요한가

현재 파이프라인이 집행 가능한 action_type은 executor의 `SUPPORTED_ACTION_TYPES` 4종뿐이다.

```
PAUSE_CAMPAIGN · DECREASE_BUDGET · INCREASE_BUDGET · REPLACE_CREATIVE
```

이들은 전부 **이미 존재하는 캠페인 객체(`target_object_ids`)에 작용**한다. 그런데 "새 캠페인 생성"은 **작용할 대상 id가 아직 없다.** 이 비대칭이 계약 4곳을 건드리게 만든다.

### 1.2 변경 항목 (정확한 위치·diff 수준)

#### (a) `contracts/policy.py` — TIER_POLICY에 1줄 추가

```python
TIER_POLICY: dict[str, ActionTier] = {
    ...
    "REPLACE_CREATIVE": ActionTier.TIER_3,
    "CREATE_CAMPAIGN": ActionTier.TIER_3,   # ★ 신규 — "신규 집행"은 항상 건별 승인
}
```

근거 — `enums.py`의 `ActionTier.TIER_3` 주석이 이미 *"예산 증액·**신규 집행**·시안 교체"*를 Tier 3으로 명시. 즉 신규 캠페인 생성은 정책상 당연히 Tier 3(항상 사용자 승인)이다. **자율 실행 경로 없음.**

#### (b) `contracts/platform.py` — Writer Port에 메서드 추가

```python
class AdPlatformWriter(Protocol):
    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult: ...
    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult: ...
    async def replace_creative(self, campaign_id: str, creative_id: str, idem_key: str) -> ActionResult: ...
    async def create_campaign(self, config: CampaignConfig, idem_key: str) -> ActionResult: ...   # ★ 신규
```

- 인자가 `campaign_id`가 아니라 **`CampaignConfig`**인 게 핵심 — 대상 id가 없으니 "무엇을 만들지"를 통째로 받는다.
- `CampaignConfig`는 **이미 `schemas.py`에 존재**(objective="traffic" 고정, daily_budget_krw, start/end, creative_ad_id, target_audience). 새 스키마 안 만들어도 됨.
- 기존 stub `writer.create_ad`는 **이름이 틀렸다**(인자는 `CampaignConfig`인데 이름은 ad). PR2에서 `create_campaign`으로 정정.

#### (c) `contracts/schemas.py` — ActionProposal의 "대상 없음" 문제

이게 **가장 민감한 변경**이라 🅰 판단이 필요하다. 현재.

```python
class ActionProposal(Contract):
    target_object_ids: tuple[str, ...] = Field(min_length=1)   # 최소 1개 강제
    ...
    # 클래스 docstring: "필드 18종 [확정: 변경 없음]"
```

`min_length=1`이라 빈 대상이 불가능하다. 신규 생성은 대상 id가 없으므로 충돌한다. 두 가지 길이 있고, **🅱 추천은 옵션 A**.

| | 옵션 A — 스키마 무변경 (추천) | 옵션 B — 필드 추가 |
|---|---|---|
| 방식 | `target_object_ids = (ad_account_id,)`로 채워 min_length=1 충족. 캠페인 설정은 기존 `evidence_metrics` dict에 `campaign_config` 키로 실음 | `ActionProposal`에 `campaign_config: CampaignConfig \| None = None` 필드 신설 |
| 계약 영향 | **없음** — 18필드 그대로, hash 산식 그대로 | 필드 19종 — "확정: 변경 없음" 깨짐, **proposal_hash 전체필드 산식에 신규 필드 반영 필요**(🅰/🅱 동시 수정) |
| 타입 안전성 | 약함 — config가 dict 안에 들어가 `extra="forbid"` 보호 밖 (§9.2 D4 경고와 동일 트레이드오프) | 강함 — Pydantic 검증 받음 |
| 리스크 | 낮음 (계약 안정) | 중간 (hash·골든샘플·픽스처 동시 갱신) |

→ **추천**: 우선 옵션 A로 계약을 안 흔들고 create 경로를 닫는다. 운영하며 config 타입 안전성이 필요해지면 별도 contracts 개정(옵션 B)으로 승격. *§9.3의 "개정 시한 박기" 원칙 적용 — 옵션 A 채택 시 옵션 B 재검토 시한을 함께 정하자.*

#### (d) `execution/executor.py` — 🅱 단독 (계약 아님, 참고용)

```python
SUPPORTED_ACTION_TYPES = (..., "CREATE_CAMPAIGN")   # 추가
# _dispatch 분기 추가:
if proposal.action_type == "CREATE_CAMPAIGN":
    config = <옵션 A면 evidence_metrics에서 복원 / 옵션 B면 proposal.campaign_config>
    return await self._writer.create_campaign(config, idem_key)
```

이건 🅱 소유 파일이라 합의 대상 아님 — 다만 (c) 결정에 따라 config 복원 방식이 갈리므로 같이 적는다.

### 1.3 변경 절차 (§9.0 그라운드 룰 준수)

- contracts 변경은 **슬라이스 브랜치 안에서 하지 않는다.** 별도 `fix/contracts-create-campaign` 브랜치 → 🅰/🅱 양측 리뷰 → main 머지 → 각자 리베이스.
- 변경되는 스키마/enum마다 **골든 샘플 JSON**을 `evals/fixtures/contracts/`에 함께 커밋 (정상 1 + 신규 캠페인 경계 1).
- 스키마/픽스처에 **버전 병기**.

### 1.4 v1 스코프 좁히기 (안전)

Meta에서 캠페인 1개 띄우려면 실제로는 **campaign → ad set → ad** 3단 객체를 만들어야 한다. PR2 v1은 여기까지 욕심내지 않고 **"캠페인 객체를 `PAUSED` 상태로 생성"까지만** 한다.
- 생성 직후 자동 게재 안 됨 → 사람이 마지막으로 켜야 노출 시작 → 안전.
- §7 Won't의 "실돈 LIVE" 원칙과 충돌 없음 (생성 코드는 만들되 LIVE 게이트로 잠금 — 아래 2번).

---

## 2. 게이팅 모델 — "실수로 Meta에 안 나간다"의 보장

🅰가 가장 걱정할 지점, 즉 *"이 코드가 데모(Mock)나 실제 돈에 영향을 주는가"*에 대한 답이다. **결론: 안 준다. LIVE는 독립된 두 스위치를 모두 뒤집어야만 발동한다.**

### 2.1 이중 게이트

| 스위치 | 위치 | 기본값(현재) | LIVE 전환 시 |
|---|---|---|---|
| ① `use_mock` | `core/config.py` → `wiring.py` | `True` | `False`로 바꿔야 Meta 어댑터가 꽂힘 |
| ② 실행 모드 허용 목록 | `executor.DEFAULT_ALLOWED_MODES` | `MOCK·DRY_RUN·SANDBOX_CONTRACT` (**LIVE 빠짐**) | LIVE를 명시적으로 추가해야 쓰기 발동 |

- ①만 바뀌고 ②가 그대로면 → Meta로 **읽기는 가능하지만 쓰기는 executor가 `EXECUTION_MODE_DISABLED`로 거부**한다.
- 둘 다 기본값이면 → Mock만 동작, **Meta 접촉 0건.** 현재 데모·발표 환경이 정확히 이 상태.

### 2.2 쓰기 모드 3단 의미 (§7 "DRY_RUN = 실제 API 계약 검증" 해석)

| 모드 | Meta 전송 | 실제 변경 | 용도 |
|---|---|---|---|
| `DRY_RUN` | ✕ (요청 빌드만) | ✕ | 로컬 파라미터·스키마 검증 |
| `SANDBOX_CONTRACT` | ○ (`execution_options=['validate_only']`) | ✕ | **Meta가 요청을 검증**해주되 변경 없음 — "실제 API 계약 검증"의 진짜 의미 |
| `LIVE` | ○ | ○ | 실제 집행 — executor 허용 목록에서 빠져 봉인 |

`validate_only`는 Meta Graph API가 공식 지원하는 옵션이라, **실제 돈/변경 없이 "이 요청이 Meta에 통하는가"를 진짜로 검증**할 수 있다. LIVE 코드를 미리 만들어두되 안전하게 검증하는 핵심 장치.

### 2.3 defense in depth — 기존 executor 검증과 겹침

게이팅은 executor의 기존 4단계 재검증(§4) **위에** 얹힌다. 즉 LIVE라도 다음을 다 통과해야 Writer에 도달한다.
- 승인·제안 만료, 정책버전 일치, tenant 일치, proposal_hash 변조 없음
- Tier 3(신규 집행 포함)는 `AUTO_APPROVER` 불가 → **반드시 사람 승인** (게이트 #4)
- 예산 90% 경고 / 95% 소프트캡(자율 차단) / 100% 하드캡 차단

→ `create_campaign`도 이 관문을 그대로 통과해야 한다. **"LLM·agent가 Writer를 직접 호출하는 경로는 없다"**(§5 불변)는 원칙도 유지 — 생성도 ActionProposal → 승인 → executor 단일 경로.

### 2.4 🅰 확인 요청 사항

- [ ] LIVE 이중 게이트 + 모드 3단 의미에 동의하는가
- [ ] `SANDBOX_CONTRACT = validate_only 실전송`을 "계약 검증" 정의로 채택하는가 (§7 해석 확정)
- [ ] 데모/발표는 `use_mock=True` 고정 — 이 작업이 데모에 영향 0임을 확인

---

## 3. 안건 요약 (🅰 결정 체크리스트)

| # | 안건 | 🅱 추천 | 🅰 결정 |
|---|---|---|---|
| 1 | `TIER_POLICY`에 `CREATE_CAMPAIGN: TIER_3` 추가 | 추가 | ☐ |
| 2 | Port에 `create_campaign(config, idem_key)` 추가 | 추가 | ☐ |
| 3 | ActionProposal "대상 없음" 처리 | 옵션 A(스키마 무변경) | ☐ A / ☐ B |
| 4 | (3=A 채택 시) 옵션 B 재검토 시한 | 정하자 | ______ |
| 5 | create v1 범위 = 캠페인 PAUSED 생성까지 | 좁히기 | ☐ |
| 6 | 게이팅 모델(2번) 동의 | — | ☐ |
| 7 | contracts 변경은 `fix/contracts-create-campaign` 별도 브랜치 | — | ☐ |
