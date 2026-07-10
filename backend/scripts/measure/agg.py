# 정성검수/ VLM CSV를 집계해 RESULTS.md용 결과 블록을 출력
"""사용법:
    uv run python scripts\\measure\\agg.py --csv <경로>            # 단일 CSV
    uv run python scripts\\measure\\agg.py --csv a.csv b.csv       # 여러 개 나란히

review_by_human_*.csv(사람 감사모드) · text_accuracy.csv(VLM) 모두 동일 스키마
(file,method,element,status,expected,seen)라 그대로 집계된다.
출력을 RESULTS.md의 "결과" 표에 붙여넣어 기록한다.
"""

import argparse
import collections
import csv
import sys

# Windows cmd(cp949)에서 한글 출력 크래시 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

COPY = ("headline", "body", "cta")
STATUS_ORDER = ("exact", "typo", "broken", "cut", "missing")


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def analyze(name, rows):
    imgs = collections.OrderedDict()
    for r in rows:
        imgs.setdefault(r["file"], []).append(r)

    def defect(s):
        return s != "exact"

    flawless = sum(1 for rs in imgs.values() if all(not defect(x["status"]) for x in rs))
    copy_flawless = sum(
        1
        for rs in imgs.values()
        if all(not defect(x["status"]) for x in rs if x["element"] in COPY)
    )
    total = len(rows)
    defects = sum(1 for r in rows if defect(r["status"]))

    copy_rows = [r for r in rows if r["element"] in COPY]
    copy_exact = sum(1 for r in copy_rows if r["status"] == "exact")
    other_rows = [r for r in rows if r["element"] == "other"]
    other_exact = sum(1 for r in other_rows if r["status"] == "exact")
    other_stat = collections.Counter(r["status"] for r in other_rows)

    n = len(imgs)
    print(f"\n### {name}")
    print("| 지표 | 값 |")
    print("|---|---|")
    print(f"| 이미지 수 | {n} |")
    print(f"| 텍스트 인스턴스 총계 | {total} |")
    print(f"| 카피 정확율(headline+body+cta) | {copy_exact}/{len(copy_rows)} = {pct(copy_exact, len(copy_rows))} |")
    print(f"| 라벨(other) 정확율 | {other_exact}/{len(other_rows)} = {pct(other_exact, len(other_rows))} |")
    print(f"| 전체 결함율 | {defects}/{total} = {pct(defects, total)} |")
    print(f"| 무결점 이미지 비율(전체) | {flawless}/{n} = {pct(flawless, n)} |")
    print(f"| 카피만 무결점 이미지 비율 | {copy_flawless}/{n} = {pct(copy_flawless, n)} |")
    parts = " / ".join(f"{s} {other_stat.get(s, 0)}" for s in STATUS_ORDER)
    print(f"\n**status 분해(other)**: {parts}")


def pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "n/a"


def main():
    ap = argparse.ArgumentParser(description="정성검수/VLM CSV 집계 → RESULTS.md 결과 블록")
    ap.add_argument("--csv", nargs="+", required=True, help="집계할 CSV 경로(들)")
    args = ap.parse_args()
    for path in args.csv:
        analyze(path, load(path))


if __name__ == "__main__":
    main()
