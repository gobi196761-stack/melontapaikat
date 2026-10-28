"""Melontahälytykset: Web Push -ilmoitus, kun tilattujen paikkojen pisteet nousevat rajaan.

Selain tilaa push-ilmoitukset (service worker /sw.js) ja lähettää tilauksen
osoitteeseen /api/halytys: ehdot ja ennusteen pituus (0–14 pv). Ehto koskee paikkaa
(mikä tahansa kohde riittää) tai yhtä kohdetta, ja taso on "toimii", "paras" (optimi)
tai pisteraja; pisteraja kohteelle vain, jos sillä ei ole toimintarajaa.
Tilaukset ovat Firestoressa (kokoelma KOKOELMA). Vercel Cron kutsuu aamuisin
/api/halyta, joka laskee päivän tilanteen ja ilmoittaa ehdoista, jotka täyttyvät
tänään tai valitun ennusteen aikana. Samasta ehdosta ei ilmoiteta uudelleen ennen
kuin se on välillä lakannut täyttymästä.

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
avainten_tila = "ei vielä haettu"   # miksi avaimet saatiin tai jäivät saamatta (GET /api/halytys)


def avaimet(kanta=None, uudelleen: bool = False) -> tuple[str, str] | None:
    """(julkinen, yksityinen): ympäristömuuttujista tai Firestoresta (luodaan tarvittaessa).
    None, jos kumpaakaan ei ole käytettävissä. Tulos pidetään muistissa; epäonnistuminen
    10 min (uudelleen=True yrittää heti)."""
    global _avaimet, avainten_tila
    julkinen, yksityinen = os.environ.get("VAPID_PUBLIC_KEY", ""), os.environ.get("VAPID_PRIVATE_KEY", "")
    if julkinen and yksityinen:
        avainten_tila = "ympäristömuuttujista (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY)"
        return julkinen, yksityinen
    if _avaimet and (_avaimet[1] or (not uudelleen and time.monotonic() - _avaimet[0] < 600)):
        return _avaimet[1]
    tulos = None
    try:
        import firestore
        kanta = kanta or firestore.Firestore.ymparistosta(aikaraja=5)   # sivun lataus ei jää odottamaan
        if not kanta:
            avainten_tila = "FIREBASE_SERVICE_ACCOUNT puuttuu Vercelin ympäristömuuttujista"
        else:
            tallessa = kanta.lue(*ASETUKSET)
            if not tallessa:   # luodaan kerran; samanaikainen luonti: toisen tallentama pari voittaa
                julkinen, yksityinen = luo_avaimet()
                kanta.luo(*ASETUKSET, {"julkinen": julkinen, "yksityinen": yksityinen})
                tallessa = kanta.lue(*ASETUKSET)
            tulos = (tallessa["julkinen"], tallessa["yksityinen"])
            avainten_tila = "Firestoresta (asetukset/vapid)"
    except Exception as e:  # Firestore ei käytettävissä: hälytykset pois päältä
        tulos = None
        avainten_tila = f"Firestore-virhe: {type(e).__name__}: {str(e)[:300]}"
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

EHTOJA_ENINTAAN = 30
TASOT = ("toimii", "paras", "pisteet")


def kohteen_tasot(kohde) -> tuple[str, ...]:
    """Kohteelle valittavat ehdot: toimii (jos toimivalla alueella on raja), optimi (jos parhaalla
    alueella on raja) ja pisteraja, kun toimintarajaa ei ole (kohde toimii kaikilla vesillä)."""
    rajaton = tuple(kohde.toimii) == (None, None)
    return (() if rajaton else ("toimii",)) + (("paras",) if tuple(kohde.paras) != (None, None) else ()) \
        + (("pisteet",) if rajaton else ())


def valittavat(paikat) -> dict[str, dict[str, tuple[str, ...]]]:
    """Paikka -> {kohde -> sallitut ehdot}; "" = paikka kokonaisuutena (mikä tahansa kohde riittää).
    Paikat ilman kohteita (ei vesikaaviota) jäävät pois."""
    return {p.nimi: {"": TASOT, **{k.nimi: kohteen_tasot(k) for k in p.kohteet}} for p in paikat if p.kohteet}


def ehdon_avain(ehto: dict) -> str:
    return f"{ehto['paikka']}|{ehto['kohde']}|{ehto['taso']}|{ehto.get('raja', '')}"


def tarkista_tilaus(data, valinnat: dict[str, dict[str, tuple[str, ...]]]) -> tuple[dict | None, str]:
    """Selaimen lähettämä tilaus tallennettavaan muotoon: (tilaus, virhe). valinnat = valittavat(PAIKAT)."""
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
    paivia = data.get("paivia")
    if isinstance(paivia, bool) or not isinstance(paivia, int) or not 0 <= paivia <= 14:
        return None, "ennusteen pituuden pitää olla 0–14 päivää"
    ehdot_ = data.get("ehdot")
    if not isinstance(ehdot_, list) or not 1 <= len(ehdot_) <= EHTOJA_ENINTAAN:
        return None, f"valitse 1–{EHTOJA_ENINTAAN} ehtoa"
    ehdot, avaimet__ = [], set()
    for e in ehdot_:
        if not isinstance(e, dict):
            return None, "virheellinen ehto"
        paikka, kohde, taso, raja = e.get("paikka"), e.get("kohde") or "", e.get("taso"), e.get("raja")
        if paikka not in valinnat or kohde not in valinnat[paikka]:
            return None, "tuntematon paikka tai kohde"
        if taso not in valinnat[paikka][kohde]:
            return None, "ehto ei sovi kohteelle"
        ehto = {"paikka": paikka, "kohde": kohde, "taso": taso}
        if taso == "pisteet":
            if isinstance(raja, bool) or not isinstance(raja, int) or not 1 <= raja <= 100:
                return None, "pisterajan pitää olla 1–100"
            ehto["raja"] = raja
        if ehdon_avain(ehto) not in avaimet__:
            avaimet__.add(ehdon_avain(ehto))
            ehdot.append(ehto)
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth, "paivia": paivia, "ehdot": ehdot,
            "kieli": "en" if data.get("kieli") == "en" else "fi", "ilmoitettu": [],
            "luotu": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, ""


def _kohteen_pisteet(k) -> float:
    """Kohteen omat pisteet 0–100 (ilman laatukerrointa, jolla paikan pisteet painotetaan)."""
    return k.pisteet / k.kohde.laatu if k.kohde.laatu else k.pisteet


def tayttyy(ehto: dict, tulos, paivia: int) -> tuple[int, str] | None:
    """Ensimmäinen päivä 0…paivia, jona ehto täyttyy, ja kohteen nimi (paikan ehdolle paras
    täyttävä kohde); None, jos ei täyty."""
    for n in range(paivia + 1):
        kohteet = tulos.kohteet if n == 0 else tulos.ennusteen_kohteet.get(n)
        if not kohteet:
            continue
        if ehto["kohde"]:
            kohteet = [k for k in kohteet if k.kohde.nimi == ehto["kohde"]]
        if ehto["taso"] == "pisteet":
            if ehto["kohde"]:
                ok = [k for k in kohteet if round(_kohteen_pisteet(k)) >= ehto["raja"]]
            else:
                pisteet = tulos.pisteet if n == 0 else tulos.ennuste.get(n)
                ok = kohteet if pisteet is not None and round(pisteet) >= ehto["raja"] else []
        else:
            ok = [k for k in kohteet if k.tila == "paras" or (ehto["taso"] == "toimii" and k.tila == "toimii")]
        if ok:
            return n, max(ok, key=lambda k: k.pisteet).kohde.nimi
    return None


def uudet_halytykset(tilaus: dict, tulokset: dict) -> tuple[list[tuple[dict, int, str]], list[str]]:
    """(ilmoitettavat (ehto, päivä, kohde), täyttyvien ehtojen avaimet tallennettavaksi).
    tulokset = paikan nimi -> PaikkaTulos. Ilmoitetusta ehdosta uudelleen vasta, kun se on
    välillä lakannut täyttymästä."""
    ennestaan, uudet, tayttyvat = set(tilaus.get("ilmoitettu") or []), [], []
    for ehto in tilaus.get("ehdot") or []:
        osuma = tayttyy(ehto, tulokset[ehto["paikka"]], tilaus.get("paivia", 0)) \
            if ehto["paikka"] in tulokset else None
        if osuma:
            tayttyvat.append(ehdon_avain(ehto))
            if ehdon_avain(ehto) not in ennestaan:
                uudet.append((ehto, *osuma))
    return sorted(uudet, key=lambda u: u[1]), sorted(tayttyvat)


VIIKONPAIVAT = {"fi": ("ma", "ti", "ke", "to", "pe", "la", "su"), "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
SANAT = {"fi": {"toimii": "toimii", "paras": "parhaimmillaan", "tanaan": "tänään", "muuta": "muuta",
                "otsikko": "Hyvät melontaolot"},
         "en": {"toimii": "works", "paras": "at its best", "tanaan": "today", "muuta": "more",
                "otsikko": "Good paddling conditions"}}


def _paiva(n: int, tanaan: dt.date, kieli: str) -> str:
    if n == 0:
        return SANAT[kieli]["tanaan"]
    p = tanaan + dt.timedelta(days=n)
    return f"{VIIKONPAIVAT[kieli][p.weekday()]} {p.day}.{p.month}."


def _kuvaus(ehto: dict, kieli: str) -> str:
    """Ehto luettavana: 'Kipinä (Iijoki) – Pikku hontto: parhaimmillaan' / '… ≥ 60 p'."""
    nimi = ehto["paikka"] + (f" – {ehto['kohde']}" if ehto["kohde"] else "")
    return f"{nimi} ≥ {ehto['raja']} p" if ehto["taso"] == "pisteet" else f"{nimi}: {SANAT[kieli][ehto['taso']]}"


def viesti(uudet: list[tuple[dict, int, str]], tanaan: dt.date, kieli: str = "fi") -> dict:
    """Ilmoituksen otsikko, teksti ja avattava osoite."""
    rivit = []
    for ehto, n, kohde in uudet[:6]:
        lisa = f" ({kohde})" if not ehto["kohde"] and ehto["taso"] != "pisteet" else ""
        rivit.append(f"{_kuvaus(ehto, kieli)}{lisa}, {_paiva(n, tanaan, kieli)}")
    if len(uudet) > 6:
        rivit.append(f"+{len(uudet) - 6} {SANAT[kieli]['muuta']}")
    return {"otsikko": SANAT[kieli]["otsikko"], "teksti": "\n".join(rivit), "url": "/?kieli=en" if kieli == "en" else "/"}


def vahvistus(tilaus: dict) -> dict:
    """Ilmoitus heti tilauksen jälkeen: kertoo, että ilmoitukset toimivat, ja tilatut ehdot."""
    kieli, n = tilaus["kieli"], tilaus["paivia"]
    if kieli == "en":
        jakso = "today" if n == 0 else f"within {n} days"
        alku = f"Notifying each morning ({jakso}): "
    else:
        jakso = "tänään" if n == 0 else f"{n} päivän sisällä"
        alku = f"Ilmoitan aamuisin ({jakso}): "
    ehdot = "; ".join(_kuvaus(e, kieli) for e in tilaus["ehdot"][:4]) \
        + (f" +{len(tilaus['ehdot']) - 4}" if len(tilaus["ehdot"]) > 4 else "")
    return {"otsikko": "Alert subscribed" if kieli == "en" else "Hälytys tilattu", "teksti": alku + ehdot,
            "url": "/?kieli=en" if kieli == "en" else "/"}


def aja(kanta, tulokset, tanaan: dt.date, avainpari: tuple[str, str], lahetin=laheta) -> dict:
    """Käy tilaukset läpi: lähettää uudet hälytykset, päivittää tilan ja poistaa vanhentuneet."""
    paikoittain = {t.paikka.nimi: t for t in tulokset}
    tilaukset = kanta.listaa(KOKOELMA)
    lahetetty, jo_ilmoitettu, poistettu, virheet = 0, 0, 0, []
    for avain, tilaus in tilaukset.items():
        uudet, tayttyvat = uudet_halytykset(tilaus, paikoittain)
        if tayttyvat and not uudet:
            jo_ilmoitettu += 1   # ehto täyttyy, mutta siitä on jo ilmoitettu
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
        if tayttyvat != sorted(tilaus.get("ilmoitettu") or []):
            kanta.kirjoita(KOKOELMA, avain, {**tilaus, "ilmoitettu": tayttyvat})
    return {"tilauksia": len(tilaukset), "lahetetty": lahetetty, "jo_ilmoitettu": jo_ilmoitettu,
            "poistettu": poistettu, "virheet": virheet}


SERVICE_WORKER = """// Melontahälytysten service worker: näyttää push-ilmoituksen ja avaa sivun napautuksesta
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (virhe) {}
  const toiminnot = Array.isArray(d.toiminnot) ? d.toiminnot : [];
  e.waitUntil(self.registration.showNotification(d.otsikko || "Melontahälytys",
    {body: d.teksti || "", tag: d.url || "melonta", renotify: true,
     actions: toiminnot.map(t => ({action: t.action, title: t.title})),
     data: {url: d.url || "/", toiminnot}}));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const data = e.notification.data || {};
  // ilmoituksen nappi: rajapintakutsu ylläpitäjän evästeellä (esim. "Täydennä") ja/tai oma sivu
  // (esim. "Ylläpito"), sitten sivu auki
  const toiminto = (data.toiminnot || []).find(t => t.action === e.action);
  const kutsu = toiminto && toiminto.api
    ? fetch(toiminto.api, {method: "POST", credentials: "include"}).catch(() => null) : Promise.resolve();
  e.waitUntil(kutsu.then(() => clients.openWindow((toiminto && toiminto.url) || data.url || "/")));
});
"""
