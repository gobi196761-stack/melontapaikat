from pathlib import Path

import kapsi

RAPORTTI = (Path(__file__).parent / "fixtures" / "kapsi_melontaraportti.html").read_text(encoding="utf-8")


class Kanta:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def lue(self, kokoelma, tunniste):
        return self.data.get((kokoelma, tunniste))

    def kirjoita(self, kokoelma, tunniste, data):
        self.data[(kokoelma, tunniste)] = data


def test_raportista_maalismaan_mittaukset():
    """Raportti 23.10.2026 klo 9: viimeisin 05:30 ja historia (HTML-kommentissa) 21:30–03:30;
    ennustetaulukko ja muiden paikkojen arvot eivät tule mukaan."""
    assert kapsi.lue_maalismaa(RAPORTTI) == [
        ("2026-10-22", "21:30", 364.56), ("2026-10-22", "23:30", 364.17),
        ("2026-10-23", "01:30", 363.35), ("2026-10-23", "03:30", 362.72), ("2026-10-23", "05:30", 362.39)]
    assert kapsi.lue_maalismaa("<html>muuttunut sivu</html>") == []


def test_tallennus_paivittain_ja_yhdistaen():
    kanta = Kanta({(kapsi.KOKOELMA, "2026-10-22"): {"mittaukset": {"19:30": 365.0, "21:30": 364.56}}})
    mittaukset = kapsi.lue_maalismaa(RAPORTTI)
    assert kapsi.tallenna(kanta, mittaukset, "2026-10-23T09:05:00+03:00") == 4   # 21:30 oli jo
    assert kanta.lue(kapsi.KOKOELMA, "2026-10-22")["mittaukset"] == {"19:30": 365.0, "21:30": 364.56, "23:30": 364.17}
    assert kanta.lue(kapsi.KOKOELMA, "2026-10-23")["mittaukset"] == {"01:30": 363.35, "03:30": 362.72, "05:30": 362.39}
    assert kapsi.tallenna(kanta, mittaukset, "2026-10-23T21:05:00+03:00") == 0   # sama raportti uudelleen


def test_keraa_ei_kaada_ajoa():
    kanta = Kanta()
    tulos = kapsi.keraa(kanta, "2026-10-23T09:05:00+03:00", hae=lambda url: RAPORTTI.encode("utf-8"))
    assert tulos == {"mittauksia": 5, "uusia": 5, "viimeisin": "2026-10-23 05:30"}

    def kaatuu(url):
        raise OSError("yhteys katkesi")
    assert kapsi.keraa(kanta, "nyt", hae=kaatuu) == {"virhe": "OSError: yhteys katkesi"}
    assert "virhe" in kapsi.keraa(kanta, "nyt", hae=lambda url: b"<html></html>")


def test_oma_ajo_kirjoittaa_lokiin(monkeypatch, capsys):
    import json

    import app
    monkeypatch.setattr(app, "_cron_kanta", lambda environ: (Kanta(), None))
    monkeypatch.setattr(kapsi, "keraa", lambda kanta, nyt: {"mittauksia": 5, "uusia": 2, "viimeisin": "2026-10-23 09:30"})
    status, tulos = app.kapsi_kerays({})
    assert status == "200 OK" and tulos["uusia"] == 2
    loki = json.loads(capsys.readouterr().out.strip().removeprefix("kapsi: "))
    assert loki == {"status": "200 OK", "mittauksia": 5, "uusia": 2, "viimeisin": "2026-10-23 09:30"}
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.undo()
    monkeypatch.delenv("CRON_SECRET", raising=False)
    status, _ = app.kapsi_kerays({})
    assert status.startswith("503")   # ilman tunnistetta ei kerätä
