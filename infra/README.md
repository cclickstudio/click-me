# infra — EC2 배포 인프라

ClickMe 운영 배포(단일 EC2 + nginx)를 위한 인프라 스크립트 모음.

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `provision_ec2.py` | AWS CLI로 운영 EC2 한 대 + 부속 리소스를 생성/철거 |
| `clickme-key.pem` | 스크립트가 만든 SSH 키 (gitignore, **커밋 금지**) |

> 리버스 프록시 설정은 `../deploy/nginx.conf`, 컨테이너 구성은 `../docker-compose.prod.yml`,
> 배포 파이프라인은 `../.github/workflows/cd.yml` 참고.

## provision_ec2.py 가 하는 일

빌드는 GitHub Actions가 하고 EC2는 ECR 이미지를 **pull해서 실행만** 하므로(부담 낮음), 비용 최소화에 맞춰져 있다.
한 번 실행하면 `us-west-2`에 아래를 **멱등적으로**(이미 있으면 재사용) 만든다.

1. **키페어** `clickme-key` → `infra/clickme-key.pem` 저장 (Windows는 ACL까지 잠금)
2. **보안그룹** `clickme-sg` → 22(SSH/CD)·80(nginx)·443(추후 HTTPS)만 오픈
3. **IAM Role/Instance Profile** → EC2가 ECR을 pull하도록 ReadOnly (EC2에 AWS 키 저장 불필요)
4. **EC2 인스턴스** `clickme-prod` → Ubuntu 24.04, EBS 30GB gp3, t3.micro(기본)
5. user-data로 부팅 시 **docker·docker compose·awscli·swap(2GB)** 자동 설치 + `~/clickme/backend` 생성

## 사용법

전제: 로컬에 `aws` CLI 설치 + 자격증명 설정(`aws sts get-caller-identity` 확인).

```bash
# 생성
python infra/provision_ec2.py

# 철거(과금 중단 — 인스턴스·SG·키페어·IAM 삭제)
python infra/provision_ec2.py --destroy
```

상단 설정 상수(`REGION`, `INSTANCE_TYPE`, `DISK_GB` 등)만 바꿔 조정한다.

## 생성 후 1회 수동 작업

스크립트가 출력하는 값으로 GitHub Secrets를 등록한다.

- `EC2_HOST` = 출력된 퍼블릭 IP
- `EC2_USER` = `ubuntu`
- `EC2_SSH_KEY` = `infra/clickme-key.pem` **전체 내용**
- `NEXT_PUBLIC_API_URL` = `http://<EC2_HOST>` (nginx 단일 진입점이라 포트·`/api` 없이 호스트만)

그리고 백엔드 운영 환경변수 파일을 EC2에 올린다(리포에 없음, gitignore).

```bash
ssh -i infra/clickme-key.pem ubuntu@<EC2_HOST> "mkdir -p ~/clickme/backend"
scp -i infra/clickme-key.pem backend/.env ubuntu@<EC2_HOST>:/home/ubuntu/clickme/backend/.env
```

`backend/.env`에는 최소 `APP_ENV=production`, `DATABASE_URL`(NeonDB), `OPENAI_API_KEY`,
`CORS_ALLOW_ORIGINS=http://<EC2_HOST>` 가 채워져 있어야 한다.

## 배포 흐름과의 관계

```
개발자 push → CD(cd.yml): backend/frontend 이미지 빌드 → ECR push
           → compose·nginx.conf EC2로 복사 → EC2가 ECR pull → docker compose up
EC2 런타임: nginx(:80) ─ /api → backend(내부) · /docs 차단 · 그 외 → frontend(내부)
```

- compose·nginx.conf는 매 배포마다 cd.yml이 자동 복사한다.
- `backend/.env`만 위처럼 **수동 1회** 배치하면 된다(비밀이라 리포·이미지에 없음).

## 인스턴스 타입 승격(비용↔성능)

t3.micro로 메모리가 부족하면(PDF/AI 동시 피크) 데이터 보존한 채 올린다.

```bash
IID=<instance-id>
aws ec2 stop-instances            --region us-west-2 --instance-ids $IID
aws ec2 wait instance-stopped     --region us-west-2 --instance-ids $IID
aws ec2 modify-instance-attribute --region us-west-2 --instance-id $IID --instance-type t3.small
aws ec2 start-instances           --region us-west-2 --instance-ids $IID
```

> start 후 퍼블릭 IP가 바뀌면 `EC2_HOST`·`NEXT_PUBLIC_API_URL` secret과 EC2의
> `backend/.env`(`CORS_ALLOW_ORIGINS`)를 갱신해야 한다. 고정하려면 Elastic IP를 연결한다.

## 비용 메모 (us-west-2, 대략)

- t3.micro: 프리티어 12개월 750h 무료 → 첫 해 컴퓨팅 $0 (1GB라 swap 2GB로 보완)
- EBS 30GB gp3: 프리티어 30GB 범위 → 첫 해 사실상 무료
- 공인 IPv4: ~$3.6/월 (사용 중이면 부과)
- 안 쓸 땐 `aws ec2 stop-instances ...`로 컴퓨팅 과금 0(EBS만), `--destroy`로 전체 삭제
