# app/services/ai_service.py

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from fastapi import HTTPException
from PIL import Image

import google.generativeai as genai

from ..config import (
    API_KEY,
    FAST_MODEL_NAME,
    GEMINI_ANALYSIS_CONCURRENCY,
    GEN_CFG,
    POWERFUL_MODEL_NAME,
)

logger = logging.getLogger(__name__)

genai.configure(api_key=API_KEY)


class AIService:
    """Servis za AI analize z Gemini API."""

    def __init__(self):
        """Inicializacija AI serviса z modeli."""
        # NOTE: response_mime_type je podprt samo v SDK verziji 0.8.0+
        # Za SDK 0.4.0 se zanašamo na prompt, da AI vrne JSON
        self._fast_json_config = {
            "temperature": 0.0,
            "top_p": 0.9,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
        self._fast_json_model = genai.GenerativeModel(
            FAST_MODEL_NAME, generation_config=self._fast_json_config
        )
        # Remove response_mime_type from GEN_CFG for powerful model
        gen_cfg_without_mime = {k: v for k, v in GEN_CFG.items() if k != "response_mime_type"}
        self._powerful_model = genai.GenerativeModel(
            POWERFUL_MODEL_NAME, generation_config=gen_cfg_without_mime
        )
        self._analysis_semaphore = asyncio.Semaphore(max(1, GEMINI_ANALYSIS_CONCURRENCY))

    async def extract_eup_and_raba(
        self, project_text: str, images: List[Image.Image]
    ) -> Dict[str, List[str]]:
        """
        Pridobi EUP in namensko rabo s hitrim modelom.

        Args:
            project_text: Besedilo projektne dokumentacije
            images: Seznam slik za analizo

        Returns:
            Dict z ključi "eup" in "namenska_raba"
        """
        prompt = f"""
        Analiziraj spodnje besedilo iz projektne dokumentacije in slike. Tvoja naloga je najti dve informaciji:
        1. **Enota Urejanja Prostora (EUP)**: Poišči ustrezne oznake enote urejanja prostora v besedilu ali grafiki (slikah),
           pri čemer je za večino objektov EUP samo eden! Za gradbeno inženirske in linijske objekte pa je lahko EUP več!
        2. **Podrobnejša namenska raba**: Poišči kratice (npr. 'SSe', 'SK') ali druge oznake namenske rabe.
           Enako kot zgoraj je za veliko večino primerov visokegradnje namenska raba samo ena.

        Odgovori SAMO v JSON formatu s ključi "eup" in "namenska_raba".
        Če ne najdeš podatka, vrni prazen seznam.

        Besedilo dokumentacije:
        ---
        {project_text[:40000]}
        ---
        """
        try:
            content_parts = [prompt, *images]
            response = await self._fast_json_model.generate_content_async(content_parts)
            details = json.loads(response.text)
            eup_list = [str(e) for e in details.get("eup", []) if e]
            raba_list = [str(r).upper() for r in details.get("namenska_raba", []) if r]
            return {"eup": eup_list, "namenska_raba": raba_list}
        except Exception as exc:
            logger.error(f"Napaka pri AI ekstrakciji EUP/raba: {exc}", exc_info=True)
            return {"eup": [], "namenska_raba": []}

    async def extract_metadata(self, project_text: str) -> Dict[str, str]:
        """
        Pridobi metapodatke projekta s hitrim modelom.

        Args:
            project_text: Besedilo projektne dokumentacije

        Returns:
            Dict z metapodatki projekta
        """
        prompt = f"""
        Analiziraj besedilo in izlušči naslednje podatke: investitor, investitor_naslov, ime_projekta,
        stevilka_projekta, datum_projekta, projektant in kratek_opis.

        "investitor_naslov" mora vsebovati celoten naslov (ulica, hišna številka, poštna številka in naselje),
        kot je naveden v projektni dokumentaciji.

        Polje "kratek_opis" mora biti 3 do 4 stavki dolg povzetek gradnje, ki vključuje NAJMANJ naslednje
        informacije (če so razvidne): naziv objekta, tlorisne dimenzije, etažnost, višino slemena,
        naklon strehe, smer slemena in vrsto kritine. Če posamezen podatek ni razviden, ni potrebno zapisati da ga ne najdeš.

        Primer kratkega opisa (samo kot slogovna usmeritev – podatke vedno vzemi iz gradiva):
        "Predmet gradnje je stanovanjska hiša, tlorisnih dimenzij 10×8 m. Etažnost objekta je pritličje +
        mansarda (P+M), streha je simetrična dvokapnica v smeri daljše stranice objekta (V–Z) z naklonom
        40°. Višina slemena znaša 10 m, kritina pa je načrtovana kot opečna. Fasada bo v svetlih tonih, z manjšimi temnimi poudarki"

        Odgovori SAMO v JSON formatu z zgoraj naštetimi ključi. Če podatka ni, uporabi "Ni podatka".

        Besedilo dokumentacije:
        ---
        {project_text[:20000]}
        ---
        """
        try:
            response = await self._fast_json_model.generate_content_async(prompt)
            data = json.loads(response.text)
            return {
                "investitor": data.get("investitor", "Ni podatka"),
                "investitor_naslov": data.get("investitor_naslov", "Ni podatka"),
                "ime_projekta": data.get("ime_projekta", "Ni podatka"),
                "stevilka_projekta": data.get("stevilka_projekta", "Ni podatka"),
                "datum_projekta": data.get("datum_projekta", "Ni podatka"),
                "projektant": data.get("projektant", "Ni podatka"),
                "kratek_opis": data.get("kratek_opis", "Ni podatka"),
            }
        except Exception as exc:
            logger.error(f"Napaka pri AI ekstrakciji metapodatkov: {exc}", exc_info=True)
            return {
                "investitor": "Ni podatka",
                "investitor_naslov": "Ni podatka",
                "ime_projekta": "Ni podatka",
                "stevilka_projekta": "Ni podatka",
                "datum_projekta": "Ni podatka",
                "projektant": "Ni podatka",
                "kratek_opis": "Ni podatka",
            }

    async def extract_key_data(
        self, project_text: str, images: List[Image.Image]
    ) -> Dict[str, Any]:
        """
        Pridobi ključne gabaritne podatke s hitrim modelom.

        Args:
            project_text: Besedilo projektne dokumentacije
            images: Seznam slik za analizo

        Returns:
            Dict s ključnimi podatki projekta
        """
        KEY_DATA_PROMPT_MAP = {
            "glavni_objekt": "Natančen opis glavnega objekta (npr. enostanovanjska hiša, gospodarski objekt, opiši funkcijo).",
            "vrsta_gradnje": "Vrsta gradnje (npr. novogradnja, dozidava, nadzidava, rekonstrukcija, sprememba namembnosti).",
            "klasifikacija_cc_si": "CC-SI oziroma druga uradna klasifikacija objekta, če je navedena.",
            "nezahtevni_objekti": "Ali projekt vključuje nezahtevne objekte (navedi katere in njihove dimenzije).",
            "enostavni_objekti": "Ali projekt vključuje enostavne objekte (navedi katere in njihove dimenzije).",
            "vzdrzevalna_dela": "Opiši načrtovana vzdrževalna dela ali manjše rekonstrukcije, če so predvidene.",
            "parcela_objekta": "Številka gradbene/osnovne parcele (npr. 123/5).",
            "stevilke_parcel_ko": "Vse parcele in katastrska občina, ki so del gradnje objekta (npr. 123/5, 124/6, k.o. Litija).",
            "velikost_parcel": "Skupna velikost vseh parcel (npr. 1500 m2).",
            "velikost_obstojecega_objekta": "Velikost in etažnost obstoječih objektov na parceli (npr. hiša 10x8m P+1N, pomožni objekt 5x4m).",
            "tlorisne_dimenzije": "Zunanje tlorisne dimenzije NOVEGA glavnega objekta (npr. 12.0 m x 8.5 m).",
            "gabariti_etaznost": "Navedi etažnost in vertikalni gabarit NOVEGA objekta (npr. K+P+1N+M, višina kolenčnega zidu 1.5 m).",
            "faktor_zazidanosti_fz": "Vrednost faktorja zazidanosti (npr. 0.35 ali FZ=35%).",
            "faktor_izrabe_fi": "Vrednost faktorja izrabe (npr. 0.70 ali FI=0.7).",
            "zelene_povrsine": "Velikost in/ali faktor zelenih površin (npr. 700 m2, FZP=0.47).",
            "naklon_strehe": "Naklon strehe v stopinjah in tip (npr. 40° ali simetrična dvokapnica, 40 stopinj).",
            "kritina_barva": "Material in barva strešne kritine (npr. opečna kritina, temno rdeča).",
            "materiali_gradnje": "Tipični materiali (npr. masivna lesena hiša ali opeka, klasična gradnja).",
            "smer_slemena": "Orientacija slemena glede na plastnice (npr. vzporedno s cesto/vrstnim redom gradnje).",
            "visinske_kote": "Pomembne kote (k.n.t., k.p. pritličja, k. slemena) (npr. k.p. = 345.50 m n.m.).",
            "odmiki_parcel": "Najmanjši in najpomembnejši navedeni odmiki od sosednjih parcelnih meja (npr. Južna meja: 4.5 m; Severna meja: 8.0 m).",
            "komunalni_prikljucki": "Opis priključitve na javno komunalno omrežje (elektrika, vodovod, kanalizacija itd.).",
        }

        prompt_items = "\n".join([f"- **{key}**: {desc}" for key, desc in KEY_DATA_PROMPT_MAP.items()])
        prompt = f"""
        Iz priložene projektne dokumentacije (besedila in slik) natančno izlušči zahtevane podatke.
        Odgovori SAMO v JSON formatu. Če podatka ni, uporabi vrednost "Ni podatka v dokumentaciji".

        ZAHTEVANI PODATKI: {json.dumps(list(KEY_DATA_PROMPT_MAP.keys()))}

        Opisi:
        {prompt_items}

        Besedilo dokumentacije:
        ---
        {project_text[:40000]}
        ---
        """
        try:
            content_parts = [prompt, *images]
            response = await self._fast_json_model.generate_content_async(content_parts)
            key_data = json.loads(response.text)
            return {
                key: key_data.get(key, "Ni podatka v dokumentaciji")
                for key in KEY_DATA_PROMPT_MAP.keys()
            }
        except Exception as exc:
            logger.error(f"Napaka pri AI ekstrakciji ključnih podatkov: {exc}", exc_info=True)
            return {key: "Napaka pri ekstrakciji" for key in KEY_DATA_PROMPT_MAP.keys()}

    async def analyze_compliance(
        self, prompt: str, images: List[Image.Image]
    ) -> str:
        """
        Izvede glavno, kompleksno analizo skladnosti z zmogljivim modelom.

        Args:
            prompt: Prompt za analizo
            images: Seznam slik za analizo

        Returns:
            JSON string z rezultati analize

        Raises:
            HTTPException(500): Če analiza ne uspe
        """
        try:
            content_parts = [prompt, *images]
            async with self._analysis_semaphore:
                response = await self._powerful_model.generate_content_async(content_parts)

            if not response.parts:
                reason = (
                    response.candidates[0].finish_reason
                    if response.candidates
                    else "NEZNAN"
                )
                raise RuntimeError(f"Gemini ni vrnil veljavnega odgovora. Razlog: {reason}")

            return "".join(part.text for part in response.parts)
        except Exception as exc:
            logger.error(f"Napaka pri AI analizi skladnosti: {exc}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Gemini napaka pri analizi: {str(exc)}"
            ) from exc

    @staticmethod
    def parse_ai_response(
        response_text: str, expected_zahteve: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Parsira AI odgovor in vrne slovar rezultatov.

        Args:
            response_text: JSON odgovor od AI
            expected_zahteve: Seznam pričakovanih zahtev

        Returns:
            Dict[zahteva_id -> rezultat]

        Raises:
            HTTPException(500): Če JSON ni veljaven
        """
        clean = re.sub(r"```(json)?", "", response_text, flags=re.IGNORECASE).strip()
        try:
            data = json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.error(f"Neveljaven JSON iz AI: {exc}\nOdgovor:\n{response_text[:500]}")
            raise HTTPException(
                status_code=500,
                detail=f"Neveljaven JSON iz AI: {exc}\nOdgovor:\n{response_text[:500]}"
            ) from exc

        if not isinstance(data, list):
            raise HTTPException(
                status_code=500,
                detail="AI ni vrnil seznama objektov v JSON formatu."
            )

        results_map: Dict[str, Dict[str, Any]] = {}
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                results_map[item["id"]] = item

        # Dodaj manjkajoče zahteve
        for z in expected_zahteve:
            if z["id"] not in results_map:
                results_map[z["id"]] = {
                    "id": z["id"],
                    "obrazlozitev": "AI ni uspel generirati odgovora.",
                    "evidence": "—",
                    "skladnost": "Neznano",
                    "predlagani_ukrep": "Ročno preverjanje.",
                }

        return results_map


# Singleton instance
ai_service = AIService()

__all__ = ["AIService", "ai_service"]
