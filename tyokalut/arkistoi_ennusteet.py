#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.24", "tzdata>=2024.1"]
# ///
"""Arkistoi SYKE:n virtaamaennusteet ja sovelluksen oman arvion päivittäin.

SYKE ei säilytä vanhoja ennusteitaan, joten niiden tarkkuutta voi verrata
vain, jos ennusteet tallennetaan itse. Aja kerran päivässä:

    uv run tyokalut/arkistoi_ennusteet.py            # -> aineisto/ennusteet/YYYY-MM-DD.json
    uv run tyokalut/arkistoi_ennusteet.py --korvaa   # korvaa saman päivän tiedoston

Jokaisen aseman ajo.jsonista tallennetaan
    qinlask_ka   mallin laskenta 7 pv taakse ja ennuste 7 pv eteen
    qinlask_5/95 ennusteen 5 %:n ja 95 %:n rajat, ennusteen alusta 7 pv eteen
    qhav         havainnot viimeiseltä 7 päivältä (ennusteen alku mukaan lukien)
ja arviomallien asemille (syke_data.ARVIOMALLIT) sovelluksen oma tämän
päivän arvo ja ennuste samalla tavalla kuin melonta.py ne laskee.
Tarkkuus lasketaan tyokalut/vertaa_ennusteet.py:llä.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

JUURI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JUURI))

import osm_sivut as osm  # noqa: E402
import syke_data  # noqa: E402
from syke_kaavio import Kaaviolukema  # noqa: E402

KANSIO = JUURI / "aineisto" / "ennusteet"
ENNUSTE_PAIVIA = 7
HAVAINTO_PAIVIA = 7

ASEMAT = {
    "61/q6101750y": "Maalismaa",
    "61/q6101452y": "Pahkakoski",
    "61/q6101600y": "Siurua",
    "61/q6100700y": "Kurenalus",
    "61/q6101210y": "Livojoki",
}


def _paivat(sarja: dict | None, alku: dt.date, loppu: dt.date) -> dict[str, float]:
    if not sarja:
        return {}
    tulos = {}
    paiva = alku
    while paiva <= loppu:
        v = syke_data._arvo(sarja, paiva)
        if v is not None:
            tulos[paiva.isoformat()] = v
        paiva += dt.timedelta(days=1)
    return tulos


def asematiedot(ajo: dict) -> dict:
    """Arkistoitavat luvut yhden aseman ajo.jsonista."""
    t = dt.date.fromisoformat(ajo["ennustepvm_www"])
    eteen = t + dt.timedelta(days=ENNUSTE_PAIVIA)
    return {
        "ennustepvm_www": t.isoformat(),
        "utc_aikaleima": ajo.get("utc_aikaleima"),
        "qinlask_ka": _paivat(ajo.get("qinlask_ka"), t - dt.timedelta(days=HAVAINTO_PAIVIA), eteen),
        "qinlask_5": _paivat(ajo.get("qinlask_5"), t, eteen),
        "qinlask_95": _paivat(ajo.get("qinlask_95"), t, eteen),
        "qhav": _paivat(ajo.get("qhav"), t - dt.timedelta(days=HAVAINTO_PAIVIA - 1), t),
    }


def oma_arvio(asema: str, ajot: dict[str, dict]) -> dict | None:
    """Sovelluksen tämän päivän arvo ja ennuste arviomallin asemalle (kuten melonta.py)."""
    oma = ajot.get(f"{asema}/ajo.json")
    if not oma:
        return None
    lukema = Kaaviolukema(url=f"{osm.SYKE_POHJA}{asema}/qinlyhyt.png", suure="virtaama",
                          yksikko="m3/s", tanaan_paiva=None, havaittu=None,
                          havaittu_paivia_sitten=None, malli=None)
    varoitukset = [v for v in (syke_data.taydenna(lukema, oma), syke_data.arvioi_tanaan(lukema, ajot)) if v]
    t = dt.date.fromisoformat(oma["ennustepvm_www"])
    ennuste = {}
    for n in range(1, ENNUSTE_PAIVIA + 1):
        v = lukema.ennuste_korjattu(n)
        if v is not None:
            ennuste[(t + dt.timedelta(days=n)).isoformat()] = round(v, 3)
    return {
        "malli": syke_data.ARVIOMALLIT[asema].nimi,
        "lahde": lukema.lahde,
        "ennustepvm_www": t.isoformat(),
        "tanaan": None if lukema.arvo is None else round(lukema.arvo, 3),
        "ennuste": ennuste,
        "varoitukset": varoitukset,
    }


def kokoa(ajot: dict[str, dict], arkistoitu: dt.datetime, virheet: dict[str, str] | None = None) -> dict:
    """`ajot`: ajo.json-avain ('61/q6101750y/ajo.json') -> luettu ajo.json."""
    asemat = {}
    for asema, nimi in ASEMAT.items():
        ajo = ajot.get(f"{asema}/ajo.json")
        tieto: dict = {"nimi": nimi}
        try:
            tieto.update(asematiedot(ajo) if ajo else {"virhe": (virheet or {}).get(asema, "ei haettu")})
        except (KeyError, TypeError, ValueError) as e:
            tieto["virhe"] = f"ajo.json ei kelpaa: {e!r}"
        asemat[asema] = tieto
    arviot = {}
    for asema in syke_data.ARVIOMALLIT:
        try:
            arvio = oma_arvio(asema, ajot)
        except (KeyError, TypeError, ValueError):
            arvio = None
        if arvio:
            arviot[asema] = arvio
    return {"arkistoitu": arkistoitu.isoformat(timespec="seconds"), "asemat": asemat, "arviot": arviot}


def hae_ajot() -> tuple[dict[str, dict], dict[str, str]]:
    try:   # paikallisesti Windowsin varmennevarasto, jos truststore on asennettu
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    avaimet = {f"{a}/ajo.json" for a in ASEMAT}
    for malli in syke_data.ARVIOMALLIT.values():
        avaimet.update(malli.ajo_avaimet())
    hakija = osm.Hakija()
    ajot, virheet = {}, {}
    for avain in sorted(avaimet):
        data, virhe = osm.hae_turvallisesti(hakija, osm.kaavio_url(avain))
        try:
            if data:
                ajot[avain] = syke_data.lue_ajo(data)
        except ValueError as e:
            virhe = f"ajo.json ei ole luettavissa ({e})"
        if virhe:
            virheet[avain.rsplit("/", 1)[0]] = virhe
    return ajot, virheet


def main(argv: list[str] | None = None) -> int:
    from zoneinfo import ZoneInfo

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kansio", type=Path, default=KANSIO, help=f"tallennuskansio (oletus {KANSIO})")
    ap.add_argument("--korvaa", action="store_true", help="korvaa saman päivän tiedosto")
    args = ap.parse_args(argv)

    nyt = dt.datetime.now(ZoneInfo("Europe/Helsinki"))
    polku = args.kansio / f"{nyt.date().isoformat()}.json"
    if polku.exists() and not args.korvaa:
        print(f"{polku} on jo olemassa (käytä --korvaa)", file=sys.stderr)
        return 0
    ajot, virheet = hae_ajot()
    arkisto = kokoa(ajot, nyt, virheet)
    onnistuneet = [a for a, t in arkisto["asemat"].items() if "virhe" not in t]
    for asema, virhe in virheet.items():
        print(f"varoitus: {asema}: {virhe}", file=sys.stderr)
    if not onnistuneet:
        print("yhtään asemaa ei saatu – ei tallennettu", file=sys.stderr)
        return 1
    args.kansio.mkdir(parents=True, exist_ok=True)
    polku.write_text(json.dumps(arkisto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{polku}: {len(onnistuneet)}/{len(ASEMAT)} asemaa, {len(arkisto['arviot'])} omaa arviota")
    return 0


if __name__ == "__main__":
    sys.exit(main())
