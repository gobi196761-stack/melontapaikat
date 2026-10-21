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
import hmac
import html
import json
import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode

import ennustearkisto
import firestore
import melonta
import osm_sivut as osm
import kaavio_svg
import kielet
import smhi_data
import syke_data
import syke_kaavio
from paikat import PAIKAT, aseman_nimi, nakyy
from paikkakunnat import PAIKKAKUNNAT

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
.suosikki { background:none; border:0; padding:0 4px; cursor:pointer; font-size:1.1rem;
            color:var(--heikko); line-height:1; vertical-align:-1px; }
.suosikki[aria-pressed="true"] { color:var(--huono); }
.otsake { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
.kieli { display:inline-flex; align-items:center; gap:6px; font-size:.85rem; color:var(--heikko);
         text-decoration:none; margin-top:4px; white-space:nowrap; }
.kieli svg { border:1px solid var(--viiva); border-radius:2px; display:block; }
.paikkakunta { display:inline-flex; align-items:center; gap:6px; font-size:.9rem; color:var(--heikko); }
.paikkakunta input { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px; font:inherit;
                     font-size:.9rem; width:11em; background:var(--tausta); color:var(--teksti); }
.reitti { white-space:nowrap; }
nav button { padding:4px 10px; border:1px solid var(--viiva); border-radius:999px; background:none;
             color:var(--linkki); font:inherit; font-size:.9rem; cursor:pointer; }
"""

# Suosikit ja etäisyys omasta sijainnista: vain selaimessa (sivu on sama kaikille ja
# CDN:n välimuistissa). Suosikit ja sijaintiluvan muistaminen localStoragessa.
SKRIPTI = """
(() => {
  const AVAIN = "melonta-suosikit", SIJ = "melonta-sijainti";
  const T = document.documentElement.lang === "en" ? {
    lisaa: "Add to favourites", poista: "Remove from favourites", km: " km by road",
    tila: "Driving distances from your location (OpenStreetMap routing).", lasketaan: "Calculating driving distances…",
    eiAjo: "Driving distances are not available right now. Distances are from Oulu city centre.",
    eiTukea: "Your browser does not support location.", haetaan: "Getting location…",
    eiSaatu: m => "Location not available (" + m + "). Distances are from Oulu city centre.",
    paikkakunnalta: n => "Driving distances from " + n + " (OpenStreetMap routing).",
    tuntematon: n => "Unknown municipality: " + n + ". Pick one from the list.",
  } : {
    lisaa: "Lisää suosikkeihin", poista: "Poista suosikeista", km: " km ajomatka",
    tila: "Ajomatkat omasta sijainnistasi (OpenStreetMap-reititys).", lasketaan: "Lasketaan ajomatkoja…",
    eiAjo: "Ajomatkoja ei saatu juuri nyt. Etäisyydet ovat Oulun keskustasta.",
    eiTukea: "Selain ei tue sijaintia.", haetaan: "Haetaan sijaintia…",
    eiSaatu: m => "Sijaintia ei saatu (" + m + "). Etäisyydet ovat Oulun keskustasta.",
    paikkakunnalta: n => "Ajomatkat paikkakunnalta " + n + " (OpenStreetMap-reititys).",
    tuntematon: n => "Tuntematon paikkakunta: " + n + ". Valitse listasta.",
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
      r.hidden = vainSuosikit && !on;
      if (!r.hidden) r.querySelector(".sija").textContent = ++n + ".";
    }
    const ohje = document.getElementById("ei-suosikkeja");
    if (ohje) ohje.hidden = !(vainSuosikit && n === 0);
  }
  for (const r of rivit) {
    r.querySelector(".suosikki").addEventListener("click", () => {
      const nimi = r.dataset.paikka;
      suosikit.has(nimi) ? suosikit.delete(nimi) : suosikit.add(nimi);
      kirjoita(AVAIN, [...suosikit]);
      paivita();
    });
  }
  paivita();

  // Ajomatkat (tavallinen ajoreitti) lähtöpisteestä kaikkiin paikkoihin: /api/ajomatkat
  // laskee ne yhdellä reitityskyselyllä. Lähtöpiste pyöristetään ~1 km:n tarkkuuteen.
  const tila = document.getElementById("sijainti-tila");
  let kysely = 0;
  function nayta(oma, teksti, lahto) {
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
    if (!oma) return;
    const oma2 = oma.map(v => v.toFixed(2)), tama = ++kysely;
    fetch("/api/ajomatkat?lahto=" + oma2.join(","))
      .then(v => v.ok ? v.json() : Promise.reject(v.status))
      .then(d => {
        if (tama !== kysely) return;   // uudempi valinta ehti ensin
        for (const r of rivit) {
          const km = r.querySelector(".km"), k = d.km[r.dataset.paikka];
          if (km && k != null) km.textContent = "~" + Math.round(k) + T.km;
        }
        tila.textContent = teksti;
      })
      .catch(() => { if (tama === kysely) tila.textContent = T.eiAjo; });
  }
  function hae() {
    if (!navigator.geolocation) { tila.textContent = T.eiTukea; tila.hidden = false; return; }
    tila.textContent = T.haetaan; tila.hidden = false;
    navigator.geolocation.getCurrentPosition(
      p => { kirjoita(SIJ, true); kentta && (kentta.value = "");
             nayta([p.coords.latitude, p.coords.longitude], T.tila, null); },
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
    nayta([lev, pit], T.paikkakunnalta(nimi), lev + "," + pit);
  }
  if (kentta) kentta.addEventListener("change", () => valitse(kentta.value, true));
  const nappi = document.getElementById("sijainti");
  if (nappi) nappi.addEventListener("click", hae);
  const muistettu = lue(SIJ, false);
  if (muistettu && muistettu.paikkakunta && kentta) valitse(muistettu.paikkakunta, false);
  else if (muistettu === true) hae();   // lupa annettu aiemmin: päivitä suoraan
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
SELITE = {
    "fi": "★ parhaimmillaan ✓ toimii ✗ ei toimi. Pisteet (0–100) kertovat, miten veden määrä osuu "
          "paikan kuvauksen optimiin; tasapisteissä lähempi paikka ensin. Tarkista aina olosuhteet "
          "paikan päällä.",
    "en": "★ at its best ✓ works ✗ does not work. The score (0–100) tells how well the water level "
          "matches the optimum in the spot description; on equal scores the closer spot comes first. "
          "Spot and feature names and descriptions are in Finnish. Always check conditions on site.",
}
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


def _pisteluokka(p: float) -> str:
    return "p-hyva" if p >= 60 else "p-keski" if p >= 30 else "p-huono"


def _paikan_rivi(sija: int, t, kieli: str = "fi") -> str:
    p = t.paikka
    k_ = lambda teksti: kielet.kaanna(teksti, kieli)   # noqa: E731
    nakyvat = []
    mittarit = []
    for avain in p.mittarit:
        l = t.lukemat.get(avain)
        if l and l.url not in nakyvat:
            nakyvat.append(l.url)
            href = kaavion_osoite(p, avain, l, kieli) or l.url
            mittarit.append(f'<li><a href="{e(href)}">{e(k_(melonta.kuvaa_lukema(l)))}</a></li>')
    kohteet = sorted(t.kohteet, key=lambda k: k.pisteet, reverse=True)
    toimivat = [k for k in kohteet if k.tila != "ei toimi"]
    lyhyet = toimivat[:3] if toimivat else kohteet[:1]

    def kohde(k) -> str:
        return f"<li>{melonta._tila_merkki(k.tila)} <b>{e(k.kohde.nimi)}</b>: {e(k_(k.selitys))}</li>"

    muut = [k for k in kohteet if k not in lyhyet]
    lisat = ""
    if muut:
        lisat = (f"<details><summary>{k_('Muut kohteet')} ({len(muut)})</summary><ul>"
                 + "".join(kohde(k) for k in muut) + "</ul></details>")
    huomiot = "".join(f'<li class="huom">! {e(k_(h))}</li>' for h in t.huomiot)
    ennuste = " / ".join(f"{t.ennuste[n]:.0f}" for n in sorted(t.ennuste)) or "–"
    km = f'<span class="km">~{p.km_oulusta} {k_("km Oulusta")}</span>' if p.km_oulusta is not None else ""
    sijainti = f' data-sijainti="{p.sijainti[0]},{p.sijainti[1]}"' if p.sijainti else ""
    # Google Mapsin ajoreitti; lähtöpiste on oma sijainti (Google) tai valittu paikkakunta (selain lisää)
    reitti = ""
    if p.sijainti:
        osoite = "https://www.google.com/maps/dir/?" + urlencode(
            {"api": 1, "destination": f"{p.sijainti[0]},{p.sijainti[1]}", "travelmode": "driving"})
        reitti = (f' · <a class="reitti" href="{e(osoite)}" target="_blank" rel="noopener">'
                  f'{k_("🚗 Reitti")}</a>')
    return f"""<tr data-paikka="{e(p.nimi)}"{sijainti}>
<td class="sija">{sija}.</td>
<td><div class="nimi"><a href="{e(p.url)}">{e(p.nimi)}</a>
<button type="button" class="suosikki" aria-pressed="false" title="{k_('Lisää suosikkeihin')}">♡</button></div>
<div class="pieni">{e(k_(p.tyyppi))}{' · ' + km if km else ''}{reitti}</div>
<ul class="pieni">{''.join(mittarit)}</ul>
<ul>{''.join(kohde(k) for k in lyhyet)}{huomiot}</ul>{lisat}</td>
<td class="pisteet {_pisteluokka(t.pisteet)}">{t.pisteet:.0f}</td>
<td class="ennuste piilo">{ennuste}</td>
</tr>"""


def _osoite(**parametrit) -> str:
    """Sivun osoite annetuilla kyselyparametreilla (tyhjät jätetään pois, oletuskieli ei näy)."""
    parametrit = {k: v for k, v in parametrit.items() if v and not (k == "kieli" and v == "fi")}
    return "/" + ("?" + urlencode(parametrit) if parametrit else "")


def sivu(tilanne: Tilanne, tulokset: list, kysely: dict[str, list[str]]) -> str:
    valittu = kysely.get("tyyppi", [""])[0]
    kieli = kielet.kieli(kysely)
    k_ = lambda teksti: kielet.kaanna(teksti, kieli)   # noqa: E731
    suodattimet = "".join(
        f'<a href="{e(_osoite(tyyppi=arvo, kieli=kieli))}"{" class=valittu" if valittu == arvo else ""}>{k_(nimi)}</a>'
        for arvo, nimi in [("", "Kaikki"), ("peli", "Pelipaikat"), ("retki", "Retket"), ("ruotsi", "Ruotsi"),
                           ("suosikit", "♥ Suosikit")])
    toinen = "fi" if kieli == "en" else "en"
    vaihto = (f'<a class="kieli" href="{e(_osoite(tyyppi=valittu, kieli=toinen))}" hreflang="{toinen}" '
              f'lang="{toinen}">{LIPUT[toinen]}{"Suomeksi" if toinen == "fi" else "In English"}</a>')
    # Veden lämpötila on Suomen asemalta (Kipinä), joten Ruotsi-välilehdellä sitä ei näytetä
    lampotilat = [l for t in tilanne.tulokset for l in t.sivun_kaaviot
                  if l.suure == "lampotila" and l.arvo is not None and valittu not in ("ruotsi", "suosikit")]
    lampo = ""
    if lampotilat:
        l = lampotilat[0]
        lampo = (f'<div class="lampo">{k_("Veden lämpötila")} ({e(aseman_nimi(osm.kaavio_avain(l.url)))}): '
                 f"<b>{l.arvo:.1f} °C</b>"
                 + (k_(" – kylmää vettä, pukeudu uintia varten!") if l.arvo < 10 else "") + "</div>")
    arvioidut = [t for t in tulokset if t.pisteet is not None]
    rivit = "".join(_paikan_rivi(i, t, kieli) for i, t in enumerate(arvioidut, 1))
    ilman = [t for t in tulokset if t.pisteet is None]
    ilman_html = ""
    if ilman:
        ilman_html = (f"<h2>{k_('Ei vesikaaviota – tarkista itse')}</h2><ul>" + "".join(
            f'<li><a href="{e(t.paikka.url)}">{e(t.paikka.nimi)}</a>: {e(t.paikka.kuvaus)}</li>'
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
<style>{TYYLI}</style>
</head>
<body><main>
<div class="otsake"><h1>{k_("Melontapaikkojen tilanne")} {tilanne.paivitetty:%d.%m.%Y}</h1>{vaihto}</div>
<div class="meta">{k_("osm.fi:n paikkakuvaukset + SYKE:n ja SMHI:n vesistöennusteet")} ·
{k_("päivitetty klo")} {tilanne.paivitetty:%H.%M}</div>
<nav>{suodattimet}<button type="button" id="sijainti">{k_("📍 Etäisyydet omasta sijainnista")}</button>
<label class="paikkakunta">{k_("tai paikkakunta")} <input id="paikkakunta" list="kunnat" autocomplete="off"
placeholder="{k_("esim. Rovaniemi")}"></label></nav>
<datalist id="kunnat">{KUNTALISTA}</datalist>
<script type="application/json" id="paikkakunnat">{KUNNAT_JSON}</script>
<p id="sijainti-tila" class="pieni" hidden></p>
{lampo}
<p id="ei-suosikkeja" hidden>{EI_SUOSIKKEJA[kieli]}</p>
<table data-valilehti="{e(valittu)}">
<thead><tr><th></th><th>{k_("Paikka")}</th><th>{k_("Pisteet")}</th><th class="piilo">{k_("+1 / +2 / +3 pv")}</th></tr></thead>
<tbody>{rivit}</tbody>
</table>
{ilman_html}
{varoitukset}
<p class="pieni">{SELITE[kieli]}</p>
</main>
<script>{SKRIPTI}</script>
</body>
</html>"""


OSRM_TAULUKKO = "https://router.project-osrm.org/table/v1/driving/{pisteet}?sources=0&annotations=distance"
AJOMATKA_CACHE = "public, max-age=86400, s-maxage=604800"
_ajomatkat: dict[tuple[float, float], dict[str, float]] = {}


def ajomatkat(lahto: str, hakija: osm.Hakija | None = None) -> tuple[str, dict]:
    """Ajomatkat (km) lähtöpisteestä 'lev,pit' kaikkiin paikkoihin OSRM:n taulukkokyselyllä
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
            matkat = json.loads(data.decode("utf-8"))["distances"][0][1:] if data else None
        except (ValueError, KeyError, IndexError, TypeError):
            matkat = None
        if not matkat:
            return "503 Service Unavailable", {"virhe": f"reitityspalvelu ei vastannut: {virhe or 'virheellinen vastaus'}"}
        if len(_ajomatkat) > 2000:
            _ajomatkat.clear()
        _ajomatkat[(lev, pit)] = {p.nimi: round(m / 1000, 1) for p, m in zip(paikat, matkat) if m is not None}
    return "200 OK", {"lahto": [lev, pit], "km": _ajomatkat[(lev, pit)]}


def arkistoi(environ) -> tuple[str, dict]:
    """Vercel Cron: kokoaa päivän ennustearkiston ja tallentaa sen Firestoreen."""
    salaisuus = os.environ.get("CRON_SECRET", "")
    if not salaisuus:
        return "503 Service Unavailable", {"virhe": "CRON_SECRET puuttuu"}
    if not hmac.compare_digest(environ.get("HTTP_AUTHORIZATION", "").encode("utf-8", "surrogateescape"),
                               f"Bearer {salaisuus}".encode("utf-8")):
        return "401 Unauthorized", {"virhe": "väärä tai puuttuva tunniste"}
    try:
        kanta = firestore.Firestore.ymparistosta()
    except (ValueError, KeyError, OSError) as e:
        return "503 Service Unavailable", {"virhe": f"FIREBASE_SERVICE_ACCOUNT ei kelpaa: {e!r}"}
    if not kanta:
        return "503 Service Unavailable", {"virhe": "FIREBASE_SERVICE_ACCOUNT puuttuu"}
    nyt = suomen_aika()
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
    if not kuvasta:
        ajo = _hae_json(hakija, osm.kaavio_url(syke_data.ajo_avain(mittari.kaavio)))
        alueet = _syke_alueet(paikka, avain, mittari, hakija)
        kuva = kaavio_svg.syke_svg(ajo, mittari.kaavio, otsikko, alueet, kieli) if ajo else None
        if kuva:
            return kuva
    # ajo.jsonissa ei ole kaavion suuretta (tai luvut eivät täsmää kuvaan): sarjat SYKE:n kuvasta
    data, _ = osm.hae_turvallisesti(hakija, osm.kaavio_url(mittari.kaavio))
    if not data:
        return None
    try:
        sarjat = syke_kaavio.KaavioLukija().lue_sarjat(data, historia=kaavio_svg.HISTORIA_PAIVIA)
    except syke_kaavio.KaavioVirhe:
        return None
    _, yksikko = syke_kaavio.suure_urlista(mittari.kaavio)
    return kaavio_svg.kuva_svg(sarjat, _kuvan_paiva(sarjat.tanaan_paiva, nyt), otsikko, yksikko,
                               _syke_alueet(paikka, avain, mittari, hakija), kieli)


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
    ajot = {a: d for a in avaimet if (d := _hae_json(hakija, osm.kaavio_url(a)))}
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
    return kaavio_svg.arvio_svg(lukema, ajot, asema, otsikko,
                                _alueet(paikka, avain, lukema.tunnusluvut), kieli, arkistoidut_arviot(asema))


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

def app(environ, start_response):
    polku = environ.get("PATH_INFO", "/").rstrip("/") or "/"
    metodi = environ.get("REQUEST_METHOD", "GET")
    kysely = {k: v for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()
              if k in ("tyyppi", "max_km", "kieli")}

    def vastaa(status: str, tyyppi: str, runko: str, valimuisti: str = "no-store"):
        data = runko.encode("utf-8")
        start_response(status, [("Content-Type", tyyppi), ("Content-Length", str(len(data))),
                                ("Cache-Control", valimuisti)])
        return [b"" if metodi == "HEAD" else data]

    if metodi not in ("GET", "HEAD"):
        return vastaa("405 Method Not Allowed", "text/plain; charset=utf-8", "Vain GET.\n")
    if polku == "/api/ajomatkat":
        status, tulos = ajomatkat(parse_qs(environ.get("QUERY_STRING", "")).get("lahto", [""])[0])
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False),
                      AJOMATKA_CACHE if status.startswith("200") else "no-store")
    if polku == "/api/arkistoi":
        status, tulos = arkistoi(environ)
        return vastaa(status, "application/json; charset=utf-8", json.dumps(tulos, ensure_ascii=False))
    if polku.startswith("/kaavio/"):
        kaavio = polku.removeprefix("/kaavio/")
        paikan_nimi = parse_qs(environ.get("QUERY_STRING", "")).get("paikka", [None])[0]
        kieli = kielet.kieli(kysely)
        kuvasta = parse_qs(environ.get("QUERY_STRING", "")).get("lahde", [""])[0] == "kuva"
        kuva = (smhi_kaavio_svg(kaavio, paikan_nimi=paikan_nimi, kieli=kieli) if kaavio.startswith("smhi/")
                else syke_kaavio_svg(kaavio.removeprefix("syke/"), paikan_nimi=paikan_nimi, kieli=kieli,
                                     kuvasta=kuvasta)
                if kaavio.startswith("syke/") else None)
        if kuva is None:
            return vastaa("404 Not Found", "text/plain; charset=utf-8", "Kaaviota ei löydy.\n")
        return vastaa("200 OK", "image/svg+xml; charset=utf-8", kuva, CACHE_CONTROL)
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
