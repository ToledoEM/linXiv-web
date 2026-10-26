"""The maintenance operations offered in Settings → Server Admin, in panel order."""

from __future__ import annotations

from . import db_backup, duplicates, metadata_fill
from .maintenance import Op

OPS: list[Op] = [duplicates.OP, metadata_fill.OP, db_backup.OP]
