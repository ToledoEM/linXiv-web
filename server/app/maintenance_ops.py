"""The maintenance operations offered in Settings → Server Admin, in panel order."""

from __future__ import annotations

from . import db_backup, duplicates, metadata_fill, pdf_check
from .maintenance import Op

OPS: list[Op] = [duplicates.OP, metadata_fill.OP, pdf_check.OP, db_backup.OP]
