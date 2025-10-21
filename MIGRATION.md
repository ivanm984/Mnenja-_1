# SDK Migration Guide

## ⚠️ Pomembno Opozorilo

Trenutno uporabljen SDK **google-generativeai** je **legacy** (zastarela verzija).

**Pomembni datumi:**
- **31. avgust 2025**: Konec podpore za bug fixe
- **30. november 2025**: Popoln konec podpore

## Trenutno Stanje

- **Trenutna verzija**: `google-generativeai==0.8.5` (zadnja stabilna legacy verzija)
- **Status**: Deluje, ampak legacy
- **Priporočilo**: Migriraj na `google-genai` pred avgustom 2025

## Prihodnja Migracija na google-genai

### Zakaj migrirat?

1. **Dolgoročna podpora**: Novi SDK je GA (General Availability) od maja 2025
2. **Novi features**: Live API, Veo, Imagen in drugi modeli
3. **Boljša arhitektura**: Izboljšan API design na podlagi feedbacka

### Kdaj migrirat?

**Priporočilo**: Do **julija 2025** (pred koncem podpore)

### Kako migrirat?

#### 1. Posodobi requirements.txt

```diff
- google-generativeai==0.8.5
+ google-genai>=1.0.0
```

#### 2. Posodobi app/services/ai_service.py

**PREJ (google-generativeai):**
```python
import google.generativeai as genai

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel(
    FAST_MODEL_NAME,
    generation_config={"response_mime_type": "application/json"}
)
```

**ZDAJ (google-genai):**
```python
from google import genai

# Client inicializacija (lahko uporabi GEMINI_API_KEY ali GOOGLE_API_KEY env var)
client = genai.Client(api_key=API_KEY)

model = client.models.generate_content(
    model=FAST_MODEL_NAME,
    contents="...",
    config={
        "response_mime_type": "application/json",
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 8192,
    }
)
```

#### 3. Ključne spremembe

| Staro API | Novo API |
|-----------|----------|
| `genai.configure(api_key=...)` | `client = genai.Client(api_key=...)` |
| `genai.GenerativeModel(model_name)` | `client.models.generate_content(model=...)` |
| `model.generate_content_async(...)` | `await client.aio.models.generate_content(...)` |
| Implicitni API client | Eksplicitni client object |

### Dokumentacija

- **Uradni migration guide**: https://ai.google.dev/gemini-api/docs/migrate
- **PyPI paket**: https://pypi.org/project/google-genai/
- **GitHub repo**: https://github.com/googleapis/python-genai

### Testiranje po migraciji

Po migraciji testiraj vse AI funkcionalnosti:

1. **Ekstrakcija podatkov**: `/extract-data` endpoint
2. **Analiza skladnosti**: `/analyze-compliance` endpoint
3. **Metadata ekstrakcija**: Preveri vse AI klice
4. **Error handling**: Testiraj napake in timeouts

## Vprašanja?

Za pomoč pri migraciji preglej:
- Uradni migration guide: https://ai.google.dev/gemini-api/docs/migrate
- Community članki: https://medium.com/google-cloud/migrating-to-the-new-google-gen-ai-sdk-python-074d583c2350
