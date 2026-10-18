"""osm.fi-sivujen ja SYKE-kaavioiden haku.

Melontapaikan sivun lopussa on otsikko "Vedenkorkeus"/"Virtaama" ja sen
alla SYKE:n kaaviokuvat (wwwi2.ymparisto.fi/i2/...). Kaavioiden osoitteet
poimitaan sivulta joka ajolla, joten jos sivulle vaihdetaan toinen
mittari, ohjelma huomaa sen.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path

KAYTTAJA = "osm-melontatilanne/1.0 (+https://www.osm.fi/)"
SYKE_POHJA = "https://wwwi2.ymparisto.fi/i2/"
_I2 = re.compile(r"""(?:src|href)=["'](https?://wwwi2\.ymparisto\.fi/i2/([^"'?#]+))["']""", re.I)
_LINKKI = re.compile(r"""href=["'](https://www\.osm\.fi/[^"'#?]+)["']""", re.I)


class Hakija:
    """Hakee verkosta tai välimuistikansiosta (offline-tila)."""

    def __init__(self, offline: Path | None = None, tallenna: Path | None = None, aikaraja: float = 30):
        self.offline = offline
        self.tallenna = tallenna
        self.aikaraja = aikaraja

    @staticmethod
    def _tiedostonimi(url: str) -> str:
        nimi = re.sub(r"^https?://", "", url).rstrip("/")
        return re.sub(r"[^A-Za-z0-9._-]+", "_", nimi)

    def hae(self, url: str) -> bytes:
        if self.offline:
            polku = self.offline / self._tiedostonimi(url)
            if not polku.exists():
                raise FileNotFoundError(f"Ei välimuistissa: {url} ({polku.name})")
            return polku.read_bytes()
        pyynto = urllib.request.Request(url, headers={"User-Agent": KAYTTAJA})
        with urllib.request.urlopen(pyynto, timeout=self.aikaraja) as vastaus:
            data = vastaus.read()
        if self.tallenna:
            self.tallenna.mkdir(parents=True, exist_ok=True)
            (self.tallenna / self._tiedostonimi(url)).write_bytes(data)
        return data


def kaavio_avain(url: str) -> str | None:
    """'https://wwwi2.ymparisto.fi/i2/67/q6702110y/wlyhyt.png' -> '67/q6702110y/wlyhyt.png'"""
    m = re.search(r"wwwi2\.ymparisto\.fi/i2/([^?#]+)", url)
    return m.group(1) if m else None


def kaavio_url(avain: str) -> str:
    return SYKE_POHJA + avain


def sivun_kaaviot(html: str) -> list[str]:
    """Sivun SYKE-kaavioiden avaimet esiintymisjärjestyksessä (kuvat ja iframet)."""
    avaimet: list[str] = []
    for _, avain in _I2.findall(html):
        if avain not in avaimet:
            avaimet.append(avain)
    return avaimet


def melontapaikkojen_linkit(html: str) -> list[str]:
    """Melontapaikat-hakemistosivun sisältöalueen linkit (uusien paikkojen havaitsemiseen)."""
    m = re.search(r"<main.*?</main>", html, flags=re.S)
    alue = m.group(0) if m else html
    linkit = []
    for url in _LINKKI.findall(alue):
        url = url.rstrip("/") + "/"
        if "/author/" in url or url in linkit:
            continue
        linkit.append(url)
    return linkit


def normalisoi(url: str) -> str:
    """Sivujen osoitteiden vertailuun: viimeinen polun osa (slug)."""
    return url.rstrip("/").rsplit("/", 1)[-1].lower()


def hae_turvallisesti(hakija: Hakija, url: str) -> tuple[bytes | None, str | None]:
    try:
        return hakija.hae(url), None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        syy = getattr(e, "code", None) or getattr(e, "reason", None) or e
        return None, f"{url}: {syy}"
