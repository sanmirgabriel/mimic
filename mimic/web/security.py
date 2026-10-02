"""Small browser policy; API docs keep their existing CDN/inline requirements."""
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

HTML_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'")
DOCS_CSP = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"


def secure_headers(headers, path: str) -> None:
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("Content-Security-Policy", DOCS_CSP if path in ("/docs", "/redoc") else HTML_CSP)


class BrowserHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured_send(message):
            if message["type"] == "http.response.start":
                secure_headers(MutableHeaders(scope=message), scope["path"])
            await send(message)

        if scope["type"] == "http" and scope["path"].startswith("/api/") and scope["method"] in ("POST", "PATCH", "PUT", "DELETE"):
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            expected = f"{scope['scheme']}://{headers.get('host', '')}"
            # Programmatic consumers do not need a form token. Browsers must
            # not submit mutations to the local API from another origin.
            if (origin is not None and origin != expected) or headers.get("sec-fetch-site") == "cross-site":
                response = JSONResponse({"detail": "cross-origin API mutation is not allowed"}, status_code=403)
                await response(scope, receive, secured_send)
                return
        await self.app(scope, receive, secured_send if scope["type"] == "http" else send)
