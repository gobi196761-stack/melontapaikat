#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["google-auth>=2.20"]
# ///
"""Arkistoitujen virtaamaennusteiden tarkkuus myöhemmin julkaistuihin havaintoihin.

    uv run tyokalut/vertaa_ennusteet.py                  # aineisto/ennusteet/*.json
    uv run tyokalut/vertaa_ennusteet.py --firestore      # Firestoresta (FIREBASE_SERVICE_ACCOUNT)
    uv run tyokalut/vertaa_ennusteet.py --kansio X --json

Ennuste +n pv = ennusteen alkupäivän (ennustepvm_www) jälkeinen n:s päivä.
Havainto (qhav) otetaan uusimmasta arkistosta, jossa se on, koska SYKE voi
tarkentaa havaintoja jälkikäteen. Menetelmät:

    SYKE         qinlask_ka sellaisenaan
    SYKE+muutos  tuorein havainto + SYKE:n ennusteen muutos siitä päivästä
    sovellus     arkistoitu sovelluksen oma ennuste (arviomallien asemat)
    pysyvyys     tuorein havainto ennusteen alkupäivänä (vertailukohta)

Harha = ennuste - havainto keskimäärin (positiivinen = yliarvio).
5–95 % = osuus havainnoista, jotka osuivat SYKE:n ennusteen 5–95 %:n välille.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

JUURI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JUURI))

import firestore  # noqa: E402

KANSIO = JUURI / "aineisto" / "ennusteet"
KOKOELMA = os.environ.get("FIRESTORE_KOKOELMA", "ennusteet")   # kuten ennustearkisto.py
HORISONTIT = (1, 2, 3)
MENETELMAT = ("SYKE", "SYKE+muutos", "sovellus", "pysyvyys")


def lue_arkistot(kansio: Path) -> list[dict]:
    arkistot = []
    for polku in sorted(kansio.glob("*.json")):
        try:
            arkistot.append(json.loads(polku.read_text(encoding="utf-8")))
        except ValueError as e:
            print(f"varoitus: {polku.name} ohitetaan ({e})", file=sys.stderr)
    return arkistot


def havainnot(arkistot: list[dict]) -> dict[str, dict[str, float]]:
    """asema -> päivä -> qhav; uudemman arkiston arvo korvaa vanhemman."""
    tulos: dict[str, dict[str, float]] = defaultdict(dict)
    for arkisto in sorted(arkistot, key=lambda a: a.get("arkistoitu", "")):
        for asema, tieto in arkisto.get("asemat", {}).items():
            tulos[asema].update(tieto.get("qhav") or {})
    return tulos


def _tuorein(qhav: dict[str, float], t: str) -> tuple[str, float] | None:
    paivat = [p for p in qhav if p <= t]
    return (max(paivat), qhav[max(paivat)]) if paivat else None


def ennusteparit(arkistot: list[dict]):
    """Tuottaa (asema, n, menetelmä, ennuste, havainto, väli osui | None)."""
    hav = havainnot(arkistot)
    # sama ennuste voi olla useassa arkistossa, jos SYKE ei ole päivittänyt sitä: uusin voittaa
    ennusteet = {}
    for arkisto in sorted(arkistot, key=lambda a: a.get("arkistoitu", "")):
        for asema, tieto in arkisto.get("asemat", {}).items():
            if "virhe" not in tieto:
                ennusteet[asema, tieto["ennustepvm_www"]] = arkisto, tieto
    for (asema, _), (arkisto, tieto) in ennusteet.items():
        t = dt.date.fromisoformat(tieto["ennustepvm_www"])
        ka = tieto.get("qinlask_ka") or {}
        tuorein = _tuorein(tieto.get("qhav") or {}, t.isoformat())
        arvio = (arkisto.get("arviot") or {}).get(asema) or {}
        oma = (arvio.get("ennuste") or {}) if arvio.get("ennustepvm_www") == t.isoformat() else {}
        for n in HORISONTIT:
            paiva = (t + dt.timedelta(days=n)).isoformat()
            toteutui = hav.get(asema, {}).get(paiva)
            if toteutui is None:
                continue
            if paiva in ka:
                ala, yla = tieto.get("qinlask_5", {}).get(paiva), tieto.get("qinlask_95", {}).get(paiva)
                osui = ala <= toteutui <= yla if ala is not None and yla is not None else None
                yield asema, n, "SYKE", ka[paiva], toteutui, osui
                if tuorein and tuorein[0] in ka:
                    yield asema, n, "SYKE+muutos", tuorein[1] + ka[paiva] - ka[tuorein[0]], toteutui, None
            if paiva in oma:
                yield asema, n, "sovellus", oma[paiva], toteutui, None
            if tuorein:
                yield asema, n, "pysyvyys", tuorein[1], toteutui, None


def vertaa(arkistot: list[dict]) -> list[dict]:
    virheet: dict[tuple, list[float]] = defaultdict(list)
    osumat: dict[tuple, list[bool]] = defaultdict(list)
    for asema, n, menetelma, ennuste, toteutui, osui in ennusteparit(arkistot):
        virheet[asema, n, menetelma].append(ennuste - toteutui)
        if osui is not None:
            osumat[asema, n, menetelma].append(osui)
    nimet = {a: t.get("nimi", a) for ark in arkistot for a, t in ark.get("asemat", {}).items()}
    rivit = []
    for (asema, n, menetelma), e in sorted(virheet.items(),
                                           key=lambda kv: (kv[0][0], kv[0][1], MENETELMAT.index(kv[0][2]))):
        o = osumat.get((asema, n, menetelma))
        rivit.append({
            "asema": asema, "nimi": nimet.get(asema, asema), "paivia": n, "menetelma": menetelma,
            "n": len(e), "rmse": math.sqrt(sum(x * x for x in e) / len(e)), "harha": sum(e) / len(e),
            "vali_osui": sum(o) / len(o) if o else None,
        })
    return rivit


def tulosta(rivit: list[dict], arkistoja: int) -> None:
    print(f"Arkistoja {arkistoja}. Virheet m³/s (harha = ennuste - havainto).")
    if not rivit:
        print("Ei vielä vertailukelpoisia pareja: tarvitaan arkisto, jonka +1 pv:n havainto on julkaistu.")
        return
    edellinen = None
    for r in rivit:
        if r["asema"] != edellinen:
            print(f"\n{r['nimi']} ({r['asema']})")
            print(f"  {'pv':>3}  {'menetelmä':<12} {'n':>4} {'RMSE':>8} {'harha':>8} {'5–95 %':>7}")
            edellinen = r["asema"]
        vali = f"{100 * r['vali_osui']:.0f} %" if r["vali_osui"] is not None else ""
        print(f"  +{r['paivia']:<2}  {r['menetelma']:<12} {r['n']:>4} {r['rmse']:>8.1f} {r['harha']:>+8.1f} {vali:>7}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kansio", type=Path, default=KANSIO, help=f"arkistokansio (oletus {KANSIO})")
    ap.add_argument("--firestore", action="store_true", help=f"lue Firestoresta (kokoelma {KOKOELMA})")
    ap.add_argument("--json", action="store_true", help="tulos JSONina")
    args = ap.parse_args(argv)
    if args.firestore:
        try:   # paikallisesti Windowsin varmennevarasto, jos truststore on asennettu
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        kanta = firestore.Firestore.ymparistosta()
        if not kanta:
            print("FIREBASE_SERVICE_ACCOUNT puuttuu", file=sys.stderr)
            return 2
        arkistot = list(kanta.listaa(KOKOELMA).values())
    else:
        arkistot = lue_arkistot(args.kansio)
    rivit = vertaa(arkistot)
    if args.json:
        print(json.dumps(rivit, ensure_ascii=False, indent=1))
    else:
        tulosta(rivit, len(arkistot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
