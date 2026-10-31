import datetime as dt
import io
import json
from urllib.parse import quote
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import app
import kaavio_svg
import melonta
import muut_kohteet
import osm_sivut as osm
import syke_data
import syke_kaavio
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


def paikkasivut(tilanne, kieli="fi"):
    """Paikkasivujen vesitilanne-osiot: kohteiden arviot, mittarit, reitti ja sää (etusivun kortissa vain tiivistelmä)."""
    return "".join(app.paikkasivu(t.paikka, kieli, tilanne) for t in tilanne.tulokset)


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
    monkeypatch.setattr(app, "hae_tilanne", lambda **_: tilanne)


def test_sivu(palvelin, tilanne):
    status, otsakkeet, runko = pyynto("/")
    assert status == "200 OK"
    assert otsakkeet["Content-Type"].startswith("text/html")
    assert "s-maxage=" in otsakkeet["Cache-Control"]
    assert runko.index("Kipinä (Iijoki)") < runko.index("Matkakoski") < runko.index("Niskakoski")
    assert "Oikean silta-aukon surffiaalto" in paikkasivut(tilanne) and "Näytä tiedot" not in runko
    # alussa merkintöjen ja kuvakkeiden selitykset (Kipinän veden lämpötila -laatikko poistettu)
    assert '<details class="selitykset" id="merkinnat"><summary>Merkinnät ja kuvakkeet</summary>' in runko   # suljettu oletuksena
    assert 'id="haku"' in runko
    assert '<div class="lukumaara" id="lukumaara">3 paikkaa</div>' in runko   # Kipinä, Matkakoski, Niskakoski
    assert runko.index('class="selitykset"') < runko.index('<nav class="kategoriat">') < runko.index("<table")   # kategorioiden yläpuolella
    assert "Veden lämpötila" not in runko and "OpenStreetMap" not in runko
    assert "<b>★</b> parhaimmillaan" in runko and "river runner -kajakki" in runko.split("<table")[0]
    assert "16.05" not in runko and "osm.fi:n paikkakuvaukset" not in runko   # ei kellonaikaa
    assert "Ehdota uutta kohdetta tai täydennä vanhaa" in runko
    assert '<summary><span class="lamppu" aria-hidden="true">💡</span> Ehdota uutta kohdetta' in runko


def test_api_ja_suodatus(palvelin):
    status, otsakkeet, runko = pyynto("/api")
    assert status == "200 OK" and otsakkeet["Content-Type"].startswith("application/json")
    data = json.loads(runko)
    assert data["paiva"] == "2026-10-18"
    assert data["paivitetty"] == "2026-10-18T16:05:00"
    assert [p["nimi"] for p in data["paikat"]] == [
        "Kipinä (Iijoki)", "Matkakoski (Tornionjoki)", "Niskakoski (Lestijoki)"]
    assert data["paikat"][0]["pisteet"] == pytest.approx(90 + 9 * 0.8 / 2.65)   # yksi kohde parhaimmillaan

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
    assert '<option value="/?tyyppi=ruotsi" selected data-nimi="Ruotsi">Ruotsi (' in runko
    assert runko.index(">Retket (") < runko.index(">Ruotsi (")
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


def test_arviomallin_kaavio(ajot, monkeypatch, vaaka):
    monkeypatch.setattr(app, "_tilanne", None)
    monkeypatch.setattr(app, "arkistoidut_arviot", lambda asema: {dt.date(2026, 10, 17): 400.0})
    kuva = app.arvio_kaavio_svg("61/q6101750y", ajot)
    ET.fromstring(kuva)
    assert "Hawa&#x27;Ii (Iijoki, Maalismaa) – mittari" in kuva
    assert "arvio Pudasjärvi + Siurua" in kuva and "ennuste tehty 18.10." in kuva
    assert "arvio tänään" in kuva and "ennusteen 5–95 %" in kuva
    # ennustehistoria toisella mallilla; ensimmäisen mallin arkistoarvoja ei piirretä
    assert "toinen malli jälkikäteen (keskivirhe" in kuva and "arvio silloin (arkisto)" not in kuva
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
        kaavio_svg.arvio_svg(lukema, luetut, "61/q6101750y", "testi", arkisto={dt.date(2026, 10, 16): 390.0})
    finally:
        kaavio_svg.piirra = monkey
    tanaan = dt.date(2026, 10, 18)
    assert tallentaja["arvio"] == pytest.approx(lukema.arvo)
    assert tanaan not in tallentaja["havainnot"]
    # menneet arviot toisella mallilla (ensimmäisen mallin arkistoarvoja ei piirretä)
    assert tallentaja["aiemmat_arviot"] == {} and tallentaja["jalkikateen_nimi"] == "toinen malli jälkikäteen"
    jalkikateen = tallentaja["jalkikateen_arviot"]
    assert max(jalkikateen) < tanaan
    assert jalkikateen[dt.date(2026, 10, 17)] == pytest.approx(
        syke_data.arvioi_paiva2("61/q6101750y", luetut, dt.date(2026, 10, 17)))
    eka = tallentaja["ennuste"][tanaan + dt.timedelta(days=1)]
    assert eka == pytest.approx(lukema.arvo + lukema.ennuste[1] - lukema.malli)


def test_kaavion_linkit():
    paikka = {p.nimi: p for p in PAIKAT}
    hawa = paikka["Hawa'Ii (Iijoki, Maalismaa)"]
    assert app.kaavion_osoite(hawa, "paa") == "/kaavio/syke/61/q6101750y/qin3lyhyt?paikka=Hawa%27Ii+%28Iijoki%2C+Maalismaa%29"
    assert app.kaavion_osoite(paikka["Pahakurkkio (Kalixälven)"], "paa").startswith("/kaavio/smhi/11/35732?paikka=")
    # SYKE:n mittarille oma kaavio vain, kun ajo.jsonin luvut täsmäsivät kuvaan
    kipina = paikka["Kipinä (Iijoki)"]
    lukema = syke_data.Kaaviolukema(url="", suure="vedenkorkeus", yksikko="m", tanaan_paiva=None, havaittu=None,
                                    havaittu_paivia_sitten=None, malli=None)
    # ilman täsmäävää ajo.jsonia sarjat luetaan SYKE:n kuvasta
    assert app.kaavion_osoite(kipina, "paa", lukema).endswith("&lahde=kuva")
    lukema.tietolahde = "SYKE-data"
    assert app.kaavion_osoite(kipina, "paa", lukema).startswith("/kaavio/syke/61/l611331001y/w3lyhyt?paikka=Kipin")


def test_kaavio_pystymalli_oletuksena(ajot):
    """Puhelimen pystynäyttö: kapea kaavio, joka skaalautuu näytön levyiseksi ja jonka tekstit
    rivittyvät kuvan sisään (vasemmalle tasatut tekstit eivät ylitä oikeaa reunaa)."""
    import re
    import kaavio_svg
    for kuva in (app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)"),
                 app.arvio_kaavio_svg("61/q6101750y", ajot)):
        ET.fromstring(kuva)
        lev = kaavio_svg.MUODOT["pysty"][0]
        assert kuva.startswith(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lev} ')
        assert "width:100%;height:auto" in kuva
        for tagi, teksti in re.findall(r'<((?:text|tspan) [^>]*)>([^<]+)<', kuva):
            if "text-anchor" in tagi:   # keskitetyt ja oikealle tasatut ovat kuvan sisällä rakenteen mukaan
                continue
            x = float(re.search(r'x="([\d.]+)"', tagi).group(1))
            koko = re.search(r'font-size="([\d.]+)"', tagi)
            leveys = len(ET.fromstring(f"<t>{teksti}</t>").text) * kaavio_svg.MERKKI_PX[float(koko.group(1) if koko else 12)]
            assert x + leveys <= lev + 4, teksti


def test_syke_kaavio(ajot, vaaka):
    kuva = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)")
    ET.fromstring(kuva)
    assert "Kipinä (Iijoki) – mittari" in kuva and "Vedenkorkeus m" in kuva
    # ennuste jatkuu viimeisestä havainnosta, mallin menneitä arvoja ei piirretä
    assert "SYKE ennuste (jatkuu viimeisestä havainnosta)" in kuva and "malli (ennuste" not in kuva and "havainto" in kuva
    # kohteiden alueet nimettyinä
    assert "Oikean silta-aukon surffiaalto 108.15–108.8 (paras 108.15–108.6)" in kuva
    assert "kohde parhaimmillaan" in kuva
    # ei SYKE:n kuvan muita merkintöjä
    assert "mediaani" not in kuva and "MHQ" not in kuva
    assert app.syke_kaavio_svg("61/l611331001y/eiole", ajot) is None
    virtaama = app.syke_kaavio_svg("61/q6101600y/qinlyhyt", ajot)
    assert virtaama is None or "Virtaama" in virtaama   # asema ei ole minkään paikan mittari -> None


def test_kaikilla_paikoilla_sijainti():
    for p in PAIKAT:
        assert p.sijainti, p.nimi
        lat, lon = p.sijainti
        assert 63 < lat < 68 and 19 < lon < 31, p.nimi


def test_suosikit_ja_sijainti_sivulla(palvelin):
    runko = pyynto("/")[2]
    assert '<option value="/?tyyppi=suosikit" id="suosikkimaara" data-nimi="♥ Suosikit">♥ Suosikit</option>' in runko
    assert 'data-paikka="Kipinä (Iijoki)" data-sijainti="65.2838,26.5408"' in runko
    assert runko.count('class="suosikki"') == runko.count("<tr data-paikka=")
    assert '<span class="km">~60 km Oulusta</span>' in runko
    assert 'id="sijainti"' in runko and "navigator.geolocation" in runko and "localStorage" in runko
    # suosikit-välilehti listaa kaikki paikat (myös Ruotsin); selain piilottaa muut kuin suosikit
    kaikki = app.suodata([type("T", (), {"paikka": p})() for p in PAIKAT], {"tyyppi": ["suosikit"]})
    assert len(kaikki) == len(PAIKAT)
    suosikit = pyynto("/", "tyyppi=suosikit")[2]
    assert '<table data-valilehti="suosikit" data-paiva0=' in suosikit and 'id="ei-suosikkeja"' in suosikit
    assert "Veden lämpötila" not in suosikit


def test_englanninkielinen_sivu(palvelin, tilanne):
    fi = pyynto("/")[2]
    assert '<html lang="fi">' in fi and 'href="/?kieli=en" hreflang="en"' in fi and 'aria-label="In English"' in fi
    en = pyynto("/", "kieli=en")[2]
    assert '<html lang="en">' in en and "<title>Paddling conditions</title>" in en
    assert 'href="/" hreflang="fi"' in en and "Suomeksi" in en
    assert '<option value="/?tyyppi=peli&amp;kieli=en" data-nimi="Play spots">Play spots (' in en
    assert "Symbols and icons" in en and "km from Oulu" in en and '<div class="pieni">Play spot · ' in en
    en_tiedot = paikkasivut(tilanne, "en")
    assert "at its best" in en_tiedot or "works (" in en_tiedot or "too little water" in en_tiedot
    assert "Eivät toimi nyt" not in en_tiedot and "Not working now" in en_tiedot
    # suomenkielisiä arvioinnin lauseita ei jää näkyviin
    for fi_teksti in ("parhaimmillaan", "liian vähän vettä", "liikaa vettä", "Oulusta", " pv: "):
        assert fi_teksti not in en.split("<script>")[0], fi_teksti
    valilehti = pyynto("/", "tyyppi=ruotsi&kieli=en")[2]
    assert 'href="/?tyyppi=ruotsi" hreflang="fi"' in valilehti


def test_kaannokset():
    import kielet
    k = lambda s: kielet.kaanna(s, "en")   # noqa: E731
    assert k("toimii (0.21 m alle parhaan)") == "works (0.21 m below best)"
    assert k("liian vähän vettä (puuttuu 215 m³/s)") == "too little water (215 m³/s short)"
    assert k("Haukipudas (Kiiminkijoki) vedenkorkeus 10.45 m (havainto, SYKE-data), 3 pv: ↘ 10.33 m, "
             "tulvaindeksi 0.41") == ("Haukipudas (Kiiminkijoki) water level 10.45 m (observed, SYKE data), "
                                      "3 d: ↘ 10.33 m, flood index 0.41")
    assert k("Olkkajärvi, tulovirtaama (Raudanjoki) virtaama 81 m³/s (havainto 2 pv sitten)") == \
        "Olkkajärvi, tulovirtaama (Raudanjoki) discharge 81 m³/s (observed 2 d ago)"
    assert kielet.kaanna("parhaimmillaan", "fi") == "parhaimmillaan"


def test_syke_kaavio_paivan_lukema_ja_englanti(ajot):
    kuva = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)")
    assert "tänään: " in kuva and "(havainto)" in kuva   # tämän päivän lukema selitteessä
    en = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)", kieli="en")
    ET.fromstring(en)
    assert "Kipinä (Iijoki) – gauge" in en and "Water level m" in en and "today: " in en
    assert "feature at its best" in en and "malli (ennuste" not in en


def test_kuvasta_luettu_kaavio():
    """Kun ajo.jsonissa ei ole kaavion suuretta, sarjat luetaan SYKE:n kuvasta (Raudanjoki)."""
    kuva = FIXTURES / "61_q6101400y_qinlyhyt.png"
    sarjat = syke_kaavio.KaavioLukija().lue_sarjat(kuva.read_bytes())
    assert sarjat.tanaan_paiva == 18
    assert 0 in sarjat.malli and max(sarjat.malli) > 5 and all(n >= -10 for n in sarjat.havainnot)
    lukema = syke_kaavio.KaavioLukija().lue(kuva.read_bytes(), osm.kaavio_url("61/q6101400y/qinlyhyt.png"))
    assert sarjat.malli[0] == pytest.approx(lukema.malli)
    svg = kaavio_svg.kuva_svg(sarjat, dt.date(2026, 10, 18), "Testi", "m3/s",
                              [("Kohde", (10, None), (20, 40))], kieli="en")
    ET.fromstring(svg)
    assert "read from the SYKE chart image" in svg and "today: " in svg and "Kohde 10– (best 20–40)" in svg
    assert '>8.10.</text>' in svg and '>7.10.</text>' not in svg   # 10 päivää taaksepäin
    assert app._kuvan_paiva(18, dt.datetime(2026, 10, 19, 8)) == dt.date(2026, 10, 18)


def test_kaavio_alkaa_kymmenen_paivaa_aiemmin(ajot):
    kuva = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)")
    assert '>8.10.</text>' in kuva and '>7.10.</text>' not in kuva and '>18.10.</text>' in kuva


def test_kaukaiset_ja_tulvaindeksirajat():
    # asteikon ulkopuolinen alue näkyy reunassa nuolella
    svg = kaavio_svg.piirra("T", "a", dt.date(2026, 10, 20), malli={dt.date(2026, 10, 19): 60.0},
                            ennuste={dt.date(2026, 10, 21): 55.0},
                            alueet=[("Treeni", (15, 450), (20, 50)), ("Isot aallot", (200, 450), (300, 350)),
                                    ("Matala", (None, 5), (None, 3))])
    # nuoli kertoo toiminta-alueen rajat (paras alue suluissa)
    assert "↑ Isot aallot 200–450 (paras 300–350)" in svg and "Treeni 15–450 (paras 20–50)" in svg
    assert "↓ Matala –5 (paras –3)" in svg
    aina = kaavio_svg.piirra("T", "a", dt.date(2026, 10, 20), malli={dt.date(2026, 10, 19): 60.0},
                             alueet=[("Virranrajat", (None, None), (None, 30))])
    assert "Virranrajat kaikilla vesillä (paras –30)" in aina
    # tulvaindeksi 0 = MNQ, 1 = MHQ
    simo = next(p for p in PAIKAT if p.nimi == "Simojoki")
    alueet = dict((n, (t, pa)) for n, t, pa in app._alueet(simo, "paa", {"MNW": 10.0, "MHW": 12.0}))
    t, pa = alueet["Retkimelonta Alaniemi – Simo (kesävesi)"]
    assert t == pytest.approx((10.2, 11.4)) and pa == pytest.approx((10.4, 11.2))
    assert all(n != "Retkimelonta Alaniemi – Simo (kesävesi)" for n, _, _ in app._alueet(simo, "paa"))


def test_arkistoidut_arviot(monkeypatch):
    class Kanta:
        def listaa(self, kokoelma):
            assert kokoelma == "ennusteet"
            return {"2026-10-19": {"arviot": {"61/q6101750y": {"ennustepvm_www": "2026-10-19", "tanaan": 401.5}}},
                    "2026-10-20": {"arviot": {"61/q6101750y": {"ennustepvm_www": "2026-10-20", "tanaan": None}}},
                    "2026-10-21": {"asemat": {}}}
    monkeypatch.setattr(app, "_arkisto", None)
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls: Kanta()))
    assert app.arkistoidut_arviot("61/q6101750y") == {dt.date(2026, 10, 19): 401.5}
    # ilman tunnuksia arkisto on tyhjä eikä kaavio kaadu
    monkeypatch.setattr(app, "_arkisto", None)
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls: None))
    assert app.arkistoidut_arviot("61/q6101750y") == {}


def test_paikkakunta_ja_reittilinkit(palvelin, tilanne):
    from paikkakunnat import PAIKKAKUNNAT
    assert len(PAIKKAKUNNAT) == 308 + 14
    assert PAIKKAKUNNAT["Oulu"] == pytest.approx((65.01, 25.47), abs=0.05)
    assert all(59.5 < lat < 70.2 and 17 < lon < 31.7 for lat, lon in PAIKKAKUNNAT.values())
    runko = pyynto("/")[2]
    assert 'id="paikkakunta" list="kunnat"' in runko and '<option value="Rovaniemi">' in runko
    kunnat = json.loads(runko.split('<script type="application/json" id="paikkakunnat">')[1].split("</script>")[0])
    assert kunnat["Rovaniemi"] == list(PAIKKAKUNNAT["Rovaniemi"])
    tiedot = paikkasivut(tilanne)
    assert ('href="https://www.google.com/maps/dir/?api=1&amp;destination=65.2838%2C26.5408&amp;travelmode=driving"'
            in tiedot) and "🚗 Reitti" in tiedot
    en = pyynto("/", "kieli=en")[2]
    assert "or municipality" in en and "🚗 Route" in paikkasivut(tilanne, "en") and "e.g. Rovaniemi" in en


def test_ajomatkat(monkeypatch):
    monkeypatch.setattr(app, "_ajomatkat", {})
    paikat = [p for p in PAIKAT if p.sijainti]
    kyselyt = []

    def hae(hakija, url):
        kyselyt.append(url)
        if hakija == "rikki":
            return None, "aikakatkaisu"
        return json.dumps({"code": "Ok", "distances": [[0] + [1000.0 * (i + 1) for i in range(len(paikat))]]}).encode(), None

    monkeypatch.setattr(app.osm, "hae_turvallisesti", hae)
    # lähtöpiste pyöristetään 0.01°:een ennen reitityskyselyä (OSRM: pit,lev)
    status, tulos = app.ajomatkat("66.50281,25.72849", "ok")
    assert status == "200 OK" and tulos["lahto"] == [66.5, 25.73]
    assert kyselyt[0].startswith("https://router.project-osrm.org/table/v1/driving/25.73,66.5;")
    assert tulos["km"][paikat[0].nimi] == 1.0 and tulos["km"][paikat[2].nimi] == 3.0
    assert app.ajomatkat("66.5,25.73", "rikki")[0] == "200 OK" and len(kyselyt) == 1   # muistista
    assert app.ajomatkat("abc", "ok")[0] == "400 Bad Request"
    assert app.ajomatkat("40.0,25.0", "ok")[0] == "400 Bad Request"
    assert app.ajomatkat("60.0,25.0", "rikki")[0] == "503 Service Unavailable"


def test_ei_json_linkkia_ja_ajomatka_selaimessa(palvelin):
    runko = pyynto("/")[2]
    assert ">JSON</a>" not in runko
    assert 'fetch("/api/ajomatkat?v=2&lahto="' in runko and "linnuntietä" not in runko


def test_saa_perilla_ja_veden_lampotila(monkeypatch, palvelin, tilanne):
    ajo = {"ennustepvm_www": "2026-10-18", "tw_ka": {"ensim_pvm": "2026-10-17", "lst": [5.2, 4.64, 4.1]}}
    assert syke_data.veden_lampotila(ajo) == pytest.approx(4.64)
    assert syke_data.veden_lampotila({"ennustepvm_www": "2026-10-18"}) is None
    assert [app.saa_ikoni(k) for k in (0, 1, 2, 3, 45, 61, 71, 95)] == ["☀️", "☀️", "⛅", "☁️", "☁️", "🌧️", "🌧️", "⛈️"]
    # tuntiennuste Open-Meteosta: menneet tunnit (yli tunti sitten) jätetään pois
    nyt = 1_792_540_800
    monkeypatch.setattr(app.time, "time", lambda: nyt)
    paikat = [p for p in PAIKAT if p.sijainti]
    tunnit = [nyt - 7200 + 3600 * i for i in range(6)]
    vastaus = [{"hourly": {"time": tunnit, "temperature_2m": [-2.0, -1.4, 0.2, 1.0, 2.0, 3.0],
                           "weather_code": [0, 0, 2, 3, 61, 61]}} for _ in paikat]
    monkeypatch.setattr(app.osm, "hae_turvallisesti", lambda h, url: (json.dumps(vastaus).encode(), None))
    saa = app.saaennusteet(None)
    assert saa[paikat[0].nimi]["aika"][0] == nyt - 3600 and len(saa) == len(paikat)
    # 60 min ajoa + 30 min -> saapuminen nyt + 1.5 h -> tunti nyt + 1 h
    assert app.saa_perilla(saa[paikat[0].nimi], 60, nyt) == (nyt + 5400, 1.0, 3)
    monkeypatch.setattr(app.osm, "hae_turvallisesti", lambda h, url: (None, "aikakatkaisu"))
    assert app.saaennusteet(None) == {}
    # sivulla kohteen perässä: saapumisaika, ilma, ikoni ja vesi
    t = next(x for x in tilanne.tulokset if x.paikka.nimi.startswith("Matkakoski"))
    next(iter(t.lukemat.values())).veden_lampotila = 4.64
    tilanne.saa, tilanne.ajo_min = {t.paikka.nimi: saa[paikat[0].nimi]}, {t.paikka.nimi: 0}
    runko = pyynto("/")[2]
    sivu = app.paikkasivu(t.paikka, "fi", tilanne)   # sää ja reitti paikkasivun vesitilanteessa
    assert '<span class="saa-aika">perillä klo ' in sivu and '<span class="saa-ilma">0 °C</span>' in sivu
    assert '<span class="saa-ikoni">⛅</span> · vesi 4.6 °C' in sivu and 'data-ajo="0"' in sivu
    en = app.paikkasivu(t.paikka, "en", tilanne)
    assert "on arrival" in en and ">air</a> <span" in en and "water 4.6 °C" in en
    # reittilinkki kohdelinkin alla, sää sen perässä; "ilma" vie paikan tuntiennusteeseen
    lev, pit = t.paikka.sijainti
    # kortti: iso kuva, nimi ♡, tilamerkki, tyyppi · km / kesto; avattavassa reitti · perillä klo ja lämpötilat
    assert '♡</button></div><span class="olot p-' in runko and '<div class="pieni">Peli · <span class="km">' in runko
    assert "Näytä tiedot" not in runko
    assert (f'<div class="pieni matka"><a class="reitti" href="https://www.google.com/maps/dir/?api=1&amp;'
            f'destination={lev}%2C{pit}&amp;travelmode=driving" target="_blank" rel="noopener">🚗 Reitti</a> · '
            f'<span class="saa-aika">perillä klo ') in sivu
    assert '<div class="pieni">Peli · <span class="km">~180 km Oulusta</span></div>' in runko
    assert '</span></div>\n<div class="pieni lampotilat"><span class="saa"' in sivu
    assert "ajomatka" not in runko.split("<script>")[0] and "\" ajomatka\"" not in runko
    assert (f'<a class="ilma-linkki" href="https://www.yr.no/en/forecast/hourly-table/{lev},{pit}" '
            f'data-foreca="https://www.foreca.fi/Finland/Ylitornio/15vrk" target="_blank" rel="noopener">ilma</a>') in sivu
    tilanne.saa, tilanne.ajo_min = {}, {}


def test_surffitilanne_ja_linkki(monkeypatch):
    nyt = dt.datetime(2026, 10, 21, 9, 30, tzinfo=dt.timezone.utc)
    tunnit = lambda *r: {"hours": [{"timestamp": f"2026-10-21T{9 + i:02d}:00:00Z", "rating": v,   # noqa: E731
                                    "data_unknown": False} for i, v in enumerate(r)]}
    vastaukset = {"/api/forecast": tunnit(1, 0), "/api/forecast/tauvo": tunnit(0, 0, 2),
                  "/api/forecast/olkijoki": {"hours": [{"timestamp": "2026-10-21T12:00:00Z", "rating": 3,
                                                        "data_unknown": True}]}}

    def hae(hakija, url):
        polku = url.removeprefix(app.SURFFI)
        return (json.dumps(vastaukset[polku]).encode(), None) if polku in vastaukset else (None, "404")

    monkeypatch.setattr(app.osm, "hae_turvallisesti", hae)
    surffi = app.surffitilanne(None, nyt)
    assert surffi["nyt"] == ["yppari"] and surffi["ennuste"] == ["tauvo"]   # olkijoki: data epävarma
    tauvo = dt.datetime(2026, 10, 21, 11, tzinfo=dt.timezone.utc).timestamp()   # ensimmäinen surffitunti
    assert surffi["ajat"] == {"yppari": nyt.timestamp(), "tauvo": tauvo}
    # sää ja merivesi surffihetkellä (Open-Meteo: sää + Marine)
    tunnit = [int(tauvo) - 3600 * 3 + 3600 * i for i in range(8)]
    saa = [{"hourly": {"time": tunnit, "temperature_2m": [-3.0 + i for i in range(8)],
                       "weather_code": [2, 2, 2, 3, 3, 95, 3, 3]}}] * 2
    meri = [{"hourly": {"time": tunnit, "sea_surface_temperature": [7.0 + i / 10 for i in range(8)]}}] * 2
    monkeypatch.setattr(app.osm, "hae_turvallisesti", lambda h, url: (
        json.dumps(meri if "marine-api" in url else saa).encode(), None))
    tiedot = app.surffisaa(None, {"yppari": nyt.timestamp(), "tauvo": tauvo})
    assert tiedot["tauvo"] == {"t": 0.0, "k": 3, "ukkonen": True, "meri": pytest.approx(7.3)}
    assert tiedot["yppari"]["t"] == -2.0 and tiedot["yppari"]["ukkonen"] is False
    surffi["saa"] = tiedot
    k_ = lambda s: s   # noqa: E731
    linkki = app.surffilinkki(surffi, k_)
    assert linkki.startswith('<span class="surffi ok"><a class="surffi-paa" href="https://surffiennustaja.vercel.app/"')
    assert '🏄 Merelle Surffaamaan</a>: <a href="https://surffiennustaja.vercel.app/yppari"' in linkki
    assert '<span class="surffi-saa">nyt: <a href="https://www.yr.no/en/forecast/hourly-table/64.4056,24.1"' in linkki
    assert '>ilma</a> −2 °C ⛅ · meri 7.1 °C</span>' in linkki
    assert '<span class="ok">(ennusteessa: <a href="https://surffiennustaja.vercel.app/tauvo"' in linkki
    assert 'Tauvo</a> <span class="surffi-saa">ke 14.00: <a class="ukkonen" title="ukkosta ennustettu"' in linkki
    assert '>ilma</a> 0 °C ☁️ · meri 7.3 °C</span>)</span>' in linkki
    en = app.surffilinkki(surffi, lambda s: app.kielet.kaanna(s, "en"), "en")
    assert "Wed 14:00: " in en and "sea 7.3 °C" in en and "now: " in en
    tyhja = app.surffilinkki({"nyt": [], "ennuste": []}, k_)
    assert tyhja.startswith('<span class="surffi">') and "ennusteessa" not in tyhja


def test_ajomatka_ja_kesto_oulusta(palvelin, tilanne):
    assert app._kesto(20) == "20 min" and app._kesto(183) == "3 h 03 min"
    t = tilanne.tulokset[0]
    tilanne.ajo_km, tilanne.ajo_min = {t.paikka.nimi: 181.4}, {t.paikka.nimi: 150}
    tilanne.surffi = {"nyt": [], "ennuste": ["yppari"]}
    runko = pyynto("/")[2]
    assert '<span class="km">~181 km / 2 h 30 min, lähtö Oulu</span>' in runko
    # surffilinkki heti otsikon alla
    assert runko.index("</h1>") < runko.index("Merelle Surffaamaan") < runko.index('<nav class="alapalkki"')
    assert "~181 km / 2 h 30 min, from Oulu" in pyynto("/", "kieli=en")[2]
    tilanne.ajo_km, tilanne.ajo_min, tilanne.surffi = {}, {}, {}


def test_lahtoaika_valinta(palvelin):
    runko = pyynto("/")[2]
    assert '<label class="paikkakunta">lähtöaika <input id="lahtoaika" type="datetime-local"' in runko
    assert 'sessionStorage.setItem("melonta-lahtoaika", lahtoKentta.value)' in runko
    assert 'sessionStorage.getItem("melonta-lahtoaika")' in runko
    assert ">departure <input" in pyynto("/", "kieli=en")[2]


def test_ukkonen(palvelin, tilanne):
    nyt = 1_792_540_800
    saa = {"aika": [nyt + 3600 * i for i in range(8)], "t": [10.0] * 8, "k": [2, 2, 2, 2, 95, 2, 2, 2]}
    assert not app.ukkosta(saa, nyt + 1800)          # ukkonen 4 h päästä saapumistunnista: ei vielä
    assert app.ukkosta(saa, nyt + 3600 * 1.5)
    assert not app.ukkosta(saa, nyt + 3600 * 5.5)    # ukkonen jo ohi
    assert not app.ukkosta({**saa, "k": [2] * 8}, nyt)
    t = tilanne.tulokset[0]
    tilanne.saa, tilanne.ajo_min = {t.paikka.nimi: saa}, {t.paikka.nimi: 0}
    monkey = app.time.time
    try:
        app.time.time = lambda: nyt + 3600   # saapuminen klo nyt+1.5 h -> ukkonen 2.5 h päästä
        runko = app.paikkasivu(t.paikka, "fi", tilanne)
    finally:
        app.time.time = monkey
    assert '<a class="ilma-linkki ukkonen" title="ukkosta ennustettu" href="https://www.yr.no/' in runko
    assert 'UKKONEN.includes(k) ? "⛈️"' in runko
    tilanne.saa, tilanne.ajo_min = {}, {}


def test_paivakohtaiset_arviot(palvelin, tilanne):
    """Lähtöpäivä muu kuin tänään: sivulla jokaiselle ennustepäivälle oma versio arvioista."""
    t = next(x for x in tilanne.tulokset if x.ennuste)
    assert set(t.ennusteen_kohteet) == set(t.ennuste)
    runko = pyynto("/")[2]
    rivi = app.paikkasivu(t.paikka, "fi", tilanne)   # päivien versiot paikkasivun vesitilanteessa
    rivi = rivi[rivi.index(f'<div class="tilanne-rivi" data-paikka="{t.paikka.nimi}"'):]
    rivi = rivi[:rivi.index("</section>")]
    assert "data-pisteet='" in runko[runko.index(f'<tr data-paikka="{t.paikka.nimi}"'):]   # etusivulla pisteet
    pisteet = json.loads(rivi.split("data-pisteet='")[1].split("'")[0])
    assert pisteet["0"] == round(t.pisteet) and pisteet["1"] == round(t.ennuste[1])
    assert '<div class="paiva" data-paiva="0">' in rivi and '<div class="paiva" data-paiva="1" hidden>' in rivi
    paiva1 = rivi.split('data-paiva="1" hidden>')[1].split("</div>")[0]
    assert "(ennuste +1 pv)" in paiva1 and "(ennuste +1 pv)" not in rivi.split('data-paiva="1"')[0]
    assert 'data-paiva0="2026-10-18"' in runko and 'id="paiva-tila"' not in runko   # ei tilariviä
    assert "(forecast +1 d)" in app.paikkasivu(t.paikka, "en", tilanne)


def test_reissun_pystyviiva(ajot):
    reissu = dt.datetime(2026, 10, 20, 10, tzinfo=dt.timezone.utc).timestamp()
    merkki = kaavio_svg.reissu.set(reissu)
    try:
        kuva = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)")
    finally:
        kaavio_svg.reissu.reset(merkki)
    juuri = ET.fromstring(kuva)
    ns = "{http://www.w3.org/2000/svg}"
    osoitin = next(g for g in juuri.iter(f"{ns}g") if g.get("data-reissu"))
    tiedot = json.loads(osoitin.get("data-reissu"))
    # vedettävä osoitin alkaa reissun ajankohdasta; arvot havainnoista ja ennusteesta aikajärjestyksessä
    assert tiedot["t0"] == reissu * 1000 and tiedot["yks"] == "m" and tiedot["nimi"] == "Perillä"
    assert [t for t, _ in tiedot["s"]] == sorted(t for t, _ in tiedot["s"]) and len(tiedot["s"]) > 10
    assert tiedot["a"] <= tiedot["t0"] <= tiedot["b"]
    assert 'class="r-kahva"' in kuva and "touch-action:none" in kuva and "<![CDATA[" in kuva
    assert f'getElementById("{tiedot["id"]}")' in kuva and "Perillä (vedä ajankohtaa)" in kuva
    # kaavion ulkopuolinen reissu: osoitin kaavion alueelle (nykyhetki tai reuna)
    kaukana = kaavio_svg.reissu.set(reissu + 365 * 86400)
    try:
        toinen = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)")
    finally:
        kaavio_svg.reissu.reset(kaukana)
    t2 = json.loads(next(g for g in ET.fromstring(toinen).iter(f"{ns}g") if g.get("data-reissu")).get("data-reissu"))
    assert t2["a"] <= t2["t0"] <= t2["b"] and t2["id"] != tiedot["id"]
    assert tiedot["matka"] is None   # ilman ?matka= lähtöaikaa ei palauteta
    m = kaavio_svg.matka.set(56.0)
    try:
        kolmas = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)")
    finally:
        kaavio_svg.matka.reset(m)
    assert '&quot;matka&quot;:56.0' in kolmas and 'sessionStorage.setItem("melonta-lahtoaika"' in kolmas
    # lähtö enintään sivun lähtöaikakentän rajalla (+14 pv), osoitin enintään siihen + matka-aika
    assert '&quot;pv&quot;:14' in kolmas and "getDate() + D.pv, 23, 45" in kolmas and "viimeinenLahto + D.matka * 60000" in kolmas


def test_kaaviolinkit_saavat_reissun(palvelin):
    runko = pyynto("/")[2]
    assert 'url.searchParams.set("reissu", Math.round(perilla / 900) * 900)' in runko
    # matka-aika kaavioon ja osoittimella valittu lähtöaika takaisin sivulle
    assert 'url.searchParams.set("matka", Math.round(ajoMin + 30))' in runko
    assert 'addEventListener("pageshow"' in runko and 'e.key !== "melonta-lahtoaika"' in runko


def test_yr_linkki_saapumispaivalle():
    nyt = dt.datetime(2026, 10, 21, 10, tzinfo=dt.timezone.utc).timestamp()   # 13.00 Suomen aikaa
    assert app.yr_osoite(65.1, 25.8) == "https://www.yr.no/en/forecast/hourly-table/65.1,25.8"
    assert app.yr_osoite(65.1, 25.8, nyt + 3600, nyt).endswith("/65.1,25.8")          # tänään
    assert app.yr_osoite(65.1, 25.8, nyt + 12 * 3600, nyt).endswith("?i=1")         # huomenna 01.00
    assert app.yr_osoite(65.1, 25.8, nyt + 2 * 86400, nyt).endswith("?i=2")
    # yr.no ennustaa vain 9 päivää: myöhempi saapuminen sen viimeiselle päivälle (sama raja selaimessa)
    assert app.yr_osoite(65.1, 25.8, nyt + 13 * 86400, nyt).endswith(f"?i={app.YR_PAIVIA}")
    assert f"const YR_PAIVIA = {app.YR_PAIVIA};" in app.SKRIPTI


def test_foreca_linkki_lahimpaan_kuntaan():
    """yr.no:n 9 päivän jälkeen selain vaihtaa ilma-linkin Forecan 15 vrk ennusteeseen (data-foreca)."""
    paikka = {p.nimi: p for p in PAIKAT}
    assert app.foreca_osoite(paikka["Kipinä (Iijoki)"]) == "https://www.foreca.fi/Finland/Pudasj%C3%A4rvi/15vrk"
    # Ruotsin paikka: lähin Ruotsin kunta, vaikka Suomen puolella olisi lähempi
    assert app.foreca_osoite(paikka["Pahakurkkio (Kalixälven)"]) == "https://www.foreca.fi/Sweden/Pajala/15vrk"
    assert "linkki.href = foreca || url.toString();" in app.SKRIPTI


def test_saaennuste_kattaa_lahtopaivat(monkeypatch):
    """Lähtöajan voi valita 14. päivän loppuun; sääennusteen on ulotuttava sen yli."""
    kyselyt = []
    monkeypatch.setattr(app.osm, "hae_turvallisesti", lambda h, url: (kyselyt.append(url), (None, "x"))[1])
    app.saaennusteet(None)
    assert "forecast_days=16" in kyselyt[0]
    import inspect
    assert inspect.signature(app.saaennusteet).parameters["tunteja"].default >= (app.LAHTO_PAIVIA + 1) * 24 + 6


def test_ennuste_jatkuu_viimeisesta_havainnosta():
    d = lambda n: dt.date(2026, 10, 21) + dt.timedelta(days=n)   # noqa: E731
    malli = {d(n): 100.0 + n for n in range(-3, 5)}
    havaitut = {d(-2): 90.0, d(-1): 95.0}   # tämän päivän havainto puuttuu
    ennuste, vali, lukema = kaavio_svg._jatka_havainnosta(havaitut, malli, d(0), {d(1): (98.0, 105.0)})
    # alkaa viimeisestä havainnosta (95), sitten mallin muutos lisättynä (siirto 95 − 99 = −4)
    assert ennuste[d(-1)] == 95.0 and ennuste[d(0)] == 96.0 and ennuste[d(3)] == 99.0
    assert d(-2) not in ennuste   # mallin menneitä arvoja ei näytetä
    assert vali == {d(1): (94.0, 101.0)} and lukema == (96.0, "ennuste")
    # ilman havaintoja: mallin ennuste tästä päivästä
    ennuste, _, lukema = kaavio_svg._jatka_havainnosta({}, malli, d(0))
    assert min(ennuste) == d(0) and lukema == (100.0, "malli")


def test_mittarin_tuntikaavio(ajot, monkeypatch, vaaka):
    """Koiteli ym.: mittarin omat tuntimittaukset ja ennuste päivän loppuun kaavion alle."""
    tunnit = {f"2026-10-18T{t:02d}": 10.50 - 0.005 * t for t in range(0, 15)}
    tulos = syke_data.mittarin_tunnit(tunnit, dt.date(2026, 10, 18))
    assert tulos["viim"] == 14 and len(tulos["arviot"]) == 15 and max(tulos["ennuste"]) == 23
    assert tulos["ennuste"][23] == pytest.approx(10.50 - 0.005 * 23)   # trendi jatkuu
    assert tulos["keskiarvo"] == pytest.approx(sum(10.50 - 0.005 * t for t in range(24)) / 24)
    assert syke_data.mittarin_tunnit({}, dt.date(2026, 10, 18)) is None
    arvo = lambda t: f"{108.60 - 0.002 * t:.3f}".replace(".", ",")   # noqa: E731
    data = "".join(f"18.10.2026;{t:02d}:00;{arvo(t)};\n" for t in range(10)).encode("latin-1")
    alkuperainen = app.osm.hae_turvallisesti
    monkeypatch.setattr(app.osm, "hae_turvallisesti", lambda h, url: (
        (data, None) if "RealTime/data/W6100710_N43" in url else alkuperainen(h, url)))
    kuva = app.syke_kaavio_svg("61/l611331001y/w3lyhyt", ajot, "Kipinä (Iijoki)",
                               nyt=dt.datetime(2026, 10, 18, 12))
    ET.fromstring(kuva)
    assert kuva.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 820" ')   # 440 + 380
    assert "Kipinä (Iijoki) – Pudasjärvi, mitattu tunneittain" in kuva and "SYKE päiväarvo" in kuva
    assert "päivän keskiarvo-ennuste 108.58" in kuva   # 108.60 − 0.002 · 11.5 (lasku jatkuu)


def test_kajakkikuvakkeet(palvelin, tilanne):
    from paikat import KAJAKKITYYPIT
    assert set(app.KAJAKKI_KUVAKKEET) == set(KAJAKKITYYPIT)
    for p in PAIKAT:
        for k in p.kohteet:
            assert set(k.kajakit) <= set(KAJAKKITYYPIT), (p.nimi, k.nimi)
    kipina = next(p for p in PAIKAT if p.nimi == "Kipinä (Iijoki)")
    assert {k.nimi: k.kajakit for k in kipina.kohteet}["Ala-aallot (ykkös- ja kakkosaalto)"] == ("slice",)
    # oletukset: retkelle slice ja river runner, Neitikoskelle ja pelipaikan honttoon freestyle, muuten slice
    from paikat import kohteen_kajakit
    oletus = {(p.nimi, k.nimi): kohteen_kajakit(p, k) for p in PAIKAT for k in p.kohteet}
    assert oletus[("Sanginjoki", "Koskiosuus Lemmenpolku – Taivalkoski")] == ("slice", "riverrunner")
    assert oletus[("Neitikoski (Lieksanjoki)", "Aalto (aaltoliikkeet)")] == ("freestyle",)
    assert oletus[("Kattilakoski (Tornionjoki)", "Grillikodan hontto")] == ("freestyle",)
    assert oletus[("Kattilakoski (Tornionjoki)", "Mega-aalto")] == ("freestyle",)
    assert oletus[("Kattilakoski (Tornionjoki)", "Kakkosaalto")] == ("slice",)
    from paikat import ISOT_SURFFIT
    assert ISOT_SURFFIT <= {k.nimi for p in PAIKAT for k in p.kohteet}   # nimet ajan tasalla
    runko = paikkasivut(tilanne)
    # Kipinän oikean silta-aukon surffiaalto: freestyle-kuvake nimen perässä
    assert ('<b>Oikean silta-aukon surffiaalto</b> <span class="kajakit"><svg class="kajakki" viewBox="0 -8 40 32" '
            'style="color:#e03131" role="img" aria-label="freestyle-kajakki"><title>freestyle-kajakki</title>') in runko
    assert 'aria-label="freestyle kayak"' in paikkasivut(tilanne, "en")


def test_halytysosio(palvelin, monkeypatch):
    import halytykset
    monkeypatch.setattr(halytykset, "avaimet", lambda kanta=None: None)
    assert 'id="halytys"' not in pyynto("/")[2]   # ilman avaimia ei tilausta
    monkeypatch.setattr(halytykset, "avaimet", lambda kanta=None: ("JULKINEN-avain", "x"))
    runko = pyynto("/")[2]
    assert '<details id="halytys" class="halytys" hidden data-vapid="JULKINEN-avain">' in runko
    assert runko.index('class="selitykset"') < runko.index('id="halytys"') < runko.index('<nav class="kategoriat">')
    assert '<option value="60" selected>60 – hyvä</option>' in runko and '<option value="3" selected>3 pv</option>' in runko
    assert '<script type="application/json" id="halytys-valinnat">{"Kipinä (Iijoki)":{"":["toimii","paras","pisteet"]' in runko
    assert 'navigator.serviceWorker.register("/sw.js")' in runko and 'fetch("/api/halytys"' in runko
    assert "Score limit" in pyynto("/", "kieli=en")[2]


def test_asennettava_sovellus(palvelin):
    import sovellus
    status, otsakkeet, runko = pyynto("/manifest.webmanifest")
    assert status == "200 OK" and otsakkeet["Content-Type"].startswith("application/manifest+json")
    m = json.loads(runko)
    # iPhonen push-ilmoitukset vaativat Koti-valikosta omana sovelluksenaan avautuvan sivun
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["name"] == "Melontatilanne"
    v = sovellus.VERSIO   # logon tiivisteestä: uusi logo -> uudet osoitteet, ei vanhaa välimuistista
    assert len(v) == 8 and {f"/kuvake-192.png?v={v}", f"/kuvake-512.png?v={v}"} <= {k["src"] for k in m["icons"]}
    assert json.loads(pyynto("/manifest.webmanifest", "kieli=en")[2])["start_url"] == "/?kieli=en"
    sivu = pyynto("/")[2]
    assert f'<link rel="manifest" href="/manifest.webmanifest?v={v}">' in sivu
    assert f'<link rel="apple-touch-icon" href="/kuvake-180.png?v={v}">' in sivu
    assert f'href="/manifest.webmanifest?kieli=en&amp;v={v}"' in pyynto("/", "kieli=en")[2]
    for koko in sovellus.KOOT:
        vastaus = app.app({"PATH_INFO": f"/kuvake-{koko}.png", "REQUEST_METHOD": "GET", "QUERY_STRING": ""},
                          lambda status, otsakkeet: None)
        data = b"".join(vastaus)
        assert data.startswith(b"\x89PNG") and int.from_bytes(data[16:20], "big") == koko
    assert pyynto("/kuvake-64.png")[0] == "404 Not Found"


def test_halyta_kirjoittaa_yhteenvedon_lokiin(monkeypatch, capsys):
    """Aamun hälytysajosta jää Vercelin lokiin rivi myös epäonnistuessa."""
    monkeypatch.delenv("CRON_SECRET", raising=False)
    status, tulos = app.halyta({})
    assert status.startswith("503") and tulos == {"virhe": "CRON_SECRET puuttuu"}
    rivi = capsys.readouterr().out.strip()
    assert rivi.startswith("halyta: ")
    loki = json.loads(rivi.removeprefix("halyta: "))
    assert loki["status"].startswith("503") and loki["virhe"] == "CRON_SECRET puuttuu" and "kesto_s" in loki

    monkeypatch.setenv("CRON_SECRET", "salainen")
    monkeypatch.setattr(app, "_cron_kanta", lambda environ: ("kanta", None))
    monkeypatch.setattr(app.kapsi, "keraa", lambda kanta, nyt: {"mittauksia": 5, "uusia": 5})
    monkeypatch.setattr(app.halytykset, "avaimet", lambda kanta: ("julk", "yks"))
    monkeypatch.setattr(app, "hae_tilanne", lambda **_: app.Tilanne(paivitetty=dt.datetime(2026, 10, 23, 8, 0),
                                                                tulokset=[], varoitukset=[], lukemia=1))
    monkeypatch.setattr(app.halytykset, "aja", lambda *a: {"tilauksia": 2, "lahetetty": 1, "jo_ilmoitettu": 1,
                                                           "poistettu": 0, "virheet": []})
    status, _ = app.halyta({})
    loki = json.loads(capsys.readouterr().out.strip().removeprefix("halyta: "))
    assert status == "200 OK" and loki["tilauksia"] == 2 and loki["lahetetty"] == 1
    assert loki["kapsi"] == {"mittauksia": 5, "uusia": 5}   # Maalismaan keruu mukana yhteenvedossa



def test_etusivun_nimet_linkittavat_paikkasivuille(palvelin):
    _, _, runko = pyynto("/")
    assert '<a href="/paikka/kipina-iijoki">Kipinä (Iijoki)</a>' in runko
    linkit = set(re.findall(r'href="(/paikka/[a-z0-9-]+)"', runko))
    assert linkit <= {f"/paikka/{t}" for t in app.PAIKKASIVUT}


def test_skriptien_syntaksi(tmp_path):
    """Sivun JavaScript jäsentyy (esim. kaksi samannimistä const-muuttujaa kaataisi koko skriptin)."""
    import muut_kohteet
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node puuttuu")
    skriptit = [app.SKRIPTI, muut_kohteet.luettelo("").split("<script>")[1].split("</script>")[0]]
    for i, s in enumerate(skriptit):
        tiedosto = tmp_path / f"s{i}.js"
        tiedosto.write_text(s, encoding="utf-8")
        tulos = subprocess.run([node, "--check", str(tiedosto)], capture_output=True, text=True)
        assert tulos.returncode == 0, tulos.stderr


def test_lisakaaviot_pois(aineisto, monkeypatch):
    """Verkkosovellus ei lue sivujen ylimääräisiä kaavioita (vain komentorivi näyttää ne)."""
    hakija, paikat = aineisto
    luetut = []
    alkuperainen = melonta._lue_kaaviot
    monkeypatch.setattr(melonta, "_lue_kaaviot", lambda t, p: luetut.extend(a for a, _ in t) or alkuperainen(t, p))
    melonta.kerää_tilanne(hakija, paikat, tarkista_hakemisto=False, prosessit=False, lisakaaviot=False)
    mittarit = {m.kaavio for p in paikat for m in p.mittarit.values()}
    assert luetut and set(luetut) <= mittarit


def test_nappien_lukumaarat(palvelin):
    runko = pyynto("/")[2]
    retket = sum(1 for p in PAIKAT if p.maa == "FI" and p.tyyppi == "retki")
    assert f'>Retket ({retket})</option>' in runko
    assert f'>Ruotsi ({sum(1 for p in PAIKAT if p.maa == "SE")})</option>' in runko
    assert f'>Muut kohteet ({len(muut_kohteet.KOHTEET)})</option>' in runko
    # kategoriavalikko hakukentän perässä, järjestysvalinta niiden alla
    assert runko.index('id="haku"') < runko.index('id="kategoria"') < runko.index('id="jarjestys"')
    assert 'id="suosikkimaara"' in runko


def test_englanninkielisen_etusivun_linkit(palvelin):
    sivu = pyynto("/", "kieli=en")[2]
    assert '/paikka/kipina-iijoki?kieli=en"' in sivu


def test_turvavaroitukset_avattavana_osiona(monkeypatch, tilanne):
    turva = {"meri": 6.0, "maatuuli": {"ms": 6.0, "puuska": None, "suunta": 90, "aika": PAIVA.timestamp(),
                                       "alkaa": PAIVA.timestamp()}}
    monkeypatch.setattr(app, "hae_tilanne", lambda **_: app.Tilanne(**{**tilanne.__dict__, "turva": turva}))
    fi = pyynto("/")[2]
    # kiinni oletuksena, otsikot (punaiset) näkyvissä, koko teksti avattuna; merkintöjen yläpuolella
    assert '<details class="turva"><summary><span class="turva-otsikko">🥶 Kylmä vesi' in fi
    assert '<span class="turva-otsikko">🥶 Kylmä vesi: kuivapuku</span></summary>' in fi   # vain ensimmäinen
    assert '<span class="turva-otsikko">💨' not in fi and "<h3>💨 Maatuuli ja matala vesi</h3>" in fi
    assert "itätuulta 6 m/s" in fi and "Mustasalmi" in fi
    assert fi.index('<details class="turva">') < fi.index('<details class="selitykset" id="merkinnat">') \
        < fi.index('<details class="ehdota" id="paneeli-ehdota">')
    assert 'id="turva"' not in fi and "turva-tausta" not in fi   # ei ponnahdusikkunaa
    en = pyynto("/", "kieli=en")[2]
    assert "Cold water: dry suit" in en and "Offshore wind on the Oulu coast" in en
    monkeypatch.setattr(app, "hae_tilanne", lambda **_: app.Tilanne(**{**tilanne.__dict__, "turva": {}}))
    ilman = pyynto("/")[2]
    assert ('<details class="turva">' in ilman) == any(
        l is not None and l.veden_lampotila is not None and l.veden_lampotila < 15
        for t in tilanne.tulokset for l in t.lukemat.values())


def test_paikkasivu_vesitilanne_ylimpana(monkeypatch, tilanne):
    """Paikkasivun alussa sama vesitilanne kuin etusivulla (pisteet, mittarit, kohteet); ei valokuvia."""
    monkeypatch.setattr(app, "_paikkasivun_tilanne", lambda: tilanne)
    nimi = tilanne.tulokset[0].paikka.nimi
    osoite = app.paikan_osoite(tilanne.tulokset[0].paikka)
    runko = pyynto(osoite)[2]
    assert '<section class="paikan-tilanne" data-paiva0="' in runko and "<h2>Vesitilanne</h2>" in runko
    assert 'class="olot' in runko and f'<div class="tilanne-rivi" data-paikka="{nimi}"' in runko
    # sama skripti kuin etusivulla: lähtöaika, sää perillä ja kaaviolinkkien reissu pysyvät samassa ajassa
    assert 'id="lahtoaika"' in runko and "melonta-lahtoaika" in runko
    # mittarilinkissä aseman nimen sijaan suure
    assert ">Vedenkorkeus: " in runko or ">Virtaama: " in runko
    assert "Listaus pisteiden mukaan" in pyynto("/")[2]
    assert runko.index('class="paikan-tilanne"') < runko.index("<h2>Lähteet</h2>")
    assert "upload.wikimedia" not in runko and "<figure" not in runko and nimi in runko


def test_piilotetut_kortit_eivat_nay(palvelin):
    """Korttien display-tyyli ei saa ohittaa hidden-attribuuttia (haku ja suosikit piilottavat rivejä)."""
    runko = pyynto("/")[2]
    assert ".etusivu tbody tr[hidden] { display:none; }" in runko.replace(".etusivu td.sija, .etusivu td.ennuste, ", "")
    assert "ilmanOsio.hidden = vainSuosikit" in runko


def test_omat_kuvat_ja_alapalkki(palvelin):
    """Sovelluksen tekijän oma kuva tarjoillaan sovelluksesta; alapalkissa pelkät kuvakkeet."""
    vastaus = {}
    runko = b"".join(app.app({"PATH_INFO": "/omat-kuvat/maalismaa.jpg", "QUERY_STRING": "", "REQUEST_METHOD": "GET",
                              "wsgi.input": io.BytesIO()}, lambda s, o: vastaus.update(s=s, o=dict(o))))
    assert vastaus["s"] == "200 OK" and vastaus["o"]["Content-Type"] == "image/jpeg" and runko[:2] == b"\xff\xd8"
    assert pyynto("/omat-kuvat/../app.py")[0] == "404 Not Found"
    from pathlib import Path
    assert all((Path(app.__file__).with_name("omat_kuvat") / t).exists() for t in app.kuvat.OMAT.values())
    runko = pyynto("/")[2]
    palkki = runko.split('<nav class="alapalkki"')[1].split("</nav>")[0]
    assert 'aria-label="Surffi: ei surffattavaa"' in palkki and "</span>Surffi" not in palkki
    assert "text-align:center" in runko



def test_etusivun_tilarivit_poissa(palvelin):
    """Etusivulla ei näytetä tilarivejä (ajomatkojen lähtöpaikka, lähtöpäivän ennuste) eikä taulukon otsikkoa."""
    runko = pyynto("/")[2]
    assert ".etusivu thead { display:none; }" in runko and 'id="paiva-tila"' not in runko
    assert "tila.textContent = teksti" not in runko   # onnistunut ajomatkahaku ei kirjoita tilariviä


def test_nimeton_asema_vesitilanteena():
    """Nimettömän aseman tunnuksen (esim. käyttäjän ehdottaman kohteen mittari) tilalla 'Vesitilanne'."""
    assert app.aseman_nimi("60/q6000110y/qinlyhyt.png") == "Vesitilanne"
    paikka = next(p for p in PAIKAT if p.mittarit)
    assert app._kaavion_otsikko(paikka, "60/q6000110y/qinlyhyt.png", "fi") == f"{paikka.nimi} – Vesitilanne"
    assert app._kaavion_otsikko(paikka, "60/q6000110y/qinlyhyt.png", "en") == f"{paikka.nimi} – Water situation"



def test_surffin_merkkivalo_ja_selitykset():
    """Surffikuvakkeen merkkivalo kertoo, onko surffattavaa; selityksissä alapalkin kuvakkeet."""
    k_ = lambda t: t   # noqa: E731
    assert 'class="surffi-nyt" aria-label="Surffi: surffattavaa nyt"' in app._surffinappi({"nyt": ["tauvo"]}, k_)
    assert 'class="surffi-ennuste"' in app._surffinappi({"nyt": [], "ennuste": ["yppari"]}, k_)
    assert 'class="surffi-ei"' in app._surffinappi({}, k_)
    selitykset = app._selitykset("fi")
    for teksti in ("Alapalkin kuvakkeet", "surffattavaa nyt", "ennusteessa", "ei surffattavaa", "<b><svg class=\"nasta\"",
                   "<b>🔔</b>", "<b>💡</b>", "<b>ⓘ</b>", "In English"):
        assert teksti in selitykset, teksti
    assert "Bottom bar icons" in app._selitykset("en")



def test_tilanne_tallessa_ja_paikkasivu_ilman_laskentaa(monkeypatch, tilanne):
    """Kylmä käynnistys lukee tallennetun tilanteen; paikkasivu ei odota laskentaa vaan hakee vesitilanteen
    jälkikäteen (/api/vesitilanne)."""
    class Kanta:
        data = {}

        def lue(self, k, t):
            return self.data.get((k, t))

        def kirjoita(self, k, t, d):
            self.data[(k, t)] = d

        def listaa(self, *a, **k):
            return {}
    kanta = Kanta()
    monkeypatch.setattr(app, "_kanta", lambda: kanta)
    monkeypatch.setattr(app, "_ehdotukset", None)   # ehdotusten välimuisti palautuu testin jälkeen
    paikat = tuple(t.paikka for t in tilanne.tulokset)
    monkeypatch.setattr(app, "kaikki_paikat", lambda: paikat)
    monkeypatch.setattr(app, "suomen_aika", lambda: tilanne.paivitetty)
    monkeypatch.setattr(app, "_tilanne", None)
    assert app.hae_tilanne(laske=False) is None   # ei muistissa eikä tallessa: ei lasketa
    app._tallenna_tilanne(tilanne, paikat)
    ladattu = app.hae_tilanne(laske=False)
    assert ladattu is not None and [t.paikka.nimi for t in ladattu.tulokset] == [t.paikka.nimi for t in tilanne.tulokset]
    monkeypatch.setattr(app.melonta, "kerää_tilanne", lambda *a, **k: (_ for _ in ()).throw(AssertionError("laskettiin")))
    assert app.hae_tilanne() is not None and app._tilanne is not None   # kylmä käynnistys: tallennetusta
    kanta.data[app.TILANNE_DOKUMENTTI]["muoto"] = "toinen"   # eri rakenteen tilannetta ei käytetä
    monkeypatch.setattr(app, "_tilanne", None)
    assert app.hae_tilanne(laske=False) is None
    # paikkasivu ilman valmista tilannetta: osio haetaan jälkikäteen, lyhyt välimuisti
    sivu = app.paikkasivu(paikat[0], "fi", None)
    assert 'id="vesitilanne-tulossa"' in sivu and "/api/vesitilanne?paikka=" in sivu
    monkeypatch.setattr(app, "hae_tilanne", lambda **_: tilanne)
    status, otsakkeet, runko = pyynto("/api/vesitilanne", "paikka=" + quote(paikat[0].nimi))
    assert status == "200 OK" and '<section class="paikan-tilanne"' in runko and "<script>" in runko
    assert pyynto("/api/vesitilanne", "paikka=Tuntematon")[0] == "404 Not Found"


def test_paikkasivulla_yksi_reitti(monkeypatch, tilanne):
    """Pisteytettävän paikan sivulla reitti vain vesitilanteessa, ei otsikon alla."""
    t = next(x for x in tilanne.tulokset if x.pisteet is not None and x.paikka.sijainti)
    sivu = app.paikkasivu(t.paikka, "fi", tilanne)
    meta = sivu.split('<div class="meta">')[1].split("</div>")[0]
    assert "🗺 Kartta" in meta and "Reitti" not in meta and sivu.count("🚗 Reitti") == 1


def test_kortin_tilamerkki_kohteiden_mukaan(palvelin, tilanne):
    """Kortin tilamerkki paikan parhaan kohteen mukaan: ★ Parhaimmillaan, ✓ Toimii tai ✗ Ei toimi."""
    from types import SimpleNamespace as K
    assert app._paras_tila([K(tila="ei toimi"), K(tila="paras")]) == "paras"
    assert app._paras_tila([K(tila="ei toimi"), K(tila="toimii")]) == "toimii"
    assert app._paras_tila([K(tila="ei toimi")]) == "ei toimi"
    runko = pyynto("/")[2]
    t = next(x for x in tilanne.tulokset if x.pisteet is not None)
    rivi = runko[runko.index(f'<tr data-paikka="{t.paikka.nimi}"'):]
    odotettu = {"paras": "★ Parhaimmillaan", "toimii": "✓ Toimii", "ei toimi": "✗ Ei toimi"}[app._paras_tila(t.kohteet)]
    assert f">{odotettu}</span>" in rivi[:rivi.index("</tr>")] and "data-tilat='" in rivi
    assert "Erinomaiset olot" not in runko and "★ At its best" in pyynto("/", "kieli=en")[2]


def test_kategoria_muistetaan(palvelin):
    """Valittu kategoria tallennetaan selaimeen ja sovellus avautuu siihen (vain etusivun avauksessa)."""
    runko = pyynto("/")[2]
    assert "localStorage.setItem(&quot;melonta-kategoria&quot;, this.value)" in runko
    alku = runko.split("</head>")[0]
    assert app.KATEGORIA_MUISTI in alku and "location.replace(valittu)" in alku


def test_esilaskenta_ja_tilanteen_muoto(monkeypatch, tilanne):
    """Cron laskee tilanteen valmiiksi; tallennettu tilanne kelpaa uudelle julkaisulle, jos rakenne on sama."""
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert app.esilaske({})[0].startswith("503")
    monkeypatch.setenv("CRON_SECRET", "s")
    assert app.esilaske({"HTTP_AUTHORIZATION": "Bearer väärä"})[0].startswith("401")
    assert len(app.TILANNE_MUOTO) == 12 and app._tilanteen_muoto() == app.TILANNE_MUOTO
    import json as json_
    crons = json_.load(open(Path(app.__file__).with_name("vercel.json")))["crons"]
    esilaskennat = [c for c in crons if c["path"] == "/api/esilaske"]
    assert len(esilaskennat) >= 10 and all(c["schedule"].split()[2:] == ["*", "*", "*"] for c in esilaskennat)
    assert len(crons) <= 20   # Vercelin ilmaisversio: kerran päivässä, rajattu määrä


def test_vanha_tilanne_heti_ja_laskenta_taustalla(monkeypatch, tilanne):
    """Saman päivän vanha tilanne näytetään heti (ei odoteta laskentaa); sivu pyytää uuden laskennan taustalla."""
    paikat = tuple(t.paikka for t in tilanne.tulokset)
    monkeypatch.setattr(app, "kaikki_paikat", lambda: paikat)
    monkeypatch.setattr(app, "suomen_aika", lambda: tilanne.paivitetty + dt.timedelta(hours=5))
    monkeypatch.setattr(app, "_tilanne", (app.time.monotonic() - 5 * 3600, tilanne))
    monkeypatch.setattr(app, "_tilanteen_paikat", {p.nimi for p in paikat})
    monkeypatch.setattr(app.melonta, "kerää_tilanne", lambda *a, **k: (_ for _ in ()).throw(AssertionError("laskettiin")))
    assert app.hae_tilanne(vanha_kelpaa=True) is tilanne and app.tilanne_vanha(tilanne)
    status, otsakkeet, runko = pyynto("/")
    assert status == "200 OK" and otsakkeet["Cache-Control"] == app.ODOTUS_CACHE
    assert 'fetch("/api/esilaske?tausta=1"' in runko
    # taustapyyntö ei tarvitse cron-tunnistetta (laskee vain, jos tilanne on vanha)
    laskettu = []
    monkeypatch.setattr(app, "hae_tilanne", lambda **_: laskettu.append(1) or tilanne)
    assert pyynto("/api/esilaske", "tausta=1")[0] == "200 OK" and laskettu == [1]
    assert pyynto("/api/esilaske")[0] != "200 OK"   # ilman taustamerkintää vaatii tunnisteen


def test_eilinen_tilanne_kelpaa_avaukseen(monkeypatch, tilanne):
    """Avaus ei odota laskentaa vuorokauden vaihduttuakaan: eilinen tilanne heti, uusi laskenta taustalla."""
    paikat = tuple(t.paikka for t in tilanne.tulokset)
    monkeypatch.setattr(app, "kaikki_paikat", lambda: paikat)
    monkeypatch.setattr(app, "suomen_aika", lambda: tilanne.paivitetty + dt.timedelta(hours=20))
    monkeypatch.setattr(app, "_tilanne", (app.time.monotonic() - 20 * 3600, tilanne))
    monkeypatch.setattr(app, "_tilanteen_paikat", {p.nimi for p in paikat})
    monkeypatch.setattr(app.melonta, "kerää_tilanne", lambda *a, **k: (_ for _ in ()).throw(AssertionError("laskettiin")))
    assert (app.suomen_aika().date() - tilanne.paivitetty.date()).days == 1
    assert app.hae_tilanne(vanha_kelpaa=True) is tilanne and app.hae_tilanne(laske=False) is tilanne
    assert 'fetch("/api/esilaske?tausta=1"' in pyynto("/")[2]


def test_takaisin_sulkee_luukun(palvelin):
    """Kategorian vaihto ei lisää historiaan; puhelimen takaisin-nappi sulkee avatun luukun."""
    runko = pyynto("/")[2]
    assert "location.replace(this.value)" in runko and "location.href = this.value" not in runko
    assert 'history.pushState({luukku: true}, "")' in runko and 'addEventListener("popstate"' in runko


def test_tuntikaavion_vertailutekstit_eivat_paallekkain():
    """Samalla arvolla olevat vertailuarvot (esim. eilen mitattu ja SYKE:n päiväarvo) allekkain."""
    import re
    tunnit = {"arviot": {0: 108.163, 6: 108.165}, "ennuste": {6: 108.165, 23: 108.171}, "keskiarvo": 108.167, "viim": 6}
    kuva = kaavio_svg.tunti_svg("Kipinä", dt.date(2026, 10, 30), tunnit,
                                [("eilen mitattu", 108.16, "#000"), ("SYKE päiväarvo", 108.16, "#e67700")])
    ET.fromstring(kuva)
    rivit = sorted(float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)" text-anchor="end" fill="#(?:000|e67700)"', kuva))
    assert len(rivit) == 2 and rivit[1] - rivit[0] >= 14
