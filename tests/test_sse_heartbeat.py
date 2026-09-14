"""Un flux de chat silencieux ne doit plus être coupé en route.

Mesuré en dev le 14/09/2026 : une question vague (« donne-moi un aperçu
des données ») faisait travailler l'agent plus d'une minute sans rien
envoyer. Le vhost front coupait à 60 s de silence (504), le relais Node de
Next coupe à 300 s, et le backend annulait l'exécution. Le flux envoie
désormais un commentaire SSE (`: ping`) quand il est resté muet trop
longtemps : toute la chaîne voit passer des octets, et le front ignore les
blocs sans `data:`.

Le signal ne s'insère qu'entre deux événements complets : les morceaux
relayés depuis ADK sont des octets bruts qui peuvent couper un événement
en deux, et un ping au milieu le corromprait.
"""

import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apowerb.core.sse_heartbeat import PING, with_sse_heartbeat


async def _source(parts, pause=0.0, pause_before=None, closed=None):
    try:
        for i, part in enumerate(parts):
            if pause_before is None or i in pause_before:
                await asyncio.sleep(pause)
            yield part
    finally:
        if closed is not None:
            closed.append(True)


async def _collect(agen):
    return [chunk async for chunk in agen]


async def test_a_silent_stream_gets_pings_between_events():
    parts = ['data: {"a": 1}\n\n', 'data: {"b": 2}\n\n']

    out = await _collect(with_sse_heartbeat(_source(parts, pause=0.35, pause_before={1}), interval=0.1))

    assert out.count(PING) >= 2
    assert [c for c in out if c != PING] == parts
    assert out.index(PING) > out.index(parts[0])


async def test_no_ping_inside_a_split_event():
    parts = ['data: {"x": ', '1}\n\n']

    out = await _collect(with_sse_heartbeat(_source(parts, pause=0.35, pause_before={1}), interval=0.1))

    assert PING not in out
    assert "".join(out) == "".join(parts)


async def test_a_ping_is_sent_before_the_first_event():
    out = await _collect(with_sse_heartbeat(_source(['data: {}\n\n'], pause=0.25), interval=0.1))

    assert out[0] == PING
    assert out[-1] == 'data: {}\n\n'


async def test_a_fast_stream_is_left_untouched():
    parts = ['data: {"a": 1}\n\n', 'data: {"b": 2}\n\n']

    assert await _collect(with_sse_heartbeat(_source(parts), interval=5)) == parts


async def test_interval_zero_disables_the_heartbeat():
    parts = ['data: {"a": 1}\n\n']

    out = await _collect(with_sse_heartbeat(_source(parts, pause=0.2), interval=0))

    assert out == parts


async def test_closing_the_stream_closes_the_agent_stream():
    closed = []
    # Référence gardée : sans elle, le ramasse-miettes fermerait la source à
    # la place du relais et le test ne prouverait rien.
    source = _source(['data: {"a": 1}\n\n', 'data: {"b": 2}\n\n'], pause=0.3, pause_before={1}, closed=closed)
    wrapped = with_sse_heartbeat(source, interval=0.1)

    assert await wrapped.__anext__() == 'data: {"a": 1}\n\n'
    await wrapped.aclose()

    assert closed == [True]


def test_the_chat_endpoint_streams_the_heartbeat(monkeypatch):
    from apowerb.auth.dependencies import get_current_user
    from apowerb.routers.adk_runner import router

    monkeypatch.setenv("SSE_HEARTBEAT_SECONDS", "0.1")

    class _User:
        email = "alice@example.com"
        user_id = 1
        role = "USER"
        plan = None

    app = FastAPI()
    app.include_router(router, prefix="/api/adk")

    async def _override():
        return _User()

    app.dependency_overrides[get_current_user] = _override

    async def _no_guard(**_kwargs):
        return None

    with patch("apowerb.routers.adk_runner.get_agent_folder_name", return_value="agent1"), \
         patch("apowerb.core.run_gate.apply_run_guards", _no_guard), \
         patch(
             "apowerb.routers.adk_runner.stream_adk_agent",
             side_effect=lambda **_: _source(['data: {"a": 1}\n\n'], pause=0.35),
         ):
        resp = TestClient(app).post(
            "/api/adk/run_sse",
            headers={"Authorization": "Bearer x"},
            json={
                "agent_name": "agent1",
                "user_id": "alice@example.com",
                "session_id": "session_1",
                "new_message": {"role": "user", "parts": [{"text": "hi"}]},
            },
        )

    assert resp.status_code == 200, resp.text
    assert PING in resp.text
    assert resp.text.endswith('data: {"a": 1}\n\n')
