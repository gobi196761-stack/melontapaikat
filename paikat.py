"""osm.fi:n melontapaikkojen optimiolosuhteet.

Jokainen paikka on analysoitu sivun kuvauksesta (osm.fi/melontapaikat/...).
Paikalla on yksi tai useampi *kohde* (pelipaikka tai reittiosuus), jolle
on kirjattu vesimäärä, jolla kohde toimii, ja vesimäärä, jolla se on
parhaimmillaan. Arvot ovat sivun tekstistä; tulkinnat ja arviot on
merkitty kenttään `lahde` sanalla "arvio" ja perusteltu README:ssä.

Mittarit viittaavat SYKE:n kaavioihin muodossa "<alue>/<asema>/<tiedosto>",
esim. "67/q6702110y/wlyhyt.png" = Matkakosken vedenkorkeus. Ensisijaisesti
käytetään paikan omalta sivulta löytyvää kuvaa. Jos sivun kuva on väärää
suuretta (esim. sivun rajat on annettu virtaamana, mutta kuva on
vedenkorkeus), käytetään saman aseman toista kaaviota (`lisakaavio=True`).

Muuttuja on joko kaavion arvo ("arvo") tai tulvaindeksi ("tulvaindeksi"):
0 = keskimääräinen vuoden alivesi (MNW/MNQ), 1 = keskimääräinen vuoden
ylivesi eli tavallinen kevättulvan huippu (MHW/MHQ). Tulvaindeksiä
käytetään paikoille, joiden kuvauksessa puhutaan vain "tulvasta" tai
"kesävedestä" ilman lukuarvoja.

Ruotsin paikoilla ei ole osm.fi-sivua eikä SYKE-kaaviota: niiden mittari on
"smhi/<asema>/<piste>" (SMHI:n havaintoasema + HydroNu-ennustepiste, ks.
smhi_data.py), ja rajat ovat paikallisen melojan (`lahde="meloja"`) tai
omia arvioita.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AVOIN = None  # avoin raja: ei ala- tai ylärajaa


@dataclass(frozen=True)
class Kohde:
    nimi: str
    toimii: tuple[float | None, float | None]
    paras: tuple[float | None, float | None]
    laatu: float = 1.0           # kohteen arvo paikan sisällä (0..1), esim. "paras pelipaikka" = 1
    mittari: str = "paa"          # avain Paikka.mittarit-sanakirjaan
    muuttuja: str = "arvo"        # "arvo" | "tulvaindeksi"
    huom: str = ""
    lahde: str = "sivu"           # "sivu" = luku suoraan kuvauksesta, "meloja" = paikallisen
                                  # melojan kertoma, "arvio" = tulkinta


@dataclass(frozen=True)
class Mittari:
    kaavio: str                   # "<alue>/<asema>/<tiedosto>" tai "smhi/<asema>/<piste>"
    lisakaavio: bool = False      # ei sivulla; saman tai lähiaseman SYKE-kaavio
    marginaali: float | None = None  # kuinka kaukana toimivasta alueesta pisteet putoavat nollaan

    @property
    def smhi(self) -> bool:
        return self.kaavio.startswith("smhi/")


@dataclass(frozen=True)
class Paikka:
    nimi: str
    url: str
    tyyppi: str                   # "peli" (pelipaikka) | "retki" (retki- ja laskupätkä)
    km_oulusta: int | None        # likimääräinen ajomatka Oulusta
    kuvaus: str
    mittarit: dict[str, Mittari] = field(default_factory=dict)
    kohteet: tuple[Kohde, ...] = ()
    maa: str = "FI"               # "FI" | "SE"; Ruotsin paikat näkyvät vain omalla välilehdellään

    @property
    def osm_sivu(self) -> bool:
        """Onko paikalla osm.fi-sivu (josta kaaviot tarkistetaan)?"""
        return "://www.osm.fi/" in self.url


VALILEHDET = ("peli", "retki", "ruotsi")


def nakyy(paikka: Paikka, valilehti: str | None) -> bool:
    """Näkyykö paikka välilehdellä: None/"" = Kaikki (Suomi), "peli", "retki" tai "ruotsi"."""
    if valilehti == "ruotsi":
        return paikka.maa == "SE"
    if paikka.maa != "FI":
        return False
    return valilehti not in ("peli", "retki") or paikka.tyyppi == valilehti


T = "tulvaindeksi"

# SYKE-asemien nimet kaavioiden otsikoista (asematunnus URL:ssa)
ASEMAT = {
    "q0400600y": "Lieksanjoki, Ruunaa",
    "q5100500y": "Saarenpää (Lestijoki)",
    "q5400410y": "Tolpankoski (Pyhäjoki)",
    "q5700700y": "Länkelä (Siikajoki)",
    "q5800000y": "Temmesjoki",
    "q5800100y": "Tyrnävänjoki",
    "q5904400y": "Sanginjoki",
    "q6000410y": "Haukipudas (Kiiminkijoki)",
    "l611331001y": "Pudasjärvi",
    "q6101400y": "Kipinä",
    "q6101750y": "Maalismaa (Iijoki)",
    "q6300210y": "Ravaska (Kuivajoki)",
    "q6400410y": "Simo",
    "q6701500y": "Pello",
    "q6702110y": "Matkakoski",
    "l657121001y": "Olkkajärvi, tulovirtaama (Raudanjoki)",
    "q6503600y": "Marraskoski (Ounasjoki)",
    "q6503300y": "Kaukonen (Ounasjoki)",
    # SMHI:n havaintoasemat ("smhi/<asema>/<piste>")
    "1387": "Gransel (Piteälven)",
    "11": "Männikkö (Kalixälven)",
}


def aseman_nimi(kaavio: str) -> str:
    """'67/q6702110y/wlyhyt.png' -> 'Matkakoski', 'smhi/1387/31914' -> 'Gransel (Piteälven)'"""
    osat = kaavio.split("/")
    return ASEMAT.get(osat[1], osat[1]) if len(osat) >= 2 else kaavio

PAIKAT: tuple[Paikka, ...] = (
    # ------------------------------------------------------------------
    # Pelipaikat
    # ------------------------------------------------------------------
    Paikka(
        "Kipinä (Iijoki)", "https://www.osm.fi/melontapaikat/kipinae/", "peli", 60,
        "Melottavaa läpi kesän, selkeät akanvirrat, vähän vaaranpaikkoja. "
        "Tulva-aikaan tasainen; mittarina Pudasjärven vedenkorkeus.",
        {"paa": Mittari("61/l611331001y/w3lyhyt.png", marginaali=0.3)},
        (
            Kohde("Keskimmäisen silta-aukon hontto", (107.7, 108.1), (107.85, 108.1), 1.0,
                  huom="paras pelipaikka; yli 107.85 m ulkoreunaan surffattava aalto-osa"),
            Kohde("Oikean silta-aukon surffiaalto", (108.1, 108.9), (108.1, 108.9), 0.8,
                  huom="hidas surffiaalto, ei akanvirtaa (kanto 2–20 m)"),
            Kohde("Ala-aallot (ykkös- ja kakkosaalto)", (106.8, 107.8), (106.8, 107.3), 0.85,
                  huom="parhaimmillaan alle 107.3 m; sopii myös koskisuppailuun"),
        ),
    ),
    Paikka(
        "Koiteli (Kiiminkijoki)", "https://www.osm.fi/koiteli/", "peli", 25,
        "Paljon pieniä pelipaikkoja eri vesillä; Tulikurkku sopii aloittelijoille. "
        "Vettä yleensä kesäkuun alkuun.",
        {"paa": Mittari("60/q6000410y/wlyhyt.png", marginaali=0.3)},
        (
            Kohde("Helmihontto", (10.3, 11.0), (10.65, 10.75), 1.0,
                  huom="parhaimmillaan 10.7 m; kärrynpyörät, voltit"),
            Kohde("Etuaalto", (10.3, 11.0), (10.4, 11.0), 0.9,
                  huom="10.4 m:stä alkaen kärryttely ja voltti onnistuvat"),
            Kohde("Takaköngäs", (10.5, 11.05), (10.8, 11.05), 0.8,
                  huom="hyvä n. 11.0 m ja sen alle; 10.5 m:llä reunoilla kolisee", lahde="arvio"),
            Kohde("Tukkirännin surffiaalto", (10.4, 10.6), (10.45, 10.55), 0.7,
                  huom="koskeen keskelle n. 10.5 m vedellä", lahde="arvio"),
            Kohde("Tulikurkku", (10.3, 11.0), (10.65, 10.75), 0.7,
                  huom="parhaimmillaan 10.7 m; sopii aloittelijoille", lahde="arvio"),
        ),
    ),
    Paikka(
        "Matkakoski (Tornionjoki)", "https://www.osm.fi/matkakoski/", "peli", 180,
        "Aina melottavaa; tulvalla Suomen suurimmat aallot ja stopparit. "
        "Ei aloittelijoille.",
        {"paa": Mittari("67/q6702110y/wlyhyt.png", marginaali=0.4)},
        (
            Kohde("Peliajan paikat (iso stoppari, Ruotsin aalto, WC-Duck)", (27.2, 28.0), (27.5, 27.8), 1.0,
                  huom="alle 28 m pelipaikoille pääsee takaisin melomalla"),
            Kohde("Pelipaikat isolla vedellä", (28.0, 31.0), (28.0, 31.0), 0.7,
                  huom="pudotettava ylhäältä, takaisin kantaen"),
            Kohde("Tulva – 'Zambezi-meininki'", (31.0, AVOIN), (31.0, AVOIN), 0.9,
                  huom="vain kokeneille; kosken keskellä oleva kallio peittyy"),
            Kohde("Ylähontto vähällä vedellä", (AVOIN, 27.5), (AVOIN, 27.5), 0.6,
                  huom="Ruotsin aalto heikkenee matalalla vedellä", lahde="arvio"),
        ),
    ),
    Paikka(
        "Kattilakoski (Tornionjoki)", "https://www.osm.fi/kattilakoski/", "peli", 230,
        "Isolla vedellä Suomen paras freestylepaikka: hevosenkenkä, mega-aalto, "
        "Finnvågen, parkkihontto. Mittarina Pellon vedenkorkeus.",
        {"paa": Mittari("67/q6701500y/wlyhyt.png", marginaali=0.4)},
        (
            # Rajat vastaavat tuorala.wordpress.com:n "Kattilakosken definitiivistä
            # vedenkorkeusreferenssiä" (25.5.2011), josta myös kakkosaalto ja väliportaan hontto.
            Kohde("Hevosenkenkä", (78.05, 78.50), (78.15, 78.25), 1.0,
                  huom="kakkosaalto 78.35–78.50 m"),
            Kohde("Kakkosaalto", (78.35, 78.50), (78.35, 78.40), 0.8,
                  huom="parhaimmillaan 78.35 m; 78.50 m kaatuu jo pohjalle (Tuorala)", lahde="meloja"),
            Kohde("Suomenpuolen väliportaan hontto", (78.20, 78.30), (78.23, 78.27), 0.6,
                  huom="parhaimmillaan n. 78.25 m, 'äärimmäisen aliarvostettu' (Tuorala)", lahde="meloja"),
            Kohde("Mega-aalto", (78.85, 79.15), (78.95, 79.05), 1.0,
                  huom="parhaimmillaan 79.00 m"),
            Kohde("Ala-aalto", (78.85, 79.00), (78.85, 78.90), 0.9, huom="parhaimmillaan 78.85 m"),
            Kohde("Ala-aalto (matala vesi)", (78.20, 78.30), (78.23, 78.27), 0.9, huom="toimii n. 78.25 m"),
            Kohde("Grillikodan hontto", (78.90, 79.10), (78.95, 79.05), 0.6, huom="n. 79 m"),
            Kohde("Parkkihontto", (79.50, AVOIN), (79.50, AVOIN), 0.8, huom="mitä enemmän vettä sen parempi"),
            Kohde("Finnvågen", (80.20, AVOIN), (80.20, AVOIN), 1.0,
                  huom="vaatii paljon vettä, parhaat surffit yli 3000 m³/s"),
            Kohde("Svansteinin stoppari", (78.00, AVOIN), (79.00, AVOIN), 0.8,
                  huom="14 km ylävirtaan; sopii kaikentasoisille"),
        ),
    ),
    Paikka(
        "Kukkolankoski (Tornionjoki)", "https://www.osm.fi/kukkolankoski/", "peli", 150,
        "Lähinnä läpilaskupaikka; Suomen reunassa pikku hontto, kallion Ruotsin "
        "reunassa surffiaalto. Mittarina Matkakoski.",
        {"paa": Mittari("67/q6702110y/wlyhyt.png", marginaali=0.4)},
        (
            Kohde("Pikku hontto ja surffiaalto", (28.0, 29.0), (28.0, 28.7), 0.7,
                  huom="kokemusta 28–28.7 m; 29.2 m on liikaa; lyhyet akanvirrat"),
        ),
    ),
    Paikka(
        "Vuentokoski (Tornionjoki)", "https://www.osm.fi/vuentokoski/", "peli", 185,
        "Isot aallot ja stopparit ilman akanvirtoja; Vuento–Matkakoski nopea "
        "jokipätkä. Tulva-aikana jännä paikka.",
        {"paa": Mittari("67/q6702110y/wlyhyt.png", marginaali=0.4)},
        (
            Kohde("Vuennonkoski – Matkakoski", (28.2, AVOIN), (28.7, AVOIN), 1.0,
                  huom="28.7 m mukavia pelipaikkoja; 28.2 m ei juuri kannata; yli 2000 m³/s "
                       "(n. 31 m) 'yksi parhaista ison veden pätkistä' (Tuorala 2010)"),
        ),
    ),
    Paikka(
        "Hawa'Ii (Iijoki, Maalismaa)", "https://www.osm.fi/hawa-ii/", "peli", 55,
        "Tulvalla iso murtuva aalto Iijoen vanhassa uomassa. Eskimon oltava "
        "varma.",
        {"paa": Mittari("61/q6101750y/qin3lyhyt.png", marginaali=200)},
        (
            Kohde("Murtuva aalto", (600, AVOIN), (850, AVOIN), 1.0,
                  huom="n. 600 m³/s keula kolisee; 850 m³/s tosi hyvä ja paranee"),
        ),
    ),
    Paikka(
        "Pyhäjoki", "https://www.osm.fi/pyhaejoki/", "peli", 110,
        "Ruukinkoski (stoppari/murtuva aalto) ja Saunarannan aalto. Kauden "
        "aloituspaikka, sesonki lyhyt. Mittarina Tolpankoski.",
        {"paa": Mittari("54/q5400410y/qinlyhyt.png", marginaali=20)},
        (
            Kohde("Ruukinkoski: stoppari / murtuva aalto", (45, 75), (45, 75), 0.8,
                  huom="akanvirta laskijan oikealla; takaisin melomalla"),
            Kohde("Saunarannan aalto", (80, 150), (130, 150), 0.9,
                  huom="parhaimmillaan n. 140 m³/s; 170 m³/s liikaa"),
        ),
    ),
    Paikka(
        "Siikajoki (Pöyryn pato)", "https://www.osm.fi/melontapaikat/siikajoki/", "peli", 70,
        "Pöyryn padon alla monipuolinen koskialue: Vaahtokylpy ja Kalliosaaren "
        "paikat. Mittarina Länkelän virtaama.",
        {"paa": Mittari("57/q5700700y/qinlyhyt.png", marginaali=40)},
        (
            Kohde("Vaahtokylpy (murtuva aalto)", (250, AVOIN), (300, 400), 1.0,
                  huom="loistava akanvirta, sopii vähemmän meloneillekin"),
            Kohde("Vaahtokylpy, kielen toinen puoli", (140, 250), (140, 200), 0.85,
                  huom="150 m³/s: hontto, jossa syvyyttä volteille", lahde="arvio"),
            Kohde("Kalliosaaren pelipaikat", (70, 250), (70, 250), 0.7,
                  huom="70 m³/s: keula kolisee upotuksessa; mukavia virranrajoja"),
            Kohde("Aalto 5 km alavirtaan", (150, AVOIN), (150, AVOIN), 0.7, huom="aaltoon pitää kantaa"),
        ),
    ),
    Paikka(
        "Niskakoski (Lestijoki)", "https://www.osm.fi/niskakoski/", "peli", 190,
        "Stoppari yli 50 m³/s, yli 85 m³/s taakse aalto. Kauden avauspaikka "
        "(huhtikuu). Sivulla vedenkorkeuskuva, rajat virtaamana.",
        {"paa": Mittari("51/q5100500y/qinlyhyt.png", lisakaavio=True, marginaali=15)},
        (
            Kohde("Stoppari", (50, AVOIN), (50, AVOIN), 0.8, huom="hyvät akanvirrat molemmin puolin"),
            Kohde("Stoppari + aalto", (85, AVOIN), (85, AVOIN), 1.0, huom="virranrajat hankalia isolla vedellä"),
        ),
    ),
    Paikka(
        "Neitikoski (Lieksanjoki)", "https://www.osm.fi/neitikoski/", "peli", 390,
        "Lähes joen levyinen aalto/stoppari, lyhyet uinnit (päättyy järveen). "
        "Toimii lähes kaikilla vesillä; tulvalla vaikeampi.",
        {"paa": Mittari("04/q0400600y/wlyhyt.png")},
        (
            Kohde("Aalto / stoppari", (AVOIN, AVOIN), (0.2, 0.9), 0.9, muuttuja=T,
                  huom="tulvalla murtuu koko leveydeltä; matalalla vasen reuna stoppariksi",
                  lahde="arvio"),
        ),
    ),
    Paikka(
        "Trollforsarna (Piteälven)", "https://sv.wikipedia.org/wiki/Trollforsarna", "peli", 450,
        "Ruotsi: Piteälvenin koskiosuus Granselin mittarin kohdalla, isoja aaltoja ja "
        "laskettavaa eri vesillä. Rajat paikalliselta kokeneelta melojalta (SMHI Gransel).",
        {"paa": Mittari("smhi/1387/31914", marginaali=60)},
        (
            Kohde("Paltvalsen (iso aalto)", (170, AVOIN), (190, 240), 1.0,
                  huom="parhaimmillaan 190–240 m³/s, toimii n. 170:stä", lahde="meloja"),
            Kohde("Glashällen (pieni aalto)", (220, AVOIN), (320, 360), 0.8,
                  huom="toimii n. 220–400+, parhaimmillaan n. 340; ylärajaa ei tiedetä", lahde="meloja"),
            Kohde("Yläpätkä (Delta / keskiränni)", (140, 300), (140, 300), 0.9,
                  huom="yli 300 m³/s karvainen", lahde="meloja"),
            Kohde("Satumaa (Sagoland)", (140, 300), (140, 300), 0.7,
                  huom="samat vedet kuin Yläpätkällä, mutta helpompi", lahde="meloja"),
            Kohde("Alapätkä (Nedre Trollforsarna)", (AVOIN, AVOIN), (300, AVOIN), 0.8,
                  huom="aina hyvä, parempi yli 300 m³/s", lahde="meloja"),
            Kohde("Benbrytarforsen", (AVOIN, 150), (AVOIN, 130), 0.8,
                  huom="hyvä alle 130 m³/s, enintään n. 150", lahde="meloja"),
        ),
        maa="SE",
    ),
    Paikka(
        "Taivalkoski", "https://www.osm.fi/taivalkoski/", "peli", 170,
        "Rakennettu rodeomonttu ja slalomrata; säännöstelypato, vettä voi tilata "
        "kunnalta. Sivulla ei vesikaaviota.",
    ),
    # ------------------------------------------------------------------
    # Retki- ja laskupätkät
    # ------------------------------------------------------------------
    Paikka(
        "Sanginjoki", "https://www.osm.fi/sanginjoki/", "retki", 15,
        "Koskisin osuus Lemmenpolulta Taivalkoskelle (n. 8 km), mukava tulva-aikaan.",
        {"paa": Mittari("59/q5904400y/qin3lyhyt.png", marginaali=3)},
        (
            Kohde("Koskiosuus Lemmenpolku – Taivalkoski", (8, AVOIN), (12, AVOIN), 0.8,
                  huom="vähintään 8 m³/s; parhaimmillaan reilusti yli 10 m³/s"),
        ),
    ),
    Paikka(
        "Kuivajoki", "https://www.osm.fi/kuivajoki/", "retki", 75,
        "Laskettavissa n. 3 vk jäiden lähdöstä; paras osuus 17 km Hyryn kylältä. "
        "Mittarina Ravaska.",
        {"paa": Mittari("63/q6300210y/wlyhyt.png", marginaali=0.3)},
        (
            Kohde("Koskiosuus (Hyry – Kuivaniemi)", (27.9, AVOIN), (28.4, AVOIN), 0.8,
                  huom="n. 28 m: pienempää aaltoa ja kivien kiertelyä", lahde="arvio"),
            Kohde("Kattilakoski – asemankylä pelipätkä", (0.7, AVOIN), (0.85, AVOIN), 0.9, muuttuja=T,
                  huom="heti jäiden lähdön jälkeen isot aallot", lahde="arvio"),
        ),
    ),
    Paikka(
        "Olhavajoki", "https://www.osm.fi/olhavajoki/", "retki", 50,
        "Vettä n. 1–2 viikkoa jäiden lähdöstä. Ei omaa mittaria: tulva samaan "
        "aikaan kuin Kuivajoella, mutta vesi laskee nopeammin.",
        {"paa": Mittari("63/q6300210y/wlyhyt.png", lisakaavio=True)},
        (
            Kohde("Kaihuanjärvi – Olhava (Sahankoski, alin koski)", (0.75, AVOIN), (0.9, AVOIN), 0.9,
                  muuttuja=T, huom="arvioitu Kuivajoen mittarista", lahde="arvio"),
        ),
    ),
    Paikka(
        "Simojoki", "https://www.osm.fi/simojoki/", "retki", 110,
        "Alaniemi–Simo lähes koko ajan koskea/virtaa. Kesävedellä aloittelijoille, "
        "tulvalla vain kokeneille; Kalliokoskella tulvalla surffiaalto.",
        {"paa": Mittari("64/q6400410y/wlyhyt.png")},
        (
            Kohde("Retkimelonta Alaniemi – Simo (kesävesi)", (0.1, 0.7), (0.2, 0.6), 0.6, muuttuja=T,
                  huom="sopii aloitteleville ja retkeilijöille", lahde="arvio"),
            Kohde("Isot kosket + Kalliokosken surffiaalto (tulva)", (0.7, AVOIN), (0.85, AVOIN), 1.0,
                  muuttuja=T, huom="vain kokeneille; paras pari viikkoa jäiden lähdöstä", lahde="arvio"),
        ),
    ),
    Paikka(
        "Lieksanjoki (Matkalahti – Siikakoski)", "https://www.osm.fi/lieksanjoki/", "retki", 390,
        "Ruunaan koskireitti, II-luokan kosket; kulkukelpoisuus hyvä/erinomainen. "
        "Murrookoski kuivalla erittäin kivinen.",
        {"paa": Mittari("04/q0400600y/wlyhyt.png")},
        (
            Kohde("Koskireitti", (0.05, AVOIN), (0.25, AVOIN), 0.7, muuttuja=T,
                  huom="Neitikoskella mela-merkkisäännöt", lahde="arvio"),
        ),
    ),
    Paikka(
        "Liminganjoki", "https://www.osm.fi/liminganjoki/", "retki", 30,
        "Kasitieltä Vanhaan Liminkaan helppoja I-luokan koskia. Paljon kaatuneita "
        "puita. Vesitilanne Tyrnävänjoen käyristä (sivun kuva ei toimi).",
        {"paa": Mittari("58/q5800100y/qinlyhyt.png", lisakaavio=True, marginaali=2)},
        (
            Kohde("Koskiosuus kasitie – Vanha Liminka", (4.0, AVOIN), (8.0, AVOIN), 0.6,
                  huom="Tyrnävällä 2.5 m³/s oli liian vähän; varo puita ja lanka-aitoja",
                  lahde="arvio"),
        ),
    ),
    Paikka(
        "Muhosjoki", "https://www.osm.fi/muhosjoki/", "retki", 40,
        "Huikola–Vääräkoski ja Murtokoski–Suokylä pikkukoskia; Suokylän alla "
        "joen upein koskijakso. Sivulla Tyrnävänjoen vedenkorkeus.",
        {"paa": Mittari("58/q5800100y/qinlyhyt.png", lisakaavio=True, marginaali=2),
         "taso": Mittari("58/q5800100y/w3lyhyt.png")},
        (
            Kohde("Pikkukosket (Huikola – Suokylä)", (3.3, AVOIN), (6.0, AVOIN), 0.6,
                  huom="syysvedellä (Tyrnävä ~3.3 m³/s) hiukan matalia", lahde="arvio"),
            Kohde("Suokylän koskijakso pelimelontaan", (0.7, AVOIN), (0.85, AVOIN), 0.8,
                  mittari="taso", muuttuja=T, huom="kevättulvalla; tarkista Ämmänkosken köngäs",
                  lahde="arvio"),
        ),
    ),
    Paikka(
        "Temmesjoki", "https://www.osm.fi/temmesjoki/", "retki", 40,
        "Hyvä koskikauden aloitus heti jäiden lähdettyä; Haurukylä–Vehkamaantie "
        "I-luokan koskia. Tulvaisuus Tyrnävänjoesta (sivun kaaviossa ei tunnuslukuja).",
        {"paa": Mittari("58/q5800000y/qinlyhyt.png"),
         "tyrnava": Mittari("58/q5800100y/qinlyhyt.png", lisakaavio=True)},
        (
            Kohde("Haurukylä – Vehkamaantie", (0.2, AVOIN), (0.5, AVOIN), 0.6,
                  mittari="tyrnava", muuttuja=T, huom="kevättulvan joki", lahde="arvio"),
        ),
    ),
    Paikka(
        "Pahakurkkio (Kalixälven)", "https://vattenwebb.smhi.se/hydronu/?subid=35732", "retki", 370,
        "Ruotsi, Saittarova (Pajala): seitsemän kosken sarja 3–4 km; kosket 1–3 n. III, "
        "4 hontto oikealla, 5 vaikein, 6–7 IV. Mittarina Männikkö (15 km alavirtaan). "
        "Yli n. 220 m³/s kosket isoja ja vitonen V-luokkaa.",
        {"paa": Mittari("smhi/11/35732", marginaali=30)},
        (
            Kohde("Koskisarja 1–7", (70, 200), (85, 150), 1.0,
                  huom="95 m³/s 'lähes optimaalinen' (8/2010); yli n. 220 vitonen V-luokkaa",
                  lahde="arvio"),
            Kohde("Åretsvågen (ykköskosken leikkiaalto)", (200, AVOIN), (200, AVOIN), 0.9,
                  huom="toimi n. 220 m³/s:llä (7/2010), vaatii korkean veden; hontot talon kokoisia",
                  lahde="arvio"),
        ),
        maa="SE",
    ),
    # ------------------------------------------------------------------
    # Rovaniemen koskikohteet (Roimeloo ry:n foorumi, roimeloo.net, alue
    # "Melontapaikkoja"). Rajat foorumin kuvauksista, mittarit kuten foorumilla.
    # ------------------------------------------------------------------
    Paikka(
        "Vikaköngäs (Raudanjoki)", "https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=12", "peli", 245,
        "Rovaniemi, Napapiirin retkeilyalue (25 km pohjoiseen, E75): Raudanjoen koski, "
        "jonka suisteet muodostavat akanvirtoja; toimii koko kauden 15–20 m³/s kesävesistä "
        "300–450 m³/s kevättulviin. Mittarina Olkkajärven tulovirtaama (Roimeloo).",
        {"paa": Mittari("65/l657121001y/qinlyhyt.png", marginaali=15)},
        (
            Kohde("Akanvirrat ja treeni (slalom, kuntomelonta)", (15, 450), (20, 50), 1.0,
                  huom="akanvirrat toimivat parhaiten alle 50 m³/s; 15–20 m³/s melko kivinen, "
                       "mutta aina jotain luovittavaa", lahde="meloja"),
            Kohde("Isot aallot (kevättulva, läpilasku)", (200, 450), (300, 350), 0.9,
                  huom="tulvalla suisteet veden alla; 300–350 m³/s parhaimmillaan isommille aalloille; "
                       "Tuorala 2010: 290 m³/s isoja aaltoja mutta ei surffattavaa, 180 'ei oikein mitään'",
                  lahde="meloja"),
        ),
    ),
    Paikka(
        "Korpikoski (Raudanjoki)", "https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=15", "peli", 245,
        "Rovaniemi, tien 82 silta: pieni, kivinen ja lyhyt koski, joka päättyy suvantoon. "
        "Koskikurssit, tekniikkatreenit ja uudet koskimelojat; pääsy Vikakönkään parkkipaikalta. "
        "Mittarina Olkkajärven tulovirtaama (Roimeloo).",
        {"paa": Mittari("65/l657121001y/qinlyhyt.png", marginaali=20)},
        (
            Kohde("Virranrajat (kurssit, tekniikka, vanhan koulun pelimelonta)", (AVOIN, AVOIN), (AVOIN, 30), 1.0,
                  huom="alle 30 m³/s kosken alle nousee iso kivi, joka jakaa virtauksen kahteen "
                       "napakkaan virranrajaan; uinnit turvallisia", lahde="meloja"),
        ),
    ),
    Paikka(
        "Vaattunkiköngäs (Raudanjoki)", "https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=16", "peli", 240,
        "Rovaniemi, Vaattungin retkeilyreitti: suora, kapeneva koskenpätkä; sillan jälkeen "
        "akanvirrat molemmin puolin. Mittarina Olkkajärven tulovirtaama (Roimeloo).",
        {"paa": Mittari("65/l657121001y/qinlyhyt.png", marginaali=40)},
        (
            Kohde("Akanvirrat ja virranylitykset (treeni)", (200, 250), (200, 250), 1.0,
                  huom="alle 250 m³/s hyvä harjoitella jämäkämmän virran ylitystä; yli 50 m³/s "
                       "rajan alla ei enää hyvä", lahde="meloja"),
            Kohde("Isompi aallokko (tulva)", (250, AVOIN), (250, AVOIN), 0.6,
                  huom="tulvavesillä vähän tuntumaa isomman aallokon melontaan; Tuorala 2010: "
                       "290 m³/s mukavan näköinen aaltojono, ei surffattava", lahde="meloja"),
        ),
    ),
    Paikka(
        "Marraskoski (Ounasjoki)", "https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=13", "peli", 260,
        "Rovaniemi, n. 30 km pohjoiseen: lyhyt pelipaikka, stoppari oikealla, virranrajat "
        "vasemmalla ja pitkä akanvirta keskellä; kevättulvalla Soulwave-surffiaalto. "
        "Mittarina Marraskosken virtaama (Roimeloo).",
        {"paa": Mittari("65/q6503600y/qinlyhyt.png", marginaali=50)},
        (
            # Kesävesi on "mukava" (enintään 80 p.), Soulwave-tulva antaa täydet 100 p.
            # Tuorala: aalto toimii n. 160–250 m³/s (2011); 250 m³/s hyvät virranrajat
            # treeneihin (9.6.2010); Soul Wave yli 1000 m³/s (2012), 1040 m³/s hieno (21.5.2010).
            Kohde("Stoppari ja akanvirta (kesäsurffi)", (100, 250), (160, 250), 0.8,
                  huom="100–250 m³/s stopparissa kokoa ja akanvirta käytössä, aalto parhaiten "
                       "160–250 (Tuorala); yli 250 kova työ päästä takaisin; alle 100 stoppari matala",
                  lahde="meloja"),
            Kohde("Soulwave (kevättulvan surffiaalto)", (800, AVOIN), (1000, AVOIN), 1.0,
                  huom="Roimeloo: yli 800 m³/s isot surffiaallot keskivasemmalla; Tuorala: leveä "
                       "aalto yli 1000 m³/s; tiputtaudu vasemmalta rannalta", lahde="meloja"),
        ),
    ),
    Paikka(
        "Molkoköngäs (Ounasjoki)", "https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=14", "peli", 300,
        "Tie 79, n. 78 km Rovaniemeltä: lyhyt ja kapea koskipätkä kanjonimaisten kallioiden "
        "vieressä; surffiaaltojono vasemmalla laidalla, akanvirta aaltojen ja kallioiden "
        "välissä. Parhaiten lyhyillä freestylekajakeilla. Mittarina Kaukosen virtaama (Roimeloo).",
        {"paa": Mittari("65/q6503300y/qinlyhyt.png", marginaali=50)},
        (
            # tuorala.wordpress.com 5.6.2012: "toiminee virtaamilla 220-280m3 Kaukosessa",
            # parhaimmillaan n. 260–270 (Roimeloo: alle 300)
            Kohde("Molkoaalto (surffiaaltojono)", (220, 280), (260, 270), 1.0,
                  huom="toimii n. 220–280 m³/s, parhaimmillaan 260–270 (Tuorala 2012); "
                       "surffi-kanto-surffi", lahde="meloja"),
        ),
    ),
    Paikka(
        "Kutujoki", "https://www.osm.fi/kutujoki/", "retki", 80,
        "Otermajärvestä Oulujokeen, I–II-luokan kosket. Hyvä aloitteleville. "
        "Sivulla ei vesikaaviota.",
    ),
    Paikka(
        "Oulujoki", "https://www.osm.fi/oulujoki/", "retki", 0,
        "Säännöstelty pääjoki, melottavissa aina. Sivulla ei vesikaaviota.",
    ),
    Paikka(
        "Oulun edustan saaret", "https://www.osm.fi/oulun-edustan-saaret/", "retki", 5,
        "Merimelonta (Hermannit, Kropsu, Hailuoto ...). Olosuhteet riippuvat "
        "tuulesta, ei vesikaaviota.",
    ),
)
