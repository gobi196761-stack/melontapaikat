import pytest

import kaavio_svg


@pytest.fixture
def vaaka():
    """Kaaviot vaakamallissa (leveä näyttö): tekstit yhdellä rivillä kuten ennen pystymallia."""
    merkki = kaavio_svg.muoto.set("vaaka")
    yield
    kaavio_svg.muoto.reset(merkki)
