from __future__ import annotations

import asyncio
from typing import Optional

from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


async def _healthz(_request):
    return web.Response(text="ok", content_type="text/plain")


async def _run_app(port: int):
    app = web.Application()
    async def _version(_request):
        try:
            from .build_info import get_build_info
            bi = get_build_info()
            data = {"version": bi.version, "commit": bi.commit, "date": bi.date}
        except Exception:
            data = {"version": None, "commit": None, "date": None}
        return web.json_response(data)
    async def _metrics(_request):
        data = generate_latest()
        return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})

    app.add_routes([
        web.get("/healthz", _healthz),
        web.get("/readyz", _healthz),
        web.get("/version", _version),
        web.get("/metrics", _metrics),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    # Keep running
    while True:
        await asyncio.sleep(3600)


def start_health_server(loop: asyncio.AbstractEventLoop, port: int) -> None:
    loop.create_task(_run_app(port))
