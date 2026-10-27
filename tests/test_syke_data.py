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


def test_kolmas_arvio_eilinen_plus_tuntiarvioiden_derivaatta():
    """Kolmas arvio = eilinen havainto + 24 h × tuntiarvioiden (mitatut tunnit) suoran kulmakerroin."""
    m = syke_data.TARKENNETUT["61/q6101750y"]
    ajot = arvioajot2()
    ajot["61/q6101600y/reaaliaika_tunnit"] = {f"2026-10-18T{t:02d}": 70.0 - 0.5 * t for t in range(0, 11)}
    ajot["61/q6100700y/reaaliaika_tunnit"] = {f"2026-10-18T{t:02d}": 205.0 for t in range(0, 11)}
    ajot["61/q6101210y/reaaliaika_tunnit"] = {f"2026-10-18T{t:02d}": 40.0 for t in range(0, 11)}
    ajot["61/l611331001y/reaaliaika_tunnit"] = {f"2026-10-18T{t:02d}": 108.59 for t in range(0, 9)}
    arvo, derivaatta = syke_data.kolmas_arvio("61/q6101750y", ajot, dt.date(2026, 10, 18))
    # vain Siurua muuttuu (−0.5/h): tuntiarvio muuttuu Siuruan kertoimen verran (eilinen ≥ 350: iso)
    assert derivaatta == pytest.approx(m.iso[3] * -0.5)
    assert arvo == pytest.approx(398.97 + 24 * m.iso[3] * -0.5)
    l = maalismaa()
    syke_data.arvioi_tanaan(l, ajot)
    assert l.kolmas_arvio == (syke_data.KOLMAS_NIMI, pytest.approx(arvo))
    # ilman tuntimittauksia tai eilistä havaintoa ei kolmatta arviota
    assert syke_data.kolmas_arvio("61/q6101750y", arvioajot2(), dt.date(2026, 10, 18)) is None
    ajot["61/q6101750y/ajo.json"] = ajo(qhav=sarja("2026-10-15", 401.49))
    assert syke_data.kolmas_arvio("61/q6101750y", ajot, dt.date(2026, 10, 18)) is None


def test_neljas_arvio_eilinen_plus_tuntikayran_muutos():
    """Neljäs arvio = eilinen havainto + (tämän päivän tuntikäyrän ka − eilisen tuntiarvioiden ka); käyrä
    mitatuilta tunneilta sellaisenaan, loppupäivä kahden viimeisen tunnin derivaatalla."""
    m = syke_data.TARKENNETUT["61/q6101750y"]
    ajot = {
        "61/q6101750y/ajo.json": ajo(qhav=sarja("2026-10-15", 404.0, 401.49, 398.97)),
        "61/q6101600y/ajo.json": ajo(qhav=sarja("2026-10-16", 68.0, "67.3", "66.8")),
        "61/q6100700y/ajo.json": ajo(qhav=sarja("2026-10-16", 212.0, 210.0, 205.0)),
        "61/q6101210y/ajo.json": ajo(qhav=sarja("2026-10-16", 42.0, 41.0, 40.0)),
        "61/l611331001y/ajo.json": ajo(whav=sarja("2026-10-15", 108.55, 108.56, 108.56),
                                       wlask_ka=sarja("2026-10-17", 108.40, 108.43)),
    }
    tunnit = lambda paiva, f, n=24: {f"2026-10-{paiva}T{t:02d}": f(t) for t in range(n)}   # noqa: E731
    ajot["61/q6101600y/reaaliaika_tunnit"] = {**tunnit(17, lambda t: 67.3), **tunnit(18, lambda t: 67.0 - 0.4 * t, 11)}
    ajot["61/q6100700y/reaaliaika_tunnit"] = {**tunnit(17, lambda t: 210.0), **tunnit(18, lambda t: 205.0, 11)}
    ajot["61/q6101210y/reaaliaika_tunnit"] = {**tunnit(17, lambda t: 41.0), **tunnit(18, lambda t: 40.0, 11)}
    ajot["61/l611331001y/reaaliaika_tunnit"] = {**tunnit(17, lambda t: 108.56), **tunnit(18, lambda t: 108.59, 11)}
    paiva = dt.date(2026, 10, 18)
    arvo, derivaatta = syke_data.neljas_arvio("61/q6101750y", ajot, paiva)
    # kahden viimeisen tunnin derivaatta: vain Siurua muuttuu (−0.4/h)
    assert derivaatta == pytest.approx(m.iso[3] * -0.4)
    e = syke_data.tuntiarviot("61/q6101750y", ajot, paiva - dt.timedelta(days=1))["arviot"]
    t = syke_data.tuntiarviot("61/q6101750y", ajot, paiva)
    kayra = [t["arviot"][h] if h <= t["viim"] else t["arviot"][t["viim"]] + derivaatta * (h - t["viim"])
             for h in range(24)]
    assert arvo == pytest.approx(398.97 + sum(kayra) / 24 - sum(e.values()) / len(e))
    l = maalismaa()
    syke_data.arvioi_tanaan(l, ajot)
    assert l.neljas_arvio == (syke_data.NELJAS_NIMI, pytest.approx(arvo))
    # ennen SYKE:n iltapäivitystä tuorein mittaus on toissapäivältä: ankkuri 16.10., käyrän muutos siitä
    ajot2 = dict(ajot)
    ajot2["61/q6101750y/ajo.json"] = ajo(qhav=sarja("2026-10-14", 406.0, 404.0, 401.49))
    for a, v in (("61/q6101600y", 68.0), ("61/q6100700y", 212.0), ("61/q6101210y", 42.0), ("61/l611331001y", 108.55)):
        ajot2[f"{a}/reaaliaika_tunnit"] = {**tunnit(16, lambda t, v=v: v), **ajot[f"{a}/reaaliaika_tunnit"]}
    for a, sarjat in (("61/q6101600y", (69.0, 68.0, "67.3", "66.8")), ("61/q6100700y", (214.0, 212.0, 210.0, 205.0)),
                      ("61/q6101210y", (43.0, 42.0, 41.0, 40.0))):
        ajot2[f"{a}/ajo.json"] = ajo(qhav=sarja("2026-10-15", *sarjat))
    ajot2["61/l611331001y/ajo.json"] = ajo(whav=sarja("2026-10-14", 108.55, 108.55, 108.56, 108.56),
                                           wlask_ka=sarja("2026-10-17", 108.40, 108.43))
    arvo2, _ = syke_data.neljas_arvio("61/q6101750y", ajot2, paiva)
    pohja = syke_data.tuntiarviot("61/q6101750y", ajot2, dt.date(2026, 10, 16))["arviot"]
    t2 = syke_data.tuntiarviot("61/q6101750y", ajot2, paiva)
    d2 = (t2["arviot"][t2["viim"]] - t2["arviot"][t2["viim"] - 2]) / 2
    kayra2 = [t2["arviot"][h] if h <= t2["viim"] else t2["arviot"][t2["viim"]] + d2 * (h - t2["viim"])
              for h in range(24)]
    assert arvo2 == pytest.approx(401.49 + sum(kayra2) / 24 - sum(pohja.values()) / len(pohja))
    k3, d3 = syke_data.kolmas_arvio("61/q6101750y", ajot2, paiva)
    assert k3 == pytest.approx(401.49 + 48 * d3)   # kaksi päivää mittauksesta
    # ilman mittauspäivän tuntiarvioita (sen syötteitä ei ole) ei neljättä arviota
    for a in ("61/q6101600y", "61/q6100700y", "61/q6101210y", "61/l611331001y"):
        ajot[f"{a}/reaaliaika_tunnit"] = {k: v for k, v in ajot[f"{a}/reaaliaika_tunnit"].items() if "-18T" in k}
    assert syke_data.neljas_arvio("61/q6101750y", ajot, paiva) is None


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


def test_lukema_pelkasta_ajosta():
    """Myllykoski (Kuusinkijoki): asemalla vain mallin virtaama, kaaviokuvaa ei saada luettua."""
    ajo = {"ennustepvm_www": "2026-10-23",
           "qinlask_ka": {"ensim_pvm": "2026-10-21", "lst": [11.3, 11.2, 11.1, 10.9, 10.8]}}
    lukema = syke_data.lukema_ajosta("73/q7300350y/qinlyhyt.png", ajo)
    assert lukema.suure == "virtaama" and lukema.yksikko == "m3/s"
    assert lukema.malli == 11.1 and lukema.havaittu is None and lukema.arvo == 11.1
    assert lukema.ennuste == {1: 10.9, 2: 10.8} and lukema.tietolahde == "SYKE-data"
    assert syke_data.lukema_ajosta("73/q7300350y/qinlyhyt.png", None) is None
    assert syke_data.lukema_ajosta("73/q7300350y/qinlyhyt.png", {"ennustepvm_www": "2026-10-23"}) is None
