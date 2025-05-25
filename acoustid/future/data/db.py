from typing import NewType

from sqlalchemy.ext.asyncio import AsyncConnection

FingerprintDB = NewType("FingerprintDB", AsyncConnection)
