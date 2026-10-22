import io
import json
import urllib.error
import urllib.parse

import pytest

import firestore

rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from google.auth import jwt  # noqa: E402


@pytest.fixture(scope="module")
def avain():
    yksityinen = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = yksityinen.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()).decode()
    julkinen = yksityinen.public_key().public_bytes(serialization.Encoding.PEM,
                                                    serialization.PublicFormat.SubjectPublicKeyInfo)
    tunnus = {"type": "service_account", "project_id": "melonta-testi", "private_key_id": "abc",
              "private_key": pem, "client_email": "arkisto@melonta-testi.iam.gserviceaccount.com"}
    return tunnus, julkinen


class Palvelin:
    """Korvaa urlopenin: Googlen token-palvelu ja Firestore muistissa."""

    def __init__(self):
        self.pyynnot = []
        self.dokumentit = {}

    def __call__(self, pyynto, timeout):
        self.pyynnot.append(pyynto)
        url = pyynto.full_url
        if url == firestore.TOKEN_URL:
            return self._vastaus({"access_token": "tunniste-1", "expires_in": 3600})
        assert pyynto.headers["Authorization"] == "Bearer tunniste-1"
        polku = urllib.parse.urlsplit(url).path.split("/documents/", 1)[1]
        if pyynto.get_method() == "DELETE":
            self.dokumentit.pop(polku, None)
            return self._vastaus({})
        if pyynto.get_method() == "PATCH" and "currentDocument.exists=false" in url and polku in self.dokumentit:
            raise urllib.error.HTTPError(url, 409, "Conflict", {}, io.BytesIO(b'{"status": "ALREADY_EXISTS"}'))
        if pyynto.get_method() == "PATCH":
            self.dokumentit[polku] = json.loads(pyynto.data)["fields"]
            return self._vastaus({"name": polku, "fields": self.dokumentit[polku]})
        if polku in self.dokumentit:
            return self._vastaus({"name": f"projects/p/databases/(default)/documents/{polku}",
                                  "fields": self.dokumentit[polku]})
        if "/" not in polku:   # kokoelman listaus, kaksi sivua
            kysely = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            omat = sorted(k for k in self.dokumentit if k.startswith(polku + "/"))
            alku = int(kysely.get("pageToken", ["0"])[0])
            sivu = {"documents": [{"name": f"x/documents/{k}", "fields": self.dokumentit[k]}
                                  for k in omat[alku:alku + 1]]}
            if alku + 1 < len(omat):
                sivu["nextPageToken"] = str(alku + 1)
            return self._vastaus(sivu)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"{}"))

    @staticmethod
    def _vastaus(data):
        return io.BytesIO(json.dumps(data).encode())


def test_koodaus_edestakaisin():
    data = {"a": 1, "b": 2.5, "c": "x", "d": None, "e": True, "f": [1.0, "y"], "61/q6101750y": {"2026-10-18": 3.0},
            "tyhja": {}}
    assert firestore.pura(firestore.koodaa(data)) == data
    assert firestore.koodaa(3) == {"integerValue": "3"}
    assert firestore.koodaa(3.0) == {"doubleValue": 3.0}
    with pytest.raises(TypeError):
        firestore.koodaa(object())


def test_kirjoitus_luku_ja_listaus(avain):
    tunnus, julkinen = avain
    palvelin = Palvelin()
    kanta = firestore.Firestore(tunnus, avaa=palvelin)
    kanta.kirjoita("ennusteet", "2026-10-18", {"asemat": {"61/q6101750y": {"qhav": {"2026-10-17": 398.97}}}})
    kanta.kirjoita("ennusteet", "2026-10-19", {"n": 2})
    assert kanta.lue("ennusteet", "2026-10-18") == {"asemat": {"61/q6101750y": {"qhav": {"2026-10-17": 398.97}}}}
    assert kanta.lue("ennusteet", "2026-10-20") is None
    assert set(kanta.listaa("ennusteet")) == {"2026-10-18", "2026-10-19"}
    assert kanta.listaa("muut") == {}

    # pääsytunniste haetaan kerran ja JWT on allekirjoitettu palvelutilin avaimella
    tokenit = [p for p in palvelin.pyynnot if p.full_url == firestore.TOKEN_URL]
    assert len(tokenit) == 1
    vaite = urllib.parse.parse_qs(tokenit[0].data.decode())["assertion"][0]
    vaitteet = jwt.decode(vaite, certs=julkinen, audience=firestore.TOKEN_URL)
    assert vaitteet["iss"] == tunnus["client_email"] and vaitteet["scope"] == firestore.SCOPE
    patch = next(p for p in palvelin.pyynnot if p.get_method() == "PATCH")
    assert patch.full_url == ("https://firestore.googleapis.com/v1/projects/melonta-testi/databases/(default)"
                              "/documents/ennusteet/2026-10-18")


def test_luonti_ja_poisto(avain):
    tunnus, _ = avain
    kanta = firestore.Firestore(tunnus, avaa=Palvelin())
    assert kanta.luo("asetukset", "vapid", {"julkinen": "a"}) is True
    assert kanta.luo("asetukset", "vapid", {"julkinen": "b"}) is False   # ei korvaa olemassa olevaa
    assert kanta.lue("asetukset", "vapid") == {"julkinen": "a"}
    kanta.poista("asetukset", "vapid")
    kanta.poista("asetukset", "vapid")   # puuttuvan poisto ei ole virhe
    assert kanta.lue("asetukset", "vapid") is None


def test_ymparistosta(avain, monkeypatch, tmp_path):
    tunnus, _ = avain
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT", raising=False)
    assert firestore.Firestore.ymparistosta() is None
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", json.dumps(tunnus))
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "toinen")
    assert firestore.Firestore.ymparistosta().projekti == "toinen"
    polku = tmp_path / "avain.json"
    polku.write_text(json.dumps(tunnus))
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", str(polku))
    monkeypatch.delenv("FIREBASE_PROJECT_ID")
    assert firestore.Firestore.ymparistosta().projekti == "melonta-testi"


def test_http_virhe(avain):
    tunnus, _ = avain

    def avaa(pyynto, timeout):
        if pyynto.full_url == firestore.TOKEN_URL:
            return io.BytesIO(b'{"access_token": "t"}')
        raise urllib.error.HTTPError(pyynto.full_url, 403, "Forbidden", {}, io.BytesIO(b"PERMISSION_DENIED"))

    with pytest.raises(firestore.FirestoreVirhe, match="403 PERMISSION_DENIED"):
        firestore.Firestore(tunnus, avaa=avaa).kirjoita("ennusteet", "x", {})
