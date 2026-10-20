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
    "Veden lämpötila": "Water temperature",
    " – kylmää vettä, pukeudu uintia varten!": " – cold water, dress for a swim!",
    "Paikka": "Spot",
    "Pisteet": "Score",
    "+1 / +2 / +3 pv": "+1 / +2 / +3 d",
    "peli": "play spot",
    "retki": "river run",
    "km Oulusta": "km from Oulu",
    "Muut kohteet": "Other features",
    "Ei vesikaaviota – tarkista itse": "No gauge chart – check yourself",
    "Huomautukset": "Notes",
    "Lisää suosikkeihin": "Add to favourites",
    "Suomeksi": "Suomeksi",
    "In English": "In English",
    # kaaviot
    "mittari": "gauge",
    "malli (ennuste katkoviivana)": "model (forecast dashed)",
    "ennuste": "forecast",
    "havainto": "observed",
    "laskettu arvio": "computed estimate",
    "keskivirhe": "mean error",
    "arvio tänään": "estimate today",
    "ennusteen 5–95 %": "forecast 5–95 %",
    "vaihteluväli": "range (other years)",
    "mediaani": "median",
    "tänään": "today",
    "kohde toimii": "feature works",
    "kohde parhaimmillaan": "feature at its best",
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
