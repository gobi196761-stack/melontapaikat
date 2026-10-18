"""Kaavionlukijan testit 18.10.2026 tallennetuilla SYKE-kaavioilla.

Odotetut arvot on luettu kaavioista silmämääräisesti. Osa kuvista ei ole
mukana glyfimallien rakentamisessa (PIDETYT), joten ne mittaavat tunnistusta
ennen näkemättömillä kuvilla.
"""

from pathlib import Path

import pytest

import syke_kaavio as sk

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def lukija():
    return sk.KaavioLukija()


def lue(lukija, nimi):
    url = "https://wwwi2.ymparisto.fi/i2/" + nimi.replace("_", "/", 2)
    return lukija.lue(FIXTURES / nimi, url=url)


# nimi: (havaittu, toleranssi, havainnon ikä pv, tunnusluvut)
ODOTETUT = {
    "67_q6702110y_wlyhyt.png": (27.95, 0.01, 0, {"MHW": 30.86, "MNW": 26.68}),
    "61_l611331001y_w3lyhyt.png": (108.59, 0.01, 0, {"MHW": 109.82, "MNW": 106.77}),
    "60_q6000410y_wlyhyt.png": (10.53, 0.01, 0, {"MHW": 11.59, "MNW": 9.65}),
    "67_q6701500y_wlyhyt.png": (77.45, 0.01, 0, {"MHW": 79.87, "MNW": 76.89}),
    "57_q5700700y_qinlyhyt.png": (90, 2, 0, {"MHQ": 334, "MNQ": 4.6}),
    "58_q5800100y_qinlyhyt.png": (6.0, 0.1, 0, {"MHQ": 21.8, "MNQ": 0.25}),
    "51_q5100500y_qinlyhyt.png": (15.0, 0.3, 0, {"MHQ": 96.6, "MNQ": 2.7}),
    # tänään ei havaintoa -> eilinen
    "61_q6101750y_qin3lyhyt.png": (398, 4, 1, {"MHQ": 803, "MNQ": 42.2}),
}

PIDETYT = {
    "54_q5400410y_qinlyhyt.png": (60.8, 1.5, 0, {"MHQ": 253, "MNQ": 4.9}),
    "59_q5904400y_qin3lyhyt.png": (9.08, 0.15, 0, {"MHQ": 17.8, "MNQ": 0.92}),
    "63_q6300210y_wlyhyt.png": (27.90, 0.01, 0, {"MHW": 29.07, "MNW": 26.97}),
    "04_q0400600y_wlyhyt.png": (138.95, 0.005, 0, {"MHW": 139.33, "MNW": 138.32}),
    "64_q6400410y_wlyhyt.png": (11.43, 0.01, 0, {"MHW": 12.43, "MNW": 10.44}),
}


@pytest.mark.parametrize("nimi", list(ODOTETUT) + list(PIDETYT))
def test_havainto_ja_tunnusluvut(lukija, nimi):
    arvo, tol, ika, tunnusluvut = {**ODOTETUT, **PIDETYT}[nimi]
    r = lue(lukija, nimi)
    assert r.havaittu == pytest.approx(arvo, abs=tol)
    assert r.havaittu_paivia_sitten == ika
    assert r.tunnusluvut == pytest.approx(tunnusluvut)
    assert r.tanaan_paiva == 18


def test_mallikaavio_ilman_havaintoja(lukija):
    r = lue(lukija, "58_q5800000y_qinlyhyt.png")      # Temmesjoki: vain malli
    assert r.havaittu is None
    assert r.malli == pytest.approx(26.5, abs=0.4)
    assert r.arvo == r.malli
    assert r.lahde == "malli"
    assert r.tunnusluvut == {}


def test_lampotila(lukija):
    r = lue(lukija, "61_q6101400y_twlyhyt.png")
    assert (r.suure, r.yksikko) == ("lampotila", "°C")
    assert r.arvo == pytest.approx(2.8, abs=0.1)
    # ennuste: 19.10. ~2.4 °C, 21.10. ~1.7 °C
    assert r.ennuste[1] == pytest.approx(2.4, abs=0.15)
    assert r.ennuste[3] == pytest.approx(1.7, abs=0.15)


def test_ennuste_ja_korjaus(lukija):
    # Pudasjärvi: havainto 108.59 mutta malli 108.44 -> ennusteen muutos lisätään havaintoon
    r = lue(lukija, "61_l611331001y_w3lyhyt.png")
    assert r.malli == pytest.approx(108.43, abs=0.02)
    muutos = r.ennuste[3] - r.malli
    assert r.ennuste_korjattu(3) == pytest.approx(r.havaittu + muutos)


def test_tulvaindeksi(lukija):
    r = lue(lukija, "04_q0400600y_wlyhyt.png")
    assert r.tulvaindeksi == pytest.approx((138.95 - 138.32) / (139.33 - 138.32), abs=0.01)


def test_historiallinen_vaihteluvali(lukija):
    r = lue(lukija, "57_q5700700y_qinlyhyt.png")  # Länkelä: harmaa ulottuu yläreunan yli
    assert r.hist_max_rajattu
    assert r.mediaani == pytest.approx(25, abs=3)
    r = lue(lukija, "64_q6400410y_wlyhyt.png")    # Simo: mediaani kaavion alareunassa
    assert r.mediaani is None


def test_asteikon_sovitus_hylkaa_virheellisen_tikin():
    pisteet = [(100.0, 30.0), (200.0, 20.0), (300.0, 10.0), (400.0, 0.0), (250.0, 99.0)]
    a, b = sk._sovita_asteikko(pisteet)
    assert a + b * 300 == pytest.approx(10.0)


def test_rikkinainen_kuva_antaa_kaaviovirheen(lukija):
    from PIL import Image
    import io
    puskuri = io.BytesIO()
    Image.new("RGB", (800, 400), "white").save(puskuri, "PNG")
    with pytest.raises(sk.KaavioVirhe):
        lukija.lue(puskuri.getvalue(), url="https://x/i2/1/q1y/wlyhyt.png")
