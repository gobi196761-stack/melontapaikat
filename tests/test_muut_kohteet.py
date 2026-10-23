import html

import muut_kohteet
import paikkasivut
from paikat import PAIKAT
from test_app import pyynto


def test_aineisto():
    assert len(muut_kohteet.KOHTEET) >= 160
    assert len(muut_kohteet.HAKEMISTO) == len(muut_kohteet.KOHTEET)   # tunnisteet yksilöllisiä
    for k in muut_kohteet.KOHTEET:
        assert k["nimi"] and k["kokoelma"], k
        assert k["lahto"], k["nimi"]                    # lähtöpaikka päiväkirjasta
    assert sum(1 for k in muut_kohteet.KOHTEET if k.get("lahto_sijainti")) > 100


def test_luettelo_ja_sivu():
    status, _, runko = pyynto("/muut")
    assert status == "200 OK" and "<h1>Muut kohteet</h1>" in runko
    k = muut_kohteet.KOHTEET[0]
    assert f'href="/muut/{k["tunniste"]}"' in runko
    status, _, sivu = pyynto(f"/muut/{k['tunniste']}")
    assert status == "200 OK"
    assert "<h2>Lähtö- ja loppupaikka</h2>" in sivu and "<b>Lähtö:</b>" in sivu and "<b>Loppu:</b>" in sivu
    assert html.escape(muut_kohteet.LAHDE) in sivu
    lahteet = sivu.split("<h2>Lähteet</h2>")[1]
    assert "Timo Piirainen" in lahteet and "Piirainen</a>" not in lahteet   # päiväkirjaa ei linkitetä
    assert pyynto("/muut/ei-tallaista")[0].startswith("404")


def test_kaikki_sivut_avautuvat():
    for tunniste in muut_kohteet.HAKEMISTO:
        assert pyynto(f"/muut/{tunniste}")[0] == "200 OK", tunniste


def test_retkikohteilla_lahto_ja_loppu():
    for p in PAIKAT:
        if p.tyyppi != "retki":
            continue
        roolit = {r for r, _, _ in paikkasivut.LAHTO_LOPPU[p.nimi]}
        assert ("Lähtö" in roolit and "Loppu" in roolit) or "Lähtö ja loppu" in roolit, p.nimi
        sivu = pyynto(f"/paikka/{paikkasivut.tunniste(p.nimi)}")[2]
        assert "<h2>Lähtö- ja loppupaikka</h2>" in sivu, p.nimi
    sivu = pyynto("/paikka/kutujoki")[2]
    assert "Autiokosken sillan" in sivu and "openstreetmap.org/?mlat=64.6768" in sivu


def test_ei_henkilokohtaisia_tapaturmia():
    teksti = " ".join(" ".join(k.get("kuvaus", [])) for k in muut_kohteet.KOHTEET)
    for sana in ("kiertäjäkalvosi", "olkapää", "kaatumiseen", "melan katoamiseen", "jouduin", "matkanteko keskeytyi"):
        assert sana not in teksti, sana
    kauhava = next(k for k in muut_kohteet.KOHTEET if k["nimi"].startswith("Kauhavajoella"))
    assert kauhava["kuvaus"] == ["Lyhyt pätkä Kauhavajoen vauhdikkailla koskilla."]


def test_haku_luettelossa():
    runko = pyynto("/muut")[2]
    assert 'id="haku"' in runko and 'data-haku="Kajakilla kahden Kuusamon kylän väliä Kitkajoki' in runko
