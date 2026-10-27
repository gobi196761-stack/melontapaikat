import json
from urllib.parse import parse_qs, urlparse

import kuvat
import paikat as paikat_
from paikat import Paikka


def _tiedot(otsikko, leveys=4000, korkeus=3000, kuvaus="", lisenssi="CC BY-SA 4.0", mime="image/jpeg"):
    return {"title": otsikko, "imageinfo": [{
        "mime": mime, "width": leveys, "height": korkeus,
        "thumburl": f"https://upload.wikimedia.org/thumb/x/{otsikko}/960px-{otsikko}",
        "url": f"https://upload.wikimedia.org/x/{otsikko}", "descriptionurl": f"https://commons.wikimedia.org/wiki/{otsikko}",
        "extmetadata": {"Artist": {"value": '<a href="//x">Matti <b>M</b></a>'}, "LicenseShortName": {"value": lisenssi},
                        "ImageDescription": {"value": kuvaus}}}]}


class Hakija:
    offline = None

    def __init__(self, geo, tiedot):
        self.geo, self.tiedot, self.kutsut = geo, tiedot, []

    def hae(self, url):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        self.kutsut.append(q)
        if q.get("list") == "geosearch":
            return json.dumps({"query": {"geosearch": [{"title": t} for t in self.geo]}}).encode()
        sivut = {str(i): self.tiedot[t] for i, t in enumerate(q["titles"].split("|")) if t in self.tiedot}
        return json.dumps({"query": {"pages": sivut}}).encode()


def test_etsi_valitsee_vesistokuvan():
    tiedot = {o: _tiedot(o, **k) for o, k in [
        ("File:Kirkko.jpg", {"kuvaus": "Kipinän kirkko"}),           # kielletty sana
        ("File:Pysty.jpg", {"leveys": 2000, "korkeus": 3000}),       # pystykuva
        ("File:Pieni.jpg", {"leveys": 640, "korkeus": 480}),         # liian pieni
        ("File:Metsa.jpg", {"kuvaus": "metsää"}),                    # ei vesistösanaa
        ("File:Iijoki.jpg", {"kuvaus": "Iijoki kesällä"}),
        ("File:Kipinänkoski.jpg", {"kuvaus": "Kipinänkoski, Iijoki"})]}
    hakija = Hakija(list(tiedot), tiedot)
    kuva = kuvat.etsi(hakija, "Kipinä (Iijoki)", (65.28, 26.54))
    assert kuva["otsikko"] == "File:Kipinänkoski.jpg" and kuva["tekija"] == "Matti M"
    assert kuva["pieni"].endswith("/250px-File:Kipinänkoski.jpg") and kuva["lisenssi"] == "CC BY-SA 4.0"
    assert kuvat.etsi(Hakija(["File:Metsa.jpg"], tiedot), "Kipinä (Iijoki)", (65.28, 26.54)) is None
    assert kuvat.etsi(hakija, "Kipinä (Iijoki)", None) is None


def test_kiintea_ja_tallennus(monkeypatch):
    tiedot = {"File:Koiteli.jpg": _tiedot("File:Koiteli.jpg"), "File:Joki.jpg": _tiedot("File:Joki.jpg", kuvaus="joki")}
    monkeypatch.setattr(kuvat, "KIINTEAT", {"Koiteli": "File:Koiteli.jpg"})
    monkeypatch.setattr(kuvat, "_kuvat", None)

    class Kanta:
        data = {}

        def lue(self, k, t):
            return self.data.get((k, t))

        def kirjoita(self, k, t, d):
            self.data[(k, t)] = d
    kanta = Kanta()
    monkeypatch.setitem(paikat_.SIJAINNIT, "Tyhjä", (65.0, 25.0))
    paikat = [Paikka("Koiteli", "", "peli", None, ""), Paikka("Tyhjä", "", "retki", None, "")]
    hakija = Hakija(["File:Joki.jpg"], tiedot)
    tulos = kuvat.paivita(hakija, kanta, paikat)
    assert tulos["Koiteli"]["otsikko"] == "File:Koiteli.jpg" and tulos["Tyhjä"]["otsikko"] == "File:Joki.jpg"
    assert len(kanta.data[("asetukset", "kuvat")]["kuvat"]) == 2
    kutsuja = len(hakija.kutsut)
    kuvat.paivita(hakija, kanta, paikat)   # tuore: ei uusia hakuja
    assert len(hakija.kutsut) == kutsuja
    monkeypatch.setattr(kuvat, "_kuvat", None)   # uusi prosessi lukee Firestoresta
    assert kuvat.kuva("Koiteli", kanta)["sivu"].endswith("File:Koiteli.jpg")


def test_verkkovirhe_ei_merkitse_haetuksi(monkeypatch):
    monkeypatch.setattr(kuvat, "_kuvat", None)

    class Rikki:
        offline = None

        def hae(self, url):
            raise OSError("ei verkkoa")
    paikat = [Paikka("Kipinä (Iijoki)", "", "peli", None, "")]
    assert kuvat.paivita(Rikki(), None, paikat) == {}


def test_kielletty_valinta_haetaan_uudelleen(monkeypatch):
    tanaan = __import__("datetime").date.today().isoformat()
    monkeypatch.setattr(kuvat, "_kuvat", {"Lieksa": {"nimi": "Lieksa", "otsikko": "File:Lieksa, Pier.jpg",
                                                     "kuva": "x", "haettu": tanaan}})
    monkeypatch.setitem(paikat_.SIJAINNIT, "Lieksa", (63.39, 30.45))
    tiedot = {"File:Neitikoski.jpg": _tiedot("File:Neitikoski.jpg", kuvaus="Neitikoski, Lieksanjoki")}
    tulos = kuvat.paivita(Hakija(list(tiedot), tiedot), None, [Paikka("Lieksa", "", "peli", None, "")])
    assert tulos["Lieksa"]["otsikko"] == "File:Neitikoski.jpg"
