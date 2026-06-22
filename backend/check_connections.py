"""S3·LangSmith 연결 확인 스크립트 — 확인 후 삭제"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from core.config import settings  # noqa: E402

# main.py와 동일하게 os.environ 주입
if settings.LANGSMITH_API_KEY:
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ["LANGSMITH_TRACING"] = "true"
else:
    os.environ["LANGSMITH_TRACING"] = "false"


async def test_s3() -> None:
    print("\n── S3 연결 테스트 ──")
    try:
        from tools.storage.s3 import download_bytes, upload_bytes

        print(f"  버킷: {settings.s3_bucket_name}  리전: {settings.aws_region}")

        test_key = "test/connection-check.txt"
        test_data = b"clickme-s3-ok"

        await upload_bytes(test_data, test_key, content_type="text/plain")
        print(f"  [OK] 업로드 성공: {test_key}")

        data = await download_bytes(test_key)
        assert data == test_data, "다운로드 데이터 불일치"
        print(f"  [OK] 다운로드 성공 ({len(data)} bytes)")

    except Exception as exc:
        print(f"  [FAIL] S3 실패: {exc}")


def test_langsmith() -> None:
    print("\n── LangSmith 연결 테스트 ──")
    try:
        from langsmith import Client

        key_preview = (
            settings.LANGSMITH_API_KEY[:12] + "..." if settings.LANGSMITH_API_KEY else "(비어있음)"
        )
        print(f"  프로젝트: {settings.LANGSMITH_PROJECT}")
        print(f"  엔드포인트: {settings.LANGSMITH_ENDPOINT}")
        print(f"  API 키: {key_preview}")

        client = Client()

        if hasattr(client, "tracing_is_enabled"):
            print(f"  트레이싱 활성: {client.tracing_is_enabled()}")

        # 실제 API 호출로 연결 검증
        projects = list(client.list_projects(limit=3))
        names = [p.name for p in projects]
        print(f"  [OK] API 연결 성공 -- 조회된 프로젝트: {names}")

    except Exception as exc:
        print(f"  [FAIL] LangSmith 실패: {exc}")


async def main() -> None:
    await test_s3()
    test_langsmith()
    print()


if __name__ == "__main__":
    asyncio.run(main())
