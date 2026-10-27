import datetime as dt
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import app
import melonta
import osm_sivut as osm
import smhi_data
from paikat import PAIKAT

FIXTURES = Path(__file__).parent / "fixtures" / "smhi"
# Fixturet haettu 19.10.2026: Granselin tuorein havainto 119.0 m³/s klo 07.00 UTC,
# Männikön 82.7 m³/s; HydroNu-ennusteet tuotettu 18.10. klo 12.10.
NYT = dt.datetime(2026, 10, 19, 8, 0, tzinfo=dt.timezone.utc)
RUOTSI = ("Trollforsarna (Piteälven)", "Pahakurkkio (Kalixälven)")


def lue(nimi):
    return json.loads((FIXTURES / nimi).read_text(encoding="utf-8"))


def test_avaimet():
    assert smhi_data.on_smhi("smhi/1387/31914") and not smhi_data.on_smhi("67/q6702110y/wlyhyt.png")
    assert smhi_data.osat("smhi/1387/31914") == ("1387", "31914")
    assert smhi_data.kaavio_avain(smhi_data.havainto_url("1387")) == "smhi/1387"
    assert smhi_data.kaavio_avain("https://wwwi2.ymparisto.fi/i2/67/q6702110y/wlyhyt.png") is None


def test_lukema_havainnosta_ja_ennusteesta():
    l = smhi_data.lukema("1387", lue("hydroobs_1387.json"), lue("point_31914.json"), NYT)
    assert l.suure == "virtaama" and l.yksikko == "m3/s"
    assert l.havaittu == 119.0 and l.havaittu_paivia_sitten == 0
    assert l.tanaan_paiva == 19
    assert l.malli == pytest.approx(117.64632)                # mallin päiväarvo 19.10.
    assert sorted(l.ennuste) == list(range(1, 9))            # ennuste 27.10. asti
    # havainto + mallin muutos: 119 + (115.3181 - 117.64632)
    assert l.ennuste_korjattu(1) == pytest.approx(116.67178)
    assert l.tunnusluvut["MHQ"] == pytest.approx(465.0759365625)
    assert 0 < l.tulvaindeksi < 0.3
    assert l.hist_min <= l.mediaani <= l.hist_max
    assert l.lahde == "havainto, SMHI"


def test_vanha_havainto_ja_puuttuva_ennuste():
    l = smhi_data.lukema("1387", lue("hydroobs_1387.json"), lue("point_31914.json"),
                         NYT + dt.timedelta(days=1))
    assert l.havaittu_paivia_sitten == 1 and l.lahde == "havainto 1 pv sitten, SMHI"
    l = smhi_data.lukema("1387", lue("hydroobs_1387.json"), lue("point_31914.json"),
                         NYT + dt.timedelta(days=5))
    assert l.havaittu is None and l.lahde == "malli, SMHI"
    assert l.arvo == pytest.approx(110.82301)               # malli 24.10.
    l = smhi_data.lukema("11", lue("hydroobs_11.json"), None, NYT)
    assert l.arvo == 82.7 and l.malli is None and l.ennuste_korjattu(1) is None


def valimuisti(kansio: Path, ilman: tuple[str, ...] = ()) -> osm.Hakija:
    for asema, piste in (("1387", "31914"), ("11", "35732")):
        for tiedosto, url in ((f"hydroobs_{asema}.json", smhi_data.havainto_url(asema)),
                              (f"point_{piste}.json", smhi_data.ennuste_url(piste))):
            if tiedosto not in ilman:
                shutil.copy(FIXTURES / tiedosto, kansio / osm.Hakija._tiedostonimi(url))
    return osm.Hakija(offline=kansio)


def test_hae_varoittaa_puuttuvasta(tmp_path):
    hakija = valimuisti(tmp_path, ilman=("point_35732.json",))
    l, varoitukset = smhi_data.hae(hakija, "smhi/11/35732", NYT)
    assert l.arvo == 82.7 and l.ennuste == {}
    assert len(varoitukset) == 1 and "ennuste" in varoitukset[0]
    tyhja = tmp_path / "tyhja"
    tyhja.mkdir()
    hakija = valimuisti(tyhja, ilman=("hydroobs_11.json", "point_35732.json"))
    l, varoitukset = smhi_data.hae(hakija, "smhi/11/35732", NYT)
    assert l is None and len(varoitukset) == 2


@pytest.fixture
def ruotsi(tmp_path):
    paikat = tuple(p for p in PAIKAT if p.nimi in RUOTSI)
    assert len(paikat) == 2 and not any(p.osm_sivu for p in paikat)
    hakija = valimuisti(tmp_path)
    sivun_kaaviot, lukemat, varoitukset = melonta.kerää_tilanne(
        hakija, paikat, tarkista_hakemisto=False, prosessit=False, nyt=NYT)
    assert varoitukset == []
    return paikat, melonta.arvioi_kaikki(paikat, sivun_kaaviot, lukemat, NYT.date())


def test_ruotsin_paikat_jarjestyksessa(ruotsi, capsys):
    paikat, tulokset = ruotsi
    t = {t.paikka.nimi: t for t in tulokset}
    # Gransel 119 m³/s: Benbrytarforsen parhaimmillaan (alle 130) 80 p. + Alapätkä toimii 2 p.
    trollforsarna = t["Trollforsarna (Piteälven)"]
    assert trollforsarna.pisteet == pytest.approx(82)
    assert trollforsarna.paras_kohde.kohde.nimi == "Benbrytarforsen"
    # Männikkö 82.7 m³/s: koskisarja ja matalan veden hontto parhaimmillaan (0.8 × 100 + 2),
    # Åretsvågen vaatii n. 180 m³/s
    pahakurkkio = t["Pahakurkkio (Kalixälven)"]
    assert pahakurkkio.pisteet == pytest.approx(82)
    assert pahakurkkio.paras_kohde.kohde.nimi == "Koskisarja 1–7"
    assert {k.kohde.nimi: k.tila for k in pahakurkkio.kohteet}["Åretsvågen (ykköskönkään surffiaalto)"] == "ei toimi"
    assert set(trollforsarna.ennuste) == set(pahakurkkio.ennuste) == set(range(1, 9))   # testidatassa HydroNu-ennuste +8 pv asti
    assert not any("ei ole tältä päivältä" in h for t in tulokset for h in t.huomiot)

    melonta.tulosta(tulokset, [], NYT.date(), laaja=False)
    tuloste = capsys.readouterr().out
    assert "Gransel (Piteälven) virtaama 119 m³/s (havainto, SMHI), 3 pv: ↘" in tuloste
    assert "Männikkö (Kalixälven) virtaama 83 m³/s (havainto, SMHI)" in tuloste
    assert "pisteet lähipäivinä (+1…+14 pv)" in tuloste

    data = melonta.json_tulos(tulokset, [], NYT.date())
    mittari = next(p for p in data["paikat"] if p["nimi"].startswith("Trollforsarna"))["mittarit"]["paa"]
    assert mittari["asema"] == "Gransel (Piteälven)"
    assert mittari["ennuste"]["+1"] == pytest.approx(116.67178)


def test_ruotsin_paikat_sivulla(ruotsi):
    _, tulokset = ruotsi
    tilanne = app.Tilanne(dt.datetime(2026, 10, 19, 11, 0), tulokset, [], 2)
    sivu = app.sivu(tilanne, tulokset, {})
    assert "Trollforsarna (Piteälven)" in sivu and "Pahakurkkio (Kalixälven)" in sivu
    sivu = "".join(app.paikkasivu(t.paikka, "fi", tilanne) for t in tulokset)   # mittarilukemat paikkasivulla
    assert "Virtaama: 119 m³/s (havainto, SMHI)" in sivu   # linkissä aseman nimen sijaan suure
    # SMHI:n mittareista linkki vie itse piirrettyyn kaavioon, ei raakaan JSON-dataan
    assert '<a href="/kaavio/smhi/1387/31914?paikka=Trollforsarna+%28Pite%C3%A4lven%29">Virtaama:' in sivu
    assert smhi_data.havainto_url("1387") not in sivu


def test_smhi_kaavio(tmp_path, vaaka):
    kuva = app.smhi_kaavio_svg("smhi/11/35732", valimuisti(tmp_path), NYT)
    assert kuva.startswith("<svg") and kuva.rstrip().endswith("</svg>")
    ET.fromstring(kuva)   # kelvollista XML:ää
    assert "Pahakurkkio (Kalixälven) – mittari Männikkö (Kalixälven)" in kuva
    assert "ennuste tehty 18.10. klo 12.10 UTC" in kuva
    assert "MQ 102" in kuva and "MHQ 531" in kuva   # MHQ on yli kuvan: vain tekstinä
    assert "Åretsvågen (ykköskönkään surffiaalto)" in kuva and "Koskisarja 1–7 " in kuva and "(paras 80–190)" in kuva   # alueiden selitykset
    assert kuva.count("<circle") > 20                 # havainnot tunnin välein + selite
    assert '>19.10.</text>' in kuva                   # tänään-nimiö


def test_smhi_kaavio_tuntematon_tai_ilman_dataa(tmp_path):
    assert app.smhi_kaavio_svg("smhi/9999/1", valimuisti(tmp_path), NYT) is None
    tyhja = tmp_path / "tyhja"
    tyhja.mkdir()
    hakija = valimuisti(tyhja, ilman=("hydroobs_11.json", "point_35732.json"))
    assert app.smhi_kaavio_svg("smhi/11/35732", hakija, NYT) is None
    # pelkkä havainto riittää kuvaan
    osa = tmp_path / "osa"
    osa.mkdir()
    hakija = valimuisti(osa, ilman=("point_35732.json",))
    assert "<circle" in app.smhi_kaavio_svg("smhi/11/35732", hakija, NYT)
