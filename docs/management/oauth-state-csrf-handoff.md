# [🅰 핸드오프] OAuth state 미검증 — Meta 연결 CSRF/토큰 주입 (Vuln 2)

> 출처: 2026-06-22 보안 리뷰. 소유: 🅰(OAuth/connect/callback). 🅱는 코드 미수정, 본 문서로 전달.
> 관련 설계: `docs/superpowers/specs/2026-06-22-management-authz-hardening-design.md` §4.

## 문제

- `/meta/connect`(`backend/api/routers/management.py:1548`)가 `state="{org}:{nonce}"`를 만들지만 nonce를
  서버에 저장하지 않는다.
- `/meta/callback`(`management.py:1578`)은 미인증이며 `state.split(":", 1)[0]`(1602)로 파싱한 org를 그대로
  신뢰해, 교환한 장기 토큰을 그 org로 `upsert`한다(`connection_repository.py` — organization_id 단일 키라
  기존 토큰을 덮어쓴다).

## 영향

- OAuth CSRF / 토큰 주입: 공격자의 Meta 토큰을 임의 org에 바인딩 → 해당 org의 캠페인 읽기/쓰기가
  공격자 자산으로 흐른다.
- 임의 org의 기존 Meta 연결 토큰 덮어쓰기(자격 탈취).

## 권장 수정

1. connect 시점에 인증 사용자/org에 바인딩된 **single-use·TTL nonce를 서버에 저장**한다(신규 테이블 또는
   기존 저장소). state는 불투명 토큰만 운반한다.
2. callback에서 nonce를 조회·소진(consume) 검증하고, **저장된 레코드의 org**를 사용한다. raw `state`의
   org는 신뢰하지 않는다.
3. callback의 org 도출을 평문 파싱(`state.split`)에서 제거한다.

## 비고

- DB 테이블 추가가 필요하면 `core/models.py`·Alembic 변경이라 사전 공지 + 양측 합의가 필요하다(공통부 규칙).
- 🅱가 이번 브랜치(`feat/management-boeun`)에서 처리한 Vuln 3(상태변경 엔드포인트 인증·소유권)와는 별개
  작업이며, OAuth 경로는 의도적으로 건드리지 않았다.
