# app/schemas.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SaveSessionPayload(BaseModel):
    session_id: str
    data: Dict[str, Any]
    project_name: Optional[str] = None
    summary: Optional[str] = None


class ConfirmReportPayload(BaseModel):
    session_id: str
    excluded_ids: Optional[List[str]] = Field(default_factory=list)
    updated_results_map: Dict[str, Any] = Field(default_factory=dict)
    updated_key_data: Dict[str, Any] = Field(default_factory=dict)
    report_format: str = Field(default="full", description="Format poročila: 'full' ali 'summary'")
    stevilka_zadeve: Optional[str] = Field(default=None, description="Številka zadeve")


class KeyDataPayload(BaseModel):
    """Pydantic model za vsa ključna gabaritna in lokacijska polja."""
    glavni_objekt: str = "Ni podatka v dokumentaciji"
    vrsta_gradnje: str = "Ni podatka v dokumentaciji"
    klasifikacija_cc_si: str = "Ni podatka v dokumentaciji"
    nezahtevni_objekti: str = "Ni podatka v dokumentaciji"
    enostavni_objekti: str = "Ni podatka v dokumentaciji"
    vzdrzevalna_dela: str = "Ni podatka v dokumentaciji"
    parcela_objekta: str = "Ni podatka v dokumentaciji"
    stevilke_parcel_ko: str = "Ni podatka v dokumentaciji"
    velikost_parcel: str = "Ni podatka v dokumentaciji"
    velikost_obstojecega_objekta: str = "Ni podatka v dokumentaciji"
    tlorisne_dimenzije: str = "Ni podatka v dokumentaciji"
    gabariti_etaznost: str = "Ni podatka v dokumentaciji"
    faktor_zazidanosti_fz: str = "Ni podatka v dokumentaciji"
    faktor_izrabe_fi: str = "Ni podatka v dokumentaciji"
    zelene_povrsine: str = "Ni podatka v dokumentaciji"
    naklon_strehe: str = "Ni podatka v dokumentaciji"
    kritina_barva: str = "Ni podatka v dokumentaciji"
    materiali_gradnje: str = "Ni podatka v dokumentaciji"
    smer_slemena: str = "Ni podatka v dokumentaciji"
    visinske_kote: str = "Ni podatka v dokumentaciji"
    odmiki_parcel: str = "Ni podatka v dokumentaciji"
    komunalni_prikljucki: str = "Ni podatka v dokumentaciji"


class AnalysisReportPayload(BaseModel):
    """Glavni model za /analyze-report klic."""
    session_id: str
    final_eup_list: List[str] = Field(default_factory=list)
    final_raba_list: List[str] = Field(default_factory=list)
    key_data: KeyDataPayload
    selected_ids: List[str] = Field(default_factory=list)
    existing_results_map: Dict[str, Any] = Field(default_factory=dict)


class MapStatePayload(BaseModel):
    """Shranjuje stanje pogleda zemljevida (lon/lat + zoom)."""
    center_lon: float
    center_lat: float
    zoom: int


__all__ = ["SaveSessionPayload", "ConfirmReportPayload", "KeyDataPayload", "AnalysisReportPayload", "MapStatePayload"]