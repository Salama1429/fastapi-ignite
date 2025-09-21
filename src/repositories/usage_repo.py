"""Repository helpers for usage tracking."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UsageRepo:
    """Provides aggregation helpers for usage counters."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment_message(
        self, tenant_id: UUID, project_id: UUID, tokens_in: int, tokens_out: int
    ) -> None:
        query = text(
            """
            INSERT INTO usage_daily (date, tenant_id, project_id, messages_count, tokens_in, tokens_out)
            VALUES (:d, :t, :p, 1, :ti, :to)
            ON CONFLICT (date, tenant_id, project_id)
            DO UPDATE SET
              messages_count = usage_daily.messages_count + 1,
              tokens_in = usage_daily.tokens_in + EXCLUDED.tokens_in,
              tokens_out = usage_daily.tokens_out + EXCLUDED.tokens_out
            """
        )
        await self.session.execute(
            query,
            {
                "d": date.today(),
                "t": str(tenant_id),
                "p": str(project_id),
                "ti": tokens_in,
                "to": tokens_out,
            },
        )
        await self.session.flush()

    async def messages_in_period(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> int:
        """Return the number of messages recorded during the billing period."""

        query = text(
            """
            SELECT COALESCE(SUM(messages_count), 0) AS messages
            FROM usage_daily
            WHERE tenant_id = :t
              AND date >= :start
              AND date < :end
            """
        )
        result = await self.session.execute(
            query,
            {
                "t": str(tenant_id),
                "start": period_start,
                "end": period_end,
            },
        )
        value = result.scalar_one()
        return int(value or 0)

    async def chars_uploaded_for_project_in_period(
        self,
        tenant_id: UUID,
        project_id: UUID,
        period_start: date,
        period_end: date,
    ) -> int:
        """Return uploaded characters for a project within the billing window."""

        query = text(
            """
            SELECT COALESCE(SUM(chars_uploaded), 0)
            FROM usage_daily
            WHERE tenant_id = :t
              AND project_id = :p
              AND date >= :start
              AND date < :end
            """
        )
        result = await self.session.execute(
            query,
            {
                "t": str(tenant_id),
                "p": str(project_id),
                "start": period_start,
                "end": period_end,
            },
        )
        value = result.scalar_one()
        return int(value or 0)

    async def chars_uploaded_in_period(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> int:
        """Return uploaded characters across all projects for the billing window."""

        query = text(
            """
            SELECT COALESCE(SUM(chars_uploaded), 0)
            FROM usage_daily
            WHERE tenant_id = :t
              AND date >= :start
              AND date < :end
            """
        )
        result = await self.session.execute(
            query,
            {
                "t": str(tenant_id),
                "start": period_start,
                "end": period_end,
            },
        )
        value = result.scalar_one()
        return int(value or 0)

    async def record_upload_chars(
        self, tenant_id: UUID, project_id: UUID, char_count: int
    ) -> None:
        """Increment the upload character counter for the current day."""

        query = text(
            """
            INSERT INTO usage_daily (date, tenant_id, project_id, messages_count, tokens_in, tokens_out, chars_uploaded)
            VALUES (:d, :t, :p, 0, 0, 0, :chars)
            ON CONFLICT (date, tenant_id, project_id)
            DO UPDATE SET
              chars_uploaded = usage_daily.chars_uploaded + EXCLUDED.chars_uploaded
            """
        )
        await self.session.execute(
            query,
            {
                "d": date.today(),
                "t": str(tenant_id),
                "p": str(project_id),
                "chars": char_count,
            },
        )
        await self.session.flush()

    async def month_totals(self, tenant_id: UUID, year: int, month: int) -> int:
        """Backwards-compatible calendar-month message total."""

        query = text(
            """
            SELECT COALESCE(SUM(messages_count), 0) AS messages
            FROM usage_daily
            WHERE tenant_id = :t
              AND date >= make_date(:y, :m, 1)
              AND date < (make_date(:y, :m, 1) + INTERVAL '1 month')
            """
        )
        result = await self.session.execute(
            query, {"t": str(tenant_id), "y": year, "m": month}
        )
        value = result.scalar_one()
        return int(value or 0)
