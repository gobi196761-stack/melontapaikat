"""Sivu asennettavaksi sovellukseksi (web app manifest ja kuvake).

iPhonessa push-ilmoitukset toimivat vain, kun sivu on lisätty Koti-valikkoon ja se
avautuu omana sovelluksenaan (manifestin display: standalone, iOS 16.4+). Androidissa
manifest tuo Chromeen "Asenna sovellus" -valinnan.

Reitit (app.py): /manifest.webmanifest ja /kuvake-<koko>.png (KOOT).
"""

from __future__ import annotations

import functools
import hashlib
import io
import json
from pathlib import Path

KOOT = (180, 192, 512)   # 180 = apple-touch-icon, 192 ja 512 = manifest
LOGO = Path(__file__).with_name("logo.jpg")
# Kuvakkeiden ja manifestin osoitteisiin logon sisällöstä laskettu versio: kun logo vaihtuu, osoite
# vaihtuu, eikä selain (tai uudelleen asennettu sovellus) käytä välimuistissa olevaa vanhaa kuvaketta.
VERSIO = hashlib.sha256(LOGO.read_bytes()).hexdigest()[:8]


def kuvake_osoite(koko: int) -> str:
    return f"/kuvake-{koko}.png?v={VERSIO}"


def manifest_osoite(kieli: str = "fi") -> str:
    return f"/manifest.webmanifest?{'kieli=en&' if kieli == 'en' else ''}v={VERSIO}"
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
        "icons": [{"src": kuvake_osoite(k), "sizes": f"{k}x{k}", "type": "image/png", "purpose": "any"}
                  for k in KOOT if k != 180]
        + [{"src": kuvake_osoite(512), "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
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
