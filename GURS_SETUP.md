# 🗺️ GURS Zemljevid - Navodila za Nastavitev

## ⚠️ POMEMBNO: Vklop GURS API

Aplikacija trenutno uporablja **simulirane podatke** namesto pravih GURS podatkov!

### Kako vklopiti GURS API:

1. **Odpri `.env` datoteko** v root direktoriju projekta
2. **Poišči vrstico:**
   ```bash
   ENABLE_REAL_GURS_API=false
   ```
3. **Spremeni v:**
   ```bash
   ENABLE_REAL_GURS_API=true
   ```
4. **Ponovno zaženi aplikacijo**

---

## 🔧 Pogosti Problemi in Rešitve

### Problem 1: Namenska raba se ne prikaže

**Vzrok:** Sloj namenske rabe je odvisen od občine in lahko ima različna imena.

**Rešitve:**

1. **Vklopi sloj "Namenska raba (RPE)"** vLayer Selector (desno zgoraj na zemljevidu)

2. **Če sloj ne deluje, poskusi z alternativnimi imeni:**

   Odpri `app/config.py` in pri `"namenska_raba"` spremeni `"name"`:

   ```python
   # Opcija 1: RPE prostorski odseki (splošno)
   "name": "RPE:RPE_PO",

   # Opcija 2: NEP sloji (občinsko specifično)
   "name": "NEP_OST_NAMENSKE_RABE",

   # Opcija 3: OPN sloji (specifično za občino)
   "name": "OPN_LITIJA_NAMENSKA_RABA",  # Primer za Litijo
   ```

3. **Preveri WMS Katalog:**
   - Klikni "Katalog WMS" → "Pokaži"
   - Preglej seznam razpoložljivih slojev
   - Poišči sloje z "NAMENSK", "RABA", "OPN" v imenu
   - Dodaj jih dinamično za testiranje

---

### Problem 2: Številke parcel niso vidne

**Vzrok:** Številke parcel lahko:
- Niso ločen WMS sloj
- Imajo drugačno ime sloja
- So prikazane samo pri določenih zoom nivojih

**Rešitve:**

1. **Klikni na parcelo** - številka se prikaže v info panelu na desni

2. **Povečaj zoom** (zoom level 16+) - številke so lahko vidne samo pri večjem zoomu

3. **Preveri WMS Katalog** za alternative:
   - Poišči sloje z "CENTROID", "PARCELE", "STEVILKE" v imenu
   - Dodaj jih dinamično

4. **Spremeni ime sloja** v `app/config.py`:
   ```python
   "katastr_stevilke": {
       "name": "SI.GURS.KN:PARCELNE_CENTROID",  # Ali drug sloj
   }
   ```

---

### Problem 3: Ne najde pravih parcel (WFS)

**Vzrok:**
- GURS API ni vklopljen (`ENABLE_REAL_GURS_API=false`)
- WFS filter uporablja napačno polje

**Rešitve:**

1. **Vklopi GURS API** (glej navodila zgoraj)

2. **Preveri log datoteke:**
   ```bash
   tail -f app.log
   ```
   Poišči napake tipa:
   - `WFS 400 Bad Request`
   - `Filter napaka`
   - `Parcela ni najdena`

3. **Debug mode:**
   V `.env` nastavi:
   ```bash
   DEBUG=true
   ```
   To bo izpisovalo več debug informacij v konzolo.

---

## 📋 Priporočene Nastavitve za Produkcijo

### `.env` datoteka:

```bash
# GURS API
ENABLE_REAL_GURS_API=true
GURS_API_TIMEOUT=30

# Debug (samo za razvoj!)
DEBUG=false

# Map nastavitve
DEFAULT_MAP_CENTER_LON=14.5058  # Ljubljana
DEFAULT_MAP_CENTER_LAT=46.0569
DEFAULT_MAP_ZOOM=14
```

---

## 🧪 Testiranje Slojev

### 1. Preveri GetCapabilities:

```bash
curl "https://ipi.eprostor.gov.si/wms-si-gurs-kn/wms?service=WMS&request=GetCapabilities" \
  -H "User-Agent: Mozilla/5.0" \
  > capabilities.xml
```

Odpri `capabilities.xml` in poišči imena slojev (<Name>...</Name>)

### 2. Testiraj WMS sloj direktno:

```
https://ipi.eprostor.gov.si/wms-si-gurs-kn/wms?
  SERVICE=WMS&
  REQUEST=GetMap&
  VERSION=1.3.0&
  LAYERS=SI.GURS.KN:PARCELE&
  BBOX=46.0,14.0,46.1,14.1&
  WIDTH=800&
  HEIGHT=600&
  FORMAT=image/png&
  CRS=EPSG:4326
```

Vnesi v brskalnik - če vidiš sliko parcel, sloj deluje!

### 3. Testiraj WFS iskanje:

```
https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs?
  service=WFS&
  request=GetFeature&
  version=2.0.0&
  typeName=SI.GURS.KN:PARCELE&
  cql_filter=ST_PARCE='940/1'&
  outputFormat=application/json
```

---

## 📚 Koristne Povezave

- **GURS e-Prostor**: https://www.e-prostor.gov.si/
- **WMS Strežniki**: https://ipi.eprostor.gov.si/
- **Dokumentacija**: https://www.gov.si/teme/geodetska-uprava/

---

## 🛠️ Napredne Nastavitve

### Dodajanje Občinskih Slojev:

Če poznaš ime specifičnega OPN sloja za tvojo občino, ga dodaj v `app/config.py`:

```python
"opn_moja_obcina": {
    "name": "OPN_LITIJA_NAMENSKA_RABA",  # Primer
    "title": "OPN Litija - Namenska raba",
    "description": "Občinski prostorski načrt Litija",
    "url": GURS_WMS_URL,
    "format": "image/png",
    "transparent": True,
    "category": "overlay",
    "default_visible": True,
    "opacity": 0.7
}
```

---

## 💡 Svetujem

1. ✅ **Najprej vklopi** `ENABLE_REAL_GURS_API=true`
2. ✅ **Odpri zemljevid** in preveri, če sloji "Parcelne meje" in "Digitalni ortofoto" delujejo
3. ✅ **Potem dodajaj** dodatne sloje preko WMS Kataloga
4. ✅ **Kopiraj imena** delujočih slojev v `config.py` za trajno uporabo
5. ✅ **Debug mode** uporablji samo za razvoj, ne produkcijo

---

## ❓ Pomoč

Če problemi ostanejo:

1. Preveri **console log** v brskalniku (F12 → Console)
2. Preveri **aplikacijski log** (`tail -f app.log`)
3. Preveri **omrežni promet** (F12 → Network → filtriraj "wms", "wfs")
4. Poglej **odzive strežnika** - ali vračajo 200 OK ali napake (400, 403, 500)?

---

**Zadnja posodobitev:** 2025-10-21
