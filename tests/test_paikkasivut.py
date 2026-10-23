import html

import app
import paikkasivut
from paikat import PAIKAT
from test_app import pyynto


def test_jokaisella_paikalla_kuvaus_ja_lahteet():
    assert set(paikkasivut.KUVAUKSET) == {p.nimi for p in PAIKAT}
    for nimi, kuvaus in paikkasivut.KUVAUKSET.items():
        assert kuvaus.johdanto, nimi
        assert kuvaus.lahteet, nimi
        assert all(url.startswith(("http://", "https://")) for _, url in kuvaus.lahteet), nimi


def test_tunnisteet_yksilollisia():
    assert paikkasivut.tunniste("Hawa'Ii (Iijoki, Maalismaa)") == "hawa-ii-iijoki-maalismaa"
    assert paikkasivut.tunniste("Lieksanjoki (Matkalahti – Siikakoski)") == "lieksanjoki-matkalahti-siikakoski"
    assert paikkasivut.tunniste("Pahakurkkio (Kalixälven)") == "pahakurkkio-kalixalven"
    assert len(app.PAIKKASIVUT) == len(PAIKAT)


def test_paikkasivu_kohteet_rajat_ja_lahteet():
    status, otsakkeet, runko = pyynto("/paikka/kipina-iijoki")
    assert status == "200 OK" and otsakkeet["Content-Type"].startswith("text/html")
    assert "<h1>Kipinä (Iijoki)</h1>" in runko
    assert "Kuusamontietä" in runko                       # koostekuvaus
    # kohteet ja rajat paikat.py:stä
    assert "Keskimmäisen silta-aukon hontto" in runko
    assert "toimii 107.65 m – 108.20 m, parhaimmillaan 107.75 m – 108.00 m" in runko
    assert "Pudasjärvi</a>, vedenkorkeus" in runko
    # lähteet lopussa, alkuperäinen sivu mukana
    lahteet = runko.split("<h2>Lähteet</h2>")[1]
    assert 'href="https://www.osm.fi/melontapaikat/kipinae/"' in lahteet
    assert "mpahkala.kapsi.fi" in lahteet


def test_kaikki_paikkasivut_avautuvat():
    for tunniste, paikka in app.PAIKKASIVUT.items():
        status, _, runko = pyynto(f"/paikka/{tunniste}")
        assert status == "200 OK", tunniste
        assert html.escape(paikka.url) in runko, tunniste
        for kohde in paikka.kohteet:
            assert html.escape(kohde.nimi) in runko, (tunniste, kohde.nimi)


def test_rajojen_muotoilu():
    assert app._rajat((250, None), "m3/s", "arvo") == "yli 250 m³/s"
    assert app._rajat((None, 27.5), "m", "arvo") == "alle 27.50 m"
    assert app._rajat((None, None), "m", "arvo") == "kaikilla vesillä"
    assert app._rajat((0.7, None), "m", "tulvaindeksi") == "tulvaindeksi yli 0.70"
    status, _, runko = pyynto("/paikka/oulujoki")
    assert "ei ole vesikaaviota" in runko


def test_tuntematon_paikka():
    status, _, _ = pyynto("/paikka/ei-tallaista")
    assert status.startswith("404")

