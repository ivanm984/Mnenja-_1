# Popravek: PDF Upload napaka

## 🐛 Problem

Pri nalaganju PDF datotek je prihajalo do napake:
```
Napaka: 400: Ni bilo mogoče prebrati nobene PDF datoteke.
```

## 🔍 Vzrok

**Glavni vzrok**: `UploadFile` objekti iz FastAPI niso bili uporabni v ozadnji nalogi (`BackgroundTasks`).

### Tehnična razlaga:
1. Endpoint `/extract-data` je validiral PDF datoteke z `validate_pdf_upload()` 
2. Po validaciji so bili `UploadFile` objekti poslani v `BackgroundTasks`
3. Ko se je ozadnja naloga izvajala, je bila HTTP zahteva že zaključena
4. File stream v `UploadFile` objektih je bil zaprt
5. Poskus branja datotek v `PDFService.process_pdf_files()` je vrnil prazne datoteke (0 bytov)
6. Ker nobena datoteka ni vsebovala besedila, je prišlo do napake

## ✅ Rešitev

### 1. Refaktoriran `/extract-data` endpoint (`app/routes.py`)

**Pred popravkom:**
```python
# Validacija datotek
for upload in pdf_files:
    await validate_pdf_upload(upload, MAX_PDF_SIZE_BYTES)

# Pošlji UploadFile objekte v ozadje
background_tasks.add_task(
    _process_extract_data_background,
    session_id,
    pdf_files,  # ❌ Ti objekti ne bodo več uporabni!
    page_overrides,
    municipality_slug
)
```

**Po popravku:**
```python
# Validacija in shranjevanje v začasne datoteke
temp_files_data = []
for upload in pdf_files:
    await validate_pdf_upload(upload, MAX_PDF_SIZE_BYTES)
    await upload.seek(0)
    
    # Preberi celotno datoteko
    content = await upload.read()
    
    # Shrani v začasno datoteko
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_file.write(content)
    temp_file.close()
    
    temp_files_data.append((
        Path(temp_file.name),
        upload.filename,
        upload.content_type
    ))

# Pošlji poti do začasnih datotek v ozadje
background_tasks.add_task(
    _process_extract_data_background,
    session_id,
    temp_files_data,  # ✅ Poti do datotek so vedno dostopne!
    page_overrides,
    municipality_slug
)
```

### 2. Nova metoda v `PDFService` (`app/services/pdf_service.py`)

Dodana metoda `process_pdf_files_from_paths()`:
- Sprejme seznam `(temp_path, filename, content_type)`
- Dela direktno z datotečnimi potmi namesto `UploadFile` objekti
- Boljša obravnava napak z podrobnimi sporočili

```python
@staticmethod
async def process_pdf_files_from_paths(
    temp_files_data: List[Tuple[Path, str, str]],
    page_overrides: Dict[str, str],
    session_id: str,
) -> Tuple[str, List, List[Dict]]:
    """Obdela PDF datoteke iz začasnih poti."""
    # ... procesiranje datotek iz poti
```

### 3. Izboljšan `stream_upload_to_tempfile` (`app/files.py`)

- Dodano podrobno logiranje za debugging:
  - Katera datoteka se procesira
  - Koliko chunkov je bilo prebranih
  - Opozorilo če je datoteka prazna (0 bytov)
- Boljša obravnava seek operacij na različnih objektih

### 4. Izboljšan frontend error handling (`app/modern_frontend.html`)

**Pred popravkom:**
```javascript
const response = await fetch('/extract-data', { method: 'POST', body: formData });
if (!response.ok) throw new Error('API napaka'); // ❌ Generično sporočilo
```

**Po popravku:**
```javascript
const response = await fetch('/extract-data', { method: 'POST', body: formData });
if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'API napaka' }));
    throw new Error(errorData.detail || 'API napaka'); // ✅ Prikaže pravo napako
}
```

## 🧪 Testiranje

### Preverite, da deluje:

1. **Upload PDF datotek**:
   ```bash
   # Aplikacija mora uspešno procesirati PDF datoteke
   # Prej: Napaka "Ni bilo mogoče prebrati nobene PDF datoteke"
   # Zdaj: Uspešno ekstrahira besedilo in metapodatke
   ```

2. **Preveri logs**:
   ```bash
   # Logs naj prikazujejo:
   [session_id] Začenjam validacijo in shranjevanje N PDF datotek...
   [session_id] ✓ filename.pdf: validiran in shranjen (X.XX MB)
   [session_id] ✓ Vse PDF datoteke so veljavne in shranjene
   [session_id] Procesiranje datoteke: filename.pdf
   [session_id] Prebral N chunkov, skupaj X bytov
   ```

3. **Preveri cleanup**:
   ```bash
   # Začasne datoteke morajo biti počiščene po procesiranju
   # Preveri: /tmp/ ne sme vsebovati starih začasnih PDF-jev
   ```

## 📋 Spremenjene datoteke

- `app/routes.py` - Refaktoriran endpoint in ozadnja naloga
- `app/services/pdf_service.py` - Nova metoda za procesiranje iz poti
- `app/files.py` - Izboljšan logging in error handling
- `app/modern_frontend.html` - Boljši prikaz napak

## 🎯 Rezultat

✅ PDF upload zdaj deluje zanesljivo  
✅ Boljša diagnostika napak z podrobnimi logi  
✅ Pravilno čiščenje začasnih datotek  
✅ Frontend prikazuje specifične napake namesto generičnih sporočil  
✅ Robustnejša obravnava file stream-ov in seek operacij  

## 🔐 Varnost

- Validacija datotek se še vedno izvaja PRED procesiranjem
- Začasne datoteke se hranijo z varnimi imeni
- Cleanup začasnih datotek se izvede tudi v primeru napak
- Vsi error path-i so obravnavani

## 📚 Reference

- FastAPI BackgroundTasks: https://fastapi.tiangolo.com/tutorial/background-tasks/
- Issue: UploadFile objekti niso uporabni po zaključku HTTP zahteve
- Rešitev: Pre-load datotek v temp files pred ozadno nalogo
