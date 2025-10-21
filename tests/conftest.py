# tests/conftest.py

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
async def client():
    """Async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_api_key():
    """Valid API key for testing."""
    return "demo_key_1"


@pytest.fixture
def auth_headers(valid_api_key):
    """Authorization headers."""
    return {"X-API-Key": valid_api_key}
