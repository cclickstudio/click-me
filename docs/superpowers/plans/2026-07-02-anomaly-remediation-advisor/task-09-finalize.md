# Task 9: 스펙 정합 + 전체 검증

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md` (§7-1 한 줄)

- [ ] **Step 1: 스펙 §7-1 예약 실행 집계 문구 조정**

§7-1 마지막 문장 "스케줄 틱도 종료 시 같은 집계를 `management.scan_summary` 로그 1줄로
남긴다"를 다음으로 교체(스케줄러 무변경 원칙과 충돌 — 구현 확정 반영):
```
수동 스캔은 응답+`management.scan_summary` 집계 로그, 예약 실행은 건별 고정 스키마
이벤트 로그(`management.notify_*`)로 관측한다(스케줄러 무변경 원칙 — 틱 종료 훅 없음).
```

- [ ] **Step 2: Ruff + 전체 테스트**

Run: `cd backend && uv run ruff format . && uv run ruff check . --fix`
Expected: 오류 0
Run: `cd backend && uv run pytest -v`
Expected: 전체 PASS (기존 테스트 회귀 없음)

- [ ] **Step 3: 최종 커밋**

```bash
# ruff가 무관 파일을 재포맷했을 수 있음 — 반드시 git status로 확인 후 이번 작업 파일만 add.
git status
git add docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md \
  backend/domain/management/remediation/ test/backend/management/ \
  backend/domain/management/notifications.py backend/api/routers/chat.py \
  backend/api/routers/management.py backend/api/assistant/subagent_tools.py
git commit -m "edit: remediation 스펙 관측 문구 정합 + ruff 정리"
```

- [ ] **Step 4: mock 데모 시딩 (배달 성립의 필수 전제)**

⚠ 시딩 없이는 벨이 절대 안 뜬다 — fresh DB에서 resolver 체인 1(AdCampaignLog→generation→
project)이 반드시 실패해 `skipped(no_project_mapping)`이 되기 때문(이건 fail-closed 정상
동작이지 버그가 아님). mock 캠페인 1개를 실제 프로젝트에 연결해 프로덕션과 같은 경로를 태운다.

1. 노출 0 mock 캠페인 확인: `adapters/mock.py`의 `list_campaigns`/`get_metrics`에서
   impressions가 0으로 나오는 campaign_id를 찾는다(없으면 mock 수정 아닌 **시딩 대상 선정만** —
   mock.py는 detection 쪽과 공유이므로 임의 수정 금지, 필요 시 🅰 확인).
2. 데모 org의 프로젝트 id 확인 후 연결 행 삽입(psql/Neon 콘솔). 아래 SQL은
   **실 DB information_schema 대조 완료**(2026-07-02) — id·created_at은 DB default
   (gen_random_uuid()/now())가 있어 생략, CTE 한 방으로 수동 id 조회 단계 제거:

```sql
-- <project_id> = 데모 프로젝트, <mock_campaign_id> = 1에서 찾은 노출 0 캠페인
WITH gen AS (
  INSERT INTO ad_generations (project_id, status, input)
  VALUES ('<project_id>', 'completed', '{}')
  RETURNING id
)
INSERT INTO ad_campaign_logs (generation_id, campaign_id, status, mocked)
SELECT id, '<mock_campaign_id>', 'mocked', true FROM gen;
```

- [ ] **Step 5: 수동 검증 (Claude Preview 권장)**

`management_chat_notify_enabled=true` + mock 모드로 백엔드·프론트 기동 후:
1. `POST /api/management/anomaly/notify-scan` 호출 → 응답 `delivered: 1` 확인
   (`skipped: no_project_mapping`이면 Step 4 시딩 누락).
2. 프론트 채팅 벨에 "⚠ 캠페인 이상 알림" 세션 배지 확인(시딩한 프로젝트 선택 상태에서 —
   벨은 현재 선택 프로젝트 스코프로 폴링됨).
3. 세션 열어 상담 메시지 확인 → "1번 해줘" 입력 → 해당 위젯(sim_form 등) 렌더 확인.
4. 같은 스캔 재호출 → 응답에서 skipped(bell_pending/cooldown) 확인.
