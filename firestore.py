"""Pieni Firestore-asiakas REST-rajapinnan kautta (ilman firebase-adminia).

Kirjautuminen palvelutilin avaimella: avaimella allekirjoitettu JWT
vaihdetaan Googlen OAuth-palvelussa pääsytunnisteeseen. Allekirjoitukseen
käytetään google-authia; HTTP-kutsut tehdään urllibillä.

Asetukset ympäristömuuttujista:
    FIREBASE_SERVICE_ACCOUNT  palvelutilin avain: JSON sellaisenaan tai polku tiedostoon
    FIREBASE_PROJECT_ID       projekti (oletus: avaimen project_id)
    FIRESTORE_DATABASE        tietokanta (oletus: (default))

Palvelutili ohittaa Firestoren tietoturvasäännöt, joten säännöt voivat
estää kaiken selainkäytön. Palvelutilille riittää rooli "Cloud Datastore User".
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/datastore"
API = "https://firestore.googleapis.com/v1"


class FirestoreVirhe(Exception):
    pass


def koodaa(arvo) -> dict:
    """Python-arvo Firestoren Value-muotoon."""
    if arvo is None:
        return {"nullValue": None}
    if isinstance(arvo, bool):
        return {"booleanValue": arvo}
    if isinstance(arvo, int):
        return {"integerValue": str(arvo)}
    if isinstance(arvo, float):
        return {"doubleValue": arvo}
    if isinstance(arvo, str):
        return {"stringValue": arvo}
    if isinstance(arvo, dict):
        return {"mapValue": {"fields": {str(k): koodaa(v) for k, v in arvo.items()}}}
    if isinstance(arvo, (list, tuple)):
        return {"arrayValue": {"values": [koodaa(v) for v in arvo]}}
    raise TypeError(f"Firestore ei tue tyyppiä {type(arvo).__name__}")


def pura(arvo: dict):
    """Firestoren Value Python-arvoksi."""
    if "mapValue" in arvo:
        return {k: pura(v) for k, v in arvo["mapValue"].get("fields", {}).items()}
    if "arrayValue" in arvo:
        return [pura(v) for v in arvo["arrayValue"].get("values", [])]
    if "integerValue" in arvo:
        return int(arvo["integerValue"])
    if "doubleValue" in arvo:
        return float(arvo["doubleValue"])
    for avain in ("stringValue", "booleanValue", "timestampValue"):
        if avain in arvo:
            return arvo[avain]
    return None


class Firestore:
    def __init__(self, tunnus: dict, projekti: str | None = None, tietokanta: str = "(default)",
                 aikaraja: float = 20, avaa=urllib.request.urlopen):
        self.tunnus = tunnus
        self.projekti = projekti or tunnus["project_id"]
        self.tietokanta = tietokanta
        self.aikaraja = aikaraja
        self._avaa = avaa   # testeissä korvataan
        self._token: tuple[str, float] | None = None

    @classmethod
    def ymparistosta(cls, **kw) -> Firestore | None:
        arvo = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
        if not arvo:
            return None
        tunnus = json.loads(arvo if arvo.startswith("{") else Path(arvo).read_text(encoding="utf-8"))
        return cls(tunnus, os.environ.get("FIREBASE_PROJECT_ID") or None,
                   os.environ.get("FIRESTORE_DATABASE") or "(default)", **kw)

    @property
    def _dokumentit(self) -> str:
        return f"{API}/projects/{self.projekti}/databases/{self.tietokanta}/documents"

    def _hae_token(self) -> str:
        if self._token and time.time() < self._token[1] - 60:
            return self._token[0]
        from google.auth import crypt, jwt

        nyt = int(time.time())
        allekirjoittaja = crypt.RSASigner.from_service_account_info(self.tunnus)
        vaite = jwt.encode(allekirjoittaja, {
            "iss": self.tunnus["client_email"], "scope": SCOPE, "aud": TOKEN_URL,
            "iat": nyt, "exp": nyt + 3600,
        })
        runko = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": vaite.decode("ascii") if isinstance(vaite, bytes) else vaite,
        }).encode("ascii")
        vastaus = self._kutsu(urllib.request.Request(
            TOKEN_URL, data=runko, headers={"Content-Type": "application/x-www-form-urlencoded"}))
        self._token = (vastaus["access_token"], nyt + int(vastaus.get("expires_in", 3600)))
        return self._token[0]

    def _kutsu(self, pyynto: urllib.request.Request) -> dict:
        try:
            with self._avaa(pyynto, timeout=self.aikaraja) as v:
                return json.loads(v.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise FileNotFoundError(pyynto.full_url) from e
            raise FirestoreVirhe(f"{pyynto.get_method()} {pyynto.full_url}: HTTP {e.code} "
                                 f"{e.read()[:500].decode('utf-8', 'replace')}") from e

    def _api(self, metodi: str, polku: str, runko: dict | None = None) -> dict:
        data = None if runko is None else json.dumps(runko).encode("utf-8")
        return self._kutsu(urllib.request.Request(
            f"{self._dokumentit}/{polku}", data=data, method=metodi,
            headers={"Authorization": f"Bearer {self._hae_token()}", "Content-Type": "application/json"}))

    def kirjoita(self, kokoelma: str, tunniste: str, data: dict) -> None:
        """Luo tai korvaa koko dokumentin."""
        self._api("PATCH", f"{kokoelma}/{urllib.parse.quote(tunniste)}", {"fields": koodaa(data)["mapValue"]["fields"]})

    def lue(self, kokoelma: str, tunniste: str) -> dict | None:
        try:
            doc = self._api("GET", f"{kokoelma}/{urllib.parse.quote(tunniste)}")
        except FileNotFoundError:
            return None
        return pura({"mapValue": doc})

    def listaa(self, kokoelma: str) -> dict[str, dict]:
        """Kokoelman kaikki dokumentit: tunniste -> data."""
        tulos, sivu = {}, None
        while True:
            kysely = urllib.parse.urlencode({"pageSize": 300, **({"pageToken": sivu} if sivu else {})})
            try:
                vastaus = self._api("GET", f"{kokoelma}?{kysely}")
            except FileNotFoundError:
                return tulos
            for doc in vastaus.get("documents", []):
                tulos[doc["name"].rsplit("/", 1)[-1]] = pura({"mapValue": doc})
            sivu = vastaus.get("nextPageToken")
            if not sivu:
                return tulos
