# SSM에 백업된 EC2 private key(PEM)를 내려받아 로컬 infra/clickme-key.pem 을 재구성하는 스크립트
"""
팀 공유용 — provision_ec2.py 를 실행한 사람만 clickme-key.pem 을 갖게 되는 문제를 없앤다.

provision_ec2.py 는 키페어 생성 시 PEM을 SSM Parameter Store(SecureString)에 백업해둔다.
팀원은 이 스크립트 하나만 실행하면:
  1) SSM에서 PEM을 받아 infra/clickme-key.pem 으로 저장(+권한 잠금)
  2) 현재 인스턴스의 EIP·instance-id를 조회해 infra/.env 재구성
그 뒤 start_portainer.py / ssh 를 바로 쓸 수 있다.

전제: 로컬에 aws CLI + (팀 계정) 자격증명. 필요한 권한:
  ssm:GetParameter(+기본 KMS decrypt), ec2:DescribeAddresses, ec2:DescribeInstances

사용법:
  python infra/fetch_key.py
"""

from __future__ import annotations

import sys

# 같은 infra/ 디렉토리의 provision_ec2 에서 상수·헬퍼를 재사용한다(직접 실행 시 sys.path[0]=infra).
from provision_ec2 import (
    EIP_NAME,
    INSTANCE_NAME,
    PEM_PATH,
    SSM_KEY_PARAM,
    _lock_pem_permissions,
    aws_ok,
    write_infra_env,
)


def fetch_pem() -> str | None:
    ok, out = aws_ok(
        "ssm",
        "get-parameter",
        "--name",
        SSM_KEY_PARAM,
        "--with-decryption",
        "--query",
        "Parameter.Value",
        "--output",
        "text",
    )
    if not ok:
        print(f"[!] SSM에서 PEM을 못 받음 ({SSM_KEY_PARAM}).")
        print("    - provision_ec2.py 가 아직 안 돌았거나, ssm:GetParameter/KMS decrypt 권한이 없을 수 있음.")
        print(f"    상세: {out}")
        return None
    return out


def current_host_and_iid() -> tuple[str | None, str | None]:
    """태그로 현재 EIP(공인 IP)와 instance-id를 조회한다. 없으면 (None, None)."""
    ok, ip = aws_ok(
        "ec2",
        "describe-addresses",
        "--filters",
        f"Name=tag:Name,Values={EIP_NAME}",
        "--query",
        "Addresses[0].PublicIp",
        "--output",
        "text",
    )
    host = ip if ok and ip and ip != "None" else None
    ok2, iid = aws_ok(
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
    instance_id = iid if ok2 and iid and iid != "None" else None
    return host, instance_id


def main() -> None:
    pem = fetch_pem()
    if not pem:
        sys.exit(1)
    PEM_PATH.write_text(pem, encoding="utf-8")
    _lock_pem_permissions()
    print(f"[+] PEM 복구 → {PEM_PATH}")

    host, iid = current_host_and_iid()
    if host and iid:
        write_infra_env(host, iid)  # 자체적으로 "infra/.env 기록" 로그 출력
    else:
        print("[!] 실행 중인 인스턴스를 못 찾음 — infra/.env 는 건너뜀(인스턴스 없거나 권한 부족).")

    print("\n이제 다음을 바로 쓸 수 있습니다:")
    print(f"  ssh -i {PEM_PATH} ubuntu@{host or '<EC2_HOST>'}")
    print("  python infra/start_portainer.py")


if __name__ == "__main__":
    main()
