import base64
import uuid
from contextvars import ContextVar
from typing import Optional

trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def generate_trace_id() -> str:
    raw_trace_id = uuid.uuid4().bytes
    return base64.b32encode(raw_trace_id).decode("ascii").rstrip("=")


def get_trace_id() -> Optional[str]:
    return trace_id.get()


def initialize_trace_id(value: Optional[str] = None):
    if value is None:
        value = generate_trace_id()
    trace_id.set(value)
