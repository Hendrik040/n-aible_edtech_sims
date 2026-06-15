"""Regression test for #518: simulation deletion must require authentication.

Previously DELETE used an optional-auth dependency and the repository skipped
the ownership check when no user was present, so anyone could delete any
simulation by id.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_delete_simulation_requires_authentication(async_client: AsyncClient):
    # No auth cookie -> must be rejected before any deletion happens.
    resp = await async_client.delete("/api/publishing/simulations/1")
    assert resp.status_code == 401
