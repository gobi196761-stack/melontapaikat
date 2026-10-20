"""Virtaamakaaviot SVG:nä niille mittareille, joille ei ole valmista kaaviokuvaa.

SYKE:n mittareille sivulla linkitetään SYKE:n valmis kaaviokuva. Itse
piirretään:

* Ruotsin mittarit (smhi_svg): SMHI:ltä saadaan vain JSON-dataa. Sininen viiva
  on HydroNu-malli (jälkilaskenta 30 pv taakse, ennuste katkoviivana), mustat
  pisteet havainnot (viimeinen vuorokausi tunnin välein), harmaa alue ja
  magenta viiva saman päivän vaihteluväli ja mediaani eri vuosilta.
* Arviomallin asemat (arvio_svg, esim. Hawa'Ii): SYKE:n kuvassa on mallin
  käyrä, vaikka aseman oma havainto julkaistaan vasta seuraavana päivänä.
  Kuvassa on vain mitatut päiväarvot ja samojen päivien lasketut arviot (näkee,
  miten hyvin malli osui), tämän päivän arvio (syke_data.Arviomalli)
  ja ennuste, joka jatkuu arviosta mallin muutoksen mukaan (kuten
  Kaaviolukema.ennuste_korjattu) 5–95 %:n vaihteluvälin kanssa.

Kummassakin: syaani katkoviiva = tänään, vaakaviivat = tunnusluvut (MQ, MHQ,
MLQ), vihreä alue = paikan laadukkaimman kohteen paras vesi.
"""

from __future__ import annotations

import datetime as dt
import html
import math

import smhi_data
import syke_data

LEVEYS, KORKEUS = 900, 420
VASEN, OIKEA, YLA, ALA = 64, 20, 58, 64
PAIVA_MS = smhi_data.PAIVA_MS
HISTORIA_PAIVIA = 30   # arviomallin kaaviossa mitattuja päiviä taaksepäin (kuten SMHI:n jälkilaskenta)

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


def _ms(paiva: dt.date) -> int:
    return smhi_data._paivan_ms(paiva)


def piirra(otsikko: str, alaotsikko: str, tanaan: dt.date, *,
           malli: dict[dt.date, float] | None = None,
           ennuste: dict[dt.date, float] | None = None,
           ennuste_vali: dict[dt.date, tuple[float, float]] | None = None,
           tausta: dict[dt.date, tuple[float, float, float]] | None = None,
           havainnot: dict[int, float] | None = None,
           havainto_viiva: bool = False,
           arvio: float | None = None,
           aiemmat_arviot: dict[dt.date, float] | None = None,
           tunnus: list[tuple[str, float, str]] | None = None,
           paras: tuple[str, float | None, float | None] | None = None) -> str:
    """Yleinen kaavio. Päiväarvot piirretään päivän keskelle, havainnot (ms -> arvo) aikaleiman kohdalle.

    malli = mallin menneet päivät (yhtenäinen viiva), ennuste = tulevat päivät (katkoviiva,
    jatkuu mallin viimeisestä päivästä tai tämän päivän arviosta), tausta = (min, mediaani, max).
    """
    malli, ennuste, ennuste_vali = malli or {}, ennuste or {}, ennuste_vali or {}
    tausta, havainnot, tunnus = tausta or {}, havainnot or {}, tunnus or []
    aiemmat_arviot = aiemmat_arviot or {}

    # aikaväli mallin, ennusteen ja havaintojen mukaan (vaihteluväli voi kattaa koko vuoden)
    paivat = sorted(set(malli) | set(ennuste)) or sorted(tausta) or [tanaan]
    alku, loppu = min(paivat[0], tanaan), max(paivat[-1], tanaan + dt.timedelta(days=1))
    if havainnot:
        alku = min(alku, smhi_data._paiva(min(havainnot)))
    tausta = {p: t for p, t in tausta.items() if alku <= p <= loppu}

    arvot = list(malli.values()) + list(ennuste.values()) + list(havainnot.values()) \
        + [v for t in tausta.values() for v in t] + [v for t in ennuste_vali.values() for v in t] \
        + list(aiemmat_arviot.values()) + ([arvio] if arvio is not None else [])
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

    ala_ms, yla_ms = _ms(alku), _ms(loppu) + PAIVA_MS
    piirto_l, piirto_k = LEVEYS - VASEN - OIKEA, KORKEUS - YLA - ALA

    def x_ms(ms: float) -> float:
        return VASEN + (ms - ala_ms) / (yla_ms - ala_ms) * piirto_l

    def x(paiva: dt.date) -> float:   # päivän keskikohta (päiväarvo)
        return x_ms(_ms(paiva) + PAIVA_MS / 2)

    def y(v: float) -> float:
        return YLA + (ylin - v) / (ylin - alin) * piirto_k

    def polku(pisteet: list[tuple[float, float]]) -> str:
        return " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py) in enumerate(pisteet))

    def vinonelio(px: float, py: float, r: float, vari: str, ontto: bool = False) -> str:
        tayte = f'fill="#fff" stroke="{vari}" stroke-width="2"' if ontto else f'fill="{vari}"'
        return (f'<path d="M{px:.1f},{py - r:.1f} L{px + r:.1f},{py:.1f} L{px:.1f},{py + r:.1f} '
                f'L{px - r:.1f},{py:.1f} Z" {tayte}/>')

    osat = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LEVEYS} {KORKEUS}" '
            f'font-family="system-ui, Segoe UI, sans-serif" font-size="12">',
            f'<title>{e(otsikko)}</title>',
            f'<rect width="{LEVEYS}" height="{KORKEUS}" fill="#fff"/>',
            f'<text x="{VASEN}" y="22" font-size="16" font-weight="600" fill="#1b1f24">{e(otsikko)}</text>',
            f'<text x="{VASEN}" y="40" fill="#5c6670">{e(alaotsikko)}</text>',
            f'<clipPath id="alue"><rect x="{VASEN}" y="{YLA}" width="{piirto_l}" height="{piirto_k}"/></clipPath>']
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
    # x-akseli: päiväviivat, nimiöt viiden päivän välein (lyhyellä välillä joka toinen)
    vali = 5 if (loppu - alku).days > 20 else 2
    paiva = alku
    while paiva <= loppu:
        px = x_ms(_ms(paiva))
        osat.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#f0f2f4"/>')
        if (paiva - alku).days % vali == 0 or paiva == tanaan:
            osat.append(f'<text x="{x(paiva):.1f}" y="{YLA + piirto_k + 16}" text-anchor="middle" '
                        f'fill="{"#007c91" if paiva == tanaan else "#5c6670"}">{paiva.day}.{paiva.month}.</text>')
        paiva += dt.timedelta(days=1)

    ryhma = ['<g clip-path="url(#alue)">']
    if tausta:
        pv = sorted(tausta)
        ryhma.append(f'<path d="{polku([(x(p), y(tausta[p][2])) for p in pv] + [(x(p), y(tausta[p][0])) for p in reversed(pv)])} Z" '
                     f'fill="#cfd4d9" fill-opacity="0.7"/>')
        ryhma.append(f'<path d="{polku([(x(p), y(tausta[p][1])) for p in pv])}" fill="none" stroke="#d81b9a" stroke-width="2"/>')
    if ennuste_vali:
        pv = sorted(ennuste_vali)
        ryhma.append(f'<path d="{polku([(x(p), y(ennuste_vali[p][1])) for p in pv] + [(x(p), y(ennuste_vali[p][0])) for p in reversed(pv)])} Z" '
                     f'fill="#90caf9" fill-opacity="0.35"/>')
    for nimi, arvo, vari in tunnus_nakyy:
        ryhma.append(f'<line x1="{VASEN}" x2="{VASEN + piirto_l}" y1="{y(arvo):.1f}" y2="{y(arvo):.1f}" '
                     f'stroke="{vari}" stroke-dasharray="2 4" stroke-width="1.5"/>'
                     f'<text x="{VASEN + piirto_l - 4}" y="{y(arvo) - 4:.1f}" text-anchor="end" fill="{vari}">'
                     f'{nimi} {_luku(arvo)}</text>')
    if malli:
        pv = sorted(malli)
        ryhma.append(f'<path d="{polku([(x(p), y(malli[p])) for p in pv])}" fill="none" stroke="#1565c0" stroke-width="2.5"/>')
    if ennuste:
        sarja = dict(ennuste)
        if arvio is not None:   # ennuste jatkuu tämän päivän arviosta
            sarja.setdefault(tanaan, arvio)
        elif malli:             # tai mallin viimeisestä päivästä
            sarja.setdefault(max(malli), malli[max(malli)])
        pv = sorted(sarja)
        ryhma.append(f'<path d="{polku([(x(p), y(sarja[p])) for p in pv])}" fill="none" stroke="#1565c0" '
                     f'stroke-width="2.5" stroke-dasharray="8 5"/>')
    if havainto_viiva and len(havainnot) > 1:
        pisteet = [(x_ms(ms), y(v)) for ms, v in sorted(havainnot.items())]
        if arvio is not None:
            pisteet.append((x(tanaan), y(arvio)))
        ryhma.append(f'<path d="{polku(pisteet)}" fill="none" stroke="#000" stroke-width="1.2"/>')
    for ms, v in sorted(havainnot.items()):
        ryhma.append(vinonelio(x_ms(ms), y(v), 5.5, "#000") if havainto_viiva
                     else f'<circle cx="{x_ms(ms):.1f}" cy="{y(v):.1f}" r="2.6" fill="#000"/>')
    if aiemmat_arviot:   # menneiden päivien arviot: näkee, miten hyvin malli osui havaintoihin
        sarja = dict(aiemmat_arviot)
        if arvio is not None:
            sarja[tanaan] = arvio
        ryhma.append(f'<path d="{polku([(x(p), y(v)) for p, v in sorted(sarja.items())])}" fill="none" '
                     f'stroke="#ef6c00" stroke-width="1.2" stroke-dasharray="3 3"/>')
        for p, v in sorted(aiemmat_arviot.items()):
            ryhma.append(vinonelio(x(p), y(v), 5.5, "#ef6c00", ontto=True))
    tx = x(tanaan)
    ryhma.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#00bcd4" '
                 f'stroke-width="2" stroke-dasharray="6 4"/>')
    if arvio is not None:
        ryhma.append(vinonelio(tx, y(arvio), 7, "#ef6c00"))
        ryhma.append(f'<text x="{tx + 10:.1f}" y="{y(arvio) - 8:.1f}" fill="#ef6c00" font-weight="600">'
                     f'{_luku(arvio)}</text>')
    ryhma.append('</g>')
    osat += ryhma
    osat.append(f'<rect x="{VASEN}" y="{YLA}" width="{piirto_l}" height="{piirto_k}" fill="none" stroke="#9aa4ae"/>')

    # selite
    selite = []
    if malli:
        selite.append(("viiva", "#1565c0", "malli (ennuste katkoviivana)"))
    elif ennuste:
        selite.append(("katko", "#1565c0", "ennuste"))
    if havainnot:
        selite.append(("vino" if havainto_viiva else "piste", "#000", "havainto"))
    if aiemmat_arviot:
        virheet = [abs(v - havainnot[_ms(p) + PAIVA_MS // 2]) for p, v in aiemmat_arviot.items()
                   if _ms(p) + PAIVA_MS // 2 in havainnot]
        teksti = "laskettu arvio" + (f" (keskivirhe {_luku(sum(virheet) / len(virheet))})" if virheet else "")
        selite.append(("onttovino", "#ef6c00", teksti))
    if arvio is not None:
        selite.append(("vino", "#ef6c00", "arvio tänään"))
    if ennuste_vali:
        selite.append(("alue", "#c6e2fb", "ennusteen 5–95 %"))
    if tausta:
        selite += [("alue", "#cfd4d9", "vaihteluväli"), ("viiva", "#d81b9a", "mediaani")]
    selite.append(("katko", "#00bcd4", "tänään"))
    if paras:
        selite.append(("alue", "#a5d6a7", f"paras: {paras[0]}"))
    piilossa = [f"{n} {_luku(a)}" for n, a, v in tunnus if (n, a, v) not in tunnus_nakyy]
    sx, sy = VASEN, KORKEUS - 18
    for laji, vari, teksti in selite:
        if laji == "viiva":
            osat.append(f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2.5"/>')
        elif laji == "katko":
            osat.append(f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2" stroke-dasharray="5 3"/>')
        elif laji == "piste":
            osat.append(f'<circle cx="{sx + 9}" cy="{sy - 4}" r="3" fill="{vari}"/>')
        elif laji in ("vino", "onttovino"):
            osat.append(vinonelio(sx + 9, sy - 4, 5, vari, ontto=laji == "onttovino"))
        else:
            osat.append(f'<rect x="{sx}" y="{sy - 10}" width="18" height="12" fill="{vari}"/>')
        osat.append(f'<text x="{sx + 23}" y="{sy}" fill="#1b1f24">{e(teksti)}</text>')
        sx += 30 + len(teksti) * 6.4
    if piilossa:
        osat.append(f'<text x="{VASEN + piirto_l}" y="{YLA - 6}" text-anchor="end" fill="#5c6670">'
                    f'{e(", ".join(piilossa))} (yli kuvan)</text>')
    osat.append("</svg>")
    return "\n".join(osat)


def smhi_svg(havainto: dict | None, ennuste: dict | None, otsikko: str, nyt: dt.datetime,
             paras: tuple[str, float | None, float | None] | None = None) -> str:
    """Ruotsin mittarin kaavio SMHI:n havainnosta ja HydroNu-pisteen tiedoista."""
    kaavio = (ennuste or {}).get("chartData") or {}

    def sarja(nimi: str) -> dict[dt.date, float]:
        return {smhi_data._paiva(ms): float(v) for ms, v in (kaavio.get(nimi) or {}).get("data") or []
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
    alaotsikko = "Virtaama m³/s · SMHI HydroNu"
    tuotettu = str((ennuste or {}).get("productionTime") or "")
    if len(tuotettu) == 12:
        alaotsikko += (f", ennuste tehty {int(tuotettu[6:8])}.{int(tuotettu[4:6])}. "
                       f"klo {tuotettu[8:10]}.{tuotettu[10:12]} UTC")
    return piirra(otsikko, alaotsikko, smhi_data._suomen_paiva(nyt), malli=sarja("coutHindcast"),
                  ennuste=sarja("coutForecast"), tausta=tausta, havainnot=havainnot,
                  tunnus=tunnus, paras=paras)


def arvio_svg(lukema, ajot: dict[str, dict], asema: str, otsikko: str,
              paras: tuple[str, float | None, float | None] | None = None) -> str:
    """Arviomallin aseman kaavio: mitatut päiväarvot, samojen päivien lasketut arviot,
    tämän päivän arvio ja siitä jatkuva ennuste.

    `lukema` on syke_data.taydenna- ja arvioi_tanaan-funktioilla täydennetty Kaaviolukema,
    `ajot` ajo.json-avain -> luettu ajo.json (aseman oma ja arviomallin syöteasemat).
    """
    ajo = ajot[f"{asema}/ajo.json"]
    tanaan = dt.date.fromisoformat(ajo["ennustepvm_www"])
    havainnot = {}
    hav = ajo.get("qhav") or {}
    for i in range(len(hav.get("lst") or [])):
        p = dt.date.fromisoformat(hav["ensim_pvm"]) + dt.timedelta(days=i)
        v = syke_data._arvo(hav, p)
        if v is not None and tanaan - dt.timedelta(days=HISTORIA_PAIVIA) <= p < tanaan:
            havainnot[_ms(p) + PAIVA_MS // 2] = v
    aiemmat = {p: v for p in (smhi_data._paiva(ms) for ms in havainnot)
               if (v := syke_data.arvioi_paiva(asema, ajot, p)) is not None}
    arvio = lukema.arvo
    ennuste = {tanaan + dt.timedelta(days=n): v for n in lukema.ennuste
               if (v := lukema.ennuste_korjattu(n)) is not None}
    # 5–95 %:n vaihteluväli siirretään samalla erotuksella kuin ennuste (arvio − malli)
    siirto = arvio - lukema.malli if arvio is not None and lukema.malli is not None else 0.0
    vali = {}
    for p in ennuste:
        ala, yla = (syke_data._arvo(ajo.get(n) or {}, p) for n in ("qinlask_5", "qinlask_95"))
        if ala is not None and yla is not None:
            vali[p] = (ala + siirto, yla + siirto)
    tunnus = [(nimi, lukema.tunnusluvut[nimi], vari) for nimi, vari in
              (("MHQ", "#c62828"), ("MQ", "#2e7d32"), ("MNQ", "#ef6c00")) if nimi in lukema.tunnusluvut]
    alaotsikko = (f"Virtaama m³/s · havainnot ja ennuste SYKE, tämän päivän arvo: {lukema.lahde} · "
                  f"ennuste tehty {tanaan.day}.{tanaan.month}.")
    return piirra(otsikko, alaotsikko, tanaan, ennuste=ennuste, ennuste_vali=vali, havainnot=havainnot,
                  havainto_viiva=True, arvio=arvio, aiemmat_arviot=aiemmat, tunnus=tunnus, paras=paras)
