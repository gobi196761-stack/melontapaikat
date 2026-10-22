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


def test_tilauksen_tarkistus():
    _, p256dh, auth = vastaanottaja()
    nimet = {"Kipinä (Iijoki)", "Koiteli (Kiiminkijoki)"}
    pyynto = {"tilaus": {"endpoint": FCM, "keys": {"p256dh": p256dh, "auth": auth}},
              "paikat": ["Kipinä (Iijoki)"], "raja": 60, "kieli": "en"}
    tilaus, virhe = h.tarkista_tilaus(pyynto, nimet)
    assert not virhe and tilaus["paikat"] == ["Kipinä (Iijoki)"] and tilaus["raja"] == 60 and tilaus["kieli"] == "en"
    assert tilaus["ilmoitettu"] == []
    for muutos in ({"raja": 0}, {"raja": "60"}, {"raja": True}, {"paikat": ["Tuntematon"]},
                   {"tilaus": {"endpoint": "https://example.com/x", "keys": {"p256dh": p256dh, "auth": auth}}},
                   {"tilaus": {"endpoint": FCM, "keys": {"p256dh": "abc", "auth": auth}}}):
        assert h.tarkista_tilaus({**pyynto, **muutos}, nimet)[0] is None
    assert h.tarkista_tilaus("roskaa", nimet)[0] is None


def tulos(nimi, pisteet, ennuste=None):
    return SimpleNamespace(paikka=SimpleNamespace(nimi=nimi, maa="FI"), pisteet=pisteet, ennuste=ennuste or {})


def test_halytys_kerran_kunnes_pisteet_laskevat():
    tilaus = {"paikat": [], "raja": 60, "ilmoitettu": []}
    oletus = ["A", "B", "C"]
    parhaat = h.parhaat([tulos("A", 40, {3: 72, 4: 72}), tulos("B", 65), tulos("C", 20, {1: 30})])
    assert parhaat == {"A": (72, 3), "B": (65, 0), "C": (30, 1)}   # tasapisteissä aikaisin päivä
    uudet, yli = h.uudet_halytykset(tilaus, parhaat, oletus)
    assert uudet == [("A", 72, 3), ("B", 65, 0)] and yli == ["A", "B"]
    # seuraavana aamuna samat paikat yli rajan: ei uutta ilmoitusta
    assert h.uudet_halytykset({**tilaus, "ilmoitettu": yli}, parhaat, oletus) == ([], ["A", "B"])
    # B laskee rajan alle ja nousee taas: ilmoitetaan uudelleen
    _, yli = h.uudet_halytykset({**tilaus, "ilmoitettu": ["A", "B"]}, {"A": (72, 3), "B": (50, 0)}, oletus)
    assert yli == ["A"]
    assert h.uudet_halytykset({**tilaus, "ilmoitettu": yli}, parhaat, oletus)[0] == [("B", 65, 0)]
    # valitut paikat rajaavat
    assert h.uudet_halytykset({**tilaus, "paikat": ["B"]}, parhaat, oletus)[0] == [("B", 65, 0)]


def test_viesti():
    tanaan = dt.date(2026, 10, 22)   # torstai
    v = h.viesti([("Kipinä (Iijoki)", 84.6, 0), ("Koiteli", 70, 2)], tanaan)
    assert v == {"otsikko": "Hyvät melontaolot", "teksti": "Kipinä (Iijoki) 85 p (tänään)\nKoiteli 70 p (la 24.10.)",
                 "url": "/"}
    assert h.viesti([("Koiteli", 70, 1)], tanaan, "en")["teksti"] == "Koiteli 70 p (Fri 23.10.)"


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
    perus = {"p256dh": "x", "auth": "y", "raja": 60, "kieli": "fi"}
    kanta = Kanta({(h.KOKOELMA, "eka"): {**perus, "endpoint": FCM + "1", "paikat": [], "ilmoitettu": []},
                   (h.KOKOELMA, "vanha"): {**perus, "endpoint": FCM + "2", "paikat": ["A"], "ilmoitettu": []},
                   (h.KOKOELMA, "ennestaan"): {**perus, "endpoint": FCM + "3", "paikat": ["A"], "ilmoitettu": ["A"]}})
    lahetetyt = []

    def lahetin(tilaus, viesti, avainpari):
        lahetetyt.append((tilaus["endpoint"], viesti["teksti"]))
        return 410 if tilaus["endpoint"].endswith("2") else 201

    tulos_ = h.aja(kanta, [tulos("A", 80)], ["A"], dt.date(2026, 10, 22), ("julk", "yks"), lahetin)
    assert tulos_ == {"lahetetty": 1, "poistettu": 1, "virheet": []}
    assert lahetetyt == [(FCM + "1", "A 80 p (tänään)"), (FCM + "2", "A 80 p (tänään)")]
    assert kanta.lue(h.KOKOELMA, "eka")["ilmoitettu"] == ["A"]
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
    pyynto = {"tilaus": {"endpoint": FCM, "keys": {"p256dh": p256dh, "auth": auth}},
              "paikat": [PAIKAT[0].nimi], "raja": 80}
    status, _, runko = wsgi("/api/halytys", "POST", pyynto)
    assert status == "200 OK", runko
    tallessa = kanta.lue(h.KOKOELMA, h.tunniste(FCM))
    assert tallessa["raja"] == 80 and tallessa["paikat"] == [PAIKAT[0].nimi]
    assert lahetetyt[0]["otsikko"] == "Hälytys tilattu" and "80" in lahetetyt[0]["teksti"]
    assert wsgi("/api/halytys", "POST", {**pyynto, "raja": 500})[0] == "400 Bad Request"
    assert wsgi("/api/halytys", "GET")[0] == "405 Method Not Allowed"
    assert wsgi("/api/halytys", "DELETE", {"endpoint": FCM})[0] == "200 OK"
    assert kanta.lue(h.KOKOELMA, h.tunniste(FCM)) is None


def test_tilaus_ei_kayta_ilman_firestorea(monkeypatch):
    monkeypatch.setattr(app.firestore.Firestore, "ymparistosta", classmethod(lambda cls, **kw: None))
    assert wsgi("/api/halytys", "POST", {"x": 1})[0] == "503 Service Unavailable"


def test_service_worker_ja_cron(monkeypatch):
    status, otsakkeet, runko = wsgi("/sw.js")
    assert status == "200 OK" and otsakkeet["Content-Type"].startswith("application/javascript")
    assert 'addEventListener("push"' in runko and "showNotification" in runko
    monkeypatch.setenv("CRON_SECRET", "salainen")
    assert wsgi("/api/halyta")[0] == "401 Unauthorized"
    assert any(c["path"] == "/api/halyta" for c in json.load(open("vercel.json"))["crons"])
