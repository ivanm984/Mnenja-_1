# app/monitoring.py

"""Monitoring in metrike za aplikacijo."""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable

from prometheus_client import Counter, Histogram, Gauge

# ==========================================
# METRIKE
# ==========================================

# HTTP zahtevki
http_requests_total = Counter(
    "http_requests_total",
    "Skupno število HTTP zahtevkov",
    ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Trajanje HTTP zahtevkov v sekundah",
    ["method", "endpoint"]
)

# PDF procesiranje
pdf_files_processed_total = Counter(
    "pdf_files_processed_total",
    "Število obdelanih PDF datotek"
)

pdf_processing_errors_total = Counter(
    "pdf_processing_errors_total",
    "Število napak pri obdelavi PDF datotek"
)

# AI klici
ai_requests_total = Counter(
    "ai_requests_total",
    "Skupno število klicev na AI (Gemini API)",
    ["model_type"]
)

ai_request_duration_seconds = Histogram(
    "ai_request_duration_seconds",
    "Trajanje AI klicev v sekundah",
    ["model_type"]
)

ai_errors_total = Counter(
    "ai_errors_total",
    "Število napak pri AI klicih",
    ["model_type", "error_type"]
)

# Seje
active_sessions = Gauge(
    "active_sessions",
    "Število aktivnih sej v Redis"
)

sessions_created_total = Counter(
    "sessions_created_total",
    "Skupno število ustvarjenih sej"
)

# Analize
compliance_analyses_total = Counter(
    "compliance_analyses_total",
    "Skupno število izvedenih analiz skladnosti"
)

compliance_requirements_checked_total = Counter(
    "compliance_requirements_checked_total",
    "Skupno število preverjenih zahtev"
)

non_compliant_requirements_total = Counter(
    "non_compliant_requirements_total",
    "Število neskladnih zahtev"
)

# Poročila
reports_generated_total = Counter(
    "reports_generated_total",
    "Število generiranih poročil",
    ["report_type"]
)


# ==========================================
# DEKORATORJI
# ==========================================

def track_ai_call(model_type: str):
    """
    Dekorator za sledenje AI klicem.

    Args:
        model_type: Tip modela ('fast' ali 'powerful')
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ai_requests_total.labels(model_type=model_type).inc()
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                ai_request_duration_seconds.labels(model_type=model_type).observe(duration)
                return result
            except Exception as e:
                error_type = type(e).__name__
                ai_errors_total.labels(model_type=model_type, error_type=error_type).inc()
                raise
        return wrapper
    return decorator


def track_pdf_processing(func: Callable):
    """Dekorator za sledenje obdelavi PDF datotek."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            # Predpostavljamo, da result vsebuje število datotek
            if isinstance(result, tuple) and len(result) >= 3:
                # result[2] je files_manifest
                pdf_files_processed_total.inc(len(result[2]))
            return result
        except Exception as e:
            pdf_processing_errors_total.inc()
            raise
    return wrapper


__all__ = [
    "http_requests_total",
    "http_request_duration_seconds",
    "pdf_files_processed_total",
    "pdf_processing_errors_total",
    "ai_requests_total",
    "ai_request_duration_seconds",
    "ai_errors_total",
    "active_sessions",
    "sessions_created_total",
    "compliance_analyses_total",
    "compliance_requirements_checked_total",
    "non_compliant_requirements_total",
    "reports_generated_total",
    "track_ai_call",
    "track_pdf_processing",
]
