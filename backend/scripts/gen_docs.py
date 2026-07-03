# FastAPI 앱과 Next.js app 트리에서 API·라우트를 추출해 문서를 자동 생성/검사하는 스크립트
"""ClickMe 문서 자동 생성기.

- `docs/api-endpoints.md`      ← `api.main:app`의 라우트 테이블에서 추출
- `docs/frontend-routes.md`    ← `frontend/src/app/**/{page,route}.tsx` 파일트리에서 추출
- `CLAUDE.md`의 AUTOGEN 마커 구간 ← 위 두 문서의 요약(개수 + 링크)

사용:
    uv run python scripts/gen_docs.py           # 문서 재생성(변경분만 기록)
    uv run python scripts/gen_docs.py --check    # 변경이 필요하면 exit 1 (CI drift 검사용)

라우터/페이지를 추가하면 커밋 시 pre-commit 훅이, PR/Push 시 CI가 이 스크립트로 문서를 동기화한다.
직접 편집한 생성 문서는 다음 실행 때 덮어써진다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT.parent.parent
REPO_ROOT = BACKEND_ROOT.parent
DOCS = REPO_ROOT / "docs"
API_DOC = DOCS / "api-endpoints.md"
ROUTES_DOC = DOCS / "frontend-routes.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
FRONT_APP = REPO_ROOT / "frontend" / "src" / "app"

AUTOGEN_START = "<!-- AUTOGEN:docs-index START -->"
AUTOGEN_END = "<!-- AUTOGEN:docs-index END -->"

_GEN_NOTE = (
    "> 이 파일은 `backend/scripts/gen_docs.py`가 코드에서 **자동 생성**합니다. "
    "직접 편집하지 말고 소스를 고친 뒤 스크립트를 다시 실행하세요"
    "(커밋 시 pre-commit 훅이 자동 갱신)."
)


# ────────────────────────────────────────────────────────────
# API 엔드포인트 추출 (FastAPI app)
# ────────────────────────────────────────────────────────────
def collect_api_endpoints() -> list[tuple[str, str, str, tuple[str, ...]]]:
    """(method, path, name, tags) 목록을 반환. 앱 import 실패 시 예외 전파."""
    # 라우트 메타만 읽으므로 필수 설정에 더미값을 주입(실제 값 불필요).
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/none")
    os.environ.setdefault("OPENAI_API_KEY", "dummy")
    os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "dummy")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "dummy")
    os.environ.setdefault("USE_MOCK", "true")
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from fastapi.routing import APIRoute

    from api.main import app

    rows: list[tuple[str, str, str, tuple[str, ...]]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(m for m in (route.methods or set()) if m not in {"HEAD", "OPTIONS"})
        tags = tuple(str(t) for t in (route.tags or ()))
        for method in methods:
            rows.append((method, route.path, route.name or "", tags))
    return rows


def _group_of(path: str, tags: tuple[str, ...]) -> str:
    if tags:
        return tags[0]
    segs = [s for s in path.split("/") if s]
    if segs and segs[0] == "api" and len(segs) > 1:
        return segs[1]
    return segs[0] if segs else "root"


def render_api_doc(rows: list[tuple[str, str, str, tuple[str, ...]]]) -> str:
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for method, path, name, tags in rows:
        groups.setdefault(_group_of(path, tags), []).append((method, path, name))

    lines: list[str] = [
        "# ClickMe API 엔드포인트 (자동 생성)",
        "",
        _GEN_NOTE,
        "",
        f"총 **{len(rows)}개** 엔드포인트 · **{len(groups)}개** 그룹.",
        "",
    ]
    for group in sorted(groups):
        entries = sorted(groups[group], key=lambda e: (e[1], e[0]))
        lines.append(f"## {group}")
        lines.append("")
        lines.append("| Method | Path | Name |")
        lines.append("|---|---|---|")
        for method, path, name in entries:
            lines.append(f"| {method} | `{path}` | {name} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ────────────────────────────────────────────────────────────
# 프론트엔드 라우트 추출 (Next.js App Router)
# ────────────────────────────────────────────────────────────
def _route_from_file(rel: Path) -> str:
    # rel: src/app 기준 상대경로(예: (app)/admin/companies/page.tsx)
    segs = list(rel.parts[:-1])  # 파일명(page/route) 제거
    out: list[str] = []
    for seg in segs:
        if seg.startswith("(") and seg.endswith(")"):
            continue  # 라우트 그룹은 URL에 안 들어감
        if seg.startswith("[[...") and seg.endswith("]]"):
            out.append(f"*{seg[5:-2]}?")  # optional catch-all [[...name]]
        elif seg.startswith("[...") and seg.endswith("]"):
            out.append(f"*{seg[4:-1]}")  # catch-all
        elif seg.startswith("[") and seg.endswith("]"):
            out.append(f":{seg[1:-1]}")  # dynamic segment
        else:
            out.append(seg)
    return "/" + "/".join(out) if out else "/"


def collect_front_routes() -> list[tuple[str, str, str]]:
    """(route, file, kind) 목록. kind = page | api(route.ts)."""
    if not FRONT_APP.exists():
        return []
    rows: list[tuple[str, str, str]] = []
    for path in sorted(FRONT_APP.rglob("*")):
        if path.name in {"page.tsx", "page.jsx"}:
            kind = "page"
        elif path.name in {"route.ts", "route.tsx", "route.js"}:
            kind = "api"
        else:
            continue
        rel = path.relative_to(FRONT_APP)
        route = _route_from_file(rel)
        file_disp = path.relative_to(REPO_ROOT).as_posix()
        rows.append((route, file_disp, kind))
    return rows


def render_routes_doc(rows: list[tuple[str, str, str]]) -> str:
    pages = [r for r in rows if r[2] == "page"]
    apis = [r for r in rows if r[2] == "api"]
    lines: list[str] = [
        "# ClickMe 프론트엔드 라우트 (자동 생성)",
        "",
        _GEN_NOTE,
        "",
        f"총 **{len(pages)}개** 페이지" + (f" · **{len(apis)}개** route 핸들러." if apis else "."),
        "",
        "| 라우트 | 파일 | 종류 |",
        "|---|---|---|",
    ]
    for route, file_disp, kind in sorted(rows):
        lines.append(f"| `{route}` | `{file_disp}` | {kind} |")
    return "\n".join(lines).rstrip() + "\n"


# ────────────────────────────────────────────────────────────
# CLAUDE.md AUTOGEN 구간
# ────────────────────────────────────────────────────────────
def render_claude_block(n_api: int, n_pages: int) -> str:
    api_link = "[docs/api-endpoints.md](docs/api-endpoints.md)"
    route_link = "[docs/frontend-routes.md](docs/frontend-routes.md)"
    return "\n".join(
        [
            AUTOGEN_START,
            f"- **API 엔드포인트 {n_api}개** — 전체 목록 {api_link} (자동 생성)",
            f"- **프론트 라우트 {n_pages}개** — 전체 목록 {route_link} (자동 생성)",
            AUTOGEN_END,
        ]
    )


def replace_claude_block(text: str, block: str) -> str:
    start = text.find(AUTOGEN_START)
    end = text.find(AUTOGEN_END)
    if start == -1 or end == -1:
        raise SystemExit(
            f"CLAUDE.md에 AUTOGEN 마커가 없습니다: {AUTOGEN_START}…{AUTOGEN_END}. 먼저 추가하세요."
        )
    return text[:start] + block + text[end + len(AUTOGEN_END) :]


# ────────────────────────────────────────────────────────────
# 파일 쓰기/검사
# ────────────────────────────────────────────────────────────
def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def sync_file(path: Path, content: str, check: bool, changed: list[str]) -> None:
    current = _norm(path.read_text(encoding="utf-8")) if path.exists() else None
    if current == _norm(content):
        return
    changed.append(path.relative_to(REPO_ROOT).as_posix())
    if not check:
        path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    check = "--check" in sys.argv[1:]
    changed: list[str] = []

    api_rows = collect_api_endpoints()
    front_rows = collect_front_routes()
    n_pages = sum(1 for r in front_rows if r[2] == "page")

    sync_file(API_DOC, render_api_doc(api_rows), check, changed)
    sync_file(ROUTES_DOC, render_routes_doc(front_rows), check, changed)

    claude_text = CLAUDE_MD.read_text(encoding="utf-8")
    new_claude = replace_claude_block(claude_text, render_claude_block(len(api_rows), n_pages))
    sync_file(CLAUDE_MD, new_claude, check, changed)

    if check:
        if changed:
            print(
                "문서가 코드와 어긋납니다. `uv run python scripts/gen_docs.py` 실행 후 커밋하세요:"
            )
            for c in changed:
                print(f"  - {c}")
            return 1
        print("문서 동기화 OK.")
        return 0

    if changed:
        print("문서 갱신:")
        for c in changed:
            print(f"  - {c}")
    else:
        print("변경 없음.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
