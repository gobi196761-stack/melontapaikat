import datetime as dt

import pytest

import syke_data
from syke_kaavio import Kaaviolukema


def ajo(**sarjat):
    return {"ennustepvm_www": "2026-10-18", **sarjat}


def sarja(alku, *arvot):
    return {"ensim_pvm": alku, "lst": list(arvot)}


def lukema(url="60/q6000410y/wlyhyt.png", yksikko="m", havaittu=10.50, malli=10.40):
    return Kaaviolukema(url=url, suure="vedenkorkeus", yksikko=yksikko, tanaan_paiva=18,
                        havaittu=havaittu, havaittu_paivia_sitten=0, malli=malli,
                        ennuste={1: 10.41, 2: 10.42})


def test_ajo_avain():
    assert syke_data.ajo_avain("67/q6702110y/wlyhyt.png") == "67/q6702110y/ajo.json"
    assert syke_data.ajo_avain("wlyhyt.png") is None


def test_taydentaa_havainnon_mallin_ja_ennusteen():
    l = lukema()
    virhe = syke_data.taydenna(l, ajo(whav=sarja("2026-10-16", 10.47, 10.51, 10.53),
                                      wlask_ka=sarja("2026-10-17", 10.40, 10.45, 10.46, None, 10.48)))
    assert virhe is None
    assert l.havaittu == 10.53 and l.havaittu_paivia_sitten == 0
    assert l.malli == 10.45
    assert l.ennuste == {1: 10.46, 3: 10.48}
    assert l.lahde == "havainto, SYKE-data"


def test_tuorein_havainto_eiliselta():
    l = lukema(url="61/q6101750y/qin3lyhyt.png", yksikko="m3/s", havaittu=None, malli=380.0)
    syke_data.taydenna(l, ajo(qhav=sarja("2026-10-16", "375.33", "398.97"),
                              qinlask_ka=sarja("2026-10-18", 385.0, 390.0)))
    assert l.havaittu == 398.97 and l.havaittu_paivia_sitten == 1
    assert l.lahde == "havainto 1 pv sitten, SYKE-data"


def test_ei_tasmaa_kuvaan():
    l = lukema()
    virhe = syke_data.taydenna(l, ajo(whav=sarja("2026-10-18", 100.0), wlask_ka=sarja("2026-10-18", 100.0)))
    assert virhe and "ei täsmää" in virhe
    assert l.havaittu == 10.50 and l.tietolahde == "kaavio"


MAALISMAA = "https://wwwi2.ymparisto.fi/i2/61/q6101750y/qin3lyhyt.png"


def maalismaa(sitten=1):
    return Kaaviolukema(url=MAALISMAA, suure="virtaama", yksikko="m3/s", tanaan_paiva=18,
                        havaittu=398.97, havaittu_paivia_sitten=sitten, malli=394.0)


def arvioajot(maalismaa_eilen=398.97):
    return {
        "61/q6101750y/ajo.json": ajo(qhav=sarja("2026-10-17", maalismaa_eilen)),
        "61/q6101600y/ajo.json": ajo(qhav=sarja("2026-10-17", "67.3", "66.8")),
        # Pudasjärvi: tämän päivän havainto puuttuu -> eilinen + mallin muutos (+0.03 m)
        "61/l611331001y/ajo.json": ajo(whav=sarja("2026-10-16", 108.56, 108.56),
                                       wlask_ka=sarja("2026-10-17", 108.40, 108.43)),
    }


def kaava(k, q, h, h1):
    return k.vakio + k.virtaama * q + k.kuutio * (((h + h1) / 2 - 10590) / 100) ** 3 + k.muutos * (h - h1)


def test_arviomalli_korjaa_eilisella_virheella():
    m = syke_data.ARVIOMALLIT["61/q6101750y"]
    l = maalismaa()
    assert syke_data.arvioi_tanaan(l, arvioajot()) is None
    k = m.pieni                                   # eilinen 398.97 < 450
    tanaan, eilen = kaava(k, 66.8, 10859, 10856), kaava(k, 67.3, 10856, 10856)
    assert l.havaittu == pytest.approx(tanaan + k.alfa * (398.97 - eilen))
    assert l.havaittu_paivia_sitten == 0
    assert l.lahde == "arvio Pudasjärvi + Siurua, eilinen korjaus"
    assert l.malli == 394.0   # ennusteen muutos lasketaan edelleen SYKE:n mallista


def test_arviomalli_isot_virtaamat_omilla_kertoimilla():
    m = syke_data.ARVIOMALLIT["61/q6101750y"]
    l = maalismaa()
    syke_data.arvioi_tanaan(l, arvioajot(maalismaa_eilen=620.0))
    k = m.iso
    tanaan, eilen = kaava(k, 66.8, 10859, 10856), kaava(k, 67.3, 10856, 10856)
    assert l.havaittu == pytest.approx(tanaan + k.alfa * (620.0 - eilen))


def test_arviomalli_kaksi_paivaa_vanha_havainto_painaa_vahemman():
    m = syke_data.ARVIOMALLIT["61/q6101750y"]
    ajot = arvioajot()
    ajot["61/q6101750y/ajo.json"] = ajo(qhav=sarja("2026-10-16", 375.33))
    ajot["61/q6101600y/ajo.json"] = ajo(qhav=sarja("2026-10-16", 47.94, "67.3", "66.8"))
    ajot["61/l611331001y/ajo.json"]["whav"] = sarja("2026-10-15", 108.57, 108.56, 108.56)
    l = maalismaa(sitten=2)
    syke_data.arvioi_tanaan(l, ajot)
    k = m.pieni
    tanaan, toissa = kaava(k, 66.8, 10859, 10856), kaava(k, 47.94, 10856, 10857)
    assert l.havaittu == pytest.approx(tanaan + k.alfa ** 2 * (375.33 - toissa))


def test_arviomalli_ei_koske_tuoreeseen_havaintoon_tai_muihin():
    l = maalismaa(sitten=0)
    syke_data.arvioi_tanaan(l, arvioajot())
    assert l.havaittu == 398.97 and l.tietolahde == "kaavio"
    l = lukema()
    l.havaittu_paivia_sitten = 1
    syke_data.arvioi_tanaan(l, arvioajot())
    assert l.havaittu == 10.50


def test_arviomalli_puuttuva_syote():
    ajot = arvioajot()
    del ajot["61/l611331001y/ajo.json"]
    l = maalismaa()
    virhe = syke_data.arvioi_tanaan(l, ajot)
    assert virhe and "puuttuu" in virhe
    assert l.havaittu == 398.97 and l.havaittu_paivia_sitten == 1


def arvioajot2(maalismaa_eilen=398.97, maalismaa_toissa=401.49):
    return {
        "61/q6101750y/ajo.json": ajo(qhav=sarja("2026-10-16", maalismaa_toissa, maalismaa_eilen)),
        "61/q6101600y/ajo.json": ajo(qhav=sarja("2026-10-17", "67.3", "66.8")),
        "61/q6100700y/ajo.json": ajo(qhav=sarja("2026-10-17", 210.0, 205.0)),
        "61/q6101210y/ajo.json": ajo(qhav=sarja("2026-10-17", 41.0, 40.0)),
        # Pudasjärvi: tämän päivän havainto puuttuu -> eilinen + mallin muutos (+0.03 m)
        "61/l611331001y/ajo.json": ajo(whav=sarja("2026-10-16", 108.56, 108.56),
                                       wlask_ka=sarja("2026-10-17", 108.40, 108.43)),
    }


def kaava2(b, q1, q2, s, k, l, s1, k1, l1, h, h1, viikonpaiva):
    x = [1, q1, q2, s, k, l, s1, k1, l1, (((h + h1) / 2 - 10590) / 100) ** 3, h - h1] \
        + [1.0 if viikonpaiva == i else 0.0 for i in range(1, 7)]
    return sum(a * c for a, c in zip(x, b))


def test_toinen_arvio_syotteista_ja_kahdesta_edellisesta_paivasta():
    m = syke_data.TARKENNETUT["61/q6101750y"]
    l = maalismaa()
    assert syke_data.arvioi_tanaan(l, arvioajot2()) is None
    # 18.10.2026 on sunnuntai; eilinen 398.97 >= 350 -> suurten virtaamien kertoimet
    odotettu = kaava2(m.iso, 398.97, 401.49, 66.8, 205.0, 40.0, 67.3, 210.0, 41.0, 10859, 10856, 6)
    assert l.toinen_arvio == ("Siurua + Kurenalus + Livojoki + Pudasjärvi", pytest.approx(odotettu))
    # ensisijainen arvio on edelleen nykyinen malli
    assert l.lahde == "arvio Pudasjärvi + Siurua, eilinen korjaus"
    assert l.havaittu == pytest.approx(syke_data.arvioi_paiva("61/q6101750y", arvioajot2(), dt.date(2026, 10, 18)))


def test_toinen_arvio_pienet_virtaamat_omilla_kertoimilla():
    m = syke_data.TARKENNETUT["61/q6101750y"]
    l = maalismaa()
    syke_data.arvioi_tanaan(l, arvioajot2(maalismaa_eilen=300.0, maalismaa_toissa=310.0))
    odotettu = kaava2(m.pieni, 300.0, 310.0, 66.8, 205.0, 40.0, 67.3, 210.0, 41.0, 10859, 10856, 6)
    assert l.toinen_arvio[1] == pytest.approx(odotettu)


def test_toinen_arvio_puuttuva_eilinen_arvioidaan():
    """Jos eilinen Maalismaan havainto puuttuu, sen tilalla on mallin arvio eiliselle."""
    ajot = arvioajot2()
    ajot["61/q6101750y/ajo.json"] = ajo(qhav=sarja("2026-10-15", 395.0, 401.49))   # 17.10. puuttuu
    ajot["61/q6101600y/ajo.json"] = ajo(qhav=sarja("2026-10-16", 68.0, "67.3", "66.8"))
    ajot["61/q6100700y/ajo.json"] = ajo(qhav=sarja("2026-10-16", 212.0, 210.0, 205.0))
    ajot["61/q6101210y/ajo.json"] = ajo(qhav=sarja("2026-10-16", 42.0, 41.0, 40.0))
    ajot["61/l611331001y/ajo.json"]["whav"] = sarja("2026-10-15", 108.57, 108.56, 108.56)
    eilen = syke_data.arvioi_paiva2("61/q6101750y", ajot, dt.date(2026, 10, 17))
    m = syke_data.TARKENNETUT["61/q6101750y"]
    assert eilen == pytest.approx(kaava2(m.iso, 401.49, 395.0, 67.3, 210.0, 41.0, 68.0, 212.0, 42.0,
                                        10856, 10856, 5))
    tanaan = syke_data.arvioi_paiva2("61/q6101750y", ajot, dt.date(2026, 10, 18))
    assert tanaan == pytest.approx(kaava2(m.iso, eilen, 401.49, 66.8, 205.0, 40.0, 67.3, 210.0, 41.0,
                                         10859, 10856, 6))


def test_toinen_arvio_reaaliaikamittaukset_taydentavat_tanaan():
    """Tämän päivän puuttuva päiväarvo otetaan SYKE:n reaaliaikamittausten keskiarvosta."""
    data = "18.10.2026;14:00;108,630;\n18.10.2026;13:00;108,610;\n17.10.2026;23:00;108,560;\n".encode("latin-1")
    assert syke_data.lue_reaaliaika(data) == {"2026-10-18": pytest.approx(108.62), "2026-10-17": 108.56}
    ajot = arvioajot2()
    ajot["61/l611331001y/reaaliaika"] = syke_data.lue_reaaliaika(data)
    m = syke_data.TARKENNETUT["61/q6101750y"]
    tanaan = syke_data.arvioi_paiva2("61/q6101750y", ajot, dt.date(2026, 10, 18))
    # 18.10.: reaaliaikamittausten keskiarvo 108.62 m (ilman sitä ennusteella korjattu 108.59 m)
    assert tanaan == pytest.approx(kaava2(m.iso, 398.97, 401.49, 66.8, 205.0, 40.0, 67.3, 210.0, 41.0,
                                         10862, 10856, 6))
    # päiväarvo voittaa reaaliaikadatan
    assert syke_data.syotteen_arvo({"qhav": sarja("2026-10-18", 50.0)}, dt.date(2026, 10, 18),
                                   reaaliaika={"2026-10-18": 49.0}) == 50.0
    assert syke_data.syotteen_arvo({}, dt.date(2026, 10, 18), reaaliaika={"2026-10-18": 49.0}) == 49.0
    haetut = []
    ajot2 = {}
    syke_data.lisaa_reaaliaika(ajot2, lambda url: haetut.append(url) or (data if "W6100710_N43" in url else None))
    assert "https://wwwi3.ymparisto.fi/i3/RealTime/data/Q6101600.txt" in haetut
    assert sorted(ajot2) == ["61/l611331001y/reaaliaika", "61/l611331001y/reaaliaika_tunnit"]
    assert ajot2["61/l611331001y/reaaliaika_tunnit"] == {"2026-10-18T14": 108.63, "2026-10-18T13": 108.61,
                                                        "2026-10-17T23": 108.56}


def test_toinen_arvio_vain_ilman_tuoretta_havaintoa():
    l = maalismaa(sitten=0)
    syke_data.arvioi_tanaan(l, arvioajot2())
    assert l.toinen_arvio is None and l.havaittu == 398.97


def test_lampotila_ja_puuttuva_sarja_ohitetaan():
    l = lukema(url="61/q6101400y/twlyhyt.png", yksikko="°C")
    assert syke_data.taydenna(l, ajo(tw_ka=sarja("2026-10-18", 3.0))) is None
    assert l.tietolahde == "kaavio"
    l = lukema()
    assert syke_data.taydenna(l, ajo()) is None
    assert l.havaittu == 10.50 and l.tietolahde == "kaavio"


def test_tuntiarviot_ja_loppupaivan_ennuste():
    """Tuntiarvo syötteiden tuntimittauksista; loppupäivälle syötteiden 6 h trendi jatkuu."""
    m = syke_data.TARKENNETUT["61/q6101750y"]
    ajot = arvioajot2()
    tunnit = lambda alku, kulma: {f"2026-10-18T{t:02d}": alku + kulma * t for t in range(0, 11)}   # noqa: E731
    ajot["61/q6101600y/reaaliaika_tunnit"] = tunnit(70.0, -0.5)     # Siurua laskee
    ajot["61/q6100700y/reaaliaika_tunnit"] = tunnit(205.0, 0.0)
    ajot["61/q6101210y/reaaliaika_tunnit"] = tunnit(40.0, 0.0)
    ajot["61/l611331001y/reaaliaika_tunnit"] = {f"2026-10-18T{t:02d}": 108.59 for t in range(0, 9)}
    tulos = syke_data.tuntiarviot("61/q6101750y", ajot, dt.date(2026, 10, 18))
    assert tulos["viim"] == 8 and sorted(tulos["arviot"]) == list(range(9)) and max(tulos["ennuste"]) == 23
    # klo 5: syötteet mitattuja; Pudasjärvellä eilinen päiväarvo 108.56 m
    odotettu = kaava2(m.iso, 398.97, 401.49, 67.5, 205.0, 40.0, 67.3, 210.0, 41.0, 10859, 10856, 6)
    assert tulos["arviot"][5] == pytest.approx(odotettu)
    # klo 20: Siurua jatkaa laskuaan 0.5/h (70 − 0.5·20 = 60), Pudasjärvi pysyy (trendi 0)
    odotettu20 = kaava2(m.iso, 398.97, 401.49, 60.0, 205.0, 40.0, 67.3, 210.0, 41.0, 10859, 10856, 6)
    assert tulos["ennuste"][20] == pytest.approx(odotettu20)
    kaikki = {**tulos["ennuste"], **tulos["arviot"]}
    assert tulos["keskiarvo"] == pytest.approx(sum(kaikki.values()) / 24)
    # ilman jonkin syötteen tuntimittauksia ei tuntiarvioita
    del ajot["61/q6101210y/reaaliaika_tunnit"]
    assert syke_data.tuntiarviot("61/q6101750y", ajot, dt.date(2026, 10, 18)) is None
