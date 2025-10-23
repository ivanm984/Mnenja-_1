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
async def test_save_session_roundtrip(client):
    """Seja se lahko shrani, prebere in izbriše."""
    session_id = "test-session-roundtrip"
    payload = {
        "session_id": session_id,
        "project_name": "Testna analiza",
        "summary": "0 zahtev: 0 skladnih, 0 neskladnih, 0 ni relevantno",
        "data": {
            "results_map": {},
            "resultsMap": {},
            "zahteve": [],
            "metadata": {},
            "key_data": {},
            "eup": [],
            "namenska_raba": [],
            "stevilka_zadeve": "TEST-1"
        }
    }

    save_response = await client.post("/save-session", json=payload)
    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["session_id"] == session_id

    list_response = await client.get("/saved-sessions")
    assert list_response.status_code == 200
    sessions = list_response.json().get("sessions", [])
    assert any(session.get("session_id") == session_id for session in sessions)

    delete_response = await client.delete(f"/saved-sessions/{session_id}")
    assert delete_response.status_code == 200


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
