import datetime as dt
import shutil
from pathlib import Path

import pytest

import arviointi
import melonta
import osm_sivut as osm
from paikat import PAIKAT, Kohde, Mittari, Paikka, aseman_nimi
from syke_kaavio import KaavioLukija, Kaaviolukema

FIXTURES = Path(__file__).parent / "fixtures"


def lukema(arvo, yksikko="m", **kw):
    return Kaaviolukema(url="u", suure="vedenkorkeus", yksikko=yksikko, tanaan_paiva=18,
                        havaittu=arvo, havaittu_paivia_sitten=0, malli=arvo, **kw)


KOHDE = Kohde("Testihontto", (10.0, 11.0), (10.4, 10.6))


@pytest.mark.parametrize("v, tila, pisteet", [
    (10.5, "paras", 100),
    (10.4, "paras", 100),
    (10.2, "toimii", 80),     # puolivälissä toimivan reunan ja parhaan välillä
    (10.0, "toimii", 60),
    (11.0, "toimii", 60),
    (9.85, "ei toimi", 22.5),  # puolet marginaalista (0.3 m) alarajan alla
    (12.0, "ei toimi", 0),
])
def test_kohteen_pisteet(v, tila, pisteet):
    t = arviointi.pisteyta_kohde(KOHDE, v, 0.3, "m")
    assert t.tila == tila
    assert t.pisteet == pytest.approx(pisteet)


def test_avoimet_rajat_ja_laatu():
    k = Kohde("Aalto", (600, None), (850, None), laatu=0.5)
    assert arviointi.pisteyta_kohde(k, 2000, 200, "m3/s").pisteet == 50
    t = arviointi.pisteyta_kohde(k, 400, 200, "m3/s")
    assert t.tila == "ei toimi" and t.pisteet == 0
    assert "puuttuu 200 m³/s" in t.selitys


def test_paikan_pisteet_lisa_toimivista_kohteista():
    p = Paikka("P", "u", "peli", 10, "", {"paa": Mittari("x", marginaali=0.3)}, (
        Kohde("A", (10.0, 11.0), (10.4, 10.6)),
        Kohde("B", (10.0, 11.0), (10.9, 11.0), laatu=0.5),
        Kohde("C", (12.0, 13.0), (12.0, 13.0)),
    ))
    t = arviointi.arvioi(p, {"paa": lukema(10.5)})
    # A paras, B toimii (laatu 0.5), C ei toimi: 90 + 9 × (1 + ½ × 0.5) / 2.5
    assert t.pisteet == pytest.approx(94.5)
    t = arviointi.arvioi(p, {"paa": lukema(10.2)})
    # ei parhaita: A toimii puolivälissä (60 + 25 × ½) + B toimii (+2)
    assert t.pisteet == pytest.approx(72.5 + 2)
    assert [k.kohde.nimi for k in t.toimivat] == ["A", "B"]


def test_tulvaindeksi_muuttujana():
    p = Paikka("P", "u", "retki", 10, "", {"paa": Mittari("x")},
               (Kohde("Tulva", (0.7, None), (0.85, None), muuttuja="tulvaindeksi"),))
    l = lukema(11.9, tunnusluvut={"MHW": 12.0, "MNW": 10.0})   # indeksi 0.95
    assert arviointi.arvioi(p, {"paa": l}).pisteet == 100
    l = lukema(11.0, tunnusluvut={"MHW": 12.0, "MNW": 10.0})   # indeksi 0.5
    assert arviointi.arvioi(p, {"paa": l}).kohteet[0].tila == "ei toimi"


def test_ennustepisteet():
    p = Paikka("P", "u", "peli", 10, "", {"paa": Mittari("x", marginaali=0.3)}, (KOHDE,))
    l = lukema(10.5, ennuste={1: 10.5, 2: 10.2, 3: 9.0})
    t = arviointi.arvioi(p, {"paa": l})
    assert t.ennuste == {1: 100, 2: pytest.approx(72.5), 3: 0}


def test_jarjestys_tasapisteissa_lahempi_ensin():
    def t(nimi, pisteet, km):
        return arviointi.PaikkaTulos(Paikka(nimi, nimi, "peli", km, ""), pisteet)
    jarj = arviointi.jarjesta([t("kaukana", 91, 300), t("lahella", 89, 20), t("ei", None, 1), t("huono", 40, 5)])
    assert [x.paikka.nimi for x in jarj] == ["lahella", "kaukana", "huono", "ei"]


def test_paikkojen_konfiguraatio_on_eheaa():
    nimet = set()
    for p in PAIKAT:
        assert p.nimi not in nimet
        nimet.add(p.nimi)
        assert p.tyyppi in ("peli", "retki")
        for k in p.kohteet:
            assert k.mittari in p.mittarit, (p.nimi, k.nimi)
            assert k.muuttuja in ("arvo", "tulvaindeksi")
            for (ta, ty), (pa, py) in [(k.toimii, k.paras)]:
                # paras alue on toimivan alueen sisällä
                assert ta is None or pa is None or pa >= ta, (p.nimi, k.nimi)
                assert ty is None or py is None or py <= ty, (p.nimi, k.nimi)


# ---------------------------------------------------------------------------
# osm.fi-sivujen jäsennys
# ---------------------------------------------------------------------------

def test_sivun_kaaviot():
    html = (FIXTURES / "sivut" / "kipinae.html").read_text(encoding="utf-8")
    assert osm.sivun_kaaviot(html) == [
        "61/l611331001y/w3lyhyt.png", "61/q6101400y/qinlyhyt.png", "61/q6101400y/twlyhyt.png"]
    html = (FIXTURES / "sivut" / "liminganjoki.html").read_text(encoding="utf-8")
    assert osm.sivun_kaaviot(html) == ["58/q5800100y/wlyhyt.gif"]   # iframe, kuollut linkki


def test_sivujen_kaaviot_vastaavat_konfiguraatiota():
    for slug in ("kipinae", "matkakoski"):
        html = (FIXTURES / "sivut" / f"{slug}.html").read_text(encoding="utf-8")
        paikka = next(p for p in PAIKAT if osm.normalisoi(p.url) == slug)
        for m in paikka.mittarit.values():
            assert m.lisakaavio or m.kaavio in osm.sivun_kaaviot(html)


def test_hakemistosta_ei_loydy_analysoimattomia_paikkoja():
    html = (FIXTURES / "sivut" / "melontapaikat.html").read_text(encoding="utf-8")
    tunnetut = {osm.normalisoi(p.url) for p in PAIKAT} | melonta.EI_PAIKKOJA
    linkit = osm.melontapaikkojen_linkit(html)
    assert len(linkit) >= 20
    assert [u for u in linkit if osm.normalisoi(u) not in tunnetut] == []


# ---------------------------------------------------------------------------
# Päästä päähän (offline): sivut + kaaviot välimuistikansiosta
# ---------------------------------------------------------------------------

def test_paasta_paahan_offline(tmp_path, capsys):
    valimuisti = tmp_path / "aineisto"
    valimuisti.mkdir()
    paikat = [p for p in PAIKAT if osm.normalisoi(p.url) in ("kipinae", "matkakoski", "niskakoski")]
    for p in paikat:
        lahde = FIXTURES / "sivut" / f"{osm.normalisoi(p.url)}.html"
        shutil.copy(lahde, valimuisti / osm.Hakija._tiedostonimi(p.url))
    for kuva in FIXTURES.glob("*.png"):
        avain = kuva.name.replace("_", "/", 2)
        shutil.copy(kuva, valimuisti / osm.Hakija._tiedostonimi(osm.kaavio_url(avain)))

    hakija = osm.Hakija(offline=valimuisti)
    sivun_kaaviot, lukemat, varoitukset = melonta.kerää_tilanne(hakija, tuple(paikat), tarkista_hakemisto=False)
    assert varoitukset == []
    tulokset = melonta.arvioi_kaikki(paikat, sivun_kaaviot, lukemat, dt.date(2026, 10, 18))
    nimet = [t.paikka.nimi for t in tulokset]
    # Kipinä: Pudasjärvi 108.59 m -> oikean silta-aukon surffiaalto parhaimmillaan, muut eivät toimi
    # Matkakoski 27.95 m -> Matkan aalto parhaimmillaan ja peliajan paikat toimivat
    # Niskakoski 15 m³/s -> stoppari vaatii yli 50 m³/s (0 p.)
    # (jokin kohde parhaimmillaan -> vähintään 90; tasapisteissä 5 pisteen tarkkuudella lähempi ensin)
    assert nimet == ["Kipinä (Iijoki)", "Matkakoski (Tornionjoki)", "Niskakoski (Lestijoki)"]
    assert tulokset[0].pisteet == pytest.approx(90 + 9 * 0.8 / 2.65)
    assert tulokset[0].paras_kohde.kohde.nimi == "Oikean silta-aukon surffiaalto"
    assert tulokset[1].pisteet == pytest.approx(90 + 9 * (0.9 + 0.5) / 4.1)
    assert tulokset[1].paras_kohde.kohde.nimi == "Matkan aalto"
    assert tulokset[2].pisteet == 0
    assert not any("ei ole tältä päivältä" in h for t in tulokset for h in t.huomiot)

    # vanhentunut kaavio havaitaan
    vanhat = melonta.arvioi_kaikki(paikat, sivun_kaaviot, lukemat, dt.date(2026, 10, 19))
    assert any("ei ole tältä päivältä" in h for t in vanhat for h in t.huomiot)

    melonta.tulosta(tulokset, varoitukset, dt.date(2026, 10, 18), laaja=True)
    tuloste = capsys.readouterr().out
    assert "Veden lämpötila (Kipinä): 2.8 °C" in tuloste
    assert " 1. Kipinä (Iijoki)" in tuloste and " 2. Matkakoski (Tornionjoki)" in tuloste


# ---------------------------------------------------------------------------
# Kutujoki: Otermajärven lähtövirtaama (SYKE 59/q5903470y), rajat arvioita
# ---------------------------------------------------------------------------

def test_kutujoen_mittari_ja_arviorajat():
    kutujoki = next(p for p in PAIKAT if p.nimi == "Kutujoki")
    mittari = kutujoki.mittarit["paa"]
    assert mittari.kaavio == "59/q5903470y/qin3lyhyt.png" and mittari.lisakaavio   # osm.fi:n sivulla ei kaaviota
    assert aseman_nimi(mittari.kaavio) == "Otermajärvi, luusua (Kutujoki)"
    korkeus = kutujoki.mittarit["korkeus"]   # järven vedenkorkeus rinnalla, ei kohteita
    assert korkeus.kaavio == "59/l592621001y/w3lyhyt.png" and korkeus.lisakaavio
    assert aseman_nimi(korkeus.kaavio) == "Otermanjärvi"
    assert all(k.mittari == "paa" for k in kutujoki.kohteet)
    assert [k.lahde for k in kutujoki.kohteet] == ["arvio", "arvio"]
    assert any("Petäjäkoski" in k.nimi for k in kutujoki.kohteet)


def test_kutujoki_otermajarven_kaaviosta():
    """22.10.2026: syystulva, lähtövirtaama 10.2 m³/s (MHQ 18.1, MNQ 1.2), järvi 141.12 m."""
    url = osm.kaavio_url("59/q5903470y/qin3lyhyt.png")
    l = KaavioLukija().lue((FIXTURES / "59_q5903470y_qin3lyhyt.png").read_bytes(), url)
    assert l.suure == "virtaama" and l.yksikko == "m3/s"
    assert l.arvo == pytest.approx(10.15, abs=0.2)
    assert l.tunnusluvut == {"MHQ": 18.1, "MNQ": 1.2}

    korkeus = KaavioLukija().lue((FIXTURES / "59_l592621001y_w3lyhyt.png").read_bytes(),
                                 osm.kaavio_url("59/l592621001y/w3lyhyt.png"))
    assert korkeus.suure == "vedenkorkeus" and korkeus.arvo == pytest.approx(141.12, abs=0.03)
    assert korkeus.tunnusluvut == {"MHW": 141.38, "MNW": 140.30}

    kutujoki = next(p for p in PAIKAT if p.nimi == "Kutujoki")
    t = arviointi.arvioi(kutujoki, {"paa": l, "korkeus": korkeus})
    assert [k.tila for k in t.kohteet] == ["paras", "paras"]
    assert t.pisteet == 100   # molemmat kohteet parhaimmillaan


@pytest.mark.parametrize("virtaama, reitti, kosket", [
    (2.5, "ei toimi", "ei toimi"),   # loppukesän alivesi
    (4.5, "toimii", "ei toimi"),
    (9.0, "paras", "paras"),          # kesäkuun alun mediaani
    (17.0, "toimii", "paras"),
    (35.0, "ei toimi", "ei toimi"),   # lähellä HQ:ta (44 m³/s)
])
def test_kutujoen_rajat(virtaama, reitti, kosket):
    kutujoki = next(p for p in PAIKAT if p.nimi == "Kutujoki")
    t = arviointi.arvioi(kutujoki, {"paa": lukema(virtaama, yksikko="m3/s")})
    assert [k.tila for k in t.kohteet] == [reitti, kosket]


# ---------------------------------------------------------------------------
# Tervajoki: ei omaa asemaa, mittarina Otermanjärven tulovirtaama (4 vrk ka)
# ---------------------------------------------------------------------------

def test_tervajoki_otermanjarven_tulovirtaamasta():
    """22.10.2026: tulovirtaama 7.5 m³/s (vesitaseesta laskettu, kaaviossa ei tunnuslukuja)."""
    tervajoki = next(p for p in PAIKAT if p.nimi == "Tervajoki (Vaala)")
    mittari = tervajoki.mittarit["paa"]
    assert mittari.kaavio == "59/l592621001y/qin2lyhyt.png" and mittari.lisakaavio
    assert not tervajoki.osm_sivu and tervajoki.sijainti is not None
    assert [k.lahde for k in tervajoki.kohteet] == ["arvio"]

    l = KaavioLukija().lue((FIXTURES / "59_l592621001y_qin2lyhyt.png").read_bytes(),
                           osm.kaavio_url(mittari.kaavio))
    assert l.suure == "virtaama" and l.yksikko == "m3/s" and l.tunnusluvut == {}
    assert l.arvo == pytest.approx(7.5, abs=0.3)
    t = arviointi.arvioi(tervajoki, {"paa": l})
    assert t.kohteet[0].tila == "paras" and t.pisteet == 100   # ainoa kohde parhaimmillaan


@pytest.mark.parametrize("virtaama, tila", [
    (1.5, "ei toimi"),    # kesän alivesi
    (5.0, "toimii"),
    (17.0, "paras"),      # toukokuun mediaanihuippu
    (30.0, "toimii"),
    (50.0, "ei toimi"),
])
def test_tervajoen_rajat(virtaama, tila):
    tervajoki = next(p for p in PAIKAT if p.nimi == "Tervajoki (Vaala)")
    t = arviointi.arvioi(tervajoki, {"paa": lukema(virtaama, yksikko="m3/s")})
    assert t.kohteet[0].tila == tila


def test_paikan_pistetasot():
    """Jokin kohde parhaimmillaan -> vähintään 90, kaikki -> 100, pelkät toimivat -> enintään 85."""
    p = Paikka("P", "u", "peli", 10, "", {"paa": Mittari("x", marginaali=0.3)}, (
        Kohde("A", (10.0, 11.0), (10.4, 10.6), 0.5),
        Kohde("B", (10.0, 11.0), (10.5, 10.9)),
    ))
    assert arviointi.arvioi(p, {"paa": lukema(10.5)}).pisteet == 100
    assert arviointi.arvioi(p, {"paa": lukema(10.4)}).pisteet == pytest.approx(90 + 9 * (0.5 + 0.5) / 1.5)
    assert arviointi.arvioi(p, {"paa": lukema(10.8)}).pisteet == pytest.approx(90 + 9 * (1 + 0.25) / 1.5)
    toimii = arviointi.arvioi(p, {"paa": lukema(10.1)}).pisteet
    assert 60 <= toimii <= 85
    assert arviointi.arvioi(p, {"paa": lukema(11.0)}).pisteet <= 85
    assert arviointi.arvioi(p, {"paa": lukema(11.3)}).pisteet < 50
