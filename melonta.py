#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.24"]
# ///
"""Melontapaikkojen päivän tilanne ja optimijärjestys (osm.fi + SYKE).

Hakee osm.fi:n melontapaikkojen sivut, lukee sivujen lopussa olevista
SYKE:n vedenkorkeus- ja virtaamakaavioista tämän päivän tilanteen ja
järjestää paikat sen mukaan, miten hyvin vesitilanne osuu kunkin paikan
optimiolosuhteisiin (ks. paikat.py ja README.md).

Käyttö (uv asentaa riippuvuudet automaattisesti, mistä hakemistosta tahansa):
    uv run melonta.py                 # päivän järjestys
    uv run melonta.py -v              # kaikki kohteet ja kaaviot
    uv run melonta.py --tyyppi peli --max-km 100
    uv run melonta.py --json > tilanne.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import arviointi
import osm_sivut as osm
import syke_data
from paikat import PAIKAT, Paikka, aseman_nimi
from syke_kaavio import KaavioLukija, Kaaviolukema, KaavioVirhe

HAKEMISTO = "https://www.osm.fi/melontapaikat/"
EI_PAIKKOJA = {"melontapaikat", "retki-ja-laskupatkat", "pelipaikat", "jokikuvaukset-muut"}

_lukija: KaavioLukija | None = None


def _lue_kaavio(tehtava: tuple[str, bytes]) -> tuple[str, Kaaviolukema | None, str | None]:
    """Prosessipoolissa ajettava: lukee yhden kaavion."""
    global _lukija
    avain, data = tehtava
    if _lukija is None:
        _lukija = KaavioLukija()
    try:
        return avain, _lukija.lue(data, url=osm.kaavio_url(avain)), None
    except (KaavioVirhe, OSError, ValueError) as e:
        return avain, None, f"{avain}: {e}"


def _lue_kaaviot(tehtavat: list[tuple[str, bytes]], prosessit: bool):
    """Lukee kaaviot prosessipoolissa tai, jos se ei ole mahdollista, peräkkäin.

    Palvelinympäristöissä (Vercel/AWS Lambda) ei ole /dev/shm:ää, joten
    ProcessPoolExecutor ei käynnisty; yhdellä vCPU:lla siitä ei olisi hyötyäkään.
    """
    if prosessit and len(tehtavat) > 1:
        try:
            with ProcessPoolExecutor() as pool:
                return list(pool.map(_lue_kaavio, tehtavat))
        except (OSError, NotImplementedError, PermissionError):
            pass
    return [_lue_kaavio(t) for t in tehtavat]


def kerää_tilanne(hakija: osm.Hakija, paikat: tuple[Paikka, ...], tarkista_hakemisto: bool = True,
                  prosessit: bool | None = None):
    """Hakee sivut ja kaaviot ja lukee kaaviot.

    prosessit=None: rinnakkaiset prosessit paitsi Vercelissä (VERCEL-ympäristömuuttuja).
    """
    if prosessit is None:
        prosessit = not os.environ.get("VERCEL")
    varoitukset: list[str] = []

    # 1. Paikkojen sivut ja niiden lopussa olevat kaaviot (verkko-odotusta, joten
    #    säikeitä saa olla paljon)
    with ThreadPoolExecutor(max_workers=24) as pool:
        sivut = list(zip(paikat, pool.map(lambda p: osm.hae_turvallisesti(hakija, p.url), paikat)))
    sivun_kaaviot: dict[str, list[str]] = {}   # paikan url -> sivun kaaviot
    for p, (data, virhe) in sivut:
        if virhe:
            varoitukset.append(f"Sivun haku epäonnistui: {virhe}")
            sivun_kaaviot[p.url] = []
            continue
        sivun_kaaviot[p.url] = osm.sivun_kaaviot(data.decode("utf-8", errors="replace"))
        for avain, mittari in p.mittarit.items():
            if not mittari.lisakaavio and mittari.kaavio not in sivun_kaaviot[p.url]:
                varoitukset.append(
                    f"{p.nimi}: sivulta ei enää löydy kaaviota {mittari.kaavio} "
                    f"(sivulla: {', '.join(sivun_kaaviot[p.url]) or 'ei kaavioita'}) – käytetään silti")

    # 2. Onko osm.fi:hin lisätty paikkoja, joita ei ole analysoitu?
    if tarkista_hakemisto:
        data, virhe = osm.hae_turvallisesti(hakija, HAKEMISTO)
        if data:
            tunnetut = {osm.normalisoi(p.url) for p in PAIKAT} | EI_PAIKKOJA
            for url in osm.melontapaikkojen_linkit(data.decode("utf-8", errors="replace")):
                if osm.normalisoi(url) not in tunnetut:
                    varoitukset.append(f"Uusi paikka osm.fi:ssä, ei vielä analysoitu: {url}")

    # 3. Kaikki tarvittavat kaaviot: pisteytykseen käytetyt + sivujen muut kaaviot
    tarvittavat: list[str] = []
    for p in paikat:
        for k in [m.kaavio for m in p.mittarit.values()] + sivun_kaaviot[p.url]:
            if k not in tarvittavat:
                tarvittavat.append(k)
    with ThreadPoolExecutor(max_workers=16) as pool:
        ladatut = list(pool.map(lambda k: (k, *osm.hae_turvallisesti(hakija, osm.kaavio_url(k))), tarvittavat))
    tehtavat = []
    for avain, data, virhe in ladatut:
        if virhe:
            kayttajat = [p.nimi for p in paikat if avain in sivun_kaaviot[p.url]
                         or avain in [m.kaavio for m in p.mittarit.values()]]
            varoitukset.append(f"Kaavion haku epäonnistui ({', '.join(kayttajat)}): {virhe}")
        else:
            tehtavat.append((avain, data))
    lukemat: dict[str, Kaaviolukema] = {}
    for avain, lukema, virhe in _lue_kaaviot(tehtavat, prosessit):
        if virhe:
            varoitukset.append(f"Kaavion tulkinta epäonnistui: {virhe}")
        else:
            lukemat[avain] = lukema

    # 4. Havainto, malli ja ennuste numeroina asemien ajo.json-tiedostoista.
    #    Jos tiedostoa ei saada, kuvasta luettu arvo jää voimaan.
    #    Arviomallien syöteasemat haetaan samalla.
    ajot = {a for a in map(syke_data.ajo_avain, lukemat) if a}
    for asema, malli in syke_data.ARVIOMALLIT.items():
        if f"{asema}/ajo.json" in ajot:
            ajot.update(malli.ajo_avaimet())
    ajot = sorted(ajot)
    with ThreadPoolExecutor(max_workers=16) as pool:
        ladatut = dict(zip(ajot, pool.map(lambda a: osm.hae_turvallisesti(hakija, osm.kaavio_url(a))[0], ajot)))
    luetut: dict[str, dict] = {}
    for a, data in ladatut.items():
        if not data:
            continue
        try:
            luetut[a] = syke_data.lue_ajo(data)
        except ValueError as e:
            varoitukset.append(f"{a}: ajo.json ei ole luettavissa ({e})")
    for avain, lukema in lukemat.items():
        ajo = luetut.get(syke_data.ajo_avain(avain))
        if not ajo:
            continue
        for virhe in (syke_data.taydenna(lukema, ajo), syke_data.arvioi_tanaan(lukema, luetut)):
            if virhe:
                varoitukset.append(virhe)
    return sivun_kaaviot, lukemat, varoitukset


def arvioi_kaikki(paikat, sivun_kaaviot, lukemat, paiva: dt.date | None):
    tulokset = []
    for p in paikat:
        omat = {avain: lukemat[m.kaavio] for avain, m in p.mittarit.items() if m.kaavio in lukemat}
        t = arviointi.arvioi(p, omat)
        if paiva:
            for avain, l in omat.items():
                if l.tanaan_paiva is not None and l.tanaan_paiva != paiva.day:
                    t.huomiot.append(
                        f"kaavio {p.mittarit[avain].kaavio} ei ole tältä päivältä "
                        f"(ennusteen alku {l.tanaan_paiva}. päivä)")
        t.sivun_kaaviot = [lukemat[k] for k in sivun_kaaviot.get(p.url, []) if k in lukemat]
        tulokset.append(t)
    return arviointi.jarjesta(tulokset)


# ---------------------------------------------------------------------------
# Tulostus
# ---------------------------------------------------------------------------

SUURE = {"vedenkorkeus": "vedenkorkeus", "virtaama": "virtaama", "lampotila": "veden lämpötila"}


def _luku(v: float | None, yksikko: str) -> str:
    if v is None:
        return "–"
    if yksikko == "m":
        return f"{v:.2f} m"
    if yksikko == "°C":
        return f"{v:.1f} °C"
    return f"{v:.1f} m³/s" if v < 20 else f"{v:.0f} m³/s"


def kuvaa_lukema(l: Kaaviolukema, ennustepaiva: int = 3) -> str:
    teksti = f"{aseman_nimi(osm.kaavio_avain(l.url) or '')} {SUURE.get(l.suure, l.suure)} " \
             f"{_luku(l.arvo, l.yksikko)} ({l.lahde})"
    tuleva = l.ennuste_korjattu(ennustepaiva)
    if tuleva is not None and l.arvo is not None:
        ero = tuleva - l.arvo
        kynnys = 0.02 if l.yksikko == "m" else max(0.5, 0.03 * abs(l.arvo))
        nuoli = "↗" if ero > kynnys else "↘" if ero < -kynnys else "→"
        teksti += f", {ennustepaiva} pv: {nuoli} {_luku(tuleva, l.yksikko)}"
    ti = l.tulvaindeksi
    if ti is not None:
        teksti += f", tulvaindeksi {ti:.2f}"
    return teksti


def _tila_merkki(tila: str) -> str:
    return {"paras": "★", "toimii": "✓", "ei toimi": "✗"}[tila]


def tulosta(tulokset, varoitukset, paiva: dt.date, laaja: bool) -> None:
    print(f"Melontapaikkojen tilanne {paiva:%d.%m.%Y} – osm.fi + SYKE:n vesistöennusteet")
    lampotilat = [l for t in tulokset for l in t.sivun_kaaviot if l.suure == "lampotila"]
    if lampotilat:
        l = lampotilat[0]
        print(f"Veden lämpötila ({aseman_nimi(osm.kaavio_avain(l.url))}): {_luku(l.arvo, '°C')}"
              + ("  – kylmää vettä, pukeudu uintia varten!" if l.arvo is not None and l.arvo < 10 else ""))
    print()

    arvioidut = [t for t in tulokset if t.pisteet is not None]
    for i, t in enumerate(arvioidut, 1):
        p = t.paikka
        km = f"~{p.km_oulusta} km" if p.km_oulusta is not None else ""
        ennuste = " / ".join(f"{t.ennuste[n]:.0f}" for n in sorted(t.ennuste))
        print(f"{i:2d}. {p.nimi:<40} {t.pisteet:5.0f}/100   {km:>8}   {p.tyyppi}")
        mittarit_nakyy = []
        for avain in p.mittarit:
            l = t.lukemat.get(avain)
            if l and l.url not in mittarit_nakyy:
                mittarit_nakyy.append(l.url)
                lisa = " [lisäkaavio]" if p.mittarit[avain].lisakaavio else ""
                print(f"      {kuvaa_lukema(l)}{lisa}")
        if ennuste:
            print(f"      pisteet lähipäivinä (+1/+2/+3 pv): {ennuste}")
        kohteet = sorted(t.kohteet, key=lambda k: k.pisteet, reverse=True)
        if not laaja:
            toimivat = [k for k in kohteet if k.tila != "ei toimi"]
            kohteet = toimivat[:3] if toimivat else kohteet[:1]
        for k in kohteet:
            huom = f" – {k.kohde.huom}" if laaja and k.kohde.huom else ""
            print(f"      {_tila_merkki(k.tila)} {k.kohde.nimi}: {k.selitys}{huom}")
        if laaja:
            muut = [l for l in t.sivun_kaaviot if l.url not in mittarit_nakyy]
            for l in muut:
                print(f"      (sivulla myös) {kuvaa_lukema(l)}")
        for h in t.huomiot:
            print(f"      ! {h}")
        print()

    ilman = [t for t in tulokset if t.pisteet is None]
    if ilman:
        print("Ei vesikaaviota sivulla – tarkista tilanne itse:")
        for t in ilman:
            print(f"    - {t.paikka.nimi}: {t.paikka.kuvaus}")
        print()
    if varoitukset:
        print("Huomautukset:")
        for v in varoitukset:
            print(f"    ! {v}")
        print()
    print("★ parhaimmillaan  ✓ toimii  ✗ ei toimi. Pisteet: veden määrä suhteessa paikan "
          "kuvauksen optimiin;\ntasapisteissä lähempi paikka ensin. Tarkista aina olosuhteet "
          "paikan päällä.")


def json_tulos(tulokset, varoitukset, paiva: dt.date) -> dict:
    def lukema_dict(l: Kaaviolukema) -> dict:
        return {
            "kaavio": l.url, "asema": aseman_nimi(osm.kaavio_avain(l.url) or ""), "suure": l.suure,
            "yksikko": l.yksikko, "arvo": l.arvo, "lahde": l.lahde, "malli": l.malli,
            "ennuste": {f"+{n}": l.ennuste_korjattu(n) for n in arviointi.ENNUSTEPAIVAT},
            "historia_min": l.hist_min, "historia_max": l.hist_max, "mediaani": l.mediaani,
            "tunnusluvut": l.tunnusluvut, "tulvaindeksi": l.tulvaindeksi,
            "ennusteen_alku_paiva": l.tanaan_paiva,
        }
    return {
        "paiva": paiva.isoformat(),
        "paikat": [{
            "sija": i, "nimi": t.paikka.nimi, "url": t.paikka.url, "tyyppi": t.paikka.tyyppi,
            "km_oulusta": t.paikka.km_oulusta, "pisteet": t.pisteet,
            "ennuste_pisteet": {f"+{n}": v for n, v in t.ennuste.items()},
            "kohteet": [{"nimi": k.kohde.nimi, "tila": k.tila, "pisteet": round(k.pisteet, 1),
                         "selitys": k.selitys, "arvo": k.arvo, "muuttuja": k.kohde.muuttuja,
                         "toimii": k.kohde.toimii, "paras": k.kohde.paras, "lahde": k.kohde.lahde}
                        for k in t.kohteet],
            "mittarit": {a: lukema_dict(l) for a, l in t.lukemat.items()},
            "huomiot": t.huomiot,
        } for i, t in enumerate(tulokset, 1)],
        "varoitukset": varoitukset,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Melontapaikkojen päivän tilanne ja optimijärjestys (osm.fi).")
    ap.add_argument("-v", "--kaikki", action="store_true", help="näytä kaikki kohteet ja sivujen kaaviot")
    ap.add_argument("--tyyppi", choices=["peli", "retki"], help="vain pelipaikat tai retkipätkät")
    ap.add_argument("--max-km", type=int, help="vain paikat enintään näin kaukana Oulusta")
    ap.add_argument("--json", action="store_true", help="tulosta JSON-muodossa")
    ap.add_argument("--tallenna", type=Path, metavar="KANSIO", help="tallenna haetut sivut ja kuvat kansioon")
    ap.add_argument("--offline", type=Path, metavar="KANSIO", help="käytä --tallenna-kansion aineistoa verkon sijaan")
    ap.add_argument("--paiva", type=dt.date.fromisoformat, metavar="VVVV-KK-PP",
                    help="päivä, jolta kaavioiden pitäisi olla (oletus tänään)")
    args = ap.parse_args(argv)

    paikat = tuple(p for p in PAIKAT
                   if (not args.tyyppi or p.tyyppi == args.tyyppi)
                   and (args.max_km is None or (p.km_oulusta or 0) <= args.max_km))
    paiva = args.paiva or dt.date.today()
    hakija = osm.Hakija(offline=args.offline, tallenna=args.tallenna)

    sivun_kaaviot, lukemat, varoitukset = kerää_tilanne(hakija, paikat)
    tulokset = arvioi_kaikki(paikat, sivun_kaaviot, lukemat, paiva)

    if args.json:
        json.dump(json_tulos(tulokset, varoitukset, paiva), sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        tulosta(tulokset, varoitukset, paiva, args.kaikki)
    return 0 if lukemat else 1


if __name__ == "__main__":
    sys.exit(main())
