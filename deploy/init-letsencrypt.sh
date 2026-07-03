#!/bin/bash
# Let's Encrypt 인증서를 최초 1회 발급하는 부트스트랩 (EC2 ~/clickme 에서 실행)
#
# 문제: nginx의 443 블록은 /etc/letsencrypt/live/clickme.co.kr/ 인증서를 참조하는데,
#       새 EC2엔 그 파일이 없어 nginx 컨테이너가 기동 즉시 크래시한다.
# 해결(표준 패턴, wmnnd/nginx-certbot):
#   1) 임시 self-signed(dummy) 인증서를 심어 nginx를 일단 정상 기동시키고(443 크래시 방지),
#   2) certbot이 80포트 webroot(/.well-known/acme-challenge) 챌린지로 진짜 인증서를 발급한 뒤,
#   3) dummy를 진짜로 교체하고 nginx를 reload 한다.
# 이후 갱신은 docker-compose.prod.yml 의 certbot 서비스가 12h 주기로 자동 처리한다.
#
# 전제:
#   - clickme.co.kr / www.clickme.co.kr 의 DNS A 레코드가 이미 이 EC2의 EIP를 가리킬 것
#     (외부 등록기관 관리 — HTTP-01 챌린지는 도메인이 서버로 resolve돼야 성공).
#   - SG 80/443 오픈(provision_ec2.py 기본), docker/compose 설치 완료.
#   - ECR 이미지 pull 가능하도록 REGISTRY 환경변수 세팅 + ECR 로그인 완료
#     (cd.yml deploy 잡이 이 스크립트 호출 전에 처리. 수동 실행 시 아래 '수동 실행' 참고).
#
# 멱등: 이미 진짜 인증서가 있으면 아무것도 하지 않고 종료한다(안전하게 반복 호출 가능).
#
# 수동 실행(EC2에서 직접):
#   cd ~/clickme
#   REGISTRY=<account>.dkr.ecr.us-west-2.amazonaws.com \
#     aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin "$REGISTRY"
#   REGISTRY=<account>.dkr.ecr.us-west-2.amazonaws.com bash deploy/init-letsencrypt.sh
#
# 옵션 환경변수:
#   LETSENCRYPT_EMAIL  만료 알림 수신 이메일 (기본: fjdksla3@gmail.com)
#   STAGING=1          Let's Encrypt 스테이징 발급(신뢰 안 되는 테스트 인증서, rate limit 넉넉). 검증용.
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
PRIMARY_DOMAIN="clickme.co.kr"
DOMAIN_ARGS="-d clickme.co.kr -d www.clickme.co.kr"
EMAIL="${LETSENCRYPT_EMAIL:-fjdksla3@gmail.com}"
RSA_KEY_SIZE=4096

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

live_path="/etc/letsencrypt/live/${PRIMARY_DOMAIN}"

# ── 0) 이미 진짜(Let's Encrypt) 인증서가 있으면 종료 ──────────────────────
# dummy는 issuer가 'localhost', 진짜는 "Let's Encrypt" → issuer로 진짜 여부 판별.
if [ -f "${live_path}/fullchain.pem" ]; then
  if docker run --rm -v /etc/letsencrypt:/etc/letsencrypt --entrypoint openssl certbot/certbot \
       x509 -in "${live_path}/fullchain.pem" -noout -issuer 2>/dev/null | grep -qi "let's encrypt"; then
    echo "[=] 이미 Let's Encrypt 인증서 존재 — 발급 건너뜀 ($live_path). 갱신은 certbot 서비스가 담당."
    exit 0
  fi
  echo "[*] dummy/비정상 인증서 감지 — 진짜 인증서로 재발급 진행."
fi

echo "[*] Let's Encrypt 최초 발급 시작 (도메인: $PRIMARY_DOMAIN, 이메일: $EMAIL)"

# ── 1) dummy 인증서 생성 → nginx가 443에서 크래시하지 않고 뜨게 한다 ────────
# (TLS 파라미터는 deploy/nginx.conf 가 직접 관리하므로 webroot 방식엔 별도 설정 파일 불필요)
echo "[*] 임시(dummy) 인증서 생성 → $live_path"
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt --entrypoint sh certbot/certbot -c "\
  mkdir -p '$live_path' && \
  openssl req -x509 -nodes -newkey rsa:$RSA_KEY_SIZE -days 1 \
    -keyout '$live_path/privkey.pem' -out '$live_path/fullchain.pem' \
    -subj '/CN=localhost'"

# ── 2) 전체 스택 기동(backend/frontend/nginx) — nginx는 dummy로 443 정상 기동 ─
# nginx.conf 가 proxy_pass http://backend:8000 을 시작 시 resolve 하므로 backend/frontend도 함께 띄운다.
echo "[*] docker compose 기동 (dummy 인증서로 nginx 임시 기동)"
compose up -d

# nginx가 뜰 시간을 잠깐 준다(80 챌린지 응답 준비).
sleep 5

# ── 3) dummy 삭제 후 진짜 인증서 발급(webroot HTTP-01) ────────────────────
echo "[*] dummy 인증서 제거"
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt --entrypoint sh certbot/certbot -c "\
  rm -rf /etc/letsencrypt/live/${PRIMARY_DOMAIN} \
         /etc/letsencrypt/archive/${PRIMARY_DOMAIN} \
         /etc/letsencrypt/renewal/${PRIMARY_DOMAIN}.conf"

staging_arg=""
if [ "${STAGING:-0}" != "0" ]; then
  echo "[!] STAGING 모드 — 신뢰되지 않는 테스트 인증서를 발급합니다."
  staging_arg="--staging"
fi

echo "[*] certbot 실제 발급(webroot /var/www/certbot)"
# certbot 서비스는 entrypoint가 '갱신 루프'로 override돼 있으므로, 일회성 발급 땐
# --entrypoint certbot 으로 이미지 기본 바이너리를 복구하고 인자를 command로 넘긴다.
# ($staging_arg·$DOMAIN_ARGS 는 공백 분리가 필요해 의도적으로 따옴표 없이 전달)
# shellcheck disable=SC2086
compose run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  $staging_arg \
  $DOMAIN_ARGS \
  --email "$EMAIL" \
  --rsa-key-size "$RSA_KEY_SIZE" \
  --agree-tos --no-eff-email \
  --non-interactive --force-renewal

# ── 4) nginx가 진짜 인증서를 로드하도록 reload ────────────────────────────
echo "[*] nginx reload (진짜 인증서 적용)"
compose exec nginx nginx -s reload

echo "[+] 완료 — https://${PRIMARY_DOMAIN} 인증서 발급·적용됨. 갱신은 certbot 서비스가 자동 처리."
