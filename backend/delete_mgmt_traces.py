# clickme LangSmith 프로젝트에서 management 관련 트레이스만 골라 삭제하는 일회용 정리 스크립트.
# 기본은 dry-run(목록만 출력). 실제 삭제는 `uv run python delete_mgmt_traces.py --delete`.
# 시뮬·제너레이터 등 타 도메인 트레이스는 건드리지 않는다(이름/태그로 management만 선별).
import datetime as dt
import os
import sys
from collections import Counter

import httpx
from dotenv import load_dotenv

# Windows 콘솔(cp949)에서도 한글·em-dash 출력이 깨지거나 죽지 않도록 utf-8 고정.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
os.environ.setdefault("LANGSMITH_API_KEY", os.environ.get("LANGCHAIN_API_KEY", ""))

from langsmith import Client  # noqa: E402 — load_dotenv 이후 임포트

PROJECT = "clickme"
LOOKBACK_DAYS = 30
BATCH = 50  # POST /runs/delete 한 번에 보낼 trace_id 수
MGMT_NAMES = {"regeneration_agent", "diagnosis_agent", "management_assistant"}


def is_mgmt(run) -> bool:
    """management 도메인 트레이스 판별 — 이름 prefix·전용 run_name·태그 중 하나라도 맞으면."""
    name = run.name or ""
    return name.startswith("management") or name in MGMT_NAMES or ("management" in (run.tags or []))


def main() -> None:
    do_delete = "--delete" in sys.argv
    client = Client()
    start = dt.datetime.now(dt.UTC) - dt.timedelta(days=LOOKBACK_DAYS)

    match_names, skip_names = Counter(), Counter()
    trace_ids: list[str] = []
    for run in client.list_runs(project_name=PROJECT, is_root=True, start_time=start):
        if is_mgmt(run):
            match_names[run.name] += 1
            trace_ids.append(str(run.trace_id))
        else:
            skip_names[run.name] += 1

    trace_ids = list(dict.fromkeys(trace_ids))  # 중복 제거

    print(f"=== 삭제 대상 (management) — 트레이스 {len(trace_ids)}개 ===")
    for name, cnt in match_names.most_common():
        print(f"  {cnt:4d}  {name}")
    print("=== 보존 (타 도메인) ===")
    for name, cnt in skip_names.most_common():
        print(f"  {cnt:4d}  {name}")

    if not do_delete:
        print("\n[dry-run] 실제로 지우려면 끝에 --delete 를 붙여 다시 실행하세요.")
        return
    if not trace_ids:
        print("\n삭제할 트레이스가 없습니다.")
        return

    project = client.read_project(project_name=PROJECT)
    headers = {"x-api-key": os.environ["LANGSMITH_API_KEY"], "Content-Type": "application/json"}
    deleted = 0
    for i in range(0, len(trace_ids), BATCH):
        chunk = trace_ids[i : i + BATCH]
        resp = httpx.post(
            f"{client.api_url}/runs/delete",
            headers=headers,
            json={"session_id": str(project.id), "trace_ids": chunk},
            timeout=60,
        )
        resp.raise_for_status()
        deleted += len(chunk)
        print(f"  삭제 {deleted}/{len(trace_ids)}")
    print(f"\n완료 — management 트레이스 {deleted}개 삭제.")


if __name__ == "__main__":
    main()
