# ClickMe CD용 EC2 인프라를 AWS CLI로 프로비저닝/철거하는 스크립트 (us-west-2)
"""
ClickMe 단일 EC2 배포 환경을 만든다.

빌드는 GitHub Actions가 하고 EC2는 ECR 이미지를 pull해서 실행만 하므로(EC2 부담 낮음),
비용 최소화에 초점을 둔다.

생성물:
  - 키페어(clickme-key)        → PEM을 ./clickme-key.pem 로 저장 (EC2_SSH_KEY 값)
  - 보안그룹(clickme-sg)        → 22(SSH, CD 배포), 80/443(웹), 8000/3000(직접 접근/테스트)
  - IAM Role/Instance Profile  → EC2가 ECR을 pull하도록 ReadOnly (EC2에 AWS 키 저장 불필요)
  - EC2 인스턴스(Ubuntu 24.04) → EBS 30GB gp3, user-data로 docker·compose·awscli·swap 자동 설치

전제: aws CLI 설치 + 자격증명 설정 완료 (현재 us-west-2 / 계정 445459853661 확인됨).

사용법:
  python infra/provision_ec2.py            # 생성
  python infra/provision_ec2.py --destroy  # 철거(과금 중단)

비용 메모(us-west-2, 대략):
  - t3.micro : 프리티어 대상(12개월 750h 무료). 1GB라 swap 2GB로 보완. (아래 INSTANCE_TYPE 기본값)
  - t3.small : ~$15/월. 2GB로 여유. 피크 부족 시 승격.
  - EBS 30GB gp3 : 프리티어(30GB) 범위 → 첫 해 사실상 무료.
  - 공인 IPv4 : ~$3.6/월 (2024년부터 부과, 사용 중이면 회피 어려움).
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
PEM_PATH = Path(__file__).resolve().parent / f"{KEY_NAME}.pem"

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
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"$ {' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout.strip() if capture else ""


def aws_ok(*args: str) -> tuple[bool, str]:
    """실패해도 예외 없이 (성공여부, 출력/에러) 반환."""
    res = subprocess.run(["aws", "--region", REGION, *args], capture_output=True, text=True)
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
        print(f"[=] 키페어 {KEY_NAME} 이미 존재 — 건너뜀 (PEM이 없으면 삭제 후 재생성 필요)")
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


def _lock_pem_permissions() -> None:
    """PEM 권한 제한. ssh가 '권한 너무 열림'으로 키를 거부하지 않도록."""
    if os.name == "nt":
        # Windows: NTFS ACL — 상속 제거 후 현재 사용자만 읽기 (chmod로는 안 됨)
        user = os.environ.get("USERNAME", "")
        subprocess.run(["icacls", str(PEM_PATH), "/inheritance:r"], capture_output=True)
        if user:
            subprocess.run(
                ["icacls", str(PEM_PATH), "/grant:r", f"{user}:R"], capture_output=True
            )
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
    # nginx 단일 진입점: 22(SSH/CD)·80(웹)·443(추후 HTTPS)만. 8000/3000은 내부 전용이라 안 엶.
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
    print(f"[+] 보안그룹 생성 {sg_id} (22/80/443/8000/3000 open)")
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
        print(f"[!] IAM Role 생성 실패(권한 부족 가능) — ECR pull은 EC2에서 수동 처리 필요:\n    {err}")
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


def wait_and_report(instance_id: str) -> None:
    print("[*] running 대기...")
    aws("ec2", "wait", "instance-running", "--instance-ids", instance_id, capture=False)
    info = json.loads(
        aws(
            "ec2",
            "describe-instances",
            "--instance-ids",
            instance_id,
            "--query",
            "Reservations[0].Instances[0].{ip:PublicIpAddress,dns:PublicDnsName}",
            "--output",
            "json",
        )
    )
    ip, dns = info.get("ip"), info.get("dns")
    print("\n" + "=" * 60)
    print("EC2 준비 완료. GitHub Secrets에 아래 값을 등록하세요.")
    print("=" * 60)
    print(f"EC2_HOST  = {ip}   (또는 도메인 연결 시 그 도메인)")
    print("EC2_USER  = ubuntu")
    print(f"EC2_SSH_KEY = {PEM_PATH} 파일의 *전체 내용* 붙여넣기")
    print(f"\nNEXT_PUBLIC_API_URL = http://{ip}:8000   (도메인+HTTPS 연결 시 https://api.도메인)")
    print(f"\nSSH 접속: ssh -i {PEM_PATH} ubuntu@{ip}")
    print(f"DNS: {dns}")
    print("\n주의:")
    print(" - user-data 설치(docker/awscli)는 부팅 후 1~3분 더 걸립니다.")
    print("   확인: ssh 접속 후 'cat ~/clickme/.bootstrap-ok' / 'docker --version'")
    print(" - ECR 리포(clickme-backend/frontend)는 cd.yml이 자동 생성합니다.")
    print(" - EC2 ~/clickme/docker-compose.prod.yml 은 아직 없습니다(다음 단계).")
    print(" - 안 쓸 땐: aws ec2 stop-instances --region %s --instance-ids %s" % (REGION, instance_id))


# ─────────────────────────── 철거 ───────────────────────────
def destroy() -> None:
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
    print("[*] 철거 완료. (ECR 리포는 cd.yml이 만든 것이므로 별도 삭제 필요 시 수동)")


# ─────────────────────────── main ───────────────────────────
def main() -> None:
    if "--destroy" in sys.argv:
        destroy()
        return
    print(f"[*] ClickMe EC2 프로비저닝 (region={REGION}, type={INSTANCE_TYPE})")
    ami = latest_ubuntu_ami()
    print(f"[*] Ubuntu 24.04 AMI = {ami}")
    create_key_pair()
    sg_id = create_security_group()
    with_profile = create_iam_role()
    iid = run_instance(ami, sg_id, with_profile)
    wait_and_report(iid)


if __name__ == "__main__":
    main()
