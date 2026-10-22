"""Mittarikaaviot SVG:nä: sivun mittarilinkit vievät näihin SYKE:n ja SMHI:n kuvien sijaan.

* SYKE:n mittarit (syke_svg): ajo.jsonin mitatut päiväarvot ja ennuste, joka jatkuu
  viimeisestä mitatusta arvosta (mallin muutos lisättynä, kuten Hawa'Iissa) 5–95 %:n
  vaihteluväleineen. Mallin menneitä arvoja eikä SYKE:n kuvan muita merkintöjä näytetä.
* Ruotsin mittarit (smhi_svg): SMHI:ltä saadaan vain JSON-dataa. Mustat pisteet
  havainnot (viimeinen vuorokausi tunnin välein), HydroNu-ennuste jatkuu tuoreimmasta
  havainnosta katkoviivana (jälkilaskentaa ei näytetä), harmaa alue ja
  magenta viiva saman päivän vaihteluväli ja mediaani eri vuosilta, vaakaviivat
  tunnusluvut (MQ, MHQ, MLQ).
* Arviomallin asemat (arvio_svg, esim. Hawa'Ii): aseman oma havainto julkaistaan
  vasta seuraavana päivänä. Kuvassa on vain mitatut päiväarvot ja samojen päivien
  lasketut arviot (näkee, miten hyvin malli osui), tämän päivän arvio
  (syke_data.Arviomalli) ja ennuste, joka jatkuu arviosta mallin muutoksen mukaan
  (kuten Kaaviolukema.ennuste_korjattu) 5–95 %:n vaihteluvälin kanssa.

Kaikissa: syaani katkoviiva = tänään, vihreät alueet = paikan kohteiden rajat
(vaalea = toimii, tummempi = parhaimmillaan) kohteen nimellä.

Muoto (`muoto`): oletuksena pystykaavio puhelimen pystyasentoon (kapea, tekstit rivittyvät ja
kuva skaalautuu näytön levyiseksi), "vaaka" leveälle näytölle (sivun JS lisää ?muoto=vaaka).
"""

from __future__ import annotations

import contextvars
import datetime as dt
import html
import itertools
import json
import math
import re
import time

import kielet
import smhi_data
import syke_data

LEVEYS, KORKEUS = 900, 440          # vaakakaavio (tunti_svg: korkeus 380)
VASEN, OIKEA, YLA, ALA = 64, 20, 58, 84
# muoto -> (leveys, vasen marginaali, piirtoalueen korkeus, tuntikaavion piirtoalueen korkeus, enimmäisleveys px).
# Pystymallilla ei enimmäisleveyttä: puhelin näyttää SVG-tiedoston 980 px:n virtuaalinäkymässä (ei viewport-
# määritystä), joten kuvan pitää täyttää koko leveys.
MUODOT = {"pysty": (440, 50, 380, 300, None), "vaaka": (LEVEYS, VASEN, KORKEUS - YLA - ALA, 380 - 58 - 70, 1200)}
MERKKI_PX = {12: 6.4, 11.5: 6.2, 16: 8.8}   # tekstin arvioitu merkkileveys fonttikoon mukaan
PAIVA_MS = smhi_data.PAIVA_MS
HISTORIA_PAIVIA = 10   # kaavio alkaa näin monta päivää ennen tätä päivää

e = html.escape

# Reissun ajankohta (unix s, saapuminen perille): sivun mittarilinkki välittää sen (?reissu=),
# ja kaavioon piirretään sen kohdalle vedettävä reissu-osoitin (ilman reissua nykyhetkeen).
# Asetetaan pyynnön ajaksi.
reissu: contextvars.ContextVar[float | None] = contextvars.ContextVar("reissu", default=None)
# Matka-aika perille (min, ajo + lisäaika) sivun linkistä (?matka=): osoitinta vedettäessä lähtöaika
# = osoittimen aika − matka-aika tallennetaan sivun lähtöaikakenttään (sessionStorage melonta-lahtoaika).
matka: contextvars.ContextVar[float | None] = contextvars.ContextVar("matka", default=None)
# Kaavion muoto pyynnön ajaksi: "pysty" (oletus) tai "vaaka" (?muoto=vaaka)
muoto: contextvars.ContextVar[str] = contextvars.ContextVar("muoto", default="pysty")


def _mitat() -> tuple[int, int, int, int, int]:
    return MUODOT.get(muoto.get(), MUODOT["pysty"])


def _juuri(lev: int, kork: int) -> str:
    """SVG:n juurielementti: skaalautuu ikkunan levyiseksi, mutta ei muotoa suuremmaksi."""
    maks = f"max-width:{_mitat()[4]}px;" if _mitat()[4] else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lev} {kork}" '
            f'style="display:block;margin:0 auto;width:100%;{maks}height:auto" '
            f'font-family="system-ui, Segoe UI, sans-serif" font-size="12">')


def _rivita(teksti: str, leveys: float, koko: float = 12) -> list[str]:
    """Teksti riveiksi sanojen välistä, kun se ei mahdu annettuun leveyteen (px)."""
    merkkeja = max(10, int(leveys / MERKKI_PX.get(koko, koko * 0.55)))
    rivit, rivi = [], ""
    for sana in teksti.split(" "):
        if rivi and len(rivi) + 1 + len(sana) > merkkeja:
            rivit.append(rivi)
            rivi = sana
        else:
            rivi = f"{rivi} {sana}" if rivi else sana
    return rivit + [rivi] if rivi else rivit


def _otsikot(otsikko: str, alaotsikko: str, x0: float, leveys: float) -> tuple[list[str], float]:
    """Otsikko (16 px) ja alaotsikko rivitettyinä; palauttaa SVG-osat ja seuraavan vapaan y:n."""
    osat, yy = [], 22
    for rivi in _rivita(otsikko, leveys, 16):
        osat.append(f'<text x="{x0}" y="{yy}" font-size="16" font-weight="600" fill="#1b1f24">{e(rivi)}</text>')
        yy += 20
    yy -= 2
    for rivi in _rivita(alaotsikko, leveys):
        osat.append(f'<text x="{x0}" y="{yy}" fill="#5c6670">{e(rivi)}</text>')
        yy += 16
    return osat, yy


def _selite(osat: list[str], merkinnat: list[tuple[str, str, str]], x0: float, oikea_reuna: float,
            sy: float, merkki) -> float:
    """Selite riveittäin (rivittyy leveyden mukaan); palauttaa viimeisen rivin y:n."""
    sx = x0
    for laji, vari, teksti in merkinnat:
        leveys = 30 + len(teksti) * MERKKI_PX[12]
        if sx + leveys > oikea_reuna and sx > x0:
            sx, sy = x0, sy + 18
        osat.append(merkki(laji, vari, sx, sy))
        rivit = _rivita(teksti, oikea_reuna - sx - 23)   # yksin liian pitkä merkintä rivittyy
        for i, rivi in enumerate(rivit):
            osat.append(f'<text x="{sx + 23}" y="{sy + 15 * i}" fill="#1b1f24">{e(rivi)}</text>')
        if len(rivit) > 1:
            sx, sy = oikea_reuna, sy + 15 * (len(rivit) - 1)   # seuraava merkintä uudelle riville
        else:
            sx += leveys
    return sy

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


_osoittimet = itertools.count(1)   # yksilöllinen tunnus jokaiselle osoittimelle (pinotut kaaviot)

# Osoittimen skripti (SVG:n sisällä; toimii, kun kaavio avataan omana sivunaan): viivaa tai alareunan
# kahvaa vedetään sormella tai hiirellä, napautus kaavioon siirtää osoittimen. Aika varttiin.
_REISSU_JS = """(function () {
  var g = document.getElementById("%s"), D = JSON.parse(g.getAttribute("data-reissu"));
  var alue = document.getElementById(D.id + "-alue"), q = function (c) { return g.querySelector("." + c); };
  var viiva = q("r-viiva"), osuma = q("r-osuma"), kahva = q("r-kahva"), nuoli = q("r-nuoli"),
      piste = q("r-piste"), aika = q("r-aika"), arvo = q("r-arvo");
  var muoto = new Intl.DateTimeFormat(D.kieli === "en" ? "en-GB" : "fi-FI", {timeZone: "Europe/Helsinki",
      weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"});
  var x = function (t) { return D.x0 + (t - D.a) / (D.b - D.a) * D.w; };
  var aikaX = function (px) { return D.a + (px - D.x0) / D.w * (D.b - D.a); };
  var y = function (v) { return D.y0 + (D.ylin - v) / (D.ylin - D.alin) * D.h; };
  function arvoAikaan(t) {
    var s = D.s;
    if (!s.length || t < s[0][0] || t > s[s.length - 1][0]) return null;
    for (var i = 1; i < s.length; i++) if (t <= s[i][0]) {
      var k = (t - s[i - 1][0]) / ((s[i][0] - s[i - 1][0]) || 1);
      return s[i - 1][1] + k * (s[i][1] - s[i - 1][1]);
    }
    return s[s.length - 1][1];
  }
  function luku(v) { return D.m ? v.toFixed(2) : Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1); }
  var kello = new Intl.DateTimeFormat(D.kieli === "en" ? "en-GB" : "fi-FI",
      {timeZone: "Europe/Helsinki", hour: "2-digit", minute: "2-digit"});
  function paikallinen(d) { return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); }
  function lahtoAika(t) { return Math.max(Date.now(), Math.round((t - D.matka * 60000) / 9e5) * 9e5); }
  function tallennaLahto(t) {   // sivun lähtöaikakenttään: sama välilehti (takaisin) ja muut välilehdet
    if (D.matka == null) return;
    var arvo = paikallinen(new Date(lahtoAika(t)));
    try { sessionStorage.setItem("melonta-lahtoaika", arvo); } catch (e) {}
    try { localStorage.setItem("melonta-lahtoaika", JSON.stringify({arvo: arvo, aika: Date.now()})); } catch (e) {}
  }
  var valittu = null;   // viimeksi asetettu aika; tallennetaan lähtöajaksi vasta vedon lopussa
  function aseta(t) {
    t = Math.max(D.a, Math.min(D.b, Math.round(t / 9e5) * 9e5));
    var px = x(t), v = arvoAikaan(t), oikea = px > D.x0 + D.w * 0.55;
    [viiva, osuma].forEach(function (l) { l.setAttribute("x1", px); l.setAttribute("x2", px); });
    kahva.setAttribute("cx", px); nuoli.setAttribute("x", px);
    aika.setAttribute("x", oikea ? px - 6 : px + 6);
    aika.setAttribute("text-anchor", oikea ? "end" : "start");
    aika.textContent = D.nimi + " " + muoto.format(new Date(t))
      + (D.matka != null ? " (" + D.lahto + " " + kello.format(new Date(lahtoAika(t))) + ")" : "");
    valittu = t;
    if (v === null) { piste.setAttribute("visibility", "hidden"); arvo.textContent = ""; return; }
    var py = Math.max(D.y0 + 24, Math.min(D.y0 + D.h - 30, y(v)));   // ei ajankohdan päälle
    piste.setAttribute("visibility", "visible"); piste.setAttribute("cx", px); piste.setAttribute("cy", y(v));
    arvo.setAttribute("x", oikea ? px - 9 : px + 9); arvo.setAttribute("y", py - 9);
    arvo.setAttribute("text-anchor", oikea ? "end" : "start");
    arvo.textContent = luku(v) + " " + D.yks;
  }
  function kohta(e) {
    var p = new DOMPoint(e.clientX, e.clientY).matrixTransform(alue.getScreenCTM().inverse());
    return aikaX(p.x);
  }
  var veto = false;
  [osuma, kahva, nuoli].forEach(function (el) {
    el.addEventListener("pointerdown", function (e) {
      veto = true; el.setPointerCapture(e.pointerId); e.preventDefault(); aseta(kohta(e));
    });
    el.addEventListener("pointermove", function (e) { if (veto) aseta(kohta(e)); });
    el.addEventListener("pointerup", function () { if (veto) tallennaLahto(valittu); veto = false; });
    el.addEventListener("pointercancel", function () { if (veto) tallennaLahto(valittu); veto = false; });
  });
  alue.addEventListener("click", function (e) { aseta(kohta(e)); tallennaLahto(valittu); });
  aseta(D.t0);
})();"""


def _reissu_osoitin(sarja: dict[int, float], ala_ms: float, yla_ms: float, x0: float, leveys: float,
                    y0: float, korkeus: float, alin: float, ylin: float, metreja: bool, yksikko: str,
                    kieli: str) -> list[str]:
    """Vedettävä reissu-osoitin: pystyviiva, alareunan kahva, piste sarjalla sekä ajankohta ja arvo.
    Alkaa reissun ajankohdasta (?reissu=), muuten nykyhetkestä; kaavion ulkopuolinen aika tuodaan reunaan."""
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    tunnus = f"reissu{next(_osoittimet)}"
    alku = (reissu.get() or time.time()) * 1000
    if not ala_ms <= alku <= yla_ms:
        alku = min(max(time.time() * 1000, ala_ms), yla_ms)
    px = x0 + (alku - ala_ms) / (yla_ms - ala_ms) * leveys
    tiedot = {"id": tunnus, "a": ala_ms, "b": yla_ms, "x0": x0, "w": leveys, "y0": y0, "h": korkeus,
              "alin": alin, "ylin": ylin, "m": metreja, "yks": "m" if metreja else "m³/s", "kieli": kieli,
              "nimi": _t("reissu"), "t0": alku, "s": [[ms, round(v, 3)] for ms, v in sorted(sarja.items())],
              "matka": matka.get(), "lahto": "departure" if kieli == "en" else "lähtö"}
    ala = y0 + korkeus
    halo = 'stroke="#fff" stroke-width="3" paint-order="stroke"'
    return [
        f'<rect id="{tunnus}-alue" x="{x0}" y="{y0}" width="{leveys}" height="{korkeus}" fill="transparent"/>',
        f"<g id=\"{tunnus}\" data-reissu='{e(json.dumps(tiedot, separators=(',', ':')))}'>",
        f'<line class="r-viiva" x1="{px:.1f}" x2="{px:.1f}" y1="{y0}" y2="{ala}" stroke="#6a1b9a" '
        f'stroke-width="2" stroke-dasharray="3 3"/>',
        f'<line class="r-osuma" x1="{px:.1f}" x2="{px:.1f}" y1="{y0}" y2="{ala}" stroke="transparent" '
        f'stroke-width="26" style="cursor:ew-resize;touch-action:none"/>',
        f'<circle class="r-piste" cx="{px:.1f}" cy="{y0}" r="5" fill="#6a1b9a" stroke="#fff" stroke-width="2" '
        f'visibility="hidden" pointer-events="none"/>',
        f'<circle class="r-kahva" cx="{px:.1f}" cy="{ala}" r="11" fill="#6a1b9a" '
        f'style="cursor:ew-resize;touch-action:none"/>',
        f'<text class="r-nuoli" x="{px:.1f}" y="{ala + 4.5}" text-anchor="middle" fill="#fff" font-size="13" '
        f'font-weight="700" style="cursor:ew-resize;touch-action:none;user-select:none">↔</text>',
        f'<text class="r-aika" x="{px + 6:.1f}" y="{ala - 17}" fill="#6a1b9a" font-weight="700" {halo} '
        f'pointer-events="none">{e(_t("reissu"))}</text>',
        f'<text class="r-arvo" x="{px + 9:.1f}" y="{y0 + 30}" fill="#6a1b9a" font-size="13" font-weight="700" {halo} '
        f'pointer-events="none"></text>',
        "</g>",
        f"<script><![CDATA[{_REISSU_JS % tunnus}]]></script>",
    ]


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
           jalkikateen_arviot: dict[dt.date, float] | None = None,
           paivan_arvo: tuple[float, str] | None = None,
           toinen_arvio: tuple[str, float] | None = None,
           tunnus: list[tuple[str, float, str]] | None = None,
           alueet: list[Alue] | None = None,
           kieli: str = "fi") -> str:
    """Yleinen kaavio. Päiväarvot piirretään päivän keskelle, havainnot (ms -> arvo) aikaleiman kohdalle.

    malli = mallin menneet päivät (yhtenäinen viiva), ennuste = tulevat päivät (katkoviiva,
    jatkuu mallin viimeisestä päivästä tai tämän päivän arviosta), tausta = (min, mediaani, max),
    paivan_arvo = (tämän päivän arvo, lähde) merkitään lukemana ennustetta muuttamatta.
    """
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    LEVEYS, VASEN, piirto_k, _, _ = _mitat()   # noqa: N806 (muodon mukaiset mitat)
    reuna = VASEN if LEVEYS > 600 else 12      # otsikoiden ja selitteen vasen reuna
    otsikkorivit, YLA = _otsikot(otsikko, alaotsikko, reuna, LEVEYS - reuna - OIKEA)   # noqa: N806
    YLA = max(YLA + 2, 58)   # noqa: N806
    malli, ennuste, ennuste_vali = malli or {}, ennuste or {}, ennuste_vali or {}
    tausta, havainnot, tunnus = tausta or {}, havainnot or {}, tunnus or []
    aiemmat_arviot, alueet = aiemmat_arviot or {}, alueet or []
    jalkikateen_arviot = jalkikateen_arviot or {}
    metreja = yksikko == "m"

    def luku(v: float) -> str:
        return _luku(v, metreja)

    # aikaväli mallin, ennusteen ja havaintojen mukaan (vaihteluväli voi kattaa koko vuoden)
    paivat = sorted(set(malli) | set(ennuste)) or sorted(tausta) or [tanaan]
    alku, loppu = min(paivat[0], tanaan), max(paivat[-1], tanaan + dt.timedelta(days=1))
    if havainnot:
        alku = min(alku, smhi_data._paiva(min(havainnot)))
    # historiaa enintään HISTORIA_PAIVIA päivää (SMHI:n jälkilaskenta ulottuu 30 päivään)
    alku = tanaan - dt.timedelta(days=HISTORIA_PAIVIA)   # aina sama 10 päivän historia-akseli
    malli = {p: v for p, v in malli.items() if p >= alku}
    havainnot = {ms: v for ms, v in havainnot.items() if ms >= _ms(alku)}
    aiemmat_arviot = {p: v for p, v in aiemmat_arviot.items() if p >= alku}
    jalkikateen_arviot = {p: v for p, v in jalkikateen_arviot.items() if p >= alku}
    tausta = {p: t for p, t in tausta.items() if alku <= p <= loppu}

    arvot = list(malli.values()) + list(ennuste.values()) + list(havainnot.values()) \
        + [v for t in tausta.values() for v in t] + [v for t in ennuste_vali.values() for v in t] \
        + list(aiemmat_arviot.values()) + list(jalkikateen_arviot.values()) \
        + ([toinen_arvio[1]] if toinen_arvio else []) \
        + ([arvio] if arvio is not None else []) \
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
    piirto_l = LEVEYS - VASEN - OIKEA

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

    osat = [f'<title>{e(otsikko)}</title>', *otsikkorivit,
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
    if aiemmat_arviot or jalkikateen_arviot:
        # menneiden päivien arviot: näkee, miten hyvin malli osui havaintoihin
        # (aiemmat = silloin näytetty arvo ennustearkistosta, jälkikäteen = laskettu nyt)
        sarja = {**jalkikateen_arviot, **aiemmat_arviot}
        if arvio is not None:
            sarja[tanaan] = arvio
        ryhma.append(f'<path d="{polku([(x(p), y(v)) for p, v in sorted(sarja.items())])}" fill="none" '
                     f'stroke="#ef6c00" stroke-width="1.2" stroke-dasharray="3 3"/>')
        for p, v in sorted(jalkikateen_arviot.items()):
            if p not in aiemmat_arviot:
                ryhma.append(vinonelio(x(p), y(v), 4.5, "#f4b183", ontto=True))
        for p, v in sorted(aiemmat_arviot.items()):
            ryhma.append(vinonelio(x(p), y(v), 5.5, "#ef6c00", ontto=True))
    for ms, v in sorted(havainnot.items()):
        ryhma.append(vinonelio(x_ms(ms), y(v), 5.5, "#000") if havainto_viiva
                     else f'<circle cx="{x_ms(ms):.1f}" cy="{y(v):.1f}" r="2.6" fill="#000"/>')
    tx = x(tanaan)
    ryhma.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{YLA}" y2="{YLA + piirto_k}" stroke="#00bcd4" '
                 f'stroke-width="2" stroke-dasharray="6 4"/>')
    lukema = arvio if arvio is not None else paivan_arvo[0] if paivan_arvo else None
    if toinen_arvio is not None:   # toinen arviomalli rinnalla: violetti ontto vinoneliö
        ty = y(toinen_arvio[1])
        ryhma.append(vinonelio(tx, ty, 7, "#6a1b9a", ontto=True))
        ryhma.append(f'<text x="{tx - 10:.1f}" y="{ty + 18:.1f}" text-anchor="end" fill="#6a1b9a" font-weight="600" '
                     f'stroke="#fff" stroke-width="3" paint-order="stroke">{luku(toinen_arvio[1])}</text>')
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
        rivit = _rivita(f"{nimi} {rajat_teksti(toimii, paras)}", piirto_l - 12, 11.5)
        if ny + 14 * (len(rivit) - 1) > YLA + piirto_k - 4:
            break
        edellinen = ny + 14 * (len(rivit) - 1)
        tspanit = "".join(f'<tspan x="{VASEN + 6}" dy="{0 if i == 0 else 14}">{e(r)}</tspan>'
                          for i, r in enumerate(rivit))
        osat.append(f'<text x="{VASEN + 6}" y="{ny:.1f}" fill="#1b5e20" font-size="11.5" font-weight="600" '
                    f'stroke="#fff" stroke-width="3" paint-order="stroke">{tspanit}</text>')
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
    # reissu-osoitin: arvot havainnoista ja niistä jatkuvasta ennusteesta (tai mallista)
    sarja = dict(havainnot)
    if arvio is not None:
        sarja[_ms(tanaan) + PAIVA_MS // 2] = arvio
    viimeinen = max(sarja, default=None)
    for p, v in (ennuste or malli).items():
        ms = _ms(p) + PAIVA_MS // 2
        if viimeinen is None or ms > viimeinen:
            sarja[ms] = v
    osat += _reissu_osoitin(sarja, ala_ms, yla_ms, VASEN, piirto_l, YLA, piirto_k, alin, ylin, metreja,
                            yksikko, kieli)

    # selite (rivittyy)
    selite = []
    if malli:
        selite.append(("viiva", "#1565c0", _t("malli (ennuste katkoviivana)")))
    elif ennuste:
        selite.append(("katko", "#1565c0", _t("ennuste (jatkuu viimeisestä havainnosta)")))
    if havainnot:
        selite.append(("vino" if havainto_viiva else "piste", "#000", _t("havainto")))
    def keskivirhe(arviot: dict[dt.date, float]) -> str:
        virheet = [abs(v - havainnot[_ms(p) + PAIVA_MS // 2]) for p, v in arviot.items()
                   if _ms(p) + PAIVA_MS // 2 in havainnot]
        return f" ({_t('keskivirhe')} {luku(sum(virheet) / len(virheet))})" if virheet else ""

    if aiemmat_arviot:
        selite.append(("onttovino", "#ef6c00", _t("arvio silloin (arkisto)") + keskivirhe(aiemmat_arviot)))
    jalkikateen = {p: v for p, v in jalkikateen_arviot.items() if p not in aiemmat_arviot}
    if jalkikateen:
        selite.append(("onttovino_vaalea", "#f4b183", _t("laskettu jälkikäteen") + keskivirhe(jalkikateen)))
    if arvio is not None:
        selite.append(("vino", "#ef6c00", _t("arvio tänään")))
    if toinen_arvio is not None:
        selite.append(("onttovino", "#6a1b9a", f"{_t('toinen arvio tänään')} ({toinen_arvio[0]})"))
    elif paivan_arvo:
        selite.append(("vino", "#ef6c00", f"{_t('tänään')}: {luku(paivan_arvo[0])} ({_t(paivan_arvo[1])})"))
    if ennuste_vali:
        selite.append(("alue", "#bcdcf7", _t("ennusteen 5–95 %")))
    if tausta:
        selite += [("alue", "#cfd4d9", _t("vaihteluväli")), ("viiva", "#d81b9a", _t("mediaani"))]
    selite.append(("katko", "#00bcd4", _t("tänään")))
    selite.append(("katko", "#6a1b9a", _t("reissu (vedä ajankohtaa)")))
    if alueet:
        selite += [("alue", "#d5ecd6", _t("kohde toimii")), ("alue", "#a9d5aa", _t("kohde parhaimmillaan"))]
    piilossa = [f"{n} {luku(a)}" for n, a, v in tunnus if (n, a, v) not in tunnus_nakyy]
    def merkki(laji: str, vari: str, sx: float, sy: float) -> str:
        if laji == "viiva":
            return f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2.5"/>'
        if laji == "katko":
            return (f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2" '
                    f'stroke-dasharray="5 3"/>')
        if laji == "piste":
            return f'<circle cx="{sx + 9}" cy="{sy - 4}" r="3" fill="{vari}"/>'
        if laji in ("vino", "onttovino", "onttovino_vaalea"):
            return vinonelio(sx + 9, sy - 4, 5, vari, ontto=laji != "vino")
        return f'<rect x="{sx}" y="{sy - 10}" width="18" height="12" fill="{vari}"/>'

    sy = _selite(osat, selite, reuna, LEVEYS - OIKEA, YLA + piirto_k + 40, merkki)
    if piilossa:
        osat.append(f'<text x="{VASEN + piirto_l}" y="{YLA - 6}" text-anchor="end" fill="#5c6670">'
                    f'{e(", ".join(piilossa))} ({_t("yli kuvan")})</text>')
    korkeus = max(round(sy + 18), KORKEUS) if LEVEYS > 600 else round(sy + 18)
    osat[:0] = [_juuri(LEVEYS, korkeus), f'<rect width="{LEVEYS}" height="{korkeus}" fill="#fff"/>']
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
    # ennuste jatkuu tuoreimmasta havainnosta (mallin päivä = havainnon UTC-päivä)
    tanaan = smhi_data._suomen_paiva(nyt)
    tuorein = smhi_data.tuorein_havainto(havainto) if havainto else None
    havaitut = {smhi_data._paiva(tuorein[1]): tuorein[0]} if tuorein else {}
    ennuste, _, lukema = _jatka_havainnosta(havaitut, {**sarja("coutHindcast"), **sarja("coutForecast")},
                                            max(havaitut, default=tanaan))
    if tuorein:
        lukema = (tuorein[0], "havainto")
    return piirra(otsikko, alaotsikko, tanaan, ennuste=ennuste, tausta=tausta, havainnot=havainnot,
                  paivan_arvo=lukema, tunnus=tunnus, alueet=alueet, kieli=kieli)


def _jatka_havainnosta(havaitut: dict[dt.date, float], malli: dict[dt.date, float], tanaan: dt.date,
                       vali: dict[dt.date, tuple[float, float]] | None = None):
    """Ennuste jatkuu viimeisestä mitatusta arvosta kuten Hawa'Iin kaaviossa: mallin muutos lisätään
    havaintoon (vrt. Kaaviolukema.ennuste_korjattu), ja 5–95 %:n väli siirretään samalla erotuksella.
    Mallin menneitä arvoja ei palauteta. Palauttaa (ennuste, väli, tämän päivän lukema)."""
    vali = vali or {}
    viimeinen = max((p for p in havaitut if p <= tanaan and p in malli), default=None)
    if viimeinen is None:   # ei havaintoa: mallin ennuste sellaisenaan tästä päivästä
        ennuste = {p: v for p, v in malli.items() if p >= tanaan}
        lukema = (malli[tanaan], "malli") if tanaan in malli else None
        return ennuste, {p: ab for p, ab in vali.items() if p >= tanaan}, lukema
    siirto = havaitut[viimeinen] - malli[viimeinen]
    ennuste = {viimeinen: havaitut[viimeinen],
               **{p: v + siirto for p, v in malli.items() if p > viimeinen}}
    siirretty = {p: (a + siirto, b + siirto) for p, (a, b) in vali.items() if p >= viimeinen}
    lukema = (havaitut[tanaan], "havainto") if tanaan in havaitut else \
        (ennuste[tanaan], "ennuste") if tanaan in ennuste else None
    return ennuste, siirretty, lukema


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
    """SYKE:n mittarin kaavio ajo.jsonista: mitatut päiväarvot ja niistä jatkuva ennuste 5–95 %:n
    vaihteluväleineen (mallin menneitä arvoja ei näytetä). None, jos kaavion suuretta ei ole ajo.jsonissa."""
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
    ala, yla = (_paivasarja(ajo.get(n), alku, tanaan + dt.timedelta(days=syke_data.ENNUSTE_PAIVIA))
                for n in (ala_nimi, yla_nimi))
    havainnot = {_ms(p) + PAIVA_MS // 2: v for p, v in _paivasarja(ajo.get(hav_nimi), alku, tanaan).items()}
    metreja = hav_nimi == "whav"
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    alaotsikko = ((f"{_t('Vedenkorkeus m')} ({ajo['w1nolla']})" if metreja and ajo.get("w1nolla") else
                   _t("Vedenkorkeus m") if metreja else _t("Virtaama m³/s"))
                  + f" · {_t('SYKE:n vesistömalli')}, {_t('ennuste tehty')} {tanaan.day}.{tanaan.month}.")
    ennuste, vali, paivan_arvo = _jatka_havainnosta(
        _paivasarja(ajo.get(hav_nimi), alku, tanaan), malli, tanaan,
        {p: (ala[p], yla[p]) for p in ala if p in yla})
    return piirra(otsikko, alaotsikko, tanaan, yksikko="m" if metreja else "m3/s", kieli=kieli,
                  paivan_arvo=paivan_arvo, ennuste=ennuste, ennuste_vali=vali,
                  havainnot=havainnot, havainto_viiva=True, alueet=alueet)


def kuva_svg(sarjat, tanaan: dt.date, otsikko: str, yksikko: str, alueet: list[Alue] | None = None,
             kieli: str = "fi") -> str:
    """Kaavio SYKE:n kaaviokuvasta luetuista sarjoista (syke_kaavio.Kaaviosarjat), kun ajo.jsonissa
    ei ole kaavion suuretta (esim. järven tulovirtaama): havainnot ja niistä jatkuva ennuste
    vaihteluväleineen (kuvan keltainen alue); mallin menneitä arvoja ei näytetä."""
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    paiva = lambda n: tanaan + dt.timedelta(days=n)   # noqa: E731
    metreja = yksikko == "m"
    havainnot = {_ms(paiva(n)) + PAIVA_MS // 2: float(v) for n, v in sarjat.havainnot.items()}
    ennuste, vali, paivan_arvo = _jatka_havainnosta(
        {paiva(n): float(v) for n, v in sarjat.havainnot.items()},
        {paiva(n): float(v) for n, v in sarjat.malli.items()}, tanaan,
        {paiva(n): (float(a), float(b)) for n, (a, b) in sarjat.vali.items()})
    alaotsikko = (f"{_t('Vedenkorkeus m') if metreja else _t('Virtaama m³/s')} · "
                  f"{_t('luettu SYKE:n kaaviokuvasta')}, {_t('ennuste tehty')} {tanaan.day}.{tanaan.month}.")
    return piirra(otsikko, alaotsikko, tanaan, yksikko=yksikko, kieli=kieli, ennuste=ennuste,
                  ennuste_vali=vali, havainnot=havainnot, havainto_viiva=True, paivan_arvo=paivan_arvo,
                  alueet=alueet)


def tunti_svg(otsikko: str, paiva: dt.date, tunnit: dict, vertailu: list[tuple[str, float, str]],
              kieli: str = "fi", yksikko: str = "m3/s", alaotsikko: str | None = None,
              mitattu: str = "arvio mitatuista syötteistä") -> str:
    """Päivän tuntikaavio arviomallin asemalle (syke_data.tuntiarviot): toisen arvion tuntiarvot
    syötteiden mittauksista (yhtenäinen), loppupäivän ennuste (katkoviiva) ja vaakaviivoina
    päivän keskiarvo-ennuste sekä vertailuarvot (nimi, arvo, väri)."""
    _t = lambda s: kielet.kaanna(s, kieli)   # noqa: E731
    metreja = yksikko == "m"
    luku = lambda v: _luku(v, metreja)   # noqa: E731
    lev, vasen, _, pk, _ = _mitat()
    oikea = OIKEA
    reuna = vasen if lev > 600 else 12
    otsikkorivit, yla = _otsikot(
        otsikko, f'{_t("Vedenkorkeus m" if metreja else "Virtaama m³/s")} · '
                 f'{_t(alaotsikko or "toinen arvio tunneittain SYKE:n reaaliaikamittauksista")} {paiva.day}.{paiva.month}.',
        reuna, lev - reuna - oikea)
    yla = max(yla + 2, 58)
    pl = lev - vasen - oikea
    kaikki = list(tunnit["arviot"].values()) + list(tunnit["ennuste"].values()) + [tunnit["keskiarvo"]] \
        + [v for _, v, _ in vertailu]
    a_, y_ = min(kaikki), max(kaikki)
    vara = max((y_ - a_) * 0.15, 0.03 if metreja else 3.0)
    tikit = _asteikko(a_ - vara, y_ + vara)
    alin, ylin = min(tikit[0], a_ - vara), max(tikit[-1], y_ + vara)
    x = lambda t: vasen + t / 24 * pl   # noqa: E731   (tunnin keskikohta: t + 0.5)
    y = lambda v: yla + (ylin - v) / (ylin - alin) * pk   # noqa: E731
    polku = lambda pis: " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py) in enumerate(pis))  # noqa: E731
    osat = list(otsikkorivit)
    for t in tikit:
        if alin <= t <= ylin:
            osat.append(f'<line x1="{vasen}" x2="{vasen + pl}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#e3e7eb"/>'
                        f'<text x="{vasen - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="#5c6670">{luku(t)}</text>')
    for h in range(0, 25, 3):
        osat.append(f'<line x1="{x(h):.1f}" x2="{x(h):.1f}" y1="{yla}" y2="{yla + pk}" stroke="#f0f2f4"/>'
                    f'<text x="{x(h):.1f}" y="{yla + pk + 16}" text-anchor="middle" fill="#5c6670">{h:02d}</text>')
    for nimi, arvo, vari in vertailu:
        osat.append(f'<line x1="{vasen}" x2="{vasen + pl}" y1="{y(arvo):.1f}" y2="{y(arvo):.1f}" stroke="{vari}" '
                    f'stroke-dasharray="2 4" stroke-width="1.5"/><text x="{vasen + pl - 4}" y="{y(arvo) - 4:.1f}" '
                    f'text-anchor="end" fill="{vari}">{e(nimi)} {luku(arvo)}</text>')
    ka = tunnit["keskiarvo"]
    osat.append(f'<line x1="{vasen}" x2="{vasen + pl}" y1="{y(ka):.1f}" y2="{y(ka):.1f}" stroke="#6a1b9a" '
                f'stroke-width="1.5"/><text x="{vasen + 6}" y="{y(ka) - 5:.1f}" fill="#6a1b9a" font-weight="600" '
                f'stroke="#fff" stroke-width="3" paint-order="stroke">{e(_t("päivän keskiarvo-ennuste"))} {luku(ka)}</text>')
    if tunnit["arviot"]:
        osat.append(f'<path d="{polku([(x(t + 0.5), y(v)) for t, v in sorted(tunnit["arviot"].items())])}" '
                    f'fill="none" stroke="#6a1b9a" stroke-width="2.5"/>')
        for t, v in sorted(tunnit["arviot"].items()):
            osat.append(f'<circle cx="{x(t + 0.5):.1f}" cy="{y(v):.1f}" r="2.8" fill="#6a1b9a"/>')
    if len(tunnit["ennuste"]) > 1:
        osat.append(f'<path d="{polku([(x(t + 0.5), y(v)) for t, v in sorted(tunnit["ennuste"].items())])}" '
                    f'fill="none" stroke="#6a1b9a" stroke-width="2.5" stroke-dasharray="8 5"/>')
    nx = x(tunnit["viim"] + 1)
    osat.append(f'<line x1="{nx:.1f}" x2="{nx:.1f}" y1="{yla}" y2="{yla + pk}" stroke="#00bcd4" stroke-width="2" '
                f'stroke-dasharray="6 4"/>')
    osat.append(f'<rect x="{vasen}" y="{yla}" width="{pl}" height="{pk}" fill="none" stroke="#9aa4ae"/>')
    selite = [("viiva", "#6a1b9a", _t(mitattu)), ("katko", "#6a1b9a", _t("ennuste päivän loppuun")),
              ("katko", "#00bcd4", _t("viimeisin mittaus"))]
    def merkki(laji: str, vari: str, sx: float, sy: float) -> str:
        viiva = ' stroke-dasharray="5 3"' if laji == "katko" else ""
        return f'<line x1="{sx}" x2="{sx + 18}" y1="{sy - 4}" y2="{sy - 4}" stroke="{vari}" stroke-width="2.5"{viiva}/>'

    sy = _selite(osat, selite, reuna, lev - oikea, yla + pk + 40, merkki)
    kork = max(round(sy + 18), 380) if lev > 600 else round(sy + 18)
    osat[:0] = [_juuri(lev, kork), f'<rect width="{lev}" height="{kork}" fill="#fff"/>']
    osat.append("</svg>")
    return "\n".join(osat)


def pinoa(*kuvat: str) -> str:
    """SVG-kaaviot allekkain yhdeksi kuvaksi (saman muodon kaaviot, sama leveys)."""
    mitat = [tuple(int(v) for v in re.search(r'viewBox="0 0 (\d+) (\d+)"', k).groups()) for k in kuvat]
    lev = max(m[0] for m in mitat)
    osat = [_juuri(lev, sum(m[1] for m in mitat))]
    yy = 0
    for kuva, (kl, kk) in zip(kuvat, mitat):
        sisa = re.sub(r' style="[^"]*"', "", kuva, count=1)   # juuren skaalaus vain uloimmalle
        osat.append(sisa.replace("<svg ", f'<svg x="0" y="{yy}" width="{kl}" height="{kk}" ', 1))
        yy += kk
    osat.append("</svg>")
    return "\n".join(osat)


def arvio_svg(lukema, ajot: dict[str, dict], asema: str, otsikko: str, alueet: list[Alue] | None = None,
              kieli: str = "fi", arkisto: dict[dt.date, float] | None = None) -> str:
    """Arviomallin aseman kaavio: mitatut päiväarvot, samojen päivien arviot, tämän päivän
    arvio ja siitä jatkuva ennuste.

    `lukema` on syke_data.taydenna- ja arvioi_tanaan-funktioilla täydennetty Kaaviolukema,
    `ajot` ajo.json-avain -> luettu ajo.json (aseman oma ja arviomallin syöteasemat),
    `arkisto` päivä -> sovelluksen silloin näyttämä arvo ennustearkistosta. Päivät, joilta
    arkistoa ei ole, lasketaan jälkikäteen (syke_data.arvioi_paiva) ja merkitään eri tavalla.
    """
    ajo = ajot[f"{asema}/ajo.json"]
    tanaan = dt.date.fromisoformat(ajo["ennustepvm_www"])
    havainnot = {_ms(p) + PAIVA_MS // 2: v for p, v in
                 _paivasarja(ajo.get("qhav"), tanaan - dt.timedelta(days=HISTORIA_PAIVIA),
                             tanaan - dt.timedelta(days=1)).items()}
    arkisto = arkisto or {}
    menneet = [tanaan - dt.timedelta(days=n) for n in range(HISTORIA_PAIVIA, 0, -1)]
    aiemmat = {p: arkisto[p] for p in menneet if p in arkisto}
    jalkikateen = {p: v for p in menneet
                   if p not in aiemmat and (v := syke_data.arvioi_paiva(asema, ajot, p)) is not None}
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
                  havainto_viiva=True, arvio=arvio, aiemmat_arviot=aiemmat, jalkikateen_arviot=jalkikateen,
                  toinen_arvio=lukema.toinen_arvio,
                  tunnus=tunnus, alueet=alueet,
                  kieli=kieli)
