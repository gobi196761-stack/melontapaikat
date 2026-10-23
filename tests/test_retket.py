import retket
from test_app import pyynto


def test_retkisivu_ja_linkit():
    status, _, sivu = pyynto("/retki/kuusamon-tulvajoet")
    assert status == "200 OK" and "Kuusamon tulvajoet" in sivu and "kuivapuku" in sivu
    for osoite, _ in retket.RETKET["kuusamon-tulvajoet"]["paikat"]:
        assert pyynto(osoite)[0] == "200 OK", osoite
    assert 'href="/retki/kuusamon-tulvajoet"' in pyynto("/paikka/kuusinkijoki")[2]
    assert pyynto("/retki/ei-tallaista")[0].startswith("404")


def test_ei_henkilo_eika_ryhmakohtaisia_tietoja():
    sivu = pyynto("/retki/kuusamon-tulvajoet")[2]
    for sana in ("Hakoranta", "Tulikankaantie", "516", "booking", "pizzeria", "omakustan", "13.5", "jumiin",
                 "sovitaan"):
        assert sana.lower() not in sivu.lower(), sana


def test_siiponjoki_ilman_henkilotietoja():
    status, _, sivu = pyynto("/paikka/siiponjoki-kalajoki")
    assert status == "200 OK" and "Pleunantie 379" in sivu and "Konikarvontie 204" in sivu
    assert "64.210165" in sivu                      # Siiponkylän silta kartalla
    for sana in ("Laura", "vetäjä", "Liity ryhmään", "ryhmän jäsenistä", "2026"):
        assert sana not in sivu, sana
