# X-Org-Id 검증 이원화 조율

> admin impersonation(X-Org-Id) 로직이 `management.py`(kuk9096, T2~T11)와
> `core/auth.py`(devdoyeon, generator·projects 공용)에 각각 구현되어 있어서,
> 두 구현의 검증 세부 수준을 비교해 정리해 보았습니다.
> 서로 충돌하는 부분은 아니고, 앞으로 함께 맞춰가면 좋을 지점들입니다.
> 작성 2026-07-02 · 관련 `backend/api/routers/management.py` ↔ `backend/core/auth.py`

---

## 0. 요약

먼저 말씀드리고 싶은 건, **이 문서는 누군가의 실수를 지적하려는 게 아니라는 점**입니다.
두 분 다 각자 필요한 상황에서 최선의 판단으로 작업하신 결과이고, 실제로 지금 당장
장애가 나는 상태도 아닙니다. 다만 같은 목적("admin이 X-Org-Id로 다른 조직 대신
조회·조작")의 구현이 두 곳에 따로 있다 보니, 시간이 지나면서 세부 검증 수준이
자연스럽게 조금씩 벌어진 것 같아 한번 짚어보면 좋겠다는 취지입니다.

- **현황**: `management.py`에 원래 있던 X-Org-Id impersonation 패턴(kuk9096, T2~T11)과
  별도로, `core/auth.py`에 같은 목적의 일반화된 버전(devdoyeon)이 만들어져
  `generator.py`·`projects.py`에 적용되어 있습니다.
- **왜 이렇게 되었는지**: `core/auth.py` 쪽 작업은 원래 X-Org-Id가 적용되어 있지 않던
  generator·projects에도 admin impersonation을 넓혀주기 위한 좋은 취지의 확장이었고,
  그 과정에서 management 코드를 참고해 새로 만드신 것으로 보입니다. management.py
  코드는 그대로 유지되어 있어서, 기존 기능에 영향을 준 부분은 없습니다.
- **한번 맞춰보면 좋을 부분**: 두 구현 사이에 org 존재 확인 · 비활성 조직 처리 ·
  impersonation 감사 기록, 이렇게 세 가지 지점에서 세부 수준 차이가 있었습니다 (§3).
- **급한 사안은 아닙니다**: 두 구현이 서로 다른 변수를 사용하고 있어서 충돌하거나
  즉시 오류가 나는 상황은 아닙니다. 다만 나중에 정책 일관성이나 감사 추적이
  필요해질 때를 대비해 미리 공유해 두면 좋을 것 같아 정리했습니다.

---

## 1. 진행된 순서 참고용 타임라인

혹시 맥락을 다시 살펴보실 때 참고하시라고 시간 순서를 정리해 봤습니다.

| 시각(2026-07-01/02) | 커밋 | 작성자 | 내용 |
|---|---|---|---|
| 07-01 | `d8bec08e` add | kuk9096 | management X-Org-Id 헤더 캡처 ContextVar 의존성 (T2) |
| 07-01 | `2b187e83` add | kuk9096 | management `_validated_org` 검증 헬퍼 (T3) |
| 07-01 | `07863a62` add | kuk9096 | management `_require_org_id` role 인지 해석기 (T4) |
| 07-01 | `b43381da` add | kuk9096 | impersonation 감사 seam + write 엔드포인트 치환 (T6) |
| 07-01 | `f98964bd` add | kuk9096 | 프론트 `request()` management 한정 X-Org-Id + `adminOrgId` 유틸 (T10) |
| 07-02 14:46 | `7f347a12` add | devdoyeon | org 스코프 공용 헬퍼 신설 — `core/auth.py`에 비슷한 패턴을 일반화 |
| 07-02 14:56 | `d6288fe0` edit | devdoyeon | generator에 `capture_selected_org` 적용(브랜드킷 404 버그도 함께 개선) |
| 07-02 ~15:00 | `5e32186a` edit | devdoyeon | projects에도 동일하게 적용 |
| 07-02 15:01 | `0cbd93ee` edit | devdoyeon | 프론트: `request()`의 `/management` 한정 조건을 `authedFetch()`로 옮겨 전 경로에 적용되도록 확장 |

참고로 kuk9096님의 management 코드(T2~T11)는 이후로 수정된 이력이 없어서,
원래 구현 그대로 잘 남아 있습니다.

---

## 2. 코드 위치 참고

| 구현체 | 파일:라인 | 사용 라우터 |
|---|---|---|
| `_capture_selected_org` / `_validated_org` / `_require_org_id` / `_require_org_id_write` | `backend/api/routers/management.py:142, 2587, 2601, 2626` | `management.py` |
| `capture_selected_org` / `_selected_org_uuid` / `OrgScope` / `resolve_read_scope` / `require_write_org` | `backend/core/auth.py:219, 235, 246, 258, 270` | `generator.py`, `projects.py` |

두 구현은 서로 다른 `ContextVar` 인스턴스(`management.py`의 `_selected_org_ctx`와
`core/auth.py`의 `_selected_org`)를 사용하고 있어서, 같은 요청 안에서 서로 값을
덮어쓰거나 잘못 읽는 일은 없습니다. 완전히 독립적으로 잘 동작하고 있습니다.

---

## 3. 검증 세부 수준 비교

| 항목 | `management.py` | `core/auth.py`(generator/projects) |
|---|---|---|
| 존재하지 않는 org UUID를 보냈을 때 | `_validated_org`가 DB로 확인 후 404 안내 | 별도 확인 없이 진행되다가 FK 제약에서 걸려 500으로 응답될 수 있음 |
| 비활성(INACTIVE) 상태 org에 쓰기 요청 | 409로 안내하며 막아 줌 | 별도 체크가 아직 없어서 통과될 수 있음 |
| impersonation 감사 기록 | write 시마다 감사 로그가 남음 | 아직 감사 로그 연결이 안 되어 있음 |

세 가지 모두 "지금 당장 잘못됐다"기보다는, management 쪽에 있던 안전장치가
generator·projects 쪽에는 아직 옮겨지지 않은 상태로 보시면 될 것 같습니다.

---

## 4. 참고로 생각해볼 수 있는 상황들

- **삭제되었거나 오타가 섞인 org_id** — admin이 이미 지워진 조직을 선택한 채 생성루프를
  시작하면, management라면 404로 안내됐을 상황이 generator에서는 DB 에러 형태로
  나타날 수 있습니다.
- **정지된 조직 관련 동작 차이** — 조직이 결제 문제 등으로 비활성 처리되었을 때,
  management 쪽 조작은 막히지만 generator·projects 쪽은 아직 그렇지 않을 수 있습니다.
- **감사 기록 공백** — 나중에 "admin이 언제 어느 조직을 대신 조작했는지" 전체를
  살펴봐야 할 일이 생기면, management 기록만 남아 있고 generator·projects 쪽 이력은
  비어 있을 수 있습니다.

---

## 5. 앞으로 편하실 때 고려해 보시면 좋을 방향

`core/auth.py`는 여러 도메인이 함께 쓰는 공통부라, CLAUDE.md 협업 규칙에 따라 작은
단독 PR로 나누고 관련된 분들과 미리 이야기 나눈 뒤 진행하면 좋을 것 같습니다. 급하게
결정하지 않으셔도 괜찮고, 편하신 시점에 아래 중 하나를 골라 주시면 될 것 같습니다.

1. **(제안)** management에 있던 검증 로직(org 존재+활성 확인, 감사 기록)을
   `core/auth.py`로 옮겨서 세 도메인이 같은 정책을 공유하도록 정리하는 방법.
2. **(가볍게)** `core/auth.py`의 관련 함수에 org 존재/활성 확인만 우선 추가하고,
   감사 로그는 추후 여유 있을 때 연결하는 방법.
3. **(지금은 보류)** 당장 문제가 되는 상황은 아니니 이 문서로 기록만 남겨두고,
   실제로 관련된 이슈가 생기면 그때 우선순위를 올려 처리하는 방법.

어떤 방향이든 편하신 대로 결정해 주시면 될 것 같고, 필요하시면 논의 자리도
언제든 잡을 수 있습니다.

---

## 6. 참고 — 에러 응답 방식 관련 메모 (별개 주제)

이번에 살펴보던 중 겸사겸사 발견한 부분이라 같이 적어 둡니다. 큰 문제는 아니고
참고하시면 좋을 것 같은 내용입니다.

요즘 실무에서는 클라이언트에는 간단한 안내 메시지만 보여주고, 자세한 오류
내용(스택트레이스, 쿼리 등)은 서버 로그에만 남기는 방식을 많이 씁니다. 상세 정보가
그대로 노출되면 보안상 좋지 않기 때문입니다.

지금 `backend/api/main.py`를 보면 입력값 검증 오류(422)에 대한 처리는 잘 되어
있는데, 그 외 일반적인 서버 오류(500)에 대한 공통 처리는 아직 없는 것 같습니다.
예를 들어 위 §4에서 말씀드린 것처럼 존재하지 않는 org_id로 인한 DB 오류가 나면,
지금은 상세 내용이 노출되지는 않지만 응답 형식이 나머지 API와 달라서(JSON이 아닌
일반 텍스트) 프론트에서 처리할 때 살짝 애매해질 수 있습니다. 여유 되실 때
`@app.exception_handler(Exception)`을 하나 추가해서, 서버에는 자세히 기록하고
클라이언트에는 "일시적인 오류가 발생했습니다" 같은 통일된 안내만 나가도록
정리해두시면 좋을 것 같습니다.
