"""Turvallisuusvaroitus sovelluksen avautuessa: kylmä vesi, maatuuli ja matala merivesi Oulussa.

Tiedot Ilmatieteen laitoksen avoimesta datasta (opendata.fmi.fi, WFS):
- Oulun Toppilan mareografi (fmisid 134248): meriveden lämpötila (TW_PT1H_AVG, °C) ja
  vedenkorkeus teoreettisesta keskivedestä (WATLEV, mm)
- saman paikan vedenkorkeusennuste (SeaLevel, cm keskivedestä)
- tuuliennuste Oulun rannikolla (WindSpeedMS, WindDirection, WindGust)
Jokien veden lämpötilat tulevat SYKE:n vesistömallista (paikkojen lukemat, ks. melonta.py).

Maatuulella (idän ja etelän väliltä) Oulun rannikko näyttää tyyneltä, mutta tuuli voimistuu
ulompana, paluu rantaan on vastatuuleen ja merivesi laskee: matalat salmet, kuten Mustasalmi,
voivat olla kuivilla.
"""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlencode

import osm_sivut as osm

FMI = "https://opendata.fmi.fi/wfs"
TOPPILA = 134248                 # Oulu Toppila, mareografi
RANNIKKO = (65.03, 25.40)        # tuuliennusteen piste Oulun edustalla
ENNUSTE_H = 12                   # tuuli- ja vedenkorkeusennuste näin monta tuntia eteenpäin

KUIVAPUKU_ALLE = 10.0            # °C: kuivapuku ainoa oikea ratkaisu
MARKAPUKU_ALLE = 15.0            # °C: ei ilman märkäpukua (tai kuivapukua)
MAATUULI = (60, 200)             # tuulen suunta (mistä puhaltaa, °): maalta merelle Oulussa
MAATUULI_MS = 4.0                # keskituuli, josta maatuuli on vaarallinen
MAATUULI_PUUSKA_MS = 7.0
MATALA_VESI_CM = -20             # keskivedestä: matalat salmet (Mustasalmi) voivat kuivua (arvio)

SUUNNAT = {"fi": ("pohjois", "koillis", "itä", "kaakkois", "etelä", "lounais", "länsi", "luoteis"),
           "en": ("northerly", "north-easterly", "easterly", "south-easterly", "southerly",
                  "south-westerly", "westerly", "north-westerly")}


def _osoite(kysely: str, **parametrit) -> str:
    return f"{FMI}?" + urlencode({"service": "WFS", "version": "2.0.0", "request": "getFeature",
                                  "storedquery_id": kysely, **parametrit})


def lue_wfs(data: bytes) -> list[tuple[float, str, float]]:
    """FMI:n simple-WFS-vastaus -> [(aika unix s, parametri, arvo)], NaN-arvot pois."""
    tulos = []
    teksti = data.decode("utf-8", errors="replace")
    for aika, nimi, arvo in re.findall(r"<BsWfs:Time>([^<]+)</BsWfs:Time>\s*<BsWfs:ParameterName>([^<]+)"
                                       r"</BsWfs:ParameterName>\s*<BsWfs:ParameterValue>([^<]+)<", teksti):
        try:
            luku = float(arvo)
        except ValueError:
            continue
        if luku != luku:   # NaN
            continue
        tulos.append((dt.datetime.fromisoformat(aika.replace("Z", "+00:00")).timestamp(), nimi, luku))
    return tulos


def _sarja(rivit, nimi: str) -> list[tuple[float, float]]:
    return sorted((a, v) for a, n, v in rivit if n == nimi)


def hae(hakija: osm.Hakija, nyt: dt.datetime | None = None) -> dict:
    """Merivesi, vedenkorkeus ja maatuuli Oulussa:
    {"meri": °C, "vesi": cm nyt, "vesi_min": (cm, aika), "maatuuli": {"ms", "puuska", "suunta", "aika"}}.
    Puuttuvat tiedot jäävät pois (palvelu ei vastaa)."""
    nyt = nyt or dt.datetime.now(dt.timezone.utc)
    alku = (nyt - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00Z")
    loppu = (nyt + dt.timedelta(hours=ENNUSTE_H)).strftime("%Y-%m-%dT%H:00:00Z")
    osoitteet = {
        "havainto": _osoite("fmi::observations::mareograph::simple", fmisid=TOPPILA,
                            parameters="WATLEV,TW_PT1H_AVG", starttime=alku),
        "vesi": _osoite("fmi::forecast::sealevel::point::simple", fmisid=TOPPILA, parameters="SeaLevel",
                        timestep=60, endtime=loppu),
        "tuuli": _osoite("fmi::forecast::edited::weather::scandinavia::point::simple",
                         latlon=f"{RANNIKKO[0]},{RANNIKKO[1]}", parameters="WindSpeedMS,WindDirection,WindGust",
                         timestep=60, endtime=loppu),
    }
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        haetut = dict(zip(osoitteet, pool.map(lambda u: osm.hae_turvallisesti(hakija, u)[0], osoitteet.values())))
    rivit = {k: lue_wfs(v) if v else [] for k, v in haetut.items()}
    tulos: dict = {}
    if meri := _sarja(rivit["havainto"], "TW_PT1H_AVG"):
        tulos["meri"] = meri[-1][1]
    if taso := _sarja(rivit["havainto"], "WATLEV"):
        tulos["vesi"] = round(taso[-1][1] / 10)   # mm -> cm
    raja = nyt.timestamp()
    if ennuste := [(a, v) for a, v in _sarja(rivit["vesi"], "SeaLevel") if a >= raja - 3600]:
        aika, cm = min(ennuste, key=lambda r: r[1])
        tulos["vesi_min"] = (round(cm), aika)
    tuuli = {}
    for a, n, v in rivit["tuuli"]:
        if a >= raja - 3600:
            tuuli.setdefault(a, {})[n] = v
    maalta = [(a, t) for a, t in sorted(tuuli.items())
              if "WindSpeedMS" in t and MAATUULI[0] <= t.get("WindDirection", -1) <= MAATUULI[1]
              and (t["WindSpeedMS"] >= MAATUULI_MS or t.get("WindGust", 0) >= MAATUULI_PUUSKA_MS)]
    if maalta:
        aika, t = max(maalta, key=lambda r: r[1]["WindSpeedMS"])
        tulos["maatuuli"] = {"ms": t["WindSpeedMS"], "puuska": t.get("WindGust"), "suunta": t["WindDirection"],
                             "aika": aika, "alkaa": maalta[0][0]}
    return tulos


def _luku(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}".rstrip("0").rstrip(".")


def viestit(turva: dict, joet: list[float], kieli: str, ajankohta) -> list[tuple[str, str]]:
    """Varoitukset [(otsikko, teksti)] valitulla kielellä; tyhjä, jos varoitettavaa ei ole.
    joet: Suomen jokien veden lämpötilat (°C); ajankohta(unix s, kieli) -> 'ke 14.00'."""
    en = kieli == "en"
    tulos = []
    meri = turva.get("meri")
    kaikki = [*joet, *([meri] if meri is not None else [])]
    if kaikki and min(kaikki) < MARKAPUKU_ALLE:
        osat = []
        if joet:
            ala, yla = min(joet), max(joet)
            vali = _luku(ala) if round(ala) == round(yla) else f"{_luku(ala)}–{_luku(yla)}"
            osat.append(f"rivers {vali} °C" if en else f"joissa {vali} °C")
        if meri is not None:
            osat.append(f"sea off Oulu {_luku(meri)} °C" if en else f"merellä Oulun edustalla {_luku(meri)} °C")
        lampo = ", ".join(osat)
        if min(kaikki) < KUIVAPUKU_ALLE:
            tulos.append((
                "🥶 Cold water: a dry suit is the only right choice" if en else
                "🥶 Kylmä vesi: kuivapuku on ainoa oikea ratkaisu",
                (f"Water temperature: {lampo}. In water this cold you lose the ability to swim and help yourself "
                 "within minutes. Especially if you are heading out on a trip or to sea: wear a dry suit with "
                 "warm layers underneath, and dress for the water temperature, not the air temperature." if en else
                 f"Veden lämpötila: {lampo}. Näin kylmässä vedessä toimintakyky ja uintikyky menevät minuuteissa. "
                 "Varsinkin retkelle tai merelle lähtiessä: kuivapuku ja sen alle lämmintä, ja pukeudu veden, "
                 "älä ilman lämpötilan mukaan.")))
        else:
            tulos.append((
                "🌡️ Water too cold without a wetsuit" if en else "🌡️ Vesi liian kylmää ilman märkäpukua",
                (f"Water temperature: {lampo}. Wear at least a wetsuit; for trips and at sea, where a swim can "
                 "be long, a dry suit is the safest choice." if en else
                 f"Veden lämpötila: {lampo}. Pue vähintään märkäpuku; retkellä ja merellä, missä uinti voi "
                 "venyä pitkäksi, kuivapuku on turvallisin valinta.")))

    tuuli = turva.get("maatuuli")
    vesi, vesi_min = turva.get("vesi"), turva.get("vesi_min")
    matala = ((vesi is not None and vesi <= MATALA_VESI_CM)
              or (vesi_min is not None and vesi_min[0] <= MATALA_VESI_CM))
    if tuuli or matala:
        osat = []
        if tuuli:
            suunta = SUUNNAT["en" if en else "fi"][round(tuuli["suunta"] / 45) % 8]
            puuska = tuuli.get("puuska")
            puuska_t = ((f", gusts {_luku(puuska)} m/s" if en else f", puuskissa {_luku(puuska)} m/s")
                        if puuska and puuska > tuuli["ms"] else "")
            hetki = ajankohta(tuuli["aika"], kieli)
            osat.append(
                f"Offshore wind on the Oulu coast: {suunta} wind {_luku(tuuli['ms'])} m/s{puuska_t} ({hetki}). "
                "With a land wind the coast looks deceptively calm, but the wind grows stronger further out "
                "and the way back to shore is straight into a headwind. Stay close to the shore." if en else
                f"Maatuulivaroitus Oulun rannikolla: {suunta}tuulta {_luku(tuuli['ms'])} m/s{puuska_t} ({hetki}). "
                "Maatuulella rannikko näyttää petollisen tyyneltä, mutta ulompana tuuli voimistuu ja paluu "
                "rantaan on vastatuuleen. Pysy lähellä rantaa.")
        tasot = []
        if vesi is not None:
            tasot.append(f"now {vesi:+d} cm" if en else f"nyt {vesi:+d} cm")
        if vesi_min is not None and (vesi is None or vesi_min[0] < vesi):
            hetki = ajankohta(vesi_min[1], kieli)
            tasot.append(f"forecast {vesi_min[0]:+d} cm ({hetki})" if en else
                         f"ennuste {vesi_min[0]:+d} cm ({hetki})")
        taso = (f" Sea level in Oulu {', '.join(tasot)} relative to mean water." if en else
                f" Merivesi Oulussa {', '.join(tasot)} keskivedestä.") if tasot else ""
        if tuuli:
            osat.append(
                "A land wind also lowers the sea level: shallow straits such as Mustasalmi may run dry so that "
                f"you cannot get through just when you are struggling back against the wind.{taso}" if en else
                "Maatuuli laskee myös merivettä: matalat salmet, kuten Mustasalmi, voivat olla kuivilla, eikä "
                f"niistä pääse läpi juuri kun vastatuuleen on jaksanut takaisin.{taso}")
        else:
            osat.append(
                "The sea level is low: shallow straits such as Mustasalmi may be dry so that you cannot get "
                f"through.{taso}" if en else
                "Merivesi on matalalla: matalat salmet, kuten Mustasalmi, voivat olla kuivilla, eikä niistä "
                f"pääse läpi.{taso}")
        tulos.append(("💨 Offshore wind and low water" if en and tuuli else
                      "🌊 Low sea level" if en else
                      "💨 Maatuuli ja matala vesi" if tuuli else "🌊 Matala merivesi",
                      " ".join(osat)))
    return tulos
