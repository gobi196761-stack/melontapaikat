import datetime as dt
import io
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import app
import kaavio_svg
import melonta
import osm_sivut as osm
import syke_data
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


def test_ruotsi_omalla_valilehdella(palvelin):
    class T:
        def __init__(self, p):
            self.paikka = p
    kaikki = [T(p) for p in PAIKAT]
    nimet = lambda tyyppi: {t.paikka.nimi for t in app.suodata(kaikki, {"tyyppi": [tyyppi]} if tyyppi else {})}
    ruotsi = {"Trollforsarna (Piteälven)", "Pahakurkkio (Kalixälven)"}
    assert nimet("ruotsi") == ruotsi
    for tyyppi in (None, "peli", "retki", "tuntematon"):
        assert not nimet(tyyppi) & ruotsi
    assert "Vikaköngäs (Raudanjoki)" in nimet(None) and "Vikaköngäs (Raudanjoki)" in nimet("peli")
    runko = pyynto("/", "tyyppi=ruotsi")[2]
    assert '<a href="/?tyyppi=ruotsi" class=valittu>Ruotsi</a>' in runko
    assert runko.index(">Retket<") < runko.index(">Ruotsi<")
    assert "Veden lämpötila" not in runko   # Suomen aseman lämpötila ei kuulu Ruotsi-välilehdelle


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


class Kanta:
    def __init__(self):
        self.kirjoitetut = []

    def kirjoita(self, kokoelma, tunniste, data):
        self.kirjoitetut.append((kokoelma, tunniste, data))


def cron(monkeypatch, otsake=None):
    vastaus = {}

    def start_response(status, otsakkeet):
        vastaus["status"] = status

    environ = {"PATH_INFO": "/api/arkistoi", "QUERY_STRING": "", "REQUEST_METHOD": "GET",
               "wsgi.input": io.BytesIO()}
    if otsake:
        environ["HTTP_AUTHORIZATION"] = otsake
    runko = b"".join(app.app(environ, start_response))
    return vastaus["status"], json.loads(runko)


@pytest.fixture
def arkisto(monkeypatch):
    kanta = Kanta()
    ajo = {"ennustepvm_www": "2026-10-18", "qhav": {"ensim_pvm": "2026-10-17", "lst": [100.0]},
           "qinlask_ka": {"ensim_pvm": "2026-10-18", "lst": [101.0, 102.0]}}
    monkeypatch.setattr(app.ennustearkisto, "hae_ajot",
                        lambda: ({"61/q6101452y/ajo.json": ajo}, {"61/q6101750y": "HTTP 500"}))
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls: kanta))
    monkeypatch.setattr(app, "suomen_aika", lambda: PAIVA)
    return kanta


def test_arkistointi_vaatii_salaisuuden(monkeypatch, arkisto):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert cron(monkeypatch, "Bearer ")[0].startswith("503")
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert cron(monkeypatch)[0].startswith("401")
    assert cron(monkeypatch, "Bearer väärä")[0].startswith("401")
    assert not arkisto.kirjoitetut


def test_arkistointi_firestoreen(monkeypatch, arkisto):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    status, tulos = cron(monkeypatch, "Bearer s3cret")
    assert status == "200 OK"
    assert tulos["tallennettu"] == "ennusteet/2026-10-18" and tulos["asemia"] == 1
    assert tulos["varoitukset"] == {"61/q6101750y": "HTTP 500"}
    [(kokoelma, tunniste, data)] = arkisto.kirjoitetut
    assert data["asemat"]["61/q6101452y"]["qhav"] == {"2026-10-17": 100.0}
    assert "virhe" in data["asemat"]["61/q6101750y"]


def test_arkistointi_ilman_firestorea(monkeypatch, arkisto):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls: None))
    assert cron(monkeypatch, "Bearer s3cret")[0].startswith("503")


@pytest.fixture
def ajot(tmp_path):
    for tiedosto in (FIXTURES / "ajo").glob("*.json"):
        avain = tiedosto.name.removesuffix("_ajo.json").replace("_", "/") + "/ajo.json"
        shutil.copy(tiedosto, tmp_path / osm.Hakija._tiedostonimi(osm.kaavio_url(avain)))
    return osm.Hakija(offline=tmp_path)


def test_arviomallin_kaavio(ajot, monkeypatch):
    monkeypatch.setattr(app, "_tilanne", None)
    kuva = app.arvio_kaavio_svg("61/q6101750y", ajot)
    ET.fromstring(kuva)
    assert "Hawa&#x27;Ii (Iijoki, Maalismaa) – mittari" in kuva
    assert "arvio Pudasjärvi + Siurua" in kuva and "ennuste tehty 18.10." in kuva
    assert "arvio tänään" in kuva and "ennusteen 5–95 %" in kuva and "laskettu arvio (keskivirhe" in kuva
    # vain mitatut historia-arvot: ei mallin jälkilaskennan viivaa
    assert "malli (ennuste" not in kuva
    # mitatut päivät 8.–17.10. (tämän päivän havaintoa ei vielä ole) vinoneliöinä + selitteen kaksi
    assert kuva.count('fill="#000"/>') == 10 + 1
    assert app.arvio_kaavio_svg("61/q6101600y", ajot) is None   # ei arviomallia


def test_arviomallin_ennuste_jatkuu_arviosta(ajot):
    lukema = syke_data.Kaaviolukema(url=osm.kaavio_url("61/q6101750y/qin3lyhyt.png"), suure="virtaama",
                                    yksikko="m3/s", tanaan_paiva=None, havaittu=None,
                                    havaittu_paivia_sitten=None, malli=None)
    oma = json.loads((FIXTURES / "ajo" / "61_q6101750y_ajo.json").read_text(encoding="utf-8"))
    luetut = {t.name.removesuffix("_ajo.json").replace("_", "/") + "/ajo.json":
              json.loads(t.read_text(encoding="utf-8")) for t in (FIXTURES / "ajo").glob("*.json")}
    syke_data.taydenna(lukema, oma)
    syke_data.arvioi_tanaan(lukema, luetut)
    assert lukema.tietolahde.startswith("arvio")
    tallentaja = {}
    monkey = kaavio_svg.piirra
    try:
        kaavio_svg.piirra = lambda *a, **k: tallentaja.update(k) or ""
        kaavio_svg.arvio_svg(lukema, luetut, "61/q6101750y", "testi")
    finally:
        kaavio_svg.piirra = monkey
    tanaan = dt.date(2026, 10, 18)
    assert tallentaja["arvio"] == pytest.approx(lukema.arvo)
    assert tanaan not in tallentaja["havainnot"]
    # menneiden päivien arviot lasketaan kuten silloin olisi laskettu, havaintojen rinnalle
    aiemmat = tallentaja["aiemmat_arviot"]
    assert aiemmat and max(aiemmat) < tanaan
    assert aiemmat[dt.date(2026, 10, 17)] == pytest.approx(
        syke_data.arvioi_paiva("61/q6101750y", luetut, dt.date(2026, 10, 17)))
    eka = tallentaja["ennuste"][tanaan + dt.timedelta(days=1)]
    assert eka == pytest.approx(lukema.arvo + lukema.ennuste[1] - lukema.malli)


def test_arviomallin_linkki():
    assert app.kaavion_osoite("61/q6101750y/qin3lyhyt.png") == "/kaavio/syke/61/q6101750y"
    assert app.kaavion_osoite("smhi/11/35732") == "/kaavio/smhi/11/35732"
    assert app.kaavion_osoite("61/q6101600y/qinlyhyt.png") is None
