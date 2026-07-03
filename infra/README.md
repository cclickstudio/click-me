# infra — EC2 배포 인프라

ClickMe 운영 배포(단일 EC2 + nginx)를 위한 인프라 스크립트 모음.

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `provision_ec2.py` | AWS CLI로 운영 EC2 한 대 + 부속 리소스(EIP 포함)를 생성/철거 |
| `start_portainer.py` | `infra/.env` 참조 → EC2에 Portainer 기동 + SSH 터널로 `localhost:9000` 열기 |
| `clickme-key.pem` | 스크립트가 만든 SSH 키 (gitignore, **커밋 금지**) |
| `.env` | provision이 자동 생성한 참조값(EC2_HOST 등). gitignore, `--destroy` 시 삭제 |

> 리버스 프록시 설정은 `../deploy/nginx.conf`, 컨테이너 구성은 `../docker-compose.prod.yml`,
> 배포 파이프라인은 `../.github/workflows/cd.yml` 참고.

## provision_ec2.py 가 하는 일

빌드는 GitHub Actions가 하고 EC2는 ECR 이미지를 **pull해서 실행만** 하므로(부담 낮음), 비용 최소화에 맞춰져 있다.
한 번 실행하면 `us-west-2`에 아래를 **멱등적으로**(이미 있으면 재사용) 만든다.

1. **키페어** `clickme-key` → `infra/clickme-key.pem` 저장 (Windows는 ACL까지 잠금)
2. **보안그룹** `clickme-sg` → 22(SSH/CD·scp)·80(nginx)·443(HTTPS)만 오픈
   - 8000(backend)/3000(frontend)은 nginx 뒤 내부 전용, 9000(Portainer)은 SSH 터널 전용 → **모두 미개방**
3. **IAM Role/Instance Profile** → EC2가 ECR을 pull하도록 ReadOnly (EC2에 AWS 키 저장 불필요)
4. **EC2 인스턴스** `clickme-prod` → Ubuntu 24.04, EBS 30GB gp3, t3.micro(기본)
5. **Elastic IP** `clickme-eip` → 인스턴스에 연결하는 고정 공인 IP. `--destroy` 해도 보존해 재생성 시 같은 IP 유지
6. user-data로 부팅 시 **docker·docker compose·awscli·swap(2GB)** 자동 설치 + `~/clickme/backend` 생성
7. 부팅 후 로컬 **`backend/.env` 를 EC2로 scp 자동 업로드**, 참조값을 **`infra/.env` 로 기록**(start_portainer.py용)

## 사용법

전제: 로컬에 `aws` CLI 설치 + 자격증명 설정(`aws sts get-caller-identity` 확인).

```bash
# 생성 (+EIP 연결 +backend/.env 업로드 +infra/.env 기록)
python infra/provision_ec2.py

# 철거(과금 중단 — 인스턴스·SG·키페어·IAM·infra/.env 삭제). EIP는 보존 → 재생성 시 같은 IP
python infra/provision_ec2.py --destroy

# EIP까지 완전 반환(다음 생성 시 IP 바뀜). 유휴 EIP 과금을 끊고 싶을 때만
python infra/provision_ec2.py --destroy --release-eip
```

상단 설정 상수(`REGION`, `INSTANCE_TYPE`, `DISK_GB` 등)만 바꿔 조정한다.

> **EIP 보존 vs 반환** — 기본 `--destroy`는 Elastic IP를 계정에 남겨 다음 생성 때 **같은 IP로 재연결**한다
> (`EC2_HOST` secret을 다시 안 바꿔도 됨). 대신 인스턴스 없이 유휴 상태인 EIP는 **~$3.6/월 과금**된다.
> 오래 안 쓸 거면 `--release-eip`로 반환한다(대신 다음엔 IP가 바뀜).

## 생성 후 1회 수동 작업

스크립트가 출력하는 값으로 GitHub Secrets를 등록한다. 같은 값이 `infra/.env`에도 기록되니 거기서 복사해도 된다.

- `EC2_HOST` = 출력된 **Elastic IP** (고정 — 철거/재생성해도 유지, EIP 반환 전까진 안 바뀜)
- `EC2_USER` = `ubuntu`
- `EC2_SSH_KEY` = `infra/clickme-key.pem` **전체 내용** (`infra/.env`엔 `EC2_SSH_KEY_PATH`로 경로만 기록됨)

> `NEXT_PUBLIC_API_URL`은 더 이상 secret이 아니다 — cd.yml이 빈 값으로 빌드해 프론트가 `/api` 상대경로로
> 호출하고, nginx 단일 진입점이라 same-origin이 된다.

백엔드 운영 환경변수 파일(`backend/.env`, 리포에 없음·gitignore)은 **provision_ec2.py가 부팅 후
자동으로 scp 업로드**한다(`~/clickme/backend/.env`). 실행 로그에서 `backend/.env 업로드 완료`를 확인.
SSH가 늦게 열려 실패하면 로그가 아래 수동 명령을 출력한다.

```bash
scp -i infra/clickme-key.pem backend/.env ubuntu@<EC2_HOST>:/home/ubuntu/clickme/backend/.env
```

`backend/.env`에는 최소 `APP_ENV=production`, `DATABASE_URL`(NeonDB), `OPENAI_API_KEY` 가 채워져 있어야 한다.

## Portainer 접근 (start_portainer.py)

컨테이너 상태·로그를 GUI로 보려면 Portainer를 쓴다. Portainer는 EC2에서 `127.0.0.1:9000`에만
바인딩돼 외부로 열려 있지 않으므로(SG에 9000 미개방), SSH 포트 포워딩으로만 접근한다. 이 과정을
`start_portainer.py`가 자동화한다 — **EC2에 Portainer 컨테이너 기동(없으면 생성) → 터널 → 브라우저 오픈**.

```bash
python infra/start_portainer.py
```

- `infra/.env`(provision이 자동 생성)에서 `EC2_HOST`·`EC2_SSH_KEY_PATH`를 읽는다.
- 실행하면 `localhost:9000` 터널이 열리고 브라우저로 **http://localhost:9000** 이 자동 오픈된다.
  터널 창은 켜 둔 채로 쓰고 **Ctrl+C** 로 종료한다.
- **첫 실행이면 관리자 계정이 자동 생성**된다 → `admin` / `adminportainer1234`
  (`start_portainer.py`의 `ADMIN_USER`·`ADMIN_PASSWORD` 상수로 교체 가능. 터널 전용이라 평문 보관, 실운영 전 변경 권장).
- `Bad permissions / UNPROTECTED PRIVATE KEY` 오류가 나면 키 ACL이 풀린 것 →
  `provision_ec2.py`를 다시 실행하거나, 아래 한 줄로 현재 사용자 단독 권한으로 재설정한다.
  ```powershell
  icacls "infra\clickme-key.pem" /reset; icacls "infra\clickme-key.pem" /inheritance:r; icacls "infra\clickme-key.pem" /grant:r "${env:USERNAME}:F"
  ```

## 배포 흐름과의 관계

```
개발자 push → CD(cd.yml): backend/frontend 이미지 빌드 → ECR push
           → compose·nginx.conf EC2로 복사 → EC2가 ECR pull → docker compose up
EC2 런타임: nginx(:80) ─ /api → backend(내부) · /docs 차단 · 그 외 → frontend(내부)
```

- compose·nginx.conf는 매 배포마다 cd.yml이 자동 복사한다.
- `backend/.env`(비밀이라 리포·이미지에 없음)는 **provision_ec2.py가 최초 생성 시 scp로 자동 배치**한다.
  내용이 바뀌면 위 수동 scp 한 줄로 갱신한다.

## 인스턴스 타입 승격(비용↔성능)

t3.micro로 메모리가 부족하면(PDF/AI 동시 피크) 데이터 보존한 채 올린다.

```bash
IID=<instance-id>
aws ec2 stop-instances            --region us-west-2 --instance-ids $IID
aws ec2 wait instance-stopped     --region us-west-2 --instance-ids $IID
aws ec2 modify-instance-attribute --region us-west-2 --instance-id $IID --instance-type t3.small
aws ec2 start-instances           --region us-west-2 --instance-ids $IID
```

> Elastic IP가 인스턴스에 연결돼 있으면 stop→start 후에도 **같은 EIP가 유지**되므로
> `EC2_HOST`를 다시 바꿀 필요가 없다. (EIP 연결은 provision_ec2.py가 자동 처리.)

## 비용 메모 (us-west-2, 대략)

- t3.micro: 프리티어 12개월 750h 무료 → 첫 해 컴퓨팅 $0 (1GB라 swap 2GB로 보완)
- EBS 30GB gp3: 프리티어 30GB 범위 → 첫 해 사실상 무료
- 공인 IPv4: ~$3.6/월 (사용 중이면 부과)
- Elastic IP: 실행 중 인스턴스에 연결돼 있으면 위 공인 IPv4 요금에 포함(추가 부담 없음).
  단 `--destroy` 후 유휴 보존하면 그 기간에도 ~$3.6/월(같은 IP 유지 대가) → 오래 안 쓰면 `--release-eip`
- 안 쓸 땐 `aws ec2 stop-instances ...`로 컴퓨팅 과금 0(EBS만), `--destroy`로 전체 삭제
