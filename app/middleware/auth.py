import base64
import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, username_env: str = "ADMIN_USER", password_env: str = "ADMIN_PASSWORD") -> None:
        super().__init__(app)
        self.username = os.environ.get(username_env, "admin")
        self.password = os.environ.get(password_env)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        # Allow non-API requests and SSE without auth
        if not path.startswith("/api") or path.startswith("/api/stream/") or path.startswith("/healthz"):
            return await call_next(request)
        # If no password configured, allow all (dev default)
        if not self.password:
            return await call_next(request)
        header = request.headers.get("authorization")
        if not header or not header.lower().startswith("basic "):
            return self._unauthorized()
        try:
            b64 = header.split(" ", 1)[1]
            decoded = base64.b64decode(b64).decode("utf-8")
            user, pw = decoded.split(":", 1)
        except Exception:
            return self._unauthorized()
        if user != self.username or pw != self.password:
            return self._unauthorized()
        return await call_next(request)

    @staticmethod
    def _unauthorized() -> Response:
        return PlainTextResponse("Unauthorized", status_code=401, headers={"WWW-Authenticate": "Basic realm=restricted"})

