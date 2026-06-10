# -*- coding: utf-8 -*-
"""
ClickMe GitHub Issues 생성 템플릿

실행 방법:
    python docs/create_issues_template.py

사전 준비:
    gh auth login
"""

import subprocess
import json
import time
import sys

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "cclickstudio/click-me"
ORG = "cclickstudio"
PROJECT_NUMBER = 1


def gh(*args, input_text=None):
    result = subprocess.run(
        [GH] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=input_text,
    )
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr.strip()}", file=sys.stderr)
    return result.stdout.strip()


def get_project_id():
    print("Project ID 조회 중...")
    query = """
    {
      organization(login: "%s") {
        projectV2(number: %d) {
          id
          title
        }
      }
    }
    """ % (ORG, PROJECT_NUMBER)
    result = gh("api", "graphql", "-f", f"query={query}")
    data = json.loads(result)
    pid = data["data"]["organization"]["projectV2"]["id"]
    title = data["data"]["organization"]["projectV2"]["title"]
    print(f"  -> Project: '{title}' (ID: {pid})")
    return pid


def create_issue(title, body, labels=None):
    print(f"\n이슈 생성: {title}")
    args = ["issue", "create", "--repo", REPO, "--title", title, "--body", body]
    if labels:
        for label in labels:
            args += ["--label", label]
    url = gh(*args)
    print(f"  -> {url}")
    return url


def get_issue_node_id(issue_number):
    query = """
    {
      repository(owner: "%s", name: "click-me") {
        issue(number: %s) {
          id
        }
      }
    }
    """ % (ORG, issue_number)
    result = gh("api", "graphql", "-f", f"query={query}")
    data = json.loads(result)
    return data["data"]["repository"]["issue"]["id"]


def add_to_project(project_id, issue_node_id):
    mutation = """
    mutation {
      addProjectV2ItemById(input: {
        projectId: "%s"
        contentId: "%s"
      }) {
        item { id }
      }
    }
    """ % (project_id, issue_node_id)
    gh("api", "graphql", "-f", f"query={mutation}")
    print("  -> Project 추가 완료")


def new_issue(project_id, title, body, labels=None):
    url = create_issue(title, body, labels)
    if url:
        issue_number = url.split("/")[-1]
        node_id = get_issue_node_id(issue_number)
        add_to_project(project_id, node_id)
    time.sleep(0.5)


# ──────────────────────────────────────────────────────────────
# 이슈 정의
# ──────────────────────────────────────────────────────────────
#
# 사용 가능한 라벨:
#   setup / backend / frontend / agent-simulation / test / devops / database
#
# 이슈 본문에서 참고 가능한 파일 (존재하는 것만 사용):
#   docs/api-spec.md
#   docs/db-schema.md
#   CLAUDE.md
#
# new_issue 호출 형식:
#
#   new_issue(project_id,
#       "[카테고리] 이슈 제목",
#       """\
#   ## 개요
#   ...
#
#   ## 참고
#   - docs/api-spec.md §...
#   """,
#       ["라벨"])
# ──────────────────────────────────────────────────────────────

def run():
    project_id = get_project_id()

    new_issue(project_id,
        "",
        """\
## 개요


## 참고
-
""",
        [""])

    print("\n" + "="*50)
    print("완료! 모든 이슈가 생성되어 Project에 추가됐습니다.")
    print("="*50)


if __name__ == "__main__":
    run()
