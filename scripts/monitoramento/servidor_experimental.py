"""Entrada Uvicorn opcional: cabeçalhos de diagnóstico sem editar as APIs."""

from datetime import datetime, timezone
from importlib import import_module
import os


class Diagnostico:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        received = datetime.now(timezone.utc).isoformat().encode("ascii")

        async def diagnostic_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                headers = list(message.get("headers", []))
                names = {key.lower() for key, value in headers}
                # CPU_DIAGNOSTICO pode já estar habilitado: preserva os cabeçalhos existentes.
                for key, value in [(b"x-worker-pid", str(os.getpid()).encode("ascii")),
                                   (b"x-server-received-utc", received),
                                   (b"x-server-sent-utc", datetime.now(timezone.utc).isoformat().encode("ascii"))]:
                    if key not in names:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, diagnostic_send)


def criar_app():
    name = os.getenv("POI_APLICACAO", "cpu")
    modules = {"cpu": "cpu_bound", "memoria": "memory_bound", "io": "io_bound"}
    if name not in modules:
        raise ValueError("POI_APLICACAO deve ser cpu, memoria ou io.")
    api = import_module(f"apps.{modules[name]}.main").app
    return Diagnostico(api) if os.getenv("POI_DIAGNOSTICO", "0") == "1" else api
