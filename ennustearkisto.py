"""SYKE:n virtaamaennusteiden ja sovelluksen oman arvion päiväarkisto.

SYKE ei säilytä vanhoja ennusteitaan, joten niiden tarkkuutta voi verrata
vain, jos ennusteet tallennetaan itse. Arkisto kootaan kerran päivässä:
Vercel Cron kutsuu app.py:n reittiä /api/arkistoi, joka tallentaa sen
Firestoreen, tai paikallisesti tyokalut/arkistoi_ennusteet.py.

Jokaisen aseman ajo.jsonista tallennetaan
    qinlask_ka   mallin laskenta 7 pv taakse ja ennuste 7 pv eteen
    qinlask_5/95 ennusteen 5 %:n ja 95 %:n rajat, ennusteen alusta 7 pv eteen
    qhav         havainnot viimeiseltä 7 päivältä (ennusteen alku mukaan lukien)
ja arviomallien asemille (syke_data.ARVIOMALLIT) sovelluksen oma tämän
päivän arvo ja ennuste samalla tavalla kuin melonta.py ne laskee, sekä päivän
tuntiarviot (syke_data.tuntiarviot: mitatut tunnit, loppupäivän ennuste, keskiarvo).

Arviomallien syöteasemista (osio "syotteet") tallennetaan SYKE:n reaaliaikamittausten
tuntikeskiarvot kahdelta edelliseltä ja kuluvalta päivältä (72 h; SYKE säilyttää reaaliaikadataa vain
n. 3 kk) ja vedenkorkeusasemalta lisäksi ajo.jsonin päiväsarjat whav ja wlask_ka.
Tarkkuus lasketaan tyokalut/vertaa_ennusteet.py:llä.
"""

from __future__ import annotations

import datetime as dt
import os

import osm_sivut as osm
import smhi_data
import syke_data
from syke_kaavio import Kaaviolukema

ENNUSTE_PAIVIA = 7
HAVAINTO_PAIVIA = 7
KOKOELMA = os.environ.get("FIRESTORE_KOKOELMA", "ennusteet")

ASEMAT = {
    "61/q6101750y": "Maalismaa",
    "61/q6101452y": "Pahkakoski",
    "61/q6101600y": "Siurua",
    "61/q6100700y": "Kurenalus",
    "61/q6101210y": "Livojoki",
}
# Arviomallien syöteasemat, joiden tuntimittaukset arkistoidaan (TARKENNETUT.reaaliaika)
SYOTEASEMAT = {"61/q6101600y": "Siurua", "61/q6100700y": "Kurenalus", "61/q6101210y": "Livojoki",
               "61/l611331001y": "Pudasjärvi (vedenkorkeus)"}
TUNTI_PAIVIA = 3   # tuntimittaukset kahdelta edelliseltä ja kuluvalta päivältä (tuoreimmasta mittauksesta asti)


def _paivat(sarja: dict | None, alku: dt.date, loppu: dt.date) -> dict[str, float]:
    if not sarja:
        return {}
    tulos = {}
    paiva = alku
    while paiva <= loppu:
        v = syke_data._arvo(sarja, paiva)
        if v is not None:
            tulos[paiva.isoformat()] = v
        paiva += dt.timedelta(days=1)
    return tulos


def asematiedot(ajo: dict) -> dict:
    """Arkistoitavat luvut yhden aseman ajo.jsonista."""
    t = dt.date.fromisoformat(ajo["ennustepvm_www"])
    eteen = t + dt.timedelta(days=ENNUSTE_PAIVIA)
    return {
        "ennustepvm_www": t.isoformat(),
        "utc_aikaleima": ajo.get("utc_aikaleima"),
        "qinlask_ka": _paivat(ajo.get("qinlask_ka"), t - dt.timedelta(days=HAVAINTO_PAIVIA), eteen),
        "qinlask_5": _paivat(ajo.get("qinlask_5"), t, eteen),
        "qinlask_95": _paivat(ajo.get("qinlask_95"), t, eteen),
        "qhav": _paivat(ajo.get("qhav"), t - dt.timedelta(days=HAVAINTO_PAIVIA - 1), t),
    }


def oma_arvio(asema: str, ajot: dict[str, dict]) -> dict | None:
    """Sovelluksen tämän päivän arvo ja ennuste arviomallin asemalle (kuten melonta.py)."""
    oma = ajot.get(f"{asema}/ajo.json")
    if not oma:
        return None
    lukema = Kaaviolukema(url=f"{osm.SYKE_POHJA}{asema}/qinlyhyt.png", suure="virtaama",
                          yksikko="m3/s", tanaan_paiva=None, havaittu=None,
                          havaittu_paivia_sitten=None, malli=None)
    varoitukset = [v for v in (syke_data.taydenna(lukema, oma), syke_data.arvioi_tanaan(lukema, ajot)) if v]
    t = dt.date.fromisoformat(oma["ennustepvm_www"])
    ennuste = {}
    for n in range(1, ENNUSTE_PAIVIA + 1):
        v = lukema.ennuste_korjattu(n)
        if v is not None:
            ennuste[(t + dt.timedelta(days=n)).isoformat()] = round(v, 3)
    return {
        "malli": syke_data.ARVIOMALLIT[asema].nimi,
        "lahde": lukema.lahde,
        "ennustepvm_www": t.isoformat(),
        "tanaan": None if lukema.arvo is None else round(lukema.arvo, 3),
        # toinen arvio (syke_data.TARKENNETUT), tallennetaan vertailua varten
        "tanaan2": None if lukema.toinen_arvio is None else round(lukema.toinen_arvio[1], 3),
        # kolmas arvio: tuorein havainto + tuntiarvioiden derivaatta (syke_data.kolmas_arvio)
        "tanaan3": None if lukema.kolmas_arvio is None else round(lukema.kolmas_arvio[1], 3),
        # neljäs arvio: tuorein havainto + tuntikäyrän muutos (syke_data.neljas_arvio)
        "tanaan4": None if lukema.neljas_arvio is None else round(lukema.neljas_arvio[1], 3),
        "ennuste": ennuste,
        "varoitukset": varoitukset,
    }


def syotetiedot(asema: str, ajot: dict[str, dict], paiva: dt.date) -> dict:
    """Syöteaseman tuntimittaukset (päivät paiva − 1 … paiva) ja vedenkorkeusasemalta päiväsarjat."""
    alku = (paiva - dt.timedelta(days=TUNTI_PAIVIA - 1)).isoformat()
    tunnit = ajot.get(f"{asema}/reaaliaika_tunnit") or {}
    tieto: dict = {"tunnit": {t: round(v, 3) for t, v in sorted(tunnit.items()) if alku <= t[:10] <= paiva.isoformat()}}
    ajo = ajot.get(f"{asema}/ajo.json")
    korkeusasemat = {m.korkeus_asema for m in (*syke_data.ARVIOMALLIT.values(), *syke_data.TARKENNETUT.values())}
    if ajo and asema in korkeusasemat:   # mallien vedenkorkeusasema: myös päiväsarjat
        t = dt.date.fromisoformat(ajo["ennustepvm_www"])
        tieto["ennustepvm_www"] = t.isoformat()
        tieto["whav"] = _paivat(ajo.get("whav"), t - dt.timedelta(days=HAVAINTO_PAIVIA - 1), t)
        tieto["wlask_ka"] = _paivat(ajo.get("wlask_ka"), t - dt.timedelta(days=HAVAINTO_PAIVIA),
                                    t + dt.timedelta(days=ENNUSTE_PAIVIA))
    return tieto


def tuntiarvio(asema: str, ajot: dict[str, dict], paiva: dt.date) -> dict | None:
    """Toisen arvion tuntiarviot päivälle (syke_data.tuntiarviot) arkistoitavassa muodossa."""
    tulos = syke_data.tuntiarviot(asema, ajot, paiva)
    if not tulos:
        return None
    return {"paiva": paiva.isoformat(), "viim": tulos["viim"], "keskiarvo": round(tulos["keskiarvo"], 3),
            "arviot": {f"{t:02d}": round(v, 3) for t, v in sorted(tulos["arviot"].items())},
            "ennuste": {f"{t:02d}": round(v, 3) for t, v in sorted(tulos["ennuste"].items())}}


def kokoa(ajot: dict[str, dict], arkistoitu: dt.datetime, virheet: dict[str, str] | None = None) -> dict:
    """`ajot`: ajo.json-avain ('61/q6101750y/ajo.json') -> luettu ajo.json."""
    asemat = {}
    for asema, nimi in ASEMAT.items():
        ajo = ajot.get(f"{asema}/ajo.json")
        tieto: dict = {"nimi": nimi}
        try:
            tieto.update(asematiedot(ajo) if ajo else {"virhe": (virheet or {}).get(asema, "ei haettu")})
        except (KeyError, TypeError, ValueError) as e:
            tieto["virhe"] = f"ajo.json ei kelpaa: {e!r}"
        asemat[asema] = tieto
    arviot = {}
    for asema in syke_data.ARVIOMALLIT:
        try:
            arvio = oma_arvio(asema, ajot)
        except (KeyError, TypeError, ValueError):
            arvio = None
        if arvio:
            arviot[asema] = arvio
    # tuntiarviot ja syöteasemien tuntimittaukset (Suomen päivän mukaan)
    paiva = smhi_data._suomen_paiva(arkistoitu) if arkistoitu.tzinfo else arkistoitu.date()
    for asema in syke_data.TARKENNETUT:
        try:
            tunnit = tuntiarvio(asema, ajot, paiva)
        except (KeyError, TypeError, ValueError):
            tunnit = None
        if tunnit and asema in arviot:
            arviot[asema]["tunnit"] = tunnit
    syotteet = {}
    for asema, nimi in SYOTEASEMAT.items():
        try:
            syotteet[asema] = {"nimi": nimi, **syotetiedot(asema, ajot, paiva)}
        except (KeyError, TypeError, ValueError) as e:
            syotteet[asema] = {"nimi": nimi, "virhe": f"{e!r}"}
    return {"arkistoitu": arkistoitu.isoformat(timespec="seconds"), "asemat": asemat, "arviot": arviot,
            "syotteet": syotteet}


def onnistuneet(arkisto: dict) -> list[str]:
    return [a for a, t in arkisto["asemat"].items() if "virhe" not in t]


def hae_ajot(aikaraja: float = 20) -> tuple[dict[str, dict], dict[str, str]]:
    """Hakee asemien ja arviomallien syöteasemien ajo.jsonit; palauttaa (ajot, virheet)."""
    avaimet = {f"{a}/ajo.json" for a in ASEMAT}
    for malli in (*syke_data.ARVIOMALLIT.values(), *syke_data.TARKENNETUT.values()):
        avaimet.update(malli.ajo_avaimet())
    hakija = osm.Hakija(aikaraja=aikaraja)
    ajot, virheet = {}, {}
    for avain in sorted(avaimet):
        data, virhe = osm.hae_turvallisesti(hakija, osm.kaavio_url(avain))
        try:
            if data:
                ajot[avain] = syke_data.lue_ajo(data)
        except ValueError as e:
            virhe = f"ajo.json ei ole luettavissa ({e})"
        if virhe:
            virheet[avain.rsplit("/", 1)[0]] = virhe
    syke_data.lisaa_reaaliaika(ajot, lambda url: osm.hae_turvallisesti(hakija, url)[0])
    return ajot, virheet
