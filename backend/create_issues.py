# 커밋엔 있으나 GitHub Issue가 없는 기능들을 일괄 등록하는 스크립트 (httpx + GitHub REST API)
"""
사용법:
    uv run python create_issues.py --dry-run   # 미리보기(생성 안 함)
    uv run python create_issues.py             # 실제 생성

토큰:
    환경변수 GITHUB_TOKEN 또는 GH_TOKEN 우선, 없으면 `gh auth token`을 자동 호출.
동작:
    기존 이슈(OPEN/CLOSED) 제목과 정확히 일치하면 건너뜀(중복 방지).
"""

import os
import subprocess
import sys

import httpx

REPO = "cclickstudio/click-me"
API = "https://api.github.com"

# 커밋 대조로 추려낸, 대응 이슈가 없는 구현 기능들.
ISSUES = [
    {
        "title": "[Simulation] AI 토론 파이프라인 (전문가4+일반인3·Judge·논제5개)",
        "labels": ["agent-simulation"],
        "body": (
            "집행 전 반응 예측을 위한 멀티에이전트 토론 파이프라인.\n\n"
            "- 패널 구성: 전문가 4 + 일반인 3\n"
            "- 최초 주제(headline) 고정, 논제 5개 생성, Judge 액션 강제\n"
            "- Judge 비용 최적화(라운드정리 Haiku·결론 1회 호출)\n\n"
            "근거 커밋: a5ca1ea, ff59415, 350a15a, dc0a63e"
        ),
    },
    {
        "title": "[Simulation] 토론 후 Q&A — 패널 순차 답변 SSE",
        "labels": ["agent-simulation"],
        "body": (
            "토론 종료 후 사용자 질문에 패널이 순차로 답변하는 Q&A 단계.\n\n"
            "- 입력 계약: question + reactions\n"
            "- 패널 순차 답변을 SSE로 스트리밍\n\n"
            "근거 커밋: f665abd, e98d71a, 7d067be"
        ),
    },
    {
        "title": "[Simulation] 일반인 토론자 선발 게이트 (타깃 적합·LLM 재랭킹·말투)",
        "labels": ["agent-simulation"],
        "body": (
            "토론에 투입할 일반인 토론자를 타깃에 맞춰 선발하는 게이트.\n\n"
            "- 타깃 밖 후보 배제(personas 인구통계), 전 연령형 보정\n"
            "- LLM 재랭킹 게이트 + 함정 테스트(선발 정확도 최우선)\n"
            "- 표현 다양성 위해 말투(tone) 부여\n\n"
            "근거 커밋: c713606, 4fb52c8, a071d62, 439afda, d13e638"
        ),
    },
    {
        "title": "[Simulation] 토론/Q&A LangSmith 단일 트레이스 묶기",
        "labels": ["agent-simulation"],
        "body": (
            "토론 1회와 Q&A를 각각 LangSmith 단일 트레이스로 묶어 관측성 확보.\n\n"
            "- @traceable 부모 run으로 LLM 호출 중첩\n"
            "- wrap_anthropic·wrap_openai로 토론 LLM 호출 트레이싱\n\n"
            "근거 커밋: 0e90a11, a3de5bd, 76a8b4c"
        ),
    },
    {
        "title": "[Frontend] 토론 패널 UI (SSE 스트림·논제 선택·Q&A 채팅)",
        "labels": ["frontend"],
        "body": (
            "토론 진행을 실시간으로 보여주는 프론트 패널.\n\n"
            "- DebatePanel SSE 스트림·결과 렌더\n"
            "- 논제 5개 선택, Q&A DM 채팅, 일반인 수 2/3/4 옵션\n\n"
            "근거 커밋: 788f8d5, 24f27e2, 0ea3bc8"
        ),
    },
    {
        "title": "[Backend] 제품 카테고리 NICE 분류 조회 API",
        "labels": ["backend"],
        "body": (
            "시뮬 입력 폼의 2단계 카테고리 선택을 위한 NICE 분류 조회 API.\n\n"
            "근거 커밋: daf52d8, c4986e9"
        ),
    },
    {
        "title": "[Management] 캠페인 목록·성과 대시보드 (CPM·CVR·시계열)",
        "labels": ["agent-management"],
        "body": (
            "집행 캠페인을 단일 창구에서 관리하는 대시보드.\n\n"
            "- 목록/카드 토글, 상세 시계열, 클릭 시 상세 모달\n"
            "- CPM·CVR 표시(conversions 합성)\n\n"
            "근거 커밋: 570b480, 43491b7, cc930f3, e7f39e1"
        ),
    },
    {
        "title": "[Management] 예산 관리 (게이지·경고·가드레일·한도)",
        "labels": ["agent-management"],
        "body": (
            "예산 소진을 추적하고 한도를 관리하는 화면·API.\n\n"
            "- /budget·/budget/limit 엔드포인트\n"
            "- 90/95/100% 가드레일, 게이지·경고·캠페인 분해\n\n"
            "근거 커밋: de64bc0, 203551a"
        ),
    },
    {
        "title": "[Management] 신규 캠페인 생성 HITL (제안→승인→생성)",
        "labels": ["agent-management"],
        "body": (
            "사람 검토(HITL)를 거치는 신규 캠페인 생성 흐름.\n\n"
            "- /campaigns/create-proposal 제안 엔드포인트(Tier3)\n"
            "- 폼→제안→승인→생성 화면\n\n"
            "근거 커밋: 9965bba, cf5b76d"
        ),
    },
    {
        "title": "[Management] 처방(Remediation) 에이전트 + 에스컬레이션 사다리",
        "labels": ["agent-management"],
        "body": (
            "성과 진단 후 처방 액션을 자율 결정하는 에이전트.\n\n"
            "- decide_action 결정 코어(진단+의향 → action 선택)\n"
            "- 타겟 범위 확장·입찰 전략 변경 등 처방 액션\n"
            "- 시간축 자동 에스컬레이션 사다리(remediation_escalations)\n"
            "- 처방 선택 정확도 eval\n\n"
            "근거 커밋: e37e781, e60fbc4, de0f860, bd65889, 9df15f4, 6bc5c06"
        ),
    },
    {
        "title": "[Management] 오가닉↔광고 비교·추천",
        "labels": ["agent-management"],
        "body": (
            "오가닉 게시물과 광고 성과를 비교해 추천 액션을 제시.\n\n"
            "- /compare·/compare/board 엔드포인트\n"
            "- ComparisonService.compare_and_recommend\n"
            "- 리프트 테이블 화면\n\n"
            "근거 커밋: 9377eb4, 168776a, 19f498f, 5f58cc2"
        ),
    },
    {
        "title": "[Management] Meta Marketing API 실연동 + 실시간 이상 감지",
        "labels": ["agent-management"],
        "body": (
            "Meta Marketing API 실연동과 실시간 캠페인 이상 감지.\n\n"
            "- 온보딩·권한 준비, KRW 예산 단위(offset=1) 검증\n"
            "- 실 캠페인 지표·감지 검증(meta_metrics_probe)\n"
            "- 실시간 이상 감지 관측 길이 정렬\n\n"
            "근거 커밋: b3dfbbc, affda78, 758d785, 7867f0d, c1b3d71"
        ),
    },
]


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("토큰을 찾을 수 없습니다. GITHUB_TOKEN 설정 또는 `gh auth login` 후 재시도하세요.")


def fetch_existing_titles(client: httpx.Client) -> set[str]:
    titles: set[str] = set()
    page = 1
    while True:
        resp = client.get(
            f"{API}/repos/{REPO}/issues",
            params={"state": "all", "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        # PR도 issues 엔드포인트에 섞여 나오므로 pull_request 키가 있으면 제외.
        titles.update(i["title"] for i in batch if "pull_request" not in i)
        page += 1
    return titles


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, timeout=30.0) as client:
        existing = fetch_existing_titles(client)

        created, skipped = 0, 0
        for issue in ISSUES:
            if issue["title"] in existing:
                print(f"[skip] 이미 존재: {issue['title']}")
                skipped += 1
                continue

            if dry_run:
                print(f"[dry-run] 생성 예정: {issue['title']}  labels={issue['labels']}")
                created += 1
                continue

            resp = client.post(
                f"{API}/repos/{REPO}/issues",
                json={
                    "title": issue["title"],
                    "body": issue["body"],
                    "labels": issue["labels"],
                },
            )
            if resp.status_code == 201:
                print(f"[ok] #{resp.json()['number']} {issue['title']}")
                created += 1
            else:
                print(f"[fail] {resp.status_code} {issue['title']} -> {resp.text}")

        verb = "생성 예정" if dry_run else "생성"
        print(f"\n완료: {created}건 {verb}, {skipped}건 건너뜀(중복).")


if __name__ == "__main__":
    main()
