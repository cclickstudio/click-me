# ClickMe CD용 EC2 인프라를 AWS CLI로 프로비저닝/철거하는 스크립트 (us-west-2)
"""
ClickMe 단일 EC2 배포 환경을 만든다.

빌드는 GitHub Actions가 하고 EC2는 ECR 이미지를 pull해서 실행만 하므로(EC2 부담 낮음),
비용 최소화에 초점을 둔다.

생성물:
  - 키페어(clickme-key)        → PEM을 ./clickme-key.pem 로 저장 (EC2_SSH_KEY 값)
  - 보안그룹(clickme-sg)        → 22(SSH/CD·scp), 80/443(웹)만 오픈. 8000/3000/9000은 안 엶
                                 (backend/frontend는 nginx 뒤 내부 전용, Portainer는 SSH 터널로만 접근)
  - Elastic IP(clickme-eip)    → 인스턴스에 연결하는 고정 공인 IP. 철거해도 반환하지 않아 재생성 시 같은 IP 유지
  - IAM Role/Instance Profile  → EC2가 ECR을 pull하도록 ReadOnly (EC2에 AWS 키 저장 불필요)
  - EC2 인스턴스(Ubuntu 24.04) → EBS 30GB gp3, user-data로 docker·compose·awscli·swap 자동 설치
  - 부팅 후 backend/.env 를 scp로 EC2에 자동 업로드 (~/clickme/backend/.env)

전제: aws CLI 설치 + 자격증명 설정 완료 (현재 us-west-2 / 계정 445459853661 확인됨).

키페어 생성 시 PEM은 SSM Parameter Store(SecureString)에 백업된다 → 팀원은 infra/fetch_key.py 로 공유받는다.

사용법:
  python infra/provision_ec2.py                          # 생성(+EIP 연결 +.env 업로드 +PEM을 SSM 백업)
  python infra/provision_ec2.py --destroy                # 철거(인스턴스·SG·키·IAM·ECR·SSM PEM). EIP는 보존 → 같은 IP 재사용
  python infra/provision_ec2.py --destroy --release-eip  # 위 + EIP까지 완전 반환(다음 생성 시 IP 바뀜)

비용 메모(us-west-2, 대략):
  - t3.micro : 프리티어 대상(12개월 750h 무료). 1GB라 swap 2GB로 보완. (아래 INSTANCE_TYPE 기본값)
  - t3.small : ~$15/월. 2GB로 여유. 피크 부족 시 승격.
  - EBS 30GB gp3 : 프리티어(30GB) 범위 → 첫 해 사실상 무료.
  - 공인 IPv4 : ~$3.6/월 (2024년부터 부과, 사용 중이면 회피 어려움).
  - Elastic IP : 인스턴스에 연결돼 있으면 공인 IPv4 요금에 포함(추가 부담 없음).
                 단 --destroy 후 '유휴 상태로 보존'하면 그 기간에도 ~$3.6/월 과금(같은 IP 유지 대가).
  - 안 쓸 땐 인스턴스 'stop' 하면 컴퓨팅 과금 0(EBS만). --destroy 로 전체 삭제 가능.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ─────────────────────────── 설정 (필요 시 수정) ───────────────────────────
REGION = "us-west-2"
INSTANCE_TYPE = "t3.micro"  # 프리티어(1GB, swap로 보완). 여유: "t3.small"(2GB) / "t3.medium"(4GB)
# ── 타입 승격(데이터 보존): PDF/AI 동시 피크에서 느리거나 OOM이면 t3.small로 올린다 ──
#   stop → 타입 변경 → start (EBS는 그대로 유지됨)
#     IID=<instance-id>
#     aws ec2 stop-instances           --region us-west-2 --instance-ids $IID
#     aws ec2 wait instance-stopped    --region us-west-2 --instance-ids $IID
#     aws ec2 modify-instance-attribute --region us-west-2 --instance-id $IID --instance-type t3.small
#     aws ec2 start-instances          --region us-west-2 --instance-ids $IID
#   (start 후 공인 IP가 바뀌므로 EC2_HOST / NEXT_PUBLIC_API_URL secret 갱신 필요.
#    고정하려면 Elastic IP 할당·연결. 단 EIP는 미사용 시 과금 주의.)
DISK_GB = 30  # gp3, 프리티어 30GB 범위
PROJECT = "clickme"

KEY_NAME = f"{PROJECT}-key"
SG_NAME = f"{PROJECT}-sg"
ROLE_NAME = f"{PROJECT}-ec2-ecr-role"
PROFILE_NAME = f"{PROJECT}-ec2-profile"
INSTANCE_NAME = f"{PROJECT}-prod"
EIP_NAME = f"{PROJECT}-eip"
ECR_BACKEND = f"{PROJECT}-backend"  # cd.yml의 ECR_BACKEND와 동일 (destroy 시 삭제 대상)
ECR_FRONTEND = f"{PROJECT}-frontend"
SSM_KEY_PARAM = f"/{PROJECT}/ec2/private-key"  # 팀 공유용 PEM(SecureString). fetch_key.py가 내려받음
PEM_PATH = Path(__file__).resolve().parent / f"{KEY_NAME}.pem"
# scp로 EC2에 올릴 로컬 backend/.env (리포 루트 = infra의 상위)
ENV_SRC = Path(__file__).resolve().parent.parent / "backend" / ".env"
# provision 결과(EC2_HOST 등)를 담아 로컬 도구(start_portainer.py)가 참조할 infra/.env
INFRA_ENV = Path(__file__).resolve().parent / ".env"

# Windows에서 subprocess로 aws CLI를 호출하면 출력이 파이프로 캡처돼도 페이저(more)가
# 뜨면서 입력 대기로 멈추는 경우가 있어, 자식 프로세스에서만 페이저를 끈다.
_AWS_ENV = {**os.environ, "AWS_PAGER": ""}

# 인스턴스 부팅 시 자동 셋업 (docker / compose plugin / awscli v2 / swap / 배포 디렉토리)
USER_DATA = r"""#!/bin/bash
set -eux
# --- swap 2GB (메모리 스파이크 대비: Chromium PDF 렌더/AI) ---
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# --- Docker ---
apt-get update
apt-get install -y ca-certificates curl gnupg unzip
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu
systemctl enable --now docker
# --- AWS CLI v2 (ECR 로그인용) ---
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
# --- 배포 디렉토리 (backend/.env 마운트 위치 포함) ---
mkdir -p /home/ubuntu/clickme/backend
chown -R ubuntu:ubuntu /home/ubuntu/clickme
echo "clickme bootstrap done" > /home/ubuntu/clickme/.bootstrap-ok
"""


# ─────────────────────────── 헬퍼 ───────────────────────────
def aws(*args: str, capture: bool = True) -> str:
    """aws CLI 호출. 실패 시 예외."""
    cmd = ["aws", "--region", REGION, *args]
    res = subprocess.run(cmd, capture_output=True, text=True, env=_AWS_ENV)
    if res.returncode != 0:
        raise RuntimeError(f"$ {' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout.strip() if capture else ""


def aws_ok(*args: str) -> tuple[bool, str]:
    """실패해도 예외 없이 (성공여부, 출력/에러) 반환."""
    res = subprocess.run(
        ["aws", "--region", REGION, *args], capture_output=True, text=True, env=_AWS_ENV
    )
    return res.returncode == 0, (res.stdout if res.returncode == 0 else res.stderr).strip()


def latest_ubuntu_ami() -> str:
    out = aws(
        "ec2",
        "describe-images",
        "--owners",
        "099720109477",  # Canonical
        "--filters",
        "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
        "Name=state,Values=available",
        "--query",
        "reverse(sort_by(Images,&CreationDate))[0].ImageId",
        "--output",
        "text",
    )
    return out


# ─────────────────────────── 생성 ───────────────────────────
def create_key_pair() -> None:
    ok, _ = aws_ok("ec2", "describe-key-pairs", "--key-names", KEY_NAME)
    if ok:
        print(f"[=] 키페어 {KEY_NAME} 이미 존재 — 건너뜀 (PEM이 없으면 infra/fetch_key.py로 SSM에서 복구)")
        return
    pem = aws(
        "ec2",
        "create-key-pair",
        "--key-name",
        KEY_NAME,
        "--query",
        "KeyMaterial",
        "--output",
        "text",
    )
    PEM_PATH.write_text(pem, encoding="utf-8")
    _lock_pem_permissions()
    print(f"[+] 키페어 생성 → {PEM_PATH}")
    _store_pem_to_ssm(pem)


def _store_pem_to_ssm(pem: str) -> None:
    """생성한 PEM을 SSM Parameter Store(SecureString)에 올려 팀원이 공유받게 한다.

    AWS는 private key를 생성 시 1회만 반환하므로, 여기서 곧바로 백업해둔다.
    팀원은 infra/fetch_key.py 로 내려받는다(파일을 직접 주고받을 필요 없음).
    권한: 이 스크립트 실행 IAM에 ssm:PutParameter + 기본 KMS(alias/aws/ssm) 암호화 필요.
    """
    ok, err = aws_ok(
        "ssm",
        "put-parameter",
        "--name",
        SSM_KEY_PARAM,
        "--type",
        "SecureString",
        "--value",
        pem,
        "--overwrite",
        "--description",
        "ClickMe EC2 private key (clickme-key.pem) - team shared",
    )
    if ok:
        print(f"[+] PEM을 SSM에 백업 → {SSM_KEY_PARAM} (팀원: python infra/fetch_key.py)")
    else:
        print(f"[!] SSM 백업 실패(ssm:PutParameter 권한 확인) — 팀 공유는 수동 필요:\n    {err}")


def _lock_pem_permissions() -> None:
    """PEM 권한 제한. ssh가 '권한 너무 열림'으로 키를 거부하지 않도록.

    Windows: NTFS DACL을 '현재 사용자 단독'으로 재설정한다.
      reset(명시적 ACE 정리) → setowner(소유권 회수, best-effort) →
      inheritance:r(상속 ACE 제거) → grant:r {user}:F(읽기+삭제 가능).
    reset 없이 inheritance:r만 하면 샌드박스/복사 잔재의 *명시적* ACE(UNKNOWN SID)가
    남아 ssh가 계속 'too open'으로 거부하고 파일 삭제도 막힌다. :R 대신 :F를 줘야
    본인이 키를 지우거나 교체할 수 있다(소유자 Full은 ssh의 'too open' 대상이 아님).
    """
    if os.name == "nt":
        path = str(PEM_PATH)
        user = os.environ.get("USERNAME") or ""
        if not user:
            try:
                user = os.getlogin()
            except OSError:
                user = ""
        subprocess.run(["icacls", path, "/reset"], capture_output=True)
        if user:
            subprocess.run(["icacls", path, "/setowner", user], capture_output=True)
        subprocess.run(["icacls", path, "/inheritance:r"], capture_output=True)
        if user:
            subprocess.run(["icacls", path, "/grant:r", f"{user}:F"], capture_output=True)
    else:
        try:
            PEM_PATH.chmod(0o400)
        except OSError:
            pass


def create_security_group() -> str:
    ok, out = aws_ok(
        "ec2",
        "describe-security-groups",
        "--filters",
        f"Name=group-name,Values={SG_NAME}",
        "--query",
        "SecurityGroups[0].GroupId",
        "--output",
        "text",
    )
    if ok and out and out != "None":
        print(f"[=] 보안그룹 {SG_NAME} 이미 존재 ({out})")
        return out
    sg_id = aws(
        "ec2",
        "create-security-group",
        "--group-name",
        SG_NAME,
        "--description",
        "ClickMe prod SG",
        "--query",
        "GroupId",
        "--output",
        "text",
    )
    # nginx 단일 진입점: 22(SSH/CD·scp)·80(웹)·443(HTTPS)만 연다.
    #   - 8000(backend)/3000(frontend)은 nginx 뒤 내부 전용이라 안 엶.
    #   - 9000(Portainer)은 EC2 127.0.0.1에만 바인딩 → SSH 터널(-L 9000)로만 접근하므로 안 엶.
    # 22는 CD 배포(Actions 러너 IP 동적)라 0.0.0.0/0 (key 인증만 허용).
    for port in (22, 80, 443):
        aws(
            "ec2",
            "authorize-security-group-ingress",
            "--group-id",
            sg_id,
            "--protocol",
            "tcp",
            "--port",
            str(port),
            "--cidr",
            "0.0.0.0/0",
            capture=False,
        )
    print(f"[+] 보안그룹 생성 {sg_id} (22/80/443 open · 8000/3000/9000 미개방)")
    return sg_id


def create_iam_role() -> bool:
    """EC2가 ECR을 pull하도록 ReadOnly Role+Profile. 권한 없으면 False 반환(계속 진행)."""
    trust = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )
    ok, err = aws_ok(
        "iam", "create-role", "--role-name", ROLE_NAME, "--assume-role-policy-document", trust
    )
    if not ok and "EntityAlreadyExists" not in err:
        print(
            f"[!] IAM Role 생성 실패(권한 부족 가능) — ECR pull은 EC2에서 수동 처리 필요:\n    {err}"
        )
        return False
    aws_ok(
        "iam",
        "attach-role-policy",
        "--role-name",
        ROLE_NAME,
        "--policy-arn",
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    )
    aws_ok("iam", "create-instance-profile", "--instance-profile-name", PROFILE_NAME)
    aws_ok(
        "iam",
        "add-role-to-instance-profile",
        "--instance-profile-name",
        PROFILE_NAME,
        "--role-name",
        ROLE_NAME,
    )
    print(f"[+] IAM Role/Profile 준비 ({ROLE_NAME})")
    return True


def run_instance(ami: str, sg_id: str, with_profile: bool) -> str:
    # 기존 동일 Name 태그 + 종료되지 않은 인스턴스 있으면 재사용
    ok, out = aws_ok(
        "ec2",
        "describe-instances",
        "--filters",
        f"Name=tag:Name,Values={INSTANCE_NAME}",
        "Name=instance-state-name,Values=pending,running,stopping,stopped",
        "--query",
        "Reservations[0].Instances[0].InstanceId",
        "--output",
        "text",
    )
    if ok and out and out != "None":
        print(f"[=] 인스턴스 {INSTANCE_NAME} 이미 존재 ({out})")
        return out

    ud_file = Path(__file__).resolve().parent / "_userdata.sh"
    # LF 고정(bash 스크립트) + fileb://로 전달 → Windows CRLF/디코딩 이슈 회피
    ud_file.write_bytes(USER_DATA.replace("\r\n", "\n").encode("utf-8"))
    bdm = (
        f"DeviceName=/dev/sda1,Ebs={{VolumeSize={DISK_GB},VolumeType=gp3,DeleteOnTermination=true}}"
    )
    args = [
        "ec2",
        "run-instances",
        "--image-id",
        ami,
        "--instance-type",
        INSTANCE_TYPE,
        "--key-name",
        KEY_NAME,
        "--security-group-ids",
        sg_id,
        "--block-device-mappings",
        bdm,
        "--user-data",
        f"fileb://{ud_file}",
        "--tag-specifications",
        f"ResourceType=instance,Tags=[{{Key=Name,Value={INSTANCE_NAME}}},{{Key=Project,Value={PROJECT}}}]",
        "--query",
        "Instances[0].InstanceId",
        "--output",
        "text",
    ]
    if with_profile:
        # instance-profile는 생성 직후 전파 지연 → 재시도
        args[2:2] = ["--iam-instance-profile", f"Name={PROFILE_NAME}"]
    for attempt in range(6):
        ok, out = aws_ok(*args)
        if ok:
            ud_file.unlink(missing_ok=True)
            print(f"[+] 인스턴스 시작 {out} ({INSTANCE_TYPE}, {DISK_GB}GB)")
            return out
        if "Invalid IAM Instance Profile" in out and attempt < 5:
            print(f"    IAM Profile 전파 대기... ({attempt + 1}/5)")
            time.sleep(10)
            continue
        ud_file.unlink(missing_ok=True)
        raise RuntimeError(out)
    raise RuntimeError("인스턴스 시작 실패")


def ensure_and_associate_eip(instance_id: str) -> str:
    """Elastic IP를 확보해 인스턴스에 연결하고 그 공인 IP를 반환한다.

    태그(Name=clickme-eip)로 기존 EIP를 먼저 찾는다 — --destroy가 EIP를 보존하므로
    철거→재생성해도 같은 IP가 유지된다. 없으면 새로 할당한다.
    """
    ok, out = aws_ok(
        "ec2",
        "describe-addresses",
        "--filters",
        f"Name=tag:Name,Values={EIP_NAME}",
        "--query",
        "Addresses[0].{alloc:AllocationId,ip:PublicIp}",
        "--output",
        "json",
    )
    alloc = ip = None
    if ok and out and out != "null":
        data = json.loads(out)
        alloc, ip = data.get("alloc"), data.get("ip")
    if not alloc:
        alloc = aws(
            "ec2",
            "allocate-address",
            "--domain",
            "vpc",
            "--tag-specifications",
            f"ResourceType=elastic-ip,Tags=[{{Key=Name,Value={EIP_NAME}}},{{Key=Project,Value={PROJECT}}}]",
            "--query",
            "AllocationId",
            "--output",
            "text",
        )
        ip = aws(
            "ec2",
            "describe-addresses",
            "--allocation-ids",
            alloc,
            "--query",
            "Addresses[0].PublicIp",
            "--output",
            "text",
        )
        print(f"[+] Elastic IP 할당 {ip} ({alloc})")
    else:
        print(f"[=] 기존 Elastic IP 재사용 {ip} ({alloc})")
    aws("ec2", "associate-address", "--instance-id", instance_id, "--allocation-id", alloc, capture=False)
    print(f"[+] EIP {ip} → 인스턴스 {instance_id} 연결")
    return ip


def upload_env_file(host: str) -> None:
    """부팅 후 SSH가 열리면 로컬 backend/.env 를 EC2로 scp 업로드한다.

    EIP는 철거/재생성 간 재사용되므로 매번 호스트키가 바뀐다 → known_hosts를 무시(os.devnull)해
    'REMOTE HOST IDENTIFICATION HAS CHANGED' 하드 실패와 대화형 프롬프트를 모두 회피한다.
    """
    if not ENV_SRC.exists():
        print(f"[!] backend/.env 없음 — scp 건너뜀 ({ENV_SRC}). 준비되면 수동 업로드하세요.")
        return
    remote = f"ubuntu@{host}"
    ssh_opts = [
        "-i",
        str(PEM_PATH),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"UserKnownHostsFile={os.devnull}",
        "-o",
        "ConnectTimeout=10",
    ]
    print("[*] SSH 준비 대기 후 backend/.env 업로드... (부팅+sshd 기동까지 최대 ~5분)")
    for attempt in range(30):
        res = subprocess.run(
            ["ssh", *ssh_opts, remote, "mkdir -p ~/clickme/backend"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            break
        time.sleep(10)
    else:
        print("[!] SSH 접속 실패 — 부팅/보안그룹 확인 후 아래를 수동 실행하세요:")
        print(f"    scp -i {PEM_PATH} {ENV_SRC} {remote}:/home/ubuntu/clickme/backend/.env")
        return
    dst = f"{remote}:/home/ubuntu/clickme/backend/.env"
    res = subprocess.run(["scp", *ssh_opts, str(ENV_SRC), dst], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"[+] backend/.env 업로드 완료 → {dst}")
    else:
        print(f"[!] scp 실패:\n{res.stderr.strip()}")


def write_infra_env(host: str, instance_id: str) -> None:
    """로컬 도구(start_portainer.py 등)가 참조할 infra/.env 를 쓴다. gitignore 대상.

    EC2_SSH_KEY 는 개인키 '내용'이 아니라 PEM '경로'로 저장한다
    (키는 clickme-key.pem에 이미 있고, PEM은 줄바꿈이 많아 .env 한 줄 값에 부적합).
    """
    INFRA_ENV.write_text(
        "# provision_ec2.py 자동 생성 — 로컬 도구(start_portainer.py) 참조용. 커밋 금지(.gitignore).\n"
        f"EC2_HOST={host}\n"
        "EC2_USER=ubuntu\n"
        f"EC2_INSTANCE_ID={instance_id}\n"
        f"EC2_REGION={REGION}\n"
        f"EC2_SSH_KEY_PATH={PEM_PATH}\n"
        "# ※ GitHub Secrets의 EC2_SSH_KEY 값은 위 PEM 파일의 *전체 내용*을 붙여넣으세요.\n",
        encoding="utf-8",
    )
    print(f"[+] infra/.env 기록 → {INFRA_ENV}")


def report(instance_id: str, host: str) -> None:
    print("\n" + "=" * 60)
    print("EC2 준비 완료. GitHub Secrets에 아래 값을 등록하세요.")
    print("=" * 60)
    print(f"EC2_HOST  = {host}   (고정 Elastic IP — 철거/재생성해도 유지)")
    print("EC2_USER  = ubuntu")
    print(f"EC2_SSH_KEY = {PEM_PATH} 파일의 *전체 내용* 붙여넣기")
    print("\n※ NEXT_PUBLIC_API_URL 은 더 이상 secret 아님(빈 값 빌드 → /api 상대경로, nginx same-origin).")
    print(f"\nSSH 접속: ssh -i {PEM_PATH} ubuntu@{host}")
    print("\n주의:")
    print(" - user-data 설치(docker/awscli)는 부팅 후 1~3분 더 걸립니다.")
    print("   확인: ssh 접속 후 'cat ~/clickme/.bootstrap-ok' / 'docker --version'")
    print(" - backend/.env 는 이 스크립트가 자동 업로드합니다(아래 로그 확인).")
    print(" - ECR 리포(clickme-backend/frontend)는 cd.yml이 자동 생성합니다.")
    print(f" - TLS: 도메인(clickme.co.kr·www) A레코드를 위 EIP({host})로 설정하세요.")
    print("   DNS 전파 후 첫 배포에서 cd.yml이 Let's Encrypt 인증서를 자동 발급합니다")
    print("   (deploy/init-letsencrypt.sh). 발급은 A레코드가 이 EIP를 가리켜야 성공합니다.")
    print(" - Portainer: 'python infra/start_portainer.py' → 자동 기동 + 터널 + localhost:9000 열림")
    print(
        " - 안 쓸 땐: aws ec2 stop-instances --region %s --instance-ids %s" % (REGION, instance_id)
    )


# ─────────────────────────── 철거 ───────────────────────────
def destroy(release_eip: bool = False) -> None:
    print(f"[*] {PROJECT} 리소스 철거 (region={REGION})")
    ok, ids = aws_ok(
        "ec2",
        "describe-instances",
        "--filters",
        f"Name=tag:Project,Values={PROJECT}",
        "Name=instance-state-name,Values=pending,running,stopping,stopped",
        "--query",
        "Reservations[].Instances[].InstanceId",
        "--output",
        "text",
    )
    inst = ids.split() if ok and ids and ids != "None" else []
    if inst:
        aws("ec2", "terminate-instances", "--instance-ids", *inst, capture=False)
        print(f"[-] 인스턴스 종료 {inst} (terminated 대기...)")
        aws("ec2", "wait", "instance-terminated", "--instance-ids", *inst, capture=False)
    # Elastic IP: 기본은 보존(같은 IP 재사용). --release-eip 일 때만 완전 반환.
    # (인스턴스 종료 시 연결은 자동 해제되고, EIP는 계정에 남는다.)
    ok, alloc = aws_ok(
        "ec2",
        "describe-addresses",
        "--filters",
        f"Name=tag:Name,Values={EIP_NAME}",
        "--query",
        "Addresses[0].AllocationId",
        "--output",
        "text",
    )
    alloc = alloc if ok and alloc and alloc != "None" else None
    if alloc:
        if release_eip:
            done, err = aws_ok("ec2", "release-address", "--allocation-id", alloc)
            print(f"[-] Elastic IP 반환 {alloc}" if done else f"[!] EIP 반환 실패: {err}")
        else:
            print(f"[=] Elastic IP 보존 {alloc} — 재생성 시 같은 IP 유지(완전 삭제는 --release-eip)")
            print("    주의: 인스턴스 없이 유휴 상태인 EIP는 시간당 과금(~$3.6/월).")
    # SG (인스턴스 종료 후)
    ok, sg = aws_ok(
        "ec2",
        "describe-security-groups",
        "--filters",
        f"Name=group-name,Values={SG_NAME}",
        "--query",
        "SecurityGroups[0].GroupId",
        "--output",
        "text",
    )
    if ok and sg and sg != "None":
        done, err = aws_ok("ec2", "delete-security-group", "--group-id", sg)
        print(f"[-] 보안그룹 삭제 {sg}" if done else f"[!] SG 삭제 보류: {err}")
    # 키페어 + 로컬 PEM
    aws_ok("ec2", "delete-key-pair", "--key-name", KEY_NAME)
    PEM_PATH.unlink(missing_ok=True)
    print("[-] 키페어/PEM 삭제")
    # SSM에 백업한 공유 PEM 삭제
    done, err = aws_ok("ssm", "delete-parameter", "--name", SSM_KEY_PARAM)
    if done:
        print(f"[-] SSM 공유 PEM 삭제 {SSM_KEY_PARAM}")
    elif "ParameterNotFound" not in err:
        print(f"[!] SSM 삭제 보류: {err}")
    # 로컬 infra/.env (provision이 만든 참조 파일)
    if INFRA_ENV.exists():
        INFRA_ENV.unlink()
        print("[-] infra/.env 삭제")
    # IAM
    aws_ok(
        "iam",
        "remove-role-from-instance-profile",
        "--instance-profile-name",
        PROFILE_NAME,
        "--role-name",
        ROLE_NAME,
    )
    aws_ok("iam", "delete-instance-profile", "--instance-profile-name", PROFILE_NAME)
    aws_ok(
        "iam",
        "detach-role-policy",
        "--role-name",
        ROLE_NAME,
        "--policy-arn",
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    )
    aws_ok("iam", "delete-role", "--role-name", ROLE_NAME)
    print("[-] IAM Role/Profile 삭제")
    # ECR 리포(이미지 포함) 삭제 — 다음 배포에서 cd.yml이 자동 재생성한다.
    for repo in (ECR_BACKEND, ECR_FRONTEND):
        done, err = aws_ok("ecr", "delete-repository", "--repository-name", repo, "--force")
        if done:
            print(f"[-] ECR 리포 삭제 {repo} (이미지 포함)")
        elif "RepositoryNotFoundException" not in err:
            print(f"[!] ECR 삭제 보류 {repo}: {err}")
    print("[*] 철거 완료. (다음 배포 시 ECR 리포는 cd.yml이 자동 재생성)")


# ─────────────────────────── main ───────────────────────────
def main() -> None:
    if "--destroy" in sys.argv:
        destroy(release_eip="--release-eip" in sys.argv)
        return
    print(f"[*] ClickMe EC2 프로비저닝 (region={REGION}, type={INSTANCE_TYPE})")
    ami = latest_ubuntu_ami()
    print(f"[*] Ubuntu 24.04 AMI = {ami}")
    create_key_pair()
    sg_id = create_security_group()
    with_profile = create_iam_role()
    iid = run_instance(ami, sg_id, with_profile)
    print("[*] running 대기...")
    aws("ec2", "wait", "instance-running", "--instance-ids", iid, capture=False)
    host = ensure_and_associate_eip(iid)
    write_infra_env(host, iid)
    report(iid, host)
    upload_env_file(host)


if __name__ == "__main__":
    main()
