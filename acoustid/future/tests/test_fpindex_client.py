import pytest

pytestmark = pytest.mark.asyncio


async def test_foo() -> None:
    assert 1 == 1
