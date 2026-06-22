"""광고 이미지 생성 end-to-end 확인 스크립트 — S3 3장 업로드 + LangSmith 트레이스.
확인 후 삭제할 것.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from core.config import settings  # noqa: E402

# main.py 와 동일하게 LangSmith 환경변수 주입
if settings.LANGSMITH_API_KEY:
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ["LANGSMITH_TRACING"] = "true"
    print(f"[LangSmith] 프로젝트: {settings.LANGSMITH_PROJECT}  트레이싱: ON")
else:
    print("[LangSmith] API 키 없음 — 트레이싱 OFF")

from domain.generator.contracts.schemas import GenerationCreateRequest  # noqa: E402
from domain.generator.graph.pipeline import generation_graph  # noqa: E402
from tools.storage.s3 import presign_get  # noqa: E402


async def main() -> None:
    generation_id = str(uuid.uuid4())

    request = GenerationCreateRequest(
        product_name="프리미엄 텀블러",
        product_description="보온·보냉 12시간 지속, 식품용 스테인리스 소재, 500ml 용량",
        target_audience="20~30대 직장인",
        campaign_objective="conversion",
        width=1080,
        height=1080,
    )

    print(f"\n생성 시작 (ID: {generation_id[:8]}...)")
    print("이미지 생성에 1~3분 소요됩니다.\n")

    config = {
        "run_name": "E2E-Connection-Test",
        "metadata": {"generation_id": generation_id, "test": True},
        "configurable": {},  # emit 없으면 emit_progress 가 자동 무시됨
    }

    final_state = await generation_graph.ainvoke(
        {"generation_id": generation_id, "request": request.model_dump()},
        config=config,
    )

    # S3 결과 확인
    print("── S3 이미지 업로드 결과 ──")
    candidates = final_state.get("candidates", [])
    if not candidates:
        print("  [FAIL] candidates 없음 — 파이프라인 실패")
        return

    for c in candidates:
        key = c["s3_key"]
        url = await presign_get(key, expires_in=600)  # 10분 URL
        status = "[OK]" if url else "[FAIL]"
        print(f"  {status} candidate-{c['idx']}  s3://{settings.s3_bucket_name}/{key}")
        if url:
            print(f"        미리보기 (10분): {url}\n")

    # LangSmith 결과 확인
    print("── LangSmith 트레이스 ──")
    try:
        from langsmith import Client

        client = Client()
        runs = list(
            client.list_runs(
                project_name=settings.LANGSMITH_PROJECT,
                filter='eq(name, "E2E-Connection-Test")',
                limit=1,
            )
        )
        if runs:
            run = runs[0]
            run_url = (
                f"https://smith.langchain.com/projects/{settings.LANGSMITH_PROJECT}/runs/{run.id}"
            )
            print("  [OK] 트레이스 확인됨")
            print(f"       URL: {run_url}")
        else:
            print("  [WAIT] 아직 인덱싱 중 — 30초 후 아래 링크에서 확인")
            print(f"       https://smith.langchain.com/projects/{settings.LANGSMITH_PROJECT}")
    except Exception as exc:
        print(f"  [FAIL] LangSmith 조회 실패: {exc}")

    print("\n완료.")


if __name__ == "__main__":
    asyncio.run(main())
