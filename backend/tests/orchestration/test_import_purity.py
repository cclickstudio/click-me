# 오케스트레이터 코어가 domain.management 내부를 직접 import하지 않음(등록/bootstrap만 예외)
import ast
import pathlib

_CORE = (
    "routing.py",
    "contracts.py",
    "registry.py",
    "plan.py",
    "planner.py",
    "executor.py",
    "turn.py",
    "policy.py",
    "context.py",
)
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
    base = pathlib.Path(__file__).resolve().parents[2] / "api" / "orchestration"
    for name in _CORE:
        for mod in _imports(base / name):
            assert not mod.startswith(_FORBIDDEN), f"{name} imports {mod}"


def test_core_modules_do_not_import_any_domain():
    # S3 추가 — generator 어댑터가 domain.generator에 있어도 core는 import 금지.
    forbidden = ("domain.management", "domain.generator", "domain.simulation")
    base = pathlib.Path(__file__).resolve().parents[2] / "api" / "orchestration"
    for name in _CORE:
        for mod in _imports(base / name):
            for f in forbidden:
                assert not mod.startswith(f), f"{name} imports {mod}"


def test_bootstrap_is_allowed_to_import_management():
    # 대조군 — bootstrap(composition root)은 도메인 import가 허용됨
    base = pathlib.Path(__file__).resolve().parents[2] / "api" / "orchestration"
    assert any(m.startswith(_FORBIDDEN) for m in _imports(base / "bootstrap.py"))
