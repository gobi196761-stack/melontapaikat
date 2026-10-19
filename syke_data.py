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
class Kertoimet:
    vakio: float
    virtaama: float     # yläpuolisen sivujoen virtaama (m³/s)
    kuutio: float       # ((H2 - h0) / 100)³, H2 = kahden päivän vedenkorkeuden keskiarvo (cm)
    muutos: float       # ΔH = H - H' (cm/vrk): nousussa osa vedestä jää varastoon
    alfa: float         # eilisen virheen paino


@dataclass(frozen=True)
class Arviomalli:
    """Q = vakio + a·Q_sivu + b·((H2 − h0)/100)³ + c·ΔH + α·(eilinen havainto − mallin eilinen arvo).

    Kertoimet valitaan aseman tuoreimman havainnon mukaan (alle/yli `raja`).
    """
    nimi: str
    virtaama_asema: str      # "<alue>/<asema>", ajo.json: qhav / qinlask_ka
    korkeus_asema: str       # "<alue>/<asema>", ajo.json: whav / wlask_ka (m) -> cm
    h0: float                # cm
    raja: float
    pieni: Kertoimet
    iso: Kertoimet

    def ajo_avaimet(self) -> list[str]:
        return [f"{self.virtaama_asema}/ajo.json", f"{self.korkeus_asema}/ajo.json"]

    def kaava(self, k: Kertoimet, q: float, h: float, h_eilen: float) -> float:
        return (k.vakio + k.virtaama * q + k.kuutio * (((h + h_eilen) / 2 - self.h0) / 100) ** 3
                + k.muutos * (h - h_eilen))


# Maalismaa (Hawa'Ii): Siuruanjoki (Leuvankoski) + Pudasjärven vedenkorkeus (Tuulisalmi
# 6100710, N43) ja eilisen virheen korjaus. Kaavan muoto toisesta analyysista
# (210 + 1,05·Q1600 + 6,43·((H2−10590)/100)³ − 1,24·ΔH, Q ≥ 450); kertoimet sovitettu
# uudelleen SYKE:n päiväarvoihin touko–15.11. 2003–2026 erikseen alle/yli 450 m³/s
# (ryhmä eilisen havainnon mukaan). Vuosittain ristiinvalidoitu keskivirhe 15.8 m³/s
# (600–800 m³/s: 11.6); ilman korjausta 22.3, Pahkakoski + Siurua (eilinen Pahkakoski) 18.9.
ARVIOMALLIT = {
    "61/q6101750y": Arviomalli(
        "Pudasjärvi + Siurua, eilinen korjaus", "61/q6101600y", "61/l611331001y", 10590, 450,
        pieni=Kertoimet(68.828, 1.4523, 12.5438, -0.9732, 0.655),
        iso=Kertoimet(208.230, 1.0538, 6.4541, -1.1160, 0.858)),
}


def syotteen_arvo(ajo: dict, paiva: dt.date, hav_nimi: str = "qhav",
                  lask_nimi: str = "qinlask_ka") -> float | None:
    """Havainto päivältä, tai tuoreimpaan havaintoon korjattu SYKE:n ennuste."""
    hav, lask = ajo.get(hav_nimi), ajo.get(lask_nimi)
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


def _mallin_arvo(malli: Arviomalli, k: Kertoimet, ajot: dict[str, dict], paiva: dt.date) -> float | None:
    q_ajo = ajot.get(f"{malli.virtaama_asema}/ajo.json") or {}
    h_ajo = ajot.get(f"{malli.korkeus_asema}/ajo.json") or {}
    q = syotteen_arvo(q_ajo, paiva)
    h = syotteen_arvo(h_ajo, paiva, "whav", "wlask_ka")
    h1 = syotteen_arvo(h_ajo, paiva - dt.timedelta(days=1), "whav", "wlask_ka")
    if None in (q, h, h1):
        return None
    return malli.kaava(k, q, h * 100, h1 * 100)


def arvioi_tanaan(lukema: Kaaviolukema, ajot: dict[str, dict]) -> str | None:
    """Korvaa vanhentuneen havainnon arviomallin arvolla (vain virtaamat).

    `ajot`: ajo.json-avain -> luettu ajo.json. Palauttaa varoituksen tai None.
    """
    asema = "/".join(lukema.url.split("/i2/", 1)[-1].split("/")[:2])
    malli = ARVIOMALLIT.get(asema)
    if not malli or lukema.suure != "virtaama" or lukema.havaittu_paivia_sitten == 0:
        return None
    oma = ajot.get(f"{asema}/ajo.json") or {}
    try:
        tanaan = dt.date.fromisoformat(oma["ennustepvm_www"])
    except (KeyError, TypeError, ValueError):
        return None
    # Aseman tuorein havainto (yleensä eilinen) valitsee kertoimet ja antaa korjauksen
    viim = None
    for n in range(1, HAVAINTO_MAX_IKA + 1):
        v = _arvo(oma.get("qhav"), tanaan - dt.timedelta(days=n)) if oma.get("qhav") else None
        if v is not None:
            viim = (n, v)
            break
    k = malli.iso if viim and viim[1] >= malli.raja else malli.pieni
    arvo = _mallin_arvo(malli, k, ajot, tanaan)
    if arvo is None:
        return f"{asema}: arviomallin ({malli.nimi}) syötteitä puuttuu – käytetään havaintoa"
    if viim:
        n, havaittu = viim
        silloin = _mallin_arvo(malli, k, ajot, tanaan - dt.timedelta(days=n))
        if silloin is not None:
            arvo += k.alfa ** n * (havaittu - silloin)   # vanhempi virhe painaa vähemmän
    lukema.havaittu, lukema.havaittu_paivia_sitten = arvo, 0
    lukema.tietolahde = f"arvio {malli.nimi}"
    return None
