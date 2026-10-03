"""Types shared across modules. Money is always a signed integer number of paise."""

from __future__ import annotations

from dataclasses import dataclass

Paise = int


@dataclass(frozen=True)
class InputStatus:
    """Whether one declared input of a gold table is complete, judged by its own source.

    Each source proves completeness differently: a partner feed by its published version, a
    database by its transaction cut. The publish gate only reads the verdict.
    """

    name: str
    complete: bool
    detail: str = ""
