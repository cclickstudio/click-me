import subprocess
import sys


def ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright

        # 브라우저 실행 시도
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()

    except Exception:
        print("⚠️ Playwright browser not found. Installing...")

        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )


def main():
    # 1. playwright 브라우저 보장
    ensure_playwright()

    # 2. dev 서버 실행
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
            "tools",
            "--reload-dir",
            "core",
            "--reload-dir",
            "domain",
            "--port",
            "8000",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()