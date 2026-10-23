import datetime as dt
import io
import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import app
import halytykset as h
from paikat import PAIKAT

FCM = "https://fcm.googleapis.com/fcm/send/abc123"


def vastaanottaja():
    """Selaimen puoli: avainpari ja auth-salaisuus."""
    avain = ec.generate_private_key(ec.SECP256R1())
    julkinen = avain.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return avain, h.b64(julkinen), h.b64(b"0123456789abcdef")


def pura(runko: bytes, avain, auth: str) -> bytes:
    """RFC 8291 -viestin purku vastaanottajana (kuten selain)."""
    suola, idlen = runko[:16], runko[20]
    as_julkinen, salattu = runko[21:21 + idlen], runko[21 + idlen:]
    ua_julkinen = avain.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    jaettu = avain.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_julkinen))
    ikm = HKDF(hashes.SHA256(), 32, h.unb64(auth), b"WebPush: info\0" + ua_julkinen + as_julkinen).derive(jaettu)
    cek = HKDF(hashes.SHA256(), 16, suola, b"Content-Encoding: aes128gcm\0").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, suola, b"Content-Encoding: nonce\0").derive(ikm)
    selko = AESGCM(cek).decrypt(nonce, salattu, None)
    assert selko.endswith(b"\x02")
    return selko[:-1]


def test_salaus_purkautuu_vastaanottajalla():
    avain, p256dh, auth = vastaanottaja()
    runko = h.salaa("Kipinä 85 p".encode(), p256dh, auth)
    assert int.from_bytes(runko[16:20], "big") == 4096 and runko[20] == 65
    assert pura(runko, avain, auth).decode() == "Kipinä 85 p"


def test_vapid_allekirjoitus(monkeypatch):
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:testi@example.com")
    julkinen, yksityinen = h.luo_avaimet()
    otsake = h.vapid_otsake(FCM, julkinen, yksityinen, nyt=1_000_000)
    assert otsake.startswith("vapid t=") and otsake.endswith(f", k={julkinen}")
    jwt = otsake.removeprefix("vapid t=").split(",")[0]
    alku, allekirjoitus = jwt.rsplit(".", 1)
    vaite = json.loads(h.unb64(alku.split(".")[1]))
    assert vaite == {"aud": "https://fcm.googleapis.com", "exp": 1_000_000 + h.TTL_S, "sub": "mailto:testi@example.com"}
    raaka = h.unb64(allekirjoitus)
    tarkistaja = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), h.unb64(julkinen))
    tarkistaja.verify(encode_dss_signature(int.from_bytes(raaka[:32], "big"), int.from_bytes(raaka[32:], "big")),
                      alku.encode(), ec.ECDSA(hashes.SHA256()))   # ei poikkeusta = kelpaa


def test_vain_tunnetut_push_palvelut():
    assert h.sallittu_osoite(FCM) and h.sallittu_osoite("https://web.push.apple.com/abc")
    assert not h.sallittu_osoite("http://fcm.googleapis.com/x")
    assert not h.sallittu_osoite("https://evil.example.com/fcm.googleapis.com")
    assert not h.sallittu_osoite("https://169.254.169.254/latest")


VALINNAT = {"Kipinä (Iijoki)": {"": h.TASOT, "Hontto": ("toimii", "paras")},
            "Trollforsarna (Piteälven)": {"": h.TASOT, "Alapätkä": ("paras", "pisteet")}}


def test_kohteen_ehdot():
    paikka = {p.nimi: p for p in PAIKAT}
    kohteet = {k.nimi: k for k in paikka["Trollforsarna (Piteälven)"].kohteet}
    # toimii kaikilla vesillä: toimii-ehdon tilalla pisteraja; optimi, koska parhaalla alueella on raja
    assert h.kohteen_tasot(kohteet["Alapätkä (Nedre Trollforsarna)"]) == ("paras", "pisteet")
    assert h.kohteen_tasot(kohteet["Satumaa (Sagoland)"]) == ("toimii", "paras")
    valinnat = h.valittavat(PAIKAT)
    assert "Taivalkoski" not in valinnat   # ei kohteita
    assert valinnat["Trollforsarna (Piteälven)"][""] == ("toimii", "paras", "pisteet")


def test_tilauksen_tarkistus():
    _, p256dh, auth = vastaanottaja()
    pyynto = {"tilaus": {"endpoint": FCM, "keys": {"p256dh": p256dh, "auth": auth}}, "paivia": 3, "kieli": "en",
              "ehdot": [{"paikka": "Kipinä (Iijoki)", "kohde": "Hontto", "taso": "paras"},
                        {"paikka": "Kipinä (Iijoki)", "kohde": "", "taso": "pisteet", "raja": 60},
                        {"paikka": "Kipinä (Iijoki)", "kohde": "Hontto", "taso": "paras"}]}   # kaksoiskappale
    tilaus, virhe = h.tarkista_tilaus(pyynto, VALINNAT)
    assert not virhe and tilaus["paivia"] == 3 and tilaus["kieli"] == "en" and tilaus["ilmoitettu"] == []
    assert tilaus["ehdot"] == [{"paikka": "Kipinä (Iijoki)", "kohde": "Hontto", "taso": "paras"},
                               {"paikka": "Kipinä (Iijoki)", "kohde": "", "taso": "pisteet", "raja": 60}]
    vaarat = [{"paivia": 15}, {"paivia": "3"}, {"ehdot": []}, {"ehdot": "x"},
              {"ehdot": [{"paikka": "Tuntematon", "kohde": "", "taso": "toimii"}]},
              {"ehdot": [{"paikka": "Kipinä (Iijoki)", "kohde": "Muu", "taso": "toimii"}]},
              {"ehdot": [{"paikka": "Kipinä (Iijoki)", "kohde": "Hontto", "taso": "pisteet", "raja": 60}]},
              {"ehdot": [{"paikka": "Trollforsarna (Piteälven)", "kohde": "Alapätkä", "taso": "toimii"}]},
              {"ehdot": [{"paikka": "Kipinä (Iijoki)", "kohde": "", "taso": "pisteet", "raja": 0}]},
              {"ehdot": [{"paikka": "Kipinä (Iijoki)", "kohde": "", "taso": "pisteet"}]},
              {"tilaus": {"endpoint": "https://example.com/x", "keys": {"p256dh": p256dh, "auth": auth}}},
              {"tilaus": {"endpoint": FCM, "keys": {"p256dh": "abc", "auth": auth}}}]
    for muutos in vaarat:
        assert h.tarkista_tilaus({**pyynto, **muutos}, VALINNAT)[0] is None, muutos
    assert h.tarkista_tilaus("roskaa", VALINNAT)[0] is None


def kt(nimi, tila, pisteet, laatu=1.0):
    return SimpleNamespace(kohde=SimpleNamespace(nimi=nimi, laatu=laatu), tila=tila, pisteet=pisteet * laatu)


def tulos(kohteet, ennusteen_kohteet=None, pisteet=None, ennuste=None):
    return SimpleNamespace(kohteet=kohteet, ennusteen_kohteet=ennusteen_kohteet or {},
                           pisteet=pisteet, ennuste=ennuste or {})


def test_ehdon_tayttyminen():
    t = tulos([kt("A", "toimii", 70), kt("B", "ei toimi", 20, laatu=0.5)],
              {1: [kt("A", "paras", 100), kt("B", "ei toimi", 30, laatu=0.5)],
               2: [kt("A", "toimii", 65), kt("B", "toimii", 70, laatu=0.5)]},
              pisteet=70, ennuste={1: 100, 2: 67})
    e = lambda kohde, taso, raja=None: {"paikka": "P", "kohde": kohde, "taso": taso,   # noqa: E731
                                        **({"raja": raja} if raja else {})}
    assert h.tayttyy(e("", "toimii"), t, 0) == (0, "A")          # mikä tahansa toimiva kohde
    assert h.tayttyy(e("", "paras"), t, 0) is None                # ei tänään
    assert h.tayttyy(e("", "paras"), t, 3) == (1, "A")            # ensimmäinen päivä ennusteessa
    assert h.tayttyy(e("B", "toimii"), t, 1) is None and h.tayttyy(e("B", "toimii"), t, 2) == (2, "B")
    assert h.tayttyy(e("", "pisteet", 80), t, 14) == (1, "A")
    # kohteen pisteraja ilman laatukerrointa (B: 70 p, laatu 0.5)
    assert h.tayttyy(e("B", "pisteet", 70), t, 2) == (2, "B")


def test_halytys_kerran_kunnes_ehto_lakkaa():
    ehto = {"paikka": "P", "kohde": "A", "taso": "paras"}
    tilaus = {"paivia": 2, "ehdot": [ehto], "ilmoitettu": []}
    hyva = {"P": tulos([kt("A", "toimii", 70)], {2: [kt("A", "paras", 100)]})}
    uudet, tayttyvat = h.uudet_halytykset(tilaus, hyva)
    assert uudet == [(ehto, 2, "A")] and tayttyvat == ["P|A|paras|"]
    assert h.uudet_halytykset({**tilaus, "ilmoitettu": tayttyvat}, hyva) == ([], tayttyvat)   # ei toistoa
    huono = {"P": tulos([kt("A", "toimii", 70)])}
    assert h.uudet_halytykset({**tilaus, "ilmoitettu": tayttyvat}, huono) == ([], [])          # lakkasi
    assert h.uudet_halytykset({**tilaus, "paivia": 1}, hyva)[0] == []                         # liian kaukana
    assert h.uudet_halytykset({**tilaus, "ehdot": [{**ehto, "paikka": "Poistunut"}]}, hyva) == ([], [])


def test_viesti():
    tanaan = dt.date(2026, 10, 22)   # torstai
    uudet = [({"paikka": "Kipinä (Iijoki)", "kohde": "Hontto", "taso": "paras"}, 0, "Hontto"),
             ({"paikka": "Koiteli", "kohde": "", "taso": "toimii"}, 2, "Aalto"),
             ({"paikka": "Koiteli", "kohde": "", "taso": "pisteet", "raja": 60}, 1, "Aalto")]
    v = h.viesti(uudet, tanaan)
    assert v == {"otsikko": "Hyvät melontaolot", "url": "/", "teksti":
                 "Kipinä (Iijoki) – Hontto: parhaimmillaan, tänään\nKoiteli: toimii (Aalto), la 24.10.\n"
                 "Koiteli ≥ 60 p, pe 23.10."}
    assert h.viesti(uudet[1:2], tanaan, "en")["teksti"] == "Koiteli: works (Aalto), Sat 24.10."
    vahvistus = h.vahvistus({"kieli": "fi", "paivia": 3, "ehdot": [u[0] for u in uudet]})
    assert vahvistus["teksti"] == ("Ilmoitan aamuisin (3 päivän sisällä): Kipinä (Iijoki) – Hontto: parhaimmillaan; "
                                   "Koiteli: toimii; Koiteli ≥ 60 p")


class Kanta:
    """Firestore-korvike muistissa."""
    def __init__(self, data=None):
        self.data = {k: dict(v) for k, v in (data or {}).items()}

    def listaa(self, kokoelma):
        return {k[1]: dict(v) for k, v in self.data.items() if k[0] == kokoelma}

    def lue(self, kokoelma, tunniste):
        return self.data.get((kokoelma, tunniste))

    def kirjoita(self, kokoelma, tunniste, data):
        self.data[(kokoelma, tunniste)] = dict(data)

    def luo(self, kokoelma, tunniste, data):
        if (kokoelma, tunniste) in self.data:
            return False
        self.kirjoita(kokoelma, tunniste, data)
        return True

    def poista(self, kokoelma, tunniste):
        self.data.pop((kokoelma, tunniste), None)


def test_aamun_ajo():
    perus = {"p256dh": "x", "auth": "y", "paivia": 0, "kieli": "fi",
             "ehdot": [{"paikka": "P", "kohde": "", "taso": "toimii"}]}
    kanta = Kanta({(h.KOKOELMA, "eka"): {**perus, "endpoint": FCM + "1", "ilmoitettu": []},
                   (h.KOKOELMA, "vanha"): {**perus, "endpoint": FCM + "2", "ilmoitettu": []},
                   (h.KOKOELMA, "ennestaan"): {**perus, "endpoint": FCM + "3", "ilmoitettu": ["P||toimii|"]}})
    lahetetyt = []

    def lahetin(tilaus, viesti, avainpari):
        lahetetyt.append((tilaus["endpoint"], viesti["teksti"]))
        return 410 if tilaus["endpoint"].endswith("2") else 201

    paikka = tulos([kt("A", "toimii", 80)])
    paikka.paikka = SimpleNamespace(nimi="P")
    tulos_ = h.aja(kanta, [paikka], dt.date(2026, 10, 22), ("julk", "yks"), lahetin)
    assert tulos_ == {"tilauksia": 3, "lahetetty": 1, "jo_ilmoitettu": 1, "poistettu": 1, "virheet": []}
    assert lahetetyt == [(FCM + "1", "P: toimii (A), tänään"), (FCM + "2", "P: toimii (A), tänään")]
    assert kanta.lue(h.KOKOELMA, "eka")["ilmoitettu"] == ["P||toimii|"]
    assert kanta.lue(h.KOKOELMA, "vanha") is None   # vanhentunut tilaus poistettu


def test_avaimet_luodaan_kerran_firestoreen(monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.setattr(h, "_avaimet", None)
    kanta = Kanta()
    eka = h.avaimet(kanta)
    assert eka and len(h.unb64(eka[0])) == 65 and kanta.lue(*h.ASETUKSET)["julkinen"] == eka[0]
    monkeypatch.setattr(h, "_avaimet", None)
    assert h.avaimet(kanta) == eka   # sama pari seuraavalla kerralla
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "julk")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "yks")
    assert h.avaimet(kanta) == ("julk", "yks")   # ympäristömuuttujat ensin


def wsgi(polku, metodi="GET", runko=None):
    data = json.dumps(runko).encode() if runko is not None else b""
    vastaus = {}

    def start_response(status, otsakkeet):
        vastaus["status"], vastaus["otsakkeet"] = status, dict(otsakkeet)

    teksti = b"".join(app.app({"PATH_INFO": polku, "QUERY_STRING": "", "REQUEST_METHOD": metodi,
                               "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data)}, start_response))
    return vastaus["status"], vastaus["otsakkeet"], teksti.decode()


@pytest.fixture
def kanta(monkeypatch):
    kanta = Kanta()
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls, **kw: kanta))
    monkeypatch.setattr(h, "_avaimet", None)
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    return kanta


def test_tilaus_ja_peruutus(kanta, monkeypatch):
    lahetetyt = []
    monkeypatch.setattr(h, "laheta", lambda tilaus, viesti, avainpari: (lahetetyt.append(viesti), 201)[1])
    avain, p256dh, auth = vastaanottaja()
    ehto = {"paikka": PAIKAT[0].nimi, "kohde": PAIKAT[0].kohteet[0].nimi, "taso": "toimii"}
    pyynto = {"tilaus": {"endpoint": FCM, "keys": {"p256dh": p256dh, "auth": auth}}, "ehdot": [ehto], "paivia": 5}
    status, _, runko = wsgi("/api/halytys", "POST", pyynto)
    assert status == "200 OK", runko
    tallessa = kanta.lue(h.KOKOELMA, h.tunniste(FCM))
    assert tallessa["paivia"] == 5 and tallessa["ehdot"] == [ehto]
    assert lahetetyt[0]["otsikko"] == "Hälytys tilattu" and "5 päivän sisällä" in lahetetyt[0]["teksti"]
    assert wsgi("/api/halytys", "POST", {**pyynto, "paivia": 30})[0] == "400 Bad Request"
    tila = json.loads(wsgi("/api/halytys", "GET")[2])
    assert tila == {"kaytossa": True, "avaimet": "Firestoresta (asetukset/vapid)"}
    assert wsgi("/api/halytys", "PUT")[0] == "405 Method Not Allowed"
    assert wsgi("/api/halytys", "DELETE", {"endpoint": FCM})[0] == "200 OK"
    assert kanta.lue(h.KOKOELMA, h.tunniste(FCM)) is None


def test_tilaus_ei_kayta_ilman_firestorea(monkeypatch):
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls, **kw: None))
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    assert wsgi("/api/halytys", "POST", {"x": 1})[0] == "503 Service Unavailable"
    tila = json.loads(wsgi("/api/halytys", "GET")[2])
    assert tila == {"kaytossa": False, "avaimet": "FIREBASE_SERVICE_ACCOUNT puuttuu Vercelin ympäristömuuttujista"}


def test_service_worker_ja_cron(monkeypatch):
    status, otsakkeet, runko = wsgi("/sw.js")
    assert status == "200 OK" and otsakkeet["Content-Type"].startswith("application/javascript")
    assert 'addEventListener("push"' in runko and "showNotification" in runko
    monkeypatch.setenv("CRON_SECRET", "salainen")
    assert wsgi("/api/halyta")[0] == "401 Unauthorized"
    assert any(c["path"] == "/api/halyta" for c in json.load(open("vercel.json"))["crons"])
