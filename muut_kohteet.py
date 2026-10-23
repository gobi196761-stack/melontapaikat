"""Muut kohteet: Timo Piiraisen melontapäiväkirjan jokireitit (/muut ja /muut/<tunniste>).

Aineisto (muut_kohteet.json) on koottu päiväkirjasta (Word-dokumentti "Melottuja
jokireittejä", 13.6.2026) työkalulla tyokalut/muut_kohteet_aineisto.py. Jokaisella
reitillä on päiväkirjan tiedot (lähtö, kohde, korkeusero, matka, melontapäivä ja
kuvaus) sekä täydennykset: lähtö- ja loppupaikan sijainti kartalla (OpenStreetMapin
paikannimihaku), ajomatka Oulusta lähtöpaikalle (OSRM), SYKE:n virtaama
melontapäivänä samalla joella olevalta asemalta ja muista lähteistä löytyneet tiedot.
Päiväkirjaan viitataan lähteenä ilman linkkiä.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urlencode

e = html.escape
AINEISTO = Path(__file__).with_name("muut_kohteet.json")
LAHDE = "Timo Piirainen: melontapäiväkirja, Melottuja jokireittejä (13.6.2026)"


def lataa() -> list[dict]:
    return json.loads(AINEISTO.read_text(encoding="utf-8")) if AINEISTO.exists() else []


KOHTEET: list[dict] = lataa()
HAKEMISTO: dict[str, dict] = {k["tunniste"]: k for k in KOHTEET}


def _kartta(piste) -> str:
    lev, pit = piste
    return f"https://www.openstreetmap.org/?mlat={lev}&mlon={pit}#map=13/{lev}/{pit}"


def _reitti(piste) -> str:
    return "https://www.google.com/maps/dir/?" + urlencode(
        {"api": 1, "destination": f"{piste[0]},{piste[1]}", "travelmode": "driving"})


def _kesto(minuutit: float) -> str:
    t, m = divmod(round(minuutit), 60)
    return f"{t} h {m:02d} min" if t else f"{m} min"


def _kappaleet(rivit: list[str]) -> str:
    return "".join(f"<p>{e(r)}</p>" for r in rivit)


def _paikka(otsikko: str, nimi: str | None, piste, kunta: str | None, ajo: dict | None) -> str:
    if not nimi:
        return ""
    osat = [f"<b>{e(otsikko)}:</b> {e(nimi)}"]
    if kunta:
        osat.append(f"({e(kunta)})")
    linkit = []
    if piste:
        linkit.append(f'<a href="{e(_kartta(piste))}" target="_blank" rel="noopener">🗺 kartta</a>')
        linkit.append(f'<a href="{e(_reitti(piste))}" target="_blank" rel="noopener">🚗 ajo-ohje</a>')
    teksti = " ".join(osat)
    if ajo:
        teksti += f" – Oulusta n. {ajo['km']:.0f} km, ajoaika n. {_kesto(ajo['min'])}"
    if linkit:
        teksti += " · " + " · ".join(linkit)
    return f"<li>{teksti}</li>"


def sivu(k: dict, tyyli: str) -> str:
    tiedot = [("Matka", k.get("matka")), ("Korkeusero", k.get("korkeusero")), ("Melottu", k.get("aika"))]
    tiedot_html = "".join(f"<li><b>{e(n)}:</b> {e(v)}</li>" for n, v in tiedot if v)
    paikat = (_paikka("Lähtö", k.get("lahto"), k.get("lahto_sijainti"), k.get("lahto_kunta"),
                      k.get("ajo") if k.get("lahto_sijainti") else None)
              + _paikka("Loppu", k.get("kohde"), k.get("kohde_sijainti"), k.get("kohde_kunta"), None))
    if k.get("alue") and not (k.get("lahto_sijainti") and k.get("kohde_sijainti")):
        paikat += _paikka("Reitin alue (likimääräinen)", "joen tai järven sijainti, kun lähtö- tai loppupaikkaa "
                          "ei löytynyt kartalta nimellä", k["alue"], None,
                          None if k.get("lahto_sijainti") else k.get("ajo"))
    paasy = _kappaleet(k.get("paasy", []))
    joet = f'<p class="meta">{e(" – ".join(k["joet"]))}</p>' if k.get("joet") else ""
    vesi = (f"<h2>Vesitilanne melontapäivänä</h2><p>{e(k['vesi'])}</p>" if k.get("vesi") else "")
    lisat = ""
    if k.get("lisatiedot"):
        lisat = "<h2>Muista lähteistä</h2>" + "".join(
            f'<p>{e(l["teksti"])} (<a href="{e(l["url"])}" target="_blank" rel="noopener">{e(l["lahde"])}</a>)</p>'
            for l in k["lisatiedot"])
    if k.get("paikkasivu"):
        lisat += (f'<p>Sovelluksessa on tältä joelta myös pisteytetty paikka: '
                  f'<a href="{e(k["paikkasivu"][0])}">{e(k["paikkasivu"][1])}</a>.</p>')
    lahteet = [f"<li>{e(LAHDE)}</li>"] + [
        f'<li><a href="{e(url)}" target="_blank" rel="noopener">{e(nimi)}</a></li>'
        for nimi, url in dict.fromkeys((l["lahde"], l["url"]) for l in k.get("lisatiedot", []))]
    if k.get("lahto_sijainti") or k.get("kohde_sijainti"):
        lahteet.append('<li>Sijainnit: <a href="https://www.openstreetmap.org/copyright" target="_blank" '
                       'rel="noopener">© OpenStreetMapin tekijät</a>; ajomatkat OSRM</li>')
    if k.get("vesi"):
        lahteet.append('<li>Virtaama: SYKE:n hydrologiarajapinta (vuorokausiarvo)</li>')
    ryhma = " · ".join(x for x in (k.get("kokoelma"), (k.get("osio") or "").capitalize() or None, k.get("ryhma")) if x)
    return f"""<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(k["nimi"])} – Muut kohteet</title>
<link rel="icon" type="image/png" href="/kuvake-192.png">
<style>{tyyli}</style>
</head>
<body><main class="kuvaus">
<a class="takaisin" href="/muut">← Muut kohteet</a>
<h1>{e(k["nimi"])}</h1>
<div class="meta">{e(ryhma)}</div>
{joet}
<ul>{tiedot_html}</ul>
<h2>Lähtö- ja loppupaikka</h2>
<ul class="lahteet">{paikat or "<li>Lähtö- ja loppupaikkaa ei ole kerrottu.</li>"}</ul>
{paasy}
<h2>Melontapäiväkirjan kuvaus</h2>
{_kappaleet(k.get("kuvaus", [])) or "<p>Päiväkirjassa ei ole sanallista kuvausta.</p>"}
{vesi}
{lisat}
<h2>Lähteet</h2>
<ul class="lahteet">{"".join(lahteet)}</ul>
</main>
</body>
</html>"""


def luettelo(tyyli: str) -> str:
    ryhmat: dict[str, list[dict]] = {}
    for k in KOHTEET:
        otsikko = k["kokoelma"] + (f" – {k['osio'].capitalize()}" if k.get("osio") else "")
        ryhmat.setdefault(otsikko, []).append(k)
    osat = []
    for otsikko, kohteet in ryhmat.items():
        rivit = "".join(
            f'<li><a href="/muut/{e(k["tunniste"])}">{e(k["nimi"])}</a>'
            f'<span class="pieni"> · {e(" – ".join(k.get("joet", [])) or "")}'
            f'{" · " + e(k["lahto_kunta"]) if k.get("lahto_kunta") else ""}'
            f'{" · " + e(k["matka"]) if k.get("matka") else ""}</span></li>'
            for k in kohteet)
        osat.append(f"<h2>{e(otsikko)}</h2><ul>{rivit}</ul>")
    return f"""<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Muut kohteet – Melontapaikat</title>
<link rel="icon" type="image/png" href="/kuvake-192.png">
<style>{tyyli}</style>
</head>
<body><main class="kuvaus">
<a class="takaisin" href="/">← Melontatilanne</a>
<h1>Muut kohteet</h1>
<p>{len(KOHTEET)} jokireittiä Timo Piiraisen melontapäiväkirjasta. Jokaisella reitillä on oma sivunsa:
lähtö- ja loppupaikka kartalla, ajo-ohje, päiväkirjan kuvaus, vesitilanne melontapäivänä ja muista
lähteistä löytyneet tiedot. Näitä reittejä ei pisteytetä vesitilanteen mukaan.</p>
{"".join(osat)}
<p class="pieni">Lähde: {e(LAHDE)}.</p>
</main>
</body>
</html>"""
