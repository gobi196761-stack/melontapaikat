"""Paikkojen kuvat Wikimedia Commonsista (vapaat lisenssit, tekijä ja lisenssi näytetään).

Kuva valitaan automaattisesti paikan sijainnin läheltä (geohaku): vaakakuva, joka on vähintään
1000 px leveä ja jonka nimessä tai kuvauksessa on vesistöön tai paikan nimeen viittaava sana.
KIINTEAT-kuvat ohittavat haun (ylläpitäjän valinta), EI_KUVAA-paikoille ei näytetä kuvaa.
Tulokset tallennetaan Firestoreen (asetukset/kuvat), ja ne haetaan uudelleen UUSINTA_PV:n välein.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import osm_sivut as osm

COMMONS = "https://commons.wikimedia.org/w/api.php?"
KOKOELMA, DOKUMENTTI = "asetukset", "kuvat"
UUSINTA_PV = 30
SADE_M = 2000
LEVEYS, PIENI = 960, 250   # Commonsin vakiokoot: paikkasivu ja listan pikkukuva

KIINTEAT: dict[str, str] = {   # paikan nimi -> Commons-tiedosto
    "Koiteli (Kiiminkijoki)": "File:Koitelinkoski Kiiminki 2006 05 20.JPG",
}
EI_KUVAA: set[str] = set()
OMAT: dict[str, str] = {   # sovelluksen tekijän omat kuvat (omat_kuvat/, reitti /omat-kuvat/<tiedosto>)
    "Hawa'Ii (Iijoki, Maalismaa)": "maalismaa.jpg",
    "Kitulankoski (Iijoki)": "kitulankoski.jpg",
    "Kiiminkijoki: Kivarinjärvi-Kalliuskoski": "kalliuskoski.jpg",
}

VESISANAT = ("koski", "joki", "köngäs", "kongas", "fors", "älv", "river", "rapid", "virta", "melon", "kajak",
             "kayak", "canoe", "suvanto", "vesi", "putous", "waterfall", "ström", "niva", "kuohu")
KIELLETYT = ("kirkko", "church", "kartta", "map", "logo", "kyltti", "sign", "muistomerk", "memorial", "hauta",
             "grave", "pier", "laituri", "harbour", "satama", "talo", "house", "koulu", "school", "asema", "station", "silta-kyltti", "interior",
             "sisäkuva", "portrait", "muotokuva", "auto", "bus", "train", "juna", "coat of arms", "vaakuna")

_kuvat: dict[str, dict] | None = None   # nimi -> {"kuva", "pieni", "sivu", "tekija", "lisenssi", "haettu"} tai {"haettu"}


def _teksti(arvo: str, enintaan: int = 120) -> str:
    teksti = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", arvo or ""))).strip()
    return teksti[:enintaan]


def _paikan_sanat(nimi: str) -> list[str]:
    return [s for s in re.findall(r"\w+", nimi.lower()) if len(s) >= 5]


class HakuVirhe(Exception):
    """Commons ei vastannut: paikkaa ei merkitä haetuksi."""


def _hae_json(hakija: osm.Hakija, parametrit: dict) -> dict:
    data, virhe = osm.hae_turvallisesti(hakija, COMMONS + urlencode({**parametrit, "format": "json"}), uusintoja=0)
    try:
        return json.loads(data.decode("utf-8"))
    except (AttributeError, ValueError):
        raise HakuVirhe(virhe or "virheellinen vastaus") from None


def _tiedot(hakija: osm.Hakija, otsikot: list[str]) -> dict[str, dict]:
    """Tiedostojen koko, pikkukuvat, tekijä, lisenssi ja kuvaus (otsikko -> tiedot)."""
    if not otsikot:
        return {}
    vastaus = _hae_json(hakija, {"action": "query", "titles": "|".join(otsikot[:50]), "prop": "imageinfo",
                                 "iiprop": "url|size|mime|extmetadata", "iiurlwidth": LEVEYS,
                                 "iiextmetadatafilter": "Artist|LicenseShortName|ImageDescription|ObjectName"})
    tulos = {}
    for sivu in (vastaus.get("query", {}).get("pages") or {}).values():
        tiedot = (sivu.get("imageinfo") or [None])[0]
        if tiedot:
            tulos[sivu["title"]] = tiedot
    return tulos


def _kuva(otsikko: str, tiedot: dict) -> dict | None:
    m = tiedot.get("extmetadata") or {}
    lisenssi = _teksti(m.get("LicenseShortName", {}).get("value", ""), 40)
    kuva = tiedot.get("thumburl") or tiedot.get("url")
    if not kuva or not lisenssi or "fair use" in lisenssi.lower():
        return None
    pieni = kuva.replace(f"/{LEVEYS}px-", f"/{PIENI}px-") if f"/{LEVEYS}px-" in kuva else kuva
    return {"kuva": kuva, "pieni": pieni, "sivu": tiedot.get("descriptionurl", ""),
            "tekija": _teksti(m.get("Artist", {}).get("value", ""), 80) or "?", "lisenssi": lisenssi,
            "otsikko": otsikko}


def _sopiva(otsikko: str, tiedot: dict, sanat: list[str]) -> int:
    """Pisteet (0 = ei kelpaa): vaakakuva, vähintään 1000 px, vesistö- tai paikkasana, ei kiellettyjä."""
    if tiedot.get("mime") != "image/jpeg" or tiedot.get("width", 0) < 1000 \
            or tiedot.get("width", 0) < tiedot.get("height", 0):
        return 0
    m = tiedot.get("extmetadata") or {}
    teksti = " ".join([otsikko, _teksti(m.get("ImageDescription", {}).get("value", ""), 500),
                       _teksti(m.get("ObjectName", {}).get("value", ""), 200)]).lower()
    if any(k in teksti for k in KIELLETYT):
        return 0
    pisteet = 2 * sum(s in teksti for s in sanat) + sum(v in teksti for v in VESISANAT)
    return pisteet


def etsi(hakija: osm.Hakija, nimi: str, sijainti: tuple[float, float] | None) -> dict | None:
    """Paikan kuva: kiinteä valinta tai paras geohaun osuma; None, jos sopivaa ei löydy."""
    if nimi in EI_KUVAA:
        return None
    if nimi in KIINTEAT:
        otsikko = KIINTEAT[nimi]
        tiedot = _tiedot(hakija, [otsikko]).get(otsikko)
        return _kuva(otsikko, tiedot) if tiedot else None
    if not sijainti:
        return None
    haku = _hae_json(hakija, {"action": "query", "list": "geosearch", "gscoord": f"{sijainti[0]}|{sijainti[1]}",
                              "gsradius": SADE_M, "gsnamespace": 6, "gslimit": 40})
    otsikot = [g["title"] for g in haku.get("query", {}).get("geosearch", [])]   # lähin ensin
    tiedot = _tiedot(hakija, otsikot)
    sanat = _paikan_sanat(nimi)
    ehdokkaat = [(_sopiva(o, tiedot[o], sanat), -i, o) for i, o in enumerate(otsikot) if o in tiedot]
    ehdokkaat = [x for x in ehdokkaat if x[0] > 0]
    if not ehdokkaat:
        return None
    _, _, paras = max(ehdokkaat)
    return _kuva(paras, tiedot[paras])


def lataa(kanta) -> dict[str, dict]:
    """Tallennetut kuvat Firestoresta (kerran prosessia kohden)."""
    global _kuvat
    if _kuvat is None:
        _kuvat = {}
        try:
            data = kanta.lue(KOKOELMA, DOKUMENTTI) if kanta else None
        except Exception:   # noqa: BLE001 – kuvat ovat vapaaehtoisia
            data = None
        for rivi in (data or {}).get("kuvat", []):
            if isinstance(rivi, dict) and rivi.get("nimi"):
                _kuvat[rivi["nimi"]] = rivi
    return _kuvat


def paivita(hakija: osm.Hakija, kanta, paikat, enintaan: int = 12) -> dict[str, dict]:
    """Hakee puuttuvat ja vanhentuneet kuvat (enintään `enintaan` paikkaa kerralla) ja tallentaa ne."""
    kuvat = lataa(kanta)
    raja = (dt.date.today() - dt.timedelta(days=UUSINTA_PV)).isoformat()
    def vanha(p) -> bool:
        rivi = kuvat.get(p.nimi) or {}
        if p.nimi in KIINTEAT:
            return rivi.get("otsikko") != KIINTEAT[p.nimi]
        # vanhentunut tai valittu ennen kuin sen sana lisättiin kiellettyihin
        return rivi.get("haettu", "") < raja or any(k in rivi.get("otsikko", "").lower() for k in KIELLETYT)

    vanhat = [p for p in paikat if vanha(p)]
    if not vanhat:
        return kuvat
    def hae(p):
        try:
            return etsi(hakija, p.nimi, p.sijainti), True
        except HakuVirhe:
            return None, False   # yritetään seuraavalla kerralla uudelleen

    with ThreadPoolExecutor(max_workers=6) as pooli:
        loydetyt = list(pooli.map(hae, vanhat[:enintaan]))
    if not any(ok for _, ok in loydetyt):
        return kuvat
    for p, (kuva, ok) in zip(vanhat, loydetyt):
        if ok:
            kuvat[p.nimi] = {**(kuva or {}), "nimi": p.nimi, "haettu": dt.date.today().isoformat()}
    if kanta:
        try:
            kanta.kirjoita(KOKOELMA, DOKUMENTTI, {"kuvat": list(kuvat.values())})
        except Exception:   # noqa: BLE001
            pass
    return kuvat


def kuva(nimi: str, kanta=None) -> dict | None:
    """Paikan tallennettu kuva tai None."""
    rivi = lataa(kanta).get(nimi) or {}
    return rivi if rivi.get("kuva") else None
