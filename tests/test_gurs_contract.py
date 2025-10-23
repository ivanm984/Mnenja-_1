import pytest
import httpx

WFS_URL = "https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs"


@pytest.mark.asyncio
async def test_gurs_wfs_capabilities_contains_parcele():
    params = {
        "service": "WFS",
        "request": "GetCapabilities",
        "version": "2.0.0",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(WFS_URL, params=params)

    assert response.status_code == 200
    assert "SI.GURS.KN:PARCELE" in response.text
