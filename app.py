"""Melontatilanne verkkosivuna ja JSON-rajapintana (WSGI, esim. Vercel).

Reitit:
    /       päivän järjestys taulukkona
    /api    sama JSON-muodossa (kuten `melonta.py --json`)
Suodattimet kummallekin: ?tyyppi=peli|retki ja ?max_km=N

Paikallisesti:
    uv run app.py            # http://localhost:8000

Yksi laskenta kestää 20–30 s (sivut + kaaviot), joten tulos pidetään
muistissa VALIMUISTI_S sekuntia ja vastaukset merkitään CDN:n
välimuistiin (Cache-Control: s-maxage). Näin vain harva pyyntö odottaa.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode

import melonta
import osm_sivut as osm
from paikat import PAIKAT, aseman_nimi

VALIMUISTI_S = 15 * 60
CACHE_CONTROL = "public, max-age=300, s-maxage=1800, stale-while-revalidate=3600, stale-if-error=86400"


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
        sivun_kaaviot, lukemat, varoitukset = melonta.kerää_tilanne(hakija, PAIKAT)
        tulokset = melonta.arvioi_kaikki(PAIKAT, sivun_kaaviot, lukemat, nyt.date())
        tilanne = Tilanne(nyt, tulokset, varoitukset, len(lukemat))
        if lukemat:   # epäonnistunutta hakua ei jätetä muistiin
            _tilanne = (time.monotonic(), tilanne)
        return tilanne


def suodata(tulokset: list, kysely: dict[str, list[str]]) -> list:
    tyyppi = kysely.get("tyyppi", [None])[0]
    try:
        max_km = int(kysely["max_km"][0]) if "max_km" in kysely else None
    except ValueError:
        max_km = None
    return [t for t in tulokset
            if (tyyppi not in ("peli", "retki") or t.paikka.tyyppi == tyyppi)
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
nav a { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px;
        color:var(--teksti); text-decoration:none; font-size:.9rem; }
nav a.valittu { background:var(--teksti); color:var(--tausta); border-color:var(--teksti); }
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
"""


def _pisteluokka(p: float) -> str:
    return "p-hyva" if p >= 60 else "p-keski" if p >= 30 else "p-huono"


def _paikan_rivi(sija: int, t) -> str:
    p = t.paikka
    nakyvat = []
    mittarit = []
    for avain in p.mittarit:
        l = t.lukemat.get(avain)
        if l and l.url not in nakyvat:
            nakyvat.append(l.url)
            mittarit.append(f'<li><a href="{e(l.url)}">{e(melonta.kuvaa_lukema(l))}</a></li>')
    kohteet = sorted(t.kohteet, key=lambda k: k.pisteet, reverse=True)
    toimivat = [k for k in kohteet if k.tila != "ei toimi"]
    lyhyet = toimivat[:3] if toimivat else kohteet[:1]

    def kohde(k) -> str:
        return f"<li>{melonta._tila_merkki(k.tila)} <b>{e(k.kohde.nimi)}</b>: {e(k.selitys)}</li>"

    muut = [k for k in kohteet if k not in lyhyet]
    lisat = ""
    if muut:
        lisat = (f"<details><summary>Muut kohteet ({len(muut)})</summary><ul>"
                 + "".join(kohde(k) for k in muut) + "</ul></details>")
    huomiot = "".join(f'<li class="huom">! {e(h)}</li>' for h in t.huomiot)
    ennuste = " / ".join(f"{t.ennuste[n]:.0f}" for n in sorted(t.ennuste)) or "–"
    km = f"~{p.km_oulusta} km" if p.km_oulusta is not None else ""
    return f"""<tr>
<td class="sija">{sija}.</td>
<td><div class="nimi"><a href="{e(p.url)}">{e(p.nimi)}</a></div>
<div class="pieni">{e(p.tyyppi)}{' · ' + km if km else ''}</div>
<ul class="pieni">{''.join(mittarit)}</ul>
<ul>{''.join(kohde(k) for k in lyhyet)}{huomiot}</ul>{lisat}</td>
<td class="pisteet {_pisteluokka(t.pisteet)}">{t.pisteet:.0f}</td>
<td class="ennuste piilo">{ennuste}</td>
</tr>"""


def sivu(tilanne: Tilanne, tulokset: list, kysely: dict[str, list[str]]) -> str:
    valittu = kysely.get("tyyppi", [""])[0]
    suodattimet = "".join(
        f'<a href="{href}"{" class=valittu" if valittu == arvo else ""}>{nimi}</a>'
        for arvo, href, nimi in [("", "/", "Kaikki"), ("peli", "/?tyyppi=peli", "Pelipaikat"),
                                 ("retki", "/?tyyppi=retki", "Retket")])
    lampotilat = [l for t in tilanne.tulokset for l in t.sivun_kaaviot
                  if l.suure == "lampotila" and l.arvo is not None]
    lampo = ""
    if lampotilat:
        l = lampotilat[0]
        lampo = (f'<div class="lampo">Veden lämpötila ({e(aseman_nimi(osm.kaavio_avain(l.url)))}): '
                 f"<b>{l.arvo:.1f} °C</b>"
                 + (" – kylmää vettä, pukeudu uintia varten!" if l.arvo < 10 else "") + "</div>")
    arvioidut = [t for t in tulokset if t.pisteet is not None]
    rivit = "".join(_paikan_rivi(i, t) for i, t in enumerate(arvioidut, 1))
    ilman = [t for t in tulokset if t.pisteet is None]
    ilman_html = ""
    if ilman:
        ilman_html = ("<h2>Ei vesikaaviota – tarkista itse</h2><ul>" + "".join(
            f'<li><a href="{e(t.paikka.url)}">{e(t.paikka.nimi)}</a>: {e(t.paikka.kuvaus)}</li>'
            for t in ilman) + "</ul>")
    varoitukset = ""
    if tilanne.varoitukset:
        varoitukset = ('<h2>Huomautukset</h2><ul class="pieni">'
                       + "".join(f"<li>{e(v)}</li>" for v in tilanne.varoitukset) + "</ul>")
    api = e("/api" + ("?" + urlencode({k: v[0] for k, v in kysely.items()}) if kysely else ""))
    return f"""<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Melontatilanne</title>
<style>{TYYLI}</style>
</head>
<body><main>
<h1>Melontapaikkojen tilanne {tilanne.paivitetty:%d.%m.%Y}</h1>
<div class="meta">osm.fi:n paikkakuvaukset + SYKE:n vesistöennusteet ·
päivitetty klo {tilanne.paivitetty:%H.%M} · <a href="{api}">JSON</a></div>
<nav>{suodattimet}</nav>
{lampo}
<table>
<thead><tr><th></th><th>Paikka</th><th>Pisteet</th><th class="piilo">+1 / +2 / +3 pv</th></tr></thead>
<tbody>{rivit}</tbody>
</table>
{ilman_html}
{varoitukset}
<p class="pieni">★ parhaimmillaan ✓ toimii ✗ ei toimi. Pisteet (0–100) kertovat, miten veden määrä
osuu paikan kuvauksen optimiin; tasapisteissä lähempi paikka ensin. Tarkista aina olosuhteet
paikan päällä.</p>
</main></body>
</html>"""


# ---------------------------------------------------------------------------
# WSGI
# ---------------------------------------------------------------------------

def app(environ, start_response):
    polku = environ.get("PATH_INFO", "/").rstrip("/") or "/"
    metodi = environ.get("REQUEST_METHOD", "GET")
    kysely = {k: v for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()
              if k in ("tyyppi", "max_km")}

    def vastaa(status: str, tyyppi: str, runko: str, valimuisti: str = "no-store"):
        data = runko.encode("utf-8")
        start_response(status, [("Content-Type", tyyppi), ("Content-Length", str(len(data))),
                                ("Cache-Control", valimuisti)])
        return [b"" if metodi == "HEAD" else data]

    if metodi not in ("GET", "HEAD"):
        return vastaa("405 Method Not Allowed", "text/plain; charset=utf-8", "Vain GET.\n")
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
    from wsgiref.simple_server import make_server
    print("http://localhost:8000")
    make_server("", 8000, app).serve_forever()
