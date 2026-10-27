import pytest

import kaavio_svg


@pytest.fixture
def vaaka():
    """Kaaviot vaakamallissa (leveä näyttö): tekstit yhdellä rivillä kuten ennen pystymallia."""
    merkki = kaavio_svg.muoto.set("vaaka")
    yield
    kaavio_svg.muoto.reset(merkki)


@pytest.fixture(autouse=True)
def ei_verkkotilannetta(monkeypatch):
    """Paikkasivu näyttää vesitilanteen: testeissä ei lasketa oikeaa tilannetta verkosta
    (testi, joka tarvitsee tilanteen, korvaa _paikkasivun_tilanne-funktion itse)."""
    import app
    monkeypatch.setattr(app, "_paikkasivun_tilanne", lambda: None)
