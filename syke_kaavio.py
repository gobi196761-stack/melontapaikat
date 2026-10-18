"""SYKE:n (WSFS-vesistömalli) ennustekaavioiden lukija.

osm.fi:n melontapaikkasivujen lopussa olevat vedenkorkeus-, virtaama- ja
lämpötilakaaviot ovat SYKE:n vakiomuotoisia PNG-kuvia (2700 x 1200 px).
Kuvissa on puhdas 9 värin paletti ilman reunanpehmennystä, joten arvot
voidaan lukea pikselitarkasti:

* y-akselin asteikko: akselin lyhyet tikkiviivat + tikkien numeroiden
  tunnistus glyfimalleilla (glyfit.json)
* "tänään": syaani katkoviiva (ennusteen alku)
* havaittu arvo: mustat vinoneliöt päivien pystyviivojen kohdalla
* malliarvo / ennuste: sininen viiva
* historiallinen vaihteluväli: harmaa alue, mediaani: magenta viiva
* pitkän ajan tunnusluvut (MHW/MNW tai MHQ/MNQ): selitteen tekstistä
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

GLYFIT_POLKU = Path(__file__).with_name("glyfit.json")

# Diagnostiikkaa varten: vinoneliön ja tikkien geometria (pikseleinä)
VINONELIO_R = 17          # vinoneliön "säde" L1-normissa (kärjestä keskelle)
VINONELIO_REUNA = (9, 16)  # musta reunus L1-etäisyyksillä 9..16 keskeltä
VINONELIO_SISUS = 6       # sisus L1-etäisyydellä <= 6 ei ole mustaa


class KaavioVirhe(Exception):
    """Kaaviota ei voitu tulkita luotettavasti."""


# ---------------------------------------------------------------------------
# Värimaskit
# ---------------------------------------------------------------------------

def _maskit(a: np.ndarray) -> dict[str, np.ndarray]:
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return {
        "musta": (r == 0) & (g == 0) & (b == 0),
        "sininen": (r == 0) & (g == 0) & (b == 255),
        "syaani": (r == 0) & (g == 255) & (b == 255),
        "magenta": (r == 255) & (g == 0) & (b == 255),
        "punainen": (r == 255) & (g == 0) & (b == 0),
        "vihrea": (r == 0) & (g == 255) & (b == 0),
        "harmaa": (r == g) & (g == b) & (r > 190) & (r < 235),
        "valkoinen": (r == 255) & (g == 255) & (b == 255),
    }


# ---------------------------------------------------------------------------
# Glyfien erottelu ja tunnistus
# ---------------------------------------------------------------------------

@dataclass
class Glyfi:
    x0: int
    x1: int
    y0: int
    y1: int
    bitit: np.ndarray  # bool, muoto (h, w)

    @property
    def leveys(self) -> int:
        return self.x1 - self.x0

    @property
    def korkeus(self) -> int:
        return self.y1 - self.y0


def _yhtenaiset_alueet(maski: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """8-yhtenäiset pikselialueet riviajoina + union-find."""
    ajot: list[tuple[int, int, int]] = []   # (y, x_alku, x_loppu) loppu mukaan lukien
    rivin_ajot: list[list[int]] = []
    for y in range(maski.shape[0]):
        rivi = maski[y].astype(np.int8)
        muutos = np.diff(np.concatenate(([0], rivi, [0])))
        alut, loput = np.nonzero(muutos == 1)[0], np.nonzero(muutos == -1)[0] - 1
        rivin_ajot.append(list(range(len(ajot), len(ajot) + len(alut))))
        ajot += [(y, int(a), int(b)) for a, b in zip(alut, loput)]

    vanhempi = list(range(len(ajot)))

    def juuri(i: int) -> int:
        while vanhempi[i] != i:
            vanhempi[i] = vanhempi[vanhempi[i]]
            i = vanhempi[i]
        return i

    for y in range(1, maski.shape[0]):
        ylempi = rivin_ajot[y - 1]
        for i in rivin_ajot[y]:
            _, a, b = ajot[i]
            for j in ylempi:
                _, c, d = ajot[j]
                if c <= b + 1 and a <= d + 1:   # päällekkäin tai kulmittain
                    vanhempi[juuri(i)] = juuri(j)

    ryhmat: dict[int, list[int]] = {}
    for i in range(len(ajot)):
        ryhmat.setdefault(juuri(i), []).append(i)
    alueet = []
    for jasenet in ryhmat.values():
        ys = np.concatenate([np.full(ajot[i][2] - ajot[i][1] + 1, ajot[i][0]) for i in jasenet])
        xs = np.concatenate([np.arange(ajot[i][1], ajot[i][2] + 1) for i in jasenet])
        alueet.append((ys, xs))
    return alueet


def erottele_glyfit(maski: np.ndarray, x_offset: int = 0, y_offset: int = 0,
                    min_korkeus: int = 1) -> list[Glyfi]:
    """Pilkkoo binäärisen tekstialueen merkeiksi yhtenäisinä alueina.

    Päällekkäin olevat osat (esim. ':' tai 'ä') yhdistetään yhdeksi merkiksi,
    mutta vierekkäin toisiinsa limittyvät merkit (esim. '/s') pysyvät erillään.
    """
    laatikot = []
    for ys, xs in _yhtenaiset_alueet(maski):
        laatikot.append([xs.min(), xs.max() + 1, ys.min(), ys.max() + 1, [(ys, xs)]])
    laatikot.sort(key=lambda b: (b[0], b[2]))
    yhdistetyt: list[list] = []
    for b in laatikot:
        for e in yhdistetyt:
            limitys = min(e[1], b[1]) - max(e[0], b[0])
            pystyrako = max(e[2], b[2]) - min(e[3], b[3])
            if limitys >= 0.6 * min(e[1] - e[0], b[1] - b[0]) and pystyrako <= 12:
                e[0], e[1] = min(e[0], b[0]), max(e[1], b[1])
                e[2], e[3] = min(e[2], b[2]), max(e[3], b[3])
                e[4] += b[4]
                break
        else:
            yhdistetyt.append(b)
    yhdistetyt.sort(key=lambda b: b[0])
    glyfit = []
    for x0, x1, y0, y1, osat in yhdistetyt:
        if y1 - y0 < min_korkeus:
            continue
        bitit = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        for ys, xs in osat:
            bitit[ys - y0, xs - x0] = True
        glyfit.append(Glyfi(int(x0) + x_offset, int(x1) + x_offset,
                            int(y0) + y_offset, int(y1) + y_offset, bitit))
    return glyfit


def _skaalaa(bitit: np.ndarray, w: int, h: int) -> np.ndarray:
    kuva = Image.fromarray(bitit.astype(np.uint8) * 255)
    return np.array(kuva.resize((w, h), Image.NEAREST)) > 127


class Glyfitunnistin:
    """Lähimmän naapurin tunnistus tallennettuja glyfimalleja vasten."""

    def __init__(self, mallit: list[dict] | None = None):
        self.mallit: list[tuple[str, np.ndarray]] = []
        for m in mallit or []:
            self.mallit.append((m["merkki"], koodaa_auki(m)))

    @classmethod
    def lataa(cls, polku: Path = GLYFIT_POLKU) -> "Glyfitunnistin":
        if not polku.exists():
            raise KaavioVirhe(f"Glyfimalleja ei löydy: {polku}")
        return cls(json.loads(polku.read_text(encoding="utf-8")))

    def tunnista(self, g: Glyfi, max_ero: float = 0.12) -> str | None:
        paras, paras_ero = None, 1.0
        skaalatut: dict[tuple[int, int], np.ndarray] = {}
        for merkki, malli in self.mallit:
            h, w = malli.shape
            if abs(h - g.korkeus) > 2 or abs(w - g.leveys) > 2:
                continue
            if (w, h) not in skaalatut:
                skaalatut[(w, h)] = _skaalaa(g.bitit, w, h)
            ero = np.count_nonzero(skaalatut[(w, h)] != malli) / (w * h)
            if ero < paras_ero:
                paras, paras_ero = merkki, ero
        return paras if paras_ero <= max_ero else None

    def lue_teksti(self, glyfit: list[Glyfi], valilyonti_px: int = 12) -> str:
        """Muuttaa glyfirivin merkkijonoksi; tuntemattomat merkit ovat '?'."""
        osat = []
        edellinen_x1 = None
        for g in glyfit:
            if edellinen_x1 is not None and g.x0 - edellinen_x1 >= valilyonti_px:
                osat.append(" ")
            osat.append(self.tunnista(g) or "?")
            edellinen_x1 = g.x1
        return "".join(osat)


def koodaa(merkki: str, bitit: np.ndarray) -> dict:
    h, w = bitit.shape
    tavut = np.packbits(bitit.astype(np.uint8).ravel())
    return {"merkki": merkki, "w": int(w), "h": int(h), "bitit": tavut.tobytes().hex()}


def koodaa_auki(m: dict) -> np.ndarray:
    tavut = np.frombuffer(bytes.fromhex(m["bitit"]), dtype=np.uint8)
    return np.unpackbits(tavut)[: m["w"] * m["h"]].reshape(m["h"], m["w"]).astype(bool)


_NUMERO = re.compile(r"-?\d+(?:\.\d+)?")


def _viimeinen_numero(teksti: str) -> float | None:
    """Ottaa merkkijonon viimeisen kokonaisen numeron (esim. '?108.8' -> 108.8)."""
    osumat = _NUMERO.findall(teksti.replace(" ", ""))
    return float(osumat[-1]) if osumat else None


# ---------------------------------------------------------------------------
# Kaavion rakenne
# ---------------------------------------------------------------------------

@dataclass
class Kehys:
    vasen: int   # y-akselin x
    oikea: int   # piirtoalueen oikea reuna
    yla: int     # piirtoalueen yläreuna
    ala: int     # x-akselin y


def etsi_kehys(m: dict[str, np.ndarray]) -> Kehys:
    musta = m["musta"]
    h, w = musta.shape
    # Y-akseli: vasemman reunan pisin musta pystyviiva
    sarakesummat = musta[:, : w // 4].sum(axis=0)
    if sarakesummat.max() < h * 0.4:
        raise KaavioVirhe("Kaavion y-akselia ei löytynyt (kuva ei ole SYKE-kaavio?)")
    vasen = int(np.nonzero(sarakesummat >= 0.9 * sarakesummat.max())[0].min())
    # X-akseli: alin vaakaviiva, joka kattaa koko piirtoalueen. Akselin päälle
    # voi olla piirretty värillinen katkoviiva (esim. punainen NQ-taso),
    # joten kelpuutetaan kaikki viivavärit.
    viiva = musta | m["punainen"] | m["sininen"] | m["magenta"] | m["vihrea"]
    kaista = viiva[:, vasen: vasen + w // 2]
    rivit = np.nonzero(kaista.mean(axis=1) >= 0.9)[0]
    if len(rivit) == 0:
        raise KaavioVirhe("Kaavion x-akselia ei löytynyt")
    ala = int(rivit.max())
    x = vasen
    while x + 1 < w and viiva[ala, x + 1]:
        x += 1
    oikea = x
    pysty = np.nonzero(musta[:, vasen])[0]
    yla = int(pysty.min())
    if not (oikea - vasen > w * 0.4 and ala - yla > h * 0.4):
        raise KaavioVirhe("Kaavion akseleita ei löytynyt")
    return Kehys(vasen, oikea, yla, ala)


def _ryhmittele(arvot: list[int], rako: int = 1) -> list[float]:
    """Yhdistää peräkkäiset kokonaisluvut ryhmiksi ja palauttaa ryhmien keskikohdat."""
    ryhmat: list[list[int]] = []
    for v in sorted(arvot):
        if ryhmat and v - ryhmat[-1][-1] <= rako:
            ryhmat[-1].append(v)
        else:
            ryhmat.append([v])
    return [float(np.mean(r)) for r in ryhmat]


def etsi_y_tikit(musta: np.ndarray, k: Kehys) -> list[float]:
    """Y-akselin tikit ovat akselista oikealle lähteviä n. 45 px mittaisia
    yhtenäisiä mustia viivanpätkiä (ruudukon vaakaviivat ovat pisteviivaa)."""
    rivit = [y for y in range(k.yla - 3, k.ala + 3)
             if musta[y, k.vasen + 3: k.vasen + 40].all()]
    return _ryhmittele(rivit)


def etsi_paivaviivat(musta: np.ndarray, k: Kehys) -> tuple[list[int], float]:
    """Pystysuorat päiväviivat (pisteviivaa). Palauttaa x-paikat ja välin."""
    alue = musta[k.yla: k.ala - 2, :]
    osuus = alue.sum(axis=0) / alue.shape[0]
    xs = [x for x in range(k.vasen + 10, k.oikea - 2) if osuus[x] > 0.25]
    viivat = [int(round(x)) for x in _ryhmittele(xs)]
    if len(viivat) < 5:
        raise KaavioVirhe("Päiväviivoja ei löytynyt")
    vali = float(np.median(np.diff(viivat)))
    return viivat, vali


# ---------------------------------------------------------------------------
# Lukutulos
# ---------------------------------------------------------------------------

@dataclass
class Kaaviolukema:
    url: str
    suure: str                 # "vedenkorkeus" | "virtaama" | "lampotila"
    yksikko: str               # "m" | "m3/s" | "°C"
    tanaan_paiva: int | None   # x-akselin päivänumero ennusteen alun kohdalla
    havaittu: float | None     # tämän päivän (tai tuoreimman) havainnon arvo
    havaittu_paivia_sitten: int | None
    malli: float | None        # sinisen käyrän arvo tänään
    ennuste: dict[int, float] = field(default_factory=dict)  # päivä+n -> arvo
    hist_min: float | None = None   # harmaan vaihteluvälin alaraja tänään
    hist_max: float | None = None   # harmaan vaihteluvälin yläraja tänään
    hist_max_rajattu: bool = False  # vaihteluväli jatkuu kaavion yläreunan yli
    hist_min_rajattu: bool = False  # vaihteluväli jatkuu kaavion alareunan ali
    mediaani: float | None = None
    tunnusluvut: dict[str, float] = field(default_factory=dict)  # MHW, MNW, ...
    asteikko: tuple[float, float] = (0.0, 0.0)  # arvo = a + b * y

    @property
    def arvo(self) -> float | None:
        """Paras arvio tämän päivän tilanteesta: havainto, muuten malli."""
        return self.havaittu if self.havaittu is not None else self.malli

    @property
    def lahde(self) -> str:
        if self.havaittu is None:
            return "malli"
        if self.havaittu_paivia_sitten:
            return f"havainto {self.havaittu_paivia_sitten} pv sitten"
        return "havainto"

    def ennuste_korjattu(self, paivia: int) -> float | None:
        """Ennusteen muutos lisättynä havaintoon (malli voi olla harhainen)."""
        if paivia not in self.ennuste or self.malli is None or self.arvo is None:
            return None
        return self.arvo + (self.ennuste[paivia] - self.malli)

    @property
    def tulvaindeksi(self) -> float | None:
        """0 = keskimääräinen vuoden alivesi (MNW/MNQ), 1 = keskim. kevättulva (MHW/MHQ)."""
        ala = self.tunnusluvut.get("MNW", self.tunnusluvut.get("MNQ"))
        yla = self.tunnusluvut.get("MHW", self.tunnusluvut.get("MHQ"))
        if ala is None or yla is None or yla <= ala or self.arvo is None:
            return None
        return (self.arvo - ala) / (yla - ala)


def suure_urlista(url: str) -> tuple[str, str]:
    nimi = url.rsplit("/", 1)[-1].lower()
    if nimi.startswith("tw"):
        return "lampotila", "°C"
    if nimi.startswith("q"):
        return "virtaama", "m3/s"
    if nimi.startswith("w"):
        return "vedenkorkeus", "m"
    raise KaavioVirhe(f"Tuntematon kaaviotyyppi: {nimi}")


class KaavioLukija:
    def __init__(self, tunnistin: Glyfitunnistin | None = None):
        self.tunnistin = tunnistin or Glyfitunnistin.lataa()

    # -- julkinen rajapinta -------------------------------------------------

    def lue(self, kuva: bytes | Path | str, url: str = "") -> Kaaviolukema:
        if isinstance(kuva, (str, Path)):
            kuva = Path(kuva).read_bytes()
        a = np.array(Image.open(io.BytesIO(kuva)).convert("RGB")).astype(np.int16)
        m = _maskit(a)
        k = etsi_kehys(m)
        a_, b_ = self._asteikko(m["musta"], k)
        arvo = lambda y: a_ + b_ * y  # noqa: E731

        viivat, vali = etsi_paivaviivat(m["musta"], k)
        x_tanaan = self._tanaan_x(m["syaani"], k)
        suure, yksikko = suure_urlista(url) if url else ("?", "")

        # Havainnot: vinoneliöt tänään ja enintään 3 päivää taaksepäin
        havaittu, sitten = None, None
        for n in range(0, 4):
            x = int(round(x_tanaan - n * vali))
            if x < k.vasen:
                break
            y = self._vinonelio(m["musta"], k, x)
            if y is not None:
                havaittu, sitten = arvo(y), n
                break

        malli_y = self._sininen(m["sininen"], k, x_tanaan, vali)
        ennuste = {}
        for n in range(1, 15):
            x = x_tanaan + n * vali
            if x > k.oikea - 2:
                break
            y = self._sininen(m["sininen"], k, x, vali)
            if y is not None:
                ennuste[n] = arvo(y)

        hist = self._harmaa_vali(m, k, int(round(x_tanaan - 0.15 * vali)))
        med_y = self._viiva_y(m["magenta"], k, int(round(x_tanaan)), leveys=int(vali * 0.1))
        if med_y is not None and (med_y <= k.yla + 3 or med_y >= k.ala - 4):
            med_y = None  # mediaani kaavion ulkopuolella (piirretty reunaan)

        tulos = Kaaviolukema(
            url=url, suure=suure, yksikko=yksikko,
            tanaan_paiva=self._paivanumero(m["musta"], k, x_tanaan, vali),
            havaittu=havaittu, havaittu_paivia_sitten=sitten,
            malli=arvo(malli_y) if malli_y is not None else None,
            ennuste=ennuste,
            mediaani=arvo(med_y) if med_y is not None else None,
            tunnusluvut=self._tunnusluvut(m["musta"], k),
            asteikko=(a_, b_),
        )
        if hist:
            y_yla, y_ala, yla_rajattu, ala_rajattu = hist
            tulos.hist_max, tulos.hist_min = arvo(y_yla), arvo(y_ala)
            tulos.hist_max_rajattu, tulos.hist_min_rajattu = yla_rajattu, ala_rajattu
        return tulos

    # -- asteikko -----------------------------------------------------------

    @staticmethod
    def y_tikkien_glyfit(musta: np.ndarray, k: Kehys) -> list[tuple[float, list[Glyfi]]]:
        """Y-akselin numerot ryhmiteltyinä riveiksi + kunkin rivin tikin y.

        Numerot sijaitsevat akselin vasemmalla puolella eikä mikään piirrä
        niiden päälle, joten ne löytyvät luotettavammin kuin itse tikit
        (sininen viiva tai vinoneliö voi peittää tikin). Tikin paikka
        otetaan löydetystä tikistä, tai sen puuttuessa numeron keskikohdasta.
        """
        x0, x1 = 110, k.vasen - 18   # vinoneliö voi ulottua 17 px akselin vasemmalle
        alue = musta[max(k.yla - 60, 0): k.ala + 30, x0:x1]
        glyfit = erottele_glyfit(alue, x0, max(k.yla - 60, 0), min_korkeus=3)
        # ryhmittele glyfit riveiksi pystysuuntaisen päällekkäisyyden mukaan
        rivit: list[list[Glyfi]] = []
        for g in sorted(glyfit, key=lambda g: g.y0):
            if rivit and g.y0 < max(r.y1 for r in rivit[-1]):
                rivit[-1].append(g)
            else:
                rivit.append([g])
        rivit = [sorted(r, key=lambda g: g.x0) for r in rivit
                 if max(g.korkeus for g in r) >= 20]
        tikit = etsi_y_tikit(musta, k)
        keskikohdat = [(min(g.y0 for g in r) + max(g.y1 for g in r)) / 2 for r in rivit]
        erot = [t - c for c in keskikohdat for t in tikit if abs(t - c - 8.5) < 6]
        siirto = float(np.median(erot)) if erot else 8.5
        tulos = []
        for r, c in zip(rivit, keskikohdat):
            lahin = min(tikit, key=lambda t: abs(t - c - siirto), default=None)
            ty = lahin if lahin is not None and abs(lahin - c - siirto) < 4 else c + siirto
            tulos.append((ty, r))
        return tulos

    def _asteikko(self, musta: np.ndarray, k: Kehys) -> tuple[float, float]:
        pisteet = []
        for ty, glyfit in self.y_tikkien_glyfit(musta, k):
            v = _viimeinen_numero(self.tunnistin.lue_teksti(glyfit))
            if v is not None:
                pisteet.append((ty, v))
        if len(pisteet) < 3:
            raise KaavioVirhe("Y-akselin asteikkoa ei saatu luettua")
        return _sovita_asteikko(pisteet)

    # -- osat ---------------------------------------------------------------

    @staticmethod
    def _tanaan_x(syaani: np.ndarray, k: Kehys) -> float:
        alue = syaani[k.yla: k.ala, k.vasen: k.oikea]
        summat = alue.sum(axis=0)
        if summat.max() < 0.3 * alue.shape[0]:
            raise KaavioVirhe("Ennusteen alkua (syaani viiva) ei löytynyt")
        xs = np.nonzero(summat >= 0.8 * summat.max())[0]
        return float(xs.mean()) + k.vasen

    @staticmethod
    def _vinonelio(musta: np.ndarray, k: Kehys, x_keski: int) -> float | None:
        """Etsii havaintovinoneliön keskipisteen y:n annetun päiväviivan kohdalta.

        Vinoneliö tunnistetaan mustasta reunuksesta. Lisäksi vaaditaan, että
        joko sisus on (enimmäkseen) tyhjä tai heti reunuksen ulkopuolella on
        tyhjää: sisuksen voi peittää esim. '+'-merkki (keskimääräinen huippu)
        tai ennusteen alusta lähtevä musta viiva.
        """
        r_min, r_max = VINONELIO_REUNA
        R = VINONELIO_R
        U = R + 4
        reuna, sisus, ulko = [], [], []
        for dy in range(-U, U + 1):
            for dx in range(-U, U + 1):
                d = abs(dx) + abs(dy)
                if r_min <= d <= r_max:
                    reuna.append((dy, dx))
                elif d <= VINONELIO_SISUS and abs(dx) > 1:  # ohita ruudukon pisteviiva
                    sisus.append((dy, dx))
                elif R + 2 <= d <= R + 4 and abs(dx) > 1:
                    ulko.append((dy, dx))
        reuna, sisus, ulko = np.array(reuna), np.array(sisus), np.array(ulko)
        paras, paras_pisteet = None, -1.0
        ys = np.arange(max(k.yla - 5, U), min(k.ala + 5, musta.shape[0] - U))
        for x in range(x_keski - 3, x_keski + 4):
            if x - U < 0 or x + U >= musta.shape[1]:
                continue
            osuus = lambda o: musta[ys[:, None] + o[:, 0], x + o[:, 1]].mean(axis=1)  # noqa: E731
            r_osuus, s_osuus, u_osuus = osuus(reuna), osuus(sisus), osuus(ulko)
            kelpaa = (r_osuus >= 0.9) & ((s_osuus <= 0.6) | (u_osuus <= 0.35))
            if not kelpaa.any():
                continue
            pisteet = np.where(kelpaa, r_osuus - np.minimum(s_osuus, u_osuus), -1.0)
            i = int(np.argmax(pisteet))
            if pisteet[i] > paras_pisteet:
                paras, paras_pisteet = float(ys[i]), float(pisteet[i])
        return paras

    @staticmethod
    def _viiva_y(maski: np.ndarray, k: Kehys, x: int, leveys: int = 3) -> float | None:
        """Värillisen viivan keskikohta sarakkeissa x-leveys..x+leveys."""
        x0, x1 = max(x - leveys, k.vasen + 2), min(x + leveys + 1, k.oikea - 1)
        if x1 <= x0:
            return None
        ys = []
        for xx in range(x0, x1):
            rivit = np.nonzero(maski[k.yla: k.ala - 1, xx])[0]
            if len(rivit):
                # pisin yhtenäinen pätkä = viiva (ei esim. irrallisia pikseleitä)
                pätkät = np.split(rivit, np.nonzero(np.diff(rivit) > 2)[0] + 1)
                pisin = max(pätkät, key=len)
                ys.append(float(pisin.mean()) + k.yla)
        return float(np.median(ys)) if ys else None

    def _sininen(self, sininen: np.ndarray, k: Kehys, x: float, vali: float) -> float | None:
        # Syaani katkoviiva peittää sinisen tasan ennusteen alussa -> näytteet sivuilta
        lev = max(2, int(vali * 0.04))
        arvot = [self._viiva_y(sininen, k, int(round(x + d)), lev)
                 for d in (-0.12 * vali, 0.0, 0.12 * vali)]
        arvot = [v for v in arvot if v is not None]
        return float(np.median(arvot)) if arvot else None

    @staticmethod
    def _harmaa_vali(m: dict, k: Kehys, x: int) -> tuple[float, float, bool, bool] | None:
        """Historiallisen vaihteluvälin (harmaa) ylä- ja alareuna sarakkeessa x."""
        sarake = m["harmaa"][k.yla + 1: k.ala - 1, x]
        rivit = np.nonzero(sarake)[0]
        if len(rivit) == 0:
            return None
        y_yla = float(rivit.min()) + k.yla + 1
        y_ala = float(rivit.max()) + k.yla + 1
        return y_yla, y_ala, bool(rivit.min() <= 2), bool(rivit.max() >= len(sarake) - 3)

    @staticmethod
    def x_akselin_glyfit(musta: np.ndarray, k: Kehys, x: float, vali: float) -> list[Glyfi]:
        """X-akselin päivänumeron glyfit päiväviivan x oikealta puolelta."""
        # Päivänumerot ovat akselin alla riveillä ala+9..ala+33; akselin alle
        # jäävät lyhyet tikit (korkeus < 12 px) suodattuvat pois korkeusrajalla.
        # Alempana oleva kuukauden nimi alkaa vasta n. ala+42.
        xi = int(round(x))
        x0, x1 = xi + 2, int(round(x + vali)) - 2
        y0 = k.ala + 2
        alue = musta[y0: k.ala + 38, x0:x1]
        return erottele_glyfit(alue, x0, y0, min_korkeus=12)

    def _paivanumero(self, musta: np.ndarray, k: Kehys, x: float, vali: float) -> int | None:
        """Lukee x-akselin päivänumeron ennusteen alun kohdalta."""
        teksti = self.tunnistin.lue_teksti(self.x_akselin_glyfit(musta, k, x, vali))
        luku = _viimeinen_numero(teksti)
        return int(luku) if luku is not None and 1 <= luku <= 31 else None

    def selitteen_rivit(self, musta: np.ndarray, k: Kehys) -> list[list[Glyfi]]:
        """Selitealueen tekstirivit glyfeinä (viivanäytteet poistettu)."""
        alue = musta[:, k.oikea + 8:].copy()
        # poista pitkät vaakaviivat (selitteen viivanäytteet ja alleviivaukset)
        for y in range(alue.shape[0]):
            rivi = alue[y]
            if rivi.sum() < 40:
                continue
            xs = np.nonzero(rivi)[0]
            for pätkä in np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1):
                if len(pätkä) >= 40:
                    rivi[pätkä] = False
        profiili = alue.sum(axis=1) > 0
        rivit = []
        y = 0
        while y < len(profiili):
            if not profiili[y]:
                y += 1
                continue
            y_alku = y
            while y < len(profiili) and profiili[y]:
                y += 1
            if y - y_alku >= 15:
                glyfit = erottele_glyfit(alue[y_alku:y], k.oikea + 8, y_alku, min_korkeus=2)
                rivit.append(glyfit)
        return rivit

    def _tunnusluvut(self, musta: np.ndarray, k: Kehys) -> dict[str, float]:
        tulos: dict[str, float] = {}
        for glyfit in self.selitteen_rivit(musta, k):
            # tunnuslukurivit alkavat M-kirjaimella (MHW, MNW, MHQ, MNQ)
            if not glyfit or self.tunnistin.tunnista(glyfit[0]) != "M":
                continue
            teksti = self.tunnistin.lue_teksti(glyfit, valilyonti_px=10)
            # kapean '1':n ympärille jää leveä rako, joka näyttää välilyönniltä
            teksti = re.sub(r"(?<=[\d.]) +(?=[\d.])", "", teksti)
            for avain, luku in re.findall(r"(MH[WQ]|MN[WQ])\s*(\d+(?:\.\d+)?)", teksti):
                tulos.setdefault(avain, float(luku))
        return tulos


def _sovita_asteikko(pisteet: list[tuple[float, float]]) -> tuple[float, float]:
    """Sovittaa suoran arvo = a + b*y. Hylkää yksittäisen väärin luetun tikin."""
    def sovita(p):
        y = np.array([q[0] for q in p])
        v = np.array([q[1] for q in p])
        b, a = np.polyfit(y, v, 1)
        jaannos = np.abs(a + b * y - v)
        return a, b, jaannos

    a, b, jaannos = sovita(pisteet)
    porras = abs(b) * float(np.median(np.diff(sorted(q[0] for q in pisteet))))
    while jaannos.max() > 0.05 * porras and len(pisteet) > 3:
        pisteet = [p for p, j in zip(pisteet, jaannos) if j < jaannos.max()]
        a, b, jaannos = sovita(pisteet)
    if jaannos.max() > 0.05 * porras or b >= 0:
        raise KaavioVirhe("Y-akselin tikkien arvot eivät ole johdonmukaisia")
    return float(a), float(b)
