# scripts/

프로젝트 운영을 돕는 유틸 스크립트 모음.

## new_worktree.py — 워크트리 생성 + 필수 파일 자동 복사

새 git worktree를 만들고, **gitignore돼서 워크트리에 따라오지 않는 필수 파일**(`.env`·폰트)을 함께 복사한다.

### 왜 필요한가

`git worktree add`는 git이 **추적하는** 파일만 새 워크트리에 체크아웃한다. 아래 파일들은 `.gitignore` 대상이라 워크트리에 딸려오지 않는다.

| 대상 | 없으면 |
| --- | --- |
| `backend/.env` | 백엔드가 설정/시크릿 없이 기동 실패 |
| `frontend/.env.local` | 프론트가 API URL 등 없이 동작 이상 |
| `backend/assets/fonts/` (Pretendard) | PDF 리포트 폰트 깨짐 |
| `frontend/src/app/fonts/` (NotoSansKR) | 프론트 빌드가 폰트 없이 깨짐 |

그래서 워크트리를 새로 팔 때마다 이 파일들을 손으로 복사해야 했는데, 이 스크립트가 그 복사까지 한 번에 처리한다.

### 사용법

```bash
# 기본 — 작업명만 주면 경로·브랜치를 관례대로 만든다
uv run python scripts/new_worktree.py <작업명>

# 예: chat-ui 작업용 워크트리
uv run python scripts/new_worktree.py chat-ui
#   → 워크트리:  ../click-me-chat-ui
#   → 브랜치:    feat/chat-ui
#   → base:      현재 HEAD
#   → 그리고 위 표의 .env·폰트를 새 워크트리로 복사
```

### 옵션

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `name` (필수) | — | 작업명. 경로·브랜치 기본값의 재료 |
| `--path` | `../click-me-<작업명>` | 워크트리를 만들 경로 |
| `--branch` | `feat/<작업명>` | 새로 만들 브랜치명 |
| `--base` | `HEAD` | 브랜치를 딸 기준 커밋/브랜치 |

```bash
# 경로·브랜치·base를 직접 지정
uv run python scripts/new_worktree.py chat-ui \
  --path ../wt-chat --branch feat/chat-experiment --base main
```

### 동작

1. `git worktree add <경로> -b <브랜치> <base>` 로 워크트리 생성
2. 스크립트 상단 `COPY_TARGETS`의 각 항목을 리포 루트에서 새 워크트리로 복사
   - 파일이면 파일 복사, 디렉터리면 통째로 복사(`dirs_exist_ok`)
   - 원본이 없으면 `! skip` 로그만 남기고 계속 진행
3. 새 세션에서 이동할 경로 안내 출력

경로가 이미 존재하면 아무것도 만들지 않고 에러로 종료한다.

### 복사 대상 바꾸기

복사할 파일이 늘거나 바뀌면 `new_worktree.py` 상단의 `COPY_TARGETS` 리스트만 고치면 된다(리포 루트 기준 상대경로).

```python
COPY_TARGETS = [
    "backend/.env",
    "frontend/.env.local",
    "backend/assets/fonts",
    "frontend/src/app/fonts",
]
```

> `node_modules`·`.venv`는 용량이 커서 일부러 복사하지 않는다. 새 워크트리에서는
> `cd frontend && pnpm install`, `cd backend && uv sync` 로 각각 설치한다.

### 생성 후

```bash
cd ../click-me-<작업명>
cd frontend && pnpm install        # 의존성 설치
cd ../backend && uv sync           # 의존성 설치
```
