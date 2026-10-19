"""SMHI:n virtaamahavainnot ja HydroNu-ennusteet Ruotsin paikoille.

Ruotsin paikoilla ei ole osm.fi-sivua eikä SYKE-kaaviota, joten mittari on
muotoa "smhi/<asema>/<piste>" ja luvut haetaan suoraan SMHI:n avoimista
rajapinnoista (ei tunnuksia):

    havainto  opendata-download-hydroobs.smhi.se, parametri 2 (virtaama 15 min),
              viimeisen vuorokauden arvot; tuorein arvo = havainto
    ennuste   vattenwebb.smhi.se/hydronu/data/point?subid=<piste>: HYPE-mallin
              päiväarvot (chartData.coutHindcast 30 pv taakse, coutForecast
              10 pv eteen, aikaleima = päivän alku UTC) sekä MQ/MHQ/MLQ.
              Sama chartData saataisiin myös .../data/chart?subid=&productionTime=,
              mutta productionTime pitäisi silti ensin hakea point-osoitteesta.

Ennuste käytetään kuten SYKE-datalla: havainto + (malli[t+n] − malli[t]),
jossa t on tämä päivä (Suomen aikaa; mallin päivät ovat UTC-päiviä). Tunnusluvut MHQ/MLQ ovat mallin, eivät
havaintojen; MLQ tallennetaan nimellä MNQ, jotta tulvaindeksi toimii.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import statistics

import osm_sivut as osm
from syke_kaavio import Kaaviolukema

HAVAINTO_URL = ("https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/2/"
                "station/{asema}/period/latest-day/data.json")
ENNUSTE_URL = "https://vattenwebb.smhi.se/hydronu/data/point?subid={piste}"
PAIVA_MS = 24 * 3600 * 1000
HAVAINTO_MAX_IKA = 3   # päivää, kuten SYKE-datalla


def on_smhi(kaavio: str) -> bool:
    return kaavio.startswith("smhi/")


def osat(kaavio: str) -> tuple[str, str]:
    """'smhi/1387/31914' -> ('1387', '31914')"""
    _, asema, piste = kaavio.split("/")
    return asema, piste


def havainto_url(asema: str) -> str:
    return HAVAINTO_URL.format(asema=asema)


def ennuste_url(piste: str) -> str:
    return ENNUSTE_URL.format(piste=piste)


def kaavio_avain(url: str) -> str | None:
    """Havainnon osoitteesta aseman avain: '.../station/1387/...' -> 'smhi/1387'"""
    m = re.search(r"hydroobs\.smhi\.se/.*/station/(\d+)/", url)
    return f"smhi/{m.group(1)}" if m else None


def _paiva(ms: int) -> dt.date:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date()


def _paivan_ms(paiva: dt.date) -> int:
    return int(dt.datetime(paiva.year, paiva.month, paiva.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _suomen_paiva(nyt: dt.datetime) -> dt.date:
    """Päivä Suomen ajassa, kuten melonta.py:n ja app.py:n päivä (tarkistukset vertaavat siihen)."""
    try:
        from zoneinfo import ZoneInfo
        return nyt.astimezone(ZoneInfo("Europe/Helsinki")).date()
    except Exception:  # aikavyöhyketietokanta puuttuu
        return nyt.astimezone(dt.timezone(dt.timedelta(hours=2))).date()


def tuorein_havainto(havainto: dict) -> tuple[float, int] | None:
    """(arvo, aikaleima ms) viimeisestä arvosta, jossa on luku."""
    for rivi in reversed(havainto.get("value") or []):
        if isinstance(rivi.get("value"), (int, float)) and isinstance(rivi.get("date"), int):
            return float(rivi["value"]), rivi["date"]
    return None


def mallisarja(kaavio: dict) -> dict[dt.date, float]:
    """HydroNu-mallin päiväarvot: jälkilaskenta ja ennuste yhdessä (ennuste voittaa)."""
    sarja = {}
    for nimi in ("coutHindcast", "coutForecast"):
        for ms, v in (kaavio.get(nimi) or {}).get("data") or []:
            if isinstance(v, (int, float)):
                sarja[_paiva(ms)] = float(v)
    return sarja


def lukema(asema: str, havainto: dict | None, ennuste: dict | None, nyt: dt.datetime) -> Kaaviolukema:
    """Kaaviolukema SMHI:n havainnosta ja HydroNu-pisteen tiedoista (kumpi tahansa voi puuttua)."""
    hav = tuorein_havainto(havainto) if havainto else None
    paiva = _suomen_paiva(nyt)
    sitten = None
    if hav:
        sitten = max(0, int((nyt.timestamp() * 1000 - hav[1]) // PAIVA_MS))
        if sitten > HAVAINTO_MAX_IKA:
            hav, sitten = None, None
    kaavio = (ennuste or {}).get("chartData") or {}
    malli = mallisarja(kaavio)
    l = Kaaviolukema(url=havainto_url(asema), suure="virtaama", yksikko="m3/s",
                     tanaan_paiva=paiva.day, havaittu=hav[0] if hav else None,
                     havaittu_paivia_sitten=sitten, malli=malli.get(paiva),
                     tietolahde="SMHI")
    l.ennuste = {n: malli[paiva + dt.timedelta(days=n)] for n in range(1, 11)
                 if paiva + dt.timedelta(days=n) in malli}
    l.tunnusluvut = {nimi: float(kaavio[k]) for nimi, k in (("MQ", "mq"), ("MHQ", "mhq"), ("MNQ", "mlq"))
                     if isinstance(kaavio.get(k), (int, float))}
    # background: [päivä, [saman päivän arvot eri vuosilta]] -> vaihteluväli ja mediaani
    for ms, arvot in kaavio.get("background") or []:
        if ms == _paivan_ms(paiva):
            arvot = [float(v) for v in arvot if isinstance(v, (int, float))]
            if arvot:
                l.hist_min, l.hist_max, l.mediaani = min(arvot), max(arvot), statistics.median(arvot)
            break
    return l


def hae(hakija: osm.Hakija, kaavio: str, nyt: dt.datetime | None = None) -> tuple[Kaaviolukema | None, list[str]]:
    """Hakee mittarin 'smhi/<asema>/<piste>' havainnon ja ennusteen; palauttaa (lukema, varoitukset)."""
    asema, piste = osat(kaavio)
    varoitukset = []
    luetut = []
    for url, nimi in ((havainto_url(asema), "havainto"), (ennuste_url(piste), "ennuste")):
        data, virhe = osm.hae_turvallisesti(hakija, url)
        try:
            luetut.append(json.loads(data.decode("utf-8")) if data else None)
        except ValueError as e:
            luetut.append(None)
            virhe = f"{url}: {e}"
        if virhe:
            varoitukset.append(f"SMHI:n {nimi} ({kaavio}) epäonnistui: {virhe}")
    havainto, ennuste = luetut
    if havainto and not tuorein_havainto(havainto):
        varoitukset.append(f"SMHI:n havainnossa ({kaavio}) ei ole arvoja")
        havainto = None
    if not havainto and not ennuste:
        return None, varoitukset
    return lukema(asema, havainto, ennuste, nyt or dt.datetime.now(dt.timezone.utc)), varoitukset
