"""Ylläpitäjän korttikohtaiset lisäykset: oma korttikuva, linkkiluukku ja (sovelluksen paikoille) johdanto.

Kortin avain on sovelluksen paikalle paikkasivun tunniste (/paikka/<avain>) ja käyttäjän ehdottamalle
kohteelle ehdotuksen tunniste (/ehdotus/<avain>). Tiedot ovat Firestoressa: KOKOELMA (linkit, tekstit,
kuvan versio) ja KUVAT (JPEG base64-muodossa, erillään, jottei korttilista kasva).
"""

from __future__ import annotations

import re

import paikkasivut

KOKOELMA = "kortit"
KUVAT = "kortit_kuvat"
KUVA_ENINTAAN = 700_000      # tavua; selain pienentää kuvan ennen lähetystä (Firestoren dokumentti ≤ 1 MiB)
LINKKEJA_ENINTAAN = 20
TEKSTI_ENINTAAN = 5000


def avain(paikka) -> str:
    if paikka.url.startswith("/ehdotus/"):
        return paikka.url.removeprefix("/ehdotus/")
    return paikkasivut.tunniste(paikka.nimi)


def kelvollinen_avain(teksti: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", teksti or ""))


def on_jpeg(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff" and len(data) <= KUVA_ENINTAAN


def tulkitse_linkit(teksti: str) -> tuple[list[dict] | None, str]:
    """Rivit 'Otsikko | https://…' tai pelkkä osoite -> [{"nimi", "url"}] tai (None, virhe)."""
    linkit = []
    for rivi in (teksti or "").splitlines():
        rivi = rivi.strip()
        if not rivi:
            continue
        nimi, _, url = rivi.rpartition("|") if "|" in rivi else ("", "", rivi)
        nimi, url = nimi.strip(), url.strip()
        if not re.fullmatch(r"https?://\S{3,490}", url):
            return None, f"Linkin pitää alkaa http:// tai https:// ({rivi[:80]})"
        linkit.append({"nimi": nimi[:150] or url, "url": url})
    if len(linkit) > LINKKEJA_ENINTAAN:
        return None, f"Enintään {LINKKEJA_ENINTAAN} linkkiä."
    return linkit, ""


def linkit_tekstiksi(linkit: list[dict]) -> str:
    return "\n".join(l["url"] if l.get("nimi") in (None, "", l["url"]) else f'{l["nimi"]} | {l["url"]}'
                     for l in linkit or [])
