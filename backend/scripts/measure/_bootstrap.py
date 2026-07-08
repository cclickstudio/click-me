# 측정 스크립트 공통 부트스트랩 — backend 루트를 import 경로·cwd로 고정
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def setup() -> Path:
    """backend 루트를 sys.path와 cwd로 고정한다 (.env·core/domain import 안정화)."""
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    os.chdir(BACKEND_ROOT)
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지
    return BACKEND_ROOT
