# 주말 루프 판정 스크립트 — ruff → 도메인 pytest → (옵션)프론트를 순차 실행하고 pass/fail을 반환한다.
#
# 사용법 (리포 루트에서):
#   uv run --directory backend python ../weekend-loop/verify.py            # 기본: simulation 범위
#   python weekend-loop/verify.py --scope simulation                       # 시뮬만 (빠름)
#   python weekend-loop/verify.py --scope backend                          # 백엔드 전체
#   python weekend-loop/verify.py --scope all                              # 백엔드 + 프론트(lint/build)
#   python weekend-loop/verify.py --scope simulation --no-ruff             # 테스트만
#
# 종료 코드: 모든 단계 통과 시 0, 하나라도 실패하면 1. 루프가 이 코드로 그린/레드를 판정한다.
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

# 특정 경로를 지정해 pytest를 부를 땐 -c pyproject.toml 을 반드시 붙인다.
# 안 붙이면 rootdir/pythonpath 해석이 어긋나 asyncio_mode=auto 가 안 실려 async 테스트가 거짓 실패한다.
PYTEST_BASE = ["uv", "run", "pytest", "-c", "pyproject.toml"]

SCOPE_TARGETS = {
    "simulation": "../test/backend/simulation",
    "management": "../test/backend/management",
    "generator": "../test/backend/generator",
    "chat": "../test/backend/chat",
    "backend": "../test/backend",
}


def run(name: str, cmd: list[str], cwd: Path) -> bool:
    """한 단계를 실행하고 통과 여부를 출력·반환한다."""
    print(f"\n=== [{name}] {' '.join(cmd)}  (cwd={cwd.name}) ===", flush=True)
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd)
    dur = time.monotonic() - started
    ok = proc.returncode == 0
    print(f"--- [{name}] {'PASS' if ok else 'FAIL'} ({dur:.1f}s, exit={proc.returncode}) ---", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="주말 루프 판정 게이트")
    parser.add_argument(
        "--scope",
        default="simulation",
        choices=[*SCOPE_TARGETS.keys(), "all"],
        help="검증 범위 (기본: simulation)",
    )
    parser.add_argument("--no-ruff", action="store_true", help="ruff 단계 생략(테스트만)")
    parser.add_argument("--no-front", action="store_true", help="scope=all 이어도 프론트 생략")
    args = parser.parse_args()

    results: list[tuple[str, bool]] = []

    # 1) ruff — 백엔드를 건드렸으면 항상 먼저. 빠르고 CI 게이트와 동일.
    if not args.no_ruff:
        results.append(
            ("ruff-format", run("ruff-format", ["uv", "run", "ruff", "format", "--check", ".", "../test/backend"], BACKEND))
        )
        results.append(
            ("ruff-check", run("ruff-check", ["uv", "run", "ruff", "check", ".", "../test/backend"], BACKEND))
        )

    # 2) pytest — 범위별. all 이면 백엔드 전체.
    pytest_scope = "backend" if args.scope == "all" else args.scope
    target = SCOPE_TARGETS[pytest_scope]
    results.append(("pytest", run(f"pytest:{pytest_scope}", [*PYTEST_BASE, target, "-q"], BACKEND)))

    # 3) 프론트 — scope=all 에서만. 프론트 소스를 건드렸을 때 의미가 있다.
    if args.scope == "all" and not args.no_front and FRONTEND.exists():
        results.append(("pnpm-lint", run("pnpm-lint", ["pnpm", "lint"], FRONTEND)))
        results.append(("pnpm-build", run("pnpm-build", ["pnpm", "build"], FRONTEND)))

    # 요약 (Windows cp949 콘솔 호환 — ASCII만 사용)
    print("\n" + "=" * 48)
    for name, ok in results:
        print(f"  [{'OK' if ok else 'XX'}] {name}")
    all_ok = all(ok for _, ok in results)
    print("=" * 48)
    print("RESULT:", "GREEN" if all_ok else "RED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
