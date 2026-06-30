# 오케스트레이터 코어가 domain.management 내부를 직접 import하지 않음(등록/bootstrap만 예외)
import ast
import pathlib

# 우리 브랜치는 보은 orchestration 중 routing.py만 체리픽(contracts/registry/bootstrap은
# 거부 — 키워드 plan-execute 모델, LLM Deep Agent와 충돌). 존재하는 파일만 검사.
_CORE = ("routing.py",)
_FORBIDDEN = "domain.management"


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(n.name for n in node.names)
    return mods


def test_core_modules_do_not_import_management():
    base = pathlib.Path(__file__).resolve().parents[3] / "backend" / "api" / "orchestration"
    for name in _CORE:
        for mod in _imports(base / name):
            assert not mod.startswith(_FORBIDDEN), f"{name} imports {mod}"
