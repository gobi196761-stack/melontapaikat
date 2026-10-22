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

KOOT = (180, 192, 512)   # 180 = apple-touch-icon, 192 ja 512 = manifest
TAUSTA = (11, 98, 196)    # sivun linkkiväri (--linkki)
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
    """Kuvake PNG:nä: valkoinen kajakki ja mela aalloilla sinisellä pohjalla. Piirretään
    4-kertaisena ja pienennetään (pehmeät reunat). Sisältö pysyy maskable-kuvakkeen
    turva-alueella (keskimmäiset 80 %)."""
    from PIL import Image, ImageDraw

    s = koko * 4
    kuva = Image.new("RGB", (s, s), TAUSTA)
    d = ImageDraw.Draw(kuva)
    valk = (255, 255, 255)
    u = s / 100   # yksikkö: prosentti kuvakkeen leveydestä
    # mela vinottain kajakin yli, lavat päissä
    d.line([(27 * u, 27 * u), (73 * u, 57 * u)], fill=valk, width=round(3.2 * u))
    for x, y in ((27, 27), (73, 57)):
        d.ellipse([(x - 5.5) * u, (y - 3.2) * u, (x + 5.5) * u, (y + 3.2) * u], fill=valk)
    # kajakki: pitkä suippo runko ja istuinaukko
    d.polygon([(14 * u, 48 * u), (30 * u, 42 * u), (70 * u, 42 * u), (86 * u, 48 * u),
               (70 * u, 53 * u), (30 * u, 53 * u)], fill=valk)
    d.ellipse([43 * u, 44.5 * u, 57 * u, 49.5 * u], fill=TAUSTA)
    # aallot
    for y in (69, 78):
        for x in range(14, 86, 12):
            d.arc([x * u, (y - 4) * u, (x + 12) * u, (y + 4) * u], 200, 340, fill=valk, width=round(2.6 * u))
    tulos = io.BytesIO()
    kuva.resize((koko, koko), Image.LANCZOS).save(tulos, "PNG", optimize=True)
    return tulos.getvalue()
