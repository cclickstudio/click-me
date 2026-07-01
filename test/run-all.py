# 백엔드 pytest + 프론트 playwright E2E를 한 번에 실행하는 통합 러너.
"""테스트 통합 실행기.

사용:
    python test/run-all.py            # 전체(backend + e2e)
    python test/run-all.py backend    # 백엔드 pytest만
    python test/run-all.py e2e        # 프론트 Playwright E2E만

backend와 e2e는 도구 체계가 달라(uv/pytest vs pnpm/playwright) 한 프로세스로는 못 돈다.
이 스크립트가 각 디렉터리에서 순차 실행하고, 둘 중 하나라도 실패하면 비0으로 종료한다.
"""

import subprocess
import sys
from pathlib import Path

# Windows 기본 콘솔(cp949)에서 한글·기호 출력이 깨지지 않게 best-effort로 UTF-8 재설정.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — 재설정 불가 환경이면 그냥 기본 인코딩 사용
    pass

ROOT = Path(__file__).resolve().parents[1]  # repo 루트


def run(label: str, cmd: str, cwd: Path) -> int:
    rel = cwd.relative_to(ROOT)
    print(f"\n{'=' * 64}\n>> {label}  -  {cmd}  (cwd: {rel})\n{'=' * 64}", flush=True)
    # uv/pnpm은 Windows에서 .cmd 래퍼라 shell=True로 PATH 해석을 맡긴다.
    return subprocess.run(cmd, cwd=cwd, shell=True).returncode


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target not in ("all", "backend", "e2e"):
        print(f"알 수 없는 인자: {target} (all|backend|e2e)")
        sys.exit(2)

    rc = 0
    if target in ("all", "backend"):
        # pyproject의 testpaths(../test/backend)를 가리키므로 인자 없이 실행.
        rc |= run("backend (pytest)", "uv run pytest", ROOT / "backend")
    if target in ("all", "e2e"):
        rc |= run("e2e (playwright)", "pnpm test:e2e", ROOT / "frontend")

    print(f"\n{'=' * 64}\n결과: {'성공' if rc == 0 else '실패'} (exit={rc})\n{'=' * 64}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
