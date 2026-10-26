"""The maintenance operations offered in Settings → Server Admin, in panel order."""

from __future__ import annotations

from . import duplicates, metadata_fill
from .maintenance import Op

OPS: list[Op] = [duplicates.OP, metadata_fill.OP]
