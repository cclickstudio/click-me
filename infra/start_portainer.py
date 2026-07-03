# infra/.env를 읽어 EC2에 Portainer를 띄우고 SSH 터널로 localhost:9000에 연결하는 스크립트
"""
provision_ec2.py가 만든 infra/.env(EC2_HOST·PEM 경로)를 읽어:
  1) EC2에 Portainer 컨테이너가 없으면 127.0.0.1:9000에 바인딩해 띄우고(외부 미노출),
  2) 로컬 9000 → EC2 9000 SSH 터널을 열고,
  3) 첫 실행이면 관리자 계정(admin)을 자동 생성한 뒤 브라우저로 http://localhost:9000 을 연다.

SG에 9000을 열지 않으므로(보안) 이 터널을 통해서만 접근된다.
터널 창은 켜 둔다(Ctrl+C 로 종료).

사용법:
  python infra/start_portainer.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

INFRA_ENV = Path(__file__).resolve().parent / ".env"
LOCAL_PORT = 9000
REMOTE_PORT = 9000

# 첫 실행 시 자동 생성할 Portainer 관리자 계정 (터널 전용이라 평문 보관 — 실운영 전 교체 권장).
# 비밀번호는 Portainer 정책상 12자 이상이어야 한다.
ADMIN_USER = "admin"
ADMIN_PASSWORD = "adminportainer1234"

# EC2에서 Portainer가 없으면 127.0.0.1:9000에 바인딩해 띄운다(멱등).
# ubuntu는 docker 그룹 소속(user-data) + SSH는 새 로그인 세션이라 sudo 없이 docker 사용 가능.
REMOTE_ENSURE = (
    "set -e; "
    'if [ -z "$(docker ps -q -f name=portainer)" ]; then '
    "docker volume create portainer_data >/dev/null; "
    "docker rm -f portainer >/dev/null 2>&1 || true; "
    "docker run -d --name portainer --restart=always "
    "-p 127.0.0.1:9000:9000 "
    "-v /var/run/docker.sock:/var/run/docker.sock "
    "-v portainer_data:/data portainer/portainer-ce:latest >/dev/null; "
    "echo started; "
    "else echo already; fi"
)


def load_env() -> dict[str, str]:
    if not INFRA_ENV.exists():
        sys.exit(f"[!] {INFRA_ENV} 없음. 먼저 'python infra/provision_ec2.py'로 인스턴스를 생성하세요.")
    env: dict[str, str] = {}
    for raw in INFRA_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def ssh_opts(key_path: str) -> list[str]:
    # EIP 재사용으로 호스트키가 바뀔 수 있어 known_hosts 무시(하드 실패·프롬프트 회피)
    return [
        "-i",
        key_path,
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"UserKnownHostsFile={os.devnull}",
        "-o",
        "ConnectTimeout=10",
    ]


def init_admin() -> None:
    """첫 실행이면 Portainer 관리자 계정을 자동 생성한다(터널이 열린 뒤 호출).

    POST /api/users/admin/init 은 admin이 아직 없을 때만 동작한다.
    이미 있으면 409 → 초기화 생략. HTTP가 아직 안 열렸으면(URLError) 잠깐 대기 후 재시도.
    """
    url = f"http://localhost:{LOCAL_PORT}/api/users/admin/init"
    body = json.dumps({"Username": ADMIN_USER, "Password": ADMIN_PASSWORD}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    for _ in range(20):  # Portainer HTTP 기동까지 최대 ~20초 대기
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print(f"[+] Portainer 관리자 계정 생성 완료 → {ADMIN_USER} / {ADMIN_PASSWORD}")
                    return
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace").strip()
            if e.code == 409 or "already exists" in msg.lower():
                print(f"[=] 관리자 계정이 이미 있습니다 → 로그인: {ADMIN_USER} (초기화 생략)")
            elif "timeout" in msg.lower():
                print("[!] Portainer 초기화 보안 타임아웃 — 컨테이너 재시작 후 재실행 필요:")
                print("    docker restart portainer  (그 뒤 python infra/start_portainer.py)")
            else:
                print(f"[!] 관리자 초기화 실패({e.code}): {msg}")
            return
        except urllib.error.URLError:
            time.sleep(1)  # 아직 HTTP 미기동 — 대기 후 재시도
    print("[!] Portainer HTTP 응답 없음 — 자동 초기화 건너뜀. 브라우저에서 수동 설정하세요.")


def main() -> None:
    env = load_env()
    host = env.get("EC2_HOST")
    user = env.get("EC2_USER", "ubuntu")
    key = env.get("EC2_SSH_KEY_PATH")
    if not host or not key:
        sys.exit(f"[!] infra/.env에 EC2_HOST/EC2_SSH_KEY_PATH가 없습니다: {env}")
    if not Path(key).exists():
        sys.exit(f"[!] PEM 키 없음: {key}")
    remote = f"{user}@{host}"
    opts = ssh_opts(key)

    print(f"[*] EC2({host})에 Portainer 확인/기동...")
    res = subprocess.run(["ssh", *opts, remote, REMOTE_ENSURE], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"[!] Portainer 기동 실패:\n{res.stderr.strip()}")
    state = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
    print("[+] Portainer 이미 실행 중" if state == "already" else "[+] Portainer 컨테이너 시작")

    url = f"http://localhost:{LOCAL_PORT}"
    print(f"[*] SSH 터널 열기: localhost:{LOCAL_PORT} → {host}:{REMOTE_PORT}")
    tunnel = subprocess.Popen(
        ["ssh", *opts, "-N", "-L", f"{LOCAL_PORT}:localhost:{REMOTE_PORT}", remote]
    )
    try:
        time.sleep(2)
        if tunnel.poll() is not None:
            sys.exit("[!] 터널이 바로 종료됐습니다. SSH 접속/키/보안그룹(22)을 확인하세요.")
        print(f"[+] 터널 연결됨 → {url}")
        init_admin()  # 첫 실행이면 admin 계정 자동 생성
        webbrowser.open(url)
        print("    이 창을 열어 두세요 (Ctrl+C 로 터널 종료).")
        tunnel.wait()
    except KeyboardInterrupt:
        print("\n[*] 터널 종료")
    finally:
        if tunnel.poll() is None:
            tunnel.terminate()


if __name__ == "__main__":
    main()
