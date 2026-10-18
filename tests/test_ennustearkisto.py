import datetime as dt
import importlib.util
import json
import math
from pathlib import Path

import pytest

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
    arkisto = arkistoi.kokoa(ajot(), ARKISTOITU)
    assert set(arkisto["asemat"]) == set(arkistoi.ASEMAT)
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
    arvio = arkistoi.kokoa(a, ARKISTOITU)["arviot"]["61/q6101750y"]
    t = dt.date(2026, 10, 18)
    odotettu = -5.423 + 1.078 * syke_data.syotteen_arvo(a["61/q6101452y/ajo.json"], t) \
        + 0.911 * syke_data.syotteen_arvo(a["61/q6101600y/ajo.json"], t)
    assert arvio["lahde"] == "arvio Pahkakoski + Siurua" and arvio["varoitukset"] == []
    assert arvio["tanaan"] == pytest.approx(odotettu, abs=1e-3)
    ka = arkistoi.kokoa(a, ARKISTOITU)["asemat"]["61/q6101750y"]["qinlask_ka"]
    assert len(arvio["ennuste"]) == 7
    assert arvio["ennuste"]["2026-10-19"] == pytest.approx(
        odotettu + ka["2026-10-19"] - ka["2026-10-18"], abs=1e-3)


def test_puuttuva_asema():
    a = ajot()
    del a["61/q6101600y/ajo.json"]
    arkisto = arkistoi.kokoa(a, ARKISTOITU, {"61/q6101600y": "HTTP 404"})
    assert arkisto["asemat"]["61/q6101600y"] == {"nimi": "Siurua", "virhe": "HTTP 404"}
    assert "virhe" not in arkisto["asemat"]["61/q6101452y"]
    arvio = arkisto["arviot"]["61/q6101750y"]   # sovellus käyttää silloin eilistä havaintoa
    assert arvio["tanaan"] == 398.97 and arvio["lahde"] == "havainto 1 pv sitten, SYKE-data"
    assert arvio["varoitukset"] and "puuttuu" in arvio["varoitukset"][0]


def test_main_tallentaa_eika_korvaa(tmp_path, monkeypatch):
    monkeypatch.setattr(arkistoi, "hae_ajot", lambda: (ajot(), {}))
    assert arkistoi.main(["--kansio", str(tmp_path)]) == 0
    [polku] = tmp_path.glob("*.json")
    assert json.loads(polku.read_text(encoding="utf-8"))["asemat"]["61/q6101210y"]["nimi"] == "Livojoki"
    polku.write_text("{}", encoding="utf-8")
    assert arkistoi.main(["--kansio", str(tmp_path)]) == 0
    assert polku.read_text(encoding="utf-8") == "{}"
    assert arkistoi.main(["--kansio", str(tmp_path), "--korvaa"]) == 0
    assert polku.read_text(encoding="utf-8") != "{}"


def test_main_ei_tallenna_tyhjaa(tmp_path, monkeypatch):
    monkeypatch.setattr(arkistoi, "hae_ajot", lambda: ({}, {"61/q6101750y": "aikakatkaisu"}))
    assert arkistoi.main(["--kansio", str(tmp_path)]) == 1
    assert not list(tmp_path.glob("*.json"))


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
