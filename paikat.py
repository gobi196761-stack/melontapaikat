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


# Kajakkityypit kohteiden suosituksiin (sivulla kuvakkeina, ks. app.KAJAKKI_KUVAKKEET)
KAJAKKITYYPIT = ("freestyle", "slice", "riverrunner")
# Pelipaikkojen isot surffiaallot, joille oletuksena freestyle (hontot ja stopparit tunnistetaan nimestä)
ISOT_SURFFIT = {"Matkan aalto", "Pelipaikat isolla vedellä", "Mega-aalto", "Finnvågen",
                "Vaahtokylpy (murtuva aalto)", "Vaahtokylpy, kielen toinen puoli", "Paltvalsen (iso aalto)",
                "Soulwave (kevättulvan surffiaalto)", "Molkoaalto (surffiaaltojono)"}


def kohteen_kajakit(paikka: "Paikka", kohde: "Kohde") -> tuple[str, ...]:
    """Kohteelle suositellut kajakkityypit: kohteen oma määritys (paikallisen melojan mukaan), muuten
    retkikohteille slice ja river runner, Neitikoskelle sekä pelipaikkojen honttoihin, stoppareihin ja
    isoihin surffeihin freestyle ja muille pelipaikkojen kohteille slice."""
    if kohde.kajakit:
        return kohde.kajakit
    if paikka.tyyppi == "retki":
        return ("slice", "riverrunner")
    nimi = kohde.nimi.lower()
    if (paikka.nimi.startswith("Neitikoski") or "hontto" in nimi or "stoppari" in nimi
            or kohde.nimi in ISOT_SURFFIT):
        return ("freestyle",)
    return ("slice",)


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
    kajakit: tuple[str, ...] = ()  # suositellut kajakkityypit (KAJAKKITYYPIT), paikallisen melojan mukaan;
                                   # tyhjä = oletus (kohteen_kajakit)


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
    def sijainti(self) -> tuple[float, float] | None:
        """(leveys, pituus) WGS84 – selain laskee tästä etäisyyden käyttäjän sijainnista."""
        return SIJAINNIT.get(self.nimi)

    @property
    def osm_sivu(self) -> bool:
        """Onko paikalla osm.fi-sivu (josta kaaviot tarkistetaan)?"""
        return "://www.osm.fi/" in self.url


VALILEHDET = ("peli", "retki", "ruotsi")


def nakyy(paikka: Paikka, valilehti: str | None) -> bool:
    """Näkyykö paikka välilehdellä: None/"" = Kaikki (Suomi), "peli", "retki", "ruotsi" tai
    "suosikit" (kaikki paikat; selain näyttää käyttäjän suosikit)."""
    if valilehti == "suosikit":
        return True
    if valilehti == "ruotsi":
        return paikka.maa == "SE"
    if paikka.maa != "FI":
        return False
    return valilehti not in ("peli", "retki") or paikka.tyyppi == valilehti


# Paikkojen sijainnit (leveys, pituus): osm.fi-sivujen karttamerkit, muille
# OpenStreetMapin paikannimet tai foorumiketjun karttalinkki (20.10.2026).
SIJAINNIT: dict[str, tuple[float, float]] = {
    "Kipinä (Iijoki)": (65.2838, 26.5408),
    "Koiteli (Kiiminkijoki)": (65.0982, 25.8144),
    "Matkakoski (Tornionjoki)": (66.1478, 23.9321),
    "Kattilakoski (Tornionjoki)": (66.5320, 23.7843),
    "Kukkolankoski (Tornionjoki)": (65.9627, 24.0388),
    "Vuentokoski (Tornionjoki)": (66.1753, 23.8366),
    "Hawa'Ii (Iijoki, Maalismaa)": (65.3041, 25.6929),
    "Pyhäjoki": (64.4566, 24.2509),
    "Siikajoki (Pöyryn pato)": (64.7513, 24.9245),
    "Niskakoski (Lestijoki)": (63.9898, 23.7600),
    "Neitikoski (Lieksanjoki)": (63.3903, 30.4500),
    "Trollforsarna (Piteälven)": (66.0178, 19.2878),
    "Taivalkoski": (65.5740, 28.2304),
    "Sanginjoki": (64.9985, 25.6988),
    "Kuivajoki": (65.6045, 25.1870),
    "Olhavajoki": (65.4734, 25.4156),
    "Simojoki": (65.6594, 25.0713),
    "Lieksanjoki (Matkalahti – Siikakoski)": (63.3901, 30.4541),
    "Liminganjoki": (64.8071, 25.4058),
    "Muhosjoki": (64.7480, 26.1337),
    "Temmesjoki": (64.7731, 25.5400),
    "Pahakurkkio (Kalixälven)": (67.3201, 22.1161),
    "Vikaköngäs (Raudanjoki)": (66.6188, 26.1859),
    "Korpikoski (Raudanjoki)": (66.6207, 26.2028),
    "Vaattunkiköngäs (Raudanjoki)": (66.6126, 26.1513),
    "Marraskoski (Ounasjoki)": (66.7947, 25.4176),
    "Molkoköngäs (Ounasjoki)": (67.0620, 25.0790),
    "Kutujoki": (64.6768, 27.0596),   # reitin alku Otermajärven luusuassa (osm.fi:n merkki Petäjäkoskella)
    "Oulujoki": (65.0005, 25.5643),
    "Oulun edustan saaret": (65.0227, 25.4240),
}

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
    "q5903470y": "Otermajärvi, luusua (Kutujoki)",
    "l592621001y": "Otermanjärvi",
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
            Kohde("Keskimmäisen silta-aukon hontto", (107.65, 108.2), (107.75, 108.0), 1.0,
                  huom="paras pelipaikka; yli 107.85 m ulkoreunaan surffattava aalto-osa "
                       "(Pilari 107.65–108.20 m, mpahkala.kapsi.fi)", lahde="meloja",
                  kajakit=("freestyle",)),
            Kohde("Oikean silta-aukon surffiaalto", (108.15, 108.8), (108.15, 108.6), 0.8,
                  huom="hidas surffiaalto, ei akanvirtaa (kanto 2–20 m); Sillanalus 108.25–108.60 m, "
                       "108.59 m optimin ylärajoilla (mpahkala.kapsi.fi)", lahde="meloja",
                  kajakit=("freestyle",)),
            Kohde("Ala-aallot (ykkös- ja kakkosaalto)", (106.7, 107.4), (106.7, 107.2), 0.85,
                  huom="parhaimmillaan 106.7–107.2 m (mpahkala.kapsi.fi); sopii myös koskisuppailuun; "
                       "nopea kajakki: half/full slice, Jackson Funin tapainen tai slalom – nykyaikainen "
                       "freestyle on hidas", lahde="meloja", kajakit=("slice",)),
        ),
    ),
    Paikka(
        "Koiteli (Kiiminkijoki)", "https://www.osm.fi/koiteli/", "peli", 25,
        "Paljon pieniä pelipaikkoja eri vesillä; Tulikurkku sopii aloittelijoille. "
        "Vettä yleensä kesäkuun alkuun.",
        {"paa": Mittari("60/q6000410y/wlyhyt.png", marginaali=0.3)},
        (
            Kohde("Helmihontto", (10.3, 10.75), (10.65, 10.75), 1.0,
                  huom="parhaimmillaan 10.7 m; kärrynpyörät, voltit; 10.37–10.45 m vähän pitoa "
                       "(mpahkala.kapsi.fi)", lahde="meloja", kajakit=("freestyle",)),
            Kohde("Etuaalto", (10.3, 10.75), (10.35, 10.75), 0.9,
                  huom="10.4 m:stä alkaen kärryttely ja voltti onnistuvat; 10.37 m ihan hyvä "
                       "(mpahkala.kapsi.fi)", lahde="meloja", kajakit=("riverrunner", "slice")),
            Kohde("Takaköngäs", (10.5, 11.05), (10.8, 11.05), 0.8,
                  huom="hyvä n. 11.0 m ja sen alle; 10.5 m:llä reunoilla kolisee", lahde="arvio",
                  kajakit=("riverrunner", "slice")),
            Kohde("Tukkirännin surffiaalto", (10.4, 10.6), (10.45, 10.55), 0.7,
                  huom="koskeen keskelle n. 10.5 m vedellä", lahde="arvio", kajakit=("riverrunner", "slice")),
            Kohde("Tulikurkku", (10.3, 11.0), (10.65, 10.75), 0.7,
                  huom="parhaimmillaan 10.7 m; sopii aloittelijoille", lahde="arvio",
                  kajakit=("riverrunner",)),
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
            Kohde("Matkan aalto", (27.7, 28.4), (27.9, 28.15), 0.9,
                  huom="27.90 m hyvä mutta kapea, alarajoilla; 28.07 m leveä (mpahkala.kapsi.fi)",
                  lahde="meloja"),
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
            Kohde("Ala-aalto", (78.85, 79.15), (78.85, 79.00), 0.9,
                  huom="parhaimmillaan 78.85 m; toimii 78.85–79.15 m (mpahkala.kapsi.fi)", lahde="meloja"),
            Kohde("Ala-aalto (matala vesi)", (78.20, 78.30), (78.23, 78.27), 0.9, huom="toimii n. 78.25 m"),
            Kohde("Grillikodan hontto", (78.90, 79.10), (78.95, 79.05), 0.6, huom="n. 79 m"),
            Kohde("Parkkihontto", (79.50, AVOIN), (79.50, AVOIN), 0.8, huom="mitä enemmän vettä sen parempi"),
            Kohde("Finnvågen", (80.00, AVOIN), (80.00, 80.80), 1.0,
                  huom="vaatii paljon vettä, parhaat surffit yli 3000 m³/s; paras 80.0–80.8 m "
                       "(mpahkala.kapsi.fi)", lahde="meloja"),
            Kohde("Svansteinin stoppari", (78.00, AVOIN), (79.00, AVOIN), 0.8,
                  huom="14 km ylävirtaan; sopii kaikentasoisille"),
            Kohde("Kattilakoski ja Svanstein (yleinen)", (78.00, 82.00), (78.00, 82.00), 0.5,
                  huom="toimiva vedenkorkeus 78.00–82.00 m (mpahkala.kapsi.fi)", lahde="meloja"),
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
            Kohde("Murtuva aalto", (650, 1300), (850, 1300), 1.0,
                  huom="n. 600 m³/s keula kolisee; 850 m³/s tosi hyvä ja paranee; "
                       "toimii 650–1300 m³/s, 645 m³/s matala (mpahkala.kapsi.fi)", lahde="meloja",
                  kajakit=("freestyle",)),
            Kohde("Kitula", (650, 1300), (650, 1300), 0.8,
                  huom="toimii 650–1300 m³/s (mpahkala.kapsi.fi); 607 m³/s keskiaallosta loppui pito, "
                       "645–649 m³/s matala", lahde="meloja", kajakit=("freestyle",)),
        ),
    ),
    Paikka(
        "Pyhäjoki", "https://www.osm.fi/pyhaejoki/", "peli", 110,
        "Ruukinkoski (stoppari/murtuva aalto) ja Saunarannan aalto. Kauden "
        "aloituspaikka, sesonki lyhyt. Mittarina Tolpankoski.",
        {"paa": Mittari("54/q5400410y/qinlyhyt.png", marginaali=20)},
        (
            Kohde("Ruukinkoski: stoppari / murtuva aalto", (40, 90), (45, 85), 0.8,
                  huom="akanvirta laskijan oikealla; takaisin melomalla; toimii 45–90 m³/s "
                       "(mpahkala.kapsi.fi)", lahde="meloja"),
            Kohde("Saunarannan aalto", (80, 150), (130, 150), 0.9,
                  huom="parhaimmillaan n. 140 m³/s; 170 m³/s liikaa"),
        ),
    ),
    Paikka(
        "Siikajoki (Pöyryn pato)", "https://www.osm.fi/melontapaikat/siikajoki/", "peli", 70,
        "Pöyryn padon alla monipuolinen koskialue: Vaahtokylpy ja Kalliosaaren "
        "paikat. Mittarina Länkelän virtaama; vedenkorkeus rinnalla (kuten Neitikoskella).",
        {"paa": Mittari("57/q5700700y/qinlyhyt.png", marginaali=40),
         "korkeus": Mittari("57/q5700700y/w3lyhyt.png", marginaali=0.3)},
        (
            Kohde("Vaahtokylpy (murtuva aalto)", (250, AVOIN), (300, 400), 1.0,
                  huom="loistava akanvirta, sopii vähemmän meloneillekin"),
            Kohde("Vaahtokylpy, kielen toinen puoli", (140, 250), (140, 200), 0.85,
                  huom="150 m³/s: hontto, jossa syvyyttä volteille", lahde="arvio"),
            Kohde("Kalliosaaren pelipaikat", (70, 250), (100, 250), 0.7,
                  huom="70 m³/s: keula kolisee upotuksessa; mukavia virranrajoja; hyvä yli 100 m³/s "
                       "(mpahkala.kapsi.fi)", lahde="meloja"),
            Kohde("Aalto 5 km alavirtaan", (150, AVOIN), (150, AVOIN), 0.7, huom="aaltoon pitää kantaa"),
            Kohde("Koskialue vedenkorkeuden mukaan", (19.50, 21.00), (19.70, 21.00), 0.8, mittari="korkeus",
                  huom="toimiva vedenkorkeus 19.50–21.00 m NN; 19.57 m matala, 19.75–19.79 m hyvä "
                       "(mpahkala.kapsi.fi)", lahde="meloja"),
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
        "Lähes joen levyinen aalto/stoppari, lyhyet uinnit (päättyy järveen). Toimii sulan "
        "veden aikaan lähes aina. Rajat koskimelonta.com:sta (Ruunaan virtaama).",
        # Pääreferenssi: koskimelonta.com/kosket/lieksanjoki-neitikoski/ (Olli Nyrhilä 2014),
        # rajat virtaamana (SYKE Lieksanjoki, Ruunaa) ja sillan/laiturin mittarina.
        {"paa": Mittari("04/q0400600y/qinlyhyt.png", lisakaavio=True, marginaali=15),
         "korkeus": Mittari("04/q0400600y/wlyhyt.png")},
        (
            Kohde("Aalto (aaltoliikkeet)", (40, AVOIN), (120, AVOIN), 1.0,
                  huom="yli 120 m³/s (laituri n. 9,5) jyrkempi aalto, aaltoliikkeet onnistuvat "
                       "helpommin; meloa voi vielä 40 m³/s:llä (laituri n. −1)"),
            Kohde("Murtuva aalto (voltit)", (100, 125), (105, 120), 0.85,
                  huom="yli 110 m³/s (sillan mittari n. 8) aaltomainen mutta murtuu pohjalle; "
                       "aaltoliikkeisiin räjähtävä melonta, oivallinen volttien harjoitteluun"),
            Kohde("Metsänlaidan hontto ja laiturin puolen aalto", (40, 100), (40, 100), 0.8,
                  huom="alle 100 m³/s metsänlaitaan hontto, keskelle kieli; matalalla keula "
                       "tai mela kolahtaa pohjaan"),
        ),
    ),
    Paikka(
        "Trollforsarna (Piteälven)", "https://tuusmelojat.fi/trollit-2017/", "peli", 450,
        "Ruotsi: Piteälvenin koskiosuus Granselin mittarin kohdalla, isoja aaltoja ja "
        "laskettavaa eri vesillä, paras kausi kesäkuu. Rajat paikalliselta kokeneelta "
        "melojalta (SMHI Gransel), kuvaukset myös Forsguidenista.",
        {"paa": Mittari("smhi/1387/31914", marginaali=60)},
        (
            Kohde("Paltvalsen (iso aalto)", (170, AVOIN), (190, 240), 1.0,
                  huom="parhaimmillaan 190–240 m³/s, toimii n. 170:stä", lahde="meloja"),
            Kohde("Glashällen (pieni aalto)", (220, AVOIN), (320, 360), 0.8,
                  huom="toimii n. 220–400+, parhaimmillaan n. 340; ylärajaa ei tiedetä; "
                       "Benbrytarforsenin alapäässä, sileä aalto, sopii vasemman käden bluntteihin",
                  lahde="meloja"),
            Kohde("Yläpätkä (Delta / keskiränni)", (140, 300), (140, 300), 0.9,
                  huom="yli 300 m³/s karvainen; Forsguiden: Björnidedeltat toimii parhaiten pienemmällä "
                       "vedellä", lahde="meloja"),
            Kohde("Satumaa (Sagoland)", (140, 300), (140, 300), 0.7,
                  huom="samat vedet kuin Yläpätkällä, mutta helpompi", lahde="meloja"),
            Kohde("Alapätkä (Nedre Trollforsarna)", (AVOIN, AVOIN), (300, AVOIN), 0.8,
                  huom="aina hyvä, parempi yli 300 m³/s", lahde="meloja"),
            Kohde("Benbrytarforsen", (AVOIN, 150), (AVOIN, 130), 0.8,
                  huom="hyvä alle 130 m³/s, enintään n. 150; Forsguiden: IV–VI, hyvin pyörteiset "
                       "akanvirrat, iso imevä valssi", lahde="meloja"),
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
            Kohde("Koskiosuus Lemmenpolku – Taivalkoski", (6, AVOIN), (10, AVOIN), 0.8,
                  huom="vähintään 8 m³/s (osm.fi), toimii yli 6 m³/s (mpahkala.kapsi.fi); "
                       "parhaimmillaan reilusti yli 10 m³/s", lahde="meloja"),
        ),
    ),
    Paikka(
        "Kuivajoki", "https://www.osm.fi/kuivajoki/", "retki", 75,
        "Laskettavissa n. 3 vk jäiden lähdöstä; paras osuus 17 km Hyryn kylältä. "
        "Mittarina Ravaska.",
        {"paa": Mittari("63/q6300210y/wlyhyt.png", marginaali=0.3)},
        (
            Kohde("Koskiosuus (Hyry – Kuivaniemi)", (27.6, AVOIN), (28.0, AVOIN), 0.8,
                  huom="n. 28 m: pienempää aaltoa ja kivien kiertelyä; hyvä yli 28.0 m "
                       "(mpahkala.kapsi.fi)", lahde="meloja"),
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
        "Pahakurkkio (Kalixälven)", "https://freestylemelonta.blogspot.com/2010/09/synkkaa-kuin-moron-pers.html", "retki", 370,
        "Ruotsi, Saittarova (Pajala): kanjonissa seitsemän kosken sarja 3–4 km ja "
        "ykköskönkään Åretsvågen, yksi maailman parhaista surffiaalloista. Kosket 1–3 n. III, "
        "4 hontto oikealla, 5 vaikein, 6–7 IV. Mittarina Männikkö (15 km alavirtaan). "
        "Yli n. 220 m³/s kosket isoja ja vitonen V-luokkaa.",
        {"paa": Mittari("smhi/11/35732", marginaali=30)},
        (
            Kohde("Åretsvågen (ykköskönkään surffiaalto)", (180, 260), (190, 235), 1.0,
                  huom="Männikkö 191 m³/s optimi ja 212 vähän yli (6/2012), 226–235 parhaimmillaan "
                       "(6/2013), 218 hyvä (7/2010); paras laskevalla vedellä", lahde="arvio"),
            Kohde("Koskisarja 1–7", (70, 220), (80, 190), 0.8,
                  huom="77–87 m³/s syysvesi helpompi (9/2010), 96 'lähes optimaalinen' (8/2010), "
                       "191 hyvä eikä kaoottinen (6/2012); 218 vitonen V-luokkaa", lahde="arvio"),
            Kohde("Ykköskönkään hontto ja aalto matalalla", (65, 110), (72, 90), 0.8,
                  huom="77–87 m³/s lähes kaikki honttoliikkeet onnistuivat, aalto parhaimmillaan "
                       "matalimmalla (9/2010)", lahde="arvio"),
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
        "Kutujoki", "https://www.osm.fi/kutujoki/", "retki", 110,
        "Melontareitti Kutujoen alkupää (Otermajärven luusua) – Järvikylä n. 17 km, 15 koskea, "
        "joista II-luokkaa Myllykoski, "
        "Monisaarikoski ja Petäjäkoski (1 400 m), muut I-luokkaa. Hyvä aloitteleville ja "
        "retkeilijöille, paras alkukesällä. Mittarina Otermajärven lähtövirtaama (luusua), "
        "järven vedenkorkeus rinnalla. Järvikylästä takaisin Ouluun n. 87 km.",
        # Sivulla ei vesikaaviota eikä lukuja. Rajat ovat arvioita aseman tunnusluvuista
        # (MNQ 1.2, MHQ 18.1, HQ 44.0 m³/s) ja havaintojen mediaanista: kesäkuun alussa
        # n. 8–10 m³/s ("paras alkukesällä"), heinä–elokuussa 2–3 m³/s.
        {"paa": Mittari("59/q5903470y/qin3lyhyt.png", lisakaavio=True, marginaali=3),
         "korkeus": Mittari("59/l592621001y/w3lyhyt.png", lisakaavio=True)},
        (
            Kohde("Kutujoen alkupää – Järvikylä (17 km)", (4, 30), (7, 16), 0.8,
                  huom="kapea (5–10 m) joki: alle n. 4 m³/s (kesän alivesi) kivikkoista; "
                       "tulvalla inkkarin paattiin voi tulla aalto (osm.fi)", lahde="arvio"),
            Kohde("II-luokan kosket (Myllykoski, Monisaarikoski, Petäjäkoski)", (5, 30), (8, 18), 0.7,
                  huom="Myllykoski heti alussa, Petäjäkoski 1 400 m; vähällä vedellä kivisiä, "
                       "yli MHQ:n (18 m³/s) vauhdikkaita aloittelijalle", lahde="arvio"),
        ),
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
