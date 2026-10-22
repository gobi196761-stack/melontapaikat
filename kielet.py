"""Käyttöliittymän kielet: suomi (oletus) ja englanti (?kieli=en).

Sovelluksen tekstit tuotetaan suomeksi; englanninkielinen sivu kääntää ne
esitysvaiheessa: kiinteät tekstit sanakirjasta ja arvioinnin tuottamat
lauseet (kohteen tila, mittarin kuvaus, huomiot) säännöllisillä lausekkeilla.
Paikkojen ja kohteiden nimet sekä vapaat kuvaukset jäävät suomeksi.
"""

from __future__ import annotations

import re

KIELET = ("fi", "en")

# Kiinteät tekstit: suomi -> englanti
SANAT = {
    # sivu
    "Melontatilanne": "Paddling conditions",
    "Melontapaikkojen tilanne": "Paddling spots",
    "osm.fi:n paikkakuvaukset + SYKE:n ja SMHI:n vesistöennusteet": "spot descriptions from osm.fi + SYKE and SMHI hydrological forecasts",
    "päivitetty klo": "updated",
    "Kaikki": "All",
    "Pelipaikat": "Play spots",
    "Retket": "River runs",
    "Ruotsi": "Sweden",
    "♥ Suosikit": "♥ Favourites",
    "📍 Etäisyydet omasta sijainnista": "📍 Distances from my location",
    "tai paikkakunta": "or municipality",
    "esim. Rovaniemi": "e.g. Rovaniemi",
    "🚗 Reitti": "🚗 Route",
    "ilma": "air",
    "Merkinnät ja kuvakkeet": "Symbols and icons",
    "freestyle-kajakki": "freestyle kayak",
    "slice-kajakki (half / full slice)": "slice kayak (half / full slice)",
    "river runner -kajakki": "river runner kayak",
    "perillä klo": "on arrival",
    "ukkosta ennustettu": "thunderstorm forecast",
    "vesi": "water",
    "Veden lämpötila": "Water temperature",
    " – kylmää vettä, pukeudu uintia varten!": " – cold water, dress for a swim!",
    "Paikka": "Spot",
    "Pisteet": "Score",
    "+1 … +14 pv": "+1 … +14 d",
    "peli": "play spot",
    "retki": "river run",
    "km Oulusta": "km from Oulu",
    "Oulusta": "from Oulu",
    "lähtö": "from",
    "lähtöaika": "departure",
    "Merelle Surffaamaan": "Surfing at sea",
    "ennusteessa": "in forecast",
    "nyt": "now",
    "meri": "sea",
    "Eivät toimi nyt": "Not working now",
    "Ei vesikaaviota – tarkista itse": "No gauge chart – check yourself",
    "Huomautukset": "Notes",
    "Lisää suosikkeihin": "Add to favourites",
    "Suomeksi": "Suomeksi",
    "In English": "In English",
    "🔔 Hälytys hyvistä oloista": "🔔 Alert for good conditions",
    "Ilmoitus puhelimeen, kun valitsemasi paikan tai kohteen ehto täyttyy tänään tai ennusteessa. Tarkistus joka aamu; samasta ehdosta uudelleen vasta, kun se on välillä lakannut täyttymästä.":
        "A notification to your phone when the condition you chose for a spot or feature is met today or in the forecast. Checked every morning; the same condition again only after it has stopped being met in between.",
    "Kohde": "Feature",
    "Ehto": "Condition",
    "+ Lisää": "+ Add",
    "Ennustetta eteenpäin": "Forecast ahead",
    "pv": "d",
    "Pisteraja": "Score limit",
    "erinomainen": "excellent",
    "hyvä": "good",
    "kohtalainen": "fair",
    "Tilaa hälytys": "Subscribe to alert",
    "Peru tilaus": "Cancel alert",
    # kaaviot
    "mittari": "gauge",
    "malli (ennuste katkoviivana)": "model (forecast dashed)",
    "ennuste": "forecast",
    "ennuste (jatkuu viimeisestä havainnosta)": "forecast (continues from the latest observation)",
    "havainto": "observed",
    "laskettu arvio": "computed estimate",
    "arvio silloin (arkisto)": "estimate at the time (archive)",
    "laskettu jälkikäteen": "computed afterwards",
    "keskivirhe": "mean error",
    "arvio tänään": "estimate today",
    "toinen arvio tänään": "second estimate today",
    "toinen arvio tunneittain SYKE:n reaaliaikamittauksista": "second estimate hourly from SYKE real-time measurements",
    "päivän keskiarvo-ennuste": "forecast daily mean",
    "arvio mitatuista syötteistä": "estimate from measured inputs",
    "mitattu tunneittain": "measured hourly",
    "mittaukset tunneittain SYKE:n reaaliaikasivulta": "hourly measurements from SYKE real-time data",
    "SYKE päiväarvo": "SYKE daily value",
    "ennuste päivän loppuun": "forecast to end of day",
    "viimeisin mittaus": "latest measurement",
    "nykyinen malli": "current model",
    "eilen mitattu": "measured yesterday",
    "tuntiarvio": "hourly estimate",
    "ennusteen 5–95 %": "forecast 5–95 %",
    "vaihteluväli": "range (other years)",
    "mediaani": "median",
    "tänään": "today",
    "reissu": "trip",
    "reissu (vedä ajankohtaa)": "trip (drag the time)",
    "kohde toimii": "feature works",
    "kohde parhaimmillaan": "feature at its best",
    "paras": "best",
    "kaikilla vesillä": "at all levels",
    "yli kuvan": "above chart",
    "Virtaama m³/s": "Discharge m³/s",
    "Vedenkorkeus m": "Water level m",
    "ennuste tehty": "forecast made",
    "klo": "at",
    "SYKE:n vesistömalli": "SYKE hydrological model",
    "luettu SYKE:n kaaviokuvasta": "read from the SYKE chart image",
    "havainnot ja ennuste SYKE, tämän päivän arvo": "observations and forecast SYKE, today's value",
}

# Arvioinnin ja mittarikuvauksen lauseet (järjestys merkitsee)
KORVAUKSET = [
    (r"^parhaimmillaan$", "at its best"),
    (r"^toimii \((.+) alle parhaan\)$", r"works (\1 below best)"),
    (r"^toimii \((.+) yli parhaan\)$", r"works (\1 above best)"),
    (r"^liian vähän vettä \(puuttuu (.+)\)$", r"too little water (\1 short)"),
    (r"^liikaa vettä \((.+) yli\)$", r"too much water (\1 over)"),
    (r"^ei vesikaaviota – tarkista tilanne itse$", "no gauge chart – check conditions yourself"),
    (r": kaaviota ei saatu luettua$", ": chart could not be read"),
    (r": arvoa ei saatu kaaviosta$", ": no value could be read from the chart"),
    (r"^kaavio (\S+) ei ole tältä päivältä \(ennusteen alku (\d+)\. päivä\)$",
     r"chart \1 is not from today (forecast starts on day \2)"),
    (r" vedenkorkeus ", " water level "),
    (r" virtaama ", " discharge "),
    (r" veden lämpötila ", " water temperature "),
    (r"\(havainto (\d+) pv sitten", r"(observed \1 d ago"),
    (r"\(havainto", "(observed"),
    (r"\(malli", "(model"),
    (r"SYKE-data", "SYKE data"),
    (r"\(arvio ", "(estimate "),
    (r"arvio Pudasjärvi", "estimate Pudasjärvi"),
    (r"eilinen korjaus", "yesterday's correction"),
    (r", (\d+) pv: ", r", \1 d: "),
    (r"tulvaindeksi", "flood index"),
    (r"toinen arvio", "second estimate"),
    (r"\(ennuste \+(\d+) pv\)", r"(forecast +\1 d)"),
]


def kieli(kysely: dict[str, list[str]]) -> str:
    k = (kysely.get("kieli") or ["fi"])[0]
    return k if k in KIELET else "fi"


def kaanna(teksti: str, kieli: str) -> str:
    """Suomenkielinen teksti valitulle kielelle (suomi palautetaan sellaisenaan)."""
    if kieli == "fi":
        return teksti
    if teksti in SANAT:
        return SANAT[teksti]
    for kuvio, korvaus in KORVAUKSET:
        teksti = re.sub(kuvio, korvaus, teksti)
    return teksti
