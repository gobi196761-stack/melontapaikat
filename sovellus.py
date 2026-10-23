"""Sivu asennettavaksi sovellukseksi (web app manifest ja kuvake).

iPhonessa push-ilmoitukset toimivat vain, kun sivu on lisätty Koti-valikkoon ja se
avautuu omana sovelluksenaan (manifestin display: standalone, iOS 16.4+). Androidissa
manifest tuo Chromeen "Asenna sovellus" -valinnan.

Reitit (app.py): /manifest.webmanifest ja /kuvake-<koko>.png (KOOT).
"""

from __future__ import annotations

import functools
import io
import json
from pathlib import Path

KOOT = (180, 192, 512)   # 180 = apple-touch-icon, 192 ja 512 = manifest
LOGO = Path(__file__).with_name("logo.jpg")
TEEMA = "#0b62c4"


def manifest(kieli: str = "fi") -> str:
    en = kieli == "en"
    return json.dumps({
        "name": "Paddling conditions" if en else "Melontatilanne",
        "short_name": "Paddling" if en else "Melonta",
        "description": ("Paddling spots in Northern Finland ranked by today's water levels" if en
                        else "Pohjois-Suomen melontapaikat päivän vesitilanteen mukaan"),
        "lang": kieli, "start_url": "/?kieli=en" if en else "/", "scope": "/", "display": "standalone",
        "background_color": "#ffffff", "theme_color": TEEMA,
        "icons": [{"src": f"/kuvake-{k}.png", "sizes": f"{k}x{k}", "type": "image/png", "purpose": "any"}
                  for k in KOOT if k != 180]
        + [{"src": "/kuvake-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    }, ensure_ascii=False, indent=1)


@functools.lru_cache(maxsize=len(KOOT))
def kuvake(koko: int) -> bytes:
    """Kuvake PNG:nä: valokuva koskessa melovasta kajakista (logo.jpg, 512 × 512) pienennettynä.
    Meloja on kuvan keskellä, joten se pysyy maskable-kuvakkeen turva-alueella."""
    from PIL import Image

    with Image.open(LOGO) as kuva:
        tulos = io.BytesIO()
        kuva.convert("RGB").resize((koko, koko), Image.LANCZOS).save(tulos, "PNG", optimize=True)
    return tulos.getvalue()
