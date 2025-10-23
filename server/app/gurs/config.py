"""Configuration constants for GURS integrations."""

from typing import Final

WFS_URL: Final[str] = "https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs"
INSPIRE_WMS_DTM_URL: Final[str] = (
    "https://storitve.eprostor.gov.si/ows-ins-wms/SI.GURS.DTM/ows"
)

LAYERS: Final[dict[str, str]] = {
    "PARCELE": "SI.GURS.KN:PARCELE",
    "STAVBE": "SI.GURS.KN:STAVBE",
    "DELI_STAVB": "SI.GURS.KN:DELI_STAVB",
    "ETAZE": "SI.GURS.KN:ETAZE",
}

EPSG_3794: Final[str] = "EPSG:3794"
DEFAULT_CLIENT_SRS: Final[str] = "EPSG:3857"
