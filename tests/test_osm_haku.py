import urllib.error

import melonta
import osm_sivut as osm
from paikat import PAIKAT


class Hakija:
    """Valehakija: palauttaa vastaukset järjestyksessä (poikkeus nostetaan)."""
    offline = None

    def __init__(self, *vastaukset):
        self.vastaukset = list(vastaukset)
        self.kutsut = 0

    def hae(self, url):
        self.kutsut += 1
        v = self.vastaukset.pop(0)
        if isinstance(v, Exception):
            raise v
        return v


def test_tilapainen_virhe_yritetaan_uudelleen(monkeypatch):
    monkeypatch.setattr(osm, "UUSINTA_ODOTUS_S", 0)
    h = Hakija(TimeoutError("timed out"), b"ok")
    assert osm.hae_turvallisesti(h, "https://www.osm.fi/x") == (b"ok", None)
    assert h.kutsut == 2
    h = Hakija(urllib.error.HTTPError("u", 503, "ruuhka", None, None), b"ok")
    assert osm.hae_turvallisesti(h, "https://www.osm.fi/x") == (b"ok", None)


def test_pysyva_virhe_ei_uusintaa(monkeypatch):
    monkeypatch.setattr(osm, "UUSINTA_ODOTUS_S", 0)
    h = Hakija(urllib.error.HTTPError("u", 404, "ei löydy", None, None), b"ok")
    data, virhe = osm.hae_turvallisesti(h, "https://www.osm.fi/x")
    assert data is None and virhe == "https://www.osm.fi/x: 404" and h.kutsut == 1


def test_epaonnistuneet_sivut_yhdessa_ilmoituksessa(monkeypatch):
    """osm.fi:n sivujen haun virheet kootaan yhdeksi huomautukseksi; pisteytys käyttää tunnettuja mittareita."""
    monkeypatch.setattr(melonta.osm, "hae_turvallisesti",
                        lambda h, url: (None, f"{url}: timed out") if "osm.fi" in url else (None, "ohitettu"))
    paikat = tuple(p for p in PAIKAT if p.osm_sivu)[:3]
    _, _, varoitukset = melonta.kerää_tilanne(None, paikat, tarkista_hakemisto=False, prosessit=False)
    sivut = [v for v in varoitukset if "osm.fi:n sivua" in v]
    assert len(sivut) == 1 and "(3: " in sivut[0]
    assert not any(v.startswith("Sivun haku epäonnistui") for v in varoitukset)
