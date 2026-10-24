import io
import json
from urllib.parse import urlencode

import pytest

import app
import ehdotukset
import firestore
import halytykset
from paikat import PAIKAT

# Kipinän mittari (Pudasjärvi, vedenkorkeus) ja kohde, jonka rajoja korjataan
KIPINA = next(p for p in PAIKAT if p.nimi.startswith("Kipinä"))


class Kanta:
    def __init__(self):
        self.data: dict[str, dict[str, dict]] = {}

    def kirjoita(self, kokoelma, tunniste, data):
        self.data.setdefault(kokoelma, {})[tunniste] = json.loads(json.dumps(data))

    def lue(self, kokoelma, tunniste):
        return self.data.get(kokoelma, {}).get(tunniste)

    def listaa(self, kokoelma):
        return dict(self.data.get(kokoelma, {}))

    def poista(self, kokoelma, tunniste):
        self.data.get(kokoelma, {}).pop(tunniste, None)


TILAUS = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc",
          "keys": {"p256dh": halytykset.b64(b"\x04" + b"\x01" * 64), "auth": halytykset.b64(b"\x02" * 16)}}


@pytest.fixture
def ymparisto(monkeypatch):
    kanta = Kanta()
    lahetetyt = []
    monkeypatch.setattr(firestore.Firestore, "ymparistosta", classmethod(lambda cls, **kw: kanta))
    monkeypatch.setattr(halytykset, "avaimet", lambda kanta=None, uudelleen=False: ("JULKINEN", "YKSITYINEN"))
    monkeypatch.setattr(halytykset, "laheta", lambda tilaus, viesti, avainpari: lahetetyt.append(
        (tilaus["endpoint"], viesti)) or 201)
    monkeypatch.setattr(app, "_ehdotukset", None)
    monkeypatch.setattr(app, "_tilanne", None)
    monkeypatch.setattr(app, "_ehdotuksen_lukemat", lambda paikka, hakija: {})
    monkeypatch.setenv("YLLAPITO_SALASANA", "salainen")
    ehdotukset._lahetykset.clear()
    return kanta, lahetetyt


def pyynto(polku, kysely="", metodi="GET", runko: bytes = b"", evaste="", tyyppi="application/x-www-form-urlencoded"):
    vastaus = {}

    def start_response(status, otsakkeet):
        vastaus["status"], vastaus["otsakkeet"] = status, dict(otsakkeet)

    data = b"".join(app.app({"PATH_INFO": polku, "QUERY_STRING": kysely, "REQUEST_METHOD": metodi,
                             "CONTENT_LENGTH": str(len(runko)), "CONTENT_TYPE": tyyppi, "HTTP_COOKIE": evaste,
                             "REMOTE_ADDR": "10.0.0.1", "wsgi.input": io.BytesIO(runko)}, start_response))
    return vastaus["status"], vastaus["otsakkeet"], data.decode("utf-8")


def lomake(**kentat) -> bytes:
    return urlencode(kentat).encode()


def test_mittari_tekstista():
    assert ehdotukset.mittari_tekstista("7300350", "virtaama") == "73/q7300350y/qinlyhyt.png"
    assert ehdotukset.mittari_tekstista("6702110", "vedenkorkeus") == "67/w6702110y/wlyhyt.png"
    assert ehdotukset.mittari_tekstista("https://wwwi2.ymparisto.fi/i2/73/q7300350y/wqfi.html", "vedenkorkeus") \
        == "73/q7300350y/qinlyhyt.png"
    assert ehdotukset.mittari_tekstista("https://wwwi2.ymparisto.fi/i2/65/w6500910y/w3lyhyt.png", "virtaama") \
        == "65/w6500910y/w3lyhyt.png"
    assert ehdotukset.mittari_tekstista("ei asema", "virtaama") is None
    assert ehdotukset.sijainti_tekstista("https://www.google.com/maps/@66.155,29.564,14z") == (66.155, 29.564)
    assert ehdotukset.linkin_laji("https://youtu.be/xyz") == "video"
    assert ehdotukset.linkin_laji("https://www.vesi.fi/x") == "vesi"


def test_tulkitse_virheet():
    tulkitse = lambda **k: ehdotukset.tulkitse({a: [b] for a, b in k.items()}, PAIKAT)   # noqa: E731
    assert tulkitse(laji="uusi")[1] == "Anna kohteen nimi."
    assert tulkitse(laji="uusi", nimi="X", k1_nimi="A", k1_toimii_ala="abc")[1] == "Kohteen 1 rajat eivät ole lukuja."
    assert tulkitse(laji="uusi", nimi="X", k1_nimi="A", k1_toimii_ala="5", k1_toimii_yla="2")[1].startswith(
        "Kohteen 1 alaraja")
    assert tulkitse(laji="uusi", nimi="X", linkit="ftp://x")[1].startswith("Linkin pitää")
    assert tulkitse(laji="uusi", nimi="X")[1] == "Anna ainakin yksi kohde, linkki tai teksti."
    ehdotus, virhe = tulkitse(laji="uusi", nimi="Kitkajoki", mittari="7300350", k1_nimi="Käylä – Juuma",
                              k1_toimii_ala="25,5", linkit="https://youtu.be/a\nhttps://koskimelojat.blogspot.com/x")
    assert not virhe and ehdotus["kohteet"] == [{"nimi": "Käylä – Juuma", "toimii": [25.5, None],
                                                 "paras": [25.5, None], "huom": ""}]
    assert [l["laji"] for l in ehdotus["linkit"]] == ["video", "muu"]


def test_uusi_kohde_esikatselu_ilmoitus_ja_hyvaksynta(ymparisto):
    kanta, lahetetyt = ymparisto
    yllapito = halytykset.tunniste(TILAUS["endpoint"])
    kanta.kirjoita(ehdotukset.YLLAPITO, yllapito, {"endpoint": TILAUS["endpoint"], "p256dh": "x", "auth": "y"})
    status, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(
        laji="uusi", nimi="Kitkajoki (Käylä – Juuma)", tyyppi="retki", mittari="7300350", suure="virtaama",
        k1_nimi="Käylä – Juuma", k1_toimii_ala="20", k1_paras_ala="30", k1_paras_yla="60",
        linkit="https://koskimelojat.blogspot.com/2009/05/kitkajoki.html", teksti="Hieno joki.\n\nToinen kappale.",
        ehdottaja="Antti", verkkosivu=""))
    assert status == "303 See Other"
    osoite = otsakkeet["Location"]
    tunniste = osoite.removeprefix("/ehdotus/")
    assert ehdotukset.kelvollinen_tunniste(tunniste)
    assert kanta.lue(ehdotukset.KOKOELMA, tunniste)["tila"] == "odottaa"
    # ylläpitäjälle push heti
    assert lahetetyt == [(TILAUS["endpoint"], {"otsikko": "Uusi ehdotus: Kitkajoki (Käylä – Juuma)",
                                               "teksti": "uusi kohde: 1 kohdetta, 1 linkkiä – Antti",
                                               "url": osoite})]
    status, _, sivu = pyynto(osoite)
    assert status == "200 OK" and "odottaa hyväksyntää" in sivu and "Käylä – Juuma" in sivu
    assert "toimii yli 20 m³/s, parhaimmillaan 30 m³/s – 60 m³/s" in sivu
    assert "Hieno joki." in sivu and "koskimelojat.blogspot.com" in sivu and 'rel="nofollow ugc noopener"' in sivu
    assert "Hyväksy" not in sivu and 'id="ilmoita"' in sivu
    # ehdottaja tilaa ilmoituksen
    status, _, _ = pyynto(f"/api/ehdotus/{tunniste}/tilaus", metodi="POST", runko=json.dumps({"tilaus": TILAUS}).encode(),
                          tyyppi="application/json")
    assert status == "200 OK" and kanta.lue(ehdotukset.KOKOELMA, tunniste)["tilaus"]["endpoint"] == TILAUS["endpoint"]
    # käsittely vaatii kirjautumisen
    assert pyynto(f"{osoite}/kasittele", metodi="POST", runko=lomake(toiminto="hyvaksy"))[0] == "403 Forbidden"
    assert pyynto("/yllapito", metodi="POST", runko=lomake(salasana="väärä"))[0] == "403 Forbidden"
    status, otsakkeet, _ = pyynto("/yllapito", metodi="POST", runko=lomake(salasana="salainen"))
    evaste = otsakkeet["Set-Cookie"].split(";")[0]
    assert status == "303 See Other" and "HttpOnly" in otsakkeet["Set-Cookie"] and "SameSite=Strict" in otsakkeet["Set-Cookie"]
    sivu = pyynto("/yllapito", evaste=evaste)[2]
    assert "Odottaa hyväksyntää (1)" in sivu and tunniste in sivu
    assert "Hyväksy ja julkaise" in pyynto(osoite, evaste=evaste)[2]
    lahetetyt.clear()
    assert pyynto(f"{osoite}/kasittele", metodi="POST", runko=lomake(toiminto="hyvaksy"), evaste=evaste)[0] == "303 See Other"
    tallessa = kanta.lue(ehdotukset.KOKOELMA, tunniste)
    assert tallessa["tila"] == "hyvaksytty" and "tilaus" not in tallessa
    assert lahetetyt == [(TILAUS["endpoint"], {"otsikko": "Ehdotuksesi hyväksyttiin",
                                               "teksti": "Kitkajoki (Käylä – Juuma)", "url": osoite})]
    # julkaistu: etusivun luukussa
    assert f'href="/ehdotus/{tunniste}">Kitkajoki (Käylä – Juuma)</a>' in app._ehdotusluukku("fi")
    assert "hyväksytty ja julkaistu" in pyynto(osoite)[2]


def test_taydennys_paikkasivulle(ymparisto):
    kanta, _ = ymparisto
    vanha = KIPINA.kohteet[0]
    status, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(
        laji="taydenna", paikka=KIPINA.nimi, mittari_avain=next(iter(KIPINA.mittarit)),
        k1_nimi=vanha.nimi, k1_toimii_ala="107.6", k1_toimii_yla="108.2",
        k2_nimi="Uusi aalto", k2_toimii_ala="107.0", k2_huom="vain matalalla",
        linkit="https://www.youtube.com/watch?v=abc"))
    assert status == "303 See Other"
    tunniste = otsakkeet["Location"].removeprefix("/ehdotus/")
    sivu = pyynto(otsakkeet["Location"])[2]
    assert "Täydennys paikkaan: Kipinä (Iijoki)" in sivu
    # omat osiot: mitä muuttuu (nykyinen -> ehdotettu) ja mitä on tulossa lisää
    muuttuu = sivu.split('<h2 class="muuttuu">Muuttuu</h2>')[1].split('<h2 class="tulossa">')[0]
    tulossa = sivu.split('<h2 class="tulossa">Tulossa lisää</h2>')[1]
    assert vanha.nimi in muuttuu and "→ toimii 107.60 m – 108.20 m" in muuttuu and "nyt: toimii" in muuttuu
    assert "Uusi aalto" not in muuttuu and "Uusi aalto" in tulossa and "vain matalalla" in tulossa
    assert "<h3>Videot</h3>" in tulossa and "youtube.com/watch?v=abc" in tulossa
    paikkasivu = f"/paikka/{app.paikkasivut.tunniste(KIPINA.nimi)}"
    assert "Käyttäjien lisäykset" not in pyynto(paikkasivu)[2]
    kanta.data[ehdotukset.KOKOELMA][tunniste]["tila"] = "hyvaksytty"
    app._ehdotukset = None
    sivu = pyynto(paikkasivu)[2]
    assert "<h2>Käyttäjien lisäykset</h2>" in sivu and "Uusi aalto" in sivu and "youtube.com/watch?v=abc" in sivu
    assert '<h3 class="muuttuu">Muutettu</h3>' in sivu and '<h3 class="tulossa">Lisätty</h3>' in sivu


def test_roskat_ja_lomake(ymparisto):
    kanta, _ = ymparisto
    status, _, sivu = pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="X", teksti="t", verkkosivu="botti"))
    assert status == "400 Bad Request" and not kanta.listaa(ehdotukset.KOKOELMA)
    status, _, sivu = pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="X", k1_nimi="A",
                                                                     k1_toimii_ala="x"))
    assert status == "400 Bad Request" and "Kohteen 1 rajat eivät ole lukuja." in sivu and 'value="X"' in sivu
    for _ in range(ehdotukset.IP_RAJA[0]):
        pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="Y", teksti="t"))
    assert pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="Y", teksti="t"))[0] == "400 Bad Request"
    sivu = pyynto("/ehdota", "laji=taydenna&kieli=en")[2]
    assert '<html lang="en">' in sivu and "Add to a spot" in sivu and 'value="taydenna" checked' in sivu
    assert pyynto("/ehdotus/olematon-tunniste-123")[0].startswith("404")
    etusivu = app._ehdotusluukku("en")
    assert "Suggest a new spot" in etusivu and "/ehdota?laji=uusi&kieli=en" in etusivu


def test_skriptit_ja_sijainti(ymparisto, tmp_path):
    """Lomakkeen, esikatselun ja ylläpidon skriptit jäsentyvät; luukku on merkintöjen alla."""
    import shutil
    import subprocess
    kanta, _ = ymparisto
    _, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="X", teksti="t"))
    _, ylla, _ = pyynto("/yllapito", metodi="POST", runko=lomake(salasana="salainen"))
    sivut = [pyynto("/ehdota")[2], pyynto(otsakkeet["Location"])[2],
             pyynto("/yllapito", evaste=ylla["Set-Cookie"].split(";")[0])[2]]
    node = shutil.which("node")
    if not node:
        pytest.skip("node puuttuu")
    for i, sivu in enumerate(sivut):
        for j, osa in enumerate(sivu.split("<script>")[1:]):
            tiedosto = tmp_path / f"s{i}_{j}.js"
            tiedosto.write_text(osa.split("</script>")[0], encoding="utf-8")
            tulos = subprocess.run([node, "--check", str(tiedosto)], capture_output=True, text=True)
            assert tulos.returncode == 0, tulos.stderr


def test_uusi_kohde_vain_yksi_paikka(ymparisto):
    """Uutena kohteena vain yksi paikka: muut rivit ohitetaan, kohteen nimi on oletuksena paikan nimi."""
    kentat = {"laji": ["uusi"], "nimi": ["Aventojoki"], "mittari": ["7300350"], "k1_toimii_ala": ["10"],
              "k2_nimi": ["Toinen"], "k2_toimii_ala": ["5"]}
    ehdotus, virhe = ehdotukset.tulkitse(kentat, PAIKAT)
    assert not virhe and [k["nimi"] for k in ehdotus["kohteet"]] == ["Aventojoki"]
    kentat["k1_nimi"] = ["Aventojoki, alaosa"]
    assert [k["nimi"] for k in ehdotukset.tulkitse(kentat, PAIKAT)[0]["kohteet"]] == ["Aventojoki, alaosa"]
    sivu = pyynto("/ehdota")[2]
    assert '<fieldset class="ensimmainen">' in sivu and sivu.count('<fieldset class="lisarivi">') == 5
    assert "Paikan toiminta-alue ja optimi" in sivu and "Yksi paikka kerrallaan" in sivu
