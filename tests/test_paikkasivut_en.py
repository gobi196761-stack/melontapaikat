import paikkasivut
import paikkasivut_en
from paikat import PAIKAT
from test_app import pyynto


def test_kaannokset_vastaavat_suomenkielisia():
    """Jokaisella paikalla englanninkielinen kuvaus samoin osioin, kappalein, lähtö- ja loppupaikoin ja huomioin."""
    for p in PAIKAT:
        fi, en = paikkasivut.KUVAUKSET[p.nimi], paikkasivut_en.KUVAUKSET[p.nimi]
        assert len(fi.osiot) == len(en.osiot), p.nimi
        assert fi.johdanto.count("\n\n") == en.johdanto.count("\n\n"), p.nimi
        for (o, t), (_, t_en) in zip(fi.osiot, en.osiot):
            assert t.count("\n\n") == t_en.count("\n\n"), (p.nimi, o)
        assert len(paikkasivut.LAHTO_LOPPU.get(p.nimi, ())) == len(paikkasivut_en.LAHTO_LOPPU.get(p.nimi, ())), p.nimi
        assert len([k for k in p.kohteet if k.huom]) == len(paikkasivut_en.HUOMIOT.get(p.nimi, ())), p.nimi
    assert set(paikkasivut_en.KUVAUKSET) == {p.nimi for p in PAIKAT}


def test_englanninkielinen_paikkasivu():
    status, _, sivu = pyynto("/paikka/kipina-iijoki", "kieli=en")
    assert status == "200 OK" and '<html lang="en">' in sivu
    assert "the best play spot at Kipinä" in sivu and "<h2>Sources</h2>" in sivu
    assert "Features and their limits" in sivu and "works " in sivu and "gauge:" in sivu
    assert "slow surf wave, no eddy" in sivu                       # kohteen huomio käännetty
    assert 'href="/?kieli=en">← All spots' in sivu
    assert 'href="/paikka/kipina-iijoki" hreflang="fi"' in sivu    # takaisin suomeksi
    sivu = pyynto("/paikka/kuusinkijoki", "kieli=en")[2]
    assert "<b>Put-in:</b> The channel below the Myllykoski power plant" in sivu
    assert "🚗 directions" in sivu
    fi = pyynto("/paikka/kuusinkijoki")[2]
    assert '<html lang="fi">' in fi and "<b>Lähtö:</b>" in fi and 'href="/paikka/kuusinkijoki?kieli=en"' in fi

