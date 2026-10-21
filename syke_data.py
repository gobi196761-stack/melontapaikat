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


def veden_lampotila(ajo: dict) -> float | None:
    """Vesistömallin veden lämpötila (tw_ka, °C) ennusteen alkupäivältä."""
    try:
        return _arvo(ajo["tw_ka"], dt.date.fromisoformat(ajo["ennustepvm_www"]))
    except (KeyError, TypeError, ValueError):
        return None


def lue_ajo(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


# ---------------------------------------------------------------------------
# Arviomallit: tämän päivän arvo muiden asemien havainnoista, kun aseman
# oma havainto julkaistaan vasta seuraavana päivänä.
# ---------------------------------------------------------------------------

# SYKE:n reaaliaikaiset (tarkistamattomat) mittaukset 15 min – 1 h välein, 3 kk taaksepäin:
# tiedoston rivi "21.10.2026;14:30;48,600;" (uusin ensin). Virtaama Q<asema>.txt (m³/s),
# vedenkorkeus W<asema>_<korkeusjärjestelmä>.txt (m). Käytetään päivän keskiarvona sille päivälle,
# jolta ajo.jsonissa ei vielä ole havaintoa (yleensä tänään).
REAALIAIKA_URL = "https://wwwi3.ymparisto.fi/i3/RealTime/data/{tiedosto}.txt"


def lue_reaaliaika_tunnit(data: bytes) -> dict[str, float]:
    """Reaaliaikatiedosto -> tuntien keskiarvot: 'VVVV-KK-PPTHH' (Suomen aikaa) -> arvo."""
    summat: dict[str, list[float]] = {}
    for rivi in data.decode("latin-1").splitlines():
        osat = rivi.strip().split(";")
        if len(osat) < 3:
            continue
        try:
            hetki = dt.datetime.strptime(f"{osat[0]} {osat[1]}", "%d.%m.%Y %H:%M")
            arvo = float(osat[2].replace(",", "."))
        except ValueError:
            continue
        summat.setdefault(hetki.strftime("%Y-%m-%dT%H"), []).append(arvo)
    return {t: sum(v) / len(v) for t, v in summat.items()}


def lue_reaaliaika(data: bytes) -> dict[str, float]:
    """Reaaliaikatiedosto -> päivän keskiarvot: 'VVVV-KK-PP' -> arvo."""
    summat: dict[str, list[float]] = {}
    for rivi in data.decode("latin-1").splitlines():
        osat = rivi.strip().split(";")
        if len(osat) < 3:
            continue
        try:
            p = dt.datetime.strptime(osat[0], "%d.%m.%Y").date().isoformat()
            arvo = float(osat[2].replace(",", "."))
        except ValueError:
            continue
        summat.setdefault(p, []).append(arvo)
    return {p: sum(v) / len(v) for p, v in summat.items()}


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


@dataclass(frozen=True)
class Syotemalli:
    """Q_t = b · [1, Q_{t−1}, Q_{t−2}, S, K, L, S', K', L', ((H2 − h0)/100)³, ΔH, ti … su].

    Q = aseman oma virtaama (eilinen ja toissapäiväinen havainto tai niiden arvio), S, K, L =
    syöttöasemien virtaamat tänään ja eilen ('), H = vedenkorkeus (cm), H2 kahden päivän keskiarvo,
    ΔH = H − H', viikonpäivä (maanantai vertailutaso: säännöstelty voimalaitos ajaa arkena eri
    tavalla). Kertoimet valitaan eilisen virtaaman mukaan (alle/yli `raja`).
    """
    nimi: str
    virtaama_asemat: tuple[str, ...]  # "<alue>/<asema>", ajo.json: qhav / qinlask_ka
    korkeus_asema: str                # "<alue>/<asema>", ajo.json: whav / wlask_ka (m) -> cm
    h0: float                         # cm
    raja: float
    pieni: tuple[float, ...]
    iso: tuple[float, ...]
    reaaliaika: dict[str, str]        # asema -> reaaliaikatiedosto (REAALIAIKA_URL)

    def ajo_avaimet(self) -> list[str]:
        return [f"{a}/ajo.json" for a in (*self.virtaama_asemat, self.korkeus_asema)]


# Toinen arvio (Maalismaa, Hawa'Ii): Siuruanjoki (Leuvankoski 6101600), Iijoki (Kurenalus 6100700), Livojoki
# (Hanhikoski 6101210), Pudasjärven vedenkorkeus (Tuulisalmi 6100710, N43) ja Maalismaan eilinen ja
# toissapäiväinen virtaama. Sovitettu SYKE:n päiväarvoihin touko–15.11. 2003–2026 erikseen
# alle/yli 350 m³/s (eilisen mukaan). Vuosittain ristiinvalidoitu keskivirhe 13.8 m³/s, yli
# 500 m³/s: 12.9 (edellinen malli Pudasjärvi + Siurua + eilinen korjaus: 15.9 / 14.1).
TARKENNETUT = {
    "61/q6101750y": Syotemalli(
        "Siurua + Kurenalus + Livojoki + Pudasjärvi", ("61/q6101600y", "61/q6100700y", "61/q6101210y"),
        "61/l611331001y", 10590, 350,
        pieni=(13.1479, 0.285527, 0.148714, 1.2296, 0.345337, 0.0415332, -0.402654, 0.144247, 0.362696,
               1.79153, -0.368733, -7.66559, -7.14899, -6.5718, -5.73668, -10.8386, -9.41838),
        iso=(8.38867, 0.848733, -0.0182474, 0.89351, 0.0205082, -0.123022, -0.677273, 0.1234, 0.195582,
             0.397231, 1.16092, 0.417417, -1.21062, -1.31787, -2.20016, 1.08905, -0.582837),
        reaaliaika={"61/q6101600y": "Q6101600", "61/q6100700y": "Q6100700", "61/q6101210y": "Q6101210",
                    "61/l611331001y": "W6100710_N43"}),
}


def reaaliaika_osoitteet() -> dict[str, str]:
    """Arviomallien syöteasemien reaaliaikatiedostot: '<asema>/reaaliaika' -> osoite."""
    return {f"{a}/reaaliaika": REAALIAIKA_URL.format(tiedosto=t)
            for m in TARKENNETUT.values() for a, t in m.reaaliaika.items()}


def lisaa_reaaliaika(ajot: dict[str, dict], hae) -> None:
    """Hakee syöteasemien reaaliaikamittaukset (hae: osoite -> bytes | None) ajot-sanakirjaan
    avaimille '<asema>/reaaliaika'. Puuttuva tiedosto ohitetaan (malli käyttää ajo.jsonia)."""
    for avain, osoite in reaaliaika_osoitteet().items():
        data = hae(osoite)
        if data:
            ajot[avain] = lue_reaaliaika(data)
            ajot[avain + "_tunnit"] = lue_reaaliaika_tunnit(data)


def syotteen_arvo(ajo: dict, paiva: dt.date, hav_nimi: str = "qhav", lask_nimi: str = "qinlask_ka",
                  reaaliaika: dict[str, float] | None = None) -> float | None:
    """Havainto päivältä; muuten reaaliaikamittausten keskiarvo (jos annettu); muuten
    tuoreimpaan havaintoon korjattu SYKE:n ennuste."""
    hav, lask = ajo.get(hav_nimi), ajo.get(lask_nimi)
    if hav:
        v = _arvo(hav, paiva)
        if v is not None:
            return v
    if reaaliaika and paiva.isoformat() in reaaliaika:
        return reaaliaika[paiva.isoformat()]
    if not hav:
        return None
    for n in range(1, HAVAINTO_MAX_IKA + 1):
        v = _arvo(hav, paiva - dt.timedelta(days=n))
        if v is None:
            continue
        nyt = _arvo(lask, paiva) if lask else None
        silloin = _arvo(lask, paiva - dt.timedelta(days=n)) if lask else None
        return v + (nyt - silloin) if nyt is not None and silloin is not None else None
    return None


def _syote(ajot: dict[str, dict], asema: str, paiva: dt.date, vedenkorkeus: bool = False) -> float | None:
    ajo = ajot.get(f"{asema}/ajo.json") or {}
    reaaliaika = ajot.get(f"{asema}/reaaliaika")
    nimet = ("whav", "wlask_ka") if vedenkorkeus else ("qhav", "qinlask_ka")
    return syotteen_arvo(ajo, paiva, *nimet, reaaliaika=reaaliaika)


def arvioi_paiva2(asema: str, ajot: dict[str, dict], paiva: dt.date, _syvyys: int = 0) -> float | None:
    """Toisen arvion (TARKENNETUT) arvo päivälle syöttöasemien sen päivän ja edellisen päivän arvoista sekä aseman
    kahden edellisen päivän virtaamasta (havainto, tai puuttuessa sen päivän arvio). `ajot`:
    ajo.json-avain -> ajo.json, ja '<asema>/reaaliaika' -> päivän keskiarvot (lue_reaaliaika).
    None, jos syötteitä puuttuu."""
    malli = TARKENNETUT[asema]
    oma = (ajot.get(f"{asema}/ajo.json") or {}).get("qhav")

    def oma_arvo(n: int) -> float | None:
        p = paiva - dt.timedelta(days=n)
        v = _arvo(oma, p) if oma else None
        if v is None and _syvyys < HAVAINTO_MAX_IKA:
            v = arvioi_paiva2(asema, ajot, p, _syvyys + 1)
        return v

    eilen = paiva - dt.timedelta(days=1)
    q1, q2 = oma_arvo(1), oma_arvo(2)
    s, k, l = (_syote(ajot, a, paiva) for a in malli.virtaama_asemat)
    s1, k1, l1 = (_syote(ajot, a, eilen) for a in malli.virtaama_asemat)
    h, h1 = (_syote(ajot, malli.korkeus_asema, p, vedenkorkeus=True) for p in (paiva, eilen))
    if None in (q1, q2, s, k, l, s1, k1, l1, h, h1):
        return None
    h, h1 = h * 100, h1 * 100
    x = [1.0, q1, q2, s, k, l, s1, k1, l1, (((h + h1) / 2 - malli.h0) / 100) ** 3, h - h1] \
        + [1.0 if paiva.weekday() == i else 0.0 for i in range(1, 7)]
    b = malli.iso if q1 >= malli.raja else malli.pieni
    return sum(xi * bi for xi, bi in zip(x, b))


# Paikkojen mittarit, joiden omat mittaukset ovat SYKE:n reaaliaikasivuilla (samat yksiköt ja
# korkeusjärjestelmä kuin ajo.jsonissa): kaavio -> reaaliaikatiedosto. Tuntikaavio kaavion alle.
REAALIAIKA_MITTARIT = {
    "60/q6000410y/wlyhyt.png": "W6000410_NN",      # Haukipudas (Koiteli)
    "61/l611331001y/w3lyhyt.png": "W6100710_N43",  # Pudasjärvi (Kipinä)
    "59/q5904400y/qin3lyhyt.png": "Q5904400",      # Sanginjoki
    "63/q6300210y/wlyhyt.png": "W6300210_N60",     # Ravaska (Kuivajoki, Olhavajoki)
    "57/q5700700y/qinlyhyt.png": "Q5700702",       # Länkelä, Digital Matter (Siikajoki)
    "57/q5700700y/w3lyhyt.png": "W5700702_NN",     # Länkelän vedenkorkeus (Siikajoki)
    "67/q6702110y/wlyhyt.png": "W6702110_N60",     # Matkakoski (myös Kukkolan- ja Vuentokoski)
}


def mittarin_tunnit(tunnit: dict[str, float], paiva: dt.date) -> dict | None:
    """Mittarin oma päivä tunneittain reaaliaikamittauksista: {"arviot": mitatut tuntiarvot,
    "ennuste": loppupäivä viimeisen TUNTITRENDI tunnin muutosta jatkaen, "keskiarvo": päivän
    keskiarvo (mitatut + ennuste), "viim": viimeinen mitattu tunti}. None ilman päivän mittauksia."""
    sarja = _tuntisarja(tunnit, paiva)
    if sarja is None:
        return None
    mitatut = {int(t[11:13]): v for t, v in tunnit.items() if t[:10] == paiva.isoformat()}
    viim = max(mitatut)
    ennuste = {t: v for t, v in sarja.items() if t >= viim}
    return {"arviot": mitatut, "ennuste": ennuste,
            "keskiarvo": (sum(mitatut.values()) + sum(v for t, v in ennuste.items() if t > viim))
            / (len(mitatut) + len([t for t in ennuste if t > viim])), "viim": viim}


TUNTITRENDI = 6   # loppupäivän ennuste: syötteen muutos viimeisen 6 tunnin aikana jatkuu suoraan


def _tuntisarja(tunnit: dict[str, float], paiva: dt.date) -> dict[int, float] | None:
    """Syötteen arvo päivän jokaiselle tunnille 0–23: mitattu (viimeisin tunti ≤ t) tai loppupäivälle
    viimeisen TUNTITRENDI tunnin muutosta jatkava ennuste. None, jos päivältä ei ole mittauksia."""
    mitatut = {int(t[11:13]): v for t, v in tunnit.items() if t[:10] == paiva.isoformat()}
    if not mitatut:
        return None
    viim = max(mitatut)
    ennen = {}
    for t, v in tunnit.items():   # trendiä varten myös edellisen päivän tunnit
        hetki = dt.datetime.strptime(t, "%Y-%m-%dT%H")
        ero = (dt.datetime.combine(paiva, dt.time(viim)) - hetki).total_seconds() / 3600
        if 0 <= ero <= TUNTITRENDI:
            ennen[ero] = v
    kulma = (mitatut[viim] - ennen[max(ennen)]) / max(ennen) if ennen and max(ennen) > 0 else 0.0
    sarja, edellinen = {}, mitatut.get(min(mitatut))
    for t in range(24):
        if t <= viim:
            edellinen = mitatut.get(t, edellinen)
            sarja[t] = edellinen
        else:
            sarja[t] = max(0.0, mitatut[viim] + kulma * (t - viim))
    return sarja


def tuntiarviot(asema: str, ajot: dict[str, dict], paiva: dt.date) -> dict | None:
    """Toisen arvion (TARKENNETUT) tunnittainen arvo päivälle syötteiden tuntimittauksista:
    {"arviot": {tunti: arvo} mitatuista syötteistä, "ennuste": {tunti: arvo} loppupäivälle
    (syötteiden trendi jatkuu), "keskiarvo": päivän keskiarvo, "viim": viimeinen mitattu tunti}.
    Malli on sovitettu päiväarvoihin; tuntiarvo kertoo, mihin päivän keskiarvo on menossa."""
    malli = TARKENNETUT.get(asema)
    if not malli:
        return None
    oma = (ajot.get(f"{asema}/ajo.json") or {}).get("qhav")

    def oma_arvo(n: int) -> float | None:
        p = paiva - dt.timedelta(days=n)
        v = _arvo(oma, p) if oma else None
        return v if v is not None else arvioi_paiva2(asema, ajot, p)

    eilen = paiva - dt.timedelta(days=1)
    q1, q2 = oma_arvo(1), oma_arvo(2)
    s1, k1, l1 = (_syote(ajot, a, eilen) for a in malli.virtaama_asemat)
    h1 = _syote(ajot, malli.korkeus_asema, eilen, vedenkorkeus=True)
    sarjat = [_tuntisarja(ajot.get(f"{a}/reaaliaika_tunnit") or {}, paiva)
              for a in (*malli.virtaama_asemat, malli.korkeus_asema)]
    if None in (q1, q2, s1, k1, l1, h1) or None in sarjat:
        return None
    viim = min(max(int(t[11:13]) for t in (ajot.get(f"{a}/reaaliaika_tunnit") or {}) if t[:10] == paiva.isoformat())
               for a in (*malli.virtaama_asemat, malli.korkeus_asema))
    b = malli.iso if q1 >= malli.raja else malli.pieni
    vp = [1.0 if paiva.weekday() == i else 0.0 for i in range(1, 7)]
    arvot = {}
    for t in range(24):
        s, k, l, h = (sarja[t] for sarja in sarjat)
        h, hh1 = h * 100, h1 * 100
        x = [1.0, q1, q2, s, k, l, s1, k1, l1, (((h + hh1) / 2 - malli.h0) / 100) ** 3, h - hh1] + vp
        arvot[t] = sum(xi * bi for xi, bi in zip(x, b))
    return {"arviot": {t: v for t, v in arvot.items() if t <= viim},
            "ennuste": {t: v for t, v in arvot.items() if t >= viim},
            "keskiarvo": sum(arvot.values()) / 24, "viim": viim}


def _mallin_arvo(malli: Arviomalli, k: Kertoimet, ajot: dict[str, dict], paiva: dt.date) -> float | None:
    q = _syote(ajot, malli.virtaama_asema, paiva)
    h = _syote(ajot, malli.korkeus_asema, paiva, vedenkorkeus=True)
    h1 = _syote(ajot, malli.korkeus_asema, paiva - dt.timedelta(days=1), vedenkorkeus=True)
    if None in (q, h, h1):
        return None
    return malli.kaava(k, q, h * 100, h1 * 100)


def arvioi_paiva(asema: str, ajot: dict[str, dict], paiva: dt.date) -> float | None:
    """Arviomallin arvo päivälle: syötteet sen päivän havainnoista ja korjaus sitä edeltävästä
    aseman havainnosta – eli arvo, jonka malli olisi antanut sinä päivänä. None, jos syötteitä puuttuu."""
    malli = ARVIOMALLIT[asema]
    oma = ajot.get(f"{asema}/ajo.json") or {}
    # Aseman tuorein havainto (yleensä eilinen) valitsee kertoimet ja antaa korjauksen
    viim = None
    for n in range(1, HAVAINTO_MAX_IKA + 1):
        v = _arvo(oma.get("qhav"), paiva - dt.timedelta(days=n)) if oma.get("qhav") else None
        if v is not None:
            viim = (n, v)
            break
    k = malli.iso if viim and viim[1] >= malli.raja else malli.pieni
    arvo = _mallin_arvo(malli, k, ajot, paiva)
    if arvo is None:
        return None
    if viim:
        n, havaittu = viim
        silloin = _mallin_arvo(malli, k, ajot, paiva - dt.timedelta(days=n))
        if silloin is not None:
            arvo += k.alfa ** n * (havaittu - silloin)   # vanhempi virhe painaa vähemmän
    return arvo


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
    arvo = arvioi_paiva(asema, ajot, tanaan)
    if arvo is None:
        return f"{asema}: arviomallin ({malli.nimi}) syötteitä puuttuu – käytetään havaintoa"
    lukema.havaittu, lukema.havaittu_paivia_sitten = arvo, 0
    lukema.tietolahde = f"arvio {malli.nimi}"
    if asema in TARKENNETUT:   # toinen arvio rinnalle (ei vaikuta pisteisiin)
        arvo2 = arvioi_paiva2(asema, ajot, tanaan)
        if arvo2 is not None:
            lukema.toinen_arvio = (TARKENNETUT[asema].nimi, arvo2)
    return None
