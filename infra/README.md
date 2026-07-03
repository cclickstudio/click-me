# infra — EC2 배포 인프라

ClickMe 운영 배포(단일 EC2 + nginx + HTTPS)를 위한 인프라 스크립트 모음.
**이 문서만 읽으면 생성·배포·운영·팀 공유가 전부 이해되도록** 정리했다.

## 구성 파일

| 파일 | 역할 | 주로 쓰는 사람 |
| --- | --- | --- |
| `provision_ec2.py` | EC2 + 부속 리소스(SG·IAM·**Elastic IP**) 생성/철거 | 인프라 담당 |
| `resize_instance.py` | 인스턴스 타입 전환(micro/small/medium) | 인프라 담당 |
| `fetch_key.py` | SSM에서 PEM·`infra/.env` 받아오기 | 팀원 |
| `start_portainer.py` | Portainer 기동 + SSH 터널로 `localhost:9000` | 팀원 |
| `clickme-key.pem` | SSH 개인키 (gitignore·**커밋 금지**) | — |
| `.env` | provision이 만든 참조값(EC2_HOST 등). gitignore | — |

> **팀원은 인스턴스 생성/삭제(`provision_ec2.py`·`resize_instance.py`)는 건드리지 말고 `fetch_key.py`·`start_portainer.py`만** 쓰면 된다.
> 리버스 프록시는 [`../deploy/nginx.conf`](../deploy/nginx.conf), 컨테이너 구성은 [`../docker-compose.prod.yml`](../docker-compose.prod.yml), 배포는 [`../.github/workflows/cd.yml`](../.github/workflows/cd.yml).

## 사전 준비

- **AWS CLI 설치** — [공식 설치 가이드](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **자격증명 설정** — `aws configure` ([설정 가이드](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)) 후 `aws sts get-caller-identity`로 확인
- 리전은 `us-west-2` (계정 `445459853661`)

## provision_ec2.py — 인스턴스 생성/철거

`us-west-2`에 아래를 **멱등적으로**(이미 있으면 재사용) 만든다.

1. **키페어** `clickme-key` → `infra/clickme-key.pem` 저장(Windows ACL 잠금) + **SSM에 백업**(팀 공유용)
2. **보안그룹** `clickme-sg` → 22·80·443만 오픈 (8000/3000/9000은 미개방 — 내부·터널 전용)
3. **IAM Role/Instance Profile** → EC2가 ECR을 **pull**하도록 ReadOnly (EC2에 AWS 키 저장 불필요)
4. **EC2 인스턴스** `clickme-prod` → Ubuntu 24.04, EBS 30GB gp3, t3.micro
5. **Elastic IP** `clickme-eip` → 인스턴스에 붙는 **고정 공인 IP**. 철거·재생성·타입 변경에도 그대로 유지
6. user-data로 부팅 시 **docker·docker compose·awscli·swap(2GB)** 자동 설치 + `~/clickme/backend` 생성
7. 참조값(EC2_HOST 등)을 `infra/.env`로 기록 (start_portainer.py·fetch_key.py용)

```bash
python infra/provision_ec2.py            # 생성
python infra/provision_ec2.py --destroy  # 철거: 인스턴스·SG·키·IAM·ECR·SSM PEM 삭제 (EIP는 보존해 재생성 시 같은 IP)
```

> **Elastic IP가 고정**이라 `EC2_HOST`(공인 IP)가 바뀌지 않는다 — 재생성·타입 변경·stop/start 후에도
> GitHub Secrets나 DNS를 다시 손댈 필요가 없다. (프론트는 nginx same-origin `/api` 호출이라 CORS도 발생하지 않는다.)
> 유휴 EIP 과금(~$3.6/월)까지 끊고 싶으면 `--destroy --release-eip` — 단 이땐 다음 생성 시 IP가 바뀐다.

## resize_instance.py — 타입 전환(비용↔성능)

메모리가 부족하면(PDF/AI 동시 피크) 위 등급으로 올리고, 한가하면 내려 비용을 아낀다.
stop→타입 변경→start를 자동으로 하며 **EBS(데이터)와 EIP가 유지**되어 데이터도 공인 IP도 그대로다.
실제로 메모리 문제로 업그레이드/다운그레이드 해야 할 상황이 아니면 **함부로 건들지 않는다.**

```bash
python infra/resize_instance.py --small
```

| 파라미터 | 타입 | 메모리 | 비고 |
| --- | --- | --- | --- |
| `--micro` | t3.micro | 1GB | 프리티어 대상 |
| `--small` | t3.small | 2GB | ~$15/월 |
| `--medium` | t3.medium | 4GB | |

## fetch_key.py — 팀원 키 공유

`provision_ec2.py`를 실행한 사람만 `clickme-key.pem`을 갖게 되는 문제를 없앤다. AWS는 private key를
**생성 시 1회만** 반환하므로, provision이 키를 만드는 순간 PEM을 **SSM Parameter Store(SecureString·KMS 암호화)**
에 백업해둔다. 팀원은 아래 한 줄로 받아온다(파일을 직접 주고받을 필요 없음).

```bash
python infra/fetch_key.py
```

- SSM(`/clickme/ec2/private-key`)에서 PEM을 받아 `infra/clickme-key.pem` 재구성(+ACL/권한 잠금)
- 현재 EIP·instance-id를 조회해 `infra/.env`도 재구성 → 곧바로 `ssh`·`start_portainer.py` 사용
- 필요 권한(팀 계정 자격증명 전제): `ssm:GetParameter`(+기본 KMS decrypt), `ec2:DescribeAddresses`, `ec2:DescribeInstances`

> 카톡·메일로 PEM을 뿌리는 것보다 안전하다(전송 중 노출 없음, KMS 저장).

## start_portainer.py — 컨테이너 상태 GUI

Portainer는 EC2 `127.0.0.1:9000`에만 바인딩돼 외부에 열리지 않는다(SG 9000 미개방). SSH 터널로만
접근하며, 이 스크립트가 **기동(없으면 생성) → 터널 → 브라우저 오픈**을 자동화한다.

```bash
python infra/start_portainer.py
```

- `infra/.env`에서 `EC2_HOST`·PEM 경로를 읽는다 (없으면 먼저 `python infra/fetch_key.py`).
- `localhost:9000` 터널이 열리고 브라우저로 **http://localhost:9000** 이 자동 오픈. 창은 켜 두고 **Ctrl+C**로 종료.
- 첫 실행이면 관리자 계정 자동 생성 → **`admin` / `clickstudio1234`**
  (`start_portainer.py`의 `ADMIN_USER`·`ADMIN_PASSWORD` 상수로 교체 가능. 터널 전용이라 평문 보관, 실운영 전 변경 권장).
- `Bad permissions / UNPROTECTED PRIVATE KEY` 오류면 키 ACL이 풀린 것 → `fetch_key.py` 재실행 또는:
  ```powershell
  icacls "infra\clickme-key.pem" /reset; icacls "infra\clickme-key.pem" /inheritance:r; icacls "infra\clickme-key.pem" /grant:r "${env:USERNAME}:F"
  ```

## backend/.env 배치 (운영 환경변수)

`backend/.env`(비밀이라 리포·이미지에 없음)는 **각자 수동으로** EC2에 올린다
(개발자마다 값이 다를 수 있어 자동 업로드하지 않는다). `~/clickme/backend/.env` 위치에 둔다.

```bash
scp -i infra/clickme-key.pem backend/.env ubuntu@<EC2_HOST>:/home/ubuntu/clickme/backend/.env
```

최소 `APP_ENV=production`, `DATABASE_URL`(NeonDB), `OPENAI_API_KEY`가 채워져 있어야 한다.
`<EC2_HOST>`는 `infra/.env`의 `EC2_HOST` 값.

## TLS 인증서 (HTTPS) — 자동 발급·갱신

nginx의 443 블록이 `/etc/letsencrypt/live/clickme.co.kr/` 인증서를 참조하는데, 새 EC2엔 그 파일이
없어 그냥 두면 nginx가 **기동 즉시 크래시**한다. 이를 막기 위해 발급을 코드로 자동화했다.

- **최초 발급** [`../deploy/init-letsencrypt.sh`](../deploy/init-letsencrypt.sh) (표준 dummy 부트스트랩 패턴)
  1. 임시 self-signed(dummy) 인증서를 심어 nginx를 일단 정상 기동(443 크래시 방지)
  2. certbot이 80포트 **webroot HTTP-01**(`/.well-known/acme-challenge`) 챌린지로 진짜 인증서 발급
  3. dummy를 진짜로 교체 후 nginx reload
  - **cd.yml이 자동 호출**한다 — deploy 스크립트가 `fullchain.pem` 부재를 감지하면 실행(있으면 건너뜀, 멱등).
- **자동 갱신** [`../docker-compose.prod.yml`](../docker-compose.prod.yml)의 **certbot 서비스**가 12h 주기로 `certbot renew`
  (만료 30일 이내만 실제 갱신). nginx는 6h마다 `nginx -s reload`로 새 인증서를 **무중단** 픽업한다.

> **전제(DNS)** — `clickme.co.kr`·`www.clickme.co.kr`의 A 레코드가 **EC2의 Elastic IP를 가리켜야** 한다
> (외부 등록기관에서 설정). EIP가 고정이라 A 레코드는 한 번만 설정하면 된다. HTTP-01 챌린지는 도메인이
> 서버로 resolve돼야 성공하므로, DNS 전파 전에는 발급이 실패한다.

수동 발급/재발급이 필요하면 EC2에서:

```bash
cd ~/clickme
# (ECR 로그인 후) REGISTRY = <account>.dkr.ecr.us-west-2.amazonaws.com
REGISTRY=<account>.dkr.ecr.us-west-2.amazonaws.com bash deploy/init-letsencrypt.sh
# 실발급 전 테스트만 하려면(rate limit 회피): STAGING=1 을 앞에 붙인다
```

Let's Encrypt 알림 이메일은 `LETSENCRYPT_EMAIL` 환경변수로 바꾼다(기본 `fjdksla3@gmail.com`).

## 배포 흐름

```
개발자 push → cd.yml: backend/frontend 이미지 빌드 → ECR push
           → compose·nginx.conf·init-letsencrypt.sh EC2로 복사 → EC2가 ECR pull
           → (인증서 없으면) init-letsencrypt.sh 최초 발급 → docker compose up
EC2 런타임: nginx(:80 리다이렉트/ACME, :443 서비스) ─ /api → backend(내부) · /docs 차단 · 그 외 → frontend(내부)
           certbot 서비스: 12h마다 renew · nginx: 6h마다 reload로 무중단 갱신
```

- compose·nginx.conf·init-letsencrypt.sh는 매 배포마다 cd.yml이 자동 복사한다.
- **GitHub Secrets**(AWS 키·`EC2_HOST`·`EC2_SSH_KEY` 등)는 **최초 1회만** 등록한다 — 필요한 목록·용도는
  [`cd.yml` 상단 주석](../.github/workflows/cd.yml)에 정리돼 있다. EIP 고정이라 이후 값 갱신은 없다.

## 비용 메모 (us-west-2, 대략)

- **t3.micro**: 프리티어 12개월 750h 무료 → 첫 해 컴퓨팅 $0 (1GB라 swap 2GB로 보완)
- **EBS 30GB gp3**: 프리티어 30GB 범위 → 첫 해 사실상 무료
- **Elastic IP**: 실행 중 인스턴스에 붙어 있으면 공인 IPv4 요금(~$3.6/월)에 포함(추가 부담 없음)
- 안 쓸 땐 `resize_instance.py`로 낮추거나 `aws ec2 stop-instances`로 컴퓨팅 과금 0(EBS만), 완전 정리는 `--destroy`
