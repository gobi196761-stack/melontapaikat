"""Ehdotuksen täydennyksen työkalu Claude Codelle (GitHub Actions, ohje tyokalut/TAYDENNYS.md).

Käsittelee vain ympäristömuuttujan TUNNISTE nimeämää ehdotusta. Firestore-tunnus
ympäristömuuttujassa FIREBASE_SERVICE_ACCOUNT.

    uv run python tyokalut/taydenna_ehdotus.py lue
    uv run python tyokalut/taydenna_ehdotus.py asemat 66.36 29.05 [--suure virtaama|vedenkorkeus] [--n 10]
    uv run python tyokalut/taydenna_ehdotus.py vesi 7300100 2010-05-10 [2010-05-20] [--suure ...]
    uv run python tyokalut/taydenna_ehdotus.py huiput 7300100 [--suure ...]
    uv run python tyokalut/taydenna_ehdotus.py tunnusluvut 73/q7300100y/qinlyhyt.png
    uv run python tyokalut/taydenna_ehdotus.py paikka "Ollilanjärvi Kuusamo"
    uv run python tyokalut/taydenna_ehdotus.py tallenna taydennys.json
    uv run python tyokalut/taydenna_ehdotus.py virhe "syy"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ehdotukset  # noqa: E402
import firestore  # noqa: E402

SYKE = "https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata"
I2 = "https://wwwi2.ymparisto.fi/i2"
TUOTANTO = os.environ.get("MELONTA_OSOITE", "https://melontapaikat.vercel.app")
SUUREET = {"virtaama": (2, "Virtaama", "q", "qinlyhyt.png", "m³/s"),
           "vedenkorkeus": (1, "Vedenkorkeus", "w", "wlyhyt.png", "cm")}
VALIMUISTI = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "syke_paikat.json"


def _hae_json(url: str, aikaraja: float = 60):
    pyynto = urllib.request.Request(url, headers={"User-Agent": "melontapaikat-taydennys"})
    with urllib.request.urlopen(pyynto, timeout=aikaraja) as v:
        return json.loads(v.read().decode("utf-8"))


def _tunniste() -> str:
    tunniste = os.environ.get("TUNNISTE", "")
    if not ehdotukset.kelvollinen_tunniste(tunniste):
        sys.exit("TUNNISTE puuttuu tai on virheellinen")
    return tunniste


def _kanta():
    kanta = firestore.Firestore.ymparistosta()
    if not kanta:
        sys.exit("FIREBASE_SERVICE_ACCOUNT puuttuu")
    return kanta


def _dms(s: str) -> float:
    s = str(s).zfill(6)
    return int(s[:-4]) + int(s[-4:-2]) / 60 + int(s[-2:]) / 3600


def _etaisyys(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _paikat() -> list[dict]:
    if VALIMUISTI.exists():
        return json.loads(VALIMUISTI.read_text(encoding="utf-8"))
    kentat = "Paikka_Id,Nimi,Nro,KoordLat,KoordLong,Suure_Id,Tila_Id,KuntaNimi,PaaVesalNimi"
    paikat = []
    while True:   # rajapinta palauttaa rajallisen määrän rivejä kerrallaan (500)
        rivit = _hae_json(f"{SYKE}/Paikka?$select={kentat}&$orderby=Paikka_Id&$skip={len(paikat)}", 120).get("value", [])
        if not rivit:
            break
        paikat += rivit
    VALIMUISTI.write_text(json.dumps(paikat, ensure_ascii=False), encoding="utf-8")
    return paikat


def _kaavio(nro: str, suure: str) -> str:
    _, _, kirjain, tiedosto, _ = SUUREET[suure]
    return f"{nro[:2]}/{kirjain}{nro}y/{tiedosto}"


def _ennuste_olemassa(nro: str, suure: str) -> bool:
    kirjain = SUUREET[suure][2]
    try:
        _hae_json(f"{I2}/{nro[:2]}/{kirjain}{nro}y/ajo.json", 20)
        return True
    except (OSError, ValueError):
        return False


def _paikka_id(nro: str, suure: str) -> int:
    suure_id = SUUREET[suure][0]
    osumat = [p for p in _paikat() if p.get("Nro") == nro and p.get("Suure_Id") == suure_id]
    if not osumat:
        sys.exit(f"asemaa {nro} ({suure}) ei löydy")
    return osumat[0]["Paikka_Id"]


def lue(_):
    tunniste = _tunniste()
    ehdotus = _kanta().lue(ehdotukset.KOKOELMA, tunniste)
    if not ehdotus:
        sys.exit("ehdotusta ei löydy")
    ehdotus.pop("tilaus", None)
    if ehdotus.get("laji") == "taydenna":
        import paikkasivut
        from paikat import PAIKAT
        p = next((p for p in PAIKAT if p.nimi == ehdotus.get("paikka")), None)
        if p:
            ehdotus["olemassa_oleva_paikka"] = {
                "mittarit": {a: m.kaavio for a, m in p.mittarit.items()},
                "kohteet": [{"nimi": k.nimi, "toimii": k.toimii, "paras": k.paras, "mittari": k.mittari,
                             "huom": k.huom} for k in p.kohteet],
                "kuvaus": getattr(paikkasivut.KUVAUKSET.get(p.nimi), "johdanto", p.kuvaus)}
    print(json.dumps(ehdotus, ensure_ascii=False, indent=1))


def asemat(a):
    piste = (a.lev, a.pit)
    rivit = []
    for p in _paikat():
        if p.get("Suure_Id") != SUUREET[a.suure][0] or not p.get("KoordLat"):
            continue
        try:
            d = _etaisyys(piste, (_dms(p["KoordLat"]), _dms(p["KoordLong"])))
        except (ValueError, TypeError):
            continue
        rivit.append((d, p))
    rivit.sort(key=lambda x: x[0])
    for d, p in rivit[:a.n]:
        ennuste = _ennuste_olemassa(p["Nro"], a.suure)
        print(f"{d:6.1f} km  {p['Nro']}  {p['Nimi']}  ({p.get('KuntaNimi')}, {p.get('PaaVesalNimi')})  "
              f"{'aktiivinen' if p.get('Tila_Id') == 1 else 'ei aktiivinen'}  "
              + (f"ennuste: kyllä, mittari {_kaavio(p['Nro'], a.suure)}" if ennuste else "ennuste: ei"))


def vesi(a):
    _, taulu, _, _, yksikko = SUUREET[a.suure]
    pid = _paikka_id(a.nro, a.suure)
    loppu = a.loppu or a.alku
    url = (f"{SYKE}/{taulu}?$filter=Paikka_Id%20eq%20{pid}%20and%20Aika%20ge%20datetime'{a.alku}T00:00:00'"
           f"%20and%20Aika%20le%20datetime'{loppu}T00:00:00'&$orderby=Aika&$top=400")
    for r in _hae_json(url).get("value", []):
        print(f"{r['Aika'][:10]}  {float(r['Arvo']):g} {yksikko}")


def huiput(a):
    _, taulu, _, _, yksikko = SUUREET[a.suure]
    pid = _paikka_id(a.nro, a.suure)
    url = f"{SYKE}/{taulu}?$filter=Paikka_Id%20eq%20{pid}&$orderby=Arvo%20desc&$top=1000&$select=Aika,Arvo"
    vuodet: dict[str, tuple[str, float]] = {}
    for r in _hae_json(url, 120).get("value", []):
        v = r["Aika"][:4]
        if v not in vuodet:
            vuodet[v] = (r["Aika"][:10], float(r["Arvo"]))
    print("Suurimmat vuosihuiput (päivä, arvo):")
    for v, (paiva, arvo) in sorted(vuodet.items(), key=lambda x: -x[1][1])[:25]:
        print(f"  {paiva}  {arvo:g} {yksikko}")


def tunnusluvut(a):
    import syke_kaavio
    pyynto = urllib.request.Request(f"{I2}/{a.kaavio}", headers={"User-Agent": "melontapaikat-taydennys"})
    with urllib.request.urlopen(pyynto, timeout=60) as v:
        data = v.read()
    try:
        print(json.dumps(syke_kaavio.KaavioLukija().lue(data, url=a.kaavio).tunnusluvut, ensure_ascii=False))
    except syke_kaavio.KaavioVirhe as e:
        print(f"kaaviota ei voitu lukea: {e}")


def paikka(a):
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode(
        {"q": a.teksti, "limit": 6, "lat": 65.0, "lon": 26.0})
    for f in _hae_json(url).get("features", []):
        p, (pit, lev) = f["properties"], f["geometry"]["coordinates"]
        print(f"{lev:.5f}, {pit:.5f}  {p.get('name')}  ({p.get('osm_value')}, "
              f"{p.get('city') or p.get('county') or ''}, {p.get('country')})")


def tallenna(a):
    tunniste = _tunniste()
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste)
    if not ehdotus:
        sys.exit("ehdotusta ei löydy")
    taydennys, virhe = ehdotukset.tarkista_taydennys(json.loads(Path(a.tiedosto).read_text(encoding="utf-8")),
                                                     ehdotus.get("yksityiset_linkit") or [])
    if not taydennys:
        sys.exit(f"täydennys ei kelpaa: {virhe}")
    vanha = ehdotus.get("taydennys") or {}
    ehdotus["taydennys"] = {**taydennys, "tila": "valmis", "pyydetty": vanha.get("pyydetty"),
                            "aika": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    try:   # tuotanto lähettää ilmoitukset ylläpitäjälle ja ehdottajalle
        pyynto = urllib.request.Request(f"{TUOTANTO}/api/ehdotus/{tunniste}/taydennys-valmis", data=b"",
                                        method="POST", headers={"User-Agent": "melontapaikat-taydennys"})
        with urllib.request.urlopen(pyynto, timeout=60) as v:
            print("ilmoitus:", v.read().decode("utf-8"))
    except OSError as e:
        print(f"ilmoitusta ei saatu lähetettyä: {e}")
    print(f"Tallennettu. Esikatselu: {TUOTANTO}/ehdotus/{tunniste}")


def virhe(a):
    tunniste = _tunniste()
    kanta = _kanta()
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste)
    if not ehdotus:
        sys.exit("ehdotusta ei löydy")
    ehdotus["taydennys"] = {**(ehdotus.get("taydennys") or {}), "tila": "virhe", "virhe": a.syy[:500]}
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    print("Virhe tallennettu.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ali = p.add_subparsers(dest="komento", required=True)
    ali.add_parser("lue").set_defaults(f=lue)
    s = ali.add_parser("asemat")
    s.add_argument("lev", type=float)
    s.add_argument("pit", type=float)
    s.add_argument("--suure", choices=SUUREET, default="virtaama")
    s.add_argument("--n", type=int, default=10)
    s.set_defaults(f=asemat)
    s = ali.add_parser("vesi")
    s.add_argument("nro")
    s.add_argument("alku", type=dt.date.fromisoformat)
    s.add_argument("loppu", nargs="?", type=dt.date.fromisoformat)
    s.add_argument("--suure", choices=SUUREET, default="virtaama")
    s.set_defaults(f=vesi)
    s = ali.add_parser("huiput")
    s.add_argument("nro")
    s.add_argument("--suure", choices=SUUREET, default="virtaama")
    s.set_defaults(f=huiput)
    s = ali.add_parser("tunnusluvut")
    s.add_argument("kaavio")
    s.set_defaults(f=tunnusluvut)
    s = ali.add_parser("paikka")
    s.add_argument("teksti")
    s.set_defaults(f=paikka)
    s = ali.add_parser("tallenna")
    s.add_argument("tiedosto")
    s.set_defaults(f=tallenna)
    s = ali.add_parser("virhe")
    s.add_argument("syy")
    s.set_defaults(f=virhe)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
