# git worktree 생성 후 추적되지 않는 필수 파일(.env·폰트)을 새 워크트리로 복사하는 헬퍼
"""
새 git worktree를 만들고, gitignore돼서 따라오지 않는 필수 파일들을 함께 복사한다.

사용법:
    uv run python scripts/new_worktree.py <작업명>
    uv run python scripts/new_worktree.py <작업명> --path <워크트리경로> --branch <브랜치명> --base <기준브랜치>

기본값:
    path   = ../click-me-<작업명>   (리포 루트 옆)
    branch = feat/<작업명>
    base   = 현재 HEAD

예:
    uv run python scripts/new_worktree.py chat-ui
      → ../click-me-chat-ui 워크트리, feat/chat-ui 브랜치 생성 + .env·폰트 복사
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# 리포 루트 기준 상대경로. 파일이면 파일 복사, 디렉터리면 통째로 복사.
# 여기 한 줄 추가하면 이후 모든 워크트리 생성에 자동 반영된다.
COPY_TARGETS = [
    "backend/.env",
    "frontend/.env.local",
    "backend/assets/fonts",
    "frontend/src/app/fonts",
]

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def copy_targets(dest_root: Path) -> None:
    for rel in COPY_TARGETS:
        src = REPO_ROOT / rel
        dst = dest_root / rel
        if not src.exists():
            print(f"  ! skip (원본 없음): {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"  + copied dir : {rel}")
        else:
            shutil.copy2(src, dst)
            print(f"  + copied file: {rel}")


def main() -> int:
    parser = argparse.ArgumentParser(description="워크트리 생성 + 필수 untracked 파일 복사")
    parser.add_argument("name", help="작업명 (예: chat-ui)")
    parser.add_argument("--path", help="워크트리 경로 (기본: ../click-me-<작업명>)")
    parser.add_argument("--branch", help="브랜치명 (기본: feat/<작업명>)")
    parser.add_argument("--base", default="HEAD", help="기준 브랜치/커밋 (기본: HEAD)")
    args = parser.parse_args()

    path = Path(args.path) if args.path else REPO_ROOT.parent / f"click-me-{args.name}"
    branch = args.branch or f"feat/{args.name}"

    if path.exists():
        print(f"에러: 경로가 이미 존재합니다: {path}", file=sys.stderr)
        return 1

    print(f"# 워크트리 생성: {path}  (브랜치 {branch}, base {args.base})")
    run(["git", "worktree", "add", str(path), "-b", branch, args.base])

    print("# 필수 untracked 파일 복사")
    copy_targets(path.resolve())

    print("\n완료. 새 세션에서:")
    print(f"  cd {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
