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
    assert not virhe and ehdotus["kohteet"] == [{"nimi": "Käylä – Juuma", "huom": "", "rajat": {
        "virtaama": {"toimii": [25.5, None], "paras": [25.5, None]}}}]   # vanha lomakemuoto -> virtaama
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
                                               "url": osoite,
                                               "toiminnot": [{"action": "taydenna", "title": "🔍 Täydennä",
                                                              "api": f"/api/ehdotus/{tunniste}/taydenna"}]})]
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
    assert vanha.nimi in muuttuu and "→ vedenkorkeus m: toimii 107.60 m – 108.20 m" in muuttuu
    assert "nyt: toimii" in muuttuu
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


def test_uusi_kohde_ja_lisaa_kohde_nappi(ymparisto):
    """Uusi kohde: ensimmäisen kohteen nimi oletuksena paikan nimi; "+ Lisää kohde" tuo lisää rivejä."""
    kentat = {"laji": ["uusi"], "nimi": ["Aventojoki"], "mittari": ["7300350"], "k1_toimii_ala": ["10"],
              "k2_nimi": ["Alakoski"], "k2_toimii_ala": ["5"]}
    ehdotus, virhe = ehdotukset.tulkitse(kentat, PAIKAT)
    assert not virhe and [k["nimi"] for k in ehdotus["kohteet"]] == ["Aventojoki", "Alakoski"]
    del kentat["k2_nimi"]
    assert ehdotukset.tulkitse(kentat, PAIKAT)[1] == "Anna kohteen 2 nimi."
    sivu = pyynto("/ehdota")[2]
    # yksi kohde-editori, "+ Lisää kohde" siirtää kohteen tekstinä listaan (enintään 6)
    assert sivu.count('<fieldset class="kohde-editori">') == 1 and 'id="kohdelista"' in sivu
    assert 'id="lisaa-kohde">+ Lisää kohde</button>' in sivu and ehdotukset.KOHTEITA_ENINTAAN == 6
    assert 'name="k1_nimi"' not in sivu   # piilokentät syntyvät vasta listasta
    # virheen jälkeen lisätyt kohteet palaavat listaan
    status, _, sivu = pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="X", k1_nimi="A",
                                                                     k1_toimii_ala="1", k2_nimi="B", k2_toimii_ala="x"))
    assert status == "400 Bad Request" and '"nimi": "B", "huom": ""' in sivu   # lisätyt palaavat listaan


TAYDENNYS = {
    "nimi": "Aventojoki (Ollilanjärvi – Aventolampi)", "teksti": "Pieni tulvajoki.\n\nVain kokeneille.",
    "lahto": "Ollilanjärven pysäköintipaikka", "lahto_sijainti": [66.363, 29.055],
    "loppu": "Oulangan luontokeskus", "loppu_sijainti": [66.3683, 29.3147],
    "mittari": "7300100", "suure": "virtaama", "mittari_perustelu": "Oulankajoki alavirrassa.",
    "kohteet": [{"nimi": "Ollilanjärvi – Aventolampi", "toimii": [300, None], "paras": [380, 480],
                 "huom": "rajat arvioita"},
                {"nimi": "Oma kohde", "toimii": [1, None]}],
    "huomiot": "Lähde vuodelta 2010.",
    "lahteet": [{"nimi": "Kuusamon Koskimelojat", "url": "https://koskimelojat.blogspot.com/2010/07/aventojoki.html"},
                {"nimi": "SYKE", "url": "javascript:alert(1)"}]}


def test_tarkista_taydennys():
    t, virhe = ehdotukset.tarkista_taydennys(TAYDENNYS)
    assert not virhe and t["mittari"] == "73/q7300100y/qinlyhyt.png"
    assert t["kohteet"][0] == {"nimi": "Ollilanjärvi – Aventolampi", "huom": "rajat arvioita",
                               "rajat": {"virtaama": {"toimii": [300.0, None], "paras": [380.0, 480.0]}}}
    assert t["lahteet"][1]["url"] == ""   # vain http(s)-linkit
    assert ehdotukset.tarkista_taydennys({**TAYDENNYS, "mittari": "ei asema"})[1].startswith("mittari")
    # rajat ilman tunnettua suuretta hylätään; kohde ilman rajoja kelpaa
    assert "suure puuttuu" in ehdotukset.tarkista_taydennys({"kohteet": [{"nimi": "X", "toimii": [1, None]}]})[1]
    assert ehdotukset.tarkista_taydennys({"kohteet": [{"nimi": "X"}]})[0]["kohteet"] == [
        {"nimi": "X", "rajat": {}, "huom": ""}]
    assert ehdotukset.tarkista_taydennys({"lahto": "x"})[1].startswith("täydennyksessä pitää olla")


def test_pelkka_linkki_ja_taydennys(ymparisto, monkeypatch):
    """Pelkkä linkki kelpaa; ylläpitäjä käynnistää täydennyksen, valmis täydennys näkyy esikatselussa
    ehdottajan tietojen rinnalla ja siitä ilmoitetaan kerran."""
    kanta, lahetetyt = ymparisto
    kanta.kirjoita(ehdotukset.YLLAPITO, "laite", {"endpoint": TILAUS["endpoint"], "p256dh": "x", "auth": "y"})
    status, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(
        laji="uusi", linkit="https://koskimelojat.blogspot.com/2010/07/aventojoki.html",
        k1_nimi="Oma kohde", k1_toimii_ala="250"))
    assert status == "303 See Other"
    osoite = otsakkeet["Location"]
    tunniste = osoite.removeprefix("/ehdotus/")
    assert lahetetyt[-1][1]["otsikko"] == "Uusi ehdotus: koskimelojat.blogspot.com"
    # Täydennä: vaatii kirjautumisen; käynnistää GitHub-ajon
    assert pyynto(f"/api/ehdotus/{tunniste}/taydenna", metodi="POST")[0] == "403 Forbidden"
    _, ylla, _ = pyynto("/yllapito", metodi="POST", runko=lomake(salasana="salainen"))
    evaste = ylla["Set-Cookie"].split(";")[0]
    assert "🔍 Täydennä" in pyynto(osoite, evaste=evaste)[2]
    kaynnistetyt = []
    monkeypatch.setenv("GITHUB_TAYDENNYS_TOKEN", "tunnus")
    monkeypatch.setattr(ehdotukset, "kaynnista_taydennys", lambda t, token: kaynnistetyt.append((t, token))
                        or (True, "GitHub 204"))
    status, _, vastaus = pyynto(f"/api/ehdotus/{tunniste}/taydenna", metodi="POST", evaste=evaste)
    assert status == "200 OK" and json.loads(vastaus)["kaynnistetty"] and kaynnistetyt == [(tunniste, "tunnus")]
    sivu = pyynto(osoite)[2]
    assert "Täydennys käynnissä" in sivu
    # Claude tallentaa täydennyksen (työkalu tekee saman) ja tuotanto ilmoittaa
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste)
    ehdotus["taydennys"] = {**ehdotukset.tarkista_taydennys(TAYDENNYS)[0], "tila": "valmis",
                            "aika": "2026-10-24T12:00:00+00:00"}
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, ehdotus)
    lahetetyt.clear()
    assert json.loads(pyynto(f"/api/ehdotus/{tunniste}/taydennys-valmis", metodi="POST")[2]) == {"ilmoitettu": True}
    assert json.loads(pyynto(f"/api/ehdotus/{tunniste}/taydennys-valmis", metodi="POST")[2]) == {"ilmoitettu": False}
    assert [v["otsikko"] for _, v in lahetetyt] == ["Täydennetty: Aventojoki (Ollilanjärvi – Aventolampi)"]
    sivu = pyynto(osoite)[2]
    assert "<h1>Aventojoki (Ollilanjärvi – Aventolampi)</h1>" in sivu and "✓ Täydennetty lähteistä" in sivu
    assert "<h2>Koottu lähteistä</h2>" in sivu and "Pieni tulvajoki." in sivu and "Oulankajoki alavirrassa." in sivu
    assert "<b>Lähtö:</b> Ollilanjärven pysäköintipaikka" in sivu and "openstreetmap.org/?mlat=66.363" in sivu
    # ehdottajan kohde säilyy (ja voittaa samannimisen), täydennyksen kohde merkitään arvioksi
    assert "Oma kohde</b> <span class=\"pieni\">(ehdottaja)</span>" in sivu and "yli 250 m³/s" in sivu
    assert "Ollilanjärvi – Aventolampi</b> <span class=\"pieni\">(arvio lähteistä)</span>" in sivu
    assert 'href="javascript' not in sivu
    paikka, _ = ehdotukset.paikaksi(kanta.lue(ehdotukset.KOKOELMA, tunniste), PAIKAT)
    assert paikka.mittarit["virtaama"].kaavio == "73/q7300100y/qinlyhyt.png" and len(paikka.kohteet) == 2


def test_service_worker_napit():
    sw = halytykset.SERVICE_WORKER
    assert "actions: toiminnot.map" in sw and 'fetch(toiminto.api, {method: "POST", credentials: "include"})' in sw


def test_kaynnista_taydennys():
    pyynnot = []

    class Vastaus:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def avaa(pyynto, timeout):
        pyynnot.append(pyynto)
        return Vastaus()

    assert ehdotukset.kaynnista_taydennys("x" * 22, None) == (False, "GITHUB_TAYDENNYS_TOKEN puuttuu Vercelin "
                                                                     "ympäristömuuttujista")
    assert ehdotukset.kaynnista_taydennys("x" * 22, "t", avaa) == (True, "GitHub 204")
    p = pyynnot[0]
    assert p.full_url.endswith("/repos/gobi196761-stack/melontapaikat/actions/workflows/taydenna.yml/dispatches")
    assert json.loads(p.data) == {"ref": "main", "inputs": {"tunniste": "x" * 22}}
    assert p.get_header("Authorization") == "Bearer t"


def test_tyokalu_tallenna_ja_rajaus(ymparisto, monkeypatch, tmp_path, capsys):
    """Täydennystyökalu käsittelee vain TUNNISTE-ehdotusta ja tallentaa tarkistetun täydennyksen."""
    import importlib.util
    import urllib.request
    kanta, _ = ymparisto
    spec = importlib.util.spec_from_file_location("taydenna_ehdotus", "tyokalut/taydenna_ehdotus.py")
    tyokalu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tyokalu)
    tunniste = "A" * 22
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, {"laji": "uusi", "nimi": "", "tila": "odottaa", "kohteet": [],
                                                   "linkit": [{"url": "https://x.fi/a", "laji": "muu"}],
                                                   "tilaus": {"endpoint": "salainen"}})
    monkeypatch.delenv("TUNNISTE", raising=False)
    with pytest.raises(SystemExit):
        tyokalu.main(["lue"])
    monkeypatch.setenv("TUNNISTE", tunniste)
    tyokalu.main(["lue"])
    assert "salainen" not in capsys.readouterr().out   # push-tilausta ei näytetä
    kutsut = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda p, timeout: kutsut.append(p.full_url) or io.BytesIO(b"{}"))
    tiedosto = tmp_path / "t.json"
    tiedosto.write_text(json.dumps({"teksti": "x", "kohteet": [{"nimi": "K", "toimii": ["abc"]}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        tyokalu.main(["tallenna", str(tiedosto)])
    tiedosto.write_text(json.dumps(TAYDENNYS), encoding="utf-8")
    tyokalu.main(["tallenna", str(tiedosto)])
    tallessa = kanta.lue(ehdotukset.KOKOELMA, tunniste)["taydennys"]
    assert tallessa["tila"] == "valmis" and tallessa["mittari"] == "73/q7300100y/qinlyhyt.png"
    assert kutsut == [f"https://melontapaikat.vercel.app/api/ehdotus/{tunniste}/taydennys-valmis"]
    tyokalu.main(["virhe", "linkki ei aukea"])
    assert kanta.lue(ehdotukset.KOKOELMA, tunniste)["taydennys"]["tila"] == "virhe"


def test_yksityiset_linkit(ymparisto):
    """Vain rakentamiseen annetut linkit: tallentuvat, näkyvät vain ylläpitäjälle (ei linkkeinä),
    eivätkä täydennys saa julkaista niitä."""
    kanta, _ = ymparisto
    yksityinen = "https://www.facebook.com/oma/postaus/123"
    status, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(
        laji="uusi", nimi="Testijoki", linkit="https://koskimelojat.blogspot.com/x", yksityiset_linkit=yksityinen))
    assert status == "303 See Other"
    tunniste = otsakkeet["Location"].removeprefix("/ehdotus/")
    assert kanta.lue(ehdotukset.KOKOELMA, tunniste)["yksityiset_linkit"] == [yksityinen]
    assert yksityinen not in pyynto(otsakkeet["Location"])[2]
    _, ylla, _ = pyynto("/yllapito", metodi="POST", runko=lomake(salasana="salainen"))
    sivu = pyynto(otsakkeet["Location"], evaste=ylla["Set-Cookie"].split(";")[0])[2]
    assert f"<code>{yksityinen}</code>" in sivu and f'href="{yksityinen}"' not in sivu
    # pelkkä yksityinen linkki riittää uudeksi kohteeksi
    assert ehdotukset.tulkitse({"laji": ["uusi"], "yksityiset_linkit": [yksityinen]}, PAIKAT)[0]
    assert "Ei-julkaistavat linkit" in pyynto("/ehdota")[2]
    # täydennys ei saa julkaista yksityistä linkkiä
    assert ehdotukset.tarkista_taydennys({**TAYDENNYS, "lahteet": [{"nimi": "FB", "url": yksityinen}]},
                                         [yksityinen])[1].startswith("yksityistä linkkiä")
    assert ehdotukset.tarkista_taydennys({**TAYDENNYS, "teksti": f"ks. {yksityinen}"}, [yksityinen])[0] is None
    assert ehdotukset.tarkista_taydennys(TAYDENNYS, [yksityinen])[0]


def test_kaksoiskappaleet(ymparisto):
    """Uusi kohde, joka on jo olemassa toisella nimellä tai samassa paikassa, merkitään."""
    kanta, _ = ymparisto
    # Muut kohteet: Kitkajoki nimellä; sovelluksen paikka: sijainti Kipinän vieressä
    kitka = {"laji": "uusi", "nimi": "Kitkajoen koskireitti", "tila": "odottaa", "kohteet": [], "linkit": []}
    osumat = app.ehdotuksen_kaksoiskappaleet("X" * 22, kitka)
    assert any("Muut kohteet" in k["nimi"] and k["syy"] == "sama nimi" for k in osumat)
    lahella = {"laji": "uusi", "nimi": "Uusi nimi", "sijainti": list(KIPINA.sijainti), "kohteet": [], "linkit": []}
    osumat = app.ehdotuksen_kaksoiskappaleet("X" * 22, lahella)
    assert any(k["nimi"] == KIPINA.nimi and k["syy"].startswith("sijainti 0.0 km") for k in osumat)
    assert app.ehdotuksen_kaksoiskappaleet("X" * 22, {"laji": "uusi", "nimi": "Tuntematonpuro", "kohteet": [],
                                                       "linkit": []}) == []
    # esikatselussa varoitus
    _, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(laji="uusi", nimi="Kitkajoki", teksti="t"))
    sivu = pyynto(otsakkeet["Location"])[2]
    # tieto, ei varoitus; ilman mittaria ja rajoja siitä ei tehdä pisteytettävää paikkaa
    assert "ℹ️ Ehdotuksessa ei ole mittaria ja rajoja" in sivu and 'href="/muut/' in sivu


def test_hyvaksytty_uusi_kohde_listassa(ymparisto, monkeypatch):
    """Hyväksytty uusi kohde tulee paikkalistaan (sivu /ehdotus/<tunniste>), pisteytetään ja on hälytyksissä."""
    kanta, _ = ymparisto
    tunniste = "B" * 22
    kanta.kirjoita(ehdotukset.KOKOELMA, tunniste, {
        "laji": "uusi", "nimi": "Aventojoki", "tyyppi": "retki", "tila": "hyvaksytty", "mittari": "",
        "kohteet": [], "linkit": [], "taydennys": {**ehdotukset.tarkista_taydennys(TAYDENNYS)[0], "tila": "valmis"}})
    paikat = app.kaikki_paikat()
    uusi = paikat[-1]
    assert len(paikat) == len(PAIKAT) + 1 and uusi.nimi == "Aventojoki" and uusi.url == f"/ehdotus/{tunniste}"
    assert uusi.mittarit["virtaama"].kaavio == "73/q7300100y/qinlyhyt.png" and uusi.sijainti == (66.363, 29.055)
    assert app.paikan_osoite(uusi, "en") == f"/ehdotus/{tunniste}?kieli=en"
    assert "Aventojoki" in halytykset.valittavat(paikat)
    # laskenta ottaa sen mukaan ja laskee uudelleen, kun hyväksyttyjen joukko muuttuu
    kaytetyt = []

    def keraa(hakija, paikat_, **kw):
        kaytetyt.append({p.nimi for p in paikat_})
        return {}, {"x": object()}, []
    monkeypatch.setattr(app.melonta, "kerää_tilanne", keraa)
    monkeypatch.setattr(app.melonta, "arvioi_kaikki", lambda paikat_, *a: [])
    monkeypatch.setattr(app, "ajomatkat", lambda *a: ("503", {}))
    monkeypatch.setattr(app, "saaennusteet", lambda *a: {})
    monkeypatch.setattr(app, "surffitilanne", lambda *a: {})
    monkeypatch.setattr(app.turvallisuus, "hae", lambda *a: {})
    app.hae_tilanne()
    app.hae_tilanne()
    assert len(kaytetyt) == 1 and "Aventojoki" in kaytetyt[0]
    kanta.data[ehdotukset.KOKOELMA][tunniste]["tila"] = "hylatty"
    app._ehdotukset = None
    app.hae_tilanne()
    assert len(kaytetyt) == 2 and "Aventojoki" not in kaytetyt[1]


def test_uusi_kohde_muunnetaan_taydennykseksi(ymparisto):
    """Uusi kohde, joka onkin olemassa oleva paikka: ylläpitäjä lisää sen uudet pelipaikat paikkaan."""
    kanta, _ = ymparisto
    avain, mittari = next(iter(KIPINA.mittarit.items()))
    vanha = KIPINA.kohteet[0].nimi
    _, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(
        laji="uusi", nimi="Pudasjärven silta", sijainti=f"{KIPINA.sijainti[0]}, {KIPINA.sijainti[1]}",
        mittari=f"https://wwwi2.ymparisto.fi/i2/{mittari.kaavio}", suure="vedenkorkeus",
        k1_nimi="Uusi kivi-aalto", k1_toimii_ala="107.0", k2_nimi=vanha.upper(), k2_toimii_ala="107.6"))
    osoite = otsakkeet["Location"]
    tunniste = osoite.removeprefix("/ehdotus/")
    _, ylla, _ = pyynto("/yllapito", metodi="POST", runko=lomake(salasana="salainen"))
    evaste = ylla["Set-Cookie"].split(";")[0]
    sivu = pyynto(osoite, evaste=evaste)[2]
    assert f"➕ Lisää paikkaan {KIPINA.nimi}: 1 uutta kohdetta, 1 rajakorjausta" in sivu
    assert "➕ Lisää paikkaan" not in pyynto(osoite)[2]   # vain ylläpitäjälle
    toiminto = f"muunna:{app.paikkasivut.tunniste(KIPINA.nimi)}"
    assert pyynto(f"{osoite}/kasittele", metodi="POST", runko=lomake(toiminto=toiminto), evaste=evaste)[0] \
        == "303 See Other"
    ehdotus = kanta.lue(ehdotukset.KOKOELMA, tunniste)
    assert ehdotus["laji"] == "taydenna" and ehdotus["paikka"] == KIPINA.nimi and ehdotus["mittari_avain"] == avain
    assert [k["nimi"] for k in ehdotus["kohteet"]] == ["Uusi kivi-aalto", vanha]   # kirjoitusasu olemassa olevan
    sivu = pyynto(osoite)[2]
    assert f"Täydennys paikkaan: {KIPINA.nimi}" in sivu and "alkuperäinen nimi: Pudasjärven silta" in sivu
    muuttuu = sivu.split('<h2 class="muuttuu">Muuttuu</h2>')[1].split('<h2 class="tulossa">')[0]
    assert vanha in muuttuu and "Uusi kivi-aalto" in sivu.split('<h2 class="tulossa">')[1]
    # eri mittari: ehdotuksen mittari lisätään paikalle kohteiden mittariksi
    toinen = ehdotukset.muunna_taydennykseksi({"laji": "uusi", "nimi": "X", "mittari": "73/q7300100y/qinlyhyt.png",
                                               "kohteet": [{"nimi": "Y", "toimii": [1, None], "paras": [1, None]}],
                                               "linkit": []}, KIPINA)
    paikka, _ = ehdotukset.paikaksi(toinen, PAIKAT)
    assert toinen["lisamittarit"] == {"virtaama": "73/q7300100y/qinlyhyt.png"}
    assert paikka.mittarit[f"{ehdotukset.LISAMITTARI}_virtaama"].kaavio == "73/q7300100y/qinlyhyt.png"
    assert next(k for k in paikka.kohteet if k.nimi == "Y").mittari == f"{ehdotukset.LISAMITTARI}_virtaama"


def test_muut_kohteet_ei_esta_uutta_paikkaa(ymparisto):
    """Muissa kohteissa oleva reitti: pisteytettävästä ehdotuksesta tulee paikka ja päiväkirjan tiedot
    kuvaukseen; ilman mittaria ja rajoja paikkaa ei tehdä. Muut kohteet -lista ei muutu."""
    import muut_kohteet
    kanta, _ = ymparisto
    ennen = json.dumps(muut_kohteet.KOHTEET, sort_keys=True)
    kitka = next(k for k in muut_kohteet.KOHTEET if k["tunniste"] == "kajakilla-kahden-kuusamon-kylan-valia")
    pisteytettava = {"laji": "uusi", "nimi": "Kitkajoki (Käylä – Juuma)", "tila": "hyvaksytty", "linkit": [],
                     "mittari": "73/q7300220y/qinlyhyt.png",
                     "kohteet": [{"nimi": "Käylä – Juuma", "toimii": [20, None], "paras": [30, 60], "huom": ""}]}
    pelkka = {"laji": "uusi", "nimi": "Kitkajoen reitti", "tila": "hyvaksytty", "linkit": [], "kohteet": []}
    kanta.kirjoita(ehdotukset.KOKOELMA, "C" * 22, pisteytettava)
    kanta.kirjoita(ehdotukset.KOKOELMA, "D" * 22, pelkka)
    assert ehdotukset.pisteytettava(pisteytettava) and not ehdotukset.pisteytettava(pelkka)
    nimet = [p.nimi for p in app.kaikki_paikat()]
    assert "Kitkajoki (Käylä – Juuma)" in nimet and "Kitkajoen reitti" not in nimet
    sivu = pyynto(f"/ehdotus/{'C' * 22}")[2]
    assert "<h2>Melontapäiväkirjasta (Muut kohteet)</h2>" in sivu and kitka["kuvaus"][0][:40] in sivu
    assert muut_kohteet.LAHDE in sivu and "Piirainen</a>" not in sivu   # päiväkirjaa ei linkitetä
    # odottava: tieto Muista kohteista ei ole kaksoiskappalevaroitus
    kanta.data[ehdotukset.KOKOELMA]["C" * 22]["tila"] = "odottaa"
    sivu = pyynto(f"/ehdotus/{'C' * 22}")[2]
    assert "ℹ️ Sama reitti on Muut kohteet -listassa" in sivu
    assert '(Muut kohteet)</a> <span class="pieni">' not in sivu   # Muut kohteet ei ole varoituslistassa
    kanta.data[ehdotukset.KOKOELMA]["D" * 22]["tila"] = "odottaa"
    assert "siitä ei tehdä pisteytettävää" in pyynto(f"/ehdotus/{'D' * 22}")[2]
    assert json.dumps(muut_kohteet.KOHTEET, sort_keys=True) == ennen


def test_rajat_suureittain(ymparisto):
    """Kohteelle rajat virtaamana, vedenkorkeutena, molempina tai ei lainkaan; avoimet rajat sallitaan."""
    kentat = {"laji": ["uusi"], "nimi": ["Testijoki"], "mittari_virtaama": ["7300100"],
              "k1_nimi": ["Molemmat"], "k1_q_toimii_ala": ["20"], "k1_w_paras_yla": ["1,5"],
              "k2_nimi": ["Vain vedenkorkeus"], "k2_w_toimii_yla": ["2"],
              "k3_nimi": ["Ei rajoja"], "k3_huom": ["kokeiltava"]}
    ehdotus, virhe = ehdotukset.tulkitse(kentat, PAIKAT)
    assert not virhe and ehdotus["mittari_virtaama"] == "73/q7300100y/qinlyhyt.png"
    k1, k2, k3 = ehdotus["kohteet"]
    assert k1["rajat"] == {"virtaama": {"toimii": [20.0, None], "paras": [20.0, None]},
                           "vedenkorkeus": {"toimii": [None, 1.5], "paras": [None, 1.5]}}   # pelkkä optimi käy
    assert k2["rajat"] == {"vedenkorkeus": {"toimii": [None, 2.0], "paras": [None, 2.0]}} and k3["rajat"] == {}
    paikka, _ = ehdotukset.paikaksi(ehdotus, PAIKAT)
    # pisteytetään vain kohteet, joiden suureelle on mittari (tässä virtaama)
    assert [k.nimi for k in paikka.kohteet] == ["Molemmat"] and paikka.kohteet[0].mittari == "virtaama"
    ehdotus["mittari_vedenkorkeus"] = "73/w7300100y/wlyhyt.png"
    paikka, _ = ehdotukset.paikaksi(ehdotus, PAIKAT)
    assert [(k.nimi, k.mittari) for k in paikka.kohteet] == [("Molemmat", "virtaama"), ("Vain vedenkorkeus", "vedenkorkeus")]
    # esikatselu näyttää kaikki rajat yksikköineen ja kertoo, miksi kohdetta ei pisteytetä
    _, otsakkeet, _ = pyynto("/ehdota", metodi="POST", runko=lomake(**{k: v[0] for k, v in kentat.items()}))
    sivu = pyynto(otsakkeet["Location"])[2]
    assert "virtaama m³/s: toimii yli 20 m³/s; vedenkorkeus m: toimii alle 1.50 m" in sivu
    assert "Vain vedenkorkeus</b> <span class=\"pieni\">(ei pisteytetä: mittari puuttuu)</span>" in sivu
    assert "Ei rajoja</b> <span class=\"pieni\">(ei pisteytetä: rajat puuttuvat)</span>" in sivu
    # lomakkeen järjestys: nimi, linkit, kohteet (yksikön valinta), mittarit
    lomake_ = pyynto("/ehdota")[2]
    assert lomake_.index('id="nimi"') < lomake_.index('id="linkit"') < lomake_.index('id="yksityiset_linkit"') \
        < lomake_.index('id="yksikko-q"') < lomake_.index('id="yksikko-w"') < lomake_.index('id="mittari_virtaama"')
    assert "Molempia linkkejä käytetään sivun rakentamiseen" in lomake_
