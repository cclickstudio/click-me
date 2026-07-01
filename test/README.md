# 테스트 가이드

ClickMe의 모든 테스트는 이 `test/` 디렉터리에 모여 있습니다. 두 종류가 있고, 도구 체계가
달라(백엔드는 `uv`/pytest, E2E는 `pnpm`/Playwright) 각각 따로 실행합니다.

```
test/
├── README.md        이 문서
├── run-all.py       통합 실행기 (backend + e2e 순차)
├── checklist.md     수동 점검 체크리스트
├── backend/         백엔드 단위·통합 테스트 (pytest)
│   ├── ruff.toml    테스트 전용 lint 규칙(backend/pyproject.toml 상속 + 완화)
│   ├── conftest.py  USE_MOCK=true 등 hermetic 설정
│   └── <도메인>/    admin · assistant · billing · chat · generator · harness · management · simulation ...
└── e2e/             브라우저 E2E (Playwright, frontend+backend 대상)
    ├── *.spec.ts
    └── helpers/
```

## 한 번에 실행

```bash
python test/run-all.py            # 전체(backend + e2e)
python test/run-all.py backend    # 백엔드 pytest만
python test/run-all.py e2e        # 프론트 Playwright E2E만
```

`run-all.py`는 각 디렉터리에서 알맞은 도구로 순차 실행하고, 하나라도 실패하면 비0으로 종료합니다.

## 백엔드 (pytest)

테스트 코드는 `test/backend/`에 있지만 **실행은 `backend/`에서** 합니다 — 가상환경(uv)과 import
루트가 backend에 있기 때문입니다. `backend/pyproject.toml`의 `testpaths`가 `../test/backend`를
가리키므로 인자 없이 실행하면 자동으로 찾습니다.

```bash
cd backend
uv run pytest                                   # 전체
uv run pytest -c pyproject.toml ../test/backend/simulation -v   # 일부만 (아래 주의 참고)
```

> **주의 — 일부만 돌릴 때는 `-c pyproject.toml` 필수.**
> 경로 인자를 주면 pytest가 설정(pyproject)을 자동으로 못 찾아 `pythonpath`가 적용되지 않고
> `ModuleNotFoundError: No module named 'tools'`가 납니다. `-c pyproject.toml`로 설정을
> 명시하면 해결됩니다. 인자 없이 전체 실행할 때는 자동 탐색되어 불필요합니다.

import 루트는 두 개입니다(`backend/pyproject.toml`의 `pythonpath`):
- `.` — backend 소스(`api` · `core` · `domain` · `tools`)
- `../test/backend` — 테스트끼리 공유하는 헬퍼(`management.helpers` 등)

## E2E (Playwright)

`frontend/`에서 실행합니다. dev 서버는 자동 기동되지만 **backend(8000)는 따로 떠 있어야** 합니다.
설정은 루트 `playwright.config.ts`(testDir = `./test/e2e`).

```bash
# 터미널 1
cd backend && uv run uvicorn api.main:app --reload --port 8000
# 터미널 2
cd frontend && pnpm test:e2e
```

시뮬 E2E는 실제 LLM 호출이라 1회 ~1분 → 직렬·재시도 1회·타임아웃 3분으로 설정돼 있습니다.

## CI 연동 (`.github/workflows/ci.yml`)

- **backend 잡** — `ruff check . ../test/backend`(테스트 코드도 lint) + `uv run pytest`(전체).
- **e2e 잡(수동 트리거)** — `uv run pytest -c pyproject.toml ../test/backend/admin`(실 DB 통합) → Playwright E2E.

테스트 lint 규칙은 `test/backend/ruff.toml`이 `backend/pyproject.toml`을 상속하면서
타입 어노테이션(ANN)·import 순서(E402) 완화를 얹습니다.
