# 센터 — 미결정 항목 메모

> 센터 구현 중 **결정을 미루기로 한 항목**. 관련자와 상의 후 `center-spec.md`에 반영한다.

## 1. 시뮬 결과 "좋음" 판정 기준 (집행 제안 트리거) — 시뮬 팀원과 상의 필요

- 배경 — 알림 센터의 "결과가 아주 좋아요, 광고를 집행하시겠어요?" 제안(집행 제안)은 **시뮬 결과가 좋을 때만** 뜬다.
- 미결정 — 어떤 KPI로, 어떤 임계값에서 "좋음"으로 볼지.
  - 후보: 클릭 의향률 신뢰구간 하한이 기준선 상회 / 구매의도 분포 상위 / 거부율 낮음 등.
  - 주의(CLAUDE.md) — "예측 CTR" 등 실측 스케일 환산 금지, 구매의도 평균 단언 금지. 분포·신뢰구간 기반으로 규칙을 정할 것.
- **액션 — 시뮬레이션 담당 팀원과 상의해 구체 규칙 확정 후 여기와 `center-spec.md` §5.2·§9에 기입.**
- 상태 — 미정 (2026-07-06 기록).

## 2. 센터 모바일 반응형 — 반응형 작업 시 검토

- 배경 — 현재 왼쪽 패널은 모바일에서 숨김(`max-md:hidden`). 센터도 데스크톱 기준으로 먼저 구현한다.
- 미결정 — 모바일에서 센터를 어떻게 노출/접이할지(전체화면 드로어? 하단 탭? 숨김?).
- **액션 — 전체 반응형 대응 시점에 함께 설계.**
- 상태 — 후순위 (2026-07-06 기록).

## 3. 제안 알림 테이블과 `management_notifications` 통합 여부 — 내일(2026-07-07) 리뷰 후 결정

- 배경 — 센터의 취지는 "알림을 하나로 통합"이라, `ManagementNotification`(management_notifications)까지 결국 센터로 합치는 게 자연스럽다. 현재는 안전하게 **두 테이블 + 병합 조회**(center-spec §8)로 얹어둔 상태.
- 오늘 한 것 — `center_suggestions`(**0008**) **additive 신설만**. management_notifications(0005)는 손대지 않음.
- ⚠️ 마이그레이션 체인 주의(2026-07-06 발견) — DB는 `feat/simulation-doyeon`이 올린 `0007_chat_sessions_created_by`(head)에 있고, `feat/alarm-center`는 이걸 아직 못 받은 상태다. 그래서 center 마이그레이션은 `0008`(down_revision=`0007_chat_sessions_created_by`)로 잡았고, **alarm-center에 0007_chat_sessions_created_by를 rebase/merge로 먼저 들여와야 체인이 로컬에서 해석**된다. 로컬 `main`은 아예 다른 `001_/002_` 스킴이라 무관. DB는 stamp 금지.
- 내일 계획 — 도연님이 결과를 보고 괜찮으면 **management_notifications를 center 테이블로 통합**(사실상 "6을 7로 흡수").
- ⚠️ 주의 — 0006은 **이미 적용됐고 데이터·코드(NotificationBell·NotificationPanel·api.management.notifications·remediation)가 물린 살아있는 테이블**이다. 그래서 **"0006 파일 삭제"는 불가**. 통합 시 두 방식 중 택1:
  - **(A) 전진 데이터 마이그레이션** — 새 `0009`에서 기존 행을 center로 이관 → 옛 테이블 drop → management 알림 코드 경로를 center로 재배선. 데이터 보존, 운영 안전.
  - **(B) DB 재구축** — dev DB가 버려도 되면 스키마를 다시 세우며 통합(데이터 이관 생략). 간단하지만 데이터 소멸.
- 추가 고려 — management 도메인 소유 코드(협업 규칙: 도메인 경계)라 통합 시 management 팀과 조율 필요.
- 상태 — 미정, 내일 리뷰 후 A/B 택1 (2026-07-06 기록).
