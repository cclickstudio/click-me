# 주말 루프 컨텍스트 노트

새 세션/루프가 이 파일 + `checklist.md` 만 읽고도 독립적으로 작업할 수 있도록 필요한 배경을 모아둔다.

## 목표
집행 전 광고를 AI 가상 소비자로 테스트하는 플랫폼(ClickMe)의 **시뮬레이션 도메인을 중점 견고화**하고, 그린이 유지되면 백엔드 전체 → 프론트로 범위를 넓힌다.
"실제 사람과 동일한 응답"이 아니라 "코드가 명세대로 정확·견고하게 동작"을 목표로 한다.

## 기준선 (2026-07-03 확인)
- 시뮬 테스트: **150 passed, 7 skipped** (~12s)
- 백엔드 전체: **846 passed, 16 skipped** (~36s)
- ruff check / format: **All checks passed** (467 files formatted)
- 즉, 시작점은 완전 그린. 루프는 이 그린을 깨지 않는 선에서만 전진한다.

## 판정 커맨드 (중요)
특정 도메인만 돌릴 땐 **반드시 `-c pyproject.toml`** 을 붙인다. 안 붙이면 rootdir/pythonpath 해석이 어긋나
`asyncio_mode=auto` 가 안 실려 async 테스트 34개가 "async def not supported"로 **거짓 실패**한다.

```bash
# 리포 루트 = C:\doyeon\lecture\2026\finalProject\ClickStudio\click-me
# 한 방에 (권장):
python weekend-loop/verify.py --scope simulation      # 시뮬만
python weekend-loop/verify.py --scope backend         # 백엔드 전체
python weekend-loop/verify.py --scope all             # + 프론트 lint/build

# 수동으로 개별 실행할 때 (cwd = backend):
uv run pytest -c pyproject.toml ../test/backend/simulation -q
uv run ruff format --check . ../test/backend
uv run ruff check . ../test/backend
```

- 테스트는 `test/backend/conftest.py` 가 `USE_MOCK=true` 를 강제 → **외부 API 키·DB·네트워크 없이 hermetic**.
- LangSmith 트레이싱도 conftest에서 off. 따라서 루프는 비용 없이 무한 반복 가능.

## 환경 주의 (Windows / 셸)
- Bash 도구는 cwd 드리프트가 있어 `cd backend` 가 실패할 수 있다. 절대경로 또는 `uv run --directory <backend절대경로>` 사용.
- 다만 pytest는 pythonpath 상대해석 때문에 **cwd가 실제로 backend여야** 한다 → PowerShell `Set-Location <backend절대경로>` 후 실행, 또는 verify.py 사용(내부에서 cwd 처리).
- PM 교차 금지: backend는 uv만, frontend는 pnpm만.

## 시뮬 도메인 지도 (핵심 경로)
- 파이프라인: `domain/simulation/graph/run_graph.py` — interpret_ad → load_panel → react(fan-out) → aggregate
- 반응 서브그래프: `graph/reaction_graph.py` — 생성 + QA 재시도(MAX_ATTEMPTS)
- 4대 KPI 집계(결정적, LLM✗): `tools/aggregation/aggregator.py` `BasicAggregator`
  - click_intent_rate = AISAS.action 가중비율 + 가중 부트스트랩 CI(seed=0, 2000 iters)
  - purchase_intent / trust_avg = 1~5 가중평균, rejection_rate / brand_recognition_rate = 가중비율
  - variance_warning = 구매의도 가중표준편차 < 0.5, effective_n = Kish 공식
- Composition Root(mock↔실 전환 유일 지점): `wiring.py`
  - 시뮬 경로는 항상 실 Gemini(폴백 없음, GEMINI_API_KEY 없으면 RuntimeError). 반응은 OPENAI 있으면 GPT 폴백.
  - 토론(debate)만 `use_mock` 유지.
- 계약/스키마: `contracts/schemas.py` — PersonaReaction, SimulationAggregate 등.
- 영속화: `repositories/` (DB 미구성이면 인메모리만).

## 하지 말 것 (재확인)
프롬프트/LLM 파라미터 튜닝, 실 외부 API 개선, KPI 캘리브레이션, `core/models.py`·db-schema 단독 변경,
`api/main.py` 라우터 순서 변경. 자세한 건 checklist.md "절대 하지 말 것" 참고.

## 커밋 규칙
`타입: 한국어 설명` (add/edit/fix/delete). 한 논리 단위 = 한 커밋. 백엔드 .py 수정 후엔 ruff 먼저.
