# tests/test_sessions.py

import pytest


@pytest.mark.asyncio
async def test_list_sessions(client):
    """Test listing saved sessions."""
    response = await client.get("/saved-sessions")
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


@pytest.mark.asyncio
async def test_get_nonexistent_session(client):
    """Test getting a session that doesn't exist."""
    response = await client.get("/saved-sessions/nonexistent_id_12345")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_session(client):
    """Test deleting a session that doesn't exist."""
    response = await client.delete("/saved-sessions/nonexistent_id_12345")
    assert response.status_code == 404
