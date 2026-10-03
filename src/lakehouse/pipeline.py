"""Entry points for the surrounding plumbing.

These are stubs: the brief invites stubbing everything around the hard parts. Each docstring
states what the real job guarantees. The hard parts they call are real:

- `ingestion.partner_files`: which version of a partner delivery is current.
- `ingestion.transaction_cut`: silver advances to a consistent, complete cut of each database.
- `publishing.publish_gate`: gold publishes only when complete and tied to the paise.
"""

from __future__ import annotations

from datetime import date


def pull_api_incrementally(endpoint: str) -> None:
    """Pull a third-party API into the landing zone.

    Saves each raw response before parsing; pages by key, never by offset; re-reads a lookback
    window on every pull and deduplicates, so records that become visible late are not lost;
    and runs a periodic full sweep, because an API gives no completeness signal of its own.
    """
    raise NotImplementedError


def snapshot_ops_sheet(sheet_id: str) -> None:
    """Keep every read of an Ops sheet as a version. A changed GL mapping waits for approval."""
    raise NotImplementedError


def load_clickhouse_copy(table: str, snapshot_id: int) -> None:
    """Load one published version into a staging table, then swap it in with EXCHANGE TABLES."""
    raise NotImplementedError


def load_aurora_copy(table: str, snapshot_id: int) -> None:
    """Load one published version into a staging table, then rename it in one transaction."""
    raise NotImplementedError


def tag_month_end(table: str, month_end: date) -> None:
    """Tag the published snapshot at month-end, so an auditor can reproduce the figure."""
    raise NotImplementedError
