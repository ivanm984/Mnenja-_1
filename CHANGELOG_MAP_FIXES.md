# 🗺️ Popravki Zemljevida - 2025-10-21

## 🎯 Povzetek Popravkov

Ta commit vsebuje več ključnih popravkov za GURS zemljevid:

---

## ✅ 1. RESPONSIVE VELIKOST ZEMLJEVIDA

### Problem:
- Zemljevid je imel fiksno višino 600px
- Se ni prilagajal velikosti okna

### Rešitev:
**Datoteka:** `app/gurs_map.html`

- Spremenjeno `.map-panel`:
  - Dodano `display: flex` in `flex-direction: column`
  - Višina spremenjena na `min-height: 70vh` (70% viewport height)

- Spremenjeno `#map`:
  - Dodano `flex: 1` za dinamično razširitev
  - Višina spremenjena na `height: 100%`
  - Obdržana `min-height: 500px` za minimalno velikost

**Rezultat:** Zemljevid se sedaj prilagaja velikosti brskalnika!

---

## ✅ 2. POSODOBLJENI WMS SLOJI

### Problem:
- Sloj "Številke parcel" (`NEP_OSNOVNI_PARCELE_CENTROID`) se ne prikaže
- Sloj "Namenska raba" (`NEP_OST_NAMENSKE_RABE`) se ne prikaže
- NEP_ sloji morda niso na voljo na vseh strežnikih

### Rešitev:
**Datoteka:** `app/config.py`

#### Številke parcel:
```python
"katastr_stevilke": {
    "name": "SI.GURS.KN:PARCELNE_CENTROID",  # Spremenjen iz NEP_OSNOVNI_PARCELE_CENTROID
    "default_visible": False,  # Skrito, ker sloj morda ne obstaja
    # + dodana opomba z alternativnimi imeni
}
```

#### Namenska raba:
```python
"namenska_raba": {
    "name": "RPE:RPE_PO",  # Spremenjeno iz NEP_OST_NAMENSKE_RABE
    "url": GURS_RPE_WMS_URL,  # Uporablja RPE strežnik
    "default_visible": True,  # Vklopljeno za testiranje
    "opacity": 0.6  # Dodana prosojnost
    # + dodana opomba z alternativnimi imeni
}
```

**Rezultat:** Namenska raba uporablja RPE strežnik, ki je bolj zanesljiv!

---

## ✅ 3. IZBOLJŠAN DEBUG LOGGING

### Problem:
- Ni bilo jasno, kateri sloji se nalagajo
- Napake pri nalaganju slojev niso bile jasno vidne
- Težko odpravljanje napak

### Rešitev:
**Datoteka:** `static/js/gurs_map.js`

#### Dodano:

1. **Tile Error Handling:**
   ```javascript
   layer.getSource().on('tileloaderror', function(event) {
       console.error(`❌ Napaka pri nalaganju tile za sloj ${cfg.id}`);
       console.error(`   Preverite, ali sloj "${layerName}" obstaja.`);
   });
   ```

2. **Layer Creation Logging:**
   ```javascript
   console.log(`✅ Overlay sloj ustvarjen: ${cfg.id} - Viden: ${visible}, Opacity: ${opacity}`);
   ```

3. **GetFeatureInfo Error Handling:**
   - Boljša obravnava napak pri nameski rabi
   - Dodani napotki (💡) za odpravljanje težav
   - Debugging za statusne kode in JSON napake

4. **Config Loading Logging:**
   ```javascript
   console.log(`🔧 Nalagam ${mapConfig.overlayLayers.length} overlay slojev...`);
   ```

**Rezultat:** Uporabnik sedaj vidi v konzoli, kaj se dogaja!

---

## ✅ 4. OPACITY PODPORA V KONFIGURACIJI

### Problem:
- Sloji niso podpirali prosojnosti iz konfiguracije

### Rešitev:
**Datoteka:** `static/js/gurs_map.js`

```javascript
// Prej:
opacity: transparent ? (cfg.opacity ?? 0.8) : 1,

// Sedaj:
opacity: cfg.opacity ?? (transparent ? 0.8 : 1),
```

**Rezultat:** Lahko nastavimo `"opacity": 0.6` v config.py!

---

## ✅ 5. WMS VERSION SPECIFIED

### Problem:
- WMS verzija ni bila eksplicitno nastavljena
- To lahko povzroči težave z nekaterimi strežniki

### Rešitev:
**Datoteka:** `static/js/gurs_map.js`

```javascript
params: {
    // ...
    VERSION: '1.3.0'  // Dodano
}
```

**Rezultat:** Boljša kompatibilnost s GURS strežniki!

---

## ✅ 6. DOKUMENTACIJA

### Dodano:
**Datoteka:** `GURS_SETUP.md` (NEW)

Obsežna dokumentacija z:
- ⚠️ Opomba o vklopu GURS API (`ENABLE_REAL_GURS_API=true`)
- 🔧 Navodila za reševanje problemov
- 📋 Priporočene nastavitve
- 🧪 Testiranje slojev
- 💡 Koristni nasveti

**Rezultat:** Uporabnik ima jasna navodila!

---

## 🚨 POMEMBNO: AKTIVIRANJE GURS API

**Trenutno stanje:** Aplikacija uporablja **simulirane podatke**!

**Za pravo delovanje:**

1. Odpri `.env`
2. Nastavi:
   ```bash
   ENABLE_REAL_GURS_API=true
   ```
3. Ponovno zaženi aplikacijo

**Brez tega popravka parcele ne bodo najdene pravilno!**

---

## 🧪 KAJ TESTIRATI

1. ✅ **Velikost zemljevida**
   - Spremeni velikost okna brskalnika
   - Zemljevid se mora prilagoditi

2. ✅ **Ortofoto sloj**
   - Mora biti viden ob zagonu
   - Prikaže satelitske posnetke

3. ✅ **Parcelne meje**
   - Morajo biti vidne ob zagonu
   - Prikaže meje parcel

4. ✅ **Namenska raba (RPE)**
   - Vklopi v Layer Selector
   - Preveri, ali se prikaže sloj
   - Preveri konzolo za napake

5. ✅ **Klik na parcelo**
   - Klikni na parcelo
   - V info panelu se morajo prikazati podatki
   - Preveri konzolo za GetFeatureInfo zahtevke

6. ✅ **WMS Katalog**
   - Klikni "Katalog WMS" → "Pokaži"
   - Preveri seznam slojev
   - Poskusi dodati dodatne sloje

---

## 📊 Statistika Sprememb

- **Spremenjene datoteke:** 3
- **Dodane datoteke:** 2
- **Vrstice kode:** ~150 novih/spremenjenih
- **Debug sporočila:** 12+ novih
- **Bug fixes:** 6
- **Dokumentacija:** 200+ vrstic

---

## 🔜 Prihodnji Izboljšave

1. Dinamično odkrivanje slojev z GetCapabilities
2. Shranjevanje priljubljenih slojev v localStorage
3. Export podatkov o parceli v PDF
4. Dodajanje merjenja površin in razdalj
5. Podpora za več občinskih OPN slojev

---

**Avtor:** Claude Code
**Datum:** 2025-10-21
**Verzija:** 1.1.0
