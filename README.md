# 🏗️ Avtomatski API za Skladnost

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Sistem za **avtomatsko preverjanje skladnosti gradbenih projektov** s prostorskimi predpisi slovenskih občin. Uporablja Google Gemini AI za analizo projektne dokumentacije in generiranje poročil o skladnosti.

---

## 📋 Kazalo

- [Funkcionalnosti](#-funkcionalnosti)
- [Arhitektura](#-arhitektura)
- [Tehnologije](#-tehnologije)
- [Namestitev](#-namestitev)
- [Uporaba](#-uporaba)
- [API Dokumentacija](#-api-dokumentacija)
- [Varnost](#-varnost)
- [Razvoj](#-razvoj)
- [Testiranje](#-testiranje)
- [Deployment](#-deployment)

---

## 🎯 Funkcionalnosti

### Faza 1: Ekstrakcija podatkov
- ✅ Nalaganje več PDF dokumentov
- ✅ Avtomatska ekstrakcija besedila in slik
- ✅ AI analiza za pridobitev:
  - Enot urejanja prostora (EUP)
  - Namenske rabe
  - Metapodatkov projekta (investitor, projektant, datum)
  - Ključnih gabaritnih podatkov (dimenzije, faktorji, materiali)

### Faza 2: Analiza skladnosti
- ✅ Primerjava s prostorskimi predpisi občine
- ✅ Generiranje zahtev iz knowledge base
- ✅ AI analiza za vsako zahtevo:
  - Status skladnosti (Skladno/Neskladno/Ni relevantno)
  - Dokazila iz dokumentacije
  - Predlagani ukrepi

### Faza 3: Generiranje poročil
- ✅ Word dokument (.docx) z rezultati analize
- ✅ Excel obrazec (Priloga 10A)
- ✅ Podpora za revizije dokumentacije
- ✅ Sledenje popravkom

### Geospatial funkcionalnosti
- ✅ Interaktivni zemljevid (OpenLayers)
- ✅ Integracija z GURS API:
  - Ortofoto posnetki
  - Kataster parcel
  - Namenska raba
  - Stavbni kataster
- ✅ Iskanje parcel
- ✅ Persistent map state

---

## 🏛️ Arhitektura

```
┌─────────────────┐
│   Frontend      │  (HTML + JavaScript + OpenLayers)
│   (Browser)     │
└────────┬────────┘
         │ HTTP/REST
         ▼
┌─────────────────┐
│   FastAPI       │  (Async REST API)
│   Routes        │
└────────┬────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼
┌─────┐  ┌────────┐ ┌────────┐ ┌────────┐
│Cache│  │Service │ │Database│ │Gemini  │
│Redis│  │ Layer  │ │SQLite  │ │  AI    │
└─────┘  └────────┘ └────────┘ └────────┘
```

### Servisni sloj
- **PDFService**: Obdelava PDF datotek
- **AIService**: AI analize (Gemini API)
- **CacheManager**: Redis predpomnenje
- **DatabaseManager**: Persistentno shranjevanje

---

## 🛠️ Tehnologije

### Backend
- **FastAPI 0.110** - Moderna async spletni okvir
- **Python 3.11+** - Programski jezik
- **Google Gemini AI** - AI analiza dokumentov
  - `gemini-2.5-flash` - hitra ekstrakcija
  - `gemini-2.5-pro` - podrobna analiza
- **Redis** - Predpomnenje sej
- **SQLite/PostgreSQL** - Trajno shranjevanje
- **aiosqlite** - Async database driver

### Frontend
- **HTML5 + Vanilla JS**
- **OpenLayers** - Interaktivni zemljevidi
- **PDF.js** - PDF prikaz

### DevOps
- **Docker + Docker Compose** - Kontejnerizacija
- **Prometheus** - Metrike
- **pytest** - Testiranje

---

## 📦 Namestitev

### Predpogoji
- Python 3.11 ali novejši
- Redis 7.x
- Docker (opcijsko)

### 1. Kloniraj repozitorij
```bash
git clone https://github.com/vase-uporabnisko-ime/Mnenja-_1.git
cd Mnenja-_1
```

### 2. Ustvari virtualno okolje
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ali
venv\Scripts\activate  # Windows
```

### 3. Namesti odvisnosti
```bash
pip install -r requirements.txt
```

### 4. Konfiguracija
```bash
# Kopiraj primer konfiguracije
cp .env.example .env

# Uredi .env in nastavi:
# - GEMINI_API_KEY (pridobi na https://makersuite.google.com/app/apikey)
# - API_KEYS (za avtentikacijo)
# - REDIS_URL
```

### 5. Zaženi Redis
```bash
# Lokalno
redis-server

# Ali z Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### 6. Zaženi aplikacijo
```bash
uvicorn app.main:app --reload
```

Aplikacija bo dostopna na: `http://localhost:8000`

---

## 🐳 Docker namestitev

### Z Docker Compose (priporočeno)
```bash
# Uredi .env datoteko
cp .env.example .env
nano .env

# Zaženi vse storitve
docker-compose up -d

# Preveri statuse
docker-compose ps

# Poglej loge
docker-compose logs -f api
```

Aplikacija bo dostopna na: `http://localhost:8000`

### Samo Docker
```bash
# Build image
docker build -t compliance-api .

# Run container
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name compliance-api \
  compliance-api
```

---

## 🚀 Uporaba

### 1. Pridobi API ključ
Dodaj svoj API ključ v `.env`:
```env
API_KEYS=moj_varni_kljuc_123,drugi_kljuc_456
```

### 2. Uporaba API-ja

#### Ekstrakcija podatkov
```bash
curl -X POST "http://localhost:8000/extract-data" \
  -H "X-API-Key: moj_varni_kljuc_123" \
  -F "pdf_files=@projekt.pdf" \
  -F "municipality_slug=litija"
```

#### Analiza skladnosti
```bash
curl -X POST "http://localhost:8000/analyze-report" \
  -H "X-API-Key: moj_varni_kljuc_123" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "1234567890.123",
    "final_eup_list": ["EUP-01"],
    "final_raba_list": ["SSe"],
    "key_data": {...},
    "selected_ids": []
  }'
```

### 3. Uporaba spletnega vmesnika
Odpri brskalnik na `http://localhost:8000` in sledi navodilom.

---

## 📚 API Dokumentacija

### Interaktivna dokumentacija
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Glavni endpointi

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/` | GET | Spletni vmesnik |
| `/health` | GET | Health check |
| `/extract-data` | POST | Ekstrakcija iz PDF |
| `/analyze-report` | POST | Analiza skladnosti |
| `/confirm-report` | POST | Generiranje poročil |
| `/upload-revision` | POST | Nalaganje popravkov |
| `/saved-sessions` | GET | Seznam sej |
| `/saved-sessions/{id}` | GET | Podrobnosti seje |
| `/saved-sessions/{id}` | DELETE | Izbris seje |

### Avtentikacija
Vsi POST/DELETE endpointi zahtevajo `X-API-Key` header:
```
X-API-Key: your_api_key_here
```

---

## 🔒 Varnost

### Implementirane varnostne funkcije
- ✅ **API Key avtentikacija** za vse POST/DELETE zahtevke
- ✅ **CORS** - konfigurirano iz .env (brez wildcards)
- ✅ **Rate limiting** - 10 zahtevkov/minuto (konfigurirano)
- ✅ **Redis z geslom** - zaščiten cache
- ✅ **Validacija velikosti datotek** - max 50MB
- ✅ **Input sanitizacija** - Pydantic validacija
- ✅ **Structured logging** - audit trail

### Produkcijska varnost
```env
# .env za produkcijo
DEBUG=false
ALLOWED_ORIGINS=https://vasa-domena.si
REDIS_URL=redis://:mocno_geslo@redis:6379/0
API_KEYS=generiran_varni_kljuc_123
RATE_LIMIT_PER_MINUTE=5
```

---

## 👨‍💻 Razvoj

### Struktura projekta
```
Mnenja-_1/
├── app/
│   ├── main.py              # FastAPI aplikacija
│   ├── routes.py            # HTTP endpointi
│   ├── config.py            # Konfiguracija
│   ├── middleware.py        # Auth middleware
│   ├── services/            # Poslovna logika
│   │   ├── pdf_service.py
│   │   └── ai_service.py
│   ├── database.py          # SQLite/Postgres
│   ├── cache.py             # Redis
│   ├── monitoring.py        # Prometheus metrike
│   └── ...
├── tests/                   # Testi
├── static/                  # JS/CSS
├── logs/                    # Aplikacijski logi
├── reports/                 # Generirana poročila
├── .env.example             # Primer konfiguracije
├── requirements.txt         # Python odvisnosti
├── Dockerfile               # Docker image
└── docker-compose.yml       # Multi-container setup
```

### Code style
```bash
# Formatting
black app/ tests/

# Linting
flake8 app/ tests/

# Type checking
mypy app/
```

---

## 🧪 Testiranje

### Zaženi vse teste
```bash
pytest
```

### Specifični testi
```bash
# Samo unit testi
pytest tests/test_auth.py

# Z verbose outputom
pytest -v

# Z code coverage
pytest --cov=app --cov-report=html
```

### Coverage report
```bash
pytest --cov=app --cov-report=term-missing
# HTML report bo v: htmlcov/index.html
```

---

## 🌐 Deployment

### Produkcijska nastavitev

1. **Uredi produkcijsko .env**
```env
DEBUG=false
GEMINI_API_KEY=production_key
DATABASE_URL=postgresql://user:pass@db:5432/compliance
REDIS_URL=redis://:strong_password@redis:6379/0
ALLOWED_ORIGINS=https://app.example.com
API_KEYS=random_secure_key_123
RATE_LIMIT_PER_MINUTE=5
```

2. **Zaženi z Docker Compose**
```bash
docker-compose up -d
```

3. **Nginx reverse proxy**
```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

4. **Monitoring**
```bash
# Prometheus metrics
curl http://localhost:8000/metrics

# Health check
curl http://localhost:8000/health
```

---

## 📊 Metrike in monitoring

Aplikacija izpostavlja Prometheus metrike:
- `http_requests_total` - Število zahtevkov
- `http_request_duration_seconds` - Trajanje zahtevkov
- `ai_requests_total` - Število AI klicev
- `pdf_files_processed_total` - Obdelane PDF datoteke
- `compliance_analyses_total` - Izvedene analize

---

## 🤝 Prispevanje

1. Fork repozitorija
2. Ustvari feature branch (`git checkout -b feature/amazing-feature`)
3. Commit spremembe (`git commit -m 'Add amazing feature'`)
4. Push na branch (`git push origin feature/amazing-feature`)
5. Odpri Pull Request

---

## 📝 Licenca

MIT License - glej [LICENSE](LICENSE) za podrobnosti

---

## 👥 Avtorji

- **Your Name** - *Initial work*

---

## 🙏 Zahvale

- Google Gemini AI
- FastAPI framework
- GURS (Geodetska uprava Republike Slovenije)

---

## 📞 Podpora

Za vprašanja ali težave odprite [GitHub Issue](https://github.com/vase-uporabnisko-ime/Mnenja-_1/issues).

---

**Verzija:** 22.0.0
**Zadnja posodobitev:** 2025-01-21
