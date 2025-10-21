# tests/test_health.py

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health endpoint returns OK status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_homepage(client):
    """Test homepage loads."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
