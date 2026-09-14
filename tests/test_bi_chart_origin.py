"""Un graphique créé dans le chat ne se confond plus avec un graphique BI.

Signalé depuis l'application le 14/09/2026 : l'écran BI affichait
« 128 Charts » à une personne qui en avait fait une dizaine. Le compteur
prenait toutes les lignes `chart`, or l'agent en persiste une à chaque
graphique montré dans une conversation.

Règles retenues :
- l'origine est fixée à la création : écran BI (API REST) → ``bi``,
  outil de l'agent → ``chat`` ; elle ne change plus ensuite, même si le
  graphique est posé sur un tableau de bord ;
- une ligne antérieure, sans origine, se classe ainsi : ``bi`` si son nom
  est identique à son titre (l'assistant de l'écran BI pose name = title),
  ``chat`` sinon (l'agent donne un nom technique). La première écriture
  fige ce classement, pour qu'un renommage ne le fasse pas basculer.
"""

import contextlib
from types import SimpleNamespace

import pytest

import apowerb.bi.db_stores as db_stores
import apowerb.tools_store.portfolio.business_intelligence as bi
from apowerb.bi import stats_router
from apowerb.bi.charts import router as charts_router
from apowerb.bi.charts.core import Chart, ChartOrigin, ChartType, DataSource, effective_origin
from apowerb.bi.charts.schemas import ChartCreateRequest, ChartResponse, DataSourceSchema
from apowerb.bi.charts.service import InMemoryChartStore

OWNER = "test@example.com"


def _request(name="ventes_par_region", title="Ventes par région"):
    return ChartCreateRequest(
        name=name,
        title=title,
        chart_type=ChartType.BAR,
        source=DataSourceSchema(query="SELECT 1"),
        organization_id="org1",
    )


class TestLegacyRule:
    def test_name_equal_to_title_is_bi(self):
        assert effective_origin("Ventes", "Ventes", None) is ChartOrigin.BI

    def test_technical_name_is_chat(self):
        assert effective_origin("ventes_bar", "Ventes", None) is ChartOrigin.CHAT

    def test_a_recorded_origin_wins_over_the_rule(self):
        assert effective_origin("Ventes", "Ventes", "chat") is ChartOrigin.CHAT
        assert effective_origin("ventes_bar", "Ventes", "bi") is ChartOrigin.BI


class TestOriginAtCreation:
    @pytest.mark.asyncio
    async def test_the_bi_screen_creates_bi_charts(self):
        captured = {}

        class Svc:
            async def create(self, body, **kwargs):
                captured.update(kwargs)
                return Chart.create(
                    name=body.name, title=body.title, chart_type=body.chart_type,
                    source=DataSource(query="SELECT 1"), organization_id="org1",
                    origin=kwargs.get("origin"),
                )

        response = await charts_router.create_chart(
            _request(), SimpleNamespace(email=OWNER), Svc()
        )

        assert captured["origin"] is ChartOrigin.BI
        assert response.origin is ChartOrigin.BI

    @pytest.mark.asyncio
    async def test_the_agent_tool_creates_chat_charts(self, monkeypatch):
        store = InMemoryChartStore()

        @contextlib.asynccontextmanager
        async def no_db():
            yield None

        monkeypatch.setattr(bi, "_get_session", no_db)
        monkeypatch.setattr(db_stores, "DatabaseChartStore", lambda db, owner=None: store)

        result = await bi._async_create_chart(
            name="Ventes", title="Ventes", chart_type="bar", query="",
            organization_id="org1", project_id="p", description="",
            refresh_interval=0, time_field="", group_by="", aggregation="",
            connection_config_id="", config="", owner_email=OWNER,
        )

        chart = await store.get(result["chart_id"])
        # name == title here on purpose: the recorded origin beats the rule.
        assert chart.origin is ChartOrigin.CHAT
        assert ChartResponse.from_domain(chart).origin is ChartOrigin.CHAT


class FakeRow(SimpleNamespace):
    pass


class FakeDb:
    def __init__(self, row=None, rows=()):
        self.row, self.rows, self.added = row, list(rows), []

    async def get(self, _model, _id):
        return self.row

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        pass

    async def execute(self, _query):
        return SimpleNamespace(all=lambda: self.rows)


class TestStore:
    @pytest.mark.asyncio
    async def test_a_legacy_row_keeps_its_class_when_renamed(self):
        old = FakeRow(
            status="active", owner=OWNER, name="Ventes",
            config={"name": "Ventes", "title": "Ventes"},
        )
        db = FakeDb(row=old)
        renamed = Chart.create(
            name="Ventes", title="Ventes 2026", chart_type=ChartType.BAR,
            source=DataSource(query="SELECT 1"), organization_id="org1",
        )

        await db_stores.DatabaseChartStore(db, owner=OWNER).save(renamed)

        assert old.config["origin"] == "bi"

    @pytest.mark.asyncio
    async def test_counts_split_bi_and_chat(self):
        db = FakeDb(rows=[
            ("Ventes", {"title": "Ventes"}),                        # ancienne, BI
            ("ventes_bar", {"title": "Ventes"}),                    # ancienne, chat
            ("ventes_bar-1a2b3c", {"title": "Ventes"}),             # ancienne, chat
            ("CA", {"title": "CA", "origin": "chat"}),              # agent, nom = titre
            ("ca_mensuel", {"title": "CA", "origin": "bi"}),        # écran BI
            ("vide", None),                                         # config absente
        ])

        counts = await db_stores.DatabaseChartStore(db, owner=OWNER).count_by_origin()

        assert counts == {ChartOrigin.BI: 2, ChartOrigin.CHAT: 4}


class TestStats:
    @pytest.mark.asyncio
    async def test_the_kpi_counts_bi_charts_and_reports_chat_ones_apart(self, monkeypatch):
        class Charts:
            def __init__(self, db, owner=None):
                pass

            async def count_by_origin(self):
                return {ChartOrigin.BI: 9, ChartOrigin.CHAT: 119}

        class Dashboards:
            def __init__(self, db, owner=None):
                pass

            async def count(self):
                return 3

        monkeypatch.setattr(stats_router, "DatabaseChartStore", Charts)
        monkeypatch.setattr(stats_router, "DatabaseDashboardStore", Dashboards)

        stats = await stats_router.bi_stats(None, SimpleNamespace(email=OWNER))

        assert stats == {"dashboard_count": 3, "chart_count": 9, "chat_chart_count": 119}
