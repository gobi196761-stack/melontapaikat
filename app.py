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
import hashlib
import hmac
import html
import json
import math
import os
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, urlencode

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
import muut_kohteet
import retket
import sovellus
import smhi_data
import syke_data
import syke_kaavio
import turvallisuus
from arviointi import muotoile
from paikat import PAIKAT, aseman_nimi, kohteen_kajakit, nakyy
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


_lukko = threading.Lock()
_tilanne: tuple[float, Tilanne] | None = None


def hae_tilanne() -> Tilanne:
    """Laskee kaikkien paikkojen tilanteen tai palauttaa tuoreen tuloksen muistista."""
    global _tilanne
    with _lukko:   # samanaikaiset pyynnöt odottavat yhtä laskentaa
        if _tilanne and time.monotonic() - _tilanne[0] < VALIMUISTI_S \
                and _tilanne[1].paivitetty.date() == suomen_aika().date():
            return _tilanne[1]
        nyt = suomen_aika()
        hakija = osm.Hakija(aikaraja=20)
        sivun_kaaviot, lukemat, varoitukset = melonta.kerää_tilanne(hakija, PAIKAT, lisakaaviot=False)
        tulokset = melonta.arvioi_kaikki(PAIKAT, sivun_kaaviot, lukemat, nyt.date())
        status, oulusta = ajomatkat(OULU, hakija)
        if not status.startswith("200"):
            oulusta = {}
        tilanne = Tilanne(nyt, tulokset, varoitukset, len(lukemat), saaennusteet(hakija),
                          oulusta.get("min", {}), oulusta.get("km", {}), surffitilanne(hakija),
                          turvallisuus.hae(hakija))
        if lukemat:   # epäonnistunutta hakua ei jätetä muistiin
            _tilanne = (time.monotonic(), tilanne)
        return tilanne


OPEN_METEO = "https://api.open-meteo.com/v1/forecast?{kysely}"


OULU = "65.01,25.47"          # oletuslähtöpaikka ajoajoille (Oulun keskusta)
LISAAIKA_MIN = 30             # ajoajan päälle: pakkaus, tauot – sää katsotaan perillä tähän aikaan
LAHTO_PAIVIA = syke_data.ENNUSTE_PAIVIA   # lähtöaika enintään näin monen päivän päähän (kaavioiden ennuste)


def saaennusteet(hakija: osm.Hakija, tunteja: int = (LAHTO_PAIVIA + 1) * 24 + 12) -> dict[str, dict]:
    """Tuntiennuste (lämpötila, WMO-sääkoodi) paikkojen sijainneissa Open-Meteosta yhdellä
    kyselyllä: nimi -> {"aika": [unix s], "t": [...], "k": [...]}. Tyhjä, jos palvelu ei vastaa."""
    paikat = [p for p in PAIKAT if p.sijainti]
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
.meta, .pieni { color:var(--heikko); font-size:.88rem; }
nav { margin:14px 0 18px; display:flex; gap:8px; flex-wrap:wrap; }
nav > a, .surffi { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px;
                   color:var(--teksti); text-decoration:none; font-size:.9rem; }
.surffirivi { margin:6px 0 8px; }
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
.turva-tausta { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:50; display:flex;
               align-items:center; justify-content:center; padding:16px; }
.turva-tausta[hidden] { display:none; }
.turva { position:relative; background:var(--tausta); color:var(--teksti); border-radius:12px; max-width:520px;
         width:100%; max-height:90vh; overflow:auto; padding:16px 18px 14px; border-top:6px solid var(--huono);
         box-shadow:0 8px 30px rgba(0,0,0,.35); }
.turva h2 { margin:0 28px 8px 0; font-size:1.15rem; }
.turva h3 { margin:12px 0 4px; font-size:1rem; color:var(--huono); }
.turva p { margin:0 0 6px; line-height:1.45; }
.turva-sulje { position:absolute; top:6px; right:8px; border:0; background:none; font-size:1.6rem;
               line-height:1; color:var(--heikko); cursor:pointer; padding:4px 8px; }
.turva-aika { height:4px; background:var(--viiva); border-radius:2px; overflow:hidden; margin:10px 0; }
.turva-aika span { display:block; height:100%; width:100%; background:var(--huono); }
.turva-ok { display:block; margin-left:auto; padding:6px 18px; border-radius:6px; border:1px solid var(--teksti);
            background:var(--teksti); color:var(--tausta); font-weight:600; cursor:pointer; }
.selitykset { background:var(--pinta); border-radius:8px; padding:8px 12px; margin:12px 0; }
.selitykset ul { display:flex; flex-wrap:wrap; gap:4px 16px; list-style:none; padding:0; margin:6px 0; }
.selitykset p { margin:4px 0 0; }
.kajakki { width:26px; height:20.8px; vertical-align:-6px; margin-left:3px; color:var(--linkki); }
.ukkonen { color:var(--huono) !important; font-weight:700; }
.tyyppi { font-weight:400; font-size:.85rem; color:var(--heikko); margin-left:2px; }
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
    kieli: "en-GB", perilla: "on arrival", paivaTila: "Water levels and ratings from the forecast for", ukkonen: "thunderstorm forecast", foreca: "Foreca 15-day forecast (yr.no covers only 9 days)", lahto: "from", oma: "your location",
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
    kieli: "fi-FI", perilla: "perillä klo", paivaTila: "Vesitilanne ja arviot ennusteen mukaan:", ukkonen: "ukkosta ennustettu", foreca: "Forecan 15 vrk ennuste (yr.no ennustaa vain 9 päivää)", lahto: "lähtö", oma: "oma sijainti",
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
                 nyt: float | None = None, ajo_km: float | None = None) -> str:
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
    matka = " · ".join(x for x in (reitti, saapuminen, km) if x)
    matka = f'\n<div class="pieni matka">{matka}</div>' if matka else ""
    lampo = f'\n<div class="pieni lampotilat">{lampo}</div>' if lampo else ""
    return f"""<tr data-paikka="{e(p.nimi)}"{sijainti} data-pisteet='{pisteet_json}' data-km="{p.km_oulusta or 0}">
<td class="sija">{sija}.</td>
<td><div class="nimi"><a href="{e(paikan_osoite(p, kieli))}">{e(p.nimi)}</a>
<button type="button" class="suosikki" aria-pressed="false" title="{k_('Lisää suosikkeihin')}">♡</button>
<span class="tyyppi">{e(k_(p.tyyppi))}</span></div>{matka}{lampo}
{versiot}</td>
<td class="pisteet {_pisteluokka(t.pisteet)}">{t.pisteet:.0f}</td>
<td class="ennuste piilo">{ennuste}</td>
</tr>"""


def _lukumaara(n: int, k_) -> str:
    return f"{n} {k_('paikka') if n == 1 else k_('paikkaa')}"


def _turvaikkuna(tilanne: Tilanne, kieli: str) -> str:
    """Sovelluksen avautuessa esiin ponnahtava varoitus (kylmä vesi, maatuuli, matala merivesi).
    Sulkeutuu itsestään lukemiseen riittävän ajan jälkeen tai sulkunapista; ei uudelleen samassa
    istunnossa, ellei varoitus muutu."""
    joet = [l.veden_lampotila for t in tilanne.tulokset if t.paikka.maa == "FI"
            for l in t.lukemat.values() if l is not None and l.veden_lampotila is not None]
    viestit = turvallisuus.viestit(tilanne.turva, joet, kieli, _ajankohta)
    if not viestit:
        return ""
    en = kieli == "en"
    avain = hashlib.sha256("".join(o + t for o, t in viestit).encode()).hexdigest()[:10]
    osiot = "".join(f"<h3>{e(o)}</h3><p>{e(t)}</p>" for o, t in viestit)
    return f"""<div id="turva" class="turva-tausta" hidden data-avain="{avain}">
<div class="turva" role="alertdialog" aria-modal="true" aria-labelledby="turva-otsikko">
<button type="button" class="turva-sulje" aria-label="{"Close" if en else "Sulje"}">×</button>
<h2 id="turva-otsikko">{"Before you go out on the water" if en else "Ennen vesille lähtöä"}</h2>
{osiot}
<p class="pieni">{"Sources: Finnish Meteorological Institute (Oulu Toppila), SYKE." if en else
                  "Lähteet: Ilmatieteen laitos (Oulu Toppila), SYKE."}</p>
<div class="turva-aika"><span></span></div>
<button type="button" class="turva-ok">{"Got it" if en else "Selvä"}</button>
</div>
</div>
<script>
(() => {{
  const ikkuna = document.getElementById("turva");
  let avain = null;
  try {{ avain = sessionStorage.getItem("melonta-turva"); }} catch (e) {{}}
  if (!ikkuna || avain === ikkuna.dataset.avain) return;
  let ajastin = null;
  const sulje = () => {{
    clearTimeout(ajastin);
    ikkuna.hidden = true;
    try {{ sessionStorage.setItem("melonta-turva", ikkuna.dataset.avain); }} catch (e) {{}}
  }};
  // lukuaika: 6 s + noin 4 sanaa sekunnissa, enintään minuutti
  const sanoja = ikkuna.querySelector(".turva").textContent.split(/\\s+/).length;
  const kesto = Math.min(60000, 6000 + sanoja * 250);
  const palkki = ikkuna.querySelector(".turva-aika span");
  ikkuna.hidden = false;
  palkki.style.transition = "none";
  palkki.style.width = "100%";
  requestAnimationFrame(() => requestAnimationFrame(() => {{
    palkki.style.transition = "width " + kesto + "ms linear";
    palkki.style.width = "0";
  }}));
  ajastin = setTimeout(sulje, kesto);
  // koskettaminen tai hiiren vieminen ikkunaan pysäyttää sulkeutumisen
  ikkuna.querySelector(".turva").addEventListener("pointerdown", () => {{
    clearTimeout(ajastin);
    palkki.parentElement.hidden = true;
  }});
  ikkuna.querySelectorAll(".turva-sulje, .turva-ok").forEach(b => b.addEventListener("click", sulje));
  ikkuna.addEventListener("click", ev => {{ if (ev.target === ikkuna) sulje(); }});
  document.addEventListener("keydown", ev => {{ if (ev.key === "Escape") sulje(); }});
}})();
</script>"""


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
        return f' <span class="maara">{sum(1 for p in PAIKAT if nakyy(p, arvo or None))}</span>'
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
                                 ajo_km=tilanne.ajo_km.get(t.paikka.nimi))
                    for i, t in enumerate(arvioidut, 1))
    ilman = [t for t in tulokset if t.pisteet is None]
    ilman_html = ""
    if ilman:
        ilman_html = (f"<h2>{k_('Ei vesikaaviota – tarkista itse')}</h2>"
                      f'<p class="lukumaara" id="lukumaara-ilman">{_lukumaara(len(ilman), k_)}</p><ul>' + "".join(
            f'<li data-haku="{e(t.paikka.nimi)}"><a href="{e(paikan_osoite(t.paikka, kieli))}">{e(t.paikka.nimi)}</a>: '
            f'{e(t.paikka.kuvaus)}</li>'
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
<body><main>
<div class="otsake"><h1>{k_("Melontapaikkojen tilanne")} {tilanne.paivitetty:%d.%m.%Y}</h1>{vaihto}</div>
<div class="surffirivi">{surffilinkki(tilanne.surffi, k_, kieli)}</div>
<div class="meta">{k_("osm.fi:n paikkakuvaukset + SYKE:n ja SMHI:n vesistöennusteet")} ·
{k_("päivitetty klo")} {tilanne.paivitetty:%H.%M}</div>
{_selitykset(kieli)}
{_halytysosio(k_)}
{_turvaikkuna(tilanne, kieli)}
<nav>{suodattimet}<button type="button" id="sijainti">{k_("📍 Etäisyydet omasta sijainnista")}</button>
<label class="paikkakunta">{k_("tai paikkakunta")} <input id="paikkakunta" list="kunnat" autocomplete="off"
placeholder="{k_("esim. Rovaniemi")}"></label>
<label class="paikkakunta">{k_("lähtöaika")} <input id="lahtoaika" type="datetime-local" step="900" data-paivia="{LAHTO_PAIVIA}"></label></nav>
<label class="haku">🔍 <input id="haku" type="search" autocomplete="off" placeholder="{k_("Hae paikkaa…")}"
aria-label="{k_("Hae paikkaa…")}"></label>
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
    valinnat = json.dumps(halytykset.valittavat(PAIKAT), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<details id="halytys" class="halytys" hidden data-vapid="{e(avainpari[0])}">
<summary>{k_("🔔 Hälytys hyvistä oloista")}</summary>
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
    if (lev, pit) not in _ajomatkat:
        paikat = [p for p in PAIKAT if p.sijainti]
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
        _ajomatkat[(lev, pit)] = {
            "km": {p.nimi: round(m / 1000, 1) for p, m in zip(paikat, matkat) if m is not None},
            "min": {p.nimi: round(s / 60) for p, s in zip(paikat, ajat) if s is not None}}
    return "200 OK", {"lahto": [lev, pit], **_ajomatkat[(lev, pit)]}


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
        tilaus, virhe = halytykset.tarkista_tilaus(data, halytykset.valittavat(PAIKAT))
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
    loydetyt = [(p, a, m) for p in PAIKAT for a, m in p.mittarit.items() if ehto(m)]
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
    """Oma kaavio, jos sen voi piirtää ilman päivän lukemaa, muuten SYKE:n asemasivu."""
    mittari = paikka.mittarit[avain]
    oma = kaavion_osoite(paikka, avain, kieli=kieli)
    if oma:
        return oma
    alue, asema = kaavion_asema(mittari.kaavio)
    return f"{osm.SYKE_POHJA}{alue}/{asema}/wqfi.html"


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
    lahteet_html = "".join(f'<li><a href="{e(url)}" target="_blank" rel="noopener">{e(otsikko)}</a></li>'
                           if url else f"<li>{e(otsikko)}</li>" for otsikko, url in lahteet)
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
{"".join(osat)}
{paikat_html}
{retkilinkit}
{kohteet}
<h2>{k_("Lähteet")}</h2>
<ul class="lahteet">{lahteet_html}</ul>
<p class="pieni">{loppu}</p>
</main>
</body>
</html>"""


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
            kuva = (smhi_kaavio_svg(kaavio, paikan_nimi=paikan_nimi, kieli=kieli) if kaavio.startswith("smhi/")
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
