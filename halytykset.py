"""Melontahälytykset: Web Push -ilmoitus, kun tilattujen paikkojen pisteet nousevat rajaan.

Selain tilaa push-ilmoitukset (service worker /sw.js) ja lähettää tilauksen
osoitteeseen /api/halytys: paikat (tyhjä = kaikki Suomen paikat) ja pisteraja.
Tilaukset ovat Firestoressa (kokoelma KOKOELMA). Vercel Cron kutsuu aamuisin
/api/halyta, joka laskee päivän tilanteen ja lähettää ilmoituksen paikoista,
joiden pisteet ovat tänään tai ennusteessa (+1…+14 pv) vähintään rajan verran.
Samasta paikasta ei ilmoiteta uudelleen ennen kuin pisteet ovat välillä
laskeneet rajan alle.

Viestit salataan RFC 8291:n mukaan (aes128gcm) ja palvelin tunnistautuu
VAPID-avaimella (RFC 8292). Avainpari luetaan ympäristömuuttujista
VAPID_PUBLIC_KEY ja VAPID_PRIVATE_KEY (base64url: pakkaamaton P-256-piste ja
32-tavuinen yksityinen avain); jos niitä ei ole, palvelin luo parin kerran ja
tallentaa sen Firestoreen (asetukset/vapid). VAPID_SUBJECT = yhteystieto
push-palvelulle (mailto: tai https:).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

KOKOELMA = "halytykset"
ASETUKSET = ("asetukset", "vapid")
OLETUS_SUBJECT = "mailto:melontapaikat@example.com"
TTL_S = 12 * 3600   # push-palvelu säilyttää viestin, jos puhelin on pois verkosta
# Vain tunnettujen push-palvelujen osoitteisiin lähetetään (tilauksen osoite tulee selaimelta)
PUSH_PALVELUT = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
                 ".push.apple.com", ".notify.windows.com")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(teksti: str) -> bytes:
    return base64.urlsafe_b64decode(teksti + "=" * (-len(teksti) % 4))


def tunniste(endpoint: str) -> str:
    """Firestore-dokumentin tunniste tilauksen osoitteesta."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:40]


def sallittu_osoite(endpoint: str) -> bool:
    osa = urllib.parse.urlsplit(endpoint)
    isanta = (osa.hostname or "").lower()
    return osa.scheme == "https" and any(isanta == p or (p.startswith(".") and isanta.endswith(p))
                                         for p in PUSH_PALVELUT)


# ---------------------------------------------------------------------------
# Avaimet, salaus ja VAPID
# ---------------------------------------------------------------------------

def luo_avaimet() -> tuple[str, str]:
    """Uusi VAPID-avainpari: (julkinen, yksityinen) base64url-muodossa."""
    from cryptography.hazmat.primitives.asymmetric import ec
    avain = ec.generate_private_key(ec.SECP256R1())
    return _julkinen(avain), b64(avain.private_numbers().private_value.to_bytes(32, "big"))


def _julkinen(avain) -> str:
    from cryptography.hazmat.primitives import serialization
    return b64(avain.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint))


def _yksityinen(teksti: str):
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec.derive_private_key(int.from_bytes(unb64(teksti), "big"), ec.SECP256R1())


_avaimet: tuple[float, tuple[str, str] | None] | None = None


def avaimet(kanta=None) -> tuple[str, str] | None:
    """(julkinen, yksityinen): ympäristömuuttujista tai Firestoresta (luodaan tarvittaessa).
    None, jos kumpaakaan ei ole käytettävissä. Tulos pidetään muistissa."""
    global _avaimet
    julkinen, yksityinen = os.environ.get("VAPID_PUBLIC_KEY", ""), os.environ.get("VAPID_PRIVATE_KEY", "")
    if julkinen and yksityinen:
        return julkinen, yksityinen
    if _avaimet and (_avaimet[1] or time.monotonic() - _avaimet[0] < 600):   # epäonnistuminen 10 min
        return _avaimet[1]
    tulos = None
    try:
        import firestore
        kanta = kanta or firestore.Firestore.ymparistosta(aikaraja=5)   # sivun lataus ei jää odottamaan
        if kanta:
            tallessa = kanta.lue(*ASETUKSET)
            if not tallessa:   # luodaan kerran; samanaikainen luonti: toisen tallentama pari voittaa
                julkinen, yksityinen = luo_avaimet()
                kanta.luo(*ASETUKSET, {"julkinen": julkinen, "yksityinen": yksityinen})
                tallessa = kanta.lue(*ASETUKSET)
            tulos = (tallessa["julkinen"], tallessa["yksityinen"])
    except Exception:  # Firestore ei käytettävissä: hälytykset pois päältä
        tulos = None
    _avaimet = (time.monotonic(), tulos)
    return tulos


def salaa(viesti: bytes, p256dh: str, auth: str) -> bytes:
    """Viestin salaus vastaanottajan avaimille (RFC 8291, Content-Encoding: aes128gcm)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    ua_julkinen = unb64(p256dh)
    vastaanottaja = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_julkinen)
    oma = ec.generate_private_key(ec.SECP256R1())
    as_julkinen = oma.public_key().public_bytes(serialization.Encoding.X962,
                                                serialization.PublicFormat.UncompressedPoint)
    jaettu = oma.exchange(ec.ECDH(), vastaanottaja)
    ikm = HKDF(hashes.SHA256(), 32, unb64(auth), b"WebPush: info\0" + ua_julkinen + as_julkinen).derive(jaettu)
    suola = os.urandom(16)
    cek = HKDF(hashes.SHA256(), 16, suola, b"Content-Encoding: aes128gcm\0").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, suola, b"Content-Encoding: nonce\0").derive(ikm)
    salattu = AESGCM(cek).encrypt(nonce, viesti + b"\x02", None)   # yksi tietue, ei täytettä
    return suola + (4096).to_bytes(4, "big") + bytes([len(as_julkinen)]) + as_julkinen + salattu


def vapid_otsake(endpoint: str, julkinen: str, yksityinen: str, nyt: float | None = None) -> str:
    """Authorization-otsake: ES256-allekirjoitettu JWT push-palvelun osoitteelle (RFC 8292)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    osa = urllib.parse.urlsplit(endpoint)
    vaite = {"aud": f"{osa.scheme}://{osa.netloc}", "exp": int((nyt or time.time()) + TTL_S),
             "sub": os.environ.get("VAPID_SUBJECT") or OLETUS_SUBJECT}
    alku = (b64(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode()) + "."
            + b64(json.dumps(vaite, separators=(",", ":")).encode()))
    r, s = decode_dss_signature(_yksityinen(yksityinen).sign(alku.encode("ascii"), ec.ECDSA(hashes.SHA256())))
    return f"vapid t={alku}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}, k={julkinen}"


def laheta(tilaus: dict, viesti: dict, avainpari: tuple[str, str], avaa=urllib.request.urlopen) -> int:
    """Lähettää viestin (JSON) tilaukselle; palauttaa push-palvelun HTTP-tilan (0 = ei yhteyttä).
    404/410 = tilaus on vanhentunut ja se poistetaan."""
    if not sallittu_osoite(tilaus["endpoint"]):
        return 400
    runko = salaa(json.dumps(viesti, ensure_ascii=False).encode("utf-8"), tilaus["p256dh"], tilaus["auth"])
    pyynto = urllib.request.Request(tilaus["endpoint"], data=runko, method="POST", headers={
        "Authorization": vapid_otsake(tilaus["endpoint"], *avainpari), "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream", "TTL": str(TTL_S), "Urgency": "normal"})
    try:
        with avaa(pyynto, timeout=15) as v:
            return v.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Tilaukset ja hälytysten valinta
# ---------------------------------------------------------------------------

def tarkista_tilaus(data, paikkojen_nimet) -> tuple[dict | None, str]:
    """Selaimen lähettämä tilaus tallennettavaan muotoon: (tilaus, virhe)."""
    if not isinstance(data, dict):
        return None, "virheellinen pyyntö"
    t = data.get("tilaus") or {}
    endpoint, avaimet_ = t.get("endpoint"), t.get("keys") or {}
    if not isinstance(endpoint, str) or not sallittu_osoite(endpoint) or len(endpoint) > 1000:
        return None, "tuntematon push-palvelu"
    p256dh, auth = avaimet_.get("p256dh"), avaimet_.get("auth")
    try:
        if len(unb64(p256dh)) != 65 or len(unb64(auth)) != 16:
            raise ValueError
    except (TypeError, ValueError):
        return None, "tilauksen avaimet puuttuvat"
    paikat, raja = data.get("paikat", []), data.get("raja")
    if not isinstance(paikat, list) or any(p not in paikkojen_nimet for p in paikat):
        return None, "tuntematon paikka"
    if isinstance(raja, bool) or not isinstance(raja, int) or not 1 <= raja <= 100:
        return None, "pisterajan pitää olla 1–100"
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth, "paikat": sorted(set(paikat)), "raja": raja,
            "kieli": "en" if data.get("kieli") == "en" else "fi", "ilmoitettu": [],
            "luotu": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, ""


def parhaat(tulokset) -> dict[str, tuple[float, int]]:
    """Paikan nimi -> (paras pisteet, päivä 0…14) tältä päivältä ja ennusteesta."""
    tulos = {}
    for t in tulokset:
        paivat = ({0: t.pisteet} if t.pisteet is not None else {}) | dict(t.ennuste)
        if paivat:
            n = max(paivat, key=lambda n: (round(paivat[n]), -n))   # tasapisteissä aikaisin päivä
            tulos[t.paikka.nimi] = (paivat[n], n)
    return tulos


def uudet_halytykset(tilaus: dict, parhaat_: dict[str, tuple[float, int]],
                     oletuspaikat: list[str]) -> tuple[list[tuple[str, float, int]], list[str]]:
    """(ilmoitettavat (paikka, pisteet, päivä), rajan ylittävät paikat tallennettavaksi)."""
    paikat = tilaus.get("paikat") or oletuspaikat
    yli = [p for p in paikat if p in parhaat_ and round(parhaat_[p][0]) >= tilaus["raja"]]
    ennestaan = set(tilaus.get("ilmoitettu") or [])
    uudet = sorted(((p, *parhaat_[p]) for p in yli if p not in ennestaan), key=lambda x: (-round(x[1]), x[2]))
    return uudet, sorted(yli)


VIIKONPAIVAT = {"fi": ("ma", "ti", "ke", "to", "pe", "la", "su"), "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}


def viesti(uudet: list[tuple[str, float, int]], tanaan: dt.date, kieli: str = "fi") -> dict:
    """Ilmoituksen otsikko, teksti ja avattava osoite."""
    def paiva(n: int) -> str:
        if n == 0:
            return "today" if kieli == "en" else "tänään"
        p = tanaan + dt.timedelta(days=n)
        return f"{VIIKONPAIVAT[kieli][p.weekday()]} {p.day}.{p.month}."
    rivit = [f"{nimi} {round(pisteet)} p ({paiva(n)})" for nimi, pisteet, n in uudet[:6]]
    if len(uudet) > 6:
        rivit.append(f"+{len(uudet) - 6} " + ("more" if kieli == "en" else "muuta"))
    return {"otsikko": "Good paddling conditions" if kieli == "en" else "Hyvät melontaolot",
            "teksti": "\n".join(rivit), "url": "/?kieli=en" if kieli == "en" else "/"}


def vahvistus(tilaus: dict) -> dict:
    """Ilmoitus heti tilauksen jälkeen: kertoo, että ilmoitukset toimivat."""
    en = tilaus["kieli"] == "en"
    kohde = (f"{len(tilaus['paikat'])} " + ("spots" if en else "paikkaa")) if tilaus["paikat"] \
        else ("all spots in Finland" if en else "kaikki Suomen paikat")
    teksti = (f"You will be notified each morning when a spot reaches {tilaus['raja']} points ({kohde})." if en
              else f"Ilmoitan aamuisin, kun paikan pisteet nousevat {tilaus['raja']}:ään ({kohde}).")
    return {"otsikko": "Alert subscribed" if en else "Hälytys tilattu", "teksti": teksti,
            "url": "/?kieli=en" if en else "/"}


def aja(kanta, tulokset, oletuspaikat: list[str], tanaan: dt.date, avainpari: tuple[str, str],
        lahetin=laheta) -> dict:
    """Käy tilaukset läpi: lähettää uudet hälytykset, päivittää tilan ja poistaa vanhentuneet."""
    parhaat_ = parhaat(tulokset)
    lahetetty, poistettu, virheet = 0, 0, []
    for avain, tilaus in kanta.listaa(KOKOELMA).items():
        uudet, yli = uudet_halytykset(tilaus, parhaat_, oletuspaikat)
        if uudet:
            tila = lahetin(tilaus, viesti(uudet, tanaan, tilaus.get("kieli", "fi")), avainpari)
            if tila in (404, 410):
                kanta.poista(KOKOELMA, avain)
                poistettu += 1
                continue
            if not 200 <= tila < 300:
                virheet.append(f"{avain[:8]}: HTTP {tila}")
                continue   # yritetään uudelleen seuraavana aamuna
            lahetetty += 1
        if yli != sorted(tilaus.get("ilmoitettu") or []):
            kanta.kirjoita(KOKOELMA, avain, {**tilaus, "ilmoitettu": yli})
    return {"lahetetty": lahetetty, "poistettu": poistettu, "virheet": virheet}


SERVICE_WORKER = """// Melontahälytysten service worker: näyttää push-ilmoituksen ja avaa sivun napautuksesta
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (virhe) {}
  e.waitUntil(self.registration.showNotification(d.otsikko || "Melontahälytys",
    {body: d.teksti || "", tag: "melonta", renotify: true, data: {url: d.url || "/"}}));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data && e.notification.data.url || "/"));
});
"""
