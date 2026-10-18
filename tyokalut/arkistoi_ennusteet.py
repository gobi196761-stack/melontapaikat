#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.24", "tzdata>=2024.1", "google-auth>=2.20"]
# ///
"""Arkistoi SYKE:n virtaamaennusteet ja sovelluksen oman arvion (ks. ennustearkisto.py).

Verkossa arkistointi tehdään Vercel Cronilla (/api/arkistoi). Paikallisesti:

    uv run tyokalut/arkistoi_ennusteet.py              # -> aineisto/ennusteet/YYYY-MM-DD.json
    uv run tyokalut/arkistoi_ennusteet.py --firestore  # -> Firestore (FIREBASE_SERVICE_ACCOUNT)
    uv run tyokalut/arkistoi_ennusteet.py --korvaa     # korvaa saman päivän arkiston
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

JUURI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JUURI))

import ennustearkisto  # noqa: E402
import firestore  # noqa: E402

KANSIO = JUURI / "aineisto" / "ennusteet"


def truststore_kayttoon() -> None:
    try:   # paikallisesti Windowsin varmennevarasto, jos truststore on asennettu
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    from zoneinfo import ZoneInfo

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kansio", type=Path, default=KANSIO, help=f"tallennuskansio (oletus {KANSIO})")
    ap.add_argument("--firestore", action="store_true",
                    help=f"tallenna Firestoreen (kokoelma {ennustearkisto.KOKOELMA}) kansion sijaan")
    ap.add_argument("--korvaa", action="store_true", help="korvaa saman päivän arkisto")
    args = ap.parse_args(argv)
    truststore_kayttoon()

    nyt = dt.datetime.now(ZoneInfo("Europe/Helsinki"))
    tunniste = nyt.date().isoformat()
    kanta = firestore.Firestore.ymparistosta() if args.firestore else None
    if args.firestore and not kanta:
        print("FIREBASE_SERVICE_ACCOUNT puuttuu", file=sys.stderr)
        return 2
    polku = args.kansio / f"{tunniste}.json"
    if not args.korvaa and (kanta.lue(ennustearkisto.KOKOELMA, tunniste) is not None if kanta else polku.exists()):
        print(f"{tunniste} on jo arkistoitu (käytä --korvaa)", file=sys.stderr)
        return 0

    ajot, virheet = ennustearkisto.hae_ajot()
    arkisto = ennustearkisto.kokoa(ajot, nyt, virheet)
    for asema, virhe in virheet.items():
        print(f"varoitus: {asema}: {virhe}", file=sys.stderr)
    onnistuneet = ennustearkisto.onnistuneet(arkisto)
    if not onnistuneet:
        print("yhtään asemaa ei saatu – ei tallennettu", file=sys.stderr)
        return 1
    if kanta:
        kanta.kirjoita(ennustearkisto.KOKOELMA, tunniste, arkisto)
        kohde = f"Firestore {kanta.projekti}/{ennustearkisto.KOKOELMA}/{tunniste}"
    else:
        args.kansio.mkdir(parents=True, exist_ok=True)
        polku.write_text(json.dumps(arkisto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        kohde = str(polku)
    print(f"{kohde}: {len(onnistuneet)}/{len(ennustearkisto.ASEMAT)} asemaa, "
          f"{len(arkisto['arviot'])} omaa arviota")
    return 0


if __name__ == "__main__":
    sys.exit(main())
