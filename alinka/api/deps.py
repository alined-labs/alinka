"""FastAPI dependencies shared by the routes: a pooled connection and the session in view."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, Query, Request, Response

from alinka import db
from alinka.api import sessions
from alinka.api.models import View
from alinka.api.sessions import CANONICAL, Ctx

SANDBOX_COOKIE = "alinka_sandbox"


def connection() -> Iterator[psycopg.Connection]:
    with db.connection() as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(connection)]
ViewQ = Annotated[View, Query(description="sandbox (default) or the read-only canonical run")]


def sandbox(request: Request, response: Response, conn: Conn) -> Ctx:
    """The visitor's sandbox from the HttpOnly cookie, created with a full inbox on first visit."""
    sid = request.cookies.get(SANDBOX_COOKIE)
    ctx = sessions.context(conn, sid) if sid and sid != CANONICAL else None
    if ctx is None:
        ctx = sessions.create_sandbox(conn)
        response.set_cookie(
            SANDBOX_COOKIE,
            ctx.session_id,
            max_age=int(sessions.SANDBOX_TTL.total_seconds()),
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        )
    return ctx


Sandbox = Annotated[Ctx, Depends(sandbox)]


def viewed(request: Request, response: Response, conn: Conn, view: ViewQ = "sandbox") -> Ctx:
    """The canonical run with ?view=canonical, otherwise the visitor's sandbox."""
    if view == "canonical":
        return sessions.ensure_canonical(conn)
    return sandbox(request, response, conn)


Viewed = Annotated[Ctx, Depends(viewed)]
