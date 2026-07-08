# B-1F 설계 — 챗 인라인 REPLACE_CREATIVE 흐름 (프론트 완결)

> 챗에서 "○○ 캠페인 소재 바꿔줘" → 후보 선택 → 영향 광고 프리뷰 → 승인 → 집행까지
> 한 세션 안에서 끊김 없이 도는 흐름을, 기존 부품 재사용으로 완성한다(mock 모드 완결).

**목표** — 백엔드 REPLACE_CREATIVE 체인(proposal·approve·execute)은 이미 존재하나, 사용자가
챗에서 이를 시작·완주할 UI 흐름이 없다. 원래 기획(챗 인라인)대로 그 흐름을 연결한다.

**선행 참조** — `docs/superpowers/specs/2026-06-29-chat-replace-creative-explicit-candidate-design.md`
(백엔드 mock 구현·엔드포인트), `docs/center/center-spec.md`(챗 렌더 위치).

---

## 1. 범위 (잠금)

- **포함** — 챗 tool `replace_creative`, 위젯 `replace_creative_form`, 프론트 카드
  `ChatReplaceCreativeCard`(후보 picker→프리뷰→승인→집행), api 클라이언트 메서드.
- **모드** — **mock 완결**. 엔드포인트가 sending mode(validate/live)에서 501로 막혀 있어
  (`management.py:2374`) 이 흐름은 mock에서 끝까지 동작하는 데모로 완성된다.
- **후속(범위 밖)** — LIVE 실집행 + 집행 시점 드리프트 재검증(별도 스펙). 자동 후보 선택(B-2).

## 2. 전체 흐름

```
사용자: "○○ 캠페인 소재 바꿔줘"
  → [챗 tool] replace_creative(campaign_id)          ← 신규 (analog: manage_campaign)
  → 위젯 replace_creative_form                        ← 신규 dispatch → ChatReplaceCreativeCard
      [1] generation 선택 (내 생성물)
      [2] 후보 3개 표시, "🔄 이 시안으로 교체"        ← GenResultWidget 카드 레이아웃 재사용
      → 후보 선택 → POST /replace-creative-proposal   ← 기존 엔드포인트
      [3] 프리뷰: 바꿀 소재 + 영향 광고 N개
      → [교체 실행] → POST /approve → POST /execute    ← 기존 범용 엔드포인트
      → 집행 결과(성공/부분실패) 표시
```

## 3. 백엔드 (변경 최소)

**신규 2개, 엔드포인트 변경 0.**

1. **챗 tool `replace_creative`** — `api/assistant/subagent_tools.py`, `manage_campaign` 패턴.
   `campaign_id`(없으면 되물음)를 받아 후보 picker 위젯을 띄운다. 폼 시점 실행 히스토리 적재
   (`spawn_record_execution`, stage=request)까지 기존 패턴 그대로. tool 리스트·`prompts.py`
   설명 한 줄 추가.
2. **위젯 헬퍼 `widgets.replace_creative_form(campaign_id)`** — `campaign_action` 패턴.
   `{type: "replace_creative", data: {campaign_id}}` 반환.

**재사용(변경 없음)** — `POST /campaigns/{id}/replace-creative-proposal`(제안+프리뷰 생성),
`POST /approve`(범용 승인), `POST /execute`(범용 집행).

## 4. 프론트 (핵심 작업)

**신규 카드 `ChatReplaceCreativeCard.tsx`** — `ChatBudgetProposalCard` 패턴, 내부 3단계 상태머신.

- **[1] generation 선택** — 카드 내 드롭다운(내 생성물 목록). 카드가 마운트되면 프로젝트의
  최근 생성물을 조회해 드롭다운을 채운다(카드 자체로 완결 — 별도 위젯 연계 안 함).
- **[2] 후보 선택** — `GenResultWidget`의 후보 카드 레이아웃 재사용(이미지·헤드라인·QA·순위 배지).
  버튼만 "🔄 이 시안으로 교체". 선택 시
  `api.management.replaceCreativeProposal(campaignId, {generation_id, candidate_id, link_url})`.
- **[3] 프리뷰 + 승인** — 응답 `preview.affected_ads`(영향 광고 N개)·`preview.candidate` 표시.
  [교체 실행] → `api.management.approve(proposal, true)` → `api.management.execute(action, proposal)`
  → 결과(성공/부분실패) 표시.

**변경/추가 파일**
- 신규 `frontend/src/components/chat/ChatReplaceCreativeCard.tsx`.
- `ChatConversation.tsx` — `widget.type === 'replace_creative'` dispatch 블록 1개(1900줄대).
- `api.ts` — `replaceCreativeProposal(campaignId, body)` 추가(`budgetProposal` 패턴).
  `approve`·`execute`는 이미 존재.
- `types.ts` — 위젯 payload 타입 한 줄.

## 5. 에러 처리

- 엔드포인트가 이미 방어함 — 캠페인 미소유 403, 후보 소재 빈값 422, 영향 광고 0건 409,
  sending mode 501, 후보 이미지 유실 422. 카드는 이 detail을 그대로 노출한다(budget 카드 패턴).
- 부분 실패(일부 광고만 교체 후 실패) — execute 응답의 `succeeded_ad_ids`/`failed_ad_id`를
  결과 영역에 표시.

## 6. 테스트·검증

- **백엔드** — `test/backend/chat/test_tools.py`에 `replace_creative` tool 테스트 추가:
  호출 시 `widget.type == "replace_creative"` + `campaign_id` 데이터 단언(기존 tool 테스트 패턴).
  엔드포인트 3개는 기존 테스트로 커버됨(재검증).
- **프론트** — 유닛테스트 없음(CI=ESLint+build). 검증은 ① 타입체크·빌드 통과 ② Claude Preview로
  실제 챗 흐름을 mock 모드에서 끝까지 구동, 스크린샷·콘솔 로그를 증거로 남김.
- **성공 기준** — mock 모드 한 세션 안에서 "campaign_id 지정 → 후보 고름 → 영향 광고 프리뷰
  확인 → 교체 실행 → 성공 결과"가 끊김 없이 완주.

## 7. Non-goals

- LIVE 실집행 및 집행 시점 드리프트 재검증(별도 스펙).
- 자동 후보 선택·역링크(B-2).
- 이상감지 페이지(`manage/anomaly`)의 `/generator` 링크 교체(진입점 A=챗으로 결정, 페이지 연계는 후속).
- 신규 generation 생성 풀체인(기존 후보 재사용 전제).
