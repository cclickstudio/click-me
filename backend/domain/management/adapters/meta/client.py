# 🤝 Meta 인증·토큰·HTTP 공통층 + 토큰 마스킹 (게이트 #8 — 민감값 평문 노출 금지)
"""🤝 Meta Graph API 인증·HTTP 공통층 — reader·writer 공용 (토큰 마스킹 포함).

raw httpx로 Graph API를 직접 호출한다(신규 SDK 의존성 0). 테스트는 생성자에
``httpx.MockTransport``를 주입해 네트워크 없이 녹화 응답으로 계약을 검증한다
(generator/adapters/instagram.py의 transport 주입 패턴과 동일).

토큰·앱 시크릿은 전송 payload에만 싣고 로그·예외에는 마스킹한다 (게이트 #8, CLAUDE.md 보안).
"""

from __future__ import annotations

from typing import Any

import httpx


def mask_token(token: str | None) -> str:
    """access_token을 로그용으로 마스킹 — 앞 4자만 남기고 가린다."""
    if not token:
        return "<none>"
    return f"{token[:4]}…(masked)"


class MetaTokenError(RuntimeError):
    """토큰/앱 자격 미설정 — 메시지에 비밀값 없음."""


class MetaApiError(RuntimeError):
    """Graph API 응답의 error 객체를 표준 예외로 변환 — 메시지에 토큰 미포함."""

    def __init__(self, code: int | None, subcode: int | None, message: str) -> None:
        self.code = code
        self.subcode = subcode
        self.message = message
        super().__init__(f"Meta API error (code={code}, subcode={subcode}): {message}")


class MetaClient:
    """Graph API 호출 공통층. path는 base 뒤에 붙는 상대 경로 (예: '{id}/insights')."""

    def __init__(
        self,
        access_token: str,
        *,
        ad_account_id: str | None = None,
        api_version: str = "v21.0",
        app_id: str | None = None,
        app_secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = access_token
        self.ad_account_id = ad_account_id
        self._base = f"https://graph.facebook.com/{api_version}"
        self._app_id = app_id
        self._app_secret = app_secret
        self._transport = transport  # 테스트용 httpx.MockTransport 주입 지점
        self._timeout = timeout

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # access_token 기본 주입 → 호출자 params가 덮어쓸 수 있음(앱 토큰 등 ⑤ 토큰검증).
        query = {"access_token": self._token, **(params or {})}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            res = await client.get(f"{self._base}/{path}", params=query)
            return self._handle(res)

    async def post(
        self, path: str, data: dict[str, Any] | None = None, *, validate_only: bool = False
    ) -> dict[str, Any]:
        body: dict[str, Any] = {**(data or {}), "access_token": self._token}
        if validate_only:
            # Meta가 요청을 검증만 하고 실제 변경은 하지 않는다 (VALIDATE_ONLY의 핵심).
            body["execution_options"] = '["validate_only"]'
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            res = await client.post(f"{self._base}/{path}", data=body)
            return self._handle(res)

    @staticmethod
    def _handle(res: httpx.Response) -> dict[str, Any]:
        payload = res.json()
        if isinstance(payload, dict) and "error" in payload:
            err = payload["error"]
            raise MetaApiError(
                err.get("code"), err.get("error_subcode"), err.get("message", "unknown error")
            )
        res.raise_for_status()
        return payload

    @property
    def app_access_token(self) -> str:
        """app_id|app_secret — 토큰 디버그용 (⑤)."""
        if not (self._app_id and self._app_secret):
            raise MetaTokenError("META_APP_ID/META_APP_SECRET 미설정 — 앱 토큰 생성 불가")
        return f"{self._app_id}|{self._app_secret}"

    async def debug_token(self) -> dict[str, Any]:
        """⑤ 토큰 검증 — 만료·스코프·유효성 조회 (앱 토큰으로 입력 토큰 점검)."""
        payload = await self.get(
            "debug_token",
            {"input_token": self._token, "access_token": self.app_access_token},
        )
        return payload.get("data", payload)

    def __repr__(self) -> str:  # 토큰 평문 노출 방지
        return f"MetaClient(token={mask_token(self._token)}, ad_account_id={self.ad_account_id})"


def build_meta_client(
    settings: object, *, transport: httpx.AsyncBaseTransport | None = None
) -> MetaClient:
    """settings에서 자격증명을 읽어 MetaClient 생성 — reader·writer 공용 팩토리."""
    return MetaClient(
        access_token=getattr(settings, "meta_access_token", None) or "",
        ad_account_id=getattr(settings, "meta_ad_account_id", None),
        api_version=getattr(settings, "meta_graph_api_version", None) or "v21.0",
        app_id=getattr(settings, "meta_app_id", None),
        app_secret=getattr(settings, "meta_app_secret", None),
        transport=transport,
    )
