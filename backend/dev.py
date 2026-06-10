"""
개발 서버 실행 스크립트
사용법: uv run dev.py
"""

import subprocess
import sys

subprocess.run(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "api.main:app",
        "--reload",
        "--reload-dir",
        "api",
        "--reload-dir",
        "agents",
        "--reload-dir",
        "services",
        "--reload-dir",
        "tools",
        "--reload-dir",
        "core",
        "--port",
        "8000",
    ]
)
