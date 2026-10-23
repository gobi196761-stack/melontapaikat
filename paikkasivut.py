"""Paikkasivujen (/paikka/<tunniste>) koostetekstit.

Jokaisesta paikasta on koottu kuvaus osm.fi:n paikkasivuista, Rovaniemen Melojien
foorumista, koskimelonta.comista, Suomen freestylemelontamaajoukkueen blogista
(freestylemelonta.blogspot.com), Tuomas Vaaralan melontapäiväkirjasta
(tuorala.wordpress.com), mpahkala.kapsi.fi:n melontaraportista ja muista
lähteistä (luettu 10/2026). Tekstit ovat lähteiden tiivistelmiä omin sanoin;
vedenkorkeudet ja virtaamat ovat lähteiden lukuja ja niiden ajankohta on
kerrottu, kun se on tiedossa. Kohteiden toimintarajat sivulle tulevat suoraan
paikat.py:stä, joten ne eivät ole tässä tiedostossa.

Sivun rakenne: johdanto, otsikolliset osiot (kappaleet erotettu tyhjällä
rivillä) ja lopuksi lähteet (otsikko, osoite).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Kuvaus:
    johdanto: str
    osiot: tuple[tuple[str, str], ...] = ()
    lahteet: tuple[tuple[str, str], ...] = ()


def tunniste(nimi: str) -> str:
    """Paikan nimi URL-muotoon: "Hawa'Ii (Iijoki, Maalismaa)" -> "hawa-ii-iijoki-maalismaa"."""
    ascii_ = unicodedata.normalize("NFKD", nimi).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


FSB = "https://freestylemelonta.blogspot.com/"
TUORALA = "https://tuorala.wordpress.com/"
KAPSI = ("Melontaraportti (mpahkala.kapsi.fi): melontapäiväkirjan vesilukemat",
         "https://mpahkala.kapsi.fi/melontaraportti.html")
KM_TORNIONJOKI = ("koskimelonta.com: Tornionjoki (vanhat koskiesittelyt)",
                  "https://koskimelonta.com/kosket/vanhat-koskiesittelyt/lappi/tornionjoki/")
TUORALA_KATTILA_REF = ("Tuorala: Kattilakosken definitiivinen vedenkorkeusreferenssi (2011)",
                       TUORALA + "2011/05/25/kattilakosken-definitiivinen-vedenkorkeusreferenssi/")
NEITI_SAANNOT = (
    "Lieksanjoella on kesäisin paljon koskenlaskuyrittäjien veneitä, joten Neitikoskelle on sovittu "
    "melamerkit. Ylävirrasta tuleva alus (kajakki, kanootti, kumi- tai puuvene) nostaa melan tai airon "
    "pystyyn hyvissä ajoin ennen koskea. Kosken alla olevat melojat vastaavat: pystysuora mela = koski on "
    "vapaa, laske; vaakasuora mela = koskessa on melojia, odota. Lupa tulee yleensä alle minuutissa.")


def _roimeloo(t: int, otsikko: str) -> tuple[str, str]:
    return (f"Rovaniemen Melojien foorumi: {otsikko} (PasiK 2020)",
            f"https://roimeloo.net/keskustelu/viewtopic.php?f=15&t={t}")


KUVAUKSET: dict[str, Kuvaus] = {
    # ------------------------------------------------------------------
    "Kipinä (Iijoki)": Kuvaus(
        "Iijoen Kipinänkoski Pudasjärvellä on monen oululaisen melojan kantapaikka: melottavaa löytyy läpi "
        "kesän, joelle pääsee helposti ja akanvirrat ovat selkeät. Aallot ja stopparit eivät ole Suomen "
        "suurimpia, mutta koski sopii mainiosti taitojen ylläpitoon, eikä uinti ole yleensä vaarallinen. Jää "
        "siirtelee kosken kiviä, joten pelipaikat muuttuvat muutaman vuoden välein.",
        (
            ("Perille",
             "Oulusta noin 45 minuuttia: Kuusamontietä noin 60 km ja vasemmalle Kipinän kylään. Parin "
             "kilometrin päästä tie ylittää Iijoen – koski on sillan alla. Auton voi jättää sillan jälkeiselle "
             "bussipysäkille. Kosken alapuolisesta venevalkamasta kävellään pellon poikki takaisin."),
            ("Pelipaikat",
             "Keskimmäinen silta-aukko on Kipinän paras pelipaikka. Vuonna 2020 sen sivuun muodostunut hontto "
             "toimi erinomaisesti Pudasjärven lukemilla 107.7–108.1 m. Lukemalla 107.7 m honton alla on jo "
             "matalaa, ja kypärä ja mela voivat kolista. Upotukset kannattaa tehdä honton ulkoreunasta, "
             "koska pilarin puoli on matala. Yli 107.85 m:n vedellä stopparin ulkoreunaan tulee kapea mutta "
             "helposti surffattava aalto-osa. Akanvirta siltapilarin alla on pitkä ja rauhallinen.\n\n"
             "Oikeanpuoleisimpaan silta-aukkoon rannan viereen syntyy korkealla vedellä (108.1–108.9 m) hidas "
             "surffiaalto, joka muuttuu veden laskiessa stopparimaisemmaksi. Akanvirtaa ei ole, mutta kantomatka "
             "on vain 2–20 metriä. Alle 108.1 m:n vedellä aallon alla on liian matalaa.\n\n"
             "Ala-aallot ovat Kipinän perinteisimmät pelipaikat, mutta vuoden 2018 kevättulva madalsi koko "
             "aaltojonoa selvästi. Ykkösaaltoa voi surffata pelipaatilla noin 107.3–107.8 m:n vedellä. Ennen "
             "vuotta 2018 jo 107.25 m oli erinomainen aaltoliikkeille, nykyään sillä on nojattava voimakkaasti "
             "eteen. Pidemmillä kajakeilla ykkös- ja kakkosaaltoa voi surffata alle 107.3 m:n vedellä aina "
             "106.8 m:iin asti. Alle 107.7 m:n vedellä ykkösaaltoon pääsee surffarin vasemmasta akanvirrasta, "
             "mutta se on haastavaa; oikeasta akanvirrasta pääsee molempiin aaltoihin alle 107.4 m:n vedellä. "
             "Ala-aallot sopivat myös koskisuppailuun."),
            ("Vesitilanne",
             "Tulva-aikaan Kipinä on tasainen ja aaltoihin pääseminen on työlästä, mutta tilanne paranee veden "
             "laskettua. Seuraa Pudasjärven vedenkorkeusmittaria: Kipinän omat laskennalliset virtaamatiedot "
             "eivät perustu mittariin eivätkä ole luotettavia. Ajantasaista tietoa voi kysyä myös Pohjolan "
             "Voimalta, puh. 050 313 3306."),
        ),
        (("osm.fi: Kipinä", "https://www.osm.fi/melontapaikat/kipinae/"), KAPSI),
    ),
    # ------------------------------------------------------------------
    "Koiteli (Kiiminkijoki)": Kuvaus(
        "Koiteli ja noin 400 m sen yläpuolella oleva Tulikurkku ovat Kiiminkijoella Kiimingissä, noin 25 "
        "minuutin ajomatkan päässä Oulusta. Mega-aaltoja tai suuria pelihonttoja ei ole, mutta avoimin mielin "
        "jokaisesta uomasta löytyy pieniä pelipaikkoja eri vesillä, ja koskessa on hyvä harjoitella "
        "laskemista. Vettä riittää yleensä kesäkuun alkupäiviin, sateisina kesinä pidempäänkin. Huipputulvalla "
        "koskessa on hyvin pitäviä pour overeita – vuoden 2010 tulvahuipussa 20.4. vedenkorkeus oli noin 11.6 m "
        "ja virtaama 250 m³/s.",
        (
            ("Pelipaikat",
             "Tukkiränni (takimmainen uoma) on mukava laskea isojen aaltojensa takia. Melko alas syntyy "
             "surffiaalto sekä korkealla että matalalla vedellä, ja noin 10.5 m:n vedellä surffiaalto myös "
             "kosken keskelle.\n\n"
             "Takaköngäs on Tukkirännin takana sivu-uomassa heti sillan alla: noin metrin könkään alle "
             "muodostuu pieni, Taivalkosken tapainen hontto. Sitä on hyvä pelata noin 11.0 m:n vedellä ja sen "
             "alle. 10.5 m:llä hontto on vielä keskeltä syvä, mutta reunoilla kolisee.\n\n"
             "Etuaalto ja Helmihontto toimivat ainakin 10.3–11.0 m:n vedellä. Etuaalto on kosken keskellä, "
             "ensimmäisenä parkkipaikalta alavirtaan meloessa. Laskusuunnassa oikea laita on honttomainen, ja "
             "jo 10.4 m:llä siinä voi kärrytellä ja tehdä voltin. Helmihontto on aallosta alavirtaan oikealla "
             "saaren rannassa ja parhaimmillaan 10.7 m:n vedellä. Veden laskiessa se muuttuu huuhtovammaksi "
             "mutta pysyy melottavana. Honton takana oleva pieni pour over ei ole vaarallinen. Se hidastaa "
             "virtausta niin, että akanvirtaan ehtii helposti. Hontossa on hyvä harjoitella kärrynpyörää, split "
             "wheeliä, volttia ja space godzillaa, mutta se ei ole kovin pitävä, joten liikkeiden on oltava "
             "tarkkoja.\n\n"
             "Tulikurkkuun pääsee vain melomalla. Kanna kajakki Tukkirännin yli siltaa pitkin ja seuraa "
             "rantapolkua ylävirtaan pellolle, josta näkyy Myllysaari. Melo ensimmäisen väylän yli saaren "
             "alapuolelle ja saaren rantaa ylävirtaan. Kallioiden väliseen kapeikkoon syntyy pieni aalto, jossa "
             "on hyvä akanvirta. Se on tarkka vedenkorkeudelle ja parhaimmillaan 10.7 m:n vedellä; veden "
             "laskiessa aalto madaltuu, mutta paikka pysyy hyvänä harjoitteluun. Tulikurkku sopii toisin kuin "
             "muut Koitelin paikat myös aloittelijoille."),
            ("Kokemuksia",
             "Keväällä 2010 freestylemaajoukkue piti Koiteliä Pohjois-Pohjanmaan parhaana treenipaikkana, koska "
             "Taivalkoskella oli liikaa ja Hawa'Iilla liian vähän vettä eikä Tornionjoelle päässyt vielä. Veden "
             "laskettua löytyi uusi Helmihontto, ja helatorstain viikonloppuna takimmaisessa portaassa oli hyvä "
             "kärrytellä pitävässä hontossa, jossa akanvirrat olivat molemmin puolin."),
        ),
        (("osm.fi: Koiteli", "https://www.osm.fi/koiteli/"),
         ("Freestylemelonta-blogi: Vesitilanne ei suosi (10.5.2010)", FSB + "2010/05/vesitilanne-ei-suosi.html"),
         ("Freestylemelonta-blogi: Uusia kuvia Koitelin koskelta (15.5.2010)",
          FSB + "2010/05/uusia-kuvia-koitelin-koskelta.html"),
         KAPSI),
    ),
    # ------------------------------------------------------------------
    "Matkakoski (Tornionjoki)": Kuvaus(
        "Tornionjoen Matkakoski Ylitorniolla on rajajoen klassikko, josta löytyy aina melottavaa. Kevättulva on "
        "oma lukunsa: muualta Suomesta tuskin löytyy yhtä paljon vettä, yhtä suuria aaltoja ja stoppareita – "
        "'Zambezi-meininkiä', varsinkin jos lähtee 6 km ylempää Vuennonkoskelta. Varsinainen pelikausi on "
        "loppukesällä ja syksyllä, kun joen vesi on matalimmillaan.",
        (
            ("Vedenkorkeus ja pelipaikat",
             "Tulvan tunnistaa kosken keskellä olevasta kalliosta: jos sitä ei näy, vettä on yli 31 m (vanhalla "
             "automaatilla 500 cm). Yli 28 m:n vedellä (automaatti 190–200 cm) pelipaikkoihin pudotetaan "
             "ylhäältä, eikä takaisin pääse melomalla – kantamiseksi menee. Paras aika alkaa, kun vesi laskee "
             "alle 28 m:n (180 cm) ja paikoille pääsee takaisin melomalla; ihanteellinen lukema on noin "
             "27.5–27.8 m.\n\n"
             "Peliaikana Suomen puolen niskalla on iso, noin 15–20 metriä leveä stoppari ja Ruotsin väylässä "
             "iso, nopea aalto. Suomen väylässä on pienempi stoppari ja aivan Suomen rannassa pieni WC-Duck-"
             "tyyppinen pour over -hontto. Kun automaatti näyttää 93–140 cm, Ruotsin aalto huononee, mutta "
             "ylähontto pelaa vähälläkin vedellä. Varsakallion hontto on 'aika miehekäs' (2010)."),
            ("Vaarat",
             "Ei aloittelijoille eikä huonoille aukkopeitoille – vaarallisia paikkoja on. Varo erityisesti "
             "kosken keskellä olevan kallion vierustoja, varsinkin Ruotsin puolta. Uintireissusta tulee pitkä. "
             "Veden laskiessa ison honton Ruotsin reuna muuttuu vaarallisen näköiseksi montuksi, ja lippoamiseen "
             "käytetyt köydet voivat aiheuttaa hankaluuksia."),
            ("Kokemuksia",
             "25.5.2010 virtaama oli noin 2300 m³/s. Vuennonkoskessa oli talon kokoisia aaltoja ja synkkiä "
             "pyörteitä, ja Matkakoski tarjosi blogin mukaan 'suurinta mämmiä mitä Suomesta löytyy': surffit "
             "olivat lähinnä selviytymistaistelua. Syyskuussa 2010 (27.7 m, noin 335 m³/s) Ruotsin aalto oli "
             "vaikea, ja lokakuussa (27.2 m, noin 210 m³/s) hontto oli hyvä voltteihin.\n\n"
             "Syyssateet 2009 nostivat vettä juuri sopivasti Ruotsin aallolle: 'hyvänä päivänä se tuo hymyn "
             "melojan suulle, huonona päivänä se murtaa parhaimmankin melojan itsetunnon'. Toukokuussa 2014 "
             "aaltokausi avattiin heti jäiden lähdettyä Ruotsin aallossa, ja heinäkuussa 2014 sekä Ruotsin "
             "että Suomen puolen aalto toimivat. Molempiin joutui kantamaan, mutta se oli sen arvoista."),
        ),
        (("osm.fi: Matkakoski", "https://www.osm.fi/matkakoski/"),
         ("Freestylemelonta-blogi: Matkakoski big water (25.5.2010)", FSB + "2010/05/matkakoski-big-water.html"),
         ("Freestylemelonta-blogi: Matkakosken kaudenavaus (25.7.2010)",
          FSB + "2010/07/matkakosken-kaudenavaus.html"),
         ("Freestylemelonta-blogi: Matkakoski 21.9.2009", FSB + "2009/09/matkakoski.html"),
         ("Freestylemelonta-blogi: Aaltokauden avaus (11.5.2014)", FSB + "2014/05/aaltokauden-avaus.html"),
         ("Freestylemelonta-blogi: Melonnan riemua Matkakoskella (13.7.2014)",
          FSB + "2014/07/melonnan-riemua-matkakoskella.html"),
         ("Tuorala: Vuennonkoski ja Matkakoski 25.5.2010",
          TUORALA + "2010/06/04/vuennonkoski-ja-matkakoski-25-5-2010/"),
         ("Tuorala: Matkakoski 22.9.2010", TUORALA + "2010/09/22/matkakoski-22-9-2010/"),
         ("Tuorala: Matkakoski 16.10.2010", TUORALA + "2010/10/18/matkakoski-16-10-2010/"),
         KAPSI),
    ),
    # ------------------------------------------------------------------
    "Kattilakoski (Tornionjoki)": Kuvaus(
        "Tornionjoen Kattilakoski on isolla vedellä Suomen paras freestylepaikka: 'Kattilakoskelta löytyy niin "
        "paljon melottavaa, ettei kunto riitä.' Koskelle ajetaan Övertorneåsta Ruotsin puolen jokivartta "
        "ylöspäin noin 20 km; rannassa on ravintola, parkkipaikka ja lämpimät vessat. Oulusta on matkaa noin "
        "230 km. Koski alkaa ravintolan kohdalta, ja viimeinen pelipaikka on noin 1,5 km alempana, jonne "
        "pääsee myös autolla (lähtöpaikasta takaisinpäin ensimmäinen tie vasemmalle, kyltti Maunu). Koski "
        "toimii vain riittävän korkealla vedellä: kausi on kevättulvan aikaan, heinäkuussa tuskin enää "
        "kannattaa vaivautua.",
        (
            ("Pelipaikat ylhäältä alas",
             "Hevosenkenkä: kosken alun kalliosaaren Ruotsin väylässä on tulvalla koko väylän levyinen, tosi "
             "miehekäs hevosenkengän muotoinen stoppari, jonka keskellä on iso kieli. Veden laskiessa siitä tulee "
             "hyvä pelipaikka, jossa kärrynpyörät ja voltit onnistuvat. Stopparin taakse muodostuu oikealla "
             "vedellä pieni kakkosaalto, joka on hyvin herkkä vedenkorkeuden muutoksille ja kaatuu pohjaan, jos "
             "vettä on liikaa. Sopivalla vedellä siinä onnistuu jokainen aaltoliike.\n\n"
             "Saaren alaosassa Ruotsin puolella on tulvalla mystinen hontto (mystery hole), joka katoaa välillä "
             "kokonaan ja ilmestyy hetken päästä uudelleen. Saaren Suomen väylässä on vauhdikas murtuva "
             "mega-aalto, 'jossa sattuu ja tapahtuu'. Kosken puolivälissä Suomen puolella on iso köngäs, joka "
             "kannattaa tarkistaa ennen laskua; sen alle tulee keskikokoinen, aika pitävä stoppari.\n\n"
             "Finnvågen on noin puoli kilometriä kosken alusta alaspäin Suomen puolella: iso, nopea aalto, joka "
             "vaatii paljon vettä ja katoaa veden vähetessä. Isolla vedellä takaisin pääsee vain kantamalla. "
             "Ruotsin reunassa on parkkihontto, jonka viereen pääsee autolla – isolla vedellä tosi hyvä "
             "treenipaikka. Ruotsin rannalla parkkipaikan kohdalla on myös makkarahontto (tarvitsee paljon "
             "vettä, sopii aloittelijoille). Alempana grillikodan kohdalla on pieni stoppari, jossa voi "
             "spinnailla ja kärrytellä. Viimeinen hyvä paikka on ala-aalto päävirrassa kalliosaaren Suomen "
             "puolella; parhaimmillaan se on pehmeä, loiva ja pitävä, ja siihen pääsee sivuaallon kautta.\n\n"
             "Svansteinin stoppari on noin 14 km ylävirtaan Svansteinin kylän yläpuolella. Lähde uimarannalta "
             "kirkkoa vastapäätä, melo ylävirtaan ja lossaa saaren reunaan, josta akanvirta vie stopparille "
             "(saaren ja Ruotsin rannan välissä). Paikka sopii kaikentasoisille ja on erinomainen "
             "stopparimelonnan harjoitteluun."),
            ("Vaarat ja vinkit",
             "Niskan stopparin reunoissa on kova takaisinveto: jos kontrolli lähtee, edessä on uinti. Kosken "
             "puolivälin Suomen puoleinen köngäs voi olla vaarallinen väärästä kohdasta laskettuna. Muuten uinti "
             "on suhteellisen turvallista, koska akanvirrat ovat isoja ja kamppeet ehtii kerätä. Jos lepuutat "
             "jalkoja keskikalliolla, vedä kajakki reilusti vesirajan yläpuolelle – maininki voi viedä kamat. "
             "Keväällä jäitä voi tulla aallon läpi."),
            ("Kokemuksia ja tulvat",
             "Toukokuussa 2010 kausi avattiin helteessä: hevosenkengän kakkosaalto oli juuri sopivalla vedellä, "
             "ja 17.5. ala-aalto ja mega-aalto olivat parhaimmillaan. Freestylen SM-kisat 2011 pidettiin "
             "Kattilakoskella grillikodan hontossa, kun ala-aallosta jäi puuttumaan vain senttejä. Toukokuussa "
             "2012 Finnvågen toimi vain päivän, koska vesi jäi ennustettua matalammalle.\n\n"
             "Toukokuussa 2023 Tornionjoella oli mittaushistorian suurin tulva. Finnvågen oli yli kolme metriä "
             "korkea, mutta sille tyypillinen jatkuva pumppaaminen alkoi 3000 m³/s:n yläpuolella jopa lisääntyä, "
             "ja 3500 m³/s:llä aalto kävi välillä aggressiivisena honttona. Parhaaksi osoittautui noin "
             "2850 m³/s, mutta silloinkin maagiset paikat vaativat minuuttien surffausta ja oikeaa ajoitusta. "
             "osm.fi:n mukaan parhaat surffit on saatu yli 3000 m³/s:n virtaamilla."),
        ),
        (("osm.fi: Kattilakoski", "https://www.osm.fi/kattilakoski/"),
         ("Video: Kattilakosken freestylemelontapaikat (HeikkiR, Vimeo)", "https://vimeo.com/258468708"),
         KM_TORNIONJOKI,
         TUORALA_KATTILA_REF,
         ("Tuorala: Freestyle ja BoaterX SM-kilpailut 28.–29.5.2011",
          TUORALA + "2011/09/20/freestyle-ja-boaterx-sm-kilpailut-28-29-5-2011/"),
         ("Tuorala: Tulvaturnee 2011 – Kattilakoski", TUORALA + "2011/06/20/tulvaturnee-2011-kattilakoski/"),
         ("Tuorala: Kattilakoski 22.5.2014", TUORALA + "2014/05/28/kattilakoski-22-5-2014/"),
         ("Freestylemelonta-blogi: Kattilakosken kaudenavaus (16.5.2010)",
          FSB + "2010/05/kattilakosken-kaudenavaus.html"),
         ("Freestylemelonta-blogi: Vuoden ensimmäiset aaltomelonnat (20.5.2010)",
          FSB + "2010/05/vuoden-ensimmaiset-aaltomelonnat.html"),
         ("Freestylemelonta-blogi: Sillä välin Kattilakoskella (23.5.2012)",
          FSB + "2012/05/silla-valin-kattilakoskella.html"),
         ("Freestylemelonta-blogi: Kattilakosken ala-aalto ja Kelokurkkio (19.5.2013)",
          FSB + "2013/05/kattilakosken-ala-aalto-ja-kelokurkkio.html"),
         ("Freestylemelonta-blogi: Koeajo Lapin aalloista (22.5.2023)",
          FSB + "2023/05/koeajo-lapin-aalloista.html"),
         KAPSI),
    ),
    # ------------------------------------------------------------------
    "Kukkolankoski (Tornionjoki)": Kuvaus(
        "Kukkolankoski on Tornionjoella noin 15–20 km Torniosta Ylitornion suuntaan. Se on isoaaltoinen, "
        "vaikuttavan kokoinen koski – vastarannalle on useampi sata metriä – ja lähinnä läpilaskupaikka. "
        "Leikkipaikkoja ei juuri ole, varsinkaan isolla vedellä. Koski tunnetaan siian lippoamisesta, "
        "ja molemmilla rannoilla on palveluita: Ruotsin puolella Kukkolaforsenin leirintäalue ravintoloineen ja "
        "saunoineen, Suomen puolella Koskipirtti ja kahvila.",
        (
            ("Pelipaikat",
             "Kosken yläosassa Suomen puolella on pitkä kallio, jonka kummallekin reunalle tulee leikkipaikka, "
             "kun Matkakosken vedenkorkeus on 28–28.7 m (vanha automaatti 200–270 cm). Suomen reunan pieni "
             "hontto on hyvä spinnailuun, mutta pito ei riitä pystyliikkeisiin, akanvirta on lyhyt ja alla on "
             "kaksi matalaa stopparia, joten eskimo on tehtävä nopeasti. Kallion Ruotsin reunassa on hyvä "
             "surffiaalto, mutta akanvirta on tosi lyhyt. 29.2 m:llä (320 cm) vettä on liikaa. Kosken "
             "loppuosassa on isoja aaltoja, ja keskellä olevassa isossa, vähän murtuvassa aallossa saa hyvät "
             "surffit, jos uskaltaa."),
            ("Laskeminen",
             "Kajakit voi kantaa Koskipirtin parkkipaikalta rantaa pitkin niskalle (kysy kulkulupa talon "
             "asukkailta) tai ajaa Koskipirtiltä reilut sata metriä eteenpäin rantaan vievälle tielle, jonka "
             "päässä on vanha tullin vartiomaja. Ensimmäisellä kerralla kannattaa linjata niskan kallion "
             "oikealta puolelta (ylävirrasta katsoen) ja pysyä melko lähellä vasenta rantaa: aivan rannassa on "
             "stoppareita, mutta 5–10 m ulompana on hyvä laskureitti. Jos niskalla joutuu uimaan, uintireissu "
             "voi olla pitkä. Aloittelijalle pelipaikat ovat hankalia, mutta laskemiseen koski sopii "
             "kokemattomammallekin.\n\n"
             "Tuus-Melojat laski heinäkuussa 2017 kosken Ruotsista Suomeen jäätelölle ja takaisin: ensin "
             "suojaan ensimmäisen saaren taakse pienen pudotuksen jälkeen ja sitten suoraviivaisesti "
             "vastarannalle ennen kuin virta vie liian alas. Laskun loppupuolella oli hienot korkeat aallot."),
            ("Kokemuksia",
             "Heinäkuussa 2014 maajoukkuemelojat surffasivat 'Gladiaattori-aaltoa': hitaassa ja pienessä "
             "aallossa onnistuivat hontto- ja aaltoliikkeet, mutta parhaiten se sopi spinnailuun. Paikka on "
             "mukava, akanvirrallinen vaihtelu Matkakosken jälkeen."),
        ),
        (("osm.fi: Kukkolankoski", "https://www.osm.fi/kukkolankoski/"),
         KM_TORNIONJOKI,
         ("Tuus-Melojat: Trollit 2017 (Kukkolankosken lasku)", "https://tuusmelojat.fi/trollit-2017/"),
         ("Freestylemelonta-blogi: Kukkolankosken Gladiaattori (13.7.2014)",
          FSB + "2014/07/kukkolankosken-gladiaattori.html"),
         ("Freestylemelonta-blogi: Freestyleä ja kärpäsiä Kukkolankoskella (2010, video)",
          FSB + "2010/06/freestylea-ja-karpasia-kukkolankoskella.html")),
    ),
    # ------------------------------------------------------------------
    "Vuentokoski (Tornionjoki)": Kuvaus(
        "Vuennonkoski on Tornionjoella noin 6 km Matkakoskelta ylöspäin. Siinä on isoja aaltoja ja "
        "stoppareita, mutta akanvirtoja ei ole, joten monttuihin ja aaltoihin pudotetaan ylhäältä – katso "
        "ensin, minne menet. Lähtöpaikka on leirintäalueella, jonne on kesällä viitat tieltä. Väli "
        "Vuennonkoskelta Matkakoskelle on melkein kokonaan virtaavaa vettä: hyvä ja nopea jokipätkä.",
        (
            ("Vesimäärät",
             "Matkakosken vedenkorkeudella 28.7 m pätkällä on mukavia pelipaikkoja, mutta 28.2 m:llä ei juuri "
             "enää kannata lähteä laskemaan. Tulva-aikaan Vuennon–Matkakosken väli on 'jännä paikka'. Tuomas "
             "Vaarala kuvasi 25.5.2010 (noin 31 m, 2300 m³/s) laskua yhdeksi Suomen parhaista isoveden "
             "pätkistä: alkupalaksi talon kokoisia aaltoja, isoja honttoja, jotka kierrettiin kaukaa, ja "
             "melko synkän oloisia pyörteitä."),
        ),
        (("osm.fi: Vuentokoski", "https://www.osm.fi/vuentokoski/"),
         ("Tuorala: Vuennonkoski ja Matkakoski 25.5.2010",
          TUORALA + "2010/06/04/vuennonkoski-ja-matkakoski-25-5-2010/"),
         ("Tuorala: Vuennonkoski–Matkakoski-video", TUORALA + "2011/02/22/vuennonkoski-matkakoski-video/"),
         ("Freestylemelonta-blogi: Matkakoski big water (25.5.2010)", FSB + "2010/05/matkakoski-big-water.html"),
         ("Freestylemelonta-blogi: Rajajoen tulva (video, 2011)", FSB + "2011/02/rajajoen-tulva.html")),
    ),
    # ------------------------------------------------------------------
    "Hawa'Ii (Iijoki, Maalismaa)": Kuvaus(
        "Hawa'Ii on tulva-ajan aalto Iijoen vanhassa uomassa Maalismaan voimalaitoksen kohdalla Yli-Iissä. "
        "Tulvalla uomaan syntyy iso, murtuva aalto, joka veden vähetessä muuttuu stopparimaisemmaksi. Hyvän "
        "akanvirran ja tasaisen muodon ansiosta se on loistava treenipaikka – mutta ei kannata meloa täällä, "
        "jos eskimo ei ole varma.",
        (
            ("Vesimäärät",
             "Kun Maalismaan virtaama on 600 m³/s tai vähän alle, keula alkaa kolista kiviin aallon pohjalla. "
             "850 m³/s:llä paikka on tosi hyvä ja paranee veden lisääntyessä, vaikka akanvirtaan pääsy samalla "
             "hankaloituu. Toukokuussa 2015 virtaama pysytteli kolme päivää noin 1150 m³/s:ssa, ja blogin "
             "mukaan se vaikutti optimaaliselta: 'Aika montaa hyvää aaltoa olen päässyt melomaan, mutten vielä "
             "koskaan näin hyvää!' Myös noin 900 m³/s (5/2015) ja 700 m³/s (5/2023) olivat hyviä. Aallon kaksi "
             "parasta kohtaa: vihreästä kulmasta ylös ja keskemmältä alas. Seuraavassa pohjapadossa on juhlava "
             "hontto, joka ei kuitenkaan ole vaikuttanut vaaralliselta 600–850 m³/s:n vesillä; rantaan "
             "ehtinee uida ennen sitä."),
            ("Perille",
             "Aja Iistä Yli-Iin suuntaan ja käänny juuri ennen Iijoen ylittävää rautasiltaa Maalismaan suuntaan. "
             "Aja 16 km, ja heti kun tie on ylittänyt voimalaitoksen, käänny vasemmalle Voimalatielle. "
             "Voimalatie kaartaa oikealle, mutta jatka kärrytietä suoraan: pelipaikka on oikealla aivan tien "
             "vieressä. Parkkipaikka on vanhan uoman ja voimalaitoksen alakanavan välisellä kannaksella, aallon "
             "kohdalla."),
            ("Kokemuksia",
             "Aalto palasi toukokuussa 2012 muutaman vuoden tauon jälkeen, ja maajoukkue majoittui viikoksi "
             "Maalismaan koululle. Kausi avattiin 28.4.2013 jäiden vielä kelluessa akanvirrassa (fullface-kypärä "
             "tarpeen). Keväällä 2010 vesi ei noussut, ja aallonpohja jäi matalaksi."),
        ),
        (("osm.fi: Hawa'Ii", "https://www.osm.fi/hawa-ii/"),
         ("Freestylemelonta-blogi: Ison veden Hawa'Ii (18.5.2015)", FSB + "2015/05/ison-veden-hawaii.html"),
         ("Freestylemelonta-blogi: Hawa'Iillä (14.5.2015)", FSB + "2015/05/hawaiilla.html"),
         ("Freestylemelonta-blogi: Hawa'Iin kauden avaus 28.4.2013", FSB + "2013/04/hawaiin-kauden-avaus-284.html"),
         ("Freestylemelonta-blogi: Melontaa palmujen alla (5.5.2012)", FSB + "2012/05/melontaa-palmujen-alla.html"),
         ("Freestylemelonta-blogi: Pieni kuvapäivitys karkeloista Hawa'Iilta (10.5.2012)",
          FSB + "2012/05/pieni-kuvapaivitys-karkeloista.html"),
         ("Freestylemelonta-blogi: Koeajo Lapin aalloista (22.5.2023)",
          FSB + "2023/05/koeajo-lapin-aalloista.html"),
         KAPSI),
    ),
    # ------------------------------------------------------------------
    "Pyhäjoki": Kuvaus(
        "Pyhäjoella on kaksi pelipaikkaa, molemmat lyhytsesonkisia kevään paikkoja. Veden väri ja haju ovat "
        "osm.fi:n mukaan 'mielenkiintoisia'. Mittarina on Tolpankosken virtaama.",
        (
            ("Ruukinkoski",
             "Ruukinkosken etelähaarassa heti kasitien alapuolella on keskikokoinen stoppari, joka murtuu "
             "toisesta päästä aalloksi (muistuttaa Kipinän keskimmäisen silta-aukon paikkaa). Se toimii, kun "
             "Tolpankosken virtaama on 45–75 m³/s. Akanvirta on laskijan oikealla, ja paikkaan pääsee takaisin "
             "melomalla. Oulusta on matkaa hieman yli 100 km. Hyvä paikka kauden aloitukseen."),
            ("Saunarannan aalto",
             "Pyhänkosken keskivaiheilla rantasaunan vieressä on Ruukinkoskea isompi murtuva aalto (matalalla "
             "vedellä osin stoppari). Akanvirta on laskijan oikealla, mutta takaisin aaltoon on yleensä kannettava "
             "muutama metri kalliokannaksen yli. Se toimii noin 80–150 m³/s:llä ja on ehkä parhaimmillaan noin "
             "140 m³/s:llä; 170 m³/s on liikaa, jolloin aalto ei pidä ja on vino. Oulusta noin 125 km.\n\n"
             "Isolla vedellä koskea voi silti laskea. Sillan yläpuolella, missä virta painaa kalliota päin, on "
             "kallion koloissa pari ikävän näköistä 'akanvirtaa' – varo. Uinnin sattuessa kamat kerätään "
             "suvannosta noin 1 km sillan alapuolelta."),
        ),
        (("osm.fi: Pyhäjoki", "https://www.osm.fi/pyhaejoki/"), KAPSI),
    ),
    # ------------------------------------------------------------------
    "Siikajoki (Pöyryn pato)": Kuvaus(
        "Siikajoella on useita leikkipaikkoja, monipuolisin alue on heti Pöyryn voimalaitospadon alla "
        "Revonlahden ja Siikajoenkylän välissä. Joki vetoaa osm.fi:n mukaan kaikkiin aisteihin: vesi on "
        "vaihtelevan väristä ja tuoksultaan maalaismaista, joten nenänipsu ja korvatulpat kannattaa ottaa "
        "mukaan. Pienempiä koskia jatkuu Siikajoenkylälle asti.",
        (
            ("Perille ja vesille",
             "Pohjoispuolen tietä tultaessa parkkipaikaksi sopiva tienpää on padon päässä kalaportaan vieressä. "
             "Vesille mennään kajakki olalla kalaportaan louhikossa tasapainoillen. Pato estää normaalin "
             "kevättulvan ja jääeroosion, joten rannat ja akanvirrat ovat pusikkoiset. Takaisin autolle "
             "kävellään koskien alta pellon reunaa ja tietä pitkin, tai paluuauton voi jättää alemmas "
             "pohjoispuolen tielle."),
            ("Vaahtokylpy",
             "Vaahtokylpy laskijan oikeanpuoleisessa uomassa toimii laajalla vesialueella. Yli 300 m³/s:llä se "
             "on alas murtuva aalto ja parhaimmillaan todella isolla vedellä, 300–400 m³/s (yli 20.5 m). Se "
             "toimii vielä 250 m³/s:llä, jolloin mela ja joskus pääkin kolisee eskimossa. Erinomaisen akanvirran "
             "(laskijan vasemmalla) ansiosta paikka sopii myös vähemmän meloneille, ja uimarin saa vedettyä "
             "saaren alle.\n\n"
             "Alle 250 m³/s:llä (ainakin 140–250 m³/s, 19.7–20.4 m) aalto on liian matala, mutta kielen toiselle "
             "puolelle syntyy uusi aalto. Noin 250 m³/s:llä sen pito on heikko ja aalto vähän vino, ja "
             "150 m³/s:llä se on muuttunut rannasta hontoksi, jossa on hyvin syvyyttä esimerkiksi volteille. "
             "Rannan akanvirta (laskijan oikealla) on lyhyt, mutta risukoissa meloen pääsee takaisin."),
            ("Muut paikat",
             "Vaahtokylvyn yläpuolisen kalliosaaren kohdalle päävirran molemmin puolin tulee kohtuullisia "
             "pelipaikkoja 70–250 m³/s:llä. Matalimmalla vedellä toimii saaren alimman portaan pieni aalto ja "
             "hontto, jossa voi vielä 70 m³/s:llä spinnailla ja kärrytellä. Matalalla vedellä täällä on mukavia "
             "virranrajoja vähemmän meloneille.\n\n"
             "Noin 5 km padolta alavirtaan on hieno aalto, joka toimii ainakin yli 150 m³/s:llä. Siihen on "
             "kannettava, ja joillakin vesillä se heittää helposti surffaajan oikealta ulos. Ruukin keskustassa "
             "padon alle pohjoisrannalle syntyy isolla tulvalla iso hontto, johon ei pidä mennä, ellei tiedä "
             "tarkalleen mitä tekee."),
        ),
        (("osm.fi: Siikajoen pelipaikat", "https://www.osm.fi/melontapaikat/siikajoki/"), KAPSI),
    ),
    # ------------------------------------------------------------------
    "Niskakoski (Lestijoki)": Kuvaus(
        "Lestijoen Niskankoski on Kannuksen ja Himangan puolivälissä parkkipaikan vieressä. Se on yksi "
        "koskikauden avauspaikoista: tänne kannattaa suunnata huhtikuun alkupuolella.",
        (
            ("Pelipaikat",
             "Stoppari toimii, kun virtaama on yli 50 m³/s. Se on vähän mutkassa, mutta siinä onnistuvat "
             "perusstoppariliikkeet. Yli 85 m³/s:llä stopparin taakse muodostuu kohtuullinen aalto. Akanvirrat ovat "
             "hyvät joen molemmin puolin, mutta isommalla vedellä virranrajat voivat olla hankalat."),
        ),
        (("osm.fi: Niskakoski", "https://www.osm.fi/niskakoski/"),),
    ),
    # ------------------------------------------------------------------
    "Neitikoski (Lieksanjoki)": Kuvaus(
        "Lieksanjoen Neitikoski Ruunaalla on erittäin suosittu freestylemelojien keskuudessa. Kosken puolivälissä on lähes joen levyinen aalto tai stoppari vedenkorkeuden "
        "mukaan, yleensä murtuva aalto, jossa on helposti surffattava kieli. Aalto päästää kaatuneen melojan "
        "tai uimarin yleensä nopeasti. Koski päättyy järveen, joten uinnit jäävät lyhyiksi, varusteet on helppo "
        "kerätä ja pelipaikalle pääsee helposti takaisin. Kosken pituus on noin 200 m, pudotus 1 m.",
        (
            ("Vesimäärät",
             "Tulvalla aalto voi murtua koko leveydeltään lähes pohjaan asti ja olla hankala vähän kokemusta "
             "omaavalle. koskimelonta.comin mukaan yli 110 m³/s:llä (sillan mittari noin 8) aalto murtuu pohjaan: "
             "aaltoliikkeisiin tarvitaan räjähtävää melontaa, mutta se on oivallinen volttien harjoitteluun. "
             "Yli 120 m³/s:llä (laiturin mittari noin 9,5) aalto jyrkkenee ja aaltoliikkeet onnistuvat "
             "helpommin. Alle 100 m³/s:llä metsän laitaan syntyy hontto ja keskelle kieli, ja matalilla "
             "vesillä pelipaikan vasen reuna muuttuu stoppariksi. Meloa voi vielä 40 m³/s:llä (laituri noin −1), "
             "vaikka pohjakosketuksia tulee.\n\n"
             "Juhannuksena 2015 virtaama oli 160 m³/s ja viikkoa myöhemmin 140 m³/s; ilmavia bluntteja riitti "
             "molemmilla."),
            ("Melamerkit", NEITI_SAANNOT),
            ("Ympärivuotinen paikka",
             "Neitikoski pysyy sulana talvellakin: maajoukkuemelojat ovat avanneet kauden tammikuussa 16 asteen "
             "pakkasessa ja meloneet maaliskuussa jäiden reunustamana. Talvella pois on lähdettävä ennen kuin "
             "palelee, koska kävelymatka parkkipaikalle tuntuu kylmissään pitkältä. Ruunaan retkeilykeskus on "
             "aivan vieressä."),
            ("Kisat",
             "Freestylemelonnan EM-kisat pidettiin Neitikoskella 10.–13.6.2026, ja kotikisoista tuli Suomeen "
             "kultamitali."),
        ),
        (("osm.fi: Neitikoski", "https://www.osm.fi/neitikoski/"),
         ("koskimelonta.com: Lieksanjoki – Neitikoski", "https://koskimelonta.com/kosket/lieksanjoki-neitikoski/"),
         ("koskimelonta.com: Freestylen EM-kisat Neitikoskella 10.–13.6.2026",
          "https://koskimelonta.com/2026/03/03/freestylen-em-kisat-neitikoskella-10-13-6-2026/"),
         ("koskimelonta.com: Kultamitali freestylemelonnan EM-kotikisoista Suomeen (15.6.2026)",
          "https://koskimelonta.com/2026/06/15/kultamitali-freestylemelonnan-em-kotikisoista-suomeen/"),
         ("Freestylemelonta-blogi: Neitikosken aallolla (29.6.2015)", FSB + "2015/06/neitikosken-aallolla.html"),
         ("Freestylemelonta-blogi: Kauden avaus Neitikoskella (23.1.2011)",
          FSB + "2011/01/kauden-avaus-neitikoskella.html"),
         ("Freestylemelonta-blogi: Neitikoski maaliskuussa (20.3.2011)", FSB + "2011/03/neitikoski-maaliskuussa.html"),
         ("Freestylemelonta-blogi: Neitikoski low water (17.8.2010)", FSB + "2010/08/neitikoski-low-water.html"),
         ("Freestylemelonta-blogi: Neitikoskella reenailemassa (24.9.2013)",
          FSB + "2013/09/neitikoskella-reenilemassa.html"),
         ("Tuorala: Neitikoski 22.–24.10.2010", TUORALA + "2010/12/03/neitikoski-22-24-10-2010/"),
         ("Ruunaan retkeilyalue", "https://ruunaa.fi/")),
    ),
    # ------------------------------------------------------------------
    "Trollforsarna (Piteälven)": Kuvaus(
        "Trollforsarna (Trollforsen) on Piteälvenin koskiosuus Ruotsin Lapissa ja suomalaisten koskimelojien "
        "suosittu kesäkohde – heinäkuussa 2012 saman nuotion ympärillä istui toistakymmentä suomalaista. "
        "Koskille vie päätieltä hyvin opastettu, 11 km pitkä hiekkatie. Leiriytyä voi ilmaiseksi koskelle "
        "vievän rantatien varrella: paikalla on huussit, lähdevesiputket ja kivestä kasattuja nuotiopaikkoja "
        "(polttopuut tuotava itse). Paras kausi on kesäkuu. Ruotsalaisten Norrlandsturen-tapahtuma on tuonut "
        "paikalle kymmeniä melojia juhannuksen ja heinäkuun tienoilla (2010, 2011).",
        (
            ("Kosket",
             "Paltvalsen on iso aalto, jossa heinäkuussa 2011 surffattiin viisi päivää ilman jonoa. Se toimii isollakin vedellä, "
             "vaikka voi olla välillä väkivaltainen, ja sen alapuolinen pour over -hontto on karmea paikka "
             "('älköön kukaan amatöörimeloja menkö siihen'). Seuraavassa koskessa on kaksi hyvää honttoa, joista "
             "ylempi stoppari on erinomainen volttikone.\n\n"
             "Creeking Delta (yläpätkä) on teknisempi pätkä pieniä pudotuksia; korkealla vedellä kosket ovat "
             "koskia eivätkä kivikoita ja linjat helpompia. Sillan jälkeen pätkän lopussa on voimakas hontto. "
             "Alempana alkaa loppulasku, jossa aallokossa lasketellaan ainakin neljä minuuttia. Tuus-Melojien "
             "mukaan reitillä on yksi pakollinen kanto, ja vaihtoehtoinen reitti löytyy lähes aina. Iltalenkki "
             "alavirtaan, auto viety ennakkoon junan ja autojen yhteiselle kombisillalle, kesti noin kolme "
             "tuntia."),
            ("Kokemuksia",
             "Juhannus 2010: leppoisa reissu, Creeking Deltan koskia ja loppukönkään linjoja. Heinäkuussa 2011 "
             "vesi oli korkea, ja Paltvalsen oli hyvässä mutta välillä väkivaltaisessa kunnossa. Kesäkuussa 2012 "
             "Paltvalsen toimi suuresta vesimäärästä huolimatta oikein hyvin. Matkalla kannattaa pysähtyä "
             "katsomaan Storforsenia – 'kerrankin koskella on nimi, joka sitä hyvin kuvastaa'."),
        ),
        (("Tuus-Melojat: Trollit 2017", "https://tuusmelojat.fi/trollit-2017/"),
         ("Tuorala: Juhannus Trollforsenilla 25.–27.6.2010",
          TUORALA + "2010/08/21/juhannus-trollforsenilla-25-27-6-2010/"),
         ("Freestylemelonta-blogi: Trollforsen (14.7.2011)", FSB + "2011/07/trollforsen.html"),
         ("Freestylemelonta-blogi: Ruotsissa (24.6.2012)", FSB + "2012/06/ruotsissa.html"),
         ("Freestylemelonta-blogi: Pojut Norjassa: Piteå ja kotiin (27.7.2012)",
          FSB + "2012/07/pojut-norjassa-pitea-ja-kotiin.html"),
         ("Forsguiden: Piteälven, Trollforsarna (Wayback 2004)",
          "https://web.archive.org/web/20040722032025/http://www.forsguiden.com/river.asp?id=3&mode=print")),
    ),
    # ------------------------------------------------------------------
    "Taivalkoski": Kuvaus(
        "Taivalkosken melontakeskuksessa on monien kokeilujen jälkeen rakennettu rodeomonttu ja sen yhteydessä "
        "mallikas slalomrata. Oulusta ajaa noin kaksi tuntia. Koskessa on hyvä harjoitella akanvirtojen "
        "nappailua ja koskenlaskua: yläosa on vaativampi, alaosa helppo. Rannalla on huoltorakennus saunoineen.",
        (
            ("Rodeomonttu",
             "Stoppari kosken puolivälissä valmistui lopulliseen muotoonsa vuonna 2002. Siitä tuli pour over "
             "-tyyppinen: pystyliikkeet ovat helppoja, mutta surffaus ja muut aaltoliikkeet eivät oikein onnistu. "
             "osm.fi kuvaa sitä kohtalaiseksi, hieman yksipuoliseksi ja kapeahkoksi stoppariksi, joka sopii "
             "stopparissa pyörimisen opetteluun. Uusittu ja korjattu hontto sai vuonna 2013 maajoukkuemelojilta "
             "kehuja: oikealla vedenkorkeudella se oli heidän mukaansa 'Suomen paras pelihontto', jossa kaikki "
             "liikkeet onnistuivat molemmille käsille. Monttua korjattiin taas elokuussa 2014."),
            ("Vesi",
             "Kosken yläpäässä on säännöstelypato. Kun vesi vähenee, sitä voi tilata Taivalkosken kunnan vapaa-"
             "ajantoimesta. Keväällä vettä voi olla liikaa (5/2010)."),
            ("Tapahtumat",
             "Taivalkosken melontafestareilla kisataan kosken kuninkuudesta kolmessa lajissa – slalomissa, "
             "freestylessä ja boatercrossissa – samalla kajakilla. Koskella on järjestetty myös slalom- ja "
             "koskicrossikisoja (2023), European Masters Gamesin slalom (2023) sekä maajoukkueen "
             "valmennusleirejä."),
        ),
        (("osm.fi: Taivalkoski", "https://www.osm.fi/taivalkoski/"),
         ("Freestylemelonta-blogi: Uusitun Taivalkosken testausta (9.8.2013)",
          FSB + "2013/08/uusitun-taivalkosken-testausta.html"),
         ("Freestylemelonta-blogi: Taivalkosken melontafestarit (12.8.2014)",
          FSB + "2014/08/taivalkosken-melontafestarit.html"),
         ("Freestylemelonta-blogi: Valmennusleiri Taivalkoskella (27.6.2014)",
          FSB + "2014/06/valmennusleiri-taivalkoskella.html"),
         ("Freestylemelonta-blogi: Keppejä kiertämässä (13.9.2023)", FSB + "2023/09/keppeja-kiertamassa.html")),
    ),
    # ------------------------------------------------------------------
    "Sanginjoki": Kuvaus(
        "Sanginjoki on noin 80 km pitkä hyvä melontajoki, joka laskee Oulujokeen Madekoskella aivan Oulun "
        "kupeessa. Yläjuoksulla on erämaan henkeä, ja siellä on yksi isompi koski, jonka loppuosa on vähällä "
        "vedellä suorastaan hankala.",
        (
            ("Koskiosuus",
             "Joen koskisin osuus alkaa vähän Lemmenpolun yläpuolelta ja päättyy Taivalkoskelle golfkentän "
             "kupeeseen. Tämä noin 8 km:n pätkä on mukava tulva-aikaan. Isoimmat kosket ovat lähellä Oulujokea. "
             "Joki on parhaimmillaan reilusti yli 10 m³/s:n virtaamalla, mutta ainakin 8 m³/s:llä ihan "
             "laskettavissa."),
        ),
        (("osm.fi: Sanginjoki", "https://www.osm.fi/sanginjoki/"),),
    ),
    # ------------------------------------------------------------------
    "Kuivajoki": Kuvaus(
        "Kuivajoki on noin 75 km Oulusta Kemiin päin (Kemistä 35 km). Se on laskettavissa noin kolme viikkoa "
        "jäiden lähdöstä. Heti jäiden lähdön jälkeen loppumatkalla on isoja aaltoja ja pelipaikkoja, viikkoa "
        "myöhemmin (Ravaskan vedenkorkeus noin 28 m) pienempää aaltoa ja enemmän kivien kiertelyä.",
        (
            ("Reitti",
             "Yläosa Oijärvestä Hyryn kylään (noin 25 km) on pientä virtaa. Sen jälkeen alkaa joen paras, noin "
             "17 km pitkä osuus, jossa ei ole montaa suvantoa. Suurin koski, Kattilakoski, on noin 4 km "
             "Asemankylältä ylöspäin. Heti jäiden lähdön jälkeen 4 km:n pätkä Kattilakoskelta Asemankylän "
             "sillalle on mukava pelipätkä. Toinen hyvä lähtöpaikka on ampumarata, josta Kuivaniemeen on noin "
             "35 km."),
            ("Lähtöpaikka",
             "Asemankylältä Oijärven tietä noin 4 km, kunnes vasemmalla on viitta 'Ravaska'. Aja niin pitkälle "
             "kuin tietä riittää ja joki näkyy."),
        ),
        (("osm.fi: Kuivajoki", "https://www.osm.fi/kuivajoki/"),),
    ),
    # ------------------------------------------------------------------
    "Olhavajoki": Kuvaus(
        "Olhavajoki on 29 km pitkä pieni joki, joka laskee Kaihuanjärvestä Perämereen Olhavan kylässä noin "
        "50 km Oulusta Kemiin päin. Putouskorkeutta on 76,5 m. Melontaan vettä riittää noin viikon tai pari "
        "jäiden lähdöstä; Kaihuanjärvi voi silloin olla vielä jäässä. Virtaamatietoja ei ole, mutta tulvahuippu "
        "ja jäidenlähtö osuvat samaan aikaan Kuivajoen kanssa. Koska järviä on vähän, Olhavajoen vesi laskee "
        "Kuivajokea nopeammin.",
        (
            ("Reitti",
             "Ensimmäinen kilometri järvestä pujotellaan virran mukana pajukoissa. Enimmäkseen joessa on pieniä "
             "koskia, ja suvannotkin virtaavat tulva-aikaan mukavasti. Kahteen suurempaan koskeen ensikertalaisen "
             "kannattaa suhtautua kunnioittavasti ja katsoa ne rannalta.\n\n"
             "Sahankoski on Konttilantien sillan kohdalla. Koski alkaa kahdessa haarassa: oikealla on pieni "
             "pudotus, vasemmalla s-mutka ja sen lopussa suurta aallokkoa. Haarat yhtyvät pieneen "
             "keräilyaltaaseen, ja sillan alla odottaa lähes silta-aukon levyinen stoppari, josta jyrätään läpi "
             "sopivasta kohdasta.\n\n"
             "Suurin koski alkaa vähän rautatiesillan jälkeen, noin kilometri ennen Oulu–Kemi-tien siltaa. Ensin "
             "sujautetaan kahden suuren kiven välistä, sitten tarjolla on jämäkkää mutkittelua honttoja "
             "kierrellen. Koski on selvästi joen muita koskia isompi."),
            ("Vesille ja pois",
             "Tie kulkee lähellä jokea useassa kohdassa, joten vesille pääsee monesta paikasta. Maihin voi nousta "
             "esimerkiksi Olhavan koulun takana olevalla urheilukentällä. Jos viimeisen kosken haluaa jättää "
             "väliin, rautatien yläpuolelle tulee tie rantaan."),
        ),
        (("osm.fi: Olhavajoki", "https://www.osm.fi/olhavajoki/"),),
    ),
    # ------------------------------------------------------------------
    "Simojoki": Kuvaus(
        "Simojoki on noin 85 km Oulusta Kemiin päin (Kemistä 25 km). Kesävedellä se on hyvä joki aloitteleville "
        "ja retkeilijöille. Tulvalla joki sopii vain kokeneille: heille paras aika on pari viikkoa jäiden "
        "lähdön jälkeen. Kesävedellä rodeohenkisten ei kannata lähteä joelle.",
        (
            ("Alaniemi – Simo",
             "Päiväretken voi aloittaa Alaniemen sillalta (noin 25 km Oulu–Kemi-tieltä Ranuan suuntaan) ja "
             "lopettaa urheilukentän viereen rautatie- ja maantiesillan väliin. Tiet kulkevat joen molemmin "
             "puolin Alaniemeen asti. Pätkä on lähes koko ajan pientä (tulvalla isoa) koskea tai virtaavaa vettä, "
             "ja siinä on yksi pitkä suvanto (Karisuvanto). Matkalla on kolme isompaa koskea (II–III). Suurin "
             "on Hamarinkoski noin 8 km Kemin tietä ylöspäin."),
            ("Kalliokoski",
             "Paras pelipaikka on Kalliokoski noin 4 km Alaniemestä alaspäin. Isolla vedellä siinä on hieno "
             "surffiaalto ja hieman alempana pohjoisrannalla stoppari. Kalliokoskelle pääsee helposti eteläpuolen "
             "tieltä, josta koski näkyy; kantomatkaa on noin 100 m."),
        ),
        (("osm.fi: Simojoki", "https://www.osm.fi/simojoki/"),
         ("Luontoon.fi: Simojoen melontareitti", "https://www.luontoon.fi/fi/simojoenmelontareitti")),
    ),
    # ------------------------------------------------------------------
    "Lieksanjoki (Matkalahti – Siikakoski)": Kuvaus(
        "Lieksanjoen melontareitti alkaa itärajan tuntumasta Ruunaanjärven yläpuolelta ja päättyy yleensä "
        "Naarajoen sillalle. Yleisimmin melottu osuus on Matkalahti – Siikakoski (22,5 km), erityisesti "
        "Neitikoskelta Siikakoskelle. Paasikoskea lukuun ottamatta kaikkiin koskiin kannattaa tutustua rannalta "
        "ennen laskua.",
        (
            ("Reitti kilometreittäin",
             "0 km Matkalahti: veneenlaskuluiskat ja laituri.\n\n"
             "5 km Paasikoski (I): kulkukelpoisuus hyvä/erinomainen, uoma matala. Matalalla vedellä paras väylä "
             "on aivan vasemman tai oikean rannan tuntumassa. Niskalla tulipaikka oikealla, alla laavu "
             "vasemmalla.\n\n"
             "6 km Haapavitja (II): 1200 m, putous 6,1 m. Suurimmat aallot ovat heti riippusillan alapuolella "
             "ensimmäisellä 400 metrillä, loppu on helppoa. Helpoin reitti on sillan jälkeen vasemman rannan "
             "tuntumassa. Ennen siltaa oikealla on stoppari, jota kokemattoman kannattaa välttää. Ennakkotarkastus "
             "on tarpeen.\n\n"
             "9 km Neitijärvi: reitti kääntyy jyrkästi oikealle, Saunaniemen laavu ja Huuhkajanvaaran "
             "näköalapaikka; Neitisaaren (telttapaikka, laavu) voi ohittaa kummalta puolelta tahansa.\n\n"
             "15 km Neitikoski (II): 200 m, putous 1 m. Puolivälissä on suuri, lähes kosken levyinen stoppari, "
             "joka voi pysäyttää ja kaataa kokemattoman. Väylän oikea puoli on kivinen; suositeltava reitti on "
             "vasen puoli, ja kokenut voi ohittaa stopparin aivan vasemman rannan tuntumasta. Helpoimmin stopparin "
             "läpäisee keskellä olevan kielen kohdalta. Alla laavu ja Ruunaan retkeilykeskus.\n\n"
             "17,5 km Kattilakoski (II): 150 m, putous 1,4 m. Alaosassa on suuria, teräviä aaltoja ja pyörteitä "
             "sekä poikkeuksellisen voimakkaat akanvirrat molemmin puolin. Suositeltava reitti on keskiväylä. "
             "Kosken taukopaikat ovat koskenlaskuyrittäjien käytössä.\n\n"
             "20 km Murrookoski (II): 300 m, putous 2,6 m – reitin vaikein koski. Kivinen, suuria aaltoja ja "
             "stoppareita, ja loppuosa on kuivalla erittäin kivinen. Suositeltava reitti on vasen puoli.\n\n"
             "21 km Siikakoski (II): 1300 m, putous 4,6 m. Alussa kaksi kivipadolla yhdistettyä saarta, ja koski "
             "kaartaa jyrkästi vasemmalle; kaarteessa päävirta painaa kohti etuoikealla olevaa saarta. Suurimmat "
             "aallot ovat ensimmäisillä 50 metreillä vasemmassa laidassa, ja ne voi ohittaa oikeaa reunaa "
             "laskien.\n\n"
             "22,5 km Siikakosken maihinnousupaikka: tie rantaan, tulipaikka ja käymälä. Tämän jälkeen alkaa "
             "rauhallinen jokiosuus."),
            ("Neitikosken melamerkit", NEITI_SAANNOT),
        ),
        (("osm.fi: Lieksanjoki", "https://www.osm.fi/lieksanjoki/"),
         ("koskimelonta.com: Lieksanjoki – Neitikoski", "https://koskimelonta.com/kosket/lieksanjoki-neitikoski/"),
         ("Ruunaan retkeilyalue", "https://ruunaa.fi/")),
    ),
    # ------------------------------------------------------------------
    "Liminganjoki": Kuvaus(
        "Liminganjoki on lakeuden yllättävin joki. Kasitien yläpuolella se on kaukana tiestä kulkeva, "
        "hidasvirtainen puro, mutta kasitieltä alavirtaan joki laskee jyrkästi Limingan keskustaan: viiden "
        "kilometrin matkalla pudotusta on noin 30 metriä. Kosket ovat helppoja, I-luokkaa, ja jokimaisema on "
        "kaunista Oulun seudun kulttuurimaisemaa.",
        (
            ("Reitti",
             "Koskimelojan kannattaa pudottautua jokeen kasitien sillalta. Hankalinta on löytää paras reitti "
             "saarten lomitse heti 150 m lähtöpaikan alapuolella olevassa koskessa. Koskiosuus loppuu "
             "Ala-Kestilän arboretumin jälkeen vähän ennen Vanhaa Liminkaa, mutta kulttuurimaisemasta kannattaa "
             "nauttia ainakin Vanhan Limingan museoalueelle asti. Hyvä lopetuspaikka löytyy urheilukentän "
             "tienoilta."),
            ("Vaarat",
             "Joki olisi erittäin miellyttävä kevättulvajoki ilman kaatuneita puita, joita on paljon. Kapean "
             "joen ne tukkivat helposti kokonaan, eikä reippaassa virrassa ole helppoa meloa ylävirtaan – "
             "pidä turvavälit. Kasitien jälkeisen sillan jälkeen joen poikki on viritetty melojan kaulan "
             "korkeudelle pari rautalanka-aitaa. Puutilanne oli pahin Värminkosken sillalta alavirtaan ja "
             "parhain välillä kasitie – Vaattasen silta sekä loppuosassa arboretum – Liminka."),
            ("Vesimäärä",
             "Limingan vesitilannetta voi arvioida Tyrnävänjoen virtaamasta. Syksyn 2010 melonnassa Tyrnävänjoen "
             "virtaama oli 2,5 m³/s, mikä oli liian vähän."),
        ),
        (("osm.fi: Liminganjoki", "https://www.osm.fi/liminganjoki/"),),
    ),
    # ------------------------------------------------------------------
    "Muhosjoki": Kuvaus(
        "Muhosjoki on kolmeen hyvin erilaiseen osaan jakautuva joki Muhoksella. Yläosa on vauhdikasta "
        "pikkukoskea, keskiosa erämaista mutta kaatuneiden puiden täyttämää, ja alaosan Suokylän koskijakso on "
        "joen upein osuus.",
        (
            ("Yläosa: Huikolan silta – Vääräkoski",
             "Oikein mukavaa melottavaa: pitkiä suvantoja ei ole ja koskissa on hyvä vietto. Suurin koski on "
             "ehkä Kuurnankoski, jossa matalalla vedellä kannattaa meloa oikeanpuoleinen haara. Pieniä "
             "pelipaikkoja voisi syntyä ainakin Kuurnankoskeen ja Kalliokoskeen."),
            ("Keskiosa: Vääräkoski – Murtokoski",
             "Joen luonne muuttuu täysin: koskia ei ole, kaatuneita puita on runsaasti, ja ohitukset ovat "
             "kinkkisiä jyrkkien ja savisten penkkojen takia. Väli on silti erittäin luonnonkaunis ja erämainen – "
             "retkimelojille kevätkesällä tulvan jo laskettua, varsinkin tuomen kukinnan tai ruskan aikaan. "
             "Koskimelojien kannattaa siirtyä autolla Murtokoskelle."),
            ("Alaosa: Murtokoski – Suokylä – Kajaanintie",
             "Murtokosken jälkeen on pari kilometriä pieniä koskia hienossa erämaassa, sitten noin 4 km "
             "tasaisempaa, jossa puita on harvassa (majavat voivat muuttaa tilannetta). Suokylän sillalta 1–2 km "
             "ylävirtaan on mukavia pikkukoskia, jotka ovat syysvesillä hieman matalia.\n\n"
             "Suokylän sillalta alkaa joen upein, reilun kilometrin koskijakso Liimanninkosken alapuolelle asti, "
             "ja se voisi sopia kevättulvalla pelimelojillekin. Heti sillan alla on Ämmänkoski ja sen köngäs, "
             "jonka laskulinja kannattaa tarkistaa rannalta. Keväällä 2010 köngäässä oli puu ikävästi "
             "laskulinjalla, syksyllä se oli vapaa. Seuraavan kosken (Käyräkoski, oikea haara) puolivälissä oli "
             "syksyllä 2010 poikittainen puu. Koskijakson jälkeen kannattaa nousta maihin, mutta tarkista "
             "nousupaikka etukäteen korkeiden penkkojen ja mudan takia. Lopetuspaikan jälkeen on Lions-klubin "
             "venelaituri, josta alaspäin joki on raivattu. Reilun 10 km:n matka Kajaanintielle on "
             "koskimelojalle tylsä; esimerkiksi Hyrkäksen koulu käy parkki- ja lopetuspaikaksi."),
        ),
        (("osm.fi: Muhosjoki", "https://www.osm.fi/muhosjoki/"),),
    ),
    # ------------------------------------------------------------------
    "Temmesjoki": Kuvaus(
        "Temmesjokea voi halutessaan meloa 70 km, mutta erinomaisesti se sopii koskikauden aloitukseen myös "
        "vähemmän meloneille. Joelle kannattaa suunnata heti jäiden lähdettyä, yleensä vapun aikoihin. Sopivia "
        "lähtöpaikkoja on useita.",
        (
            ("Haurukylä – Vehkamaantie",
             "Mukava ja sopivan virtaava iltapäiväpätkä on esimerkiksi Haurukylän (puretulta) sillalta "
             "Vehkamaantien sillalle (myös 'Ylempi Ketunmaan silta'). Koskia on useita, ja ne kaikki ovat "
             "varsin helppoja, I-luokkaa. Jokimaisema on perinteistä ja kaunista Oulun seudun kulttuurimaisemaa, "
             "eikä vanhan jokikuvauksen kaatopaikkamaininnoista ole tällä pätkällä jälkeäkään. Mittarina "
             "käytetään Temmesjoen ja Tyrnävänjoen virtaamia."),
        ),
        (("osm.fi: Temmesjoki", "https://www.osm.fi/temmesjoki/"),),
    ),
    # ------------------------------------------------------------------
    "Pahakurkkio (Kalixälven)": Kuvaus(
        "Pahakurkkio (Pahis) on Kalixälvenin kanjoniosuus Saittarovassa Pajalan kunnassa Ruotsissa: noin "
        "3–4 km:n matkalla on seitsemän könkään sarja. Ykköskönkään Åretsvågen on kuuluisa surffiaalto. "
        "Kausi on yhtä pitkä kuin kesä. Kevättulvalla kanjonista löytyy isoa, paineista vettä – "
        "'kuin jäisessä Zambezissa' – eikä melonta silloin ole leppoisaa; uinti voi olla kohtalokas. Veden "
        "laskiessa pelipaikat ilmestyvät ja kosken luonne muuttuu ystävällisemmäksi.",
        (
            ("Kosket",
             "Kosket 1–3 ovat noin III-luokkaa, nelosessa on hontto oikealla, vitonen on vaikein ja 6–7 ovat "
             "IV-luokkaa. Isolla vedellä (yli noin 220 m³/s Männikössä) kosket ovat isoja ja vitonen V-luokkaa. "
             "Vitoskönkään 'kuolemanhontto' on kummitellut monen melojan mielessä. Pelipaikoissa on hyvät "
             "akanvirrat, ja alemmat könkäät ovat mukavan haastavaa laskettelua. Pikkuhontto on hyvä paikka "
             "harjoitella McNastya, ja aallossa on helppo harjoitella kalastajakuningasta."),
            ("Åretsvågen ja vesimäärät",
             "Åretsvågen on herkkä vesimäärälle. Kesäkuussa 2012 sen 'kuuluisa seinä' toimi, ja kesäkuussa 2013 "
             "se oli parhaimmillaan laskevalla vedellä. Toukokuussa 2013 vettä oli liikaa: Åretsvågen ei "
             "toiminut, mutta samassa kohdassa oli pari muuta hauskaa aaltoa, ja koski näytti aivan erilaiselta "
             "kuin matalalla. Syysvedellä (9/2010) lähes kaikki honttoliikkeet onnistuivat ykköskönkään "
             "hontossa. Tarkat Männikön virtaamat käyntipäiviltä näkyvät kohteiden huomioissa alla."),
            ("Majoitus",
             "Lähistöllä on vuokrattavia mökkejä saunoineen – syksyllä huomattavasti miellyttävämpi vaihtoehto "
             "kuin kylmä teltta."),
        ),
        (("Freestylemelonta-blogi: Synkkää kuin mörön pers... (24.9.2010)",
          FSB + "2010/09/synkkaa-kuin-moron-pers.html"),
         ("Freestylemelonta-blogi: Wave Hunters – Pahakurkkio (6.6.2012)",
          FSB + "2012/06/wave-hunters-pahakurkkio.html"),
         ("Freestylemelonta-blogi: Kalixjoki tulvalla! (4.6.2013)", FSB + "2013/06/kalixjoki-tulvalla.html"),
         ("Tuorala: Aaltomelontaa Matkakoskella ja Pahakurkkiolla 23. ja 25.7.2010",
          TUORALA + "2010/08/10/aaltomelontaa-matkakoskella-ja-pahakurkkiolla-23-ja-25-7-2010/"),
         ("Tuorala: Pahakurkkio 17.–19.9.2010", TUORALA + "2010/09/20/pahakurkkio-17-19-9-2010/"),
         ("Tuorala: Grillausta ja veden pärsketta (2012)", TUORALA + "2012/06/04/grillausta-ja-veden-parsketta/"),
         ("Tuorala: Viikko aaltoja (2013)", TUORALA + "2013/06/11/viikko-aaltoja-4-9-5-2013/"),
         ("Forsguiden: Kalixälven, Pahakurkkio (Wayback 2004)",
          "https://web.archive.org/web/20041116174352/http://forsguiden.com/river.asp?id=8&mode=print")),
    ),
    # ------------------------------------------------------------------
    "Vikaköngäs (Raudanjoki)": Kuvaus(
        "Vikaköngäs Raudanjoella Rovaniemen lähellä on rovaniemeläisille koskimelojille erittäin tuttu paikka. "
        "Se on Metsähallituksen kehittämä ulkoilualue, ja koskeen on muotoiltu suisteita, jotka tekevät "
        "akanvirtoja kalastusta ja melontaa varten. Koski toimii harjoitteluun läpi kauden, kesän 15–20 m³/s:n "
        "vähästä vedestä kevättulvien 300–450 m³/s:n pauhuun. Mittarina käytetään Olkkajärven tulovirtaamaa.",
        (
            ("Vesimäärät",
             "Akanvirrat toimivat melonnassa parhaiten alle 50 m³/s:llä. 15–20 m³/s:llä koski on melko kivinen, "
             "mutta luovittavaa löytyy aina. Kesävesillä koski on oivallinen treenipaikka vaikka slalomhenkiseen "
             "kuntomelontaan. Kevättulvilla suisteet jäävät veden alle, ja läpilaskuissa saa isomman kosken "
             "tuntumaa; isommille aalloille parasta on noin 300–350 m³/s. 13.5.2010 (180 m³/s) ei ollut vielä "
             "isoa vettä eikä oikein pelipaikkoja."),
            ("Kisat",
             "Boatercrossin SM-kisat pidettiin Vikakönkäällä 29.5.2011. Koski osoittautui erinomaiseksi "
             "boatercross-paikaksi, ja rakennettu rata keräsi kehuja."),
        ),
        (_roimeloo(12, "Koskikohde Vikaköngäs"),
         ("Tuorala: Vikaköngäs 13.5.2010", TUORALA + "2010/06/03/vikakongas-13-5-2010/"),
         ("Tuorala: Kattilakoski ja Vikaköngäs 15.–16.5.2010",
          TUORALA + "2010/06/03/kattilakoski-ja-vikakongas-15-16-5-2010/"),
         ("Tuorala: Freestyle ja BoaterX SM-kilpailut 28.–29.5.2011",
          TUORALA + "2011/09/20/freestyle-ja-boaterx-sm-kilpailut-28-29-5-2011/")),
    ),
    # ------------------------------------------------------------------
    "Korpikoski (Raudanjoki)": Kuvaus(
        "Korpikoski on Raudanjoella pieni, kivinen ja lyhyt koski, joka virtaa tien 82 sillan ali ja päättyy "
        "suureen suvantoon. Koskelle pääsee kätevästi Vikakönkään parkkipaikalta: kanna mattopesupaikan ohi "
        "moottorikelkkareitin pohjalle ja melo suvantoa pitkin kosken alle.",
        (
            ("Harjoittelupaikka",
             "Kun virtaama laskee alle 30 m³/s:n, kosken alle nousee näkyviin iso kivi, joka jakaa virran kahteen "
             "napakkaan virranrajaan. Paikka on erityisen hyvä koskikursseille ja tekniikkatreeneille, ja "
             "virranrajoissa voi pelailla vanhan koulukunnan tyyliin – 'mitä huonompi paatti, sen hauskempaa'. "
             "Korpikoski sopii erityisesti uusille koskimelojille: virta riittää tekniikan hiomiseen, mutta uinti "
             "vastaa järven rannalla pulikointia. Helppo paikka hakea tuntumaa ja vaikka rolliin rutiinia."),
        ),
        (_roimeloo(15, "Koskikohde Korpikoski"),),
    ),
    # ------------------------------------------------------------------
    "Vaattunkiköngäs (Raudanjoki)": Kuvaus(
        "Vaattunkiköngäs on Raudanjoella suora ja hiukan kapeneva koskipätkä Vaattungin retkeilyreitin "
        "tuntumassa. Matalan ja kivisen osuuden jälkeen koski kaartaa suvantoon.",
        (
            ("Harjoittelupaikka",
             "Sillan jälkeen virran molemmin puolin muodostuu akanvirrat, jotka sopivat loistavasti melontatreeniin. "
             "Alle 250 m³/s:n virtaamilla könkäässä on hyvä harjoitella jämäkämmän virran ylitystä molempiin "
             "suuntiin. Tulvavesillä saa vähän tuntumaa isomman aallokon melontaan."),
        ),
        (_roimeloo(16, "Koskikohde Vaattunkiköngäs"),),
    ),
    # ------------------------------------------------------------------
    "Marraskoski (Ounasjoki)": Kuvaus(
        "Marraskoski Ounasjoella on rovaniemeläisten perinteinen pelimelontapaikka. Koski on lyhyt: käytännössä "
        "yksi stoppari joen oikealla laidalla ja pari virranrajaa vasemmalla. Keskelle muodostuu pitkä "
        "akanvirta, jota voi käyttää surffailuun ja virranrajoissa pelailuun. Vasemman rannan kalliot sopivat "
        "kesäpäivän paistatteluun.",
        (
            ("Kesäsurffi",
             "Kesäsurffailuun sopii noin 100–250 m³/s, jolloin stopparissa on vielä kokoa ja akanvirta on "
             "käytettävissä. Yli 250 m³/s:llä surffiin on kova työ meloa ja kiire takaisin akanvirtaan, ja alle "
             "100 m³/s:llä stoppari madaltuu, mutta virranrajoissa voi yhä pelailla. Tuoralan mukaan aalto toimii "
             "noin 160–250 m³/s:llä. 9.6.2010 (88 m, noin 250 m³/s) koski oli hyvässä kunnossa koskitreeniin: "
             "virranrajat olivat voimakkaita, ja pääväylän aaltokin toimi."),
            ("Soulwave",
             "Kevättulvilla yli 800 m³/s:llä joen keskivasemmalle muodostuu isoja surffiaaltoja. Soulwaveksi "
             "ristityn aallon saa parhaiten kiinni tiputtautumalla vasemmalta rannalta, ja surffilta poistutaan "
             "samalle laidalle. Uusintasurffeille kannetaan rantapolkua pitkin, mutta aaltojen tuntumasta voi "
             "myös meloa akanvirran avulla reilusti yläpuolelle. 21.5.2010 (90 m, 1040 m³/s) keskellä jokea oli "
             "hieno surffiaalto, jossa voi surffata vaikka tunnin: vasemmalla vihreä olkapää kliineille "
             "spinneille, keskellä vähemmän kaatuva kieli ja oikealla voimakas kuohu honttoliikkeille. Joen "
             "itäpuolella oli myös pienempi surffiaalto, johon pääsi akanvirrasta."),
        ),
        (_roimeloo(13, "Koskikohde Marraskoski"),
         ("Tuorala: Marraskoski 21.5.2010", TUORALA + "2010/06/03/marraskoski-21-5-2010/"),
         ("Tuorala: Koskitreenit Marraskoskella 9.6.2010",
          TUORALA + "2010/06/11/koskitreenit-marraskoskella-9-6-2010/"),
         ("Tuorala: Kevään Marraskoski-sessiot (2011)", TUORALA + "2011/05/20/kevaan-marraskoski-sessiot/"),
         ("Tuorala: Marraskoski Soul Wave (2012)", TUORALA + "2012/05/28/marraskoski-soul-wave/"),
         ("Video: Marraskosken SoulWave (Vimeo)", "https://vimeo.com/42846932")),
    ),
    # ------------------------------------------------------------------
    "Molkoköngäs (Ounasjoki)": Kuvaus(
        "Molkoköngäs on Ounasjoella Rovaniemen ja Kittilän välissä: lyhyt ja kapeahko koskipätkä kauniin, "
        "kanjonimaisen rantamuodostelman keskellä. Sitä melotaan yleensä pelimelontahengessä.",
        (
            ("Molkoaalto",
             "Alle 300 m³/s:n virtaamilla (Kaukonen) kosken vasempaan laitaan kallioiden viereen, näköalapaikan "
             "tuntumaan, muodostuu parin surffiaallon jono. Tuoralan mukaan se toimii noin 220–280 m³/s:llä ja "
             "on parhaimmillaan noin 260–270 m³/s:llä. Paikka toimii parhaiten lyhyillä freestylekajakeilla, "
             "mutta matalammilla vesillä pidemmällekin koskikajakille löytyy lossailtavaa. Surffailu vaatii "
             "tiuhaa surffi–kanto–surffi-rytmiä, mutta napakalla melonnalla aaltojonon ja kallioiden välisen "
             "akanvirran saa kiinni.\n\n"
             "Toukokuussa 2014 Molkoaalto oli maajoukkuemelojien mukaan helppo meloa, ja nopeutta oli riittävästi. "
             "Akanvirtaan on kiire, mutta siihen ehtii lähes aina. Aalto ei ole järin suuri, mutta sopii kauden "
             "alkuun, ja myös pari alempaa aaltoa ovat blunttikelpoisia. Veden noustessa aalto muuttuu vihreäksi "
             "ja liikkeet vaikeutuvat."),
        ),
        (_roimeloo(14, "Koskikohde Molkoköngäs"),
         ("Tuorala: Molkoköngäs 5.6.2012", TUORALA + "2012/06/07/molkokongas-5-6-2012/"),
         ("Freestylemelonta-blogi: Molkoaalto (17.5.2014)", FSB + "2014/05/molkoaalto.html"),
         ("Video: Molkokönkään Molkoaalto (Vimeo)", "https://vimeo.com/channels/roimelo/43557242")),
    ),
    # ------------------------------------------------------------------
    "Kutujoki": Kuvaus(
        "Kutujoki laskee Otermajärvestä Oulujokeen Vaalan pohjoispuolella. Se on Tervajoen–Kutujoen 50 km:n "
        "melontareitin pisin ja koskisin osuus: noin 17 km ja 15 koskea. Kutujoella ovat reitin ainoat "
        "II-luokan kosket – Myllykoski aivan alussa sekä Monisaarikoski ja 1400 m pitkä Petäjäkoski joen "
        "keskivaiheilla. Muut kosket ovat I-luokkaa. Joki sopii aloitteleville ja retkeilijöille, ja se on "
        "parhaimmillaan alkukesällä.",
        (
            ("Reitti ja palvelut",
             "Joen luusuassa (Kutujoen niskalla) on riippusilta ja autiotupa, ja jokivarressa on taukopaikkoja "
             "nuotiokehineen ja huoltopalveluineen; Monisaaressa on laavu. Vauhdikkain osuus on kalanviljelylaitoksen "
             "kohdalla. Reitti päättyy Järvikylään Oulun ja Kajaanin välisen valtatie 22:n varteen, josta on "
             "Ouluun noin 87 km.\n\n"
             "Tulva-aikaan inkkarikanoottiin voi mennä jokunen aalto, mutta koskissa ennenkin käyneelle "
             "kajakkimelojalle Kutujoki on helppo. Joki tunnetaan myös virkistyskalastuksesta: siihen istutetaan "
             "pyyntikokoisia taimenia ja kirjolohia."),
        ),
        (("osm.fi: Kutujoki", "https://www.osm.fi/kutujoki/"),
         ("Visit Vaala: Tervajoen–Kutujoen melontareitti",
          "https://visitvaala.fi/retkeilykohteet/tervajoen-kutujoen-melontareitti/")),
    ),
    # ------------------------------------------------------------------
    "Tervajoki (Vaala)": Kuvaus(
        "Tervajoki on Kutujoen yläjuoksu ja Tervajoen–Kutujoen melontareitin yläosa. Pienanjärvestä "
        "Otermanjärveen on noin 14 km. Koko reitti on 50 km pitkä, ja siinä on 25 koskea ja 40 metriä "
        "putouskorkeutta. Reitti koostuu muutamasta järvestä ja niitä yhdistävistä pitkistä jokiosuuksista. "
        "Järviosuuksilla on pari selkää, mutta muuten maisemat ovat pienipiirteisiä, ja joki mutkittelee "
        "pohjoissuomalaisessa metsässä. Reitti on parhaimmillaan alkukesällä.",
        (
            ("Kosket ja palvelut",
             "Tervajoen kosket ovat I-luokkaa (mm. Vääräkoski, Pirunkoski, Pystönkoski ja Holtto) – "
             "osm.fi:n mukaan 'hyvä pikkujoki, ei yllätyskoskia'. Joen varrella on Pirunkosken autiotupa. "
             "Joensuunperältä on takaisin Ouluun noin 115 km.\n\n"
             "Tervajoella ei ole omaa vesiasemaa. Siksi sovellus käyttää mittarina Otermanjärven "
             "tulovirtaamaa, jonka päälähde Tervajoki on."),
        ),
        (("Visit Vaala: Tervajoen–Kutujoen melontareitti",
          "https://visitvaala.fi/retkeilykohteet/tervajoen-kutujoen-melontareitti/"),
         ("osm.fi: muut jokikuvaukset", "https://www.osm.fi/jokikuvaukset-muut/")),
    ),
    # ------------------------------------------------------------------
    "Oulujoki": Kuvaus(
        "Oulujoki on Oulujärven laskujoki, joka laskee Perämereen Oulussa. Se on Pohjois-Pohjanmaan ja Kainuun "
        "pääjoki, ja suurin osa Kainuusta kuuluu sen valuma-alueeseen. Joki on säännöstelty ja melottavissa "
        "aina. Oulujärveltä Ouluun maisema on hyvä, ja voimaloita ohittaessa voi miettiä, millainen joki oli "
        "ennen rakentamista.",
        (
            ("Melontamahdollisuudet",
             "Oulujoen kosket on valjastettu voimalaitoksiin, joten joki on retki- ja kuntomelontaa varten. "
             "Koskia löytyy sivujoista Sanginjoesta ja Muhosjoesta (ks. omat sivunsa)."),
        ),
        (("osm.fi: Oulujoki", "https://www.osm.fi/oulujoki/"),),
    ),
    # ------------------------------------------------------------------
    "Oulun edustan saaret": Kuvaus(
        "Oulun edustalla on helposti saavutettavia merimelontakohteita lähisaarista Hailuodon ympärimelontaan. "
        "Olosuhteet riippuvat tuulesta, eikä vesikaaviota ole. Lisäksi osm.fi:n kuvauksessa on retkiä "
        "kauemmas: Rahjan saaristoon, Perämeren pohjoisosan saarille Suomen ja Ruotsin puolella sekä "
        "Kokkolan–Vaasan saaristoon.",
        (
            ("Oulun edusta",
             "Hermannit: lähin kohde, kolme saarta noin 2,5 km Toppilan kanavan suulta länteen; keskimmäisen "
             "saaren länsirannalla on mukava hiekkaranta. Laitakari: noin 10 km Toppilan kanavan suulta, "
             "maamerkkinä puinen majakka. Kropsu: noin 1,5 km Virpiniemestä länteen, metsäinen saari ja hyvä "
             "sienipaikka. Saaressa on laituri ja nuotiopaikkoja, ja se on veneilijöiden suosikki, joten omaa "
             "rauhaa ei kannata hakea sieltä. Santapankki: hiekkasärkkä noin 16 km Martinniemestä länteen."),
            ("Hailuoto",
             "Hailuodon ympäri kertyy matkaa yli 100 km sen mukaan, kuinka tarkkaan lahdet kiertää. Saarella on "
             "pieniä autiotupia, jotka sopivat melojien tukikohdiksi: Vaskin rannalla, Ulkokarvon rannalla ja "
             "Sunijärvellä 1,4 km sisämaahan Keskikarvon majakalta. Iso laavu on Hannuksenlammella noin 1 km "
             "Hannuksennokalta sisämaahan. Marjaniemessä on leirintäalue ja Huikun lauttarannassa kahvila. "
             "Sorsastuskausi alkaa elokuun lopussa: älä silloin meloa rantapusikoissa."),
            ("Kauempana",
             "Rahja Kalajoen eteläpuolella on monien saarten ja karikkojen pieni alue, jonka ehtii kiertää "
             "viikonlopussa. Siellä on laavuja, nuotiopaikkoja ja kaksi autiotupaa, joista Koivukarin tupa on "
             "Ryöppään saarella. Ryöppään ja Pappilankarin välistä ei pääse melomalla läpi.\n\n"
             "Perämeren pohjoisosassa (Haaparanta–Kalix–Luulaja ja Perämeren kansallispuisto) on enemmän ja "
             "kallioisempia saaria hiekkarantoineen. Esimerkkejä: Selkä-Sarvi (avoin sauna, autiotupa), "
             "Haparanda Sandskär (Kumpulan kalastajakylä, autiotupa, sauna), Likskär (jatulintarhoja), Berghamn "
             "(lohkareluolat), Renskär (avoin sauna), Stora Huvön (alueen hienoin saari, hiekkasärkkä ja "
             "kallioseinä), Lill Furuön ja Rövarn. Lintujensuojelualueiden maihinnousurajoitukset ovat voimassa "
             "toukokuun alusta heinäkuun loppuun. Vesillelaskupaikkoja ovat esimerkiksi Seskarön Tromsövikenin "
             "leirintäalue, Storön ja Rörbäckin uimarannat sekä Hertsöskatanin venesatama.\n\n"
             "Kokkolan–Vaasan saaristossa (lähtö esim. Brunnilandetin venesatamasta) kohteita ovat mm. Tankar, "
             "Orsskär, Punakarit, Mikkelinsaaret ja Boskäret."),
        ),
        (("osm.fi: Oulun edustan saaret", "https://www.osm.fi/oulun-edustan-saaret/"),),
    ),
}
