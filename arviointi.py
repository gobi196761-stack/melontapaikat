"""Paikkojen pisteytys kaavioista luettujen arvojen perusteella.

Kohteen pisteet (0–100) ennen laatukerrointa:

* parhaalla alueella                           100
* toimivalla alueella, mutta ei parhaalla      60–100 (lineaarisesti parhaan reunaa kohti)
* toimivan alueen ulkopuolella                 0–45 (lähestyy nollaa marginaalin matkalla)

Paikan pisteet = paras kohde × laatu + 2 pistettä jokaisesta muusta
toimivasta kohteesta (lisä enintään 6, kokonaisuus enintään 100). Ennusteesta lasketaan samat pisteet
lähipäiville, jotta nähdään paraneeko vai heikkeneekö tilanne.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from paikat import Kohde, Paikka
from syke_data import ENNUSTE_PAIVIA
from syke_kaavio import Kaaviolukema

ENNUSTEPAIVAT = tuple(range(1, ENNUSTE_PAIVIA + 1))   # +1…+14 pv, kuten kaavioiden ennuste
REUNAPISTEET = 45      # pisteet heti toimivan alueen ulkopuolella
LISA_PER_KOHDE = 2     # lisäpisteet jokaisesta muusta toimivasta kohteesta
LISA_MAX = 6


def muotoile(x: float, yksikko: str, muuttuja: str = "arvo") -> str:
    """Erotus tai arvo luettavassa muodossa (pienet erot tarkemmin)."""
    if muuttuja == "tulvaindeksi":
        return f"{x:.2f}"
    if yksikko == "m":
        return "<0.01 m" if 0 < abs(x) < 0.005 else f"{x:.2f} m"
    if yksikko == "m3/s":
        if 0 < abs(x) < 0.05:
            return "<0.1 m³/s"
        return f"{x:.1f} m³/s" if abs(x) < 20 else f"{x:.0f} m³/s"
    return f"{x:.1f} {yksikko}"


@dataclass
class KohdeTulos:
    kohde: Kohde
    pisteet: float          # laatukertoimella painotettu
    tila: str               # "paras" | "toimii" | "ei toimi"
    selitys: str
    arvo: float | None


@dataclass
class PaikkaTulos:
    paikka: Paikka
    pisteet: float | None
    kohteet: list[KohdeTulos] = field(default_factory=list)
    lukemat: dict[str, Kaaviolukema] = field(default_factory=dict)  # mittariavain -> lukema
    ennuste: dict[int, float] = field(default_factory=dict)          # päivä -> pisteet
    ennusteen_kohteet: dict[int, list[KohdeTulos]] = field(default_factory=dict)  # päivä -> kohteet
    huomiot: list[str] = field(default_factory=list)
    sivun_kaaviot: list[Kaaviolukema] = field(default_factory=list)  # kaikki sivun kaaviot

    @property
    def paras_kohde(self) -> KohdeTulos | None:
        return max(self.kohteet, key=lambda k: k.pisteet, default=None)

    @property
    def toimivat(self) -> list[KohdeTulos]:
        return [k for k in self.kohteet if k.tila != "ei toimi"]


def _sisalla(v: float, vali: tuple[float | None, float | None]) -> bool:
    ala, yla = vali
    return (ala is None or v >= ala) and (yla is None or v <= yla)


def _etaisyys(v: float, vali: tuple[float | None, float | None]) -> float:
    ala, yla = vali
    if ala is not None and v < ala:
        return ala - v
    if yla is not None and v > yla:
        return v - yla
    return 0.0


def _oletusmarginaali(kohde: Kohde, arvo: float, yksikko: str) -> float:
    if kohde.muuttuja == "tulvaindeksi":
        return 0.25
    if yksikko != "m3/s":
        return 0.3  # vedenkorkeus: 30 cm
    # virtaama: 30 % rajasta
    rajat = [r for r in (*kohde.toimii, *kohde.paras) if r is not None]
    return 0.3 * (max(rajat) if rajat else abs(arvo))


def pisteyta_kohde(kohde: Kohde, v: float, marginaali: float | None, yksikko: str) -> KohdeTulos:
    if marginaali is None:
        marginaali = _oletusmarginaali(kohde, v, yksikko)
    def fmt(x: float) -> str:
        return muotoile(x, yksikko, kohde.muuttuja)

    if _sisalla(v, kohde.paras):
        perus, tila, selitys = 100.0, "paras", "parhaimmillaan"
    elif _sisalla(v, kohde.toimii):
        # 60 toimivan alueen reunalla -> 100 parhaan alueen reunalla
        d_paras = _etaisyys(v, kohde.paras)
        ala, yla = kohde.toimii
        pa, py = kohde.paras
        if pa is not None and v < pa:
            leveys = pa - (ala if ala is not None else pa - marginaali)
        else:
            leveys = (yla if yla is not None else py + marginaali) - py
        osuus = max(0.0, 1 - d_paras / leveys) if leveys > 0 else 1.0
        perus, tila = 60 + 40 * osuus, "toimii"
        suunta = "alle" if (pa is not None and v < pa) else "yli"
        selitys = f"toimii ({fmt(d_paras)} {suunta} parhaan)"
    else:
        d = _etaisyys(v, kohde.toimii)
        perus = REUNAPISTEET * max(0.0, 1 - d / marginaali)
        tila = "ei toimi"
        ala, _ = kohde.toimii
        if ala is not None and v < ala:
            selitys = f"liian vähän vettä (puuttuu {fmt(d)})"
        else:
            selitys = f"liikaa vettä ({fmt(d)} yli)"
    return KohdeTulos(kohde, perus * kohde.laatu, tila, selitys, v)


def _muuttujan_arvo(kohde: Kohde, lukema: Kaaviolukema, ennustepaiva: int = 0) -> float | None:
    arvo = lukema.arvo if ennustepaiva == 0 else lukema.ennuste_korjattu(ennustepaiva)
    if arvo is None:
        return None
    if kohde.muuttuja == "tulvaindeksi":
        ala = lukema.tunnusluvut.get("MNW", lukema.tunnusluvut.get("MNQ"))
        yla = lukema.tunnusluvut.get("MHW", lukema.tunnusluvut.get("MHQ"))
        if ala is None or yla is None or yla <= ala:
            return None
        return (arvo - ala) / (yla - ala)
    return arvo


def _yhdista(kohteet: list[KohdeTulos]) -> float | None:
    if not kohteet:
        return None
    jarjestetty = sorted(kohteet, key=lambda k: k.pisteet, reverse=True)
    lisa = min(LISA_MAX, LISA_PER_KOHDE * sum(1 for k in jarjestetty[1:] if k.tila != "ei toimi"))
    return min(100.0, jarjestetty[0].pisteet + lisa)


def arvioi(paikka: Paikka, lukemat: dict[str, Kaaviolukema]) -> PaikkaTulos:
    tulos = PaikkaTulos(paikka, None, lukemat=lukemat)
    if not paikka.kohteet:
        tulos.huomiot.append("ei vesikaaviota – tarkista tilanne itse")
        return tulos

    for kohde in paikka.kohteet:
        lukema = lukemat.get(kohde.mittari)
        if lukema is None:
            tulos.huomiot.append(f"{kohde.nimi}: kaaviota ei saatu luettua")
            continue
        v = _muuttujan_arvo(kohde, lukema)
        if v is None:
            tulos.huomiot.append(f"{kohde.nimi}: arvoa ei saatu kaaviosta")
            continue
        mittari = paikka.mittarit[kohde.mittari]
        marginaali = mittari.marginaali if kohde.muuttuja == "arvo" else None
        tulos.kohteet.append(pisteyta_kohde(kohde, v, marginaali, lukema.yksikko))

    tulos.pisteet = _yhdista(tulos.kohteet)

    for n in ENNUSTEPAIVAT:
        kohteet_n = []
        for kohde in paikka.kohteet:
            lukema = lukemat.get(kohde.mittari)
            v = _muuttujan_arvo(kohde, lukema, n) if lukema else None
            if v is None:
                continue
            mittari = paikka.mittarit[kohde.mittari]
            marginaali = mittari.marginaali if kohde.muuttuja == "arvo" else None
            kohteet_n.append(pisteyta_kohde(kohde, v, marginaali, lukema.yksikko))
        p = _yhdista(kohteet_n)
        if p is not None:
            tulos.ennuste[n] = p
            tulos.ennusteen_kohteet[n] = kohteet_n
    return tulos


def jarjesta(tulokset: list[PaikkaTulos]) -> list[PaikkaTulos]:
    """Optimijärjestys: pisteet laskevasti (5 pisteen tarkkuudella), tasapelissä
    lähempi paikka ensin. Paikat ilman kaaviota viimeisenä."""
    def avain(t: PaikkaTulos):
        if t.pisteet is None:
            return (1, 0, t.paikka.km_oulusta or 0)
        return (0, -round(t.pisteet / 5), t.paikka.km_oulusta or 0)
    return sorted(tulokset, key=avain)
