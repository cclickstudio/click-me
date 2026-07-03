# EC2 인스턴스 타입을 stop→변경→start로 전환하는 스크립트 (EBS·EIP 유지)
"""
clickme-prod 인스턴스의 타입을 파라미터로 전환한다.

EBS(디스크 데이터)와 Elastic IP는 그대로 유지되므로 EC2_HOST(공인 IP)는 바뀌지 않는다
— GitHub Secrets 갱신 불필요. PDF/AI 동시 피크에서 느리거나 OOM이면 위 등급으로 올리고,
한가하면 내려 비용을 아낀다.

타입 매핑:
  --micro   t3.micro   (1GB, 프리티어 대상)
  --small   t3.small   (2GB, ~$15/월)
  --medium  t3.medium  (4GB)

사용법:
  python infra/resize_instance.py --small

전제: aws CLI + 자격증명(provision_ec2.py와 동일). 인스턴스가 이미 생성돼 있어야 한다.
"""

from __future__ import annotations

import sys

# provision_ec2 에서 리전·태그·헬퍼를 재사용한다(같은 infra/ 디렉토리 → 직접 실행 시 import 가능).
from provision_ec2 import INSTANCE_NAME, aws, aws_ok

TYPES = {"micro": "t3.micro", "small": "t3.small", "medium": "t3.medium"}


def find_instance_id() -> str | None:
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
    return out if ok and out and out != "None" else None


def current_type(iid: str) -> str:
    ok, out = aws_ok(
        "ec2",
        "describe-instances",
        "--instance-ids",
        iid,
        "--query",
        "Reservations[0].Instances[0].InstanceType",
        "--output",
        "text",
    )
    return out if ok and out else "?"


def usage() -> None:
    print("사용법: python infra/resize_instance.py --micro | --small | --medium")
    for k, v in TYPES.items():
        print(f"    --{k:<7} → {v}")


def main() -> None:
    chosen = [k for k in TYPES if f"--{k}" in sys.argv]
    if len(chosen) != 1:
        usage()
        sys.exit(1)
    target = TYPES[chosen[0]]

    iid = find_instance_id()
    if not iid:
        sys.exit(f"[!] 실행 중/중지된 {INSTANCE_NAME} 인스턴스를 찾지 못했습니다.")

    cur = current_type(iid)
    print(f"[*] {INSTANCE_NAME} ({iid}) 현재 타입: {cur} → 목표: {target}")
    if cur == target:
        print("[=] 이미 목표 타입입니다 — 변경 없음.")
        return

    print("[*] stop 중... (인스턴스 중지 대기)")
    aws("ec2", "stop-instances", "--instance-ids", iid, capture=False)
    aws("ec2", "wait", "instance-stopped", "--instance-ids", iid, capture=False)

    print(f"[*] 타입 변경 → {target}")
    aws(
        "ec2",
        "modify-instance-attribute",
        "--instance-id",
        iid,
        "--instance-type",
        target,
        capture=False,
    )

    print("[*] start 중... (running 대기)")
    aws("ec2", "start-instances", "--instance-ids", iid, capture=False)
    aws("ec2", "wait", "instance-running", "--instance-ids", iid, capture=False)

    print(f"[+] 완료 — {target}. Elastic IP·EBS 유지되어 EC2_HOST는 그대로입니다.")


if __name__ == "__main__":
    main()
