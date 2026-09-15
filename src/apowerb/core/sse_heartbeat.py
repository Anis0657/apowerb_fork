"""Signal régulier dans un flux SSE resté muet.

Un agent qui explore une base peut rester plus d'une minute sans produire
d'événement. Chaque maillon entre le navigateur et le backend coupe alors
la connexion sur son propre délai de silence (nginx, relais Node de Next) ;
le backend voit le client partir et annule l'exécution. Un commentaire SSE
(`: ping`) fait passer des octets sans rien signifier : les clients SSE et
le front ignorent les blocs sans `data:`.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

PING = ": ping\n\n"

DEFAULT_INTERVAL_SECONDS = 15.0


def heartbeat_interval() -> float:
    """`SSE_HEARTBEAT_SECONDS` (défaut 15) ; 0 désactive le signal."""
    raw = os.getenv("SSE_HEARTBEAT_SECONDS", "")
    try:
        return max(0.0, float(raw)) if raw.strip() else DEFAULT_INTERVAL_SECONDS
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


async def with_sse_heartbeat(
    source: AsyncIterator[str],
    interval: float | None = None,
) -> AsyncIterator[str]:
    """Relaie `source` et intercale `PING` après `interval` s de silence.

    Le signal n'est envoyé qu'entre deux événements complets : un morceau
    relayé peut s'arrêter au milieu d'un événement, et un ping à cet endroit
    le corromprait.
    """
    if interval is None:
        interval = heartbeat_interval()
    iterator = source.__aiter__()
    if interval <= 0:
        async for chunk in iterator:
            yield chunk
        return

    at_boundary = True
    pending: asyncio.Task | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                if at_boundary:
                    yield PING
                continue
            task, pending = pending, None
            try:
                chunk = task.result()
            except StopAsyncIteration:
                return
            if chunk:
                at_boundary = chunk.endswith("\n\n")
            yield chunk
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration, Exception):
                pass
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()
