"""
bi/stats_router.py
------------------
Lightweight BI statistics endpoint.

Returns aggregate counts for dashboards and charts so the frontend can
render summary cards without fetching every item.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apowerb.auth.dependencies import get_current_user
from apowerb.users import schemas as user_schemas
from apowerb.bi.charts.core import ChartOrigin
from apowerb.bi.db_stores import DatabaseChartStore, DatabaseDashboardStore
from apowerb.helpers.database import get_db

router = APIRouter(tags=["bi-stats"])


@router.get(
    "/bi/stats",
    summary="BI module statistics",
    description=(
        "Returns the count of dashboards, of charts made on the BI screen "
        "(chart_count) and of charts made inside a conversation (chat_chart_count)."
    ),
)
async def bi_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: user_schemas.User = Depends(get_current_user),
) -> dict:
    owner = str(current_user.email)
    charts = await DatabaseChartStore(db, owner=owner).count_by_origin()
    dashboard_count = await DatabaseDashboardStore(db, owner=owner).count()
    return {
        "dashboard_count": dashboard_count,
        "chart_count": charts[ChartOrigin.BI],
        "chat_chart_count": charts[ChartOrigin.CHAT],
    }
