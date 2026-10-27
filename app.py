"""Melontatilanne verkkosivuna ja JSON-rajapintana (WSGI, esim. Vercel).

Reitit:
    /       päivän järjestys taulukkona
    /api    sama JSON-muodossa (kuten `melonta.py --json`)
    /api/ajomatkat?lahto=lev,pit  ajomatkat paikkoihin (OSRM), sivun paikkakunta / oma sijainti
    /kaavio/smhi/<asema>/<piste>  Ruotsin mittarin virtaamakaavio (SVG, ks. kaavio_svg.py)
    /kaavio/syke/<alue>/<asema>/<kaavio>  SYKE:n mittarin kaavio ajo.jsonista; arviomallin
                  asemalla (Hawa'Ii) mitatut arvot + arvio. ?paikka=<nimi> valitsee kohteiden alueet
    /api/arkistoi  päivän ennusteiden arkistointi Firestoreen (Vercel Cron,
                   vaatii otsakkeen Authorization: Bearer $CRON_SECRET)
    /api/halytys   hälytyksen tilaus (POST) ja peruutus (DELETE), ks. halytykset.py
    /api/halyta    aamun hälytysten lähetys (Vercel Cron, kuten /api/arkistoi)
    /sw.js         push-ilmoitusten service worker
    /manifest.webmanifest, /kuvake-<koko>.png  sivu asennettavaksi sovellukseksi (sovellus.py)
Suodattimet kummallekin: ?tyyppi=peli|retki|ruotsi ja ?max_km=N
(ilman tyyppiä vain Suomen paikat; Ruotsin paikat näkyvät vain tyyppi=ruotsi)

Paikallisesti:
    uv run app.py            # http://localhost:8000

Yksi laskenta kestää 20–30 s (sivut + kaaviot), joten tulos pidetään
muistissa VALIMUISTI_S sekuntia ja vastaukset merkitään CDN:n
välimuistiin (Cache-Control: s-maxage). Näin vain harva pyyntö odottaa.
"""

from __future__ import annotations

import datetime as dt
import re
import hmac
import html
import json
import math
import os
import threading
import time
from dataclasses import dataclass, field, replace
from urllib.parse import parse_qs, quote, urlencode

import arviointi
import ehdotukset
import ennustearkisto
import firestore
import halytykset
import kapsi
import melonta
import osm_sivut as osm
import paikkasivut
import paikkasivut_en
import kaavio_svg
import kielet
import kuvat
import muut_kohteet
import retket
import sovellus
import smhi_data
import syke_data
import syke_kaavio
import turvallisuus
from arviointi import muotoile
from paikat import PAIKAT, SIJAINNIT, aseman_nimi, kohteen_kajakit, nakyy
from paikkakunnat import PAIKKAKUNNAT, RUOTSI

VALIMUISTI_S = 60 * 60   # SYKE:n data päivittyy kerran päivässä; pidempi aika säästää suoritinaikaa
CACHE_CONTROL = "public, max-age=300, s-maxage=3600, stale-while-revalidate=3600, stale-if-error=86400"


def suomen_aika() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Helsinki"))
    except Exception:  # aikavyöhyketietokanta puuttuu
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=2)))


@dataclass
class Tilanne:
    paivitetty: dt.datetime
    tulokset: list
    varoitukset: list[str]
    lukemia: int
    # paikan nimi -> tuntiennuste {"aika": [unix s], "t": [°C], "k": [WMO-sääkoodi]} (Open-Meteo)
    saa: dict[str, dict] = field(default_factory=dict)
    ajo_min: dict[str, float] = field(default_factory=dict)   # paikan nimi -> ajoaika Oulusta (min)
    ajo_km: dict[str, float] = field(default_factory=dict)    # paikan nimi -> ajomatka Oulusta (km)
    surffi: dict[str, list[str]] = field(default_factory=dict)  # {"nyt": [spotti], "ennuste": [spotti]}
    turva: dict = field(default_factory=dict)   # merivesi, vedenkorkeus ja maatuuli Oulussa (turvallisuus.py)
    kuvat: dict = field(default_factory=dict)   # paikan nimi -> Commons-kuva (kuvat.py)


_lukko = threading.Lock()
_tilanne: tuple[float, Tilanne] | None = None
_tilanteen_paikat: set[str] | None = None   # laskennan paikat (hyväksytty uusi kohde laskee uudelleen)


def hae_tilanne() -> Tilanne:
    """Laskee kaikkien paikkojen tilanteen tai palauttaa tuoreen tuloksen muistista."""
    global _tilanne, _tilanteen_paikat
    with _lukko:   # samanaikaiset pyynnöt odottavat yhtä laskentaa
        paikat = kaikki_paikat()
        if _tilanne and time.monotonic() - _tilanne[0] < VALIMUISTI_S \
                and _tilanne[1].paivitetty.date() == suomen_aika().date() \
                and _tilanteen_paikat == {p.nimi for p in paikat}:
            return _tilanne[1]   # uusi hyväksytty kohde laskee tilanteen uudelleen
        nyt = suomen_aika()
        hakija = osm.Hakija(aikaraja=20)
        sivun_kaaviot, lukemat, varoitukset = melonta.kerää_tilanne(hakija, paikat, lisakaaviot=False)
        tulokset = melonta.arvioi_kaikki(paikat, sivun_kaaviot, lukemat, nyt.date())
        status, oulusta = ajomatkat(OULU, hakija)
        if not status.startswith("200"):
            oulusta = {}
        try:
            paikkojen_kuvat = kuvat.paivita(osm.Hakija(aikaraja=8), _kanta(), paikat)
        except Exception:   # noqa: BLE001 – kuvat eivät saa kaataa sivua
            paikkojen_kuvat = {}
        tilanne = Tilanne(nyt, tulokset, varoitukset, len(lukemat), saaennusteet(hakija),
                          oulusta.get("min", {}), oulusta.get("km", {}), surffitilanne(hakija),
                          turvallisuus.hae(hakija), {n: k for n, k in paikkojen_kuvat.items() if k.get("kuva")})
        if lukemat:   # epäonnistunutta hakua ei jätetä muistiin
            _tilanne = (time.monotonic(), tilanne)
            _tilanteen_paikat = {p.nimi for p in paikat}
        return tilanne


OPEN_METEO = "https://api.open-meteo.com/v1/forecast?{kysely}"


OULU = "65.01,25.47"          # oletuslähtöpaikka ajoajoille (Oulun keskusta)
LISAAIKA_MIN = 30             # ajoajan päälle: pakkaus, tauot – sää katsotaan perillä tähän aikaan
LAHTO_PAIVIA = syke_data.ENNUSTE_PAIVIA   # lähtöaika enintään näin monen päivän päähän (kaavioiden ennuste)


def saaennusteet(hakija: osm.Hakija, tunteja: int = (LAHTO_PAIVIA + 1) * 24 + 12) -> dict[str, dict]:
    """Tuntiennuste (lämpötila, WMO-sääkoodi) paikkojen sijainneissa Open-Meteosta yhdellä
    kyselyllä: nimi -> {"aika": [unix s], "t": [...], "k": [...]}. Tyhjä, jos palvelu ei vastaa."""
    paikat = [p for p in kaikki_paikat() if p.sijainti]
    kysely = urlencode({"latitude": ",".join(str(p.sijainti[0]) for p in paikat),
                        "longitude": ",".join(str(p.sijainti[1]) for p in paikat),
                        "hourly": "temperature_2m,weather_code", "forecast_days": 16,
                        "timeformat": "unixtime"})
    data, _ = osm.hae_turvallisesti(hakija, OPEN_METEO.format(kysely=kysely))
    try:
        vastaus = json.loads(data.decode("utf-8")) if data else []
        vastaus = vastaus if isinstance(vastaus, list) else [vastaus]
        alku = int(time.time()) - 3600
        tulos = {}
        for p, v in zip(paikat, vastaus):
            h = v["hourly"]
            # peräkkäiset tunnit (sivulle pakataan alku + 3600 s välein): ensimmäinen puuttuva katkaisee
            rivit = []
            for a, t, k in zip(h["time"], h["temperature_2m"], h["weather_code"]):
                if a < alku:
                    continue
                if not (isinstance(t, (int, float)) and isinstance(k, int)) or len(rivit) == tunteja:
                    break
                rivit.append((a, t, k))
            if rivit:
                tulos[p.nimi] = {"aika": [r[0] for r in rivit], "t": [round(r[1], 1) for r in rivit],
                                 "k": [r[2] for r in rivit]}
        return tulos
    except (ValueError, AttributeError, KeyError, TypeError):
        return {}


SURFFI = "https://surffiennustaja.vercel.app"
# spotti -> (nimi, ennusteen rajapinta); Yppärin ennuste on oletusreitissä /api/forecast
# spotti -> (nimi, ennusteen rajapinta, sijainti); Yppärin ennuste on oletusreitissä /api/forecast.
# Sijainnit OpenStreetMapista / Wikipediasta; Pumppari likimain Yyterin rannalta.
SURFFISPOTIT = {
    "yppari": ("Yppäri", "/api/forecast", (64.4056, 24.1)),
    "tauvo": ("Tauvo", "/api/forecast/tauvo", (64.814, 24.5438)),
    "ohtakari": ("Ohtakari", "/api/forecast/ohtakari", (64.0909, 23.4046)),
    "marjaniemi": ("Marjaniemi", "/api/forecast/marjaniemi", (65.04, 24.5615)),
    "ohtakari-vattaja": ("Ohtakari Vattaja", "/api/forecast/ohtakari-vattaja", (64.0814, 23.4136)),
    "olkijoki": ("Olkijoki", "/api/forecast/olkijoki", (64.7332, 24.6131)),
    "pumppari": ("Pumppari", "/api/forecast/pumppari", (61.5642, 21.5225)),
}
OPEN_METEO_MERI = "https://marine-api.open-meteo.com/v1/marine?{kysely}"


def surffitilanne(hakija: osm.Hakija, nyt: dt.datetime | None = None) -> dict:
    """Surffiennustajan spotit, joissa surffattavaa (rating > 0) nyt ja seuraavan 48 h ennusteessa:
    {"nyt": [spotti], "ennuste": [spotti], "ajat": {spotti: surffihetki unix s}, "saa": {...}}.
    Ennusteessa vain ne, jotka eivät toimi jo nyt; surffihetki on nyt tai ennusteen ensimmäinen
    surffattava tunti, ja sille hetkelle haetaan sää ja meriveden lämpötila (surffisaa)."""
    from concurrent.futures import ThreadPoolExecutor
    nyt = nyt or dt.datetime.now(dt.timezone.utc)

    def tila(spotti: str) -> tuple[bool, float | None]:
        data, _ = osm.hae_turvallisesti(hakija, SURFFI + SURFFISPOTIT[spotti][1])
        try:
            tunnit = json.loads(data.decode("utf-8"))["hours"] if data else []
        except (ValueError, KeyError, TypeError):
            return False, None
        heti, ensimmainen = False, None
        for h in tunnit:
            try:
                alku = dt.datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if h.get("data_unknown") or not (h.get("rating") or 0) > 0:
                continue
            if alku <= nyt < alku + dt.timedelta(hours=1):
                heti = True
            elif alku > nyt and (ensimmainen is None or alku.timestamp() < ensimmainen):
                ensimmainen = alku.timestamp()
        return heti, ensimmainen

    with ThreadPoolExecutor(max_workers=len(SURFFISPOTIT)) as pool:
        tilat = dict(zip(SURFFISPOTIT, pool.map(tila, SURFFISPOTIT)))
    tulos = {"nyt": [s for s, (heti, _) in tilat.items() if heti],
             "ennuste": [s for s, (heti, ens) in tilat.items() if ens and not heti]}
    tulos["ajat"] = {**{s: nyt.timestamp() for s in tulos["nyt"]}, **{s: tilat[s][1] for s in tulos["ennuste"]}}
    tulos["saa"] = surffisaa(hakija, tulos["ajat"]) if tulos["ajat"] else {}
    return tulos


def _tunnin_arvo(ajat: list, arvot: list, hetki: float):
    i = max((i for i, a in enumerate(ajat) if a <= hetki), default=None)
    return arvot[i] if i is not None and i < len(arvot) else None


def surffisaa(hakija: osm.Hakija, ajat: dict[str, float]) -> dict[str, dict]:
    """Ilman lämpötila, sääkoodi, ukkonen ja meriveden lämpötila spottien surffihetkellä
    (Open-Meteo: sää ja Marine-rajapinta): spotti -> {"t", "k", "ukkonen", "meri"}."""
    spotit = list(ajat)
    sijainnit = [SURFFISPOTIT[s][2] for s in spotit]
    kysely = {"latitude": ",".join(str(p[0]) for p in sijainnit),
              "longitude": ",".join(str(p[1]) for p in sijainnit), "forecast_days": 3, "timeformat": "unixtime"}

    def hae(osoite: str, sarjat: str) -> list:
        data, _ = osm.hae_turvallisesti(hakija, osoite.format(kysely=urlencode({**kysely, "hourly": sarjat})))
        try:
            vastaus = json.loads(data.decode("utf-8")) if data else []
        except ValueError:
            return []
        return vastaus if isinstance(vastaus, list) else [vastaus]

    saa, meri = hae(OPEN_METEO, "temperature_2m,weather_code"), hae(OPEN_METEO_MERI, "sea_surface_temperature")
    tulos = {}
    for i, spotti in enumerate(spotit):
        hetki, tiedot = ajat[spotti], {}
        try:
            h = saa[i]["hourly"]
            tiedot["t"] = _tunnin_arvo(h["time"], h["temperature_2m"], hetki)
            tiedot["k"] = _tunnin_arvo(h["time"], h["weather_code"], hetki)
            alku = max((a for a in h["time"] if a <= hetki), default=hetki)
            tiedot["ukkonen"] = any(k in UKKOSKOODIT for a, k in zip(h["time"], h["weather_code"])
                                    if alku <= a < alku + UKKOS_TUNNIT * 3600)
        except (IndexError, KeyError, TypeError):
            pass
        try:
            m = meri[i]["hourly"]
            tiedot["meri"] = _tunnin_arvo(m["time"], m["sea_surface_temperature"], hetki)
        except (IndexError, KeyError, TypeError):
            pass
        tulos[spotti] = tiedot
    return tulos


VIIKONPAIVAT = {"fi": ("ma", "ti", "ke", "to", "pe", "la", "su"), "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}


def _ajankohta(aika: float, kieli: str) -> str:
    """'ke 14.00' Suomen aikaa."""
    try:
        from zoneinfo import ZoneInfo
        hetki = dt.datetime.fromtimestamp(aika, ZoneInfo("Europe/Helsinki"))
    except Exception:  # aikavyöhyketietokanta puuttuu
        hetki = dt.datetime.fromtimestamp(aika, dt.timezone(dt.timedelta(hours=2)))
    return f"{VIIKONPAIVAT[kieli][hetki.weekday()]} {_kello(aika, kieli)}"


def surffilinkki(surffi: dict, k_, kieli: str = "fi") -> str:
    """Otsikon alla: linkki Surffiennustajaan, vihreä jos jossain on surffattavaa nyt; toimivat spotit
    linkkeinä perässä ja ennusteessa olevat vihreinä sulkeissa. Spotin perässä surffihetken sää
    (ilma-linkki yr.no:hon, punainen ukkosella) ja meriveden lämpötila."""
    saat = surffi.get("saa") or {}

    def spotti(s: str, ajankohta: str) -> str:
        nimi, _, (lev, pit) = SURFFISPOTIT[s]
        teksti = f'<a href="{SURFFI}/{s}" target="_blank" rel="noopener">{e(nimi)}</a>'
        tiedot = saat.get(s) or {}
        osat = []
        if tiedot.get("t") is not None:
            ukkonen = tiedot.get("ukkonen")
            luokka = ' class="ukkonen"' if ukkonen else ""
            vihje = f' title="{e(k_("ukkosta ennustettu"))}"' if ukkonen else ""
            ikoni = f" {saa_ikoni(tiedot['k'])}" if tiedot.get("k") is not None else ""
            lampo = f'{tiedot["t"]:.0f} °C'.replace("-", "−")
            osoite = yr_osoite(lev, pit, (surffi.get("ajat") or {}).get(s))
            osat.append(f'<a{luokka}{vihje} href="{e(osoite)}" target="_blank" '
                        f'rel="noopener">{k_("ilma")}</a> {lampo}{ikoni}')
        if tiedot.get("meri") is not None:
            osat.append(f'{k_("meri")} {tiedot["meri"]:.1f} °C')
        if osat:
            teksti += f' <span class="surffi-saa">{ajankohta}: {" · ".join(osat)}</span>'
        return teksti

    ajat = surffi.get("ajat") or {}
    nyt, ennuste = surffi.get("nyt") or [], surffi.get("ennuste") or []
    osat = [f'<a class="surffi-paa" href="{SURFFI}/" target="_blank" rel="noopener">'
            f'🏄 {k_("Merelle Surffaamaan")}</a>']
    if nyt:
        osat.append(": " + "; ".join(spotti(s, k_("nyt")) for s in nyt))
    if ennuste:
        lista = "; ".join(spotti(s, _ajankohta(ajat[s], kieli) if s in ajat else "") for s in ennuste)
        osat.append(f' <span class="ok">({k_("ennusteessa")}: {lista})</span>')
    return f'<span class="surffi{" ok" if nyt else ""}">{"".join(osat)}</span>'


def _kesto(minuutit: float) -> str:
    """Ajoaika: '20 min' tai '3 h 05 min'."""
    m = round(minuutit)
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


UKKOSKOODIT = (95, 96, 99)   # WMO: ukkonen, ukkonen ja raekuuroja
UKKOS_TUNNIT = 4              # ukkonen "tiedossa": saapumistunnista näin monen tunnin päähän (melonta-aika)


def ukkosta(saa: dict, perilla: float) -> bool:
    """Onko ukkosta ennustettu saapumistunnista UKKOS_TUNNIT tunnin päähän?"""
    alku = max((a for a in saa["aika"] if a <= perilla), default=perilla)
    return any(k in UKKOSKOODIT for a, k in zip(saa["aika"], saa["k"]) if alku <= a < alku + UKKOS_TUNNIT * 3600)


def saa_ikoni(koodi: int) -> str:
    """WMO-sääkoodi -> aurinko, puolipilvi, pilvi tai sadepilvi."""
    if koodi <= 1:
        return "☀️"
    if koodi == 2:
        return "⛅"
    if koodi in (3, 45, 48):
        return "☁️"
    if koodi in UKKOSKOODIT:
        return "⛈️"
    return "🌧️"   # tihku, sade, lumi, kuurot


def suodata(tulokset: list, kysely: dict[str, list[str]]) -> list:
    tyyppi = kysely.get("tyyppi", [None])[0]
    try:
        max_km = int(kysely["max_km"][0]) if "max_km" in kysely else None
    except ValueError:
        max_km = None
    return [t for t in tulokset
            if nakyy(t.paikka, tyyppi)
            and (max_km is None or (t.paikka.km_oulusta or 0) <= max_km)]


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

e = html.escape

TYYLI = """
:root { --tausta:#fff; --teksti:#1b1f24; --heikko:#5c6670; --viiva:#dde2e7; --pinta:#f4f6f8;
        --hyva:#1a7f37; --keski:#9a6700; --huono:#b42318; --linkki:#0b62c4; }
@media (prefers-color-scheme: dark) {
  :root { --tausta:#121417; --teksti:#e6e9ec; --heikko:#9aa4ae; --viiva:#2c3238; --pinta:#1b1f24;
          --hyva:#4ac26b; --keski:#d4a72c; --huono:#f47067; --linkki:#6cb6ff; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--tausta); color:var(--teksti);
       font:15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:960px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:1.45rem; margin:0 0 4px; }
main.etusivu { padding-top:12px; }
.etusivu h1 { font-size:1.15rem; margin:0 0 2px; line-height:1.3; }
.etusivu nav { margin:10px 0 10px; gap:6px; }
.tyokalut { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; align-items:flex-start; }
.tyokalut > details { margin:0; padding:4px 12px; border-radius:999px; background:var(--pinta); }
.tyokalut > details[open] { flex-basis:100%; border-radius:8px; padding:8px 12px; }
.tyokalut > details > summary { font-size:.88rem; color:var(--teksti); margin:0; list-style:none; }
.tyokalut > details > summary::-webkit-details-marker { display:none; }
.valinnat p { margin:8px 0 0; }
.valinnat button { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px; background:none;
                   color:var(--teksti); font:inherit; font-size:.9rem; cursor:pointer; }
/* etusivun kortit: taulukon rivi korttina (selaimen skripti käyttää yhä rivejä ja pistesolua) */
.etusivu table, .etusivu tbody { display:block; }
.etusivu thead { display:block; }
.etusivu thead tr { display:block; }
.etusivu thead th { display:none; border:0; padding:0; }
.etusivu thead th:nth-child(2) { display:block; color:transparent; font-size:0; }
.etusivu thead th:nth-child(2) .lukumaara { font-size:.8rem; color:var(--heikko); }
.etusivu tbody tr { display:block; position:relative; border-bottom:1px solid var(--viiva); padding:14px 0; }
.etusivu tbody td { display:block; border:0; padding:0; }
.etusivu td.sija, .etusivu td.ennuste { display:none; }
.etusivu td.pisteet { position:absolute; right:0; top:96px; font-size:1.7rem; line-height:1; }
.etusivu td.pisteet::after { content:"/100"; font-size:.8rem; font-weight:600; margin-left:1px; }
.kortti { display:flex; gap:12px; align-items:flex-start; }
.kortti-kuva { flex:none; }
.kortti-kuva img { width:112px; height:112px; object-fit:cover; border-radius:14px; display:block;
                   background:var(--pinta); }
.kortti-tiedot { flex:1; min-width:0; min-height:112px; padding-right:4px; }
.kortti .nimi { display:flex; justify-content:space-between; align-items:flex-start; gap:6px; font-size:1.05rem; }
.kortti .nimi a { color:var(--teksti); text-decoration:none; }
.olot { display:inline-block; margin:6px 0 4px; padding:2px 10px; border-radius:999px; font-size:.82rem;
        font-weight:600; background:var(--pinta); }
.olot.p-hyva { background:color-mix(in srgb, var(--hyva) 14%, transparent); }
.olot.p-keski { background:color-mix(in srgb, var(--keski) 16%, transparent); }
.olot.p-huono { background:color-mix(in srgb, var(--huono) 14%, transparent); }
.kortti-tiedot .pieni { padding-right:72px; }
details.tiedot { margin-top:8px; }
details.tiedot > summary { font-size:.88rem; }
ul.kortit { list-style:none; padding:0; }
ul.kortit > li { border-bottom:1px solid var(--viiva); padding:14px 0; margin:0; }
ul.kortit .kortti-tiedot .pieni { padding-right:0; }
.paikkakuva { margin:12px 0; }
.paikkakuva img { width:100%; max-width:720px; aspect-ratio:4/3; object-fit:cover; border-radius:8px; display:block;
                  background:var(--pinta); }
.paikkakuva figcaption { color:var(--heikko); font-size:.8rem; margin-top:4px; overflow-wrap:anywhere; }
.meta, .pieni { color:var(--heikko); font-size:.88rem; }
nav { margin:14px 0 18px; display:flex; gap:8px; flex-wrap:wrap; }
nav > a, .surffi { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px;
                   color:var(--teksti); text-decoration:none; font-size:.9rem; }
.surffirivi { margin:4px 0 6px; }
.surffirivi .surffi { border-radius:12px; font-size:.85rem; padding:3px 10px; }
.surffi { display:inline-block; }
.surffi a { color:inherit; }
.surffi .surffi-paa { text-decoration:none; }
.surffi-saa { font-weight:400; color:var(--heikko); }
.surffi .surffi-saa a { color:var(--linkki); }
.surffi .surffi-saa a.ukkonen { color:var(--huono); }
.surffi.ok { border-color:var(--hyva); }
.surffi.ok, .surffi .ok { color:var(--hyva); font-weight:600; }
nav a.valittu { background:var(--teksti); color:var(--tausta); border-color:var(--teksti); }
nav .maara { font-size:.8em; opacity:.7; font-weight:400; }
nav .maara:empty { display:none; }
a { color:var(--linkki); }
.lampo { background:var(--pinta); border-radius:8px; padding:8px 12px; margin:12px 0; }
table { width:100%; border-collapse:collapse; }
th { text-align:left; font-size:.8rem; color:var(--heikko); font-weight:600;
     border-bottom:1px solid var(--viiva); padding:6px 8px; }
td { border-bottom:1px solid var(--viiva); padding:10px 8px; vertical-align:top; }
td.sija { color:var(--heikko); width:2.2em; }
td.pisteet { font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap; }
.p-hyva { color:var(--hyva); } .p-keski { color:var(--keski); } .p-huono { color:var(--huono); }
.nimi { font-weight:600; }
ul { margin:6px 0 0; padding-left:18px; }
li { margin:2px 0; }
details summary { cursor:pointer; color:var(--heikko); font-size:.88rem; margin-top:4px; }
.huom { color:var(--keski); }
.ennuste { font-variant-numeric:tabular-nums; white-space:nowrap; }
@media (max-width:640px) {
  .piilo { display:none; }
  td, th { padding:8px 4px; }
}
.suosikki { background:none; border:0; padding:0 4px; cursor:pointer; font-size:1.1rem;
            color:var(--heikko); line-height:1; vertical-align:-1px; }
.suosikki[aria-pressed="true"] { color:var(--huono); }
.otsake { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
.etusivu .otsake { align-items:baseline; }
.kieli { display:inline-flex; align-items:center; gap:6px; font-size:.85rem; color:var(--heikko);
         text-decoration:none; margin-top:4px; white-space:nowrap; }
.kieli svg { border:1px solid var(--viiva); border-radius:2px; display:block; }
.paikkakunta { display:inline-flex; align-items:center; gap:6px; font-size:.9rem; color:var(--heikko); }
#lahtoaika { width:auto; }
.paikkakunta input { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px; font:inherit;
                     font-size:.9rem; width:11em; background:var(--tausta); color:var(--teksti); }
.reitti { white-space:nowrap; }
.saa { color:var(--heikko); }
.lukumaara { font-weight:400; font-size:.8rem; color:var(--heikko); margin:0; }
h2 + .lukumaara { margin:-4px 0 6px; }
.haku { display:flex; align-items:center; gap:6px; margin:0 0 12px; color:var(--heikko); }
.haku input { flex:1; max-width:22em; padding:6px 12px; border:1px solid var(--viiva); border-radius:999px; font:inherit;
              background:var(--tausta); color:var(--teksti); }
li[hidden] { display:none; }
.takaisin { display:inline-block; margin-bottom:10px; font-size:.9rem; }
.kuvaus h2 { font-size:1.1rem; margin:22px 0 6px; }
.kuvaus p { margin:6px 0; }
.kohteet { list-style:none; padding:0; }
.kohteet li { border-bottom:1px solid var(--viiva); padding:8px 0; margin:0; }
.kohteet .rajat { font-variant-numeric:tabular-nums; }
.lahteet li { overflow-wrap:anywhere; }
.matka, .lampotilat { margin:1px 0; }
.kajakit { white-space:nowrap; }
.turva { background:var(--pinta); border-radius:8px; padding:6px 12px; margin:6px 0; }
.turva summary { color:var(--huono); font-weight:600; font-size:.92rem; }
.turva-otsikko { display:inline; }
.turva-otsikko + .turva-otsikko::before { content:" · "; color:var(--heikko); font-weight:400; }
.turva h3 { margin:10px 0 2px; font-size:.95rem; color:var(--huono); }
.turva p { margin:0 0 6px; line-height:1.45; }
.selitykset { background:var(--pinta); border-radius:8px; padding:8px 12px; margin:12px 0; }
.selitykset ul { display:flex; flex-wrap:wrap; gap:4px 16px; list-style:none; padding:0; margin:6px 0; }
.selitykset p { margin:4px 0 0; }
.kajakki { width:26px; height:20.8px; vertical-align:-6px; margin-left:3px; color:var(--linkki); }
.ukkonen { color:var(--huono) !important; font-weight:700; }
.tyyppi { font-weight:400; font-size:.85rem; color:var(--heikko); margin-left:2px; }
.ehdota { background:var(--pinta); border-radius:8px; padding:8px 12px; margin:12px 0; }
.ehdota ul { margin:6px 0; padding-left:18px; }
.ehdota summary { font-size:.95rem; color:var(--teksti); margin:0; }
.lamppu { display:inline-block; animation:syty 2.4s ease-in-out 1s 2; }
@keyframes syty { 0%, 100% { filter:grayscale(1) brightness(.8); }
                  40%, 70% { filter:none; text-shadow:0 0 6px #ffd23f, 0 0 14px #ffd23f; } }
@media (prefers-reduced-motion: reduce) { .lamppu { animation:none; } }
.nappi { display:inline-block; padding:6px 14px; margin:4px 6px 4px 0; border-radius:6px; text-decoration:none;
         border:1px solid var(--teksti); background:var(--teksti); color:var(--tausta); font-weight:600;
         cursor:pointer; font-size:.92rem; }
.nappi.toissijainen { background:none; color:var(--teksti); }
.halytys { background:var(--pinta); border-radius:8px; padding:8px 12px; margin:12px 0; }
.halytys summary { font-size:.95rem; color:var(--teksti); margin:0; }
.halytys p { margin:8px 0 0; }
.halytys label { margin-right:12px; white-space:nowrap; display:inline-block; margin-top:4px; }
.halytys select { max-width:100%; }
.halytys-ehdot { margin:8px 0 0; padding-left:18px; }
.halytys select, .halytys button { font:inherit; font-size:.9rem; padding:4px 10px; border:1px solid var(--viiva);
                                   border-radius:999px; background:var(--tausta); color:var(--teksti); }
.halytys button { color:var(--linkki); cursor:pointer; }
.halytys [hidden] { display:none; }
.halytys .halytys-ehdot button { border:0; background:none; padding:0 6px; color:var(--huono); }
nav button { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px; background:none;
             color:var(--linkki); font:inherit; font-size:.9rem; cursor:pointer; }
"""

# Suosikit ja etäisyys omasta sijainnista: vain selaimessa (sivu on sama kaikille ja
# CDN:n välimuistissa). Suosikit ja sijaintiluvan muistaminen localStoragessa.
SKRIPTI = """
(() => {
  const AVAIN = "melonta-suosikit", SIJ = "melonta-sijainti";
  const T = document.documentElement.lang === "en" ? {
    lisaa: "Add to favourites", poista: "Remove from favourites", km: "", paikka: "spot", paikkaa: "spots",
    kieli: "en-GB", olot: ["Poor conditions", "Fair conditions", "Good conditions", "Excellent conditions"], perilla: "on arrival", paivaTila: "Water levels and ratings from the forecast for", ukkonen: "thunderstorm forecast", foreca: "Foreca 15-day forecast (yr.no covers only 9 days)", lahto: "from", oma: "your location",
    tila: "Driving distances from your location.", lasketaan: "Calculating driving distances…",
    eiAjo: "Driving distances are not available right now. Distances are from Oulu city centre.",
    eiTukea: "Your browser does not support location.", haetaan: "Getting location…",
    eiSaatu: m => "Location not available (" + m + "). Distances are from Oulu city centre.",
    paikkakunnalta: n => "Driving distances from " + n + ".",
    tuntematon: n => "Unknown municipality: " + n + ". Pick one from the list.",
    tilaa: "Subscribe to alert", paivitaHal: "Update alert", tilataan: "Subscribing…",
    tilattu: "Alert subscribed. You should get a confirmation notification now.", peruttu: "Alert cancelled.",
    eiLupaa: "Notifications are blocked. Allow them in the browser settings for this site.",
    eiEhtoja: "Add at least one condition (+ Add).", halVirhe: "Subscribing failed: ",
    muutettu: "Changes take effect when you press Update alert.", mikaTahansa: "Any feature",
    tasot: {toimii: "works", paras: "optimum (at its best)", pisteet: "score limit"}, poistaEhto: "Remove",
    iphone: "On iPhone, first add this page to the home screen (Share → Add to Home Screen) and open it from there.",
  } : {
    lisaa: "Lisää suosikkeihin", poista: "Poista suosikeista", km: "", paikka: "paikka", paikkaa: "paikkaa",
    kieli: "fi-FI", olot: ["Heikot olot", "Kohtalaiset olot", "Hyvät olot", "Erinomaiset olot"], perilla: "perillä klo", paivaTila: "Vesitilanne ja arviot ennusteen mukaan:", ukkonen: "ukkosta ennustettu", foreca: "Forecan 15 vrk ennuste (yr.no ennustaa vain 9 päivää)", lahto: "lähtö", oma: "oma sijainti",
    tila: "Ajomatkat omasta sijainnistasi.", lasketaan: "Lasketaan ajomatkoja…",
    eiAjo: "Ajomatkoja ei saatu juuri nyt. Etäisyydet ovat Oulun keskustasta.",
    eiTukea: "Selain ei tue sijaintia.", haetaan: "Haetaan sijaintia…",
    eiSaatu: m => "Sijaintia ei saatu (" + m + "). Etäisyydet ovat Oulun keskustasta.",
    paikkakunnalta: n => "Ajomatkat paikkakunnalta " + n + ".",
    tuntematon: n => "Tuntematon paikkakunta: " + n + ". Valitse listasta.",
    tilaa: "Tilaa hälytys", paivitaHal: "Päivitä hälytys", tilataan: "Tilataan…",
    tilattu: "Hälytys tilattu. Puhelimeen pitäisi tulla nyt vahvistusilmoitus.", peruttu: "Hälytys peruttu.",
    eiLupaa: "Ilmoitukset on estetty. Salli ne selaimen asetuksista tälle sivulle.",
    eiEhtoja: "Lisää vähintään yksi ehto (+ Lisää).", halVirhe: "Tilaus epäonnistui: ",
    muutettu: "Muutokset tulevat voimaan, kun painat Päivitä hälytys.", mikaTahansa: "Mikä tahansa kohde",
    tasot: {toimii: "toimii", paras: "optimi (parhaimmillaan)", pisteet: "pisteraja"}, poistaEhto: "Poista",
    iphone: "iPhonessa lisää sivu ensin kotivalikkoon (Jaa → Lisää Koti-valikkoon) ja avaa se sieltä.",
  };
  const lue = (k, oletus) => { try { return JSON.parse(localStorage.getItem(k)) ?? oletus; } catch { return oletus; } };
  const kirjoita = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
  const rivit = [...document.querySelectorAll("tr[data-paikka]")];
  const taulukko = document.querySelector("table[data-valilehti]");
  const vainSuosikit = taulukko && taulukko.dataset.valilehti === "suosikit";
  let suosikit = new Set(lue(AVAIN, []));

  function paivita() {
    let n = 0;
    for (const r of rivit) {
      const on = suosikit.has(r.dataset.paikka);
      const nappi = r.querySelector(".suosikki");
      nappi.textContent = on ? "♥" : "♡";
      nappi.setAttribute("aria-pressed", on);
      nappi.title = on ? T.poista : T.lisaa;
      r.hidden = (vainSuosikit && !on) || !osuu(r.dataset.paikka);
      if (!r.hidden) r.querySelector(".sija").textContent = ++n + ".";
    }
    const lukumaara = document.getElementById("lukumaara");
    if (lukumaara) lukumaara.textContent = n + " " + (n === 1 ? T.paikka : T.paikkaa);
    const ohje = document.getElementById("ei-suosikkeja");
    if (ohje) ohje.hidden = !(vainSuosikit && n === 0);
    let m = 0;
    document.querySelectorAll("li[data-haku]").forEach(li => { li.hidden = !osuu(li.dataset.haku); if (!li.hidden) m++; });
    const ilman = document.getElementById("lukumaara-ilman");
    if (ilman) ilman.textContent = m + " " + (m === 1 ? T.paikka : T.paikkaa);
    const suosikkimaara = document.getElementById("suosikkimaara");
    if (suosikkimaara) suosikkimaara.textContent = suosikit.size;
  }
  // Haku: paikan nimen osa, isoilla ja pienillä kirjaimilla ei väliä
  const hakukentta = document.getElementById("haku");
  function osuu(teksti) {
    const q = hakukentta ? hakukentta.value.trim().toLowerCase() : "";
    return !q || teksti.toLowerCase().includes(q);
  }
  if (hakukentta) hakukentta.addEventListener("input", () => paivita());
  for (const r of rivit) {
    r.querySelector(".suosikki").addEventListener("click", () => {
      const nimi = r.dataset.paikka;
      suosikit.has(nimi) ? suosikit.delete(nimi) : suosikit.add(nimi);
      kirjoita(AVAIN, [...suosikit]);
      paivita();
    });
  }
  paivita();

  // Sää perillä: tuntiennuste rivillä (data-saa), saapuminen = lähtöaika (oletus nyt) + ajoaika + 30 min
  const UKKONEN = [95, 96, 99];
  const ikoni = k => k <= 1 ? "☀️" : k === 2 ? "⛅" : (k === 3 || k === 45 || k === 48) ? "☁️" : UKKONEN.includes(k) ? "⛈️" : "🌧️";
  const kello = s => new Date(s * 1000).toLocaleTimeString(T.kieli, {hour: "2-digit", minute: "2-digit", timeZone: "Europe/Helsinki"});
  const lahtoKentta = document.getElementById("lahtoaika");
  const paikallinen = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  if (lahtoKentta) {   // oletuksena nykyhetki
    const nyt = new Date();
    lahtoKentta.value = lahtoKentta.min = paikallinen(nyt);
    // lähtö viimeistään kaavioiden ennusteen viimeisenä päivänä (data-paivia, +14 pv); sääennuste 16 päivää
    const viimeinen = new Date(nyt.getFullYear(), nyt.getMonth(), nyt.getDate() + Number(lahtoKentta.dataset.paivia), 23, 45);
    lahtoKentta.max = paikallinen(viimeinen);
    // asetettu lähtöaika säilyy välilehteä vaihdettaessa (sessionStorage), jos se on vielä tulevaisuudessa
    let tallessa = null;
    try { tallessa = sessionStorage.getItem("melonta-lahtoaika"); } catch {}
    if (tallessa && new Date(tallessa) > nyt && new Date(tallessa) <= viimeinen) lahtoKentta.value = tallessa;
  }
  const lahto = () => {
    const v = lahtoKentta && lahtoKentta.value ? new Date(lahtoKentta.value).getTime() : NaN;
    return (isNaN(v) ? Date.now() : Math.max(v, Date.now())) / 1000;
  };
  function saa(r, ajoMin) {
    const el = r.querySelector(".saa[data-saa]");
    if (!el || ajoMin == null) return;
    const s = JSON.parse(el.dataset.saa), perilla = lahto() + (ajoMin + 30) * 60;
    s.aika = s.aika || s.t.map((_, j) => s.a0 + 3600 * j);
    let i = -1;
    s.aika.forEach((a, j) => { if (a <= perilla) i = j; });
    const ohi = i < 0 || perilla >= s.aika[s.aika.length - 1] + 3600;   // ennuste ei ulotu
    const aika = r.querySelector(".saa-aika"), ilma = el.querySelector(".saa-ilma"), kuva = el.querySelector(".saa-ikoni");
    if (aika) aika.textContent = T.perilla + " " + kello(perilla) + (lahto() > Date.now() / 1000 + 43200 ? " " + paiva(perilla) : "");
    // kaaviolinkit: reissun ajankohta (varttiin pyöristettynä) vedettäväksi osoittimeksi kaavioon ja
    // matka-aika, jotta osoittimen siirto palauttaa lähtöajan (osoittimen aika − matka-aika)
    r.querySelectorAll('a[href^="/kaavio/"]').forEach(a => {
      const url = new URL(a.href);
      url.searchParams.set("reissu", Math.round(perilla / 900) * 900);
      url.searchParams.set("matka", Math.round(ajoMin + 30));
      a.href = url.pathname + url.search;
    });
    if (ilma) ilma.textContent = ohi ? "–" : Math.round(s.t[i]).toString().replace("-", "−") + " °C";
    if (kuva) kuva.textContent = ohi ? "" : ikoni(s.k[i]);
    // ukkonen tiedossa saapumisesta 4 h eteenpäin: ilma-linkki punaiseksi
    const linkki = el.querySelector(".ilma-linkki");
    if (linkki) {
      const ukkonen = !ohi && s.aika.some((a, j) => a >= s.aika[i] && a < s.aika[i] + 4 * 3600 && UKKONEN.includes(s.k[j]));
      linkki.classList.toggle("ukkonen", ukkonen);
      // yr.no:n tuntiennuste saapumispäivälle (?i = päiviä tästä päivästä, Suomen aikaa);
      // yr.no ennustaa vain YR_PAIVIA päivää, joten myöhemmästä saapumisesta Forecan 15 vrk ennuste
      const YR_PAIVIA = 9;   // app.YR_PAIVIA
      const pvm = s => new Date(s * 1000).toLocaleDateString("sv-SE", {timeZone: "Europe/Helsinki"});
      const erotus = Math.round((new Date(pvm(perilla)) - new Date(pvm(Date.now() / 1000))) / 86400000);
      const foreca = erotus > YR_PAIVIA && linkki.dataset.foreca;
      const otsikko = ukkonen ? T.ukkonen : foreca ? T.foreca : "";
      otsikko ? linkki.title = otsikko : linkki.removeAttribute("title");
      linkki.dataset.yr = linkki.dataset.yr || linkki.href;   // alkuperäinen yr.no-osoite talteen
      const url = new URL(linkki.dataset.yr);
      erotus > 0 ? url.searchParams.set("i", Math.min(erotus, YR_PAIVIA)) : url.searchParams.delete("i");
      linkki.href = foreca || url.toString();
    }
  }
  const paiva = s => new Date(s * 1000).toLocaleDateString(T.kieli, {weekday: "short", day: "numeric", month: "numeric", timeZone: "Europe/Helsinki"});
  let ajoajat = null;   // null = Oulusta (rivin data-ajo), muuten valitun lähtöpaikan ajoajat
  const paivitaSaat = () => rivit.forEach(r => {
    const el = r.querySelector(".saa[data-ajo]");
    saa(r, ajoajat ? ajoajat[r.dataset.paikka] : el ? Number(el.dataset.ajo) : null);
  });
  const saaOulusta = () => { ajoajat = null; paivitaSaat(); };

  // Lähtöpäivä muu kuin tänään: vesitilanne, kohteiden arviot ja pisteet sen päivän ennusteesta,
  // paikat sen mukaiseen järjestykseen (sama sääntö kuin palvelimella: pisteet 5:n tarkkuudella, lähempi ensin)
  const paivaTila = document.getElementById("paiva-tila");
  const luokka = p => p >= 60 ? "p-hyva" : p >= 30 ? "p-keski" : "p-huono";
  function naytaPaiva() {
    if (!taulukko || !lahtoKentta) return;
    const alku = new Date(taulukko.dataset.paiva0 + "T00:00");
    const lahtoPv = lahtoKentta.value ? new Date(lahtoKentta.value.slice(0, 10) + "T00:00") : alku;
    const n = Math.max(0, Math.round((lahtoPv - alku) / 86400000));
    for (const r of rivit) {
      // lyhyempi ennuste (esim. SMHI 10 pv): sen viimeinen päivä ennen lähtöpäivää
      const p = JSON.parse(r.dataset.pisteet || "{}"), nn = Math.max(0, ...Object.keys(p).map(Number).filter(k => k <= n));
      r.querySelectorAll(".paiva").forEach(d => d.hidden = Number(d.dataset.paiva) !== nn);
      const solu = r.querySelector("td.pisteet");
      if (solu && p[nn] != null) { solu.textContent = p[nn]; solu.className = "pisteet " + luokka(p[nn]); }
      const olot = r.querySelector(".olot");
      if (olot && p[nn] != null) {
        olot.textContent = T.olot[p[nn] >= 80 ? 3 : p[nn] >= 60 ? 2 : p[nn] >= 30 ? 1 : 0];
        olot.className = "olot " + luokka(p[nn]);
      }
      r.dataset.nyt = p[nn] ?? -1;
    }
    rivit.sort((a, b) => (Math.round(b.dataset.nyt / 5) - Math.round(a.dataset.nyt / 5)) || (a.dataset.km - b.dataset.km));
    const runko = rivit[0] && rivit[0].parentElement;
    if (runko) rivit.forEach(r => runko.appendChild(r));
    paivita();
    paivaTila.textContent = n ? T.paivaTila + " " + lahtoPv.toLocaleDateString(T.kieli, {weekday: "short", day: "numeric", month: "numeric"}) : "";
    paivaTila.hidden = !n;
  }
  saaOulusta();   // sivu voi olla välimuistista: saapumisaika tämän hetken mukaan
  if (lahtoKentta) {
    lahtoKentta.addEventListener("change", () => {
      if (!lahtoKentta.value) {   // tyhjennä-nappi: takaisin nykyhetkeen
        lahtoKentta.value = paikallinen(new Date());
        try { sessionStorage.removeItem("melonta-lahtoaika"); } catch {}
      } else {
        try { sessionStorage.setItem("melonta-lahtoaika", lahtoKentta.value); } catch {}
      }
      paivitaSaat(); naytaPaiva();
    });
    naytaPaiva();   // tallessa ollut lähtöpäivä: sen päivän arviot heti
    // kaavion reissu-osoittimella valittu lähtöaika: takaisin-napilla (sivu välimuistista) tai toisesta välilehdestä
    const otaLahto = arvo => {
      if (arvo && new Date(arvo) > new Date(lahtoKentta.max)) arvo = lahtoKentta.max;   // ennusteen rajalle
      if (!arvo || arvo === lahtoKentta.value || new Date(arvo) < new Date(lahtoKentta.min)) return;
      lahtoKentta.value = arvo;
      try { sessionStorage.setItem("melonta-lahtoaika", arvo); } catch {}
      paivitaSaat(); naytaPaiva();
    };
    addEventListener("pageshow", () => { try { otaLahto(sessionStorage.getItem("melonta-lahtoaika")); } catch {} });
    // toisen välilehden muutokset: jonossa olleet ilmoitukset kootaan, ja vain viimeisin arvo otetaan käyttöön
    let odotus = null;
    addEventListener("storage", e => {
      if (e.key !== "melonta-lahtoaika") return;
      clearTimeout(odotus);
      odotus = setTimeout(() => {
        try { otaLahto(JSON.parse(localStorage.getItem("melonta-lahtoaika")).arvo); } catch {}
      }, 300);
    });
  }

  // Ajomatkat (tavallinen ajoreitti) lähtöpisteestä kaikkiin paikkoihin: /api/ajomatkat
  // laskee ne yhdellä reitityskyselyllä. Lähtöpiste pyöristetään ~1 km:n tarkkuuteen.
  const tila = document.getElementById("sijainti-tila");
  const kesto = m => m < 60 ? Math.round(m) + " min" : Math.floor(m / 60) + " h " + String(Math.round(m % 60)).padStart(2, "0") + " min";
  let kysely = 0;
  // nimi = lähtöpaikka matkatietoon (paikkakunta tai oma sijainti)
  function nayta(oma, teksti, lahto, nimi) {
    for (const r of rivit) {
      const km = r.querySelector(".km");
      if (km) { km.dataset.oulu ??= km.textContent; km.textContent = km.dataset.oulu; }
      const reitti = r.querySelector(".reitti");
      if (reitti) {
        const url = new URL(reitti.href);
        lahto ? url.searchParams.set("origin", lahto) : url.searchParams.delete("origin");
        reitti.href = url.toString();
      }
    }
    tila.textContent = oma ? T.lasketaan : "";
    tila.hidden = !oma;
    if (!oma) { saaOulusta(); return; }
    const oma2 = oma.map(v => v.toFixed(2)), tama = ++kysely;
    fetch("/api/ajomatkat?v=2&lahto=" + oma2.join(","))   // v: vastauksen muoto (ajoajat mukana)
      .then(v => v.ok ? v.json() : Promise.reject(v.status))
      .then(d => {
        if (tama !== kysely) return;   // uudempi valinta ehti ensin
        for (const r of rivit) {
          const km = r.querySelector(".km"), k = d.km[r.dataset.paikka];
          const m = d.min ? d.min[r.dataset.paikka] : null;
          if (km && k != null) km.textContent = "~" + Math.round(k) + " km" + (m != null ? " / " + kesto(m) : "") + T.km
                                                + (nimi ? ", " + T.lahto + " " + nimi : "");
        }
        ajoajat = d.min || null;
        paivitaSaat();
        tila.textContent = teksti;
      })
      .catch(() => { if (tama === kysely) tila.textContent = T.eiAjo; });
  }
  function hae() {
    if (!navigator.geolocation) { tila.textContent = T.eiTukea; tila.hidden = false; return; }
    tila.textContent = T.haetaan; tila.hidden = false;
    navigator.geolocation.getCurrentPosition(
      p => { kirjoita(SIJ, true); kentta && (kentta.value = "");
             nayta([p.coords.latitude, p.coords.longitude], T.tila, null, T.oma); },
      v => { kirjoita(SIJ, false); tila.textContent = T.eiSaatu(v.message); },
      { maximumAge: 10 * 60 * 1000, timeout: 15000 });
  }
  // Paikkakunta sijainnin sijaan: koordinaatit sivulla (paikkakunnat.py), ei lähde mihinkään
  const kentta = document.getElementById("paikkakunta");
  const kunnat = JSON.parse(document.getElementById("paikkakunnat")?.textContent || "{}");
  const avain = n => n.trim().toLocaleLowerCase("fi");
  const haku = Object.fromEntries(Object.keys(kunnat).map(n => [avain(n), n]));
  function valitse(arvo, muista) {
    if (!arvo.trim()) { kirjoita(SIJ, false); nayta(null, "", null); return; }
    const nimi = haku[avain(arvo)];
    if (!nimi) { tila.textContent = T.tuntematon(arvo.trim()); tila.hidden = false; return; }
    const [lev, pit] = kunnat[nimi];
    if (muista) kirjoita(SIJ, {paikkakunta: nimi});
    kentta.value = nimi;
    nayta([lev, pit], T.paikkakunnalta(nimi), lev + "," + pit, nimi);
  }
  if (kentta) kentta.addEventListener("change", () => valitse(kentta.value, true));
  const nappi = document.getElementById("sijainti");
  if (nappi) nappi.addEventListener("click", hae);
  const muistettu = lue(SIJ, false);
  if (muistettu && muistettu.paikkakunta && kentta) valitse(muistettu.paikkakunta, false);
  else if (muistettu === true) hae();   // lupa annettu aiemmin: päivitä suoraan
  // Hälytys hyvistä oloista: ehdot (paikka tai kohde; toimii / optimi / pisteraja) ja ennusteen pituus,
  // push-tilaus (service worker /sw.js) ja asetukset palvelimelle (/api/halytys)
  const halytys = document.getElementById("halytys");
  if (halytys && halytys.dataset.vapid && "serviceWorker" in navigator) {
    halytys.hidden = false;
    const $ = id => document.getElementById("halytys-" + id);
    const HAL = "melonta-halytys", tilaa = $("tilaa"), peru = $("peru"), halTila = $("tila"), raja = $("raja"),
          paikkaV = $("paikka"), kohdeV = $("kohde"), tasoV = $("taso"), lista = $("ehdot"), paivia = $("paivia");
    const valinnat = JSON.parse($("valinnat").textContent);
    const tuettu = "PushManager" in window && "Notification" in window;
    const asetukset = lue(HAL, null) || {};   // viimeksi tilatut ehdot ja ennusteen pituus
    let ehdot = Array.isArray(asetukset.ehdot) ? asetukset.ehdot.filter(e => valinnat[e.paikka]
      && (valinnat[e.paikka][e.kohde] || []).includes(e.taso)) : [];
    if (asetukset.paivia != null) paivia.value = asetukset.paivia;
    const lisaaVaihtoehto = (v, arvo, teksti) => v.add(new Option(teksti, arvo));
    // suosikit ensin, sitten muut sivun järjestyksessä
    Object.keys(valinnat).sort((a, b) => suosikit.has(b) - suosikit.has(a))
      .forEach(p => lisaaVaihtoehto(paikkaV, p, (suosikit.has(p) ? "♥ " : "") + p));
    function paivitaKohteet() {
      kohdeV.length = 0;
      Object.keys(valinnat[paikkaV.value] || {}).forEach(k => lisaaVaihtoehto(kohdeV, k, k || T.mikaTahansa));
      paivitaTasot();
    }
    function paivitaTasot() {
      tasoV.length = 0;
      ((valinnat[paikkaV.value] || {})[kohdeV.value] || []).forEach(t => lisaaVaihtoehto(tasoV, t, T.tasot[t]));
      $("raja-kentta").hidden = tasoV.value !== "pisteet";
    }
    paikkaV.addEventListener("change", paivitaKohteet);
    kohdeV.addEventListener("change", paivitaTasot);
    tasoV.addEventListener("change", () => { $("raja-kentta").hidden = tasoV.value !== "pisteet"; });
    paivitaKohteet();
    const kuvaus = e => e.paikka + (e.kohde ? " – " + e.kohde : "") + ": "
      + (e.taso === "pisteet" ? "≥ " + e.raja + " p" : T.tasot[e.taso]);
    let tilattu = false;
    function naytaEhdot() {
      lista.replaceChildren(...ehdot.map((e, i) => {
        const li = document.createElement("li"), pois = document.createElement("button");
        li.textContent = kuvaus(e);
        pois.type = "button"; pois.textContent = "✕"; pois.title = pois.ariaLabel = T.poistaEhto;
        pois.addEventListener("click", () => { ehdot.splice(i, 1); naytaEhdot(); muutos(); });
        li.append(pois);
        return li;
      }));
    }
    const muutos = () => { if (tilattu) halTila.textContent = T.muutettu; };
    naytaEhdot();
    $("lisaa").addEventListener("click", () => {
      const e = {paikka: paikkaV.value, kohde: kohdeV.value, taso: tasoV.value};
      if (e.taso === "pisteet") e.raja = Number(raja.value);
      const avain = JSON.stringify(e);
      if (!ehdot.some(x => JSON.stringify(x) === avain)) { ehdot.push(e); naytaEhdot(); muutos(); }
    });
    paivia.addEventListener("change", muutos);
    const avain = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - s.length % 4) % 4)),
                                       c => c.charCodeAt(0));
    const rekisteri = tuettu ? navigator.serviceWorker.register("/sw.js") : null;
    const naytaTilaus = async () => {
      const tilaus = rekisteri && await (await rekisteri).pushManager.getSubscription();
      tilattu = !!tilaus;
      peru.hidden = !tilaus;
      tilaa.textContent = tilaus ? T.paivitaHal : T.tilaa;
    };
    naytaTilaus().catch(() => {});
    const kutsu = (metodi, runko) => fetch("/api/halytys", {method: metodi,
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(runko)})
      .then(async v => { if (!v.ok) throw new Error((await v.json().catch(() => ({}))).virhe || "HTTP " + v.status); });
    tilaa.addEventListener("click", async () => {
      if (!tuettu) { halTila.textContent = T.iphone; return; }
      if (!ehdot.length) { halTila.textContent = T.eiEhtoja; return; }
      halTila.textContent = T.tilataan;
      try {
        if (await Notification.requestPermission() !== "granted") { halTila.textContent = T.eiLupaa; return; }
        const r = await rekisteri;
        const tilaus = await r.pushManager.getSubscription()
          || await r.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: avain(halytys.dataset.vapid)});
        await kutsu("POST", {tilaus: tilaus.toJSON(), ehdot, paivia: Number(paivia.value),
                             kieli: document.documentElement.lang});
        kirjoita(HAL, {ehdot, paivia: Number(paivia.value)});
        halTila.textContent = T.tilattu;
      } catch (virhe) { halTila.textContent = T.halVirhe + virhe.message; }
      naytaTilaus().catch(() => {});
    });
    peru.addEventListener("click", async () => {
      try {
        const tilaus = await (await rekisteri).pushManager.getSubscription();
        if (tilaus) { await kutsu("DELETE", {endpoint: tilaus.endpoint}); await tilaus.unsubscribe(); }
        try { localStorage.removeItem(HAL); } catch {}
        halTila.textContent = T.peruttu;
      } catch (virhe) { halTila.textContent = T.halVirhe + virhe.message; }
      naytaTilaus().catch(() => {});
    });
  }
  // kaaviot ovat oletuksena pystymallisia (puhelin); leveällä vaakanäytöllä vaakamalli
  function kaavionMuoto() {
    const vaaka = innerWidth >= 700 && innerWidth > innerHeight;
    document.querySelectorAll('a[href^="/kaavio/"]').forEach(a => {
      const url = new URL(a.href);
      if (vaaka) url.searchParams.set("muoto", "vaaka"); else url.searchParams.delete("muoto");
      a.href = url.pathname + url.search;
    });
  }
  kaavionMuoto();
  addEventListener("resize", kaavionMuoto);
})();
"""


KUNTALISTA = "".join(f'<option value="{html.escape(n)}">' for n in PAIKKAKUNNAT)
KUNNAT_JSON = json.dumps(PAIKKAKUNNAT, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

EI_SUOSIKKEJA = {
    "fi": "Ei vielä suosikkeja. Lisää paikka suosikiksi sen nimen vieressä olevasta ♡-napista – "
          "suosikit tallentuvat tähän selaimeen.",
    "en": "No favourites yet. Mark a spot as a favourite with the ♡ button next to its name – "
          "favourites are saved in this browser.",
}
# Sivun alun selitykset: merkinnät ja kuvakkeet (kajakkikuvakkeet KAJAKKI_KUVAKKEET)
SELITYKSET = {
    "fi": [("★", "parhaimmillaan"), ("✓", "toimii"), ("✗", "ei toimi"), ("♡ / ♥", "lisää suosikiksi / suosikki"),
           ("🚗", "reitti Google Mapsiin; perillä-aika sekä matkan pituus ja kesto valitusta lähtöpaikasta ja -ajasta"),
           ("🌡", "ilma ja vesi perillä; ilma-linkki vie paikan säähän, punaisena ukkosta ennustettu"),
           ("☀️ ⛅ ☁️ 🌧️ ⛈️", "aurinkoista, puolipilvistä, pilvistä, sadetta, ukkosta")],
    "en": [("★", "at its best"), ("✓", "works"), ("✗", "does not work"), ("♡ / ♥", "add to favourites / favourite"),
           ("🚗", "driving route in Google Maps; arrival time and distance from the chosen start and departure"),
           ("🌡", "air and water on arrival; the air link opens the local weather, red when a thunderstorm is forecast"),
           ("☀️ ⛅ ☁️ 🌧️ ⛈️", "sunny, partly cloudy, cloudy, rain, thunderstorm")],
}
SELITE = {
    "fi": "Kajakit: suositeltu tyyppi kohteen nimen perässä. Pisteet (0–100) kertovat, miten veden määrä "
          "osuu paikan kuvauksen optimiin; tasapisteissä lähempi paikka ensin. Tarkista aina olosuhteet "
          "paikan päällä.",
    "en": "Kayaks: recommended type after the feature name. The score (0–100) tells how well the water "
          "level matches the optimum in the spot description; on equal scores the closer spot comes first. "
          "Spot and feature names and descriptions are in Finnish. Always check conditions on site.",
}


def _selitykset(kieli: str) -> str:
    """Merkintöjen ja kuvakkeiden selitykset sivun alkuun (aiemmin osa sivun lopussa)."""
    k_ = lambda teksti: kielet.kaanna(teksti, kieli)   # noqa: E731
    merkit = "".join(f"<li><b>{e(m)}</b> {e(t)}</li>" for m, t in SELITYKSET[kieli])
    kajakit = "".join(f'<li>{_kajakki_svg(tyyppi, k_, selite=True)} {e(k_(KAJAKKI_KUVAKKEET[tyyppi][0]))}</li>'
                      for tyyppi in KAJAKKI_KUVAKKEET)
    return (f'<details class="selitykset"><summary>{e(k_("Merkinnät ja kuvakkeet"))}</summary>'
            f'<ul class="pieni">{merkit}{kajakit}</ul><p class="pieni">{SELITE[kieli]}</p></details>')
# Kielen vaihto: Ison-Britannian lippu englanniksi, Suomen lippu takaisin suomeksi
LIPUT = {
    "en": ('<svg viewBox="0 0 60 30" width="28" height="14" aria-hidden="true">'
           '<clipPath id="uk-a"><path d="M0,0v30h60v-30z"/></clipPath>'
           '<clipPath id="uk-b"><path d="M30,15h30v15zv15h-30zh-30v-15zv-15h30z"/></clipPath>'
           '<g clip-path="url(#uk-a)"><path d="M0,0v30h60v-30z" fill="#012169"/>'
           '<path d="M0,0L60,30M60,0L0,30" stroke="#fff" stroke-width="6"/>'
           '<path d="M0,0L60,30M60,0L0,30" clip-path="url(#uk-b)" stroke="#C8102E" stroke-width="4"/>'
           '<path d="M30,0v30M0,15h60" stroke="#fff" stroke-width="10"/>'
           '<path d="M30,0v30M0,15h60" stroke="#C8102E" stroke-width="6"/></g></svg>'),
    "fi": ('<svg viewBox="0 0 18 11" width="23" height="14" aria-hidden="true">'
           '<rect width="18" height="11" fill="#fff"/><rect x="5" width="3" height="11" fill="#002f6c"/>'
           '<rect y="4" width="18" height="3" fill="#002f6c"/></svg>'),
}


# Kajakkityyppien kuvakkeet (omat sivuprofiilit: meloja + runko + vesiviiva). Tyypit erottuvat värin ja
# asennon mukaan (liikennevalovärit): freestyle punainen ja ylösalaisin ilmassa veden yllä (voltti), slice
# keltainen 70 asteen kulmassa keula pystyssä (peräupotus), river runner vihreä oikein päin;
# kaikissa sama mittakaava. viewBox 0 -8 40 32.
KAJAKKI_MELOJA = ('<circle cx="20" cy="5.2" r="2.1"/><path d="M18 7.6h4l.8 6.4h-5.6Z"/>'
                  '<path d="M11.5 15.5 28.5 2.5" stroke="currentColor" stroke-width="1.1" fill="none"/>'
                  '<path d="M10.2 16.8l2.6-2.2.9 1.2-2.4 1.9ZM29.8 1.2l-2.6 2.2-.9-1.2 2.4-1.9Z"/>')
# tyyppi -> (nimi, runko, väri, asento (SVG transform), vesiviivan y)
KAJAKKI_KUVAKKEET = {
    "freestyle": ("freestyle-kajakki",
                  "M9 15.2C10.5 17.6 15 18.3 20 18.3S29.5 17.6 31 15.2C28.5 14.6 24.5 13.8 20 13.8S11.5 14.6 9 15.2Z",
                  "#e03131", "translate(0 -6) matrix(1 0 0 -1 0 20)", 17),   # voltissa ilmassa
    "slice": ("slice-kajakki (half / full slice)",   # Dagger Rewindin tapaan: täyteläinen keula, ohut perä, river runneria lyhyempi
              "M6.4 16.4C10.4 17.2 15.2 17.8 20 18.2C25.6 18.6 30.4 18.2 33.2 16.2C34.4 15.2 34.2 13 32.8 12.4"
              "C28.8 11.4 24 12.6 20 13.4C15.2 14.4 10.4 15.6 6.4 16.4Z",
              "#f08c00", "translate(21 7) rotate(-70) translate(-20 -14)", 7.7),
    "riverrunner": ("river runner -kajakki",
                    "M4.5 13.4C5 17 11 18.6 20 18.6S35 17 35.5 13.4C33 14.2 27 13.6 20 13.6S7 14.2 4.5 13.4Z",
                    "#2f9e44", "", 16.5),
}


def _kajakki_svg(tyyppi: str, k_, selite: bool = False) -> str:
    """Kajakkityypin kuvake: värillinen meloja ja runko tyypin asennossa sekä vesiviiva."""
    nimi, runko, vari, asento, vesi = KAJAKKI_KUVAKKEET[tyyppi]
    aallot = "".join("t5 0" for _ in range(7))
    kuva = (f'<path d="M0 {vesi}q2.5-1.3 5 0{aallot}" fill="none" stroke="#339af0" stroke-width="1.1"/><g fill="currentColor"{f" transform={chr(34)}{asento}{chr(34)}" if asento else ""}>'
            f'<path d="{runko}"/>{KAJAKKI_MELOJA}</g>')
    if selite:
        return f'<svg class="kajakki" viewBox="0 -8 40 32" style="color:{vari}" aria-hidden="true">{kuva}</svg>'
    return (f'<svg class="kajakki" viewBox="0 -8 40 32" style="color:{vari}" role="img" aria-label="{e(k_(nimi))}">'
            f'<title>{e(k_(nimi))}</title>{kuva}</svg>')


def _kajakit(paikka, kohde, k_) -> str:
    """Kohteelle suositeltujen kajakkityyppien kuvakkeet kohteen nimen perään (nimi vihjeenä)."""
    kuvat = "".join(_kajakki_svg(tyyppi, k_) for tyyppi in kohteen_kajakit(paikka, kohde))
    return f' <span class="kajakit">{kuvat}</span>' if kuvat else ""


def _pisteluokka(p: float) -> str:
    return "p-hyva" if p >= 60 else "p-keski" if p >= 30 else "p-huono"


def saa_perilla(saa: dict, ajo_min: float, nyt: float) -> tuple[float, float, int] | None:
    """(saapumisaika unix s, lämpötila, sääkoodi) tunnilta, jolle nyt + ajoaika + 30 min osuu."""
    perilla = nyt + (ajo_min + LISAAIKA_MIN) * 60
    i = max((i for i, a in enumerate(saa["aika"]) if a <= perilla), default=None)
    return (perilla, saa["t"][i], saa["k"][i]) if i is not None else None


def _kello(aika: float, kieli: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        hetki = dt.datetime.fromtimestamp(aika, ZoneInfo("Europe/Helsinki"))
    except Exception:  # aikavyöhyketietokanta puuttuu
        hetki = dt.datetime.fromtimestamp(aika, dt.timezone(dt.timedelta(hours=2)))
    return hetki.strftime("%H:%M" if kieli == "en" else "%H.%M")


YR_SAA = "https://www.yr.no/en/forecast/hourly-table/{lev},{pit}"
YR_PAIVIA = 9   # yr.no:n tuntitaulukko ulottuu tästä päivästä 9 päivän päähän (?i=0…9)


def yr_osoite(lev: float, pit: float, aika: float | None = None, nyt: float | None = None) -> str:
    """yr.no:n tuntiennuste paikalle; ?i=N avaa ajankohdan päivän (0 = tänään, Suomen aikaa),
    yr.no:n ennusteen ulkopuolella sen viimeisen päivän."""
    osoite = YR_SAA.format(lev=lev, pit=pit)
    if aika is None:
        return osoite
    paiva = lambda s: dt.datetime.fromtimestamp(s, dt.timezone(dt.timedelta(hours=3))).date()   # noqa: E731
    try:
        from zoneinfo import ZoneInfo
        paiva = lambda s: dt.datetime.fromtimestamp(s, ZoneInfo("Europe/Helsinki")).date()   # noqa: E731
    except Exception:  # aikavyöhyketietokanta puuttuu
        pass
    erotus = (paiva(aika) - paiva(nyt or time.time())).days
    return osoite + (f"?i={min(erotus, YR_PAIVIA)}" if erotus > 0 else "")


FORECA_SAA = "https://www.foreca.fi/{maa}/{kunta}/15vrk"


def foreca_osoite(paikka) -> str | None:
    """Forecan 15 vuorokauden ennuste paikkaa lähimmälle saman maan kunnalle (yr.no:n 9 päivän jälkeen)."""
    if not paikka.sijainti:
        return None
    lev, pit = paikka.sijainti
    kunnat = [n for n in PAIKKAKUNNAT if (n in RUOTSI) == (paikka.maa == "SE")]
    kunta = min(kunnat, key=lambda n: (PAIKKAKUNNAT[n][0] - lev) ** 2
                + ((PAIKKAKUNNAT[n][1] - pit) * math.cos(math.radians(lev))) ** 2)
    return FORECA_SAA.format(maa="Sweden" if paikka.maa == "SE" else "Finland",
                             kunta=quote(kunta.removesuffix(" (Ruotsi)")))


def _lampotilat(t, saa: dict | None, ajo_min: float | None, k_, kieli: str, nyt: float) -> tuple[str, str]:
    """(saapumisaika, lämpörivi): 'perillä klo 12.40' reittilinkin perään ja omalle rivilleen
    '🌡 ilma −1 °C ⛅ · vesi 4.6 °C'. Ilma ja sää saapumishetkeltä (ajoaika Oulusta + 30 min;
    selain laskee uudelleen lähtöpaikan mukaan), vesi mittariaseman vesistömallista. Sana
    "ilma" vie paikan tuntiennusteeseen (yr.no)."""
    vesi = next((l.veden_lampotila for avain in t.paikka.mittarit
                 if (l := t.lukemat.get(avain)) is not None and l.veden_lampotila is not None), None)
    tiedot = ""
    if saa:
        pakattu = {"a0": saa["aika"][0], "t": saa["t"], "k": saa["k"]}   # tunnit peräkkäin
        tiedot += f" data-saa='{html.escape(json.dumps(pakattu, separators=(',', ':')))}'"
    if ajo_min is not None:
        tiedot += f' data-ajo="{ajo_min:.0f}"'
    perilla = saa_perilla(saa, ajo_min, nyt) if saa and ajo_min is not None else None
    ilma_linkki = k_("ilma")
    if t.paikka.sijainti:
        osoite = yr_osoite(*t.paikka.sijainti, perilla[0] if perilla else None, nyt)
        ukkonen = bool(perilla) and ukkosta(saa, perilla[0])
        luokka = ' class="ilma-linkki ukkonen"' if ukkonen else ' class="ilma-linkki"'
        vihje = f' title="{e(k_("ukkosta ennustettu"))}"' if ukkonen else ""
        foreca = foreca_osoite(t.paikka)   # selain vaihtaa linkin siihen yr.no:n ennusteen jälkeen
        ilma_linkki = (f'<a{luokka}{vihje} href="{e(osoite)}" data-foreca="{e(foreca)}" target="_blank" '
                       f'rel="noopener">{ilma_linkki}</a>')
    ilma, saapuminen = "", ""
    if perilla:
        aika, lampo, koodi = perilla
        lampo_teksti = f"{lampo:.0f} °C".replace("-", "−")
        saapuminen = f'<span class="saa-aika">{k_("perillä klo")} {_kello(aika, kieli)}</span>'
        ilma = (f'{ilma_linkki} <span class="saa-ilma">{lampo_teksti}</span> '
                f'<span class="saa-ikoni">{saa_ikoni(koodi)}</span>')
    osat = ([ilma] if ilma else []) + ([f"{k_('vesi')} {vesi:.1f} °C"] if vesi is not None else [])
    rivi = f'<span class="saa"{tiedot}>🌡 {" · ".join(osat)}</span>' if osat or tiedot else ""
    return saapuminen, rivi


def _paikan_rivi(sija: int, t, kieli: str = "fi", saa: dict | None = None, ajo_min: float | None = None,
                 nyt: float | None = None, ajo_km: float | None = None, kuva: dict | None = None) -> str:
    p = t.paikka
    k_ = lambda teksti: kielet.kaanna(teksti, kieli)   # noqa: E731
    def mittarit(paiva: int) -> str:
        nakyvat, rivit = [], []
        for avain in p.mittarit:
            l = t.lukemat.get(avain)
            if l and l.url not in nakyvat:
                nakyvat.append(l.url)
                teksti = melonta.kuvaa_lukema(l) if paiva == 0 else melonta.kuvaa_ennuste(l, paiva)
                if teksti:
                    href = kaavion_osoite(p, avain, l, kieli) or l.url
                    rivit.append(f'<li><a href="{e(href)}">{e(k_(teksti))}</a></li>')
        return "".join(rivit)

    def kohde(k) -> str:
        return (f"<li>{melonta._tila_merkki(k.tila)} <b>{e(k.kohde.nimi)}</b>{_kajakit(p, k.kohde, k_)}: "
                f"{e(k_(k.selitys))}</li>")

    def kohteet(lista: list, huomiot: str) -> str:
        jarjestetty = sorted(lista, key=lambda k: k.pisteet, reverse=True)
        # kaikki toimivat kohteet näkyvissä, toimimattomat piilossa
        toimivat = [k for k in jarjestetty if k.tila != "ei toimi"]
        muut = [k for k in jarjestetty if k.tila == "ei toimi"]
        lyhyet = toimivat
        lisat = ""
        if muut:
            lisat = (f"<details><summary>{k_('Eivät toimi nyt')} ({len(muut)})</summary><ul>"
                     + "".join(kohde(k) for k in muut) + "</ul></details>")
        return f"<ul>{''.join(kohde(k) for k in lyhyet)}{huomiot}</ul>{lisat}"

    # Päivä 0 = tänään; 1–14 = ennuste (selain näyttää lähtöpäivän version, kaavioita ei muuteta)
    huomiot = "".join(f'<li class="huom">! {e(k_(h))}</li>' for h in t.huomiot)
    paivat = {0: (t.kohteet, t.pisteet, huomiot)}
    paivat.update({n: (t.ennusteen_kohteet[n], t.ennuste[n], "") for n in sorted(t.ennuste)
                   if n in t.ennusteen_kohteet})
    versiot = "".join(f'<div class="paiva" data-paiva="{n}"{"" if n == 0 else " hidden"}>\n'
                      f'<ul class="pieni">{mittarit(n)}</ul>\n{kohteet(lista, huom)}</div>'
                      for n, (lista, _, huom) in paivat.items())
    pisteet_json = json.dumps({n: round(pist) for n, (_, pist, _) in paivat.items()}, separators=(",", ":"))
    ennuste = " / ".join(f"{t.ennuste[n]:.0f}" for n in sorted(t.ennuste)) or "–"
    if ajo_km is not None and ajo_min is not None:   # reititetty ajomatka ja -aika Oulusta
        km = f'<span class="km">~{ajo_km:.0f} km / {_kesto(ajo_min)}, {k_("lähtö")} Oulu</span>'
    else:
        km = f'<span class="km">~{p.km_oulusta} {k_("km Oulusta")}</span>' if p.km_oulusta is not None else ""
    sijainti = f' data-sijainti="{p.sijainti[0]},{p.sijainti[1]}"' if p.sijainti else ""
    # Google Mapsin ajoreitti; lähtöpiste on oma sijainti (Google) tai valittu paikkakunta (selain lisää)
    reitti = ""
    if p.sijainti:
        osoite = "https://www.google.com/maps/dir/?" + urlencode(
            {"api": 1, "destination": f"{p.sijainti[0]},{p.sijainti[1]}", "travelmode": "driving"})
        reitti = (f'<a class="reitti" href="{e(osoite)}" target="_blank" rel="noopener">'
                  f'{k_("🚗 Reitti")}</a>')
    # nimen alle: reittilinkki · perillä klo · km / kesto; seuraavalle riville lämpötilat
    saapuminen, lampo = _lampotilat(t, saa, ajo_min, k_, kieli, nyt or time.time())
    lampo = f'\n<div class="pieni lampotilat">{lampo}</div>' if lampo else ""
    matka = " · ".join(x for x in (reitti, saapuminen) if x)
    matka = f'\n<div class="pieni matka">{matka}</div>' if matka else ""
    return f"""<tr data-paikka="{e(p.nimi)}"{sijainti} data-pisteet='{pisteet_json}' data-km="{p.km_oulusta or 0}">
<td class="sija">{sija}.</td>
<td>{_kortti(p, kuva, kieli, km, _olot(t.pisteet, kieli))}
<details class="tiedot"><summary>{k_("Näytä tiedot")}</summary>{matka}{lampo}
{versiot}</details></td>
<td class="pisteet {_pisteluokka(t.pisteet)}">{t.pisteet:.0f}</td>
<td class="ennuste piilo">{ennuste}</td>
</tr>"""


OLOT = {"fi": ("Heikot olot", "Kohtalaiset olot", "Hyvät olot", "Erinomaiset olot"),
        "en": ("Poor conditions", "Fair conditions", "Good conditions", "Excellent conditions")}


def _olot(pisteet: float | None, kieli: str) -> str:
    """Kortin tilamerkki: samat rajat kuin hälytyksissä (80 / 60 / 30 pistettä)."""
    if pisteet is None:
        return ""
    taso = 3 if pisteet >= 80 else 2 if pisteet >= 60 else 1 if pisteet >= 30 else 0
    return f'<span class="olot {_pisteluokka(pisteet)}">{OLOT["en" if kieli == "en" else "fi"][taso]}</span>'


def _kortti(paikka, kuva: dict | None, kieli: str, km: str = "", merkki: str = "", suosikki: bool = True) -> str:
    """Kohteen kortti: iso kuva (paikan oma tai sovelluksen kuva), nimi, suosikki, tilamerkki, tyyppi ja matka."""
    k_ = lambda teksti: kielet.kaanna(teksti, kieli)   # noqa: E731
    osoite = paikan_osoite(paikka, kieli)
    kuva_url = kuva["pieni"] if kuva else sovellus.kuvake_osoite(512)
    tiedot = " · ".join(x for x in (e(k_(paikka.tyyppi)).capitalize(), km) if x)
    return (f'<div class="kortti"><a class="kortti-kuva" href="{e(osoite)}" tabindex="-1" aria-hidden="true">'
            f'<img src="{e(kuva_url)}" alt="" loading="lazy" width="112" height="112"></a>'
            f'<div class="kortti-tiedot"><div class="nimi"><a href="{e(osoite)}">{e(paikka.nimi)}</a>'
            + (f'<button type="button" class="suosikki" aria-pressed="false" title="{k_("Lisää suosikkeihin")}">♡</button>'
               if suosikki else "") + '</div>'
            f'{merkki}<div class="pieni">{tiedot}</div></div></div>')


def kuvaosio(nimi: str, kieli: str) -> str:
    """Paikkasivun kuva ja sen tekijä, lisenssi ja lähde (Wikimedia Commons)."""
    kuva = kuvat.kuva(nimi, _kanta())
    if not kuva:
        return ""
    selite = "Photo" if kieli == "en" else "Kuva"
    return (f'<figure class="paikkakuva"><img src="{e(kuva["kuva"])}" alt="{e(nimi)}" loading="lazy">'
            f'<figcaption>{selite}: {e(kuva["tekija"])} · {e(kuva["lisenssi"])} · '
            f'<a href="{e(kuva["sivu"])}" target="_blank" rel="noopener">Wikimedia Commons</a></figcaption></figure>')


def _lukumaara(n: int, k_) -> str:
    return f"{n} {k_('paikka') if n == 1 else k_('paikkaa')}"


def _turvaosio(tilanne: Tilanne, kieli: str) -> str:
    """Turvallisuusvaroitukset (kylmä vesi, maatuuli, matala merivesi) avattavana osiona
    merkintöjen yläpuolella: kiinni ollessa näkyvät varoitusten otsikot punaisella, avattuna
    koko teksti. Ei mitään, kun varoitettavaa ei ole."""
    joet = [l.veden_lampotila for t in tilanne.tulokset if t.paikka.maa == "FI"
            for l in t.lukemat.values() if l is not None and l.veden_lampotila is not None]
    viestit = turvallisuus.viestit(tilanne.turva, joet, kieli, _ajankohta)
    if not viestit:
        return ""
    en = kieli == "en"
    otsikot = "".join(f'<span class="turva-otsikko">{e(o)}</span>' for o, _ in viestit)
    tekstit = "".join(f"<h3>{e(o)}</h3><p>{e(t)}</p>" for o, t in viestit)
    lahde = ("Sources: Finnish Meteorological Institute (Oulu Toppila), SYKE." if en else
             "Lähteet: Ilmatieteen laitos (Oulu Toppila), SYKE.")
    return (f'<details class="turva"><summary>{otsikot}</summary>{tekstit}'
            f'<p class="pieni">{lahde}</p></details>')


def _osoite(**parametrit) -> str:
    """Sivun osoite annetuilla kyselyparametreilla (tyhjät jätetään pois, oletuskieli ei näy)."""
    parametrit = {k: v for k, v in parametrit.items() if v and not (k == "kieli" and v == "fi")}
    return "/" + ("?" + urlencode(parametrit) if parametrit else "")


def sivu(tilanne: Tilanne, tulokset: list, kysely: dict[str, list[str]]) -> str:
    valittu = kysely.get("tyyppi", [""])[0]
    kieli = kielet.kieli(kysely)
    k_ = lambda teksti: kielet.kaanna(teksti, kieli)   # noqa: E731
    def maara(arvo: str) -> str:
        if arvo == "suosikit":   # suosikit ovat selaimessa: skripti täyttää määrän
            return ' <span class="maara" id="suosikkimaara"></span>'
        return f' <span class="maara">{sum(1 for p in kaikki_paikat() if nakyy(p, arvo or None))}</span>'
    suodattimet = "".join(
        f'<a href="{e(_osoite(tyyppi=arvo, kieli=kieli))}"{" class=valittu" if valittu == arvo else ""}>'
        f'{k_(nimi)}{maara(arvo)}</a>'
        for arvo, nimi in [("", "Kaikki"), ("peli", "Pelipaikat"), ("retki", "Retket"), ("ruotsi", "Ruotsi"),
                           ("suosikit", "♥ Suosikit")]) + (
        f'<a href="/muut">{k_("Muut kohteet")} <span class="maara">{len(muut_kohteet.KOHTEET)}</span></a>')
    toinen = "fi" if kieli == "en" else "en"
    vaihto = (f'<a class="kieli" href="{e(_osoite(tyyppi=valittu, kieli=toinen))}" hreflang="{toinen}" '
              f'lang="{toinen}">{LIPUT[toinen]}{"Suomeksi" if toinen == "fi" else "In English"}</a>')
    arvioidut = [t for t in tulokset if t.pisteet is not None]
    rivit = "".join(_paikan_rivi(i, t, kieli, tilanne.saa.get(t.paikka.nimi), tilanne.ajo_min.get(t.paikka.nimi),
                                 ajo_km=tilanne.ajo_km.get(t.paikka.nimi), kuva=tilanne.kuvat.get(t.paikka.nimi))
                    for i, t in enumerate(arvioidut, 1))
    ilman = [t for t in tulokset if t.pisteet is None]
    ilman_html = ""
    TARKISTA = {k: f'<span class="olot p-keski">{v}</span>' for k, v in
                (("fi", "Vesitiedot tarkistettava"), ("en", "Check the water yourself"))}
    if ilman:
        ilman_html = (f"<h2>{k_('Ei vesikaaviota – tarkista itse')}</h2>"
                      f'<p class="lukumaara" id="lukumaara-ilman">{_lukumaara(len(ilman), k_)}</p><ul class="kortit">' + "".join(
            f'<li data-haku="{e(t.paikka.nimi)}">'
            f'{_kortti(t.paikka, tilanne.kuvat.get(t.paikka.nimi), kieli, merkki=TARKISTA[kieli], suosikki=False)}'
            f'<p class="pieni">{e(t.paikka.kuvaus)}</p></li>'
            for t in ilman) + "</ul>")
    varoitukset = ""
    if tilanne.varoitukset:
        varoitukset = (f'<h2>{k_("Huomautukset")}</h2><ul class="pieni">'
                       + "".join(f"<li>{e(v)}</li>" for v in tilanne.varoitukset) + "</ul>")
    return f"""<!doctype html>
<html lang="{kieli}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{k_("Melontatilanne")}</title>
<link rel="manifest" href="{e(sovellus.manifest_osoite(kieli))}">
<meta name="theme-color" content="{sovellus.TEEMA}">
<link rel="icon" type="image/png" href="{sovellus.kuvake_osoite(192)}">
<link rel="apple-touch-icon" href="{sovellus.kuvake_osoite(180)}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{k_("Melonta")}">
<style>{TYYLI}</style>
</head>
<body><main class="etusivu">
<div class="otsake"><h1>{k_("Melontapaikkojen tilanne")} {tilanne.paivitetty:%d.%m.%Y}</h1>{vaihto}</div>
<div class="surffirivi">{surffilinkki(tilanne.surffi, k_, kieli)}</div>
{_turvaosio(tilanne, kieli)}
<div class="tyokalut">
{_selitykset(kieli)}
<details class="valinnat"><summary>{k_("📍 Sijainti ja lähtöaika")}</summary>
<p><button type="button" id="sijainti">{k_("📍 Etäisyydet omasta sijainnista")}</button></p>
<p><label class="paikkakunta">{k_("tai paikkakunta")} <input id="paikkakunta" list="kunnat" autocomplete="off"
placeholder="{k_("esim. Rovaniemi")}"></label></p>
<p><label class="paikkakunta">{k_("lähtöaika")} <input id="lahtoaika" type="datetime-local" step="900" data-paivia="{LAHTO_PAIVIA}"></label></p>
</details>
{_halytysosio(k_)}
{_ehdotusluukku(kieli)}
</div>
<label class="haku">🔍 <input id="haku" type="search" autocomplete="off" placeholder="{k_("Hae paikkaa…")}"
aria-label="{k_("Hae paikkaa…")}"></label>
<nav>{suodattimet}</nav>
<datalist id="kunnat">{KUNTALISTA}</datalist>
<script type="application/json" id="paikkakunnat">{KUNNAT_JSON}</script>
<p id="sijainti-tila" class="pieni" hidden></p>
<p id="ei-suosikkeja" hidden>{EI_SUOSIKKEJA[kieli]}</p>
<p id="paiva-tila" class="pieni" hidden></p>
<table data-valilehti="{e(valittu)}" data-paiva0="{tilanne.paivitetty:%Y-%m-%d}">
<thead><tr><th></th><th>{k_("Paikka")}<div class="lukumaara" id="lukumaara">{_lukumaara(len(arvioidut), k_)}</div></th><th>{k_("Pisteet")}</th><th class="piilo">{k_("+1 … +14 pv")}</th></tr></thead>
<tbody>{rivit}</tbody>
</table>
{ilman_html}
{varoitukset}
{f'<p class="pieni">{k_("Kuvat: Wikimedia Commons (vapaat lisenssit); tekijä ja lisenssi paikan sivulla.")}</p>' if tilanne.kuvat else ""}
</main>
<script>{SKRIPTI}</script>
</body>
</html>"""


def _halytysosio(k_) -> str:
    """Hälytyksen tilaus (näkyy, kun selain tukee push-ilmoituksia ja VAPID-avain on saatavilla).
    Selain rakentaa valinnat paikoista ja kohteista (#halytys-valinnat: paikka -> kohde -> ehdot)."""
    avainpari = halytykset.avaimet()
    if not avainpari:
        return ""
    rajat = "".join(f'<option value="{r}"{" selected" if r == 60 else ""}>{r} – {k_(nimi)}</option>'
                    for r, nimi in ((80, "erinomainen"), (60, "hyvä"), (30, "kohtalainen")))
    paivat = "".join(f'<option value="{n}"{" selected" if n == 3 else ""}>'
                     f'{k_("tänään") if n == 0 else f"{n} " + k_("pv")}</option>' for n in range(LAHTO_PAIVIA + 1))
    valinnat = json.dumps(halytykset.valittavat(kaikki_paikat()), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<details id="halytys" class="halytys" hidden data-vapid="{e(avainpari[0])}">
<summary>{k_("🔔 Hälytys kohteen toimivuudesta")}</summary>
<p class="pieni">{k_("Ilmoitus puhelimeen, kun valitsemasi paikan tai kohteen ehto täyttyy tänään tai ennusteessa. Tarkistus joka aamu; samasta ehdosta uudelleen vasta, kun se on välillä lakannut täyttymästä.")}</p>
<p><label>{k_("Paikka")} <select id="halytys-paikka"></select></label>
<label>{k_("Kohde")} <select id="halytys-kohde"></select></label>
<label>{k_("Ehto")} <select id="halytys-taso"></select></label>
<label id="halytys-raja-kentta" hidden>{k_("Pisteraja")} <select id="halytys-raja">{rajat}</select></label>
<button type="button" id="halytys-lisaa">{k_("+ Lisää")}</button></p>
<ul id="halytys-ehdot" class="halytys-ehdot"></ul>
<p><label>{k_("Ennustetta eteenpäin")} <select id="halytys-paivia">{paivat}</select></label></p>
<p><button type="button" id="halytys-tilaa">{k_("Tilaa hälytys")}</button>
<button type="button" id="halytys-peru" hidden>{k_("Peru tilaus")}</button></p>
<p id="halytys-tila" class="pieni" aria-live="polite"></p>
<script type="application/json" id="halytys-valinnat">{valinnat}</script>
</details>"""


OSRM_TAULUKKO = "https://router.project-osrm.org/table/v1/driving/{pisteet}?sources=0&annotations=distance,duration"
AJOMATKA_CACHE = "public, max-age=86400, s-maxage=604800"
_ajomatkat: dict[tuple[float, float], dict[str, dict[str, float]]] = {}


def ajomatkat(lahto: str, hakija: osm.Hakija | None = None) -> tuple[str, dict]:
    """Ajomatkat (km) ja -ajat (min) lähtöpisteestä 'lev,pit' kaikkiin paikkoihin OSRM:n taulukkokyselyllä
    (OpenStreetMap-reititys, tavallinen ajoreitti). Lähtöpiste pyöristetään 0.01°:een, jotta
    tarkka sijainti ei lähde eteenpäin ja tulokset voidaan pitää muistissa."""
    try:
        lev, pit = (round(float(v), 2) for v in lahto.split(","))
    except ValueError:
        return "400 Bad Request", {"virhe": "lahto=lev,pit puuttuu tai on virheellinen"}
    if not (54 <= lev <= 71 and 4 <= pit <= 35):
        return "400 Bad Request", {"virhe": "lähtöpiste on liian kaukana"}
    paikat = [p for p in kaikki_paikat() if p.sijainti]
    if (lev, pit, len(paikat)) not in _ajomatkat:
        pisteet = ";".join(f"{x[1]},{x[0]}" for x in [(lev, pit)] + [p.sijainti for p in paikat])
        data, virhe = osm.hae_turvallisesti(hakija or osm.Hakija(aikaraja=15), OSRM_TAULUKKO.format(pisteet=pisteet))
        try:
            vastaus = json.loads(data.decode("utf-8")) if data else {}
            matkat = vastaus["distances"][0][1:]
            ajat = (vastaus.get("durations") or [[None] * (len(matkat) + 1)])[0][1:]
        except (ValueError, KeyError, IndexError, TypeError):
            matkat = None
        if not matkat:
            return "503 Service Unavailable", {"virhe": f"reitityspalvelu ei vastannut: {virhe or 'virheellinen vastaus'}"}
        if len(_ajomatkat) > 2000:
            _ajomatkat.clear()
        _ajomatkat[(lev, pit, len(paikat))] = {
            "km": {p.nimi: round(m / 1000, 1) for p, m in zip(paikat, matkat) if m is not None},
            "min": {p.nimi: round(s / 60) for p, s in zip(paikat, ajat) if s is not None}}
    return "200 OK", {"lahto": [lev, pit], **_ajomatkat[(lev, pit, len(paikat))]}


def _cron_kanta(environ):
    """Vercel Cronin tunnisteen tarkistus ja Firestore: (kanta, None) tai (None, (status, virhe))."""
    salaisuus = os.environ.get("CRON_SECRET", "")
    if not salaisuus:
        return None, ("503 Service Unavailable", {"virhe": "CRON_SECRET puuttuu"})
    if not hmac.compare_digest(environ.get("HTTP_AUTHORIZATION", "").encode("utf-8", "surrogateescape"),
                               f"Bearer {salaisuus}".encode("utf-8")):
        return None, ("401 Unauthorized", {"virhe": "väärä tai puuttuva tunniste"})
    try:
        kanta = firestore.Firestore.ymparistosta()
    except (ValueError, KeyError, OSError) as e:
        return None, ("503 Service Unavailable", {"virhe": f"FIREBASE_SERVICE_ACCOUNT ei kelpaa: {e!r}"})
    if not kanta:
        return None, ("503 Service Unavailable", {"virhe": "FIREBASE_SERVICE_ACCOUNT puuttuu"})
    return kanta, None


def halyta(environ) -> tuple[str, dict]:
    """Vercel Cron aamuisin: hälytykset paikoista, joiden pisteet nousevat tilaajan rajaan.
    Jokaisesta ajosta kirjoitetaan yhteenveto Vercelin lokiin (rivi alkaa "halyta:")."""
    alku = time.monotonic()
    status, tulos = _halyta(environ)
    print("halyta: " + json.dumps({"status": status, "kesto_s": round(time.monotonic() - alku, 1), **tulos},
                                  ensure_ascii=False), flush=True)
    return status, tulos


def _halyta(environ) -> tuple[str, dict]:
    kanta, virhe = _cron_kanta(environ)
    if virhe:
        return virhe
    # Sivutoiminto: Maalismaan tuntimittausten keruu talteen (ei näytetä sovelluksessa)
    kerays = kapsi.keraa(kanta, suomen_aika().isoformat(timespec="seconds"))
    status, tulos = _halyta_kannalla(kanta)
    return status, {**tulos, "kapsi": kerays}


def _halyta_kannalla(kanta) -> tuple[str, dict]:
    avainpari = halytykset.avaimet(kanta)
    if not avainpari:
        return "503 Service Unavailable", {"virhe": "VAPID-avaimia ei saatu"}
    tilanne = hae_tilanne()
    if not tilanne.lukemia:
        return "502 Bad Gateway", {"virhe": "tilannetta ei saatu laskettua", "varoitukset": tilanne.varoitukset}
    try:
        tulos = halytykset.aja(kanta, tilanne.tulokset, tilanne.paivitetty.date(), avainpari)
    except (firestore.FirestoreVirhe, OSError) as e:
        return "502 Bad Gateway", {"virhe": f"Firestore: {e}"}
    return "200 OK", tulos


def halytys_api(environ, metodi: str) -> tuple[str, dict]:
    """Selaimen hälytystilaus: POST {tilaus, ehdot, paivia, kieli} tallentaa (ja lähettää
    vahvistusilmoituksen), DELETE {endpoint} poistaa. GET kertoo, ovatko hälytykset käytössä
    ja miksi eivät (sivun hälytysosio näkyy vain, kun ne ovat)."""
    if metodi in ("GET", "HEAD"):
        kaytossa = halytykset.avaimet(uudelleen=True) is not None
        return "200 OK", {"kaytossa": kaytossa, "avaimet": halytykset.avainten_tila}
    if metodi not in ("POST", "DELETE"):
        return "405 Method Not Allowed", {"virhe": "vain GET, POST tai DELETE"}
    try:
        pituus = int(environ.get("CONTENT_LENGTH") or 0)
        if not 0 < pituus <= 8192:
            raise ValueError
        data = json.loads(environ["wsgi.input"].read(pituus))
    except (ValueError, KeyError):
        return "400 Bad Request", {"virhe": "virheellinen pyyntö"}
    try:
        kanta = firestore.Firestore.ymparistosta()
    except (ValueError, KeyError, OSError):
        kanta = None
    avainpari = halytykset.avaimet(kanta) if kanta else None
    if not avainpari:
        return "503 Service Unavailable", {"virhe": "hälytykset eivät ole käytössä"}
    try:
        if metodi == "DELETE":
            endpoint = data.get("endpoint") if isinstance(data, dict) else None
            if not isinstance(endpoint, str):
                return "400 Bad Request", {"virhe": "endpoint puuttuu"}
            kanta.poista(halytykset.KOKOELMA, halytykset.tunniste(endpoint))
            return "200 OK", {"poistettu": True}
        tilaus, virhe = halytykset.tarkista_tilaus(data, halytykset.valittavat(kaikki_paikat()))
        if not tilaus:
            return "400 Bad Request", {"virhe": virhe}
        tila = halytykset.laheta(tilaus, halytykset.vahvistus(tilaus), avainpari)
        if not 200 <= tila < 300:
            return "502 Bad Gateway", {"virhe": f"push-palvelu vastasi {tila}"}
        kanta.kirjoita(halytykset.KOKOELMA, halytykset.tunniste(tilaus["endpoint"]), tilaus)
    except (firestore.FirestoreVirhe, OSError) as e:
        return "502 Bad Gateway", {"virhe": f"Firestore: {e}"}
    return "200 OK", {"tilattu": True}


def arkistoi(environ) -> tuple[str, dict]:
    """Vercel Cron: kokoaa päivän ennustearkiston ja tallentaa sen Firestoreen."""
    kanta, virhe = _cron_kanta(environ)
    if virhe:
        return virhe
    nyt = suomen_aika()
    kerays = kapsi.keraa(kanta, nyt.isoformat(timespec="seconds"))   # Maalismaan tuntimittaukset talteen
    status, tulos = _arkistoi_kannalla(kanta, nyt)
    return status, {**tulos, "kapsi": kerays}


def _arkistoi_kannalla(kanta, nyt: dt.datetime) -> tuple[str, dict]:
    ajot, virheet = ennustearkisto.hae_ajot()
    arkisto = ennustearkisto.kokoa(ajot, nyt, virheet)
    onnistuneet = ennustearkisto.onnistuneet(arkisto)
    if not onnistuneet:
        return "502 Bad Gateway", {"virhe": "yhtään asemaa ei saatu", "varoitukset": virheet}
    tunniste = nyt.date().isoformat()
    try:
        kanta.kirjoita(ennustearkisto.KOKOELMA, tunniste, arkisto)
    except (firestore.FirestoreVirhe, OSError) as e:
        return "502 Bad Gateway", {"virhe": f"Firestore: {e}"}
    return "200 OK", {"tallennettu": f"{ennustearkisto.KOKOELMA}/{tunniste}", "asemia": len(onnistuneet),
                      "arvioita": len(arkisto["arviot"]), "varoitukset": virheet}


def kapsi_kerays(environ) -> tuple[str, dict]:
    """Vercel Cron (useita kertoja vuorokaudessa, ks. vercel.json): Maalismaan tuntimittaukset
    kapsin raportista Firestoreen (kapsi.py). Yhteenveto Vercelin lokiin ("kapsi: ...")."""
    kanta, virhe = _cron_kanta(environ)
    if virhe:
        status, tulos = virhe
    else:
        tulos = kapsi.keraa(kanta, suomen_aika().isoformat(timespec="seconds"))
        status = "502 Bad Gateway" if "virhe" in tulos else "200 OK"
    print("kapsi: " + json.dumps({"status": status, **tulos}, ensure_ascii=False), flush=True)
    return status, tulos


def _arvioasema(kaavio: str) -> str | None:
    """'61/q6101750y/qin3lyhyt.png' -> '61/q6101750y', jos asemalla on arviomalli."""
    asema = "/".join(kaavion_asema(kaavio))
    return asema if asema in syke_data.ARVIOMALLIT and not kaavio.startswith("smhi/") else None


def kaavion_asema(kaavio: str) -> list[str]:
    return kaavio.split("/")[:2]


def kaavion_osoite(paikka, avain: str, lukema=None, kieli: str = "fi") -> str | None:
    """Itse piirretyn kaavion osoite (None = linkitetään SYKE:n kuva). SMHI:ltä saadaan vain
    JSON-dataa. SYKE:n mittareille piirretään oma kuva ajo.jsonista, kun sen luvut täsmäsivät
    SYKE:n kuvaan (tietolahde ei ole "kaavio") – silloin kohteiden rajat ovat samassa
    korkeusjärjestelmässä; muuten (esim. järven tulovirtaama, jota ajo.jsonissa ei ole) sarjat
    luetaan SYKE:n kaaviokuvasta (lahde=kuva)."""
    kaavio = paikka.mittarit[avain].kaavio
    parametrit = {"paikka": paikka.nimi, **({"kieli": kieli} if kieli != "fi" else {})}
    if kaavio.startswith("smhi/"):
        return f"/kaavio/{kaavio}?{urlencode(parametrit)}"
    if lukema is not None and lukema.suure not in ("virtaama", "vedenkorkeus"):
        return None
    if not _arvioasema(kaavio):
        if lukema is None:
            return None
        if lukema.tietolahde == "kaavio" or not syke_data._sarjat(kaavio):
            parametrit["lahde"] = "kuva"
    return f"/kaavio/syke/{kaavio.removesuffix('.png')}?{urlencode(parametrit)}"


def _alueet(paikka, avain: str, tunnusluvut: dict[str, float] | None = None) -> list:
    """Paikan kohteiden rajat mittarin arvoina. Tulvaindeksin rajat (0 = MNQ/MNW, 1 = MHQ/MHW,
    ks. Kaaviolukema.tulvaindeksi) muunnetaan arvoiksi, kun tunnusluvut tiedetään."""
    tunnusluvut = tunnusluvut or {}
    ala = tunnusluvut.get("MNW", tunnusluvut.get("MNQ"))
    yla = tunnusluvut.get("MHW", tunnusluvut.get("MHQ"))
    alueet = []
    for k in paikka.kohteet:
        if k.mittari != avain:
            continue
        if k.muuttuja == "arvo":
            alueet.append((k.nimi, k.toimii, k.paras))
        elif ala is not None and yla is not None and yla > ala:
            arvoksi = lambda raja: tuple(None if r is None else ala + r * (yla - ala) for r in raja)  # noqa: E731
            alueet.append((k.nimi, arvoksi(k.toimii), arvoksi(k.paras)))
    return alueet


def _tunnusluvut(mittari, hakija: osm.Hakija) -> dict[str, float]:
    """Mittarin tunnusluvut (MHQ, MNQ, ...) SYKE:n kuvasta: muistissa olevasta tilanteesta tai
    lukemalla kuva, jos paikalla on tulvaindeksikohteita (ajo.jsonissa niitä ei ole)."""
    url = osm.kaavio_url(mittari.kaavio)
    if _tilanne:
        for lukema in (l for t in _tilanne[1].tulokset for l in t.lukemat.values()):
            if lukema.url == url and lukema.tunnusluvut:
                return dict(lukema.tunnusluvut)
    data, _ = osm.hae_turvallisesti(hakija, url)
    try:
        return syke_kaavio.KaavioLukija().lue(data, url).tunnusluvut if data else {}
    except syke_kaavio.KaavioVirhe:
        return {}


def _syke_alueet(paikka, avain: str, mittari, hakija: osm.Hakija) -> list:
    tulvaindeksi = any(k.mittari == avain and k.muuttuja != "arvo" for k in paikka.kohteet)
    return _alueet(paikka, avain, _tunnusluvut(mittari, hakija) if tulvaindeksi else None)


def _kaavion_paikka(ehto, paikan_nimi: str | None = None) -> tuple | None:
    """(paikka, mittariavain, mittari) mittarille, jolle ehto(mittari) pätee; nimetty paikka ensin."""
    loydetyt = [(p, a, m) for p in kaikki_paikat() for a, m in p.mittarit.items() if ehto(m)]
    return next((x for x in loydetyt if x[0].nimi == paikan_nimi), loydetyt[0] if loydetyt else None)


def _hae_json(hakija: osm.Hakija, url: str) -> dict | None:
    data, _ = osm.hae_turvallisesti(hakija, url)
    try:
        return json.loads(data.decode("utf-8")) if data else None
    except ValueError:
        return None


def smhi_kaavio_svg(kaavio: str, hakija: osm.Hakija | None = None, nyt: dt.datetime | None = None,
                    paikan_nimi: str | None = None, kieli: str = "fi") -> str | None:
    """Ruotsin mittarin kaavio SVG:nä; None, jos mittaria ei ole paikoissa tai dataa ei saatu."""
    loydetty = _kaavion_paikka(lambda m: m.smhi and m.kaavio == kaavio, paikan_nimi)
    if not loydetty:
        return None
    paikka, avain, _ = loydetty
    hakija = hakija or osm.Hakija(aikaraja=20)
    asema, piste = smhi_data.osat(kaavio)
    havainto = _hae_json(hakija, smhi_data.havainto_url(asema))
    ennuste = _hae_json(hakija, smhi_data.ennuste_url(piste))
    if not havainto and not ennuste:
        return None
    otsikko = f"{paikka.nimi} – {kielet.kaanna('mittari', kieli)} {aseman_nimi(kaavio)}"
    return kaavio_svg.smhi_svg(havainto, ennuste, otsikko, nyt or suomen_aika(), _alueet(paikka, avain), kieli)


def syke_kaavio_svg(polku: str, hakija: osm.Hakija | None = None, paikan_nimi: str | None = None,
                    kieli: str = "fi", kuvasta: bool = False, nyt: dt.datetime | None = None) -> str | None:
    """SYKE:n mittarin kaavio SVG:nä polusta '<alue>/<asema>/<kaavio>' (tai arviomallin asemalle
    '<alue>/<asema>'); None, jos mittaria ei ole paikoissa tai dataa ei saatu."""
    osat = polku.split("/")
    if len(osat) == 2:   # arviomallin asema (vanha osoite)
        ehto = lambda m: _arvioasema(m.kaavio) == polku   # noqa: E731
    else:
        ehto = lambda m: not m.smhi and m.kaavio == polku + ".png"   # noqa: E731
    loydetty = _kaavion_paikka(ehto, paikan_nimi)
    if not loydetty:
        return None
    paikka, avain, mittari = loydetty
    hakija = hakija or osm.Hakija(aikaraja=20)
    otsikko = f"{paikka.nimi} – {kielet.kaanna('mittari', kieli)} {aseman_nimi(mittari.kaavio)}"
    asema = _arvioasema(mittari.kaavio)
    if asema:
        return _arvio_kaavio(paikka, avain, mittari, asema, hakija, otsikko, kieli)
    return _mittarin_svg(paikka, avain, mittari, hakija, otsikko, kieli, kuvasta, nyt)


def _mittarin_svg(paikka, avain: str, mittari, hakija: osm.Hakija, otsikko: str, kieli: str = "fi",
                  kuvasta: bool = False, nyt: dt.datetime | None = None) -> str | None:
    """SYKE-mittarin kaavio paikan kohteiden rajoineen: ajo.jsonista tai SYKE:n kuvasta."""
    ajo = None
    if not kuvasta:
        ajo = _hae_json(hakija, osm.kaavio_url(syke_data.ajo_avain(mittari.kaavio)))
        alueet = _syke_alueet(paikka, avain, mittari, hakija)
        kuva = kaavio_svg.syke_svg(ajo, mittari.kaavio, otsikko, alueet, kieli) if ajo else None
        if kuva:
            return _lisaa_tuntikaavio(kuva, paikka, mittari, ajo, hakija, kieli, nyt)
    # ajo.jsonissa ei ole kaavion suuretta (tai luvut eivät täsmää kuvaan): sarjat SYKE:n kuvasta
    data, _ = osm.hae_turvallisesti(hakija, osm.kaavio_url(mittari.kaavio))
    if not data:
        return None
    try:
        sarjat = syke_kaavio.KaavioLukija().lue_sarjat(data, historia=kaavio_svg.HISTORIA_PAIVIA)
    except syke_kaavio.KaavioVirhe:
        return None
    _, yksikko = syke_kaavio.suure_urlista(mittari.kaavio)
    kuva = kaavio_svg.kuva_svg(sarjat, _kuvan_paiva(sarjat.tanaan_paiva, nyt), otsikko, yksikko,
                               _syke_alueet(paikka, avain, mittari, hakija), kieli)
    return _lisaa_tuntikaavio(kuva, paikka, mittari, ajo, hakija, kieli, nyt)


def _lisaa_tuntikaavio(kuva: str, paikka, mittari, ajo: dict | None, hakija: osm.Hakija, kieli: str,
                       nyt: dt.datetime | None = None) -> str:
    """Kaavion alle mittarin oma päivä tunneittain SYKE:n reaaliaikamittauksista ja ennuste
    päivän loppuun (syke_data.REAALIAIKA_MITTARIT); ilman reaaliaikadataa kaavio sellaisenaan."""
    tiedosto = syke_data.REAALIAIKA_MITTARIT.get(mittari.kaavio)
    if not tiedosto:
        return kuva
    data, _ = osm.hae_turvallisesti(hakija, syke_data.REAALIAIKA_URL.format(tiedosto=tiedosto))
    tanaan = (nyt or suomen_aika()).date()
    tunnit = syke_data.mittarin_tunnit(syke_data.lue_reaaliaika_tunnit(data), tanaan) if data else None
    if not tunnit:
        return kuva
    _, yksikko = syke_kaavio.suure_urlista(mittari.kaavio)
    vertailu = []
    if ajo:   # SYKE:n tämän päivän päiväarvo ja eilinen havainto vertailuksi
        hav = "whav" if yksikko == "m" else "qhav"
        for nimi, p, vari in (("SYKE päiväarvo", tanaan, "#ef6c00"),
                              ("eilen mitattu", tanaan - dt.timedelta(days=1), "#1b1f24")):
            v = syke_data._arvo(ajo.get(hav) or {}, p)
            if v is not None:
                vertailu.append((kielet.kaanna(nimi, kieli), v, vari))
    nimi = f"{paikka.nimi} – {aseman_nimi(mittari.kaavio)}, {kielet.kaanna('mitattu tunneittain', kieli)}"
    return kaavio_svg.pinoa(kuva, kaavio_svg.tunti_svg(
        nimi, tanaan, tunnit, vertailu, kieli, yksikko=yksikko,
        alaotsikko="mittaukset tunneittain SYKE:n reaaliaikasivulta", mitattu="mitattu tunneittain"))


def _kuvan_paiva(paiva: int | None, nyt: dt.datetime | None = None) -> dt.date:
    """Kaaviokuvan ennusteen alkupäivä päivänumerosta: tämä päivä tai enintään 3 päivää sitten."""
    tanaan = (nyt or suomen_aika()).date()
    for n in range(4):
        if paiva is None or (tanaan - dt.timedelta(days=n)).day == paiva:
            return tanaan - dt.timedelta(days=n)
    return tanaan


def _arvio_kaavio(paikka, avain, mittari, asema: str, hakija: osm.Hakija, otsikko: str,
                  kieli: str = "fi") -> str | None:
    """Arviomallin aseman kaavio: mitatut arvot, lasketut arviot ja arviosta jatkuva ennuste."""
    avaimet = [f"{asema}/ajo.json"] + syke_data.ARVIOMALLIT[asema].ajo_avaimet()
    if asema in syke_data.TARKENNETUT:
        avaimet += syke_data.TARKENNETUT[asema].ajo_avaimet()
    ajot = {a: d for a in avaimet if (d := _hae_json(hakija, osm.kaavio_url(a)))}
    syke_data.lisaa_reaaliaika(ajot, lambda url: osm.hae_turvallisesti(hakija, url)[0])
    oma = ajot.get(f"{asema}/ajo.json")
    if not oma or "ennustepvm_www" not in oma:
        return None
    lukema = syke_data.Kaaviolukema(url=osm.kaavio_url(mittari.kaavio), suure="virtaama", yksikko="m3/s",
                                    tanaan_paiva=None, havaittu=None, havaittu_paivia_sitten=None, malli=None)
    syke_data.taydenna(lukema, oma)
    syke_data.arvioi_tanaan(lukema, ajot)
    # Tunnusluvut ovat vain SYKE:n kuvassa: otetaan ne muistissa olevasta tilanteesta, jos sellainen on
    if _tilanne:
        for vanha in (l for t in _tilanne[1].tulokset for l in t.lukemat.values()):
            if vanha.url == lukema.url:
                lukema.tunnusluvut = dict(vanha.tunnusluvut)
    kuva = kaavio_svg.arvio_svg(lukema, ajot, asema, otsikko,
                                _alueet(paikka, avain, lukema.tunnusluvut), kieli, arkistoidut_arviot(asema))
    # alle päivän tuntikaavio toisesta arviosta (syötteiden reaaliaikamittaukset)
    tanaan = dt.date.fromisoformat(oma["ennustepvm_www"])
    tunnit = syke_data.tuntiarviot(asema, ajot, tanaan)
    if tunnit:
        vertailu = []
        if lukema.tietolahde.startswith("arvio") and lukema.arvo is not None:
            vertailu.append((kielet.kaanna("nykyinen malli", kieli), lukema.arvo, "#ef6c00"))
        eilen = syke_data._arvo(oma.get("qhav") or {}, tanaan - dt.timedelta(days=1))
        if eilen is not None:
            vertailu.append((kielet.kaanna("eilen mitattu", kieli), eilen, "#1b1f24"))
        nimi = f"{paikka.nimi} – {kielet.kaanna('tuntiarvio', kieli)} {tanaan.day}.{tanaan.month}."
        kuva = kaavio_svg.pinoa(kuva, kaavio_svg.tunti_svg(nimi, tanaan, tunnit, vertailu, kieli))
    return kuva


_arkisto: tuple[float, dict[str, dict]] | None = None


def arkistoidut_arviot(asema: str) -> dict[dt.date, float]:
    """Sovelluksen kunakin päivänä näyttämä arviomallin arvo ennustearkistosta (Firestore,
    ennustearkisto.py): ennusteen alkupäivä -> arvo. Tyhjä, jos arkistoon ei päästä."""
    global _arkisto
    if not _arkisto or time.monotonic() - _arkisto[0] > VALIMUISTI_S:
        try:
            kanta = firestore.Firestore.ymparistosta()
            dokumentit = kanta.listaa(ennustearkisto.KOKOELMA) if kanta else {}
        except (firestore.FirestoreVirhe, OSError, ValueError, KeyError, ImportError):
            dokumentit = {}   # arkisto ei saatavilla: menneet arviot lasketaan jälkikäteen
        _arkisto = (time.monotonic(), dokumentit)
    tulos = {}
    for doc in _arkisto[1].values():
        arvio = (doc.get("arviot") or {}).get(asema) or {}
        try:
            if arvio.get("tanaan") is not None:
                tulos[dt.date.fromisoformat(arvio["ennustepvm_www"])] = float(arvio["tanaan"])
        except (KeyError, TypeError, ValueError):
            continue
    return tulos


def arvio_kaavio_svg(asema: str, hakija: osm.Hakija | None = None) -> str | None:
    """Arviomallin aseman kaavio SVG:nä; None, jos asemaa ei ole tai sen ajo.json puuttuu."""
    return syke_kaavio_svg(asema, hakija)


# ---------------------------------------------------------------------------
# WSGI
# ---------------------------------------------------------------------------

PAIKKASIVUT = {paikkasivut.tunniste(p.nimi): p for p in PAIKAT}
LAHDETYYPIT = {"sivu": "lähteen kuvaus", "meloja": "paikallinen meloja", "arvio": "arvio"}
SUUREET = {"vedenkorkeus": "vedenkorkeus", "virtaama": "virtaama", "lampotila": "lämpötila"}


def paikan_osoite(paikka, kieli: str = "fi") -> str:
    if paikka.url.startswith("/ehdotus/"):   # käyttäjän ehdottama, hyväksytty kohde
        return paikka.url + ("?kieli=en" if kieli == "en" else "")
    return f"/paikka/{paikkasivut.tunniste(paikka.nimi)}" + ("?kieli=en" if kieli == "en" else "")


def _mittarin_suure(mittari) -> tuple[str, str]:
    """(suure, yksikkö) kaavion tiedostonimestä; SMHI:ltä haetaan virtaama."""
    if mittari.smhi:
        return "virtaama", "m3/s"
    return syke_kaavio.suure_urlista(mittari.kaavio)


def _rajat(raja: tuple, yksikko: str, muuttuja: str, kieli: str = "fi") -> str:
    """Kohteen raja luettavassa muodossa: "107.65 m – 108.20 m", "yli 250 m³/s", "kaikilla vesillä"."""
    en = kieli == "en"
    ala, yla = raja
    if ala is None and yla is None:
        return "at all levels" if en else "kaikilla vesillä"
    luku = lambda x: muotoile(x, yksikko, muuttuja)   # noqa: E731
    teksti = (f"{'below' if en else 'alle'} {luku(yla)}" if ala is None
              else f"{'above' if en else 'yli'} {luku(ala)}" if yla is None
              else f"{luku(ala)} – {luku(yla)}")
    return f"{'flood index' if en else 'tulvaindeksi'} {teksti}" if muuttuja == "tulvaindeksi" else teksti


def _mittarin_linkki(paikka, avain: str, kieli: str = "fi") -> str:
    """Mittarin oma kaaviosivu (ei vesi.fi:tä). Muistissa olevan tilanteen lukemasta tiedetään,
    piirretäänkö kaavio ajo.jsonista vai SYKE:n kuvasta; ilman sitä kaaviosivu kokeilee ensin
    ajo.jsonia ja sitten kuvaa."""
    mittari = paikka.mittarit[avain]
    lukema = None
    if _tilanne:
        tulos = next((t for t in _tilanne[1].tulokset if t.paikka.nimi == paikka.nimi), None)
        lukema = tulos.lukemat.get(avain) if tulos else None
    oma = kaavion_osoite(paikka, avain, lukema, kieli)
    if oma:
        return oma
    parametrit = {"paikka": paikka.nimi, **({"kieli": kieli} if kieli != "fi" else {})}
    if lukema is not None:   # esim. lämpötila: sarjat SYKE:n kuvasta
        parametrit["lahde"] = "kuva"
    return f"/kaavio/syke/{mittari.kaavio.removesuffix('.png')}?{urlencode(parametrit)}"


# Paikkasivun kiinteät tekstit englanniksi (kuvaukset: paikkasivut_en.py)
PAIKKASIVU_EN = {
    "← Kaikki paikat": "← All spots",
    "pelipaikka": "play spot",
    "retki- ja laskupätkä": "river run",
    "km Oulusta": "km from Oulu",
    "🗺 Kartta": "🗺 Map",
    "🗺 kartta": "🗺 map",
    "🚗 ajo-ohje": "🚗 directions",
    "Lähtö- ja loppupaikka": "Put-in and take-out",
    "Retkiehdotus": "Trip suggestion (in Finnish)",
    "Kohteet ja niiden rajat": "Features and their limits",
    "toimii": "works",
    "parhaimmillaan": "at its best",
    "mittari": "gauge",
    "rajat": "limits",
    "Lähteet": "Sources",
    "Paikan pääsivu": "Spot main page",
    "lähteen kuvaus": "source description",
    "paikallinen meloja": "local paddler",
    "arvio": "estimate",
    "vedenkorkeus": "water level",
    "virtaama": "discharge",
    "lämpötila": "temperature",
    "rajat_selite": ("The limits are the same ones the app uses to score the spot. Flood index: 0 = mean annual "
                     "low water, 1 = mean spring flood peak. "),
    "tilanne_linkki": "Today's conditions and forecast on the front page",
    "ei_rajoja": "There is no gauge chart or numerical limits for this spot – check the conditions yourself.",
    "loppuhuomautus": (
        "The description has been compiled from the sources in our own words; always check the conditions "
        "on site. Water data in brackets are daily values for the day described from SYKE's hydrology API "
        "(Swedish spots: SMHI's corrected daily archive); water levels have been converted to the same scale "
        "as in the app's charts. The Tornionjoki discharge at Matkakoski is from the Karunki station."),
}


def paikkasivu(paikka, kieli: str = "fi") -> str:
    """Paikan koostesivu: lähteistä koottu kuvaus, kohteet ja niiden rajat (paikat.py) sekä lähteet.
    Englanniksi (kieli="en") kuvaukset, lähtö- ja loppupaikat ja huomiot tulevat paikkasivut_en.py:stä."""
    en = kieli == "en"
    k_ = lambda teksti: PAIKKASIVU_EN.get(teksti, teksti) if en else teksti   # noqa: E731
    kuvaus = paikkasivut.KUVAUKSET.get(paikka.nimi)
    if en:
        kuvaus = paikkasivut_en.KUVAUKSET.get(paikka.nimi, kuvaus)

    def kappaleet(teksti: str) -> str:
        return "".join(f"<p>{e(kpl)}</p>" for kpl in teksti.split("\n\n"))

    osat = [kappaleet(kuvaus.johdanto if kuvaus else paikka.kuvaus)]
    for otsikko, teksti in (kuvaus.osiot if kuvaus else ()):
        osat.append(f"<h2>{e(otsikko)}</h2>{kappaleet(teksti)}")

    retkilinkit = "".join(f'<li><a href="/retki/{e(t)}">{e(r["nimi"])}</a></li>'
                          for t, r in retket.RETKET.items()
                          if any(u == paikan_osoite(paikka) for u, _ in r["paikat"]))
    retkilinkit = f"<h2>{k_('Retkiehdotus')}</h2><ul>{retkilinkit}</ul>" if retkilinkit else ""
    paikat_html = ""
    if paikka.nimi in paikkasivut.LAHTO_LOPPU:
        kaannokset = paikkasivut_en.LAHTO_LOPPU.get(paikka.nimi) if en else None
        rivit_ = []
        for i, (rooli, teksti, piste) in enumerate(paikkasivut.LAHTO_LOPPU[paikka.nimi]):
            if kaannokset:
                rooli, teksti = kaannokset[i]
            linkit = ""
            if piste:
                kartta_ = f"https://www.openstreetmap.org/?mlat={piste[0]}&mlon={piste[1]}#map=14/{piste[0]}/{piste[1]}"
                ajo_ = "https://www.google.com/maps/dir/?" + urlencode(
                    {"api": 1, "destination": f"{piste[0]},{piste[1]}", "travelmode": "driving"})
                linkit = (f' · <a href="{e(kartta_)}" target="_blank" rel="noopener">{k_("🗺 kartta")}</a>'
                          f' · <a href="{e(ajo_)}" target="_blank" rel="noopener">{k_("🚗 ajo-ohje")}</a>')
            rivit_.append(f"<li><b>{e(rooli)}:</b> {e(teksti)}{linkit}</li>")
        paikat_html = f'<h2>{k_("Lähtö- ja loppupaikka")}</h2><ul class="lahteet">{"".join(rivit_)}</ul>'
    tiedot = [k_("pelipaikka") if paikka.tyyppi == "peli" else k_("retki- ja laskupätkä")]
    if paikka.maa == "SE":
        tiedot.append(kielet.kaanna("Ruotsi", kieli))
    if paikka.km_oulusta:
        tiedot.append(f"~{paikka.km_oulusta} {k_('km Oulusta')}")
    if paikka.sijainti:
        lev, pit = paikka.sijainti
        kartta = f"https://www.openstreetmap.org/?mlat={lev}&mlon={pit}#map=14/{lev}/{pit}"
        reitti = "https://www.google.com/maps/dir/?" + urlencode(
            {"api": 1, "destination": f"{lev},{pit}", "travelmode": "driving"})
        tiedot.append(f'<a href="{e(kartta)}" target="_blank" rel="noopener">{k_("🗺 Kartta")}</a>')
        tiedot.append(f'<a href="{e(reitti)}" target="_blank" rel="noopener">{kielet.kaanna("🚗 Reitti", kieli)}</a>')
    tiedot_html = " · ".join(t if t.startswith("<a ") else e(t) for t in tiedot)

    etusivu = _osoite(kieli=kieli)
    if paikka.kohteet:
        huomiot = iter(paikkasivut_en.HUOMIOT.get(paikka.nimi, ())) if en else None
        rivit = []
        for kohde in paikka.kohteet:
            mittari = paikka.mittarit[kohde.mittari]
            suure, yksikko = _mittarin_suure(mittari)
            toimii = _rajat(kohde.toimii, yksikko, kohde.muuttuja, kieli)
            paras = _rajat(kohde.paras, yksikko, kohde.muuttuja, kieli)
            rajat = f"{k_('toimii')} {toimii}" + (f", {k_('parhaimmillaan')} {paras}" if paras != toimii else "")
            mittari_teksti = (f'<a href="{e(_mittarin_linkki(paikka, kohde.mittari, kieli))}">'
                              f'{e(aseman_nimi(mittari.kaavio))}</a>, {e(k_(SUUREET.get(suure, suure)))}')
            huom_teksti = (next(huomiot, kohde.huom) if huomiot is not None else kohde.huom) if kohde.huom else ""
            huom = f"<br>{e(huom_teksti)}" if huom_teksti else ""
            rivit.append(f'<li><b>{e(kohde.nimi)}</b>{_kajakit(paikka, kohde, lambda t: kielet.kaanna(t, kieli))}<br>'
                         f'<span class="rajat">{e(rajat)}</span>'
                         f'<br><span class="pieni">{k_("mittari")}: {mittari_teksti} · {k_("rajat")}: '
                         f'{e(k_(LAHDETYYPIT.get(kohde.lahde, kohde.lahde)))}</span>{huom}</li>')
        selite = (k_("rajat_selite") if en else
                  "Rajat ovat samat, joilla sovellus pisteyttää paikan. Tulvaindeksi: 0 = keskimääräinen "
                  "vuoden alivesi, 1 = keskimääräinen kevättulvan huippu. ")
        linkki = k_("tilanne_linkki") if en else "Tämän päivän tilanne ja ennuste etusivulla"
        kohteet = (f'<h2>{k_("Kohteet ja niiden rajat")}</h2><ul class="kohteet">{"".join(rivit)}</ul>'
                   f'<p class="pieni">{selite}<a href="{e(etusivu)}">{linkki}</a>.</p>')
    else:
        kohteet = (f'<h2>{k_("Kohteet ja niiden rajat")}</h2><p>'
                   + (k_("ei_rajoja") if en else "Paikalle ei ole vesikaaviota eikä lukuarvoisia rajoja – "
                      "tarkista olosuhteet itse.") + "</p>")

    lahteet = list(paikkasivut.KUVAUKSET[paikka.nimi].lahteet if paikka.nimi in paikkasivut.KUVAUKSET else ())
    if paikka.url not in {url for _, url in lahteet}:
        lahteet.insert(0, (k_("Paikan pääsivu"), paikka.url))
    def lahde(otsikko: str, url: str | None) -> str:
        if not url:
            return f"<li>{e(otsikko)}</li>"
        if url.startswith("/"):   # sovelluksen oma sivu (esim. mittarin kaavio): samaan ikkunaan
            url += "&kieli=en" if en and url.startswith("/kaavio/") else ""
            return f'<li><a href="{e(url)}">{e(otsikko)}</a></li>'
        return f'<li><a href="{e(url)}" target="_blank" rel="noopener">{e(otsikko)}</a></li>'
    lahteet_html = "".join(lahde(otsikko, url) for otsikko, url in lahteet)
    loppu = (k_("loppuhuomautus") if en else
             "Kuvaus on koottu lähteistä omin sanoin; tarkista olosuhteet aina paikan päällä. Suluissa olevat "
             "vesitiedot ovat kuvatun päivän vuorokausiarvoja SYKE:n hydrologiarajapinnasta (Ruotsin paikat: "
             "SMHI:n korjattu päiväarkisto); vedenkorkeudet on muunnettu samalle asteikolle kuin sovelluksen "
             "kaavioissa. Tornionjoen virtaama Matkakosken kohdalla on Karungin asemalta.")
    kuvaus_meta = (kuvaus.johdanto.split(". ")[0] + ".") if en and kuvaus else paikka.kuvaus
    toinen = "fi" if en else "en"
    vaihto = (f'<a class="kieli" href="{e(paikan_osoite(paikka, toinen))}" hreflang="{toinen}" '
              f'lang="{toinen}">{LIPUT[toinen]}{"Suomeksi" if toinen == "fi" else "In English"}</a>')
    return f"""<!doctype html>
<html lang="{kieli}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(paikka.nimi)} – {"Paddling spots" if en else "Melontapaikat"}</title>
<meta name="description" content="{e(kuvaus_meta)}">
<link rel="manifest" href="{e(sovellus.manifest_osoite(kieli))}">
<meta name="theme-color" content="{sovellus.TEEMA}">
<link rel="icon" type="image/png" href="{sovellus.kuvake_osoite(192)}">
<link rel="apple-touch-icon" href="{sovellus.kuvake_osoite(180)}">
<link rel="alternate" hreflang="{toinen}" href="{e(paikan_osoite(paikka, toinen))}">
<style>{TYYLI}</style>
</head>
<body><main class="kuvaus">
<div class="otsake"><a class="takaisin" href="{e(etusivu)}">{k_("← Kaikki paikat")}</a>{vaihto}</div>
<h1>{e(paikka.nimi)}</h1>
<div class="meta">{tiedot_html}</div>
{kuvaosio(paikka.nimi, kieli)}
{"".join(osat)}
{paikat_html}
{retkilinkit}
{kohteet}
{_kayttajien_lisaykset(paikka, kieli)}
<h2>{k_("Lähteet")}</h2>
<ul class="lahteet">{lahteet_html}</ul>
<p class="pieni">{loppu}</p>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Käyttäjien ehdotukset (ehdotukset.py): lomake, esikatselu, ylläpito ja ilmoitukset
# ---------------------------------------------------------------------------

LAHDETYYPIT["ehdotus"] = "käyttäjän ehdotus"
PAIKKASIVU_EN["käyttäjän ehdotus"] = "user suggestion"
EHDOTUS_VALIMUISTI_S = 120   # hyväksytty kohde näkyy listassa viimeistään näin monen sekunnin päästä
_ehdotukset: tuple[float, dict[str, dict]] | None = None

EHDOTUS_TYYLI = """
.lomake label { display:block; margin:10px 0 2px; font-weight:600; font-size:.92rem; }
.lomake input[type=text], .lomake select, .lomake textarea { width:100%; max-width:560px; padding:6px 8px;
  border:1px solid var(--viiva); border-radius:6px; background:var(--tausta); color:var(--teksti); font:inherit; }
.lomake textarea { min-height:90px; }
.lomake fieldset { border:1px solid var(--viiva); border-radius:8px; margin:10px 0; padding:6px 10px 10px; }
.lomake legend { font-weight:600; font-size:.92rem; }
.rajat-rivi { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.rajat-rivi input { width:7em !important; }
.lomake .ohje { color:var(--heikko); font-size:.85rem; margin:2px 0; }
.lomake .piilo { position:absolute; left:-9999px; }
.lomake .lisaa-kohde { font:inherit; font-size:.9rem; padding:4px 10px; border:1px solid var(--viiva);
                       border-radius:6px; background:var(--tausta); color:var(--linkki); cursor:pointer; }
.lomake .lisaa-kohde:disabled { color:var(--heikko); cursor:default; }
.kohdelista { margin:8px 0; padding-left:18px; }
.lomake label.valinta { font-weight:400; margin:4px 0; }
.lomake details.lisatiedot { margin:14px 0 6px; }
.lomake details.lisatiedot summary { font-weight:600; color:var(--teksti); }
.yksikon-rajat { margin:2px 0 8px 22px; }
.kohdelista button { border:0; background:none; color:var(--huono); cursor:pointer; font-size:1rem; padding:0 6px; }
.virhe { color:var(--huono); font-weight:600; }
.tila-merkki { display:inline-block; padding:1px 8px; border-radius:999px; border:1px solid var(--viiva);
               font-size:.85rem; }
.kuvaus .muuttuu { color:var(--keski); } .kuvaus .tulossa { color:var(--hyva); }
.kuvaus .huom { color:var(--keski); }
.tila-odottaa { color:var(--keski); } .tila-hyvaksytty { color:var(--hyva); } .tila-hylatty { color:var(--huono); }
.ehdotus-kaavio { width:100%; max-width:720px; border:1px solid var(--viiva); border-radius:8px; }
"""


def _kanta():
    try:
        return firestore.Firestore.ymparistosta()
    except (ValueError, KeyError, OSError):
        return None


def kaikki_ehdotukset(pakota: bool = False) -> dict[str, dict]:
    """Firestoren ehdotukset (tunniste -> ehdotus), muistissa EHDOTUS_VALIMUISTI_S sekuntia."""
    global _ehdotukset
    if not pakota and _ehdotukset and time.monotonic() - _ehdotukset[0] < EHDOTUS_VALIMUISTI_S:
        return _ehdotukset[1]
    kanta = _kanta()
    if not kanta:
        return {}
    try:
        kaikki = kanta.listaa(ehdotukset.KOKOELMA)
    except (firestore.FirestoreVirhe, OSError):
        return _ehdotukset[1] if _ehdotukset else {}
    _ehdotukset = (time.monotonic(), kaikki)
    return kaikki


def hyvaksytyt_ehdotukset() -> list[tuple[str, dict]]:
    return sorted(((t, e) for t, e in kaikki_ehdotukset().items() if e.get("tila") == "hyvaksytty"),
                  key=lambda x: x[1].get("kasitelty") or x[1].get("luotu") or "")


def kaikki_paikat() -> tuple:
    """Sovelluksen paikat (PAIKAT) ja hyväksytyt käyttäjien uudet kohteet. Käyttäjän kohteen sivu on
    /ehdotus/<tunniste> (paikan url); sijainti ehdotuksesta tai täydennyksestä (SIJAINNIT)."""
    nimet = {p.nimi for p in PAIKAT}
    julkaistut = []
    for tunniste, ehdotus in hyvaksytyt_ehdotukset():
        if ehdotus.get("laji") != "uusi":
            continue
        paikka, _ = ehdotukset.paikaksi(ehdotus, PAIKAT)
        if paikka is None:
            continue
        nimi = paikka.nimi if paikka.nimi not in nimet else f"{paikka.nimi} (käyttäjän ehdotus)"
        nimet.add(nimi)
        pisteet = ehdotukset.ehdotuksen_sijainnit(ehdotus)
        if pisteet:
            SIJAINNIT.setdefault(nimi, pisteet[0])
        julkaistut.append(replace(paikka, nimi=nimi, url=f"/ehdotus/{tunniste}"))
    return PAIKAT + tuple(julkaistut)


_kaksois_pohja: list[dict] | None = None


def _kaksoisehdokkaat(oma_tunniste: str) -> list[dict]:
    """Vertailukohteet kaksoiskappaleiden etsintään: sovelluksen paikat (nimi, sijainti, lähtö ja loppu),
    Muut kohteet (nimi, joet, lähtö ja loppu) ja muut ehdotukset (paitsi hylätyt)."""
    global _kaksois_pohja
    if _kaksois_pohja is None:
        _kaksois_pohja = [
            {"nimi": p.nimi, "osoite": paikan_osoite(p), "sanat": ehdotukset._sanat(p.nimi),
             "pisteet": [x for x in [p.sijainti] + [piste for _, _, piste in paikkasivut.LAHTO_LOPPU.get(p.nimi, ())]
                         if x]} for p in PAIKAT]
        _kaksois_pohja += [
            {"nimi": f"{k['nimi']} (Muut kohteet)", "osoite": f"/muut/{k['tunniste']}",
             "sanat": ehdotukset._sanat(" ".join([k["nimi"], *k.get("joet", [])])),
             "pisteet": [tuple(x) for x in (k.get("lahto_sijainti"), k.get("kohde_sijainti")) if x]}
            for k in muut_kohteet.KOHTEET]
    muut = [{"nimi": f"{ehdotukset.nimi(ed)} (ehdotus)", "osoite": f"/ehdotus/{tun}",
             "sanat": ehdotukset._sanat(ehdotukset.nimi(ed)), "pisteet": ehdotukset.ehdotuksen_sijainnit(ed)}
            for tun, ed in kaikki_ehdotukset().items()
            if tun != oma_tunniste and ed.get("laji") == "uusi" and ed.get("tila") != "hylatty"]
    return _kaksois_pohja + muut


def ehdotuksen_kaksoiskappaleet(tunniste: str, ehdotus: dict) -> list[dict]:
    if ehdotus.get("laji") != "uusi":
        return []
    return ehdotukset.kaksoiskappaleet(ehdotus, _kaksoisehdokkaat(tunniste))


def _muut_osumat(tunniste: str, ehdotus: dict) -> list[dict]:
    """Muut kohteet -listan reitit, jotka ovat samoja kuin ehdotettu uusi kohde (eivät estä uutta paikkaa)."""
    return [muut_kohteet.HAKEMISTO[k["osoite"].removeprefix("/muut/")]
            for k in ehdotuksen_kaksoiskappaleet(tunniste, ehdotus)
            if k["osoite"].startswith("/muut/") and k["osoite"].removeprefix("/muut/") in muut_kohteet.HAKEMISTO]


def _muut_linkit(kohteet: list[dict], kieli: str) -> str:
    """Sama reitti Muut kohteet -listassa: vain linkki (sisältöä ei käytetä kohteen kuvauksessa)."""
    if not kohteet:
        return ""
    t = ehdotukset.tekstit(kieli)
    linkit = ", ".join(f'<a href="/muut/{e(k["tunniste"])}{"?kieli=en" if kieli == "en" else ""}">{e(k["nimi"])}</a>'
                       for k in kohteet)
    return f'<p class="pieni">{e(t["muut_linkki"])}: {linkit}</p>'


def _ehdotusluukku(kieli: str) -> str:
    """Etusivun avattava luukku merkintöjen alla: linkit lomakkeelle ja hyväksytyt uudet kohteet."""
    t = ehdotukset.tekstit(kieli)
    q = "&kieli=en" if kieli == "en" else ""
    uudet = [(tun, ed) for tun, ed in hyvaksytyt_ehdotukset() if ed.get("laji") == "uusi"]
    lista = ""
    if uudet:
        lista = (f'<p><b>{e(t["kayttajien_kohteet"])}</b></p><ul>' + "".join(
            f'<li><a href="/ehdotus/{e(tun)}{"?kieli=en" if kieli == "en" else ""}">{e(ehdotukset.nimi(ed))}</a></li>'
            for tun, ed in uudet) + "</ul>")
    return (f'<details class="ehdota"><summary><span class="lamppu" aria-hidden="true">💡</span> {e(t["luukku"])}</summary><p>{e(t["luukku_teksti"])}</p>'
            f'<a class="nappi" href="/ehdota?laji=uusi{q}">{e(t["uusi"])}</a>'
            f'<a class="nappi toissijainen" href="/ehdota?laji=taydenna{q}">{e(t["taydenna"])}</a>{lista}</details>')


def _sivupohja(otsikko: str, runko: str, kieli: str, takaisin: str = "/") -> str:
    t = ehdotukset.tekstit(kieli)
    return f"""<!doctype html>
<html lang="{kieli}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{e(otsikko)} – {"Paddling spots" if kieli == "en" else "Melontapaikat"}</title>
<link rel="icon" type="image/png" href="{sovellus.kuvake_osoite(192)}">
<style>{TYYLI}{EHDOTUS_TYYLI}</style>
</head>
<body><main class="kuvaus">
<a class="takaisin" href="{e(takaisin)}">{e(t["takaisin"])}</a>
{runko}
</main>
</body>
</html>"""


def ehdotuslomake(kieli: str, laji: str = "uusi", paikan_nimi: str = "", virhe: str = "",
                  kentat: dict[str, list[str]] | None = None) -> str:
    """Lomake /ehdota: nimi, linkit (julkaistavat ja ei-julkaistavat), kohteet rajoineen suureittain
    (virtaama, vedenkorkeus, molemmat tai ei kumpaakaan), mittarit ja sijainti, oma teksti.
    Virheen jälkeen kentät täytetään uudelleen."""
    t = ehdotukset.tekstit(kieli)
    kentat = kentat or {}
    arvo = lambda nimi, oletus="": e((kentat.get(nimi) or [oletus])[0])   # noqa: E731
    laji = arvo("laji", laji) if kentat else laji
    paikan_nimi = arvo("paikka", paikan_nimi) if kentat else paikan_nimi
    paikat = sorted(PAIKAT, key=lambda p: p.nimi)
    paikka_valinnat = "".join(
        f'<option value="{e(p.nimi)}"{" selected" if p.nimi == html.unescape(paikan_nimi) else ""}>{e(p.nimi)}</option>'
        for p in paikat)
    mittarit = {p.nimi: {a: aseman_nimi(m.kaavio) for a, m in p.mittarit.items()} for p in paikat}
    kohteet = {p.nimi: [k.nimi for k in p.kohteet] for p in paikat}
    rajakentat = [f"{lyh}_{x}" for lyh in ("q", "w") for x in ("toimii_ala", "toimii_yla", "paras_ala", "paras_yla")]
    # aiemmin lisätyt kohteet (virheen jälkeen lomake täytetään uudelleen)
    lisatyt = []
    for i in range(1, ehdotukset.KOHTEITA_ENINTAAN + 1):
        rivi = {x: (kentat.get(f"k{i}_{x}") or [""])[0] for x in ["nimi", "huom", *rajakentat]}
        if any(v.strip() for v in rivi.values()):
            lisatyt.append(rivi)

    def rajarivit(lyh: str) -> str:
        return (f'<div class="rajat-rivi"><span>{e(t["toimii"])}</span>'
                f'<input type="text" inputmode="decimal" id="kohde-{lyh}_toimii_ala" placeholder="{e(t["ala"])}">–'
                f'<input type="text" inputmode="decimal" id="kohde-{lyh}_toimii_yla" placeholder="{e(t["yla"])}"></div>'
                f'<div class="rajat-rivi"><span>{e(t["optimi"])}</span>'
                f'<input type="text" inputmode="decimal" id="kohde-{lyh}_paras_ala" placeholder="{e(t["ala"])}">–'
                f'<input type="text" inputmode="decimal" id="kohde-{lyh}_paras_yla" placeholder="{e(t["yla"])}"></div>')
    editori = f"""<fieldset class="kohde-editori"><legend>{e(t["kohde"])}</legend>
<label for="kohde-nimi"><span class="vain-taydenna">{e(t["kohteen_nimi"])}</span><span class="vain-uusi">{e(t["kohteen_nimi_uusi"])}</span></label>
<input type="text" id="kohde-nimi" maxlength="100" list="kohdenimet">
<p class="ohje" style="margin-top:8px">{e(t["yksikot"])}</p>
<label class="valinta"><input type="checkbox" id="yksikko-q"> {e(t["yksikko_q"])}</label>
<div id="rajat-q" class="yksikon-rajat" hidden>{rajarivit("q")}</div>
<label class="valinta"><input type="checkbox" id="yksikko-w"> {e(t["yksikko_w"])}</label>
<div id="rajat-w" class="yksikon-rajat" hidden>{rajarivit("w")}</div>
<label for="kohde-huom">{e(t["huom"])}</label>
<input type="text" id="kohde-huom" maxlength="300">
<p><button type="button" class="lisaa-kohde" id="lisaa-kohde">{e(t["lisaa_kohde"])}</button>
<span class="virhe" id="kohde-virhe"></span></p>
</fieldset>
<ul id="kohdelista" class="kohdelista"></ul>
<div id="kohdekentat"></div>"""
    virhe_html = f'<p class="virhe">{e(t["virhe_otsikko"])}: {e(virhe)}</p>' if virhe else ""
    tyyppi = arvo("tyyppi", "retki")
    runko = f"""<h1>{e(t["lomake_otsikko"])}</h1>
<p>{e(t["lomake_ohje"])}</p>
{virhe_html}
<form class="lomake" method="post" action="/ehdota{"?kieli=en" if kieli == "en" else ""}">
<label>{e(t["laji"])}</label>
<label style="font-weight:400"><input type="radio" name="laji" value="uusi"{" checked" if laji != "taydenna" else ""}> {e(t["uusi"])}</label>
<label style="font-weight:400"><input type="radio" name="laji" value="taydenna"{" checked" if laji == "taydenna" else ""}> {e(t["taydenna"])}</label>
<div id="osa-taydenna">
<label for="paikka">{e(t["paikka"])}</label>
<select id="paikka" name="paikka">{paikka_valinnat}</select>
</div>
<div id="osa-uusi">
<label for="nimi">{e(t["nimi"])}</label>
<input type="text" id="nimi" name="nimi" maxlength="100" value="{arvo("nimi")}">
<label for="tyyppi">{e(t["tyyppi"])}</label>
<select id="tyyppi" name="tyyppi"><option value="retki"{" selected" if tyyppi == "retki" else ""}>{e(t["retki"])}</option>
<option value="peli"{" selected" if tyyppi == "peli" else ""}>{e(t["peli"])}</option></select>
</div>
<h2>{e(t["linkit_otsikko"])}</h2>
<p class="ohje">{e(t["linkit_ohje"])}</p>
<label for="linkit">{e(t["linkit"])}</label>
<textarea id="linkit" name="linkit" rows="4">{arvo("linkit")}</textarea>
<label for="yksityiset_linkit">{e(t["yksityiset_linkit"])}</label>
<p class="ohje">{e(t["yksityiset_ohje"])}</p>
<textarea id="yksityiset_linkit" name="yksityiset_linkit" rows="3">{arvo("yksityiset_linkit")}</textarea>
<h2><span class="vain-taydenna">{e(t["kohteet"])}</span><span class="vain-uusi">{e(t["rajat_uusi"])}</span></h2>
<p class="ohje"><span class="vain-taydenna">{e(t["kohteet_ohje"])}</span><span class="vain-uusi">{e(t["rajat_uusi_ohje"])}</span></p>
<datalist id="kohdenimet"></datalist>
{editori}
<label for="teksti">{e(t["teksti"])}</label>
<p class="ohje">{e(t["teksti_ohje"])}</p>
<textarea id="teksti" name="teksti" rows="8" maxlength="{ehdotukset.TEKSTI_ENINTAAN}">{arvo("teksti")}</textarea>
<label for="ehdottaja">{e(t["ehdottaja"])}</label>
<input type="text" id="ehdottaja" name="ehdottaja" maxlength="100" value="{arvo("ehdottaja")}">
<details class="lisatiedot"{" open" if any(arvo(k) for k in ("mittari_virtaama", "mittari_vedenkorkeus", "sijainti")) else ""}>
<summary>{e(t["mittarit_otsikko"])}</summary>
<p class="ohje">{e(t["mittarit_ohje"])}</p>
<div id="osa-taydenna-mittari">
<label for="mittari_avain">{e(t["paikan_mittari"])}</label>
<select id="mittari_avain" name="mittari_avain"></select>
</div>
<div id="osa-uusi-mittarit">
<label for="mittari_virtaama">{e(t["mittari_virtaama"])}</label>
<input type="text" id="mittari_virtaama" name="mittari_virtaama" maxlength="300" value="{arvo("mittari_virtaama")}">
<label for="mittari_vedenkorkeus">{e(t["mittari_vedenkorkeus"])}</label>
<input type="text" id="mittari_vedenkorkeus" name="mittari_vedenkorkeus" maxlength="300" value="{arvo("mittari_vedenkorkeus")}">
<p class="ohje">{e(t["mittari_ohje"])}</p>
<label for="sijainti">{e(t["sijainti"])}</label>
<input type="text" id="sijainti" name="sijainti" maxlength="300" value="{arvo("sijainti")}">
</div>
</details>
<div class="piilo" aria-hidden="true"><label for="verkkosivu">Verkkosivu</label>
<input type="text" id="verkkosivu" name="verkkosivu" tabindex="-1" autocomplete="off"></div>
<p class="ohje">{e(t["tietosuoja"])}</p>
<button class="nappi" type="submit">{e(t["laheta"])}</button>
</form>
<script type="application/json" id="mittarit">{json.dumps(mittarit, ensure_ascii=False).replace("</", "<\\/")}</script>
<script type="application/json" id="kohteet">{json.dumps(kohteet, ensure_ascii=False).replace("</", "<\\/")}</script>
<script>
(() => {{
  const mittarit = JSON.parse(document.getElementById("mittarit").textContent);
  const kohteet = JSON.parse(document.getElementById("kohteet").textContent);
  const paikka = document.getElementById("paikka"), avain = document.getElementById("mittari_avain");
  const valittu = {json.dumps(arvo("mittari_avain"))};
  function paivita() {{
    const taydenna = document.querySelector('input[name="laji"]:checked').value === "taydenna";
    document.getElementById("osa-taydenna").hidden = !taydenna;
    document.getElementById("osa-uusi").hidden = taydenna;
    document.getElementById("osa-uusi-mittarit").hidden = taydenna;
    document.getElementById("osa-taydenna-mittari").hidden = !taydenna;
    document.querySelectorAll(".vain-uusi").forEach(x => {{ x.hidden = taydenna; }});
    document.querySelectorAll(".vain-taydenna").forEach(x => {{ x.hidden = !taydenna; }});
    avain.length = 0;
    Object.entries(mittarit[paikka.value] || {{}}).forEach(([a, n]) => avain.add(new Option(n, a, false, a === valittu)));
    document.getElementById("kohdenimet").replaceChildren(...(taydenna ? kohteet[paikka.value] || [] : [])
      .map(n => new Option(n)));
    nayta();
  }}
  // Kohteet kuten hyvien olojen hälytyksen ehdot: kentät täytetään, "+ Lisää kohde" siirtää kohteen
  // tekstinä listaan (✕ poistaa) ja tyhjentää kentät seuraavalle; enintään {ehdotukset.KOHTEITA_ENINTAAN} kohdetta.
  // Rajat suureittain (q = virtaama m³/s, w = vedenkorkeus m): kumpikin, toinen tai ei kumpaakaan;
  // avoin ala- tai yläraja sallitaan. Lomakkeen mukana kohteet lähtevät piilokenttinä k1_..k{ehdotukset.KOHTEITA_ENINTAAN}_.
  const RAJAT = {json.dumps(rajakentat)}, KENTAT = ["nimi", "huom", ...RAJAT];
  const ENINTAAN = {ehdotukset.KOHTEITA_ENINTAAN}, T = {json.dumps({x: t[x] for x in (
      "toimii", "optimi", "poista_kohde", "virhe_kohteen_nimi", "virhe_luku", "virhe_jarjestys",
      "kohteita_enintaan", "paikan_nimi", "yksikko_q", "yksikko_w", "ei_rajoja")}, ensure_ascii=False)};
  let lista = {json.dumps(lisatyt, ensure_ascii=False)};
  const kentta = k => document.getElementById("kohde-" + k);
  const valinta = lyh => document.getElementById("yksikko-" + lyh);
  const lisaa = document.getElementById("lisaa-kohde"), virhe = document.getElementById("kohde-virhe");
  const luku = v => v.trim() === "" ? null : Number(v.trim().replace(",", ".").replace("−", "-"));
  const uusi = () => document.querySelector('input[name="laji"]:checked').value === "uusi";
  const vali = (a, b) => a && b ? a + "–" + b : a ? "≥ " + a : b ? "≤ " + b : "";
  ["q", "w"].forEach(lyh => valinta(lyh).addEventListener("change", () => {{
    document.getElementById("rajat-" + lyh).hidden = !valinta(lyh).checked;
  }}));
  function rajateksti(k) {{
    const osat = ["q", "w"].map(lyh => {{
      const toimii = vali(k[lyh + "_toimii_ala"], k[lyh + "_toimii_yla"]), optimi = vali(k[lyh + "_paras_ala"], k[lyh + "_paras_yla"]);
      if (!toimii && !optimi) return "";
      return T["yksikko_" + lyh] + ": " + [toimii && T.toimii.toLowerCase() + " " + toimii,
                                         optimi && T.optimi.toLowerCase() + " " + optimi].filter(Boolean).join(", ");
    }}).filter(Boolean);
    return osat.length ? osat.join("; ") : T.ei_rajoja;
  }}
  function nayta() {{
    const ul = document.getElementById("kohdelista");
    ul.replaceChildren(...lista.map((k, i) => {{
      const li = document.createElement("li"), pois = document.createElement("button");
      li.textContent = (k.nimi || T.paikan_nimi) + ": " + rajateksti(k) + (k.huom ? " · " + k.huom : "");
      pois.type = "button"; pois.textContent = "✕"; pois.title = pois.ariaLabel = T.poista_kohde;
      pois.addEventListener("click", () => {{ lista.splice(i, 1); nayta(); }});
      li.append(pois);
      return li;
    }}));
    const piilot = document.getElementById("kohdekentat");
    piilot.replaceChildren(...lista.flatMap((k, i) => KENTAT.map(x => {{
      const h = document.createElement("input");
      h.type = "hidden"; h.name = "k" + (i + 1) + "_" + x; h.value = k[x] || "";
      return h;
    }})));
    // uuden paikan ensimmäisen kohteen nimi on vapaaehtoinen (oletus = paikan nimi), muiden pakollinen
    const ensimmainen = uusi() && !lista.length;
    document.querySelector('label[for="kohde-nimi"] .vain-uusi').hidden = !ensimmainen;
    document.querySelector('label[for="kohde-nimi"] .vain-taydenna').hidden = ensimmainen;
    lisaa.disabled = lista.length >= ENINTAAN;
    virhe.textContent = lisaa.disabled ? T.kohteita_enintaan.replace("{{n}}", ENINTAAN) : "";
  }}
  function lisaaKohde() {{
    const k = Object.fromEntries(KENTAT.map(x => [x, kentta(x).value.trim()]));
    ["q", "w"].forEach(lyh => {{ if (!valinta(lyh).checked) RAJAT.filter(x => x.startsWith(lyh)).forEach(x => {{ k[x] = ""; }}); }});
    if (!KENTAT.some(x => k[x])) return true;   // tyhjä: ei lisättävää
    const n = lista.length + 1;
    let ongelma = "";
    if (lista.length >= ENINTAAN) ongelma = T.kohteita_enintaan.replace("{{n}}", ENINTAAN);
    else if (!k.nimi && !(uusi() && n === 1)) ongelma = T.virhe_kohteen_nimi.replace("{{n}}", n);
    else if (RAJAT.some(x => k[x] && isNaN(luku(k[x])))) ongelma = T.virhe_luku.replace("{{n}}", n);
    else if (["q_toimii", "q_paras", "w_toimii", "w_paras"].some(r => {{
      const a = luku(k[r + "_ala"]), b = luku(k[r + "_yla"]);
      return a !== null && b !== null && a > b;
    }})) ongelma = T.virhe_jarjestys.replace("{{n}}", n);
    if (ongelma) {{ virhe.textContent = ongelma; return false; }}
    lista.push(k);
    KENTAT.forEach(x => {{ kentta(x).value = ""; }});
    nayta();
    kentta("nimi").focus();
    return true;
  }}
  lisaa.addEventListener("click", lisaaKohde);
  // kentissä oleva, listaan lisäämätön kohde otetaan mukaan lähetettäessä
  document.querySelector("form.lomake").addEventListener("submit", ev => {{
    if (!lisaaKohde()) ev.preventDefault();
  }});
  nayta();
  document.querySelectorAll('input[name="laji"]').forEach(r => r.addEventListener("change", paivita));
  paikka.addEventListener("change", paivita);
  paivita();
}})();
</script>"""
    return _sivupohja(t["lomake_otsikko"], runko, kieli, _osoite(kieli=kieli))


def _ehdotuksen_lukemat(paikka, hakija: osm.Hakija) -> dict:
    """Paikan mittareiden tämän päivän lukemat: muistissa olevasta tilanteesta tai ajo.jsonista."""
    lukemat = {}
    for avain, mittari in paikka.mittarit.items():
        lukema = None
        if _tilanne:
            lukema = next((t.lukemat[a] for t in _tilanne[1].tulokset for a, m in t.paikka.mittarit.items()
                           if m.kaavio == mittari.kaavio and t.lukemat.get(a) is not None), None)
        if lukema is None and not mittari.smhi:
            ajo = _hae_json(hakija, osm.kaavio_url(syke_data.ajo_avain(mittari.kaavio)))
            lukema = syke_data.lukema_ajosta(mittari.kaavio, ajo)
        if lukema is not None:
            lukemat[avain] = lukema
    return lukemat


def _linkkilista(linkit: list[dict]) -> str:
    return "".join(f'<li><a href="{e(l["url"])}" target="_blank" rel="nofollow ugc noopener">{e(l["url"])}</a></li>'
                   for l in linkit)


def _ehdotuksen_sisalto(tunniste: str, ehdotus: dict, kieli: str, hakija: osm.Hakija | None = None,
                        tilanne_mukaan: bool = True, otsikkotaso: int = 2) -> str:
    """Ehdotuksen osat: päivän tilanne, kuvaus, kohteet rajoineen ja linkit. Täydennyksessä omina
    osioinaan "Muuttuu" (rajakorjaukset: nykyinen -> ehdotettu) ja "Tulossa lisää" (uudet kohteet,
    teksti ja linkit); hyväksytyssä "Muutettu" ja "Lisätty"."""
    t = ehdotukset.tekstit(kieli)
    en = kieli == "en"
    paikka, uudet = ehdotukset.paikaksi(ehdotus, PAIKAT)
    osat = []
    if tilanne_mukaan and paikka is not None:
        osat.append(f"<h{otsikkotaso}>{e(t['paivan_tilanne'])}</h{otsikkotaso}>")
        if not paikka.mittarit:
            osat.append(f"<p>{e(t['ei_mittaria'])}</p>")
        else:
            lukemat = _ehdotuksen_lukemat(paikka, hakija or osm.Hakija(aikaraja=15))
            if not lukemat:
                osat.append(f"<p>{e(t['ei_dataa'])}</p>")
            else:
                for l in lukemat.values():
                    osat.append(f"<p>{e(t['mittari_arvo'])}: {e(kielet.kaanna(melonta.kuvaa_lukema(l), kieli))}</p>")
                tulos = arviointi.arvioi(paikka, lukemat) if paikka.kohteet else None
                if tulos and tulos.kohteet:
                    osat.append("<ul>" + "".join(
                        f"<li>{melonta._tila_merkki(k.tila)} <b>{e(k.kohde.nimi)}</b>"
                        f"{' <span class=pieni>(' + e(t['uusi_merkki']) + ')</span>' if k.kohde.nimi in uudet else ''}: "
                        f"{e(kielet.kaanna(k.selitys, kieli))}</li>"
                        for k in sorted(tulos.kohteet, key=lambda k: k.pisteet, reverse=True)) + "</ul>")
                    if tulos.pisteet is not None:
                        osat.append(f"<p><b>{e(t['pisteet'])}: {tulos.pisteet:.0f}</b></p>")
                avain = next((k.mittari for k in paikka.kohteet if k.nimi in uudet), next(iter(paikka.mittarit)))
                if not paikka.mittarit[avain].smhi:
                    osat.append(f'<img class="ehdotus-kaavio" alt="" loading="lazy" '
                                f'src="/kaavio/ehdotus/{e(tunniste)}{"?kieli=en" if en else ""}">')
    h, h2 = f"h{otsikkotaso}", f"h{otsikkotaso + 1}"
    taydennys = ehdotus.get("laji") == "taydenna"
    vanhat = {}
    if taydennys:
        alkuperainen = next((p for p in PAIKAT if p.nimi == ehdotus.get("paikka")), None)
        vanhat = {k.nimi: k for k in alkuperainen.kohteet} if alkuperainen else {}

    def rajateksti(k, yksikko: str) -> str:
        toimii, paras = _rajat(k.toimii, yksikko, k.muuttuja, kieli), _rajat(k.paras, yksikko, k.muuttuja, kieli)
        return (f"{'works' if en else 'toimii'} {toimii}"
                + (f", {'at its best' if en else 'parhaimmillaan'} {paras}" if paras != toimii else ""))

    tayd = ehdotukset.valmis_taydennys(ehdotus)
    tayd_en = (tayd.get("en") or {}) if en else {}   # englanninkieliset tekstit (täydennys kääntää)
    if tayd_en:
        tayd = {**tayd, **{k: v for k, v in tayd_en.items() if k not in ("huom", "ehdottajan_teksti")}}

    def huom_(k: dict) -> str:
        return tayd_en.get("huom", {}).get(k["nimi"]) or k.get("huom") or ""

    def alkupera(arvio: bool) -> str:   # kun täydennys on tehty: kuka kohteen rajat antoi
        if not tayd:
            return ""
        teksti = t["alkupera_arvio"] if arvio else t["alkupera_ehdottaja"]
        return f' <span class="pieni">({e(teksti)})</span>'

    def suureiden_rajat(rajat: dict) -> str:
        """Kaikki annetut rajat yksikköineen: 'virtaama m³/s: toimii yli 20 m³/s; vedenkorkeus m: …'."""
        osat = []
        for suure in ehdotukset.SUUREET:
            if suure in rajat:
                toimii, paras = rajat[suure]
                yksikko = ehdotukset.YKSIKOT[suure]
                teksti = _rajat(tuple(toimii), yksikko, "arvo", kieli)
                optimi = _rajat(tuple(paras), yksikko, "arvo", kieli)
                osat.append(f"{t['yksikko_q' if suure == 'virtaama' else 'yksikko_w']}: "
                            f"{'works' if en else 'toimii'} {teksti}"
                            + (f", {'at its best' if en else 'parhaimmillaan'} {optimi}" if optimi != teksti else ""))
        return "; ".join(osat) or t["ei_rajoja"]

    pisteytettavat = {k.nimi for k in (paikka.kohteet if paikka is not None else ()) if k.nimi in uudet}
    oletus = ehdotukset.oletussuure(ehdotus, PAIKAT)
    lisatyt, muutokset = [], []
    for k in ehdotukset.kaikki_kohteet(ehdotus) if paikka is not None else ():
        rajat = ehdotukset.kohteen_rajat(k, oletus)
        huomautus = ""
        if k["nimi"] not in pisteytettavat:   # ei rajoja tai ei mittaria rajojen suureelle
            syy = t["syy_rajat"] if not rajat else t["syy_mittari"]
            huomautus = f' <span class="pieni">({e(t["ei_pisteyteta"].format(syy=syy))})</span>'
        if k["nimi"] in vanhat:   # rajakorjaus: nykyinen -> ehdotettu
            v = vanhat[k["nimi"]]
            mittari = paikka.mittarit.get(v.mittari)
            _, yksikko = _mittarin_suure(mittari) if mittari else ("", "")
            huom = ""
            if k.get("huom") and k["huom"] != v.huom:
                huom = (f'<br><span class="pieni">{e(t["nyt"])}: {e(v.huom) or "–"}</span>'
                        f'<br>{e(t["huom"])} → {e(huom_(k))}')
            muutokset.append(f'<li><b>{e(k["nimi"])}</b>{alkupera(k.get("arvio"))}{huomautus}<br>'
                             f'<span class="pieni">{e(t["nyt"])}: {e(rajateksti(v, yksikko))}</span><br>'
                             f'<span class="rajat">→ {e(suureiden_rajat(rajat))}</span>{huom}</li>')
        else:
            lisatyt.append(f'<li><b>{e(k["nimi"])}</b>{alkupera(k.get("arvio"))}{huomautus}<br>'
                           f'<span class="rajat">{e(suureiden_rajat(rajat))}</span>'
                           f'{"<br>" + e(huom_(k)) if k.get("huom") else ""}</li>')
    teksti = "".join(f"<p>{e(kpl)}</p>" for kpl in re.split(r"\n\s*\n", tayd_en.get("ehdottajan_teksti")
                                                             or ehdotus.get("teksti") or "")
                     if kpl.strip())
    koottu = ""
    if tayd:   # Clauden lähteistä kokoama kuvaus, lähtö ja loppu, mittarin valinta ja lähteet
        osa = [f"<p>{e(kpl)}</p>" for kpl in re.split(r"\n\s*\n", tayd.get("teksti") or "") if kpl.strip()]
        paikat = []
        for avain, otsikko in (("lahto", "lahto"), ("loppu", "loppu")):
            if tayd.get(avain):
                piste = tayd.get(f"{avain}_sijainti")
                kartta = (f' · <a href="https://www.openstreetmap.org/?mlat={piste[0]}&amp;mlon={piste[1]}#map=14/'
                          f'{piste[0]}/{piste[1]}" target="_blank" rel="noopener">🗺 {e(t["kartta"])}</a>' if piste else "")
                paikat.append(f"<li><b>{e(t[otsikko])}:</b> {e(tayd[avain])}{kartta}</li>")
        if paikat:
            osa.append(f'<ul class="lahteet">{"".join(paikat)}</ul>')
        if tayd.get("mittari_perustelu"):
            osa.append(f'<p><b>{e(t["mittarin_valinta"])}:</b> {e(tayd["mittari_perustelu"])}</p>')
        if tayd.get("huomiot"):
            osa.append(f'<p class="huom"><b>{e(t["huomioita"])}:</b> {e(tayd["huomiot"])}</p>')
        if tayd.get("lahteet"):
            osa.append(f'<p><b>{e(t["lahteet"])}:</b></p><ul class="lahteet">' + "".join(
                f'<li><a href="{e(l["url"])}" target="_blank" rel="nofollow noopener">{e(l["nimi"])}</a></li>'
                if l.get("url") else f"<li>{e(l['nimi'])}</li>" for l in tayd["lahteet"]) + "</ul>")
        koottu = "".join(osa)
    linkit = ehdotus.get("linkit") or []
    linkkiosat = [(t[otsikko], _linkkilista([l for l in linkit if l.get("laji") == laji]))
                  for laji, otsikko in (("vesi", "vesitiedot"), ("video", "videot"), ("muu", "muut_linkit"))]
    linkkiosat = [(o, lista) for o, lista in linkkiosat if lista]
    if taydennys:
        hyvaksytty = ehdotus.get("tila") == "hyvaksytty"
        if muutokset:
            osat.append(f'<{h} class="muuttuu">{e(t["muutettu" if hyvaksytty else "muuttuu"])}</{h}>'
                        f'<p class="pieni">{e(t["muuttuu_ohje"])}</p><ul class="kohteet">{"".join(muutokset)}</ul>')
        lisaa = []
        if lisatyt:
            lisaa.append(f'<{h2}>{e(t["kohteet_rajat"])}</{h2}><ul class="kohteet">{"".join(lisatyt)}</ul>')
        if teksti:
            lisaa.append(f"<{h2}>{e(t['ehdottajan_teksti' if tayd else 'kuvaus'])}</{h2}>{teksti}")
        if koottu:
            lisaa.append(f"<{h2}>{e(t['koottu'])}</{h2}>{koottu}")
        lisaa += [f'<{h2}>{e(o)}</{h2}><ul class="lahteet">{lista}</ul>' for o, lista in linkkiosat]
        if lisaa:
            osat.append(f'<{h} class="tulossa">{e(t["lisatty" if hyvaksytty else "tulossa"])}</{h}>' + "".join(lisaa))
    else:
        if koottu:
            osat.append(f"<{h}>{e(t['koottu'])}</{h}>{koottu}")
        if teksti:
            osat.append(f"<{h}>{e(t['ehdottajan_teksti' if tayd else 'kuvaus'])}</{h}>{teksti}")
        if lisatyt:
            osat.append(f'<{h}>{e(t["kohteet_rajat"])}</{h}><ul class="kohteet">{"".join(lisatyt)}</ul>')
        osat += [f'<{h}>{e(o)}</{h}><ul class="lahteet">{lista}</ul>' for o, lista in linkkiosat]
    if not taydennys:   # sama reitti Muissa kohteissa: vain linkki
        osat.append(_muut_linkit(_muut_osumat(tunniste, ehdotus), kieli))
    if ehdotus.get("sijainti"):
        lev, pit = ehdotus["sijainti"]
        osat.append(f'<p><a href="https://www.openstreetmap.org/?mlat={lev}&amp;mlon={pit}#map=13/{lev}/{pit}" '
                    f'target="_blank" rel="noopener">🗺 {lev:.5f}, {pit:.5f}</a></p>')
    if ehdotus.get("ehdottaja"):
        osat.append(f'<p class="pieni">{e(t["ehdottaja_nimi"])}: {e(ehdotus["ehdottaja"])}</p>')
    return "".join(osat)


def ehdotussivu(tunniste: str, ehdotus: dict, kieli: str, yllapitaja: bool = False,
                hakija: osm.Hakija | None = None) -> str:
    """Ehdotuksen esikatselu tai julkaistu sivu /ehdotus/<tunniste>."""
    t = ehdotukset.tekstit(kieli)
    tila = ehdotus.get("tila", "odottaa")
    if ehdotus.get("laji") == "taydenna":
        paikka = next((p for p in PAIKAT if p.nimi == ehdotus.get("paikka")), None)
        otsikko = f'{t["taydennys"]}: {ehdotus.get("paikka", "?")}'
        alku = (f'<p><a href="{e(paikan_osoite(paikka, kieli))}">{e(paikka.nimi)}</a></p>' if paikka else "")
    else:
        otsikko, alku = ehdotukset.nimi(ehdotus), ""
    meta = (f'<div class="meta">{e(t["esikatselu"] if tila != "hyvaksytty" else t["uusi_kohde"])} · '
            f'<span class="tila-merkki tila-{e(tila)}">{e(t["tila_" + tila])}</span></div>')
    ilmoitus = ""
    if tila == "odottaa":
        vapid = halytykset.avaimet(uudelleen=False)
        ilmoitus = f'<p class="pieni">{e(t["tallenna_linkki"])}</p>'
        if vapid:
            ilmoitus += f"""<p><button class="nappi toissijainen" type="button" id="ilmoita" hidden>{e(t["ilmoita"])}</button>
<span id="ilmoitus-tila" class="pieni"></span></p>
<script>
(() => {{
  const nappi = document.getElementById("ilmoita"), tila = document.getElementById("ilmoitus-tila");
  if (!("serviceWorker" in navigator && "PushManager" in window && "Notification" in window)) return;
  nappi.hidden = false;
  const avain = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - s.length % 4) % 4)),
                                     c => c.charCodeAt(0));
  nappi.addEventListener("click", async () => {{
    try {{
      if (await Notification.requestPermission() !== "granted") throw new Error("–");
      const r = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const tilaus = await r.pushManager.getSubscription()
        || await r.pushManager.subscribe({{userVisibleOnly: true, applicationServerKey: avain({json.dumps(vapid[0])})}});
      const v = await fetch("/api/ehdotus/{tunniste}/tilaus", {{method: "POST",
        headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{tilaus: tilaus.toJSON()}})}});
      if (!v.ok) throw new Error("HTTP " + v.status);
      nappi.hidden = true;
      tila.textContent = {json.dumps(t["ilmoitus_tilattu"])};
    }} catch (virhe) {{
      tila.textContent = {json.dumps(t["ilmoitus_virhe"])} + " (" + virhe.message + ")";
    }}
  }});
}})();
</script>"""
    taydennys = ehdotus.get("taydennys") or {}
    taydennys_tila = ""
    if taydennys.get("tila") == "kaynnissa":
        taydennys_tila = f'<p class="huom">{e(t["taydennys_kaynnissa"])}</p>'
    elif taydennys.get("tila") == "valmis":
        taydennys_tila = (f'<p class="pieni">{e(t["taydennys_valmis"])} '
                          f'{e((taydennys.get("aika") or "")[:16].replace("T", " "))}</p>')
    elif taydennys.get("tila") == "virhe" and yllapitaja:
        taydennys_tila = f'<p class="virhe">{e(t["taydennys_virhe"])}: {e(taydennys.get("virhe", ""))}</p>'
    if taydennys.get("kaannos") == "kaynnissa" and yllapitaja:
        taydennys_tila += f'<p class="huom">{e(t["kaannos_kaynnissa"])}</p>'
    elif taydennys.get("kaannos") == "virhe" and yllapitaja:
        taydennys_tila += (f'<p class="virhe">{e(t["kaannos_virhe"])}: '
                           f'{e(taydennys.get("kaannos_virhe") or "GitHub-ajo epäonnistui")}</p>')
    hallinta = ""
    if yllapitaja:
        taydenna = t["taydenna_uudelleen"] if taydennys.get("tila") == "valmis" else t["taydenna_nappi"]
        napit = ""
        if tila == "odottaa":   # käsitellylle ei hyväksyntää eikä hylkäystä
            napit = (f'<button class="nappi" name="toiminto" value="hyvaksy">{e(t["hyvaksy"])}</button>'
                     f'<button class="nappi toissijainen" name="toiminto" value="hylkaa">{e(t["hylkaa"])}</button>'
                     + (f'<button class="nappi toissijainen" name="toiminto" value="taydenna">{e(taydenna)}</button>'
                        if taydennys.get("tila") != "kaynnissa" else ""))
        if taydennys.get("tila") == "valmis" and not taydennys.get("en") and taydennys.get("kaannos") != "kaynnissa":
            napit += f'<button class="nappi toissijainen" name="toiminto" value="kaanna">{e(t["kaanna_nappi"])}</button>'
        if napit:
            hallinta = (f'<form method="post" action="/ehdotus/{e(tunniste)}/kasittele" style="margin-top:16px">'
                        f'<b>{e(t["yllapito"])}:</b> {napit} <a href="/yllapito">{e(t["yllapito"])} →</a></form>')
    yksityiset = ""
    if yllapitaja and ehdotus.get("yksityiset_linkit"):   # vain ylläpitäjälle, ei linkkeinä
        yksityiset = (f'<h2>{e(t["yksityiset_otsikko"])}</h2><ul class="lahteet">'
                      + "".join(f"<li><code>{e(u)}</code></li>" for u in ehdotus["yksityiset_linkit"]) + "</ul>")
    kaikki_kaksoset = ehdotuksen_kaksoiskappaleet(tunniste, ehdotus) if tila == "odottaa" else []
    kaksoset = [k for k in kaikki_kaksoset if not k["osoite"].startswith("/muut/")]
    muut_osumat = [k for k in kaikki_kaksoset if k["osoite"].startswith("/muut/")]
    kaksois_html = ""
    if muut_osumat and not ehdotukset.pisteytettava(ehdotus):   # muuten Muut kohteet on vain linkki sivulla
        kaksois_html += f'<p class="pieni">ℹ️ {e(t["muut_ei_pisteytettava"])}</p>'
    if kaksoset:
        muunnot = ""
        if yllapitaja:   # sovelluksen paikka: ehdotuksen pelipaikat voi lisätä siihen täydennyksenä
            for k in kaksoset:
                paikka = next((p for p in PAIKAT if paikan_osoite(p) == k["osoite"]), None)
                if paikka is None:
                    continue
                uudet, korjaukset = ehdotukset.uudet_kohteet_paikkaan(ehdotus, paikka)
                muunnot += (f'<button class="nappi toissijainen" name="toiminto" '
                            f'value="muunna:{e(paikkasivut.tunniste(paikka.nimi))}">'
                            f'{e(t["muunna"].format(paikka=paikka.nimi, uudet=len(uudet), korjaukset=len(korjaukset)))}'
                            f'</button>')
            if muunnot:
                muunnot = (f'<form method="post" action="/ehdotus/{e(tunniste)}/kasittele">{muunnot}'
                           f'<p class="pieni">{e(t["muunna_ohje"])}</p></form>')
        kaksois_html += (f'<div class="huom"><b>⚠️ {e(t["kaksoiskappale"])}</b><ul>' + "".join(
            f'<li><a href="{e(k["osoite"])}">{e(k["nimi"])}</a> <span class="pieni">({e(k["syy"])})</span></li>'
            for k in kaksoset) + f"</ul>{muunnot}</div>")
    if ehdotus.get("alkuperainen_nimi"):
        kaksois_html += f'<p class="pieni">{e(t["muunnettu"].format(nimi=ehdotus["alkuperainen_nimi"]))}</p>'
    kuva_html = kuvaosio(otsikko, kieli) if ehdotus.get("laji") == "uusi" and tila == "hyvaksytty" else ""
    runko = (f"<h1>{e(otsikko)}</h1>{meta}{kuva_html}{alku}{kaksois_html}{taydennys_tila}{hallinta}{ilmoitus}"
             f"{_ehdotuksen_sisalto(tunniste, ehdotus, kieli, hakija)}{yksityiset}")
    return _sivupohja(otsikko, runko, kieli, _osoite(kieli=kieli))


def _kayttajien_lisaykset(paikka, kieli: str) -> str:
    """Paikkasivun osio hyväksytyistä täydennyksistä (kohteet, linkit, teksti)."""
    t = ehdotukset.tekstit(kieli)
    omat = [(tun, ed) for tun, ed in hyvaksytyt_ehdotukset()
            if ed.get("laji") == "taydenna" and ed.get("paikka") == paikka.nimi]
    if not omat:
        return ""
    osat = []
    for tun, ed in omat:
        sisalto = _ehdotuksen_sisalto(tun, ed, kieli, tilanne_mukaan=False, otsikkotaso=3)
        osat.append(f'<div class="lisays">{sisalto}<p class="pieni"><a href="/ehdotus/{e(tun)}'
                    f'{"?kieli=en" if kieli == "en" else ""}">{e(t["lisaysta"])} →</a></p></div>')
    return f"<h2>{e(t['kayttajien_lisaykset'])}</h2>" + "".join(osat)


def ehdotuksen_kaavio(tunniste: str, kieli: str, hakija: osm.Hakija | None = None) -> str | None:
    """Ehdotuksen mittarin kaavio ehdotetuin rajoin (/kaavio/ehdotus/<tunniste>)."""
    if not ehdotukset.kelvollinen_tunniste(tunniste):
        return None
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste) if kanta else None
    if not ehdotus:
        return None
    paikka, uudet = ehdotukset.paikaksi(ehdotus, PAIKAT)
    if paikka is None or not paikka.mittarit:
        return None
    avain = next((k.mittari for k in paikka.kohteet if k.nimi in uudet), next(iter(paikka.mittarit)))
    mittari = paikka.mittarit[avain]
    if mittari.smhi:
        return None
    hakija = hakija or osm.Hakija(aikaraja=20)
    otsikko = f"{paikka.nimi} – {kielet.kaanna('mittari', kieli)} {aseman_nimi(mittari.kaavio)}"
    return _mittarin_svg(paikka, avain, mittari, hakija, otsikko, kieli)


def _push_kaikille(kanta, kokoelma: str, viesti: dict) -> int:
    """Lähettää viestin kokoelman push-tilauksille; vanhentuneet poistetaan. Palauttaa onnistuneet."""
    avainpari = halytykset.avaimet(kanta)
    if not avainpari:
        return 0
    onnistui = 0
    for tun, tilaus in kanta.listaa(kokoelma).items():
        tila = halytykset.laheta(tilaus, viesti, avainpari)
        if tila in (404, 410):
            kanta.poista(kokoelma, tun)
        elif 200 <= tila < 300:
            onnistui += 1
    return onnistui


def _ilmoita_ehdottajalle(kanta, tunniste: str, ehdotus: dict) -> None:
    tilaus = ehdotus.get("tilaus")
    avainpari = halytykset.avaimet(kanta)
    if not tilaus or not avainpari:
        return
    en = ehdotus.get("kieli") == "en"
    hyvaksytty = ehdotus.get("tila") == "hyvaksytty"
    viesti = {"otsikko": ("Your suggestion was approved" if hyvaksytty else "Your suggestion was rejected") if en
              else ("Ehdotuksesi hyväksyttiin" if hyvaksytty else "Ehdotuksesi hylättiin"),
              "teksti": ehdotukset.nimi(ehdotus), "url": f"/ehdotus/{tunniste}" + ("?kieli=en" if en else "")}
    halytykset.laheta(tilaus, viesti, avainpari)


def tallenna_ehdotus(kentat: dict[str, list[str]], kieli: str, ip: str) -> tuple[str | None, str]:
    """Lomakkeen tallennus: (tunniste, '') tai (None, virhe). Ilmoittaa ylläpitäjille."""
    t = ehdotukset.tekstit(kieli)
    if ehdotukset.roskaa(kentat, ip):
        return None, t["virhe_jono"]
    ehdotus, virhe = ehdotukset.tulkitse(kentat, PAIKAT, kieli)
    if not ehdotus:
        return None, virhe
    kanta = _kanta()
    if not kanta:
        return None, t["virhe_tallennus"]
    try:
        odottavia = sum(1 for x in kaikki_ehdotukset(pakota=True).values() if x.get("tila") == "odottaa")
        if odottavia >= ehdotukset.ODOTTAVIA_ENINTAAN:
            return None, t["virhe_jono"]
        tunniste = ehdotukset.uusi_tunniste()
        kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    except (firestore.FirestoreVirhe, OSError):
        return None, t["virhe_tallennus"]
    laji = "täydennys" if ehdotus["laji"] == "taydenna" else "uusi kohde"
    kaksoset = [k for k in ehdotuksen_kaksoiskappaleet(tunniste, ehdotus) if not k["osoite"].startswith("/muut/")]
    try:
        _push_kaikille(kanta, ehdotukset.YLLAPITO, {
            "otsikko": f"Uusi ehdotus: {ehdotukset.nimi(ehdotus)}",
            "teksti": f"{laji}: {len(ehdotus['kohteet'])} kohdetta, {len(ehdotus['linkit'])} linkkiä"
                      + (f" – {ehdotus['ehdottaja']}" if ehdotus.get("ehdottaja") else "")
                      + (f" ⚠️ mahdollisesti sama kuin {kaksoset[0]['nimi']}" if kaksoset else ""),
            "url": f"/ehdotus/{tunniste}",
            # ilmoituksen nappi (Android, työpöytä): service worker kutsuu rajapintaa ja avaa esikatselun
            "toiminnot": [{"action": "taydenna", "title": "🔍 Täydennä", "api": f"/api/ehdotus/{tunniste}/taydenna"}]})
    except (firestore.FirestoreVirhe, OSError):
        pass   # ehdotus on tallessa, vaikka ilmoitus epäonnistuisi
    return tunniste, ""


def kaanna_ehdotus(tunniste: str) -> tuple[bool, str]:
    """Ylläpitäjän "Käännä englanniksi": valmiin täydennyksen käännös (myös hyväksytylle kohteelle)."""
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste) if kanta and ehdotukset.kelvollinen_tunniste(tunniste) else None
    if not ehdotus or not ehdotukset.valmis_taydennys(ehdotus):
        return False, "ehdotuksella ei ole valmista täydennystä"
    ok, viesti = ehdotukset.kaynnista_taydennys(tunniste, os.environ.get("GITHUB_TAYDENNYS_TOKEN"), kaannos=True)
    ehdotus["taydennys"]["kaannos"] = "kaynnissa" if ok else "virhe"
    ehdotus["taydennys"]["kaannos_virhe"] = "" if ok else viesti
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    return ok, viesti


def taydenna_ehdotus(tunniste: str) -> tuple[bool, str]:
    """Ylläpitäjän "Täydennä": käynnistää Claude Code -ajon GitHub Actionsissa (ehdotukset.TYONKULKU)."""
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste) if kanta and ehdotukset.kelvollinen_tunniste(tunniste) else None
    if not ehdotus or ehdotus.get("tila") != "odottaa":
        return False, "ehdotusta ei löydy tai se on jo käsitelty"
    ok, viesti = ehdotukset.kaynnista_taydennys(tunniste, os.environ.get("GITHUB_TAYDENNYS_TOKEN"))
    nyt = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    vanha = {k: v for k, v in (ehdotus.get("taydennys") or {}).items() if k not in ("tila", "virhe", "ilmoitettu")}
    ehdotus["taydennys"] = {**vanha, "tila": "kaynnissa", "pyydetty": nyt} if ok else \
        {**vanha, "tila": "virhe", "virhe": viesti, "pyydetty": nyt}
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    return ok, viesti


def ilmoita_taydennyksesta(tunniste: str) -> bool:
    """Kutsutaan täydennysajon lopuksi: ilmoitus ylläpitäjälle (hyväksy tai hylkää) ja ehdottajalle
    (esikatselu valmis). Kerran täydennystä kohden; ei vaadi tunnistautumista."""
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste) if kanta and ehdotukset.kelvollinen_tunniste(tunniste) else None
    taydennys = (ehdotus or {}).get("taydennys") or {}
    if taydennys.get("tila") != "valmis" or taydennys.get("ilmoitettu"):
        return False
    taydennys["ilmoitettu"] = True
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    nimi = ehdotukset.nimi(ehdotus)
    try:
        _push_kaikille(kanta, ehdotukset.YLLAPITO, {
            "otsikko": f"Täydennetty: {nimi}", "teksti": "Esikatselu valmis – hyväksy tai hylkää." + "".join(
                f" ⚠️ Mahdollisesti sama kuin {k['nimi']} ({k['syy']})."
                for k in [k for k in ehdotuksen_kaksoiskappaleet(tunniste, ehdotus)
                          if not k["osoite"].startswith("/muut/")][:1]),
            "url": f"/ehdotus/{tunniste}"})
        avainpari = halytykset.avaimet(kanta)
        if ehdotus.get("tilaus") and avainpari:
            en = ehdotus.get("kieli") == "en"
            halytykset.laheta(ehdotus["tilaus"], {
                "otsikko": "Preview of your suggestion is ready" if en else "Ehdotuksesi esikatselu on valmis",
                "teksti": nimi, "url": f"/ehdotus/{tunniste}" + ("?kieli=en" if en else "")}, avainpari)
    except (firestore.FirestoreVirhe, OSError):
        pass
    return True


def kasittele_ehdotus(tunniste: str, toiminto: str) -> bool:
    """Ylläpitäjän hyväksyntä tai hylkäys; ilmoittaa ehdottajalle. False = ei löytynyt."""
    if toiminto == "taydenna":
        taydenna_ehdotus(tunniste)
        return True
    if toiminto == "kaanna":
        kaanna_ehdotus(tunniste)
        return True
    if toiminto.startswith("muunna:"):   # uusi kohde onkin olemassa oleva paikka -> täydennys siihen
        paikka = PAIKKASIVUT.get(toiminto.removeprefix("muunna:"))
        kanta = _kanta()
        ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste) if kanta and ehdotukset.kelvollinen_tunniste(tunniste) \
            else None
        if not paikka or not ehdotus or ehdotus.get("laji") != "uusi" or ehdotus.get("tila") != "odottaa":
            return False
        kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotukset.muunna_taydennykseksi(ehdotus, paikka))
        kaikki_ehdotukset(pakota=True)
        return True
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste) if kanta and ehdotukset.kelvollinen_tunniste(tunniste) else None
    if not ehdotus or toiminto not in ("hyvaksy", "hylkaa"):
        return False
    ehdotus["tila"] = "hyvaksytty" if toiminto == "hyvaksy" else "hylatty"
    ehdotus["kasitelty"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    global _tilanne
    _tilanne = None   # hyväksytty kohde tulee listaan heti tällä palvelininstanssilla
    try:
        _ilmoita_ehdottajalle(kanta, tunniste, ehdotus)
    except OSError:
        pass
    ehdotus.pop("tilaus", None)   # ilmoitus lähetetty: tilausta ei säilytetä
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    kaikki_ehdotukset(pakota=True)
    return True


def yllapitosivu(kirjautunut: bool, virhe: str = "") -> str:
    """Ylläpito: kirjautuminen, ehdotusten lista ja push-ilmoitusten tilaus tälle laitteelle."""
    salasana = os.environ.get("YLLAPITO_SALASANA")
    if not salasana:
        runko = ("<h1>Ylläpito</h1><p>Ylläpito ei ole käytössä: aseta Vercelin ympäristömuuttuja "
                 "<code>YLLAPITO_SALASANA</code>.</p>")
        return _sivupohja("Ylläpito", runko, "fi")
    if not kirjautunut:
        runko = (f'<h1>Ylläpito</h1>{f"<p class=virhe>{e(virhe)}</p>" if virhe else ""}'
                 '<form class="lomake" method="post" action="/yllapito"><label for="salasana">Salasana</label>'
                 '<input type="password" id="salasana" name="salasana" autocomplete="current-password" '
                 'style="max-width:300px;padding:6px 8px">'
                 '<p><button class="nappi" type="submit">Kirjaudu</button></p></form>')
        return _sivupohja("Ylläpito", runko, "fi")
    kaikki = kaikki_ehdotukset(pakota=True)
    osat = []
    for tila, otsikko in (("odottaa", "Odottaa hyväksyntää"), ("hyvaksytty", "Hyväksytyt"), ("hylatty", "Hylätyt")):
        omat = sorted(((tun, ed) for tun, ed in kaikki.items() if ed.get("tila") == tila),
                      key=lambda x: x[1].get("luotu", ""), reverse=True)
        rivit = "".join(
            f'<li><a href="/ehdotus/{e(tun)}">{e(ehdotukset.nimi(ed))}</a> <span class="pieni">· '
            f'{"täydennys" if ed.get("laji") == "taydenna" else "uusi kohde"} · {e(ed.get("luotu", "")[:16])}'
            f'{" · " + e(ed["ehdottaja"]) if ed.get("ehdottaja") else ""}</span></li>' for tun, ed in omat)
        osat.append(f"<h2>{otsikko} ({len(omat)})</h2><ul>{rivit or '<li class=pieni>–</li>'}</ul>")
    vapid = halytykset.avaimet(uudelleen=False)
    tilaus = ""
    if vapid:
        tilaus = f"""<p><button class="nappi" type="button" id="tilaa">🔔 Ilmoitukset uusista ehdotuksista tälle laitteelle</button>
<span id="tilaus-tila" class="pieni"></span></p>
<script>
(() => {{
  const nappi = document.getElementById("tilaa"), tila = document.getElementById("tilaus-tila");
  const avain = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - s.length % 4) % 4)),
                                     c => c.charCodeAt(0));
  nappi.addEventListener("click", async () => {{
    try {{
      if (!("serviceWorker" in navigator && "PushManager" in window)) throw new Error("selain ei tue");
      if (await Notification.requestPermission() !== "granted") throw new Error("ei lupaa");
      const r = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const t = await r.pushManager.getSubscription()
        || await r.pushManager.subscribe({{userVisibleOnly: true, applicationServerKey: avain({json.dumps(vapid[0])})}});
      const v = await fetch("/api/yllapito/tilaus", {{method: "POST", headers: {{"Content-Type": "application/json"}},
                                                     body: JSON.stringify({{tilaus: t.toJSON()}})}});
      if (!v.ok) throw new Error("HTTP " + v.status);
      tila.textContent = "Tilattu – saat ilmoituksen jokaisesta uudesta ehdotuksesta.";
    }} catch (virhe) {{ tila.textContent = "Tilaus epäonnistui: " + virhe.message; }}
  }});
}})();
</script>"""
    runko = ("<h1>Ylläpito: ehdotukset</h1>" + tilaus + "".join(osat)
             + '<form method="post" action="/yllapito"><input type="hidden" name="ulos" value="1">'
               '<button class="nappi toissijainen" type="submit">Kirjaudu ulos</button></form>')
    return _sivupohja("Ylläpito", runko, "fi")


def ehdotus_api(polku: str, environ, metodi: str):
    """POST-reitit ja ehdotussivut: palauttaa (status, otsakkeet, runko) tai None, jos polku ei kuulu tänne."""
    kysely = parse_qs(environ.get("QUERY_STRING", ""))
    kieli = kielet.kieli(kysely)
    salasana = os.environ.get("YLLAPITO_SALASANA")
    yllapitaja = ehdotukset.on_yllapitaja(environ.get("HTTP_COOKIE", ""), salasana)
    html_tyyppi = [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store")]

    def runko_lomake() -> dict[str, list[str]]:
        try:
            pituus = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            pituus = 0
        if not 0 < pituus <= 30000:
            return {}
        return parse_qs(environ["wsgi.input"].read(pituus).decode("utf-8", errors="replace"), keep_blank_values=True)

    def runko_json():
        try:
            pituus = int(environ.get("CONTENT_LENGTH") or 0)
            return json.loads(environ["wsgi.input"].read(pituus)) if 0 < pituus <= 4096 else None
        except (ValueError, KeyError):
            return None

    def ohjaa(osoite: str, evaste: str | None = None):
        otsakkeet = [("Location", osoite), ("Cache-Control", "no-store"), ("Content-Length", "0")]
        if evaste:
            otsakkeet.append(("Set-Cookie", evaste))
        return "303 See Other", otsakkeet, b""

    def json_vastaus(status: str, data: dict):
        return status, [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")], \
            json.dumps(data, ensure_ascii=False).encode("utf-8")

    if polku == "/ehdota":
        if metodi == "POST":
            kentat = runko_lomake()
            ip = (environ.get("HTTP_X_FORWARDED_FOR") or environ.get("REMOTE_ADDR") or "").split(",")[0].strip()
            tunniste, virhe = tallenna_ehdotus(kentat, kieli, ip)
            if tunniste:
                return ohjaa(f"/ehdotus/{tunniste}" + ("?kieli=en" if kieli == "en" else ""))
            return "400 Bad Request", html_tyyppi, ehdotuslomake(kieli, virhe=virhe, kentat=kentat).encode("utf-8")
        laji = (kysely.get("laji") or ["uusi"])[0]
        return "200 OK", html_tyyppi, ehdotuslomake(kieli, "taydenna" if laji == "taydenna" else "uusi",
                                                    (kysely.get("paikka") or [""])[0]).encode("utf-8")
    m = re.fullmatch(r"/ehdotus/([A-Za-z0-9_-]+)(/kasittele)?", polku)
    if m:
        tunniste = m.group(1)
        if m.group(2):
            if metodi != "POST" or not yllapitaja:
                return "403 Forbidden", html_tyyppi, b"Ei oikeutta."
            toiminto = (runko_lomake().get("toiminto") or [""])[0]
            if not kasittele_ehdotus(tunniste, toiminto):
                return "404 Not Found", html_tyyppi, b"Ehdotusta ei loydy."
            return ohjaa(f"/ehdotus/{tunniste}")
        kanta = _kanta()
        ehdotus = (kanta.lue(ehdotukset.KOKOELMA, tunniste)
                   if kanta and ehdotukset.kelvollinen_tunniste(tunniste) else None)
        if not ehdotus or (ehdotus.get("tila") == "hylatty" and not yllapitaja):
            return "404 Not Found", html_tyyppi, "Ehdotusta ei löydy.\n".encode("utf-8")
        return "200 OK", html_tyyppi, ehdotussivu(tunniste, ehdotus, kieli, yllapitaja).encode("utf-8")
    m = re.fullmatch(r"/api/ehdotus/([A-Za-z0-9_-]+)/(taydenna|taydennys-valmis)", polku)
    if m and metodi == "POST":
        if m.group(2) == "taydennys-valmis":
            return json_vastaus("200 OK", {"ilmoitettu": ilmoita_taydennyksesta(m.group(1))})
        if not yllapitaja:
            return json_vastaus("403 Forbidden", {"virhe": "kirjaudu ensin"})
        ok, viesti = taydenna_ehdotus(m.group(1))
        return json_vastaus("200 OK" if ok else "502 Bad Gateway", {"kaynnistetty": ok, "viesti": viesti})
    m = re.fullmatch(r"/api/ehdotus/([A-Za-z0-9_-]+)/tilaus", polku)
    if m and metodi == "POST":
        tilaus = ehdotukset.tarkista_push(runko_json())
        kanta = _kanta()
        tunniste = m.group(1)
        ehdotus = (kanta.lue(ehdotukset.KOKOELMA, tunniste)
                   if kanta and ehdotukset.kelvollinen_tunniste(tunniste) else None)
        if not tilaus or not ehdotus or ehdotus.get("tila") != "odottaa":
            return json_vastaus("400 Bad Request", {"virhe": "virheellinen tilaus tai ehdotus"})
        ehdotus["tilaus"] = tilaus
        kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
        return json_vastaus("200 OK", {"tilattu": True})
    if polku == "/api/yllapito/tilaus" and metodi == "POST":
        tilaus = ehdotukset.tarkista_push(runko_json())
        kanta = _kanta()
        if not yllapitaja:
            return json_vastaus("403 Forbidden", {"virhe": "kirjaudu ensin"})
        if not tilaus or not kanta:
            return json_vastaus("400 Bad Request", {"virhe": "virheellinen tilaus"})
        kanta.kirjoita(ehdotukset.YLLAPITO, halytykset.tunniste(tilaus["endpoint"]), tilaus)
        halytykset.laheta(tilaus, {"otsikko": "Ylläpidon ilmoitukset käytössä",
                                   "teksti": "Saat ilmoituksen uusista ehdotuksista.", "url": "/yllapito"},
                          halytykset.avaimet(kanta))
        return json_vastaus("200 OK", {"tilattu": True})
    if polku == "/yllapito":
        if metodi == "POST":
            kentat = runko_lomake()
            if kentat.get("ulos"):
                return ohjaa("/yllapito", f"{ehdotukset.EVASTE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict")
            annettu = (kentat.get("salasana") or [""])[0]
            if salasana and hmac.compare_digest(annettu.encode(), salasana.encode()):
                return ohjaa("/yllapito", f"{ehdotukset.EVASTE}={ehdotukset.kirjautumisavain(salasana)}; Path=/; "
                                          "Max-Age=7776000; HttpOnly; Secure; SameSite=Strict")
            time.sleep(1)   # hidastaa arvailua
            return "403 Forbidden", html_tyyppi, yllapitosivu(False, "Väärä salasana.").encode("utf-8")
        return "200 OK", html_tyyppi, yllapitosivu(yllapitaja).encode("utf-8")
    return None


def app(environ, start_response):
    polku = environ.get("PATH_INFO", "/").rstrip("/") or "/"
    metodi = environ.get("REQUEST_METHOD", "GET")
    kysely = {k: v for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()
              if k in ("tyyppi", "max_km", "kieli")}

    def vastaa(status: str, tyyppi: str, runko: str | bytes, valimuisti: str = "no-store"):
        data = runko if isinstance(runko, bytes) else runko.encode("utf-8")
        start_response(status, [("Content-Type", tyyppi), ("Content-Length", str(len(data))),
                                ("Cache-Control", valimuisti)])
        return [b"" if metodi == "HEAD" else data]

    if polku == "/api/halytys":
        status, tulos = halytys_api(environ, metodi)
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False))
    ehdotusvastaus = ehdotus_api(polku, environ, metodi)
    if ehdotusvastaus:
        status, otsakkeet, runko = ehdotusvastaus
        if not any(n == "Content-Length" for n, _ in otsakkeet):
            otsakkeet = otsakkeet + [("Content-Length", str(len(runko)))]
        start_response(status, otsakkeet)
        return [b"" if metodi == "HEAD" else runko]
    if metodi not in ("GET", "HEAD"):
        return vastaa("405 Method Not Allowed", "text/plain; charset=utf-8", "Vain GET.\n")
    if polku == "/manifest.webmanifest":
        return vastaa("200 OK", "application/manifest+json; charset=utf-8",
                      sovellus.manifest(kielet.kieli(kysely)), "public, max-age=86400")
    if polku.startswith("/kuvake-") and polku.endswith(".png"):
        koko = polku.removeprefix("/kuvake-").removesuffix(".png")
        if koko.isdigit() and int(koko) in sovellus.KOOT:
            return vastaa("200 OK", "image/png", sovellus.kuvake(int(koko)), "public, max-age=604800")
        return vastaa("404 Not Found", "text/plain; charset=utf-8", "Ei löydy.\n")
    if polku == "/sw.js":
        return vastaa("200 OK", "application/javascript; charset=utf-8", halytykset.SERVICE_WORKER, "no-cache")
    if polku == "/api/halyta":
        status, tulos = halyta(environ)
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False))
    if polku == "/api/ajomatkat":
        status, tulos = ajomatkat(parse_qs(environ.get("QUERY_STRING", "")).get("lahto", [""])[0])
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False),
                      AJOMATKA_CACHE if status.startswith("200") else "no-store")
    if polku == "/api/kapsi":
        status, tulos = kapsi_kerays(environ)
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False))
    if polku == "/api/arkistoi":
        status, tulos = arkistoi(environ)
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False))
    if polku.startswith("/kaavio/"):
        kaavio = polku.removeprefix("/kaavio/")
        paikan_nimi = parse_qs(environ.get("QUERY_STRING", "")).get("paikka", [None])[0]
        kieli = kielet.kieli(kysely)
        kuvasta = parse_qs(environ.get("QUERY_STRING", "")).get("lahde", [""])[0] == "kuva"
        try:   # reissun ajankohta (unix s) pystyviivaksi kaavioon
            reissu = float(parse_qs(environ.get("QUERY_STRING", "")).get("reissu", [""])[0])
        except ValueError:
            reissu = None
        merkki = kaavio_svg.reissu.set(reissu)
        try:   # matka-aika perille (min): osoittimen siirto palauttaa lähtöajan
            matka = kaavio_svg.matka.set(float(parse_qs(environ.get("QUERY_STRING", "")).get("matka", [""])[0]))
        except ValueError:
            matka = kaavio_svg.matka.set(None)
        # kaavion muoto: pysty (oletus, puhelin) tai vaaka (sivun JS lisää leveällä näytöllä)
        muoto = kaavio_svg.muoto.set(parse_qs(environ.get("QUERY_STRING", "")).get("muoto", ["pysty"])[0])
        try:
            kuva = (ehdotuksen_kaavio(kaavio.removeprefix("ehdotus/"), kieli) if kaavio.startswith("ehdotus/")
                    else smhi_kaavio_svg(kaavio, paikan_nimi=paikan_nimi, kieli=kieli) if kaavio.startswith("smhi/")
                    else syke_kaavio_svg(kaavio.removeprefix("syke/"), paikan_nimi=paikan_nimi, kieli=kieli,
                                         kuvasta=kuvasta)
                    if kaavio.startswith("syke/") else None)
        finally:
            kaavio_svg.reissu.reset(merkki)
            kaavio_svg.matka.reset(matka)
            kaavio_svg.muoto.reset(muoto)
        if kuva is None:
            return vastaa("404 Not Found", "text/plain; charset=utf-8", "Kaaviota ei löydy.\n")
        return vastaa("200 OK", "image/svg+xml; charset=utf-8", kuva, CACHE_CONTROL)
    if polku.startswith("/retki/"):
        retki = retket.sivu(polku.removeprefix("/retki/"), TYYLI)
        if retki is None:
            return vastaa("404 Not Found", "text/plain; charset=utf-8", "Retkeä ei löydy.\n")
        return vastaa("200 OK", "text/html; charset=utf-8", retki, "public, max-age=3600")
    if polku == "/muut":
        return vastaa("200 OK", "text/html; charset=utf-8", muut_kohteet.luettelo(TYYLI), "public, max-age=3600")
    if polku.startswith("/muut/"):
        kohde = muut_kohteet.HAKEMISTO.get(polku.removeprefix("/muut/"))
        if kohde is None:
            return vastaa("404 Not Found", "text/plain; charset=utf-8", "Kohdetta ei löydy.\n")
        return vastaa("200 OK", "text/html; charset=utf-8", muut_kohteet.sivu(kohde, TYYLI), "public, max-age=3600")
    if polku.startswith("/paikka/"):
        paikka = PAIKKASIVUT.get(polku.removeprefix("/paikka/"))
        if paikka is None:
            return vastaa("404 Not Found", "text/plain; charset=utf-8", "Paikkaa ei löydy.\n")
        return vastaa("200 OK", "text/html; charset=utf-8", paikkasivu(paikka, kielet.kieli(kysely)),
                      "public, max-age=3600")
    if polku not in ("/", "/api"):
        return vastaa("404 Not Found", "text/plain; charset=utf-8", "Ei löydy.\n")

    tilanne = hae_tilanne()
    if not tilanne.lukemia:
        viesti = "SYKE:n kaavioita ei saatu luettua.\n" + "\n".join(tilanne.varoitukset)
        return vastaa("503 Service Unavailable", "text/plain; charset=utf-8", viesti)
    tulokset = suodata(tilanne.tulokset, kysely)
    if polku == "/api":
        tulos = melonta.json_tulos(tulokset, tilanne.varoitukset, tilanne.paivitetty.date())
        tulos["paivitetty"] = tilanne.paivitetty.isoformat(timespec="seconds")
        return vastaa("200 OK", "application/json; charset=utf-8",
                      json.dumps(tulos, ensure_ascii=False), CACHE_CONTROL)
    return vastaa("200 OK", "text/html; charset=utf-8", sivu(tilanne, tulokset, kysely), CACHE_CONTROL)


if __name__ == "__main__":
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server

    class Palvelin(ThreadingMixIn, WSGIServer):
        """Säikeistetty: selaimen avoin yhteys tai pitkä laskenta ei jumita muita pyyntöjä."""
        daemon_threads = True

    print("http://localhost:8000")
    make_server("", 8000, app, server_class=Palvelin).serve_forever()
