"""SYKE:n kaavioiden numerodata (ajo.json) kaaviokuvien lukemisen tarkennukseksi.

Jokaisen SYKE-aseman kansiossa on kaaviokuvien lisäksi ajo.json, josta
vesi.fi:n karttapalvelu piirtää omat kaavionsa:

    https://wwwi2.ymparisto.fi/i2/<alue>/<asema>/ajo.json

Siinä on samat sarjat kuin kuvissa päivittäisinä lukuina:
    whav / qhav            havainnot (vedenkorkeus / virtaama), tuorein usein tältä päivältä
    wlask_ka / qinlask_ka  mallin laskenta ja ennuste (kuvan sininen käyrä)
    ennustepvm_www         ennusteen alkupäivä ("tänään")

Tunnuslukuja (MHW, MNW, ...) tiedostossa ei ole, joten kaavio luetaan aina
kuvasta ja JSONista korvataan vain havainto, malli ja ennuste – ja vain, jos
JSONin malli täsmää kuvasta luettuun (sama korkeusjärjestelmä ja yksikkö).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from syke_kaavio import Kaaviolukema

HAVAINTO_MAX_IKA = 3   # päivää, kuten kuvista luettaessa
ENNUSTE_PAIVIA = 14

# kaaviotiedoston alku -> (havaintosarja, mallisarja)
SARJAT = {"w": ("whav", "wlask_ka"), "q": ("qhav", "qinlask_ka")}


def ajo_avain(kaavio: str) -> str | None:
    """'67/q6702110y/wlyhyt.png' -> '67/q6702110y/ajo.json'"""
    osat = kaavio.split("/")
    return "/".join(osat[:2]) + "/ajo.json" if len(osat) >= 3 else None


def _sarjat(kaavio: str) -> tuple[str, str] | None:
    nimi = kaavio.rsplit("/", 1)[-1].lower()
    if nimi.startswith("tw"):   # lämpötilasta ei ole havaintosarjaa
        return None
    return SARJAT.get(nimi[:1])


def _arvo(sarja: dict, paiva: dt.date) -> float | None:
    try:
        i = (paiva - dt.date.fromisoformat(sarja["ensim_pvm"])).days
        v = sarja["lst"][i] if i >= 0 else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return float(v) if isinstance(v, (int, float, str)) and str(v).strip() not in ("", "nan") else None


def _toleranssi(lukema: Kaaviolukema) -> float:
    vertailu = abs(lukema.malli or lukema.havaittu or 0.0)
    return 0.10 if lukema.yksikko == "m" else max(1.0, 0.10 * vertailu)


def taydenna(lukema: Kaaviolukema, ajo: dict) -> str | None:
    """Korvaa havainnon, mallin ja ennusteen ajo.jsonin luvuilla.

    Palauttaa varoituksen, jos dataa ei voitu käyttää; muuten None.
    Lukema jätetään ennalleen, jos data puuttuu tai ei täsmää kuvaan.
    """
    sarjat = _sarjat(lukema.url)
    if not sarjat:
        return None
    hav_nimi, malli_nimi = sarjat
    try:
        tanaan = dt.date.fromisoformat(ajo["ennustepvm_www"])
    except (KeyError, TypeError, ValueError):
        return f"{lukema.url}: ajo.jsonista puuttuu ennusteen alkupäivä"
    malli_sarja = ajo.get(malli_nimi)
    malli = _arvo(malli_sarja, tanaan) if malli_sarja else None
    if malli is None:
        return None

    vertailu = lukema.malli if lukema.malli is not None else lukema.havaittu
    if vertailu is not None and abs(malli - vertailu) > _toleranssi(lukema):
        return (f"{lukema.url}: ajo.jsonin malli {malli:g} ei täsmää kuvaan ({vertailu:g}) "
                "– käytetään kuvasta luettua")

    havaittu, sitten = None, None
    hav_sarja = ajo.get(hav_nimi)
    if hav_sarja:
        for n in range(HAVAINTO_MAX_IKA + 1):
            havaittu = _arvo(hav_sarja, tanaan - dt.timedelta(days=n))
            if havaittu is not None:
                sitten = n
                break
    ennuste = {}
    for n in range(1, ENNUSTE_PAIVIA + 1):
        v = _arvo(malli_sarja, tanaan + dt.timedelta(days=n))
        if v is not None:
            ennuste[n] = v

    if havaittu is not None or lukema.havaittu is None:
        lukema.havaittu, lukema.havaittu_paivia_sitten = havaittu, sitten
    lukema.malli = malli
    if ennuste:
        lukema.ennuste = ennuste
    if lukema.tanaan_paiva is None:
        lukema.tanaan_paiva = tanaan.day
    lukema.tietolahde = "SYKE-data"
    return None


def lue_ajo(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


# ---------------------------------------------------------------------------
# Arviomallit: tämän päivän arvo muiden asemien havainnoista, kun aseman
# oma havainto julkaistaan vasta seuraavana päivänä.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Arviomalli:
    nimi: str
    vakio: float
    syotteet: tuple[tuple[str, float], ...]   # (asema "<alue>/<asema>", kerroin), virtaamat

    def ajo_avaimet(self) -> list[str]:
        return [f"{asema}/ajo.json" for asema, _ in self.syotteet]


# Maalismaa (Hawa'Ii) = Pahkakosken voimalaitos + Siuruanjoki. Sovitettu SYKE:n
# päiväarvoihin, avovesikaudet 2003–2026: testijakson 2020–2026 keskivirhe
# 10.5 m³/s, kun syötteet ovat havaintoja (Pudasjärvi + Siurua: 18.8 m³/s).
ARVIOMALLIT = {
    "61/q6101750y": Arviomalli("Pahkakoski + Siurua", -5.423,
                               (("61/q6101452y", 1.078), ("61/q6101600y", 0.911))),
}


def syotteen_arvo(ajo: dict, paiva: dt.date) -> float | None:
    """Havainto päivältä, tai tuoreimpaan havaintoon korjattu SYKE:n ennuste."""
    hav, lask = ajo.get("qhav"), ajo.get("qinlask_ka")
    if not hav:
        return None
    for n in range(HAVAINTO_MAX_IKA + 1):
        v = _arvo(hav, paiva - dt.timedelta(days=n))
        if v is None:
            continue
        if n == 0:
            return v
        nyt = _arvo(lask, paiva) if lask else None
        silloin = _arvo(lask, paiva - dt.timedelta(days=n)) if lask else None
        return v + (nyt - silloin) if nyt is not None and silloin is not None else None
    return None


def arvioi_tanaan(lukema: Kaaviolukema, ajot: dict[str, dict]) -> str | None:
    """Korvaa vanhentuneen havainnon arviomallin arvolla (vain virtaamat).

    `ajot`: ajo.json-avain -> luettu ajo.json. Palauttaa varoituksen tai None.
    """
    asema = "/".join(lukema.url.split("/i2/", 1)[-1].split("/")[:2])
    malli = ARVIOMALLIT.get(asema)
    if not malli or lukema.suure != "virtaama" or lukema.havaittu_paivia_sitten == 0:
        return None
    oma = ajot.get(f"{asema}/ajo.json")
    try:
        tanaan = dt.date.fromisoformat(oma["ennustepvm_www"])
    except (KeyError, TypeError, ValueError):
        return None
    arvo = malli.vakio
    for avain, (_, kerroin) in zip(malli.ajo_avaimet(), malli.syotteet):
        v = syotteen_arvo(ajot.get(avain) or {}, tanaan)
        if v is None:
            return f"{asema}: arviomallin ({malli.nimi}) syöte {avain} puuttuu – käytetään havaintoa"
        arvo += kerroin * v
    lukema.havaittu, lukema.havaittu_paivia_sitten = arvo, 0
    lukema.tietolahde = f"arvio {malli.nimi}"
    return None
