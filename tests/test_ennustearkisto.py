import datetime as dt
import importlib.util
import json
import math
from pathlib import Path

import pytest

import ennustearkisto
import syke_data

JUURI = Path(__file__).resolve().parent.parent
AJOT = Path(__file__).parent / "fixtures" / "ajo"


def _tuo(nimi):
    spec = importlib.util.spec_from_file_location(nimi, JUURI / "tyokalut" / f"{nimi}.py")
    moduuli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(moduuli)
    return moduuli


arkistoi = _tuo("arkistoi_ennusteet")
vertaa = _tuo("vertaa_ennusteet")

ARKISTOITU = dt.datetime(2026, 10, 18, 20, 0, tzinfo=dt.timezone.utc)


def ajot():
    """Oikeat ajo.jsonit 18.10.2026, rajattu ±10 päivään ennusteen alusta."""
    return {p.name.replace("_ajo.json", "").replace("_", "/", 1) + "/ajo.json": json.loads(p.read_text())
            for p in AJOT.glob("*_ajo.json")}


def test_kokoaa_asemat_fixtureista():
    arkisto = ennustearkisto.kokoa(ajot(), ARKISTOITU)
    assert set(arkisto["asemat"]) == set(ennustearkisto.ASEMAT)
    m = arkisto["asemat"]["61/q6101750y"]
    assert m["nimi"] == "Maalismaa" and m["ennustepvm_www"] == "2026-10-18"
    ennustepaivat = [f"2026-10-{d}" for d in range(18, 26)]
    for sarja in ("qinlask_5", "qinlask_95"):
        assert list(m[sarja]) == ennustepaivat
    assert list(m["qinlask_ka"]) == [f"2026-10-{d}" for d in range(11, 26)]
    # Maalismaan havainto julkaistaan vasta seuraavana päivänä
    assert list(m["qhav"]) == [f"2026-10-{d}" for d in range(12, 18)]
    assert m["qhav"]["2026-10-17"] == 398.97
    assert all(isinstance(v, float) for v in m["qhav"].values())


def test_oma_arvio_kuten_sovelluksessa():
    a = ajot()
    arvio = ennustearkisto.kokoa(a, ARKISTOITU)["arviot"]["61/q6101750y"]
    # Siurua 18.10. 66.8 / 17.10. 67.3, Pudasjärvi 108.59 / 108.56 / 108.56 m, Maalismaa 17.10. 398.97
    k = syke_data.ARVIOMALLIT["61/q6101750y"].pieni
    kaava = lambda q, h, h1: (k.vakio + k.virtaama * q + k.kuutio * (((h + h1) / 2 - 10590) / 100) ** 3
                              + k.muutos * (h - h1))
    odotettu = kaava(66.8, 10859, 10856) + k.alfa * (398.97 - kaava(67.3, 10856, 10856))
    assert arvio["lahde"] == "arvio Pudasjärvi + Siurua, eilinen korjaus" and arvio["varoitukset"] == []
    assert arvio["tanaan"] == pytest.approx(odotettu, abs=1e-3)
    ka = ennustearkisto.kokoa(a, ARKISTOITU)["asemat"]["61/q6101750y"]["qinlask_ka"]
    assert len(arvio["ennuste"]) == 7
    assert arvio["ennuste"]["2026-10-19"] == pytest.approx(
        odotettu + ka["2026-10-19"] - ka["2026-10-18"], abs=1e-3)


def test_tuntimittaukset_ja_tuntiarviot():
    """Syöteasemien tuntimittaukset (edellinen ja kuluva päivä) ja Maalismaan päivän tuntiarviot."""
    a = ajot()
    perus = {"61/q6101600y": 66.8, "61/q6100700y": 120.0, "61/q6101210y": 40.0, "61/l611331001y": 108.59}
    for asema, v in perus.items():
        a[f"{asema}/reaaliaika_tunnit"] = {f"2026-10-{d}T{t:02d}": v for d in (16, 17, 18) for t in range(24)
                                           if (d, t) <= (18, 15)}
    arkisto = ennustearkisto.kokoa(a, ARKISTOITU)
    s = arkisto["syotteet"]
    assert set(s) == set(ennustearkisto.SYOTEASEMAT)
    siurua = s["61/q6101600y"]["tunnit"]
    assert min(siurua) == "2026-10-17T00" and max(siurua) == "2026-10-18T15" and len(siurua) == 24 + 16
    pudas = s["61/l611331001y"]
    assert pudas["nimi"] == "Pudasjärvi (vedenkorkeus)" and pudas["whav"]["2026-10-18"] == 108.59
    assert "2026-10-25" in pudas["wlask_ka"] and "whav" not in s["61/q6101600y"]
    tunnit = arkisto["arviot"]["61/q6101750y"]["tunnit"]
    assert tunnit["paiva"] == "2026-10-18" and tunnit["viim"] == 15
    assert list(tunnit["arviot"]) == [f"{t:02d}" for t in range(16)]
    assert list(tunnit["ennuste"]) == [f"{t:02d}" for t in range(15, 24)]
    assert tunnit["keskiarvo"] == pytest.approx(
        syke_data.tuntiarviot("61/q6101750y", a, dt.date(2026, 10, 18))["keskiarvo"], abs=1e-3)
    # ilman reaaliaikadataa: tyhjät tuntisarjat, ei tuntiarviota
    ilman = ennustearkisto.kokoa(ajot(), ARKISTOITU)
    assert ilman["syotteet"]["61/q6101600y"]["tunnit"] == {} and "tunnit" not in ilman["arviot"]["61/q6101750y"]


def test_puuttuva_asema():
    a = ajot()
    del a["61/q6101600y/ajo.json"]
    arkisto = ennustearkisto.kokoa(a, ARKISTOITU, {"61/q6101600y": "HTTP 404"})
    assert arkisto["asemat"]["61/q6101600y"] == {"nimi": "Siurua", "virhe": "HTTP 404"}
    assert "virhe" not in arkisto["asemat"]["61/q6101452y"]   # Pahkakoski arkistoidaan yhä
    arvio = arkisto["arviot"]["61/q6101750y"]   # sovellus käyttää silloin eilistä havaintoa
    assert arvio["tanaan"] == 398.97 and arvio["lahde"] == "havainto 1 pv sitten, SYKE-data"
    assert arvio["varoitukset"] and "puuttuu" in arvio["varoitukset"][0]


def test_main_tallentaa_eika_korvaa(tmp_path, monkeypatch):
    monkeypatch.setattr(ennustearkisto, "hae_ajot", lambda: (ajot(), {}))
    assert arkistoi.main(["--kansio", str(tmp_path)]) == 0
    [polku] = tmp_path.glob("*.json")
    assert json.loads(polku.read_text(encoding="utf-8"))["asemat"]["61/q6101210y"]["nimi"] == "Livojoki"
    polku.write_text("{}", encoding="utf-8")
    assert arkistoi.main(["--kansio", str(tmp_path)]) == 0
    assert polku.read_text(encoding="utf-8") == "{}"
    assert arkistoi.main(["--kansio", str(tmp_path), "--korvaa"]) == 0
    assert polku.read_text(encoding="utf-8") != "{}"


def test_main_ei_tallenna_tyhjaa(tmp_path, monkeypatch):
    monkeypatch.setattr(ennustearkisto, "hae_ajot", lambda: ({}, {"61/q6101750y": "aikakatkaisu"}))
    assert arkistoi.main(["--kansio", str(tmp_path)]) == 1
    assert not list(tmp_path.glob("*.json"))


class Kanta:
    projekti = "testi"

    def __init__(self):
        self.dokumentit = {}

    def lue(self, kokoelma, tunniste):
        return self.dokumentit.get((kokoelma, tunniste))

    def kirjoita(self, kokoelma, tunniste, data):
        self.dokumentit[kokoelma, tunniste] = data

    def listaa(self, kokoelma):
        return {t: d for (k, t), d in self.dokumentit.items() if k == kokoelma}


def test_main_firestoreen(tmp_path, monkeypatch):
    kanta = Kanta()
    monkeypatch.setattr(ennustearkisto, "hae_ajot", lambda: (ajot(), {}))
    monkeypatch.setattr(arkistoi.firestore.Firestore, "ymparistosta", classmethod(lambda cls: kanta))
    assert arkistoi.main(["--firestore", "--kansio", str(tmp_path)]) == 0
    [(kokoelma, _)] = kanta.dokumentit
    assert kokoelma == "ennusteet" and not list(tmp_path.glob("*.json"))
    monkeypatch.setattr(ennustearkisto, "hae_ajot", lambda: pytest.fail("haettiin uudelleen"))
    assert arkistoi.main(["--firestore"]) == 0   # päivä on jo arkistoitu

    # vertailu lukee saman kokoelman
    monkeypatch.setattr(vertaa.firestore.Firestore, "ymparistosta", classmethod(lambda cls: kanta))
    assert vertaa.main(["--firestore", "--json"]) == 0


def test_main_firestore_ilman_tunnusta(monkeypatch):
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT", raising=False)
    assert arkistoi.main(["--firestore"]) == 2
    assert vertaa.main(["--firestore"]) == 2


# ---------------------------------------------------------------------------
# vertaa_ennusteet
# ---------------------------------------------------------------------------

def _arkisto(paiva, qhav, ka=None, ala=None, yla=None, oma=None):
    tieto = {"nimi": "Testi", "ennustepvm_www": paiva, "qhav": qhav, "qinlask_ka": ka or {},
             "qinlask_5": ala or {}, "qinlask_95": yla or {}}
    arviot = {"61/x": {"ennustepvm_www": paiva, "ennuste": oma}} if oma else {}
    return {"arkistoitu": paiva + "T20:00:00+03:00", "asemat": {"61/x": tieto}, "arviot": arviot}


def arkistot():
    return [
        _arkisto("2026-10-18", {"2026-10-17": 100.0},
                 ka={"2026-10-17": 90.0, "2026-10-18": 110.0, "2026-10-19": 120.0, "2026-10-20": 130.0},
                 ala={"2026-10-19": 115.0, "2026-10-20": 126.0},
                 yla={"2026-10-19": 125.0, "2026-10-20": 128.0},
                 oma={"2026-10-19": 117.0}),
        _arkisto("2026-10-19", {"2026-10-18": 105.0, "2026-10-19": 118.0}),
        # SYKE tarkensi 19.10. havaintoa: uusin arvo voittaa
        _arkisto("2026-10-20", {"2026-10-19": 119.0, "2026-10-20": 125.0}),
    ]


def _rivi(rivit, n, menetelma):
    [r] = [r for r in rivit if r["paivia"] == n and r["menetelma"] == menetelma]
    return r


def test_virheet_ja_pysyvyys():
    rivit = vertaa.vertaa(arkistot())
    r = _rivi(rivit, 1, "SYKE")
    assert (r["n"], r["harha"], r["rmse"], r["vali_osui"]) == (1, 1.0, 1.0, 1.0)
    assert _rivi(rivit, 2, "SYKE")["harha"] == 5.0
    assert _rivi(rivit, 2, "SYKE")["vali_osui"] == 0.0           # 125 < 126
    assert _rivi(rivit, 1, "SYKE+muutos")["harha"] == 100 + 120 - 90 - 119
    assert _rivi(rivit, 1, "sovellus")["harha"] == -2.0
    # pysyvyys: +1 pv 18.10. (100 -> 119) ja 19.10. (118 -> 125)
    p = _rivi(rivit, 1, "pysyvyys")
    assert p["n"] == 2 and p["harha"] == pytest.approx((-19 - 7) / 2)
    assert p["rmse"] == pytest.approx(math.sqrt((19 ** 2 + 7 ** 2) / 2))
    assert not [r for r in rivit if r["paivia"] == 3]


def test_sama_ennuste_kahdesti_lasketaan_kerran():
    kopio = _arkisto("2026-10-18", {"2026-10-17": 100.0}, ka={"2026-10-19": 121.0})
    kopio["arkistoitu"] = "2026-10-18T23:00:00+03:00"
    rivit = vertaa.vertaa(arkistot() + [kopio])
    r = _rivi(rivit, 1, "SYKE")
    assert r["n"] == 1 and r["harha"] == 2.0


def test_main_kansiosta(tmp_path, capsys):
    for a in arkistot():
        (tmp_path / f"{a['asemat']['61/x']['ennustepvm_www']}.json").write_text(json.dumps(a), encoding="utf-8")
    (tmp_path / "rikki.json").write_text("{", encoding="utf-8")
    assert vertaa.main(["--kansio", str(tmp_path), "--json"]) == 0
    rivit = json.loads(capsys.readouterr().out)
    assert _rivi(rivit, 1, "SYKE")["rmse"] == 1.0
    assert vertaa.main(["--kansio", str(tmp_path)]) == 0
    tulos = capsys.readouterr().out
    assert "Testi (61/x)" in tulos and "pysyvyys" in tulos


def test_tyhja_arkisto(tmp_path, capsys):
    assert vertaa.main(["--kansio", str(tmp_path)]) == 0
    assert "Ei vielä" in capsys.readouterr().out
