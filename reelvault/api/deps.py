from __future__ import annotations

from fastapi import Request

from ..workspace import Workspace


def ws(request: Request) -> Workspace:
    return request.app.state.workspace
