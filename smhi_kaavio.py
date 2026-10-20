"""SMHI:n havainnosta ja HydroNu-ennusteesta SVG-kaavio, SYKE:n kaavioiden tapaan.

SYKE:n mittareille sivulla linkitetään SYKE:n valmis kaaviokuva; SMHI:ltä
saadaan vain JSON-dataa, joten kuva piirretään itse samoilla merkinnöillä:

* sininen viiva: HydroNu-malli (jälkilaskenta 30 pv taakse, ennuste katkoviivana)
* harmaa alue ja magenta viiva: saman päivän vaihteluväli ja mediaani eri vuosilta
* mustat pisteet: SMHI:n havainnot (viimeinen vuorokausi, tunnin välein)
* syaani katkoviiva: tänään
* vaakaviivat: MQ, MHQ ja MLQ (mallin tunnusluvut), vihreä alue: paikan paras vesi
"""

from __future__ import annotations

import datetime as dt
import html
import math

import smhi_data

LEVEYS, KORKEUS = 900, 420
VASEN, OIKEA, YLA, ALA = 64, 20, 58, 64

e = html.escape


def _asteikko(alin: float, ylin: float, tikkeja: int = 6) -> list[float]:
    """Tasaiset tikkiarvot (1, 2, 2.5 tai 5 × 10^n) välille alin..ylin."""
    vali = (ylin - alin) / tikkeja or 1.0
    potenssi = 10 ** math.floor(math.log10(vali))
    askel = next(k * potenssi for k in (1, 2, 2.5, 5, 10) if k * potenssi >= vali)
    ensimmainen = math.floor(alin / askel) * askel
    return [ensimmainen + i * askel for i in range(int((ylin - ensimmainen) / askel) + 2)]


def _luku(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}".rstrip("0").rstrip(".")


def svg(havainto: dict | None, ennuste: dict | None, otsikko: str, nyt: dt.datetime,
        paras: tuple[str, float | None, float | None] | None = None) -> str:
    """Kaavio SVG-tekstinä. paras = (kohteen nimi, alaraja, yläraja) piirretään vihreänä alueena."""
    kaavio = (ennuste or {}).get("chartData") or {}
    tanaan = smhi_data._suomen_paiva(nyt)
    jalki = {smhi_data._paiva(ms): float(v) for ms, v in (kaavio.get("coutHindcast") or {}).get("data") or []
             if isinstance(v, (int, float))}
    tuleva = {smhi_data._paiva(ms): float(v) for ms, v in (kaavio.get("coutForecast") or {}).get("data") or []
              if isinstance(v, (int, float))}
    tausta = {}
    for ms, arvot in kaavio.get("background") or []:
        arvot = sorted(float(v) for v in arvot if isinstance(v, (int, float)))
        if arvot:
            tausta[smhi_data._paiva(ms)] = (arvot[0], arvot[len(arvot) // 2], arvot[-1])
    # havainnot tunnin välein (15 min arvot ovat kaavion mittakaavassa päällekkäin)
    havainnot = {}
    for rivi in (havainto or {}).get("value") or []:
        if isinstance(rivi.get("value"), (int, float)) and isinstance(rivi.get("date"), int):
            havainnot[rivi["date"] // 3_600_000 * 3_600_000] = float(rivi["value"])
    tunnus = [(nimi, float(kaavio[k]), vari) for nimi, k, vari in
              (("MHQ", "mhq", "#c62828"), ("MQ", "mq", "#2e7d32"), ("MLQ", "mlq", "#ef6c00"))
              if isinstance(kaavio.get(k), (int, float))]

    # aikaväli mallin mukaan (vaihteluväli voi kattaa koko vuoden)
    paivat = sorted(set(jalki) | set(tuleva)) or sorted(tausta) or [tanaan]
    alku, loppu = min(paivat[0], tanaan), max(paivat[-1], tanaan + dt.timedelta(days=1))
    if havainnot:
        alku = min(alku, smhi_data._paiva(min(havainnot)))
    tausta = {p: t for p, t in tausta.items() if alku <= p <= loppu}
    arvot = list(jalki.values()) + list(tuleva.values()) + list(havainnot.values()) \
        + [v for t in tausta.values() for v in t]
    if not arvot:
        arvot = [0.0, 1.0]
    datan_yla = max(arvot)
    # tunnusluku piirretään, jos se mahtuu järkevästi kuvaan (MHQ voi olla moninkertainen)
    tunnus_nakyy = [t for t in tunnus if t[1] <= datan_yla * 1.6]
    rajat = [r for r in (paras[1:] if paras else ()) if r is not None and r <= datan_yla * 1.6]
    ylin = max([datan_yla] + [t[1] for t in tunnus_nakyy] + rajat) * 1.08
    alin = max(0.0, min(arvot + [t[1] for t in tunnus_nakyy] + rajat) * 0.9)
    tikit = [t for t in _asteikko(alin, ylin) if t >= 0]
    alin, ylin = tikit[0], max(tikit[-1], ylin)

    ala_ms = smhi_data._paivan_ms(alku)
    yla_ms = smhi_data._paivan_ms(loppu) + smhi_data.PAIVA_MS
    piirto_l, piirto_k = LEVEYS - VASEN - OIKEA, KORKEUS - YLA - ALA

    def x_ms(ms: float) -> float:
        return VASEN + (ms - ala_ms) / (yla_ms - ala_ms) * piirto_l

    def x(paiva: dt.date) -> float:   # päivän keskikohta (mallin päiväarvo)
        return x_ms(smhi_data._paivan_ms(paiva) + smhi_data.PAIVA_MS / 2)

    def y(v: float) -> float:
        return YLA + (ylin - v) / (ylin - alin) * piirto_k

    def polku(pisteet: list[tuple[float, float]]) -> str:
        return " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py) in enumerate(pisteet))

    osat = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LEVEYS} {KORKEUS}" '
            f'font-family="system-ui, Segoe UI, sans-serif" font-size="12">',
            f'<title>{e(otsikko)}</title>',
            f'<rect width="{LEVEYS}" height="{KORKEUS}" fill="#fff"/>',
            f'<text x="{VASEN}" y="22" font-size="16" font-weight="600" fill="#1b1f24">{e(otsikko)}</text>']
    tuotettu = str((ennuste or {}).get("productionTime") or "")
    if len(tuotettu) == 12:
        osat.append(f'<text x="{VASEN}" y="40" fill="#5c6670">Virtaama m³/s · SMHI HydroNu, ennuste tehty '
                    f'{int(tuotettu[6:8])}.{int(tuotettu[4:6])}. klo {tuotettu[8:10]}.{tuotettu[10:12]} UTC</text>')

    # leikkaus piirtoalueeseen
    osat.append(f'<clipPath id="alue"><rect x="{VASEN}" y="{YLA}" width="{piirto_l}" height="{piirto_k}"/></clipPath>')
    if paras and (paras[1] is not None or paras[2] is not None):
        y1 = y(min(paras[2], ylin)) if paras[2] is not None else YLA
        y2 = y(max(paras[1], alin)) if paras[1] is not None else YLA + piirto_k
        if y2 > y1:
            osat.append(f'<rect x="{VASEN}" y="{y1:.1f}" width="{piirto_l}" height="{y2 - y1:.1f}" '
                        f'fill="#4caf50" fill-opacity="0.13"/>')
    # ruudukko ja y-akseli
    for t in tikit:
        if alin <= t <= ylin:
            osat.append(f'<line x1="{VASEN}" x2="{VASEN + piirto_l}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#e3e7eb"/>'
                        f'<text x="{VASEN - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="#5c6670">{_luku(t)}</text>')
    # x-akseli: päiväviivat, nimiöt viiden päivän välein
    paiva = alku
    while paiva <= loppu:
        px = x_ms(smhi_data._paivan_ms(paiva))
        osat.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#f0f2f4"/>')
        if (paiva - alku).days % 5 == 0 or paiva == tanaan:
            osat.append(f'<text x="{px:.1f}" y="{YLA + piirto_k + 16}" text-anchor="middle" '
                        f'fill="{"#007c91" if paiva == tanaan else "#5c6670"}">{paiva.day}.{paiva.month}.</text>')
        paiva += dt.timedelta(days=1)

    ryhma = ['<g clip-path="url(#alue)">']
    if tausta:
        pv = sorted(tausta)
        ryhma.append(f'<path d="{polku([(x(p), y(tausta[p][2])) for p in pv] + [(x(p), y(tausta[p][0])) for p in reversed(pv)])} Z" '
                     f'fill="#cfd4d9" fill-opacity="0.7"/>')
        ryhma.append(f'<path d="{polku([(x(p), y(tausta[p][1])) for p in pv])}" fill="none" stroke="#d81b9a" stroke-width="2"/>')
    for nimi, arvo, vari in tunnus_nakyy:
        ryhma.append(f'<line x1="{VASEN}" x2="{VASEN + piirto_l}" y1="{y(arvo):.1f}" y2="{y(arvo):.1f}" '
                     f'stroke="{vari}" stroke-dasharray="2 4" stroke-width="1.5"/>'
                     f'<text x="{VASEN + piirto_l - 4}" y="{y(arvo) - 4:.1f}" text-anchor="end" fill="{vari}">'
                     f'{nimi} {_luku(arvo)}</text>')
    if jalki:
        pv = sorted(jalki)
        ryhma.append(f'<path d="{polku([(x(p), y(jalki[p])) for p in pv])}" fill="none" stroke="#1565c0" stroke-width="2.5"/>')
    if tuleva:
        pv = sorted(tuleva)
        if jalki:   # ennuste jatkuu jälkilaskennan viimeisestä päivästä
            pv = [max(jalki)] + pv
        sarja = {**jalki, **tuleva}
        ryhma.append(f'<path d="{polku([(x(p), y(sarja[p])) for p in pv])}" fill="none" stroke="#1565c0" '
                     f'stroke-width="2.5" stroke-dasharray="8 5"/>')
    for ms, v in sorted(havainnot.items()):
        ryhma.append(f'<circle cx="{x_ms(ms):.1f}" cy="{y(v):.1f}" r="2.6" fill="#000"/>')
    tx = x_ms(smhi_data._paivan_ms(tanaan) + smhi_data.PAIVA_MS / 2)
    ryhma.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#00bcd4" '
                 f'stroke-width="2" stroke-dasharray="6 4"/>')
    ryhma.append('</g>')
    osat += ryhma
    osat.append(f'<rect x="{VASEN}" y="{YLA}" width="{piirto_l}" height="{piirto_k}" fill="none" stroke="#9aa4ae"/>')

    # selite
    selite = [("viiva", "#1565c0", "malli (ennuste katkoviivana)"), ("piste", "#000", "havainto"),
              ("alue", "#cfd4d9", "vaihteluväli"), ("viiva", "#d81b9a", "mediaani"),
              ("katko", "#00bcd4", "tänään")]
    if paras:
        selite.append(("alue", "#a5d6a7", f"paras: {paras[0]}"))
    piilossa = [f"{n} {_luku(a)}" for n, a, _ in tunnus if (n, a, _) not in tunnus_nakyy]
    sx, sy = VASEN, KORKEUS - 18
    for laji, vari, teksti in selite:
        if laji == "viiva":
            osat.append(f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2.5"/>')
        elif laji == "katko":
            osat.append(f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2" stroke-dasharray="5 3"/>')
        elif laji == "piste":
            osat.append(f'<circle cx="{sx + 9}" cy="{sy - 4}" r="3" fill="{vari}"/>')
        else:
            osat.append(f'<rect x="{sx}" y="{sy - 10}" width="18" height="12" fill="{vari}"/>')
        osat.append(f'<text x="{sx + 23}" y="{sy}" fill="#1b1f24">{e(teksti)}</text>')
        sx += 30 + len(teksti) * 6.4
    if piilossa:
        osat.append(f'<text x="{VASEN + piirto_l}" y="{YLA - 6}" text-anchor="end" fill="#5c6670">'
                    f'{e(", ".join(piilossa))} (yli kuvan)</text>')
    osat.append("</svg>")
    return "\n".join(osat)
