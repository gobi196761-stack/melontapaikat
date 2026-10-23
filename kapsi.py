"""Maalismaan (Iijoki) tuntimittausten keruu mpahkala.kapsi.fi-melontaraportista Firestoreen.

Raportti (KAPSI_URL) päivittyy muutaman tunnin välein ja näyttää HawaIi-kohdassa Maalismaan
virtaaman viimeisimmän arvon ja edelliset 12 tuntia kahden tunnin välein. SYKE julkaisee
Maalismaasta vain vuorokausiarvot, joten tunnittaiset arvot kerätään talteen vertailua varten.
Kerättyä dataa ei näytetä sovelluksessa.

Kutsutaan molemmista Vercel Cron -ajoista (/api/halyta aamulla ja /api/arkistoi illalla):
kahdella 12 tunnin ikkunalla saadaan vuorokauden mittaukset. Tallennus: kokoelma KOKOELMA,
dokumentti päivää kohden ('2026-10-23') -> {"mittaukset": {"05:30": 362.39, ...}, "paivitetty": ...}.
Ajat ovat raportin aikoja (Suomen aikaa).
"""

from __future__ import annotations

import re

import osm_sivut as osm

KAPSI_URL = "https://mpahkala.kapsi.fi/melontaraportti.html"
KOKOELMA = "kapsi_maalismaa"
OSIO = 'id="HawaIi"'

# Kahden sarakkeen rivit (aika, arvo); ennustetaulukon neljän sarakkeen rivit eivät täsmää
_RIVI = re.compile(r"<tr><td>(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})(?: \([^)]*\))?</td><td>(-?\d+(?:\.\d+)?)</td></tr>")


def lue_maalismaa(html: str) -> list[tuple[str, str, float]]:
    """Raportin HawaIi-kohdan mittaukset: [(päivä, kellonaika, m³/s)] (viimeisin ja historia,
    myös HTML-kommentin sisältä). Tyhjä, jos kohtaa ei löydy."""
    alku = html.find(OSIO)
    if alku < 0:
        return []
    loppu = html.find('<div class="location"', alku + len(OSIO))
    osio = html[alku:loppu if loppu > 0 else len(html)]
    return sorted({(p, k, float(a)) for p, k, a in _RIVI.findall(osio)})


def tallenna(kanta, mittaukset: list[tuple[str, str, float]], nyt: str) -> int:
    """Yhdistää mittaukset päiväkohtaisiin dokumentteihin; palauttaa uusien mittausten määrän."""
    paivittain: dict[str, dict[str, float]] = {}
    for paiva, aika, arvo in mittaukset:
        paivittain.setdefault(paiva, {})[aika] = arvo
    uusia = 0
    for paiva, uudet in paivittain.items():
        vanha = (kanta.lue(KOKOELMA, paiva) or {}).get("mittaukset") or {}
        lisatty = {a: v for a, v in uudet.items() if vanha.get(a) != v}
        if lisatty:
            uusia += len(lisatty)
            kanta.kirjoita(KOKOELMA, paiva, {"mittaukset": {**vanha, **uudet}, "paivitetty": nyt,
                                             "lahde": KAPSI_URL})
    return uusia


def keraa(kanta, nyt: str, hae=None) -> dict:
    """Hakee raportin ja tallentaa mittaukset. Ei koskaan nosta poikkeusta: virhe palautetaan
    tuloksessa, jottei keruu kaada ajastettua ajoa, johon se on liitetty."""
    try:
        data = (hae or osm.Hakija(aikaraja=20).hae)(KAPSI_URL)
        mittaukset = lue_maalismaa(data.decode("utf-8", errors="replace"))
        if not mittaukset:
            return {"virhe": "raportista ei löytynyt Maalismaan mittauksia"}
        return {"mittauksia": len(mittaukset), "uusia": tallenna(kanta, mittaukset, nyt),
                "viimeisin": " ".join(mittaukset[-1][:2])}
    except Exception as e:   # noqa: BLE001 - keruu on sivutoiminto
        return {"virhe": f"{type(e).__name__}: {e}"}
