"""Mittarikaaviot SVG:nä: sivun mittarilinkit vievät näihin SYKE:n ja SMHI:n kuvien sijaan.

* SYKE:n mittarit (syke_svg): ajo.jsonin mitatut päiväarvot, mallin simuloitu
  historia, ennuste ja sen 5–95 %:n vaihteluväli – ei SYKE:n kuvan muita
  merkintöjä (vaihteluväli eri vuosilta, tunnusluvut ym.).
* Ruotsin mittarit (smhi_svg): SMHI:ltä saadaan vain JSON-dataa. Sininen viiva
  on HydroNu-malli (jälkilaskenta 30 pv taakse, ennuste katkoviivana), mustat
  pisteet havainnot (viimeinen vuorokausi tunnin välein), harmaa alue ja
  magenta viiva saman päivän vaihteluväli ja mediaani eri vuosilta, vaakaviivat
  tunnusluvut (MQ, MHQ, MLQ).
* Arviomallin asemat (arvio_svg, esim. Hawa'Ii): aseman oma havainto julkaistaan
  vasta seuraavana päivänä. Kuvassa on vain mitatut päiväarvot ja samojen päivien
  lasketut arviot (näkee, miten hyvin malli osui), tämän päivän arvio
  (syke_data.Arviomalli) ja ennuste, joka jatkuu arviosta mallin muutoksen mukaan
  (kuten Kaaviolukema.ennuste_korjattu) 5–95 %:n vaihteluvälin kanssa.

Kaikissa: syaani katkoviiva = tänään, vihreät alueet = paikan kohteiden rajat
(vaalea = toimii, tummempi = parhaimmillaan) kohteen nimellä.
"""

from __future__ import annotations

import datetime as dt
import html
import math

import kielet
import smhi_data
import syke_data

LEVEYS, KORKEUS = 900, 440
VASEN, OIKEA, YLA, ALA = 64, 20, 58, 84
PAIVA_MS = smhi_data.PAIVA_MS
HISTORIA_PAIVIA = 10   # kaavio alkaa näin monta päivää ennen tätä päivää

e = html.escape

# kohteen rajat: (nimi, toimii (ala, ylä), paras (ala, ylä)); None = avoin raja
Alue = tuple[str, tuple[float | None, float | None], tuple[float | None, float | None]]


def _asteikko(alin: float, ylin: float, tikkeja: int = 6) -> list[float]:
    """Tasaiset tikkiarvot (1, 2, 2.5 tai 5 × 10^n) välille alin..ylin."""
    vali = (ylin - alin) / tikkeja or 1.0
    potenssi = 10 ** math.floor(math.log10(vali))
    askel = next(k * potenssi for k in (1, 2, 2.5, 5, 10) if k * potenssi >= vali)
    ensimmainen = math.floor(alin / askel + 1e-9) * askel
    return [ensimmainen + i * askel for i in range(int((ylin - ensimmainen) / askel + 1e-9) + 2)]


def _luku(v: float, metreja: bool = False) -> str:
    if metreja:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}".rstrip("0").rstrip(".")


def _ms(paiva: dt.date) -> int:
    return smhi_data._paivan_ms(paiva)


def piirra(otsikko: str, alaotsikko: str, tanaan: dt.date, *,
           yksikko: str = "m3/s",
           malli: dict[dt.date, float] | None = None,
           ennuste: dict[dt.date, float] | None = None,
           ennuste_vali: dict[dt.date, tuple[float, float]] | None = None,
           tausta: dict[dt.date, tuple[float, float, float]] | None = None,
           havainnot: dict[int, float] | None = None,
           havainto_viiva: bool = False,
           arvio: float | None = None,
           aiemmat_arviot: dict[dt.date, float] | None = None,
           paivan_arvo: tuple[float, str] | None = None,
           tunnus: list[tuple[str, float, str]] | None = None,
           alueet: list[Alue] | None = None,
           kieli: str = "fi") -> str:
    """Yleinen kaavio. Päiväarvot piirretään päivän keskelle, havainnot (ms -> arvo) aikaleiman kohdalle.

    malli = mallin menneet päivät (yhtenäinen viiva), ennuste = tulevat päivät (katkoviiva,
    jatkuu mallin viimeisestä päivästä tai tämän päivän arviosta), tausta = (min, mediaani, max),
    paivan_arvo = (tämän päivän arvo, lähde) merkitään lukemana ennustetta muuttamatta.
    """
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    malli, ennuste, ennuste_vali = malli or {}, ennuste or {}, ennuste_vali or {}
    tausta, havainnot, tunnus = tausta or {}, havainnot or {}, tunnus or []
    aiemmat_arviot, alueet = aiemmat_arviot or {}, alueet or []
    metreja = yksikko == "m"

    def luku(v: float) -> str:
        return _luku(v, metreja)

    # aikaväli mallin, ennusteen ja havaintojen mukaan (vaihteluväli voi kattaa koko vuoden)
    paivat = sorted(set(malli) | set(ennuste)) or sorted(tausta) or [tanaan]
    alku, loppu = min(paivat[0], tanaan), max(paivat[-1], tanaan + dt.timedelta(days=1))
    if havainnot:
        alku = min(alku, smhi_data._paiva(min(havainnot)))
    # historiaa enintään HISTORIA_PAIVIA päivää (SMHI:n jälkilaskenta ulottuu 30 päivään)
    alku = max(alku, tanaan - dt.timedelta(days=HISTORIA_PAIVIA))
    malli = {p: v for p, v in malli.items() if p >= alku}
    havainnot = {ms: v for ms, v in havainnot.items() if ms >= _ms(alku)}
    aiemmat_arviot = {p: v for p, v in aiemmat_arviot.items() if p >= alku}
    tausta = {p: t for p, t in tausta.items() if alku <= p <= loppu}

    arvot = list(malli.values()) + list(ennuste.values()) + list(havainnot.values()) \
        + [v for t in tausta.values() for v in t] + [v for t in ennuste_vali.values() for v in t] \
        + list(aiemmat_arviot.values()) + ([arvio] if arvio is not None else []) \
        + ([paivan_arvo[0]] if paivan_arvo else [])
    if not arvot:
        arvot = [0.0, 1.0]
    datan_ala, datan_yla = min(arvot), max(arvot)
    # Raja tai tunnusluku otetaan asteikkoon, jos se on lähellä dataa (MHQ voi olla moninkertainen,
    # vedenkorkeudessa kohteiden rajat voivat olla metrejä ylempänä)
    vali = max(datan_yla - datan_ala, 0.4 if metreja else 0.3 * datan_yla)
    lahella = lambda v: datan_ala - vali <= v <= datan_yla + vali   # noqa: E731
    tunnus_nakyy = [t for t in tunnus if lahella(t[1])]
    rajat = [r for _, toimii, paras in alueet for r in (*toimii, *paras) if r is not None and lahella(r)]
    ala = min([datan_ala] + [t[1] for t in tunnus_nakyy] + rajat)
    yla = max([datan_yla] + [t[1] for t in tunnus_nakyy] + rajat)
    vara = (yla - ala) * 0.08 or (0.05 if metreja else 1.0)
    ala, yla = ala - vara, yla + vara
    if not metreja:
        ala = max(0.0, ala)
    tikit = _asteikko(ala, yla)
    tikit = [t for t in tikit if t >= ala - 1e-9 or t == tikit[0]]
    alin, ylin = min(tikit[0], ala), max(tikit[-1], yla)

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

    def kaista(raja: tuple[float | None, float | None]) -> tuple[float, float] | None:
        """Rajojen (ala, ylä) pikselit piirtoalueella; None, jos kaista on kokonaan näkyvän ulkopuolella."""
        a = alin if raja[0] is None else max(raja[0], alin)
        b = ylin if raja[1] is None else min(raja[1], ylin)
        return (y(b), y(a)) if b > a else None

    osat = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LEVEYS} {KORKEUS}" '
            f'font-family="system-ui, Segoe UI, sans-serif" font-size="12">',
            f'<title>{e(otsikko)}</title>',
            f'<rect width="{LEVEYS}" height="{KORKEUS}" fill="#fff"/>',
            f'<text x="{VASEN}" y="22" font-size="16" font-weight="600" fill="#1b1f24">{e(otsikko)}</text>',
            f'<text x="{VASEN}" y="40" fill="#5c6670">{e(alaotsikko)}</text>',
            f'<clipPath id="alue"><rect x="{VASEN}" y="{YLA}" width="{piirto_l}" height="{piirto_k}"/></clipPath>']
    # kohteiden alueet: vaalea = toimii, tummempi = parhaimmillaan
    nimioit, reuna_yla, reuna_ala = [], [], []
    for nimi, toimii, paras in alueet:
        k1, k2 = kaista(toimii), kaista(paras)
        for k, vari, peitto in ((k1, "#81c784", 0.18), (k2, "#43a047", 0.22)):
            if k:
                osat.append(f'<rect x="{VASEN}" y="{k[0]:.1f}" width="{piirto_l}" height="{k[1] - k[0]:.1f}" '
                            f'fill="{vari}" fill-opacity="{peitto}"/>')
        if k2 or k1:
            nimioit.append([(k2 or k1)[0] + 13, nimi, toimii, paras])
        else:   # alue kokonaan asteikon ulkopuolella: nuoli kaavion reunaan
            yli = toimii[0] is not None and toimii[0] >= ylin
            (reuna_yla if yli else reuna_ala).append((nimi, toimii, paras))
    # ruudukko ja y-akseli
    for t in tikit:
        if alin <= t <= ylin:
            osat.append(f'<line x1="{VASEN}" x2="{VASEN + piirto_l}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#e3e7eb"/>'
                        f'<text x="{VASEN - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="#5c6670">{luku(t)}</text>')
    # x-akseli: päiväviivat, nimiöt viiden päivän välein (lyhyellä välillä joka toinen)
    askel = 5 if (loppu - alku).days > 20 else 2
    paiva = alku
    while paiva <= loppu:
        px = x_ms(_ms(paiva))
        osat.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#f0f2f4"/>')
        if (paiva - alku).days % askel == 0 or paiva == tanaan:
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
                     f'fill="#90caf9" fill-opacity="0.45"/>')
    for nimi, arvo, vari in tunnus_nakyy:
        ryhma.append(f'<line x1="{VASEN}" x2="{VASEN + piirto_l}" y1="{y(arvo):.1f}" y2="{y(arvo):.1f}" '
                     f'stroke="{vari}" stroke-dasharray="2 4" stroke-width="1.5"/>'
                     f'<text x="{VASEN + piirto_l - 4}" y="{y(arvo) - 4:.1f}" text-anchor="end" fill="{vari}">'
                     f'{nimi} {luku(arvo)}</text>')
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
    if aiemmat_arviot:   # menneiden päivien arviot: näkee, miten hyvin malli osui havaintoihin
        sarja = dict(aiemmat_arviot)
        if arvio is not None:
            sarja[tanaan] = arvio
        ryhma.append(f'<path d="{polku([(x(p), y(v)) for p, v in sorted(sarja.items())])}" fill="none" '
                     f'stroke="#ef6c00" stroke-width="1.2" stroke-dasharray="3 3"/>')
        for p, v in sorted(aiemmat_arviot.items()):
            ryhma.append(vinonelio(x(p), y(v), 5.5, "#ef6c00", ontto=True))
    for ms, v in sorted(havainnot.items()):
        ryhma.append(vinonelio(x_ms(ms), y(v), 5.5, "#000") if havainto_viiva
                     else f'<circle cx="{x_ms(ms):.1f}" cy="{y(v):.1f}" r="2.6" fill="#000"/>')
    tx = x(tanaan)
    ryhma.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#00bcd4" '
                 f'stroke-width="2" stroke-dasharray="6 4"/>')
    lukema = arvio if arvio is not None else paivan_arvo[0] if paivan_arvo else None
    if lukema is not None:   # tämän päivän lukema numerona, kuten Hawa'Iin arvio
        ryhma.append(vinonelio(tx, y(lukema), 7, "#ef6c00"))
        ryhma.append(f'<text x="{tx + 10:.1f}" y="{y(lukema) - 8:.1f}" fill="#ef6c00" font-weight="600" '
                     f'stroke="#fff" stroke-width="3" paint-order="stroke">{luku(lukema)}</text>')
    ryhma.append('</g>')
    osat += ryhma
    # alueiden selitykset: kohteen nimi ja rajat alueen yläreunassa, päällekkäiset siirretään alemmas
    edellinen = YLA
    def rajat_teksti(toimii, paras) -> str:
        """Yleissääntö kaikille alueille: toiminta-alueen rajat, paras alue suluissa, jos se on eri."""
        def rajat(raja) -> str:
            if raja[0] is None and raja[1] is None:
                return _t("kaikilla vesillä")
            return "–".join("" if r is None else luku(r) for r in raja)
        teksti = rajat(toimii)
        if paras != toimii and any(r is not None for r in paras):
            teksti += f" ({_t('paras')} {rajat(paras)})"
        return teksti

    for ny, nimi, toimii, paras in sorted(nimioit):
        ny = max(ny, edellinen + 14)
        if ny > YLA + piirto_k - 4:
            break
        edellinen = ny
        osat.append(f'<text x="{VASEN + 6}" y="{ny:.1f}" fill="#1b5e20" font-size="11.5" font-weight="600" '
                    f'stroke="#fff" stroke-width="3" paint-order="stroke">{e(nimi)} {rajat_teksti(toimii, paras)}</text>')
    # asteikon ulkopuoliset alueet oikeaan reunaan: ↑ yläpuolella, ↓ alapuolella
    # (teksti: toiminta-alueen rajat, paras alue suluissa, jos se on eri)
    reunat = [(YLA + 14 + 14 * i, "↑", *a) for i, a in enumerate(sorted(reuna_yla, key=lambda a: -(a[1][0] or 0)))]
    reunat += [(YLA + piirto_k - 7 - 14 * i, "↓", *a)
               for i, a in enumerate(sorted(reuna_ala, key=lambda a: a[1][1] if a[1][1] is not None else 0))]
    for ny, nuoli, nimi, toimii, paras in reunat:
        osat.append(f'<text x="{VASEN + piirto_l - 6}" y="{ny:.1f}" text-anchor="end" fill="#1b5e20" '
                    f'font-size="11.5" font-weight="600" stroke="#fff" stroke-width="3" paint-order="stroke">'
                    f'{nuoli} {e(nimi)} {rajat_teksti(toimii, paras)}</text>')
    osat.append(f'<rect x="{VASEN}" y="{YLA}" width="{piirto_l}" height="{piirto_k}" fill="none" stroke="#9aa4ae"/>')

    # selite (rivittyy)
    selite = []
    if malli:
        selite.append(("viiva", "#1565c0", _t("malli (ennuste katkoviivana)")))
    elif ennuste:
        selite.append(("katko", "#1565c0", _t("ennuste")))
    if havainnot:
        selite.append(("vino" if havainto_viiva else "piste", "#000", _t("havainto")))
    if aiemmat_arviot:
        virheet = [abs(v - havainnot[_ms(p) + PAIVA_MS // 2]) for p, v in aiemmat_arviot.items()
                   if _ms(p) + PAIVA_MS // 2 in havainnot]
        teksti = _t("laskettu arvio") + (f" ({_t('keskivirhe')} {luku(sum(virheet) / len(virheet))})" if virheet else "")
        selite.append(("onttovino", "#ef6c00", teksti))
    if arvio is not None:
        selite.append(("vino", "#ef6c00", _t("arvio tänään")))
    elif paivan_arvo:
        selite.append(("vino", "#ef6c00", f"{_t('tänään')}: {luku(paivan_arvo[0])} ({_t(paivan_arvo[1])})"))
    if ennuste_vali:
        selite.append(("alue", "#bcdcf7", _t("ennusteen 5–95 %")))
    if tausta:
        selite += [("alue", "#cfd4d9", _t("vaihteluväli")), ("viiva", "#d81b9a", _t("mediaani"))]
    selite.append(("katko", "#00bcd4", _t("tänään")))
    if alueet:
        selite += [("alue", "#d5ecd6", _t("kohde toimii")), ("alue", "#a9d5aa", _t("kohde parhaimmillaan"))]
    piilossa = [f"{n} {luku(a)}" for n, a, v in tunnus if (n, a, v) not in tunnus_nakyy]
    sx, sy = VASEN, YLA + piirto_k + 40
    for laji, vari, teksti in selite:
        leveys = 30 + len(teksti) * 6.4
        if sx + leveys > LEVEYS - OIKEA and sx > VASEN:
            sx, sy = VASEN, sy + 18
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
        sx += leveys
    if piilossa:
        osat.append(f'<text x="{VASEN + piirto_l}" y="{YLA - 6}" text-anchor="end" fill="#5c6670">'
                    f'{e(", ".join(piilossa))} ({_t("yli kuvan")})</text>')
    osat.append("</svg>")
    return "\n".join(osat)


def smhi_svg(havainto: dict | None, ennuste: dict | None, otsikko: str, nyt: dt.datetime,
             alueet: list[Alue] | None = None, kieli: str = "fi") -> str:
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
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    alaotsikko = _t("Virtaama m³/s") + " · SMHI HydroNu"
    tuotettu = str((ennuste or {}).get("productionTime") or "")
    if len(tuotettu) == 12:
        alaotsikko += (f", {_t('ennuste tehty')} {int(tuotettu[6:8])}.{int(tuotettu[4:6])}. "
                       f"{_t('klo')} {tuotettu[8:10]}.{tuotettu[10:12]} UTC")
    # tämän päivän lukema: tuorein havainto
    tuorein = smhi_data.tuorein_havainto(havainto) if havainto else None
    return piirra(otsikko, alaotsikko, smhi_data._suomen_paiva(nyt), malli=sarja("coutHindcast"),
                  ennuste=sarja("coutForecast"), tausta=tausta, havainnot=havainnot,
                  paivan_arvo=(tuorein[0], "havainto") if tuorein else None,
                  tunnus=tunnus, alueet=alueet, kieli=kieli)


def _paivasarja(sarja: dict | None, alku: dt.date, loppu: dt.date) -> dict[dt.date, float]:
    """ajo.jsonin sarjan päiväarvot väliltä alku..loppu (molemmat mukaan)."""
    tulos = {}
    p = alku
    while sarja and p <= loppu:
        v = syke_data._arvo(sarja, p)
        if v is not None:
            tulos[p] = v
        p += dt.timedelta(days=1)
    return tulos


def syke_svg(ajo: dict, kaavio: str, otsikko: str, alueet: list[Alue] | None = None,
             kieli: str = "fi") -> str | None:
    """SYKE:n mittarin kaavio ajo.jsonista: mitatut päiväarvot, mallin simuloitu historia,
    ennuste ja sen 5–95 %:n vaihteluväli. None, jos kaavion suuretta ei ole ajo.jsonissa."""
    sarjat = syke_data._sarjat(kaavio)
    if not sarjat or "ennustepvm_www" not in ajo:
        return None
    hav_nimi, malli_nimi = sarjat
    tanaan = dt.date.fromisoformat(ajo["ennustepvm_www"])
    alku = tanaan - dt.timedelta(days=HISTORIA_PAIVIA)
    malli = _paivasarja(ajo.get(malli_nimi), alku, tanaan + dt.timedelta(days=syke_data.ENNUSTE_PAIVIA))
    if not malli:
        return None
    ala_nimi, yla_nimi = (malli_nimi.removesuffix("_ka") + p for p in ("_5", "_95"))
    ala, yla = (_paivasarja(ajo.get(n), tanaan, tanaan + dt.timedelta(days=syke_data.ENNUSTE_PAIVIA))
                for n in (ala_nimi, yla_nimi))
    havainnot = {_ms(p) + PAIVA_MS // 2: v for p, v in _paivasarja(ajo.get(hav_nimi), alku, tanaan).items()}
    metreja = hav_nimi == "whav"
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    alaotsikko = ((f"{_t('Vedenkorkeus m')} ({ajo['w1nolla']})" if metreja and ajo.get("w1nolla") else
                   _t("Vedenkorkeus m") if metreja else _t("Virtaama m³/s"))
                  + f" · {_t('SYKE:n vesistömalli')}, {_t('ennuste tehty')} {tanaan.day}.{tanaan.month}.")
    # tämän päivän lukema: tämän päivän havainto, muuten mallin arvo (kuten Kaaviolukema.arvo)
    havaittu = syke_data._arvo(ajo.get(hav_nimi) or {}, tanaan)
    paivan_arvo = (havaittu, "havainto") if havaittu is not None else \
        (malli[tanaan], "malli") if tanaan in malli else None
    return piirra(otsikko, alaotsikko, tanaan, yksikko="m" if metreja else "m3/s", kieli=kieli,
                  paivan_arvo=paivan_arvo,
                  malli={p: v for p, v in malli.items() if p <= tanaan},
                  ennuste={p: v for p, v in malli.items() if p > tanaan},
                  ennuste_vali={p: (ala[p], yla[p]) for p in ala if p in yla and p >= tanaan},
                  havainnot=havainnot, havainto_viiva=True, alueet=alueet)


def kuva_svg(sarjat, tanaan: dt.date, otsikko: str, yksikko: str, alueet: list[Alue] | None = None,
             kieli: str = "fi") -> str:
    """Kaavio SYKE:n kaaviokuvasta luetuista sarjoista (syke_kaavio.Kaaviosarjat), kun ajo.jsonissa
    ei ole kaavion suuretta (esim. järven tulovirtaama): havainnot, simuloitu historia, ennuste
    ja ennusteen vaihteluväli kuvan keltaisesta alueesta."""
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    paiva = lambda n: tanaan + dt.timedelta(days=n)   # noqa: E731
    metreja = yksikko == "m"
    havainnot = {_ms(paiva(n)) + PAIVA_MS // 2: float(v) for n, v in sarjat.havainnot.items()}
    if 0 in sarjat.havainnot:
        paivan_arvo = (float(sarjat.havainnot[0]), "havainto")
    elif 0 in sarjat.malli:
        paivan_arvo = (float(sarjat.malli[0]), "malli")
    else:
        paivan_arvo = None
    alaotsikko = (f"{_t('Vedenkorkeus m') if metreja else _t('Virtaama m³/s')} · "
                  f"{_t('luettu SYKE:n kaaviokuvasta')}, {_t('ennuste tehty')} {tanaan.day}.{tanaan.month}.")
    return piirra(otsikko, alaotsikko, tanaan, yksikko=yksikko, kieli=kieli,
                  malli={paiva(n): float(v) for n, v in sarjat.malli.items() if n <= 0},
                  ennuste={paiva(n): float(v) for n, v in sarjat.malli.items() if n > 0},
                  ennuste_vali={paiva(n): (float(a), float(b)) for n, (a, b) in sarjat.vali.items()},
                  havainnot=havainnot, havainto_viiva=True, paivan_arvo=paivan_arvo, alueet=alueet)


def arvio_svg(lukema, ajot: dict[str, dict], asema: str, otsikko: str, alueet: list[Alue] | None = None,
              kieli: str = "fi") -> str:
    """Arviomallin aseman kaavio: mitatut päiväarvot, samojen päivien lasketut arviot,
    tämän päivän arvio ja siitä jatkuva ennuste.

    `lukema` on syke_data.taydenna- ja arvioi_tanaan-funktioilla täydennetty Kaaviolukema,
    `ajot` ajo.json-avain -> luettu ajo.json (aseman oma ja arviomallin syöteasemat).
    """
    ajo = ajot[f"{asema}/ajo.json"]
    tanaan = dt.date.fromisoformat(ajo["ennustepvm_www"])
    havainnot = {_ms(p) + PAIVA_MS // 2: v for p, v in
                 _paivasarja(ajo.get("qhav"), tanaan - dt.timedelta(days=HISTORIA_PAIVIA),
                             tanaan - dt.timedelta(days=1)).items()}
    aiemmat = {p: v for p in (smhi_data._paiva(ms) for ms in havainnot)
               if (v := syke_data.arvioi_paiva(asema, ajot, p)) is not None}
    arvio = lukema.arvo
    ennuste = {tanaan + dt.timedelta(days=n): v for n in lukema.ennuste
               if (v := lukema.ennuste_korjattu(n)) is not None}
    # 5–95 %:n vaihteluväli siirretään samalla erotuksella kuin ennuste (arvio − malli)
    siirto = arvio - lukema.malli if arvio is not None and lukema.malli is not None else 0.0
    vali = {}
    for p in ennuste:
        a, b = (syke_data._arvo(ajo.get(n) or {}, p) for n in ("qinlask_5", "qinlask_95"))
        if a is not None and b is not None:
            vali[p] = (a + siirto, b + siirto)
    tunnus = [(nimi, lukema.tunnusluvut[nimi], vari) for nimi, vari in
              (("MHQ", "#c62828"), ("MQ", "#2e7d32"), ("MNQ", "#ef6c00")) if nimi in lukema.tunnusluvut]
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    alaotsikko = (f"{_t('Virtaama m³/s')} · {_t('havainnot ja ennuste SYKE, tämän päivän arvo')}: "
                  f"{_t('(' + lukema.lahde)[1:]} · {_t('ennuste tehty')} {tanaan.day}.{tanaan.month}.")
    return piirra(otsikko, alaotsikko, tanaan, ennuste=ennuste, ennuste_vali=vali, havainnot=havainnot,
                  havainto_viiva=True, arvio=arvio, aiemmat_arviot=aiemmat, tunnus=tunnus, alueet=alueet,
                  kieli=kieli)
