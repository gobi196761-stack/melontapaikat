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


def test_lampotila_ja_puuttuva_sarja_ohitetaan():
    l = lukema(url="61/q6101400y/twlyhyt.png", yksikko="°C")
    assert syke_data.taydenna(l, ajo(tw_ka=sarja("2026-10-18", 3.0))) is None
    assert l.tietolahde == "kaavio"
    l = lukema()
    assert syke_data.taydenna(l, ajo()) is None
    assert l.havaittu == 10.50 and l.tietolahde == "kaavio"
