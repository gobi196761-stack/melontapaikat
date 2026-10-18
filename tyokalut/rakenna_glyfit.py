"""Rakentaa glyfit.json-tiedoston (numeroiden ja selitetekstin merkkimallit).

Mallit leikataan tunnetuista SYKE-kaavioista, joiden tekstit on luettu
käsin (TOTUUS-taulukko alla). Aja uudelleen, jos SYKE muuttaa fonttia:

    uv run tyokalut/rakenna_glyfit.py

Osa tests/fixtures-kuvista jätetään tarkoituksella pois, jotta testit
mittaavat tunnistusta kuvilla, joita mallit eivät ole nähneet.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

JUURI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JUURI))

import syke_kaavio as sk  # noqa: E402

FIXTURES = JUURI / "tests" / "fixtures"


def _vali(yla: float, ala: float, askel: float, desimaalit: int) -> list[str]:
    n = int(round((yla - ala) / askel))
    return [f"{yla - i * askel:.{desimaalit}f}" for i in range(n + 1)]


# tiedosto -> (y-akselin tikit ylhäältä alas, x-akselin 1. päivä, selitteen rivit)
TOTUUS = {
    "67_q6702110y_wlyhyt.png": (_vali(29.2, 27.6, 0.2, 1), 8, [
        "MHW 30.86 NHW 29.73", "HW 32.41 m 11.06.1968",
        "MNW 26.68 HNW 27.37", "NW 26.28 m 27.10.1997", "18-Oct-2026 14:49 WSFS-O"]),
    "61_l611331001y_w3lyhyt.png": (_vali(108.8, 107.7, 0.1, 1), 8, [
        "MHW 109.82 NHW 108.59", "HW 110.90 m 14.05.1982",
        "MNW 106.77 HNW 107.34", "NW 106.25 m 25.08.1980", "18-Oct-2026 14:53 WSFS-O"]),
    "57_q5700700y_qinlyhyt.png": (_vali(160, 0, 20, 0), 8, [
        "MHQ 334 m³/s NHQ 96.0", "19.05.1955 HQ 686 m³/s",
        "MNQ 4.6 m³/s HNQ 15.5", "12.03.1942 NQ 0.10 m³/s", "18-Oct-2026 15:22 WSFS-O"]),
    "61_q6101750y_qin3lyhyt.png": (_vali(500, 0, 50, 0), 8, [
        "MHQ 803 m³/s NHQ 422", "10.05.1982 HQ 1390 m³/s",
        "MNQ 42.2 m³/s HNQ 87.1", "30.08.1969 NQ 26.0 m³/s", "18-Oct-2026 14:51 WSFS-O"]),
    "58_q5800000y_qinlyhyt.png": (_vali(40, 0, 5, 0), 8, ["18-Oct-2026 12:22 WSFS-O"]),
    "61_q6101400y_twlyhyt.png": (_vali(8, 1, 1, 0), 8, ["18-Oct-2026 14:51 WSFS-O"]),
    "58_q5800100y_w3lyhyt.png": (_vali(23.85, 23.40, 0.05, 2), 8, [
        "MHW 24.20 NHW 23.88", "HW 24.67 m 24.04.2000",
        "MNW 23.13 HNW 23.25", "NW 22.91 m 06.11.2000", "18-Oct-2026 12:22 WSFS-O"]),
    "51_q5100500y_wlyhyt.png": (_vali(26.0, 25.0, 0.1, 1), 8, [
        "MHW 26.63 NHW 25.87", "HW 27.42 m 24.04.2000",
        "MNW 24.64 HNW 24.92", "NW 24.46 m 13.09.1990", "18-Oct-2026 12:21 WSFS-O"]),
    "51_q5100500y_qinlyhyt.png": (_vali(45, 0, 5, 0), 8, [
        "MHQ 96.6 m³/s NHQ 39.0", "24.04.2000 HQ 190 m³/s",
        "MNQ 2.7 m³/s HNQ 4.8", "07.04.1996 NQ 1.3 m³/s", "18-Oct-2026 12:21 WSFS-O"]),
    "58_q5800100y_qinlyhyt.png": (_vali(10, 0, 1, 0), 8, [
        "MHQ 21.8 m³/s NHQ 12.2", "29.04.2012 HQ 34.5 m³/s",
        "MNQ 0.25 m³/s HNQ 0.70", "08.11.2000 NQ 0.00 m³/s", "18-Oct-2026 12:22 WSFS-O"]),
    "67_q6701500y_wlyhyt.png": (_vali(78.3, 77.2, 0.1, 1), 8, [
        "MHW 79.87 NHW 78.54", "HW 81.59 m 10.06.1968",
        "MNW 76.89 HNW 77.16", "NW 75.80 m 29.02.1952", "18-Oct-2026 14:48 WSFS-O"]),
    "60_q6000410y_wlyhyt.png": (_vali(10.9, 10.1, 0.1, 1), 8, [
        "MHW 11.59 NHW 10.90", "HW 12.33 m 29.04.2000",
        "MNW 9.65 HNW 9.89", "NW 9.40 m 30.08.1994", "18-Oct-2026 15:22 WSFS-O"]),
}


def kerää() -> dict[str, list[np.ndarray]]:
    lukija = sk.KaavioLukija(sk.Glyfitunnistin([]))
    naytteet: dict[str, list[np.ndarray]] = defaultdict(list)

    def lisaa(glyfit, teksti, kuvaus):
        merkit = teksti.replace(" ", "")
        if len(glyfit) != len(merkit):
            print(f"  ! {kuvaus}: {len(glyfit)} glyfiä, odotettiin {len(merkit)} ('{teksti}')")
            return False
        for g, c in zip(glyfit, merkit):
            naytteet[c].append(g.bitit)
        return True

    for nimi, (y_tikit, eka_paiva, selite) in TOTUUS.items():
        print(nimi)
        a = np.array(Image.open(FIXTURES / nimi).convert("RGB")).astype(np.int16)
        m = sk._maskit(a)
        k = sk.etsi_kehys(m)

        tikit = lukija.y_tikkien_glyfit(m["musta"], k)
        if len(tikit) != len(y_tikit):
            print(f"  ! y-tikkejä {len(tikit)}, odotettiin {len(y_tikit)}")
        else:
            for (ty, glyfit), teksti in zip(tikit, y_tikit):
                lisaa(glyfit, teksti, f"y-tikki {ty:.0f}")

        viivat, vali = sk.etsi_paivaviivat(m["musta"], k)
        for i, x in enumerate([k.vasen] + viivat):
            glyfit = lukija.x_akselin_glyfit(m["musta"], k, x, vali)
            lisaa(glyfit, str(eka_paiva + i), f"x-päivä {x}")

        rivit = lukija.selitteen_rivit(m["musta"], k)
        alku = 0
        for teksti in selite:
            merkit = teksti.replace(" ", "")
            # Rivin tunnistamiseksi pelkkä merkkimäärä ei riitä (esim.
            # "Havaintojen mediaani"); myös pienten merkkien ('.' ja '-')
            # paikkojen pitää täsmätä.
            odotettu = [c in ".-" for c in merkit]
            for j in range(alku, len(rivit)):
                if [g.korkeus <= 8 for g in rivit[j]] == odotettu:
                    lisaa(rivit[j], teksti, f"selite '{teksti}'")
                    alku = j + 1
                    break
            else:
                print(f"  ! selitteen riviä ei löytynyt: '{teksti}'")
    return naytteet


def main() -> None:
    naytteet = kerää()
    mallit = []
    for merkki, lista in sorted(naytteet.items()):
        uniikit: list[np.ndarray] = []
        for b in lista:
            if not any(u.shape == b.shape and (u == b).all() for u in uniikit):
                uniikit.append(b)
        # Tarkistus: saman merkin näytteiden pitää muistuttaa toisiaan
        for u in uniikit:
            ref = uniikit[0]
            if abs(u.shape[0] - ref.shape[0]) <= 2 and abs(u.shape[1] - ref.shape[1]) <= 2:
                ero = np.count_nonzero(sk._skaalaa(u, ref.shape[1], ref.shape[0]) != ref) / ref.size
                if ero > 0.12:
                    print(f"  ? merkin '{merkki}' näytteet poikkeavat ({ero:.2f})")
        mallit += [sk.koodaa(merkki, u) for u in uniikit]
        print(f"'{merkki}': {len(lista)} näytettä, {len(uniikit)} mallia")
    sk.GLYFIT_POLKU.write_text(json.dumps(mallit, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Kirjoitettu {len(mallit)} mallia -> {sk.GLYFIT_POLKU}")


if __name__ == "__main__":
    main()
