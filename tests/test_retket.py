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
