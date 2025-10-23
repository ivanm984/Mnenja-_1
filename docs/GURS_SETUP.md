# GURS Setup Guide

Ta dokument povzema osnovne informacije za delo z GURS storitvami v projektu.

## CRS

- **EPSG:3794** – SI-D96/TM (nativni koordinatni sistem za kataster).
- **EPSG:3857** – privzeti projekcijski sistem za odjemalca (spletni zemljevid).

## Storitev URL-ji

| Storitev | URL |
| --- | --- |
| WFS | https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs |
| INSPIRE WMS DTM | https://storitve.eprostor.gov.si/ows-ins-wms/SI.GURS.DTM/ows |

## Razpoložljivi sloji (KN)

- `SI.GURS.KN:PARCELE`
- `SI.GURS.KN:STAVBE`
- `SI.GURS.KN:DELI_STAVB`
- `SI.GURS.KN:ETAZE`

## Opombe

- Vsi zunanji HTTP requesti naj gredo preko FastAPI proxy-ja (`/gurs/proxy`).
- WFS zahteve uporabljajo CRS **EPSG:3794**; transformacija v **EPSG:3857** se izvede na odjemalcu.
