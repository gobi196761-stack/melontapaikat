import datetime as dt
import io
import json
import shutil
from pathlib import Path

import pytest

import app
import melonta
import osm_sivut as osm
from paikat import PAIKAT

FIXTURES = Path(__file__).parent / "fixtures"
PAIVA = dt.datetime(2026, 10, 18, 16, 5)


@pytest.fixture(scope="module")
def aineisto(tmp_path_factory):
    """Kipinä, Matkakoski ja Niskakoski tallennetusta aineistosta, ilman verkkoa."""
    valimuisti = tmp_path_factory.mktemp("aineisto")
    paikat = tuple(p for p in PAIKAT if osm.normalisoi(p.url) in ("kipinae", "matkakoski", "niskakoski"))
    for p in paikat:
        shutil.copy(FIXTURES / "sivut" / f"{osm.normalisoi(p.url)}.html",
                    valimuisti / osm.Hakija._tiedostonimi(p.url))
    for kuva in FIXTURES.glob("*.png"):
        shutil.copy(kuva, valimuisti / osm.Hakija._tiedostonimi(osm.kaavio_url(kuva.name.replace("_", "/", 2))))
    return osm.Hakija(offline=valimuisti), paikat


@pytest.fixture(scope="module")
def tilanne(aineisto):
    hakija, paikat = aineisto
    sivun_kaaviot, lukemat, varoitukset = melonta.kerää_tilanne(
        hakija, paikat, tarkista_hakemisto=False, prosessit=False)
    tulokset = melonta.arvioi_kaikki(paikat, sivun_kaaviot, lukemat, PAIVA.date())
    return app.Tilanne(PAIVA, tulokset, varoitukset, len(lukemat))


def pyynto(polku, kysely="", metodi="GET"):
    vastaus = {}

    def start_response(status, otsakkeet):
        vastaus["status"] = status
        vastaus["otsakkeet"] = dict(otsakkeet)

    runko = b"".join(app.app({"PATH_INFO": polku, "QUERY_STRING": kysely, "REQUEST_METHOD": metodi,
                              "wsgi.input": io.BytesIO()}, start_response))
    return vastaus["status"], vastaus["otsakkeet"], runko.decode("utf-8")


@pytest.fixture
def palvelin(monkeypatch, tilanne):
    monkeypatch.setattr(app, "hae_tilanne", lambda: tilanne)


def test_sivu(palvelin):
    status, otsakkeet, runko = pyynto("/")
    assert status == "200 OK"
    assert otsakkeet["Content-Type"].startswith("text/html")
    assert "s-maxage=" in otsakkeet["Cache-Control"]
    assert runko.index("Kipinä (Iijoki)") < runko.index("Matkakoski") < runko.index("Niskakoski")
    assert "Oikean silta-aukon surffiaalto" in runko
    assert "Veden lämpötila" in runko and "2.8 °C" in runko
    assert "päivitetty klo 16.05" in runko


def test_api_ja_suodatus(palvelin):
    status, otsakkeet, runko = pyynto("/api")
    assert status == "200 OK" and otsakkeet["Content-Type"].startswith("application/json")
    data = json.loads(runko)
    assert data["paiva"] == "2026-10-18"
    assert data["paivitetty"] == "2026-10-18T16:05:00"
    assert [p["nimi"] for p in data["paikat"]] == [
        "Kipinä (Iijoki)", "Matkakoski (Tornionjoki)", "Niskakoski (Lestijoki)"]
    assert data["paikat"][0]["pisteet"] == pytest.approx(80)

    data = json.loads(pyynto("/api/", "max_km=150")[2])
    assert all(p["km_oulusta"] <= 150 for p in data["paikat"])
    assert [p["sija"] for p in data["paikat"]] == list(range(1, len(data["paikat"]) + 1))
    assert json.loads(pyynto("/api", "max_km=abc")[2])["paikat"]  # virheellinen suodatin ohitetaan


def test_tuntemattomat_pyynnot(palvelin):
    assert pyynto("/favicon.ico")[0].startswith("404")
    assert pyynto("/", metodi="POST")[0].startswith("405")
    status, otsakkeet, runko = pyynto("/", metodi="HEAD")
    assert status == "200 OK" and runko == "" and int(otsakkeet["Content-Length"]) > 0


def test_epaonnistunut_haku_ei_jaa_valimuistiin(monkeypatch):
    kutsut = []

    def kerää(hakija, paikat, **kw):
        kutsut.append(1)
        return {}, {}, ["verkko alhaalla"]

    monkeypatch.setattr(app, "_tilanne", None)
    monkeypatch.setattr(melonta, "kerää_tilanne", kerää)
    status, otsakkeet, runko = pyynto("/")
    assert status.startswith("503") and otsakkeet["Cache-Control"] == "no-store"
    assert "verkko alhaalla" in runko
    pyynto("/")
    assert len(kutsut) == 2


def test_onnistunut_tulos_pidetaan_muistissa(monkeypatch, tilanne):
    kutsut = []

    def kerää(hakija, paikat, **kw):
        kutsut.append(1)
        return {}, {"x": object()}, []

    monkeypatch.setattr(app, "_tilanne", None)
    monkeypatch.setattr(melonta, "kerää_tilanne", kerää)
    monkeypatch.setattr(melonta, "arvioi_kaikki", lambda *a: tilanne.tulokset)
    ensimmainen = app.hae_tilanne()
    assert app.hae_tilanne() is ensimmainen
    assert len(kutsut) == 1


def test_kaaviot_luetaan_perakkain_vercelissa(monkeypatch, aineisto):
    monkeypatch.setenv("VERCEL", "1")

    def ei_prosesseja(*a, **kw):
        raise AssertionError("ProcessPoolExecutor käynnistettiin")

    monkeypatch.setattr(melonta, "ProcessPoolExecutor", ei_prosesseja)
    hakija, paikat = aineisto
    _, lukemat, varoitukset = melonta.kerää_tilanne(hakija, paikat, tarkista_hakemisto=False)
    assert len(lukemat) >= 4 and varoitukset == []


def test_prosessipoolin_puuttuminen_ei_kaada(monkeypatch):
    def rikki(*a, **kw):
        raise OSError(38, "Function not implemented")   # kuten AWS Lambdassa

    monkeypatch.setattr(melonta, "ProcessPoolExecutor", rikki)
    kuvat = sorted(FIXTURES.glob("*.png"))[:2]
    tulokset = melonta._lue_kaaviot([(k.name.replace("_", "/", 2), k.read_bytes()) for k in kuvat], True)
    assert len(tulokset) == 2 and all(virhe is None for _, _, virhe in tulokset)
