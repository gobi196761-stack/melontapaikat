import datetime as dt
import turvallisuus

NYT = dt.datetime(2026, 10, 23, 18, 0, tzinfo=dt.timezone.utc)


def _wfs(*rivit) -> bytes:
    jasenet = "".join(
        f"<wfs:member><BsWfs:BsWfsElement><BsWfs:Time>{a}</BsWfs:Time>"
        f"<BsWfs:ParameterName>{n}</BsWfs:ParameterName><BsWfs:ParameterValue>{v}</BsWfs:ParameterValue>"
        "</BsWfs:BsWfsElement></wfs:member>" for a, n, v in rivit)
    return f"<wfs:FeatureCollection>{jasenet}</wfs:FeatureCollection>".encode()


class Hakija:
    """Palauttaa FMI-kyselyille valmiit vastaukset kyselyn tunnisteen mukaan."""
    offline = None

    def __init__(self, vastaukset: dict[str, bytes]):
        self.vastaukset = vastaukset

    def hae(self, url: str) -> bytes:
        for avain, data in self.vastaukset.items():
            if avain in url:
                return data
        raise OSError("ei vastausta")


def test_lue_wfs_ohittaa_nan():
    rivit = turvallisuus.lue_wfs(_wfs(("2026-10-23T17:00:00Z", "WATLEV", "19.0"),
                                      ("2026-10-23T17:00:00Z", "WindGust", "NaN")))
    assert rivit == [(dt.datetime(2026, 10, 23, 17, tzinfo=dt.timezone.utc).timestamp(), "WATLEV", 19.0)]


def test_hae_maatuuli_ja_vesi():
    hakija = Hakija({
        "mareograph": _wfs(("2026-10-23T16:00:00Z", "WATLEV", "-150.0"), ("2026-10-23T17:00:00Z", "WATLEV", "-190.0"),
                           ("2026-10-23T17:00:00Z", "TW_PT1H_AVG", "7.6")),
        "sealevel": _wfs(("2026-10-23T19:00:00Z", "SeaLevel", "-22.4"), ("2026-10-23T22:00:00Z", "SeaLevel", "-31.0")),
        "weather": _wfs(("2026-10-23T18:00:00Z", "WindSpeedMS", "3.0"), ("2026-10-23T18:00:00Z", "WindDirection", "120"),
                        ("2026-10-23T21:00:00Z", "WindSpeedMS", "7.5"), ("2026-10-23T21:00:00Z", "WindDirection", "135"),
                        ("2026-10-23T21:00:00Z", "WindGust", "11.0"),
                        ("2026-10-24T03:00:00Z", "WindSpeedMS", "9.0"), ("2026-10-24T03:00:00Z", "WindDirection", "270")),
    })
    turva = turvallisuus.hae(hakija, NYT)
    assert turva["meri"] == 7.6 and turva["vesi"] == -19 and turva["vesi_min"][0] == -31
    # länsituuli (merituuli) ei ole maatuulta, vaikka on kovempi
    assert turva["maatuuli"]["ms"] == 7.5 and turva["maatuuli"]["suunta"] == 135


def test_hae_kestaa_katkon():
    assert turvallisuus.hae(Hakija({}), NYT) == {}


def ajankohta(aika, kieli):
    return "ke 21.00"


def test_viestit_kuivapuku_ja_maatuuli():
    turva = {"meri": 7.6, "vesi": -19, "vesi_min": (-31, 0),
             "maatuuli": {"ms": 7.5, "puuska": 11.0, "suunta": 135, "aika": 0, "alkaa": 0}}
    fi = turvallisuus.viestit(turva, [4.2, 6.8], "fi", ajankohta)
    otsikot = [o for o, _ in fi]
    assert otsikot == ["🥶 Kylmä vesi: kuivapuku", "💨 Maatuuli ja matala vesi"]
    assert "joissa 4.2–6.8 °C, merellä Oulun edustalla 7.6 °C" in fi[0][1]
    assert "kaakkoistuulta 7.5 m/s, puuskissa 11 m/s (ke 21.00)" in fi[1][1]
    assert "Mustasalmi" in fi[1][1] and "nyt -19 cm, ennuste -31 cm" in fi[1][1]
    en = turvallisuus.viestit(turva, [4.2, 6.8], "en", ajankohta)
    assert en[0][0] == "🥶 Cold water: dry suit"
    assert "south-easterly wind 7.5 m/s" in en[1][1] and "Mustasalmi" in en[1][1]


def test_viestit_markapuku_ja_ei_varoitusta():
    viestit = turvallisuus.viestit({"meri": 13.0}, [12.5, 16.0], "fi", ajankohta)
    assert [o for o, _ in viestit] == ["🌡️ Vesi liian kylmää ilman märkäpukua"]
    assert turvallisuus.viestit({"meri": 18.0, "vesi": 5}, [17.0, 19.5], "fi", ajankohta) == []

