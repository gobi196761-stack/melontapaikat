"""Käyttäjien ehdotukset: uusi kohde tai täydennys olemassa olevaan paikkaan (/ehdota).

Lomakkeella annetaan kohteen nimi, mittari (SYKE-aseman numero tai kaavion osoite, tai
täydennyksessä paikan oma mittari), pelipaikat tai laskuosuudet toimii- ja optimirajoineen,
vesitieto-, video- ja muut linkit sekä vapaa teksti. Ehdotus tallentuu Firestoreen
(KOKOELMA, dokumentin tunnus = salainen satunnainen tunniste, joka on myös esikatselusivun
osoite /ehdotus/<tunniste>). Esikatselu näyttää heti päivän tilanteen ehdotetuilla rajoilla.

Ylläpitäjä (salasana ympäristömuuttujassa YLLAPITO_SALASANA) saa push-ilmoituksen uudesta
ehdotuksesta (tilaukset kokoelmassa YLLAPITO) ja hyväksyy tai hylkää sen esikatselusivulla;
ehdottaja voi tilata push-ilmoituksen käsittelystä. Hyväksytyt ehdotukset näkyvät sivustolla:
uudet kohteet etusivun ehdotusluukussa ja täydennykset paikkasivun "Käyttäjien lisäykset"
-osiossa. Sähköpostia ei kerätä.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import replace
from urllib.parse import urlparse

from paikat import Kohde, Mittari, Paikka

KOKOELMA = "ehdotukset"
YLLAPITO = "yllapito_tilaukset"
TILAT = ("odottaa", "hyvaksytty", "hylatty")
KOHTEITA_ENINTAAN = 6           # lomakkeen "+ Lisää kohde" enintään 6 kertaa
LINKKEJA_ENINTAAN = 10
TEKSTI_ENINTAAN = 3000
NIMI_ENINTAAN = 100
ODOTTAVIA_ENINTAAN = 100          # roskapostin varalta: uusia ei oteta, jos jono on täynnä
IP_RAJA = (5, 3600)               # enintään 5 ehdotusta tunnissa samasta osoitteesta (per palvelininstanssi)
VIDEOPALVELUT = ("youtube.com", "youtu.be", "vimeo.com", "facebook.com", "instagram.com", "tiktok.com")
VESIPALVELUT = ("ymparisto.fi", "vesi.fi", "syke.fi", "smhi.se", "fmi.fi", "ilmatieteenlaitos.fi")

_lahetykset: dict[str, list[float]] = {}


def uusi_tunniste() -> str:
    return secrets.token_urlsafe(16)


def kelvollinen_tunniste(tunniste: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{16,40}", tunniste or ""))


# ---------------------------------------------------------------------------
# Lomakkeen tulkinta
# ---------------------------------------------------------------------------

def luku(teksti: str) -> float | None:
    """'12,5' -> 12.5; tyhjä -> None; muu -> ValueError."""
    teksti = (teksti or "").strip().replace(",", ".").replace("−", "-")
    if not teksti:
        return None
    arvo = float(teksti)
    if arvo != arvo or abs(arvo) > 1e6:
        raise ValueError(teksti)
    return arvo


def mittari_tekstista(teksti: str, suure: str) -> str | None:
    """SYKE-aseman numero tai kaavion osoite -> kaavion avain '<alue>/<asema>/<tiedosto>'.
    '7300350' + virtaama -> '73/q7300350y/qinlyhyt.png'; 'https://wwwi2.ymparisto.fi/i2/73/q7300350y/...'
    -> sama asema; 'w6702110y' -> vedenkorkeus."""
    teksti = (teksti or "").strip()
    if not teksti:
        return None
    m = re.search(r"(\d{2})/([qw])(\d{7})y(?:/([a-z0-9]+\.png))?", teksti)
    if m:
        alue, laji, nro, tiedosto = m.groups()
    else:
        m = re.search(r"\b([qw])?(\d{7})y?\b", teksti)
        if not m:
            return None
        laji, nro = m.groups()
        alue, tiedosto = nro[:2], None
        laji = laji or ("w" if suure == "vedenkorkeus" else "q")
    if not tiedosto or not tiedosto.startswith(("q", "w")):
        tiedosto = "qinlyhyt.png" if laji == "q" else "wlyhyt.png"
    return f"{alue}/{laji}{nro}y/{tiedosto}"


def sijainti_tekstista(teksti: str) -> tuple[float, float] | None:
    """'65.01, 25.47', Google Mapsin '@65.01,25.47,' tai '?q=65.01,25.47' -> (leveys, pituus)."""
    m = re.search(r"(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)", teksti or "")
    if not m:
        return None
    lev, pit = float(m.group(1)), float(m.group(2))
    return (lev, pit) if -90 <= lev <= 90 and -180 <= pit <= 180 else None


def linkin_laji(url: str) -> str:
    isanta = urlparse(url).hostname or ""
    if any(isanta == p or isanta.endswith("." + p) for p in VIDEOPALVELUT):
        return "video"
    if any(isanta == p or isanta.endswith("." + p) for p in VESIPALVELUT):
        return "vesi"
    return "muu"


def _kentta(kentat: dict[str, list[str]], nimi: str, enintaan: int = NIMI_ENINTAAN) -> str:
    return (kentat.get(nimi) or [""])[0].strip()[:enintaan]


def tulkitse(kentat: dict[str, list[str]], paikat: tuple[Paikka, ...], kieli: str = "fi") \
        -> tuple[dict | None, str]:
    """Lomakkeen kentät -> (ehdotus, '') tai (None, virheilmoitus valitulla kielellä)."""
    t = TEKSTIT["en" if kieli == "en" else "fi"]
    laji = _kentta(kentat, "laji")
    if laji not in ("uusi", "taydenna"):
        return None, t["virhe_laji"]
    ehdotus: dict = {"laji": laji, "kieli": "en" if kieli == "en" else "fi", "tila": "odottaa",
                     "luotu": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    if laji == "taydenna":
        paikka = next((p for p in paikat if p.nimi == _kentta(kentat, "paikka")), None)
        if paikka is None:
            return None, t["virhe_paikka"]
        ehdotus["paikka"] = paikka.nimi
        avain = _kentta(kentat, "mittari_avain") or next(iter(paikka.mittarit), "")
        if paikka.mittarit and avain not in paikka.mittarit:
            return None, t["virhe_mittari"]
        ehdotus["mittari_avain"] = avain
        ehdotus["nimi"] = paikka.nimi
    else:
        nimi = _kentta(kentat, "nimi")
        if not nimi and not any((kentat.get(k) or [""])[0].strip() for k in ("linkit", "yksityiset_linkit")):
            return None, t["virhe_nimi"]   # pelkkä linkki riittää: täydennys etsii nimen
        ehdotus["nimi"] = nimi
        ehdotus["tyyppi"] = "peli" if _kentta(kentat, "tyyppi") == "peli" else "retki"
        suure = "vedenkorkeus" if _kentta(kentat, "suure") == "vedenkorkeus" else "virtaama"
        mittari_teksti = _kentta(kentat, "mittari", 300)
        kaavio = mittari_tekstista(mittari_teksti, suure)
        if mittari_teksti and not kaavio:
            return None, t["virhe_asema"]
        ehdotus["mittari"] = kaavio or ""
        sijainti = sijainti_tekstista(_kentta(kentat, "sijainti", 300))
        ehdotus["sijainti"] = list(sijainti) if sijainti else None
    kohteet = []
    # uutena kohteena ehdotetaan yksi paikka kerrallaan; sen ensimmäisen kohteen nimi on oletuksena
    # paikan nimi, ja lisää pelipaikkoja tai laskuosuuksia tulee "+ Lisää kohde" -napilla
    for i in range(1, KOHTEITA_ENINTAAN + 1):
        nimi = _kentta(kentat, f"k{i}_nimi")
        arvot = [_kentta(kentat, f"k{i}_{x}", 20) for x in ("toimii_ala", "toimii_yla", "paras_ala", "paras_yla")]
        huom = _kentta(kentat, f"k{i}_huom", 300)
        if not nimi and not any(arvot) and not huom:
            continue
        nimi = nimi or (ehdotus["nimi"] if laji == "uusi" and i == 1 else "")
        try:
            ta, ty, pa, py = (luku(a) for a in arvot)
        except ValueError:
            return None, t["virhe_luku"].format(n=i)
        if not nimi:
            return None, t["virhe_kohteen_nimi"].format(n=i)
        if ta is None and ty is None:
            return None, t["virhe_rajat"].format(n=i)
        if pa is None and py is None:
            pa, py = ta, ty
        if any(a is not None and b is not None and a > b for a, b in ((ta, ty), (pa, py))):
            return None, t["virhe_jarjestys"].format(n=i)
        kohteet.append({"nimi": nimi, "toimii": [ta, ty], "paras": [pa, py], "huom": huom})
    def linkkirivit(kentta: str) -> tuple[list[str] | None, str]:
        urlit = []
        for rivi in (kentat.get(kentta) or [""])[0].splitlines():
            url = rivi.strip()
            if not url:
                continue
            if not re.fullmatch(r"https?://\S{3,490}", url):
                return None, t["virhe_linkki"].format(url=url[:80])
            urlit.append(url)
        if len(urlit) > LINKKEJA_ENINTAAN:
            return None, t["virhe_linkkeja"].format(n=LINKKEJA_ENINTAAN)
        return urlit, ""
    julkiset, virhe = linkkirivit("linkit")
    if julkiset is None:
        return None, virhe
    linkit = [{"url": url, "laji": linkin_laji(url)} for url in julkiset]
    # linkit vain sivun rakentamiseen (täydennyksen lähteiksi): ei näytetä eikä linkitetä julkisesti
    yksityiset, virhe = linkkirivit("yksityiset_linkit")
    if yksityiset is None:
        return None, virhe
    teksti = (kentat.get("teksti") or [""])[0].strip()
    if len(teksti) > TEKSTI_ENINTAAN:
        return None, t["virhe_teksti"].format(n=TEKSTI_ENINTAAN)
    if not kohteet and not linkit and not yksityiset and not teksti:
        return None, t["virhe_tyhja"]
    ehdotus.update(kohteet=kohteet, linkit=linkit, yksityiset_linkit=yksityiset, teksti=teksti,
                   ehdottaja=_kentta(kentat, "ehdottaja"))
    return ehdotus, ""


def roskaa(kentat: dict[str, list[str]], ip: str, nyt: float | None = None) -> bool:
    """Piilokenttä täytetty (botti) tai liikaa ehdotuksia samasta osoitteesta."""
    if _kentta(kentat, "verkkosivu"):
        return True
    nyt = nyt or time.time()
    maara, ikkuna = IP_RAJA
    ajat = [a for a in _lahetykset.get(ip, []) if a > nyt - ikkuna]
    if len(ajat) >= maara:
        return True
    _lahetykset[ip] = ajat + [nyt]
    return False


# ---------------------------------------------------------------------------
# Ehdotus paikaksi (esikatselu ja julkaisu)
# ---------------------------------------------------------------------------

def _kohde(k: dict, avain: str) -> Kohde:
    return Kohde(k["nimi"], tuple(k["toimii"]), tuple(k["paras"]), 1.0, avain, huom=k.get("huom", ""),
                 lahde="arvio" if k.get("arvio") else "ehdotus")


def valmis_taydennys(ehdotus: dict) -> dict:
    """Clauden valmis täydennys (TAYDENNYS-kentät) tai tyhjä."""
    t = ehdotus.get("taydennys") or {}
    return t if t.get("tila") == "valmis" else {}


def nimi(ehdotus: dict) -> str:
    """Ehdotuksen nimi: ehdottajan antama, täydennyksen löytämä tai ensimmäisen linkin palvelin."""
    if ehdotus.get("nimi"):
        return ehdotus["nimi"]
    if valmis_taydennys(ehdotus).get("nimi"):
        return valmis_taydennys(ehdotus)["nimi"]
    linkit = ehdotus.get("linkit") or []
    return urlparse(linkit[0]["url"]).hostname or "?" if linkit else "?"


def kaikki_kohteet(ehdotus: dict) -> list[dict]:
    """Ehdottajan kohteet ja täydennyksen lisäämät (merkitty "arvio": True); ehdottajan kohde voittaa."""
    omat = [dict(k) for k in ehdotus.get("kohteet", [])]
    nimet = {k["nimi"] for k in omat}
    return omat + [{**k, "arvio": True} for k in valmis_taydennys(ehdotus).get("kohteet", [])
                   if k.get("nimi") not in nimet]


def paikaksi(ehdotus: dict, paikat: tuple[Paikka, ...]) -> tuple[Paikka | None, set[str]]:
    """Ehdotus Paikka-olioksi: (paikka, ehdotettujen kohteiden nimet). Täydennyksessä olemassa
    olevan paikan kohteet, joista samanniminen ehdotus korvaa vanhan (rajakorjaus). Clauden
    täydennyksen mittari, sijainti ja kohteet otetaan mukaan, kun ehdottaja ei ole antanut niitä."""
    kohteet_ = kaikki_kohteet(ehdotus)
    uudet = {k["nimi"] for k in kohteet_}
    taydennys = valmis_taydennys(ehdotus)
    if ehdotus.get("laji") == "taydenna":
        paikka = next((p for p in paikat if p.nimi == ehdotus.get("paikka")), None)
        if paikka is None:
            return None, uudet
        avain = ehdotus.get("mittari_avain") or next(iter(paikka.mittarit), "paa")
        ehdotetut = [_kohde(k, avain) for k in kohteet_]
        vanhat = [k for k in paikka.kohteet if k.nimi not in uudet]
        return replace(paikka, kohteet=tuple(vanhat + ehdotetut)), uudet
    kaavio = ehdotus.get("mittari") or taydennys.get("mittari")
    mittarit = {"paa": Mittari(kaavio, lisakaavio=True)} if kaavio else {}
    kohteet = tuple(_kohde(k, "paa") for k in kohteet_) if mittarit else ()
    linkit = ehdotus.get("linkit") or []
    return Paikka(nimi(ehdotus), linkit[0]["url"] if linkit else "", ehdotus.get("tyyppi", "retki"),
                  None, (ehdotus.get("teksti") or taydennys.get("teksti") or "")[:300], mittarit, kohteet), uudet


# ---------------------------------------------------------------------------
# Clauden täydennys (GitHub Actions, .github/workflows/taydenna.yml; ohje tyokalut/TAYDENNYS.md)
# ---------------------------------------------------------------------------

GITHUB_REPO = "gobi196761-stack/melontapaikat"
TYONKULKU = "taydenna.yml"


def tarkista_taydennys(data, yksityiset: list[str] | tuple = ()) -> tuple[dict | None, str]:
    """Clauden kirjoittama täydennys tallennettavaan muotoon: (täydennys, virhe). Ehdottajan vain
    rakentamiseen antamat linkit (yksityiset) eivät saa näkyä lähteissä eikä tekstissä."""
    if not isinstance(data, dict):
        return None, "täydennyksen pitää olla JSON-olio"
    tulos: dict = {}
    for kentta, enintaan in (("nimi", NIMI_ENINTAAN), ("teksti", 6000), ("lahto", 600), ("loppu", 600),
                             ("mittari_perustelu", 1000), ("huomiot", 2000)):
        arvo = data.get(kentta) or ""
        if not isinstance(arvo, str):
            return None, f"{kentta}: pitää olla teksti"
        if arvo.strip():
            tulos[kentta] = arvo.strip()[:enintaan]
    if data.get("mittari"):
        kaavio = mittari_tekstista(str(data["mittari"]), str(data.get("suure") or "virtaama"))
        if not kaavio:
            return None, f"mittari: tuntematon asema {data['mittari']!r}"
        tulos["mittari"] = kaavio
    for kentta in ("sijainti", "lahto_sijainti", "loppu_sijainti"):
        arvo = data.get(kentta)
        if arvo:
            try:
                lev, pit = float(arvo[0]), float(arvo[1])
            except (TypeError, ValueError, IndexError):
                return None, f"{kentta}: pitää olla [leveys, pituus]"
            if not (-90 <= lev <= 90 and -180 <= pit <= 180):
                return None, f"{kentta}: ei koordinaatti"
            tulos[kentta] = [lev, pit]
    kohteet = []
    for i, k in enumerate(data.get("kohteet") or [], 1):
        if not isinstance(k, dict) or not str(k.get("nimi") or "").strip():
            return None, f"kohde {i}: nimi puuttuu"
        try:
            toimii = [luku(str(x)) if x is not None else None for x in (k.get("toimii") or [None, None])[:2]]
            paras = [luku(str(x)) if x is not None else None for x in (k.get("paras") or toimii)[:2]]
        except ValueError:
            return None, f"kohde {i}: rajat eivät ole lukuja"
        if toimii == [None, None]:
            return None, f"kohde {i}: toimii-raja puuttuu"
        kohteet.append({"nimi": str(k["nimi"]).strip()[:NIMI_ENINTAAN], "toimii": toimii,
                        "paras": paras if paras != [None, None] else toimii, "huom": str(k.get("huom") or "")[:300]})
    if len(kohteet) > KOHTEITA_ENINTAAN:
        return None, f"enintään {KOHTEITA_ENINTAAN} kohdetta"
    tulos["kohteet"] = kohteet
    lahteet = []
    for l in data.get("lahteet") or []:
        if isinstance(l, dict) and str(l.get("nimi") or "").strip():
            url = str(l.get("url") or "").strip()
            lahteet.append({"nimi": str(l["nimi"]).strip()[:200],
                            "url": url if re.fullmatch(r"https?://\S{3,490}", url) else ""})
    tulos["lahteet"] = lahteet[:15]
    for url in yksityiset:   # yksityinen linkki ei saa päätyä julkiseksi
        if any(url in (tulos.get(k) or "") for k in ("teksti", "lahto", "loppu", "mittari_perustelu", "huomiot")) \
                or any(url == l["url"] for l in lahteet):
            return None, f"yksityistä linkkiä ei saa julkaista: {url}"
    if not tulos.get("teksti") and not kohteet:
        return None, "täydennyksessä pitää olla vähintään teksti tai kohteita"
    return tulos, ""


def kaynnista_taydennys(tunniste: str, token: str | None, avaa=None) -> tuple[bool, str]:
    """Käynnistää GitHub Actions -ajon (workflow_dispatch), joka täydentää ehdotuksen Claude Codella."""
    import json
    import urllib.error
    import urllib.request
    if not token:
        return False, "GITHUB_TAYDENNYS_TOKEN puuttuu Vercelin ympäristömuuttujista"
    if not kelvollinen_tunniste(tunniste):
        return False, "virheellinen tunniste"
    pyynto = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{TYONKULKU}/dispatches",
        data=json.dumps({"ref": "main", "inputs": {"tunniste": tunniste}}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "melontapaikat"})
    try:
        with (avaa or urllib.request.urlopen)(pyynto, timeout=20) as v:
            return 200 <= v.status < 300, f"GitHub {v.status}"
    except urllib.error.HTTPError as e:
        return False, f"GitHub {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
    except OSError as e:
        return False, f"GitHub ei vastaa: {e}"


# ---------------------------------------------------------------------------
# Ylläpitäjän kirjautuminen (salasana ympäristömuuttujassa)
# ---------------------------------------------------------------------------

EVASTE = "melonta_yllapito"


def kirjautumisavain(salasana: str) -> str:
    return hmac.new(salasana.encode(), b"melontapaikat-yllapito", hashlib.sha256).hexdigest()


def on_yllapitaja(evasteet: str, salasana: str | None) -> bool:
    if not salasana:
        return False
    m = re.search(rf"(?:^|;\s*){EVASTE}=([0-9a-f]{{64}})", evasteet or "")
    return bool(m) and hmac.compare_digest(m.group(1), kirjautumisavain(salasana))


# ---------------------------------------------------------------------------
# Tekstit
# ---------------------------------------------------------------------------

TEKSTIT = {
    "fi": {
        "luukku": "➕ Ehdota uutta kohdetta tai täydennä paikkaa",
        "luukku_teksti": "Tiedätkö paikan, jota sovelluksessa ei ole, tai pelipaikan rajat paremmin? Lähetä "
                         "ehdotus: linkit, oma teksti ja kohteiden toiminta-alueet ja optimit. Näet heti "
                         "esikatselun päivän tilanteesta, ja ehdotus julkaistaan, kun ylläpitäjä on hyväksynyt sen.",
        "uusi": "Uusi kohde", "taydenna": "Täydennä paikkaa",
        "kayttajien_kohteet": "Käyttäjien ehdottamat kohteet",
        "lomake_otsikko": "Ehdota uutta kohdetta tai täydennä paikkaa",
        "lomake_ohje": "Ehdotus tarkistetaan ennen julkaisua. Lähettämisen jälkeen näet esikatselun, jossa on "
                       "päivän tilanne ehdottamillasi rajoilla. Sähköpostia ei kysytä: voit tilata "
                       "esikatselusivulla ilmoituksen, kun ehdotus on käsitelty.",
        "laji": "Ehdotus", "paikka": "Paikka", "nimi": "Kohteen nimi (esim. joki ja paikka)",
        "tyyppi": "Tyyppi", "peli": "pelipaikka", "retki": "retki- tai laskupätkä",
        "mittari": "Mittari: SYKE-aseman numero tai linkki kaavioon (vapaaehtoinen)",
        "mittari_ohje": "Esim. 7300350 tai https://wwwi2.ymparisto.fi/i2/73/q7300350y/wqfi.html",
        "suure": "Mittarin suure", "virtaama": "virtaama (m³/s)", "vedenkorkeus": "vedenkorkeus (m)",
        "paikan_mittari": "Mittari", "sijainti": "Sijainti (koordinaatit tai karttalinkki, vapaaehtoinen)",
        "kohteet": "Pelipaikat tai laskuosuudet ja niiden rajat",
        "rajat_uusi": "Paikan toiminta-alue ja optimi",
        "rajat_uusi_ohje": "Yksi paikka kerrallaan: anna paikan rajat mittarin yksikössä. Toimii = alue, jolla "
                           "paikka toimii; optimi = paras alue (tyhjä = sama kuin toimii). Jätä toinen pää "
                           "tyhjäksi, jos rajaa ei ole, ja paina + Lisää kohde. Paikan muut pelipaikat tai "
                           "laskuosuudet lisätään samalla tavalla.",
        "lisaa_kohde": "+ Lisää kohde", "poista_kohde": "Poista kohde",
        "kohteita_enintaan": "Enintään {n} kohdetta.", "paikan_nimi": "(paikan nimi)",
        "kohteen_nimi_uusi": "Kohteen tarkempi nimi (vapaaehtoinen, oletus = paikan nimi)",
        "kohteet_ohje": "Rajat mittarin yksikössä. Toimii = alue, jolla kohde toimii; optimi = paras alue "
                        "(tyhjä = sama kuin toimii). Jätä toinen pää tyhjäksi, jos rajaa ei ole (esim. vain "
                        "alaraja), ja paina + Lisää kohde; seuraava kohde samoin. Olemassa olevan kohteen nimellä "
                        "korjaat sen rajoja.",
        "kohde": "Kohde", "kohteen_nimi": "Nimi", "toimii": "Toimii", "optimi": "Optimi", "huom": "Huomio",
        "ala": "alaraja", "yla": "yläraja",
        "linkit": "Julkaistavat linkit, yksi riviä kohden: vesitiedot, videot, kuvaukset (näytetään sivulla)",
        "yksityiset_linkit": "Linkit vain sivun rakentamiseen (ei näytetä eikä linkitetä)",
        "yksityiset_ohje": "Esim. omat kuvat, somepäivitykset tai muistiinpanot, joista täydennys saa tietoja. "
                           "Linkkejä ei julkaista; ne näkyvät vain ylläpitäjälle.",
        "yksityiset_otsikko": "Vain sivun rakentamiseen (ei julkaista)", "teksti": "Oma teksti",
        "teksti_ohje": "Esim. lähtö- ja lopetuspaikat, kosket, pelipaikkojen kuvaukset, kokemukset eri vesillä.",
        "ehdottaja": "Nimesi tai nimimerkki (vapaaehtoinen)", "laheta": "Lähetä ehdotus",
        "tietosuoja": "Ehdotuksesta tallennetaan vain lomakkeen tiedot. Julkaistussa ehdotuksessa näkyy "
                      "antamasi nimimerkki; vain rakentamiseen annettuja linkkejä ei julkaista.",
        "esikatselu": "Ehdotuksen esikatselu", "tila_odottaa": "odottaa hyväksyntää",
        "tila_hyvaksytty": "hyväksytty ja julkaistu", "tila_hylatty": "hylätty",
        "taydennys": "Täydennys paikkaan", "uusi_kohde": "Uusi kohde",
        "paivan_tilanne": "Päivän tilanne ehdotetuilla rajoilla", "ei_mittaria": "Mittaria ei ole annettu, joten "
                          "päivän tilannetta ei voi laskea.", "ei_dataa": "Mittarin tietoja ei saatu juuri nyt.",
        "mittari_arvo": "Mittari", "pisteet": "Pisteet tänään", "kuvaus": "Kuvaus",
        "kohteet_rajat": "Kohteet ja rajat", "uusi_merkki": "ehdotettu", "korjaus": "rajakorjaus",
        "nykyiset": "nykyiset rajat", "nyt": "nyt", "muuttuu": "Muuttuu", "muutettu": "Muutettu",
        "tulossa": "Tulossa lisää", "lisatty": "Lisätty",
        "muuttuu_ohje": "Olemassa olevien kohteiden rajat: nykyinen → ehdotettu.", "vesitiedot": "Vesitiedot", "videot": "Videot", "muut_linkit": "Linkit",
        "ehdottaja_nimi": "Ehdottaja", "ilmoita": "🔔 Ilmoita minulle, kun ehdotus on käsitelty",
        "ilmoitus_tilattu": "Ilmoitus tilattu – saat push-ilmoituksen, kun ehdotus on käsitelty.",
        "ilmoitus_virhe": "Ilmoitusta ei voitu tilata", "tallenna_linkki": "Tallenna tämän sivun osoite: "
        "sillä näet ehdotuksen tilan myöhemmin.",
        "hyvaksy": "✓ Hyväksy ja julkaise", "hylkaa": "✗ Hylkää", "yllapito": "Ylläpito",
        "kayttajien_lisaykset": "Käyttäjien lisäykset", "lisaysta": "Katso koko ehdotus",
        "takaisin": "← Melontatilanne", "virhe_otsikko": "Ehdotusta ei voitu lähettää",
        "virhe_laji": "Valitse, onko kyseessä uusi kohde vai täydennys.", "virhe_paikka": "Valitse paikka.",
        "virhe_mittari": "Valitse paikan mittari.", "virhe_nimi": "Anna kohteen nimi.",
        "virhe_asema": "Mittaria ei tunnistettu: anna SYKE-aseman 7-numeroinen tunnus tai linkki kaavioon.",
        "virhe_luku": "Kohteen {n} rajat eivät ole lukuja.", "virhe_kohteen_nimi": "Anna kohteen {n} nimi.",
        "virhe_rajat": "Anna kohteelle {n} ainakin toinen toimii-raja.",
        "virhe_jarjestys": "Kohteen {n} alaraja on suurempi kuin yläraja.",
        "virhe_linkki": "Linkin pitää alkaa http:// tai https:// ({url}).",
        "virhe_linkkeja": "Enintään {n} linkkiä.", "virhe_teksti": "Teksti on liian pitkä (enintään {n} merkkiä).",
        "virhe_tyhja": "Anna ainakin yksi kohde, linkki tai teksti.",
        "virhe_jono": "Ehdotuksia on juuri nyt liikaa jonossa – yritä myöhemmin uudelleen.",
        "virhe_tallennus": "Ehdotusta ei saatu tallennettua – yritä myöhemmin uudelleen.",
        "palaa": "← Takaisin lomakkeelle",
        "taydenna_nappi": "🔍 Täydennä", "taydenna_uudelleen": "🔍 Täydennä uudelleen",
        "taydennys_kaynnissa": "⏳ Täydennys käynnissä: Claude kokoaa tietoja lähteistä. Päivitä sivu muutaman "
                               "minuutin päästä.",
        "taydennys_valmis": "✓ Täydennetty lähteistä", "taydennys_virhe": "Täydennystä ei voitu käynnistää",
        "koottu": "Koottu lähteistä", "ehdottajan_teksti": "Ehdottajan teksti", "lahto": "Lähtö", "loppu": "Loppu",
        "mittarin_valinta": "Mittari", "huomioita": "Huomioita", "lahteet": "Lähteet",
        "kaksoiskappale": "Mahdollisesti jo olemassa (tarkista ennen hyväksyntää):",
        "alkupera_arvio": "arvio lähteistä", "alkupera_ehdottaja": "ehdottaja", "kartta": "kartta",
    },
    "en": {
        "luukku": "➕ Suggest a new spot or add to an existing one",
        "luukku_teksti": "Do you know a spot that is not in the app, or the limits of a play spot better? Send a "
                         "suggestion: links, your own text and the working ranges and optimums of the features. "
                         "You will see a preview of today's conditions right away, and the suggestion is "
                         "published once the administrator has approved it.",
        "uusi": "New spot", "taydenna": "Add to a spot",
        "kayttajien_kohteet": "Spots suggested by users",
        "lomake_otsikko": "Suggest a new spot or add to an existing one",
        "lomake_ohje": "Suggestions are reviewed before publishing. After sending you will see a preview with "
                       "today's conditions using your limits. No email is asked: on the preview page you can "
                       "subscribe to a notification when the suggestion has been processed.",
        "laji": "Suggestion", "paikka": "Spot", "nimi": "Name of the spot (e.g. river and place)",
        "tyyppi": "Type", "peli": "play spot", "retki": "river run",
        "mittari": "Gauge: SYKE station number or a link to its chart (optional)",
        "mittari_ohje": "E.g. 7300350 or https://wwwi2.ymparisto.fi/i2/73/q7300350y/wqfi.html",
        "suure": "Gauge quantity", "virtaama": "discharge (m³/s)", "vedenkorkeus": "water level (m)",
        "paikan_mittari": "Gauge", "sijainti": "Location (coordinates or a map link, optional)",
        "kohteet": "Play spots or river sections and their limits",
        "rajat_uusi": "Working range and optimum of the spot",
        "rajat_uusi_ohje": "One spot at a time: give the spot's limits in the gauge's unit. Works = the range "
                           "where the spot works; optimum = the best range (empty = same as works). Leave one end "
                           "empty if there is no limit, and press + Add feature. Other play spots or river "
                           "sections of the spot are added the same way.",
        "lisaa_kohde": "+ Add feature", "poista_kohde": "Remove feature",
        "kohteita_enintaan": "At most {n} features.", "paikan_nimi": "(name of the spot)",
        "kohteen_nimi_uusi": "More specific name of the feature (optional, default = name of the spot)",
        "kohteet_ohje": "Limits in the gauge's unit. Works = the range where the feature works; optimum = the "
                        "best range (empty = same as works). Leave one end empty if there is no limit (e.g. "
                        "only a lower limit) and press + Add feature; the next feature the same way. Use the name of an "
                        "existing feature to correct its limits.",
        "kohde": "Feature", "kohteen_nimi": "Name", "toimii": "Works", "optimi": "Optimum", "huom": "Note",
        "ala": "lower", "yla": "upper",
        "linkit": "Links to publish, one per line: water data, videos, descriptions (shown on the page)",
        "yksityiset_linkit": "Links only for building the page (not shown or linked)",
        "yksityiset_ohje": "E.g. your own photos, social media posts or notes the completion can draw on. The "
                           "links are not published; only the administrator sees them.",
        "yksityiset_otsikko": "Only for building the page (not published)", "teksti": "Your text",
        "teksti_ohje": "E.g. put-in and take-out, rapids, play spot descriptions, experiences at different levels.",
        "ehdottaja": "Your name or nickname (optional)", "laheta": "Send suggestion",
        "tietosuoja": "Only the form contents are stored. A published suggestion shows the nickname you gave; "
                      "links given only for building the page are not published.",
        "esikatselu": "Suggestion preview", "tila_odottaa": "awaiting approval",
        "tila_hyvaksytty": "approved and published", "tila_hylatty": "rejected",
        "taydennys": "Addition to", "uusi_kohde": "New spot",
        "paivan_tilanne": "Today's conditions with the suggested limits", "ei_mittaria": "No gauge was given, "
                          "so today's conditions cannot be calculated.",
        "ei_dataa": "The gauge data could not be fetched right now.",
        "mittari_arvo": "Gauge", "pisteet": "Score today", "kuvaus": "Description",
        "kohteet_rajat": "Features and limits", "uusi_merkki": "suggested", "korjaus": "limit correction",
        "nykyiset": "current limits", "nyt": "now", "muuttuu": "Changes", "muutettu": "Changed",
        "tulossa": "Coming in addition", "lisatty": "Added",
        "muuttuu_ohje": "Limits of existing features: current → suggested.", "vesitiedot": "Water data", "videot": "Videos", "muut_linkit": "Links",
        "ehdottaja_nimi": "Suggested by", "ilmoita": "🔔 Notify me when the suggestion has been processed",
        "ilmoitus_tilattu": "Notification set – you will get a push notification when the suggestion has been "
                            "processed.", "ilmoitus_virhe": "Could not set the notification",
        "tallenna_linkki": "Save the address of this page: it shows the status of your suggestion later.",
        "hyvaksy": "✓ Approve and publish", "hylkaa": "✗ Reject", "yllapito": "Admin",
        "kayttajien_lisaykset": "Additions by users", "lisaysta": "See the full suggestion",
        "takaisin": "← Paddling conditions", "virhe_otsikko": "The suggestion could not be sent",
        "virhe_laji": "Choose whether this is a new spot or an addition.", "virhe_paikka": "Choose a spot.",
        "virhe_mittari": "Choose the spot's gauge.", "virhe_nimi": "Give the name of the spot.",
        "virhe_asema": "Gauge not recognised: give the 7-digit SYKE station number or a link to its chart.",
        "virhe_luku": "The limits of feature {n} are not numbers.", "virhe_kohteen_nimi": "Name feature {n}.",
        "virhe_rajat": "Give feature {n} at least one 'works' limit.",
        "virhe_jarjestys": "The lower limit of feature {n} is above the upper limit.",
        "virhe_linkki": "Links must start with http:// or https:// ({url}).",
        "virhe_linkkeja": "At most {n} links.", "virhe_teksti": "The text is too long (at most {n} characters).",
        "virhe_tyhja": "Give at least one feature, link or text.",
        "virhe_jono": "Too many suggestions are queued right now – please try again later.",
        "virhe_tallennus": "The suggestion could not be saved – please try again later.",
        "palaa": "← Back to the form",
        "taydenna_nappi": "🔍 Complete", "taydenna_uudelleen": "🔍 Complete again",
        "taydennys_kaynnissa": "⏳ Completion in progress: Claude is gathering information from sources. Reload "
                               "the page in a few minutes.",
        "taydennys_valmis": "✓ Completed from sources", "taydennys_virhe": "Completion could not be started",
        "koottu": "Compiled from sources", "ehdottajan_teksti": "Text by the suggester", "lahto": "Put-in",
        "loppu": "Take-out", "mittarin_valinta": "Gauge", "huomioita": "Notes", "lahteet": "Sources",
        "kaksoiskappale": "Possibly already exists (check before approving):",
        "alkupera_arvio": "estimate from sources", "alkupera_ehdottaja": "suggester", "kartta": "map",
    },
}


def tekstit(kieli: str) -> dict[str, str]:
    return TEKSTIT["en" if kieli == "en" else "fi"]


def tarkista_push(data) -> dict | None:
    """Selaimen push-tilaus ({endpoint, keys: {p256dh, auth}}) tallennettavaan muotoon."""
    import halytykset
    t = data.get("tilaus") if isinstance(data, dict) else None
    if not isinstance(t, dict):
        return None
    endpoint, avaimet = t.get("endpoint"), t.get("keys") or {}
    if not isinstance(endpoint, str) or len(endpoint) > 1000 or not halytykset.sallittu_osoite(endpoint):
        return None
    try:
        if len(halytykset.unb64(avaimet.get("p256dh"))) != 65 or len(halytykset.unb64(avaimet.get("auth"))) != 16:
            return None
    except (TypeError, ValueError):
        return None
    return {"endpoint": endpoint, "p256dh": avaimet["p256dh"], "auth": avaimet["auth"]}


# ---------------------------------------------------------------------------
# Kaksoiskappaleet: onko ehdotettu uusi kohde jo olemassa (toisella nimellä)?
# ---------------------------------------------------------------------------

# yleissanat, jotka eivät yksin tee kohteista samoja
YLEISSANAT = {"joki", "jokea", "koski", "kosket", "järvi", "lampi", "salmi", "reitti", "melonta", "melontareitti",
              "alaosa", "yläosa", "keskiosa", "alajuoksu", "yläjuoksu", "kansallispuisto", "silta", "kanava",
              "pato", "voimalaitos", "aalto", "hontto", "stoppari", "pelipaikka", "kylä", "luusua", "niska"}
LAHELLA_KM = 3.0


def _sanat(teksti: str) -> set[str]:
    """Nimen tunnistavat sanat: pienet kirjaimet, yleissanat pois; pitkistä sanoista 6 ensimmäistä
    kirjainta, jotta taivutusmuodot täsmäävät (Aventojoki – Aventojoen)."""
    sanat = set()
    for sana in re.findall(r"[a-zåäöA-ZÅÄÖ]{4,}", teksti or ""):
        sana = sana.lower()
        if sana in YLEISSANAT:
            continue
        sanat.add(sana[:6] if len(sana) >= 6 else sana)
    return sanat


def _etaisyys_km(a, b) -> float:
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def ehdotuksen_sijainnit(ehdotus: dict) -> list[tuple[float, float]]:
    t = valmis_taydennys(ehdotus)
    return [tuple(p) for p in (ehdotus.get("sijainti"), t.get("sijainti"), t.get("lahto_sijainti"),
                               t.get("loppu_sijainti")) if p]


def kaksoiskappaleet(ehdotus: dict, ehdokkaat: list[dict]) -> list[dict]:
    """Mahdolliset olemassa olevat kohteet: ehdokkaat = [{"nimi", "osoite", "sanat": set, "pisteet": [(lev, pit)]}]
    (sovelluksen paikat, Muut kohteet, muut ehdotukset). Palauttaa [{"nimi", "osoite", "syy"}]."""
    t = valmis_taydennys(ehdotus)
    omat_sanat = _sanat(" ".join(x for x in (ehdotus.get("nimi"), t.get("nimi")) if x))
    omat_pisteet = ehdotuksen_sijainnit(ehdotus)
    tulos = []
    for k in ehdokkaat:
        syyt = []
        yhteiset = omat_sanat & k["sanat"]
        if yhteiset:
            syyt.append("sama nimi")
        lahin = min((_etaisyys_km(a, b) for a in omat_pisteet for b in k["pisteet"]), default=None)
        if lahin is not None and lahin <= LAHELLA_KM:
            syyt.append(f"sijainti {lahin:.1f} km päässä")
        if syyt:
            tulos.append({"nimi": k["nimi"], "osoite": k["osoite"], "syy": ", ".join(syyt)})
    return tulos
