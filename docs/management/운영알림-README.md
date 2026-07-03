# 운영 알림(이상 감지 C안) — 팀원 안내 README

> 2026-07-03, 담당 🅱. 이상 감지 알림이 채팅 세션 대신 **알림 벨/패널**로 오고,
> [상담하기]를 눌러야 채팅 상담이 시작되는 구조로 바뀌었습니다.
> 상세 설계: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md`

## 무엇이 생겼나 (1분 요약)

- **상단 우측 알림 벨 🔔** — org 전체 미읽음 배지, SSE 실시간 갱신 (`AppLayout.tsx`에 장착)
- **알림 패널** — 카드 목록(프로젝트 필터·[지금 점검]·[상담하기]·[무시])
- **[상담하기]** → 재검증 후 채팅 세션에 상담 메시지 + **옵션 버튼**(①②③④ + 기타) 렌더
- **[무시]** → 같은 (캠페인, 이상 유형) 재통지 완전 억제
- 스캔이 정상화를 확인하면 알림 **자동 해소**(auto_normal)

## 실행 방법

```bash
# 1. dev 머지 후 마이그레이션 (0005 — management_notifications 테이블)
cd backend && uv run alembic upgrade head

# 2. .env 설정 (backend/.env — 루트에 .env 있으면 그쪽이 우선!)
#    MANAGEMENT_NOTIFY_CHANNEL=panel   ← 신규 채널 설정 (log|chat|panel)

# 3. 백엔드 (dev.py에 graceful shutdown 3초 포함 — SSE 연결 때문에 필요)
cd backend && uv run dev.py

# 4. 프론트
cd frontend && pnpm dev
```

⚠ **설정 키 이행**: 구 `MANAGEMENT_CHAT_NOTIFY_ENABLED`(bool)는 삭제됐습니다.
`true` → `MANAGEMENT_NOTIFY_CHANNEL=chat`, `false` → `log`. C안 데모는 `panel`.

## 데모 재현 절차 (알림이 뜨는 걸 보고 싶다면)

기본 데이터에는 "노출 0 캠페인"이 없어서 알림이 안 생깁니다. 재현하려면 —

1. `backend/.env`에 `MANAGEMENT_READER_MOCK=true` (매니지먼트 reader만 mock — 데모용
   노출 0 캠페인 **camp_3**이 보임). ⚠ `USE_MOCK=true`로 하면 **채팅 에이전트가 통째로
   꺼지므로**(deep_agent_builder — mock이면 None) 상담하기 이후 흐름이 안 됩니다.
   전역 `USE_MOCK=false` 유지 + 이 키만 켜세요.
2. camp_3 ↔ 내 프로젝트 연결 시딩 (resolver가 fail-closed라 필수):

```sql
WITH gen AS (
  INSERT INTO ad_generations (id, project_id, status, input)
  VALUES (gen_random_uuid(), '<내 프로젝트 id>', 'completed', '{}')
  RETURNING id
)
INSERT INTO ad_campaign_logs (id, generation_id, campaign_id, status, mocked)
SELECT gen_random_uuid(), id, 'camp_3', 'mocked', true FROM gen;
```

3. 백엔드 재시작 → 로그인 → 벨 클릭 → **[지금 점검]** → 카드 "⚠ 신규 런칭 티저 — 노출 0 감지"
4. [상담하기] → 채팅 + 옵션 버튼 → 버튼 클릭으로 시뮬/생성/중지 진행
5. 정리: `mocked=true` 행 삭제로 흔적 제거 (검증 가이드 §7)

상세 절차·트러블슈팅: `docs/management/remediation-advisor-검증-가이드.md` §10(panel)·§6(트러블슈팅)

## 자주 겪는 문제

| 증상 | 원인 · 해결 |
|---|---|
| 벨 SSE가 `400 Bad Request` 반복 | **ADMIN 계정이 조직 미선택** — /manage 상단에서 조직 선택(X-Org-Id) |
| [지금 점검]이 "새 알림 없음" | 노출 0 캠페인이 없거나(정상) `no_project_mapping`(시딩 필요 — fail-closed 정상 동작) |
| `429 N초 후 다시 시도` | 수동 스캔 쿨다운(60초) — 연타 방지 정상 동작 |
| Ctrl+C 해도 uvicorn이 안 죽음 | SSE 장수명 연결 때문 — `uv run dev.py`에 graceful 3초 반영됨(구 명령이면 Ctrl+C 2번) |
| env 바꿨는데 안 먹힘 | uvicorn `--reload`는 .env를 감지 안 함 — **재시작 필요** |

## 공통부 변경 공지 (머지 전 확인 부탁)

| 변경 | 파일 | 성격 |
|---|---|---|
| `management_notifications` 테이블 + Alembic **0005** | `core/models.py` | 신규 append, 기존 무변경 |
| `ChatRequest.option_select` 필드 1개 | `core/schemas.py` | append-only |
| 알림 벨 1줄 장착 | `frontend/src/components/AppLayout.tsx` | import+컴포넌트 2줄 |
| 채널 설정 키 교체 | `core/config.py` | 위 이행 노트 참조 |
| **camp_3 추가** (데모 신호) | `domain/management/adapters/mock.py` | ⚠ detection(🅰)과 공유 파일 — 확인 요청 |

## API 요약 (프론트/챗 연동 시 참고)

```
GET  /api/management/notifications            목록 + unread_count(org 전체)
POST /api/management/notifications/read       {ids} bulk 읽음
POST /api/management/notifications/{id}/resolve  {resolution: ignored|actioned}
POST /api/management/notifications/{id}/consult  상담 진입 → {status, session_id}
GET  /api/management/notifications/stream     SSE (changed 신호 → refetch)
POST /api/management/anomaly/notify-scan      수동 스캔 (잠금 409·쿨다운 429)
```
