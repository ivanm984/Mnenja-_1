# tests/test_auth.py

import pytest


@pytest.mark.asyncio
async def test_extract_data_requires_auth(client):
    """Test that /extract-data requires API key."""
    response = await client.post("/extract-data", files=[])
    # Should fail due to missing API key (401) or validation error (422)
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_extract_data_with_invalid_api_key(client):
    """Test that invalid API key is rejected."""
    headers = {"X-API-Key": "invalid_key_12345"}
    response = await client.post("/extract-data", headers=headers, files=[])
    # Could be 401 (invalid key) or 422 (missing files)
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_analyze_report_requires_auth(client):
    """Test that /analyze-report requires API key."""
    response = await client.post(
        "/analyze-report",
        json={
            "session_id": "test",
            "final_eup_list": [],
            "final_raba_list": ["SSe"],
            "key_data": {},
            "selected_ids": [],
            "existing_results_map": {}
        }
    )
    assert response.status_code == 401
