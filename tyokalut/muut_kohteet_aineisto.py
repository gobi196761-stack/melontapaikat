"""Kokoaa muut_kohteet.json Timo Piiraisen melontapäiväkirjasta (Word) ja täydentää sen.

Käyttö:
    python3 tyokalut/muut_kohteet_aineisto.py MELOTUT_JOET.docx VALIMUISTI_HAKEMISTO

Välimuistihakemistoon tallentuvat paikannimihaun (Photon / OpenStreetMap), SYKE:n
asemaluettelon ja virtaamien vastaukset, jotta ajo on toistettava eikä kuormita
palveluita. Vaiheet:

1. Word-dokumentin kappaleet jäsennetään reiteiksi: reitti alkaa "Lähtö:"-rivistä,
   otsikko on sitä edeltävä otsikkorivi ja ISOILLA kirjoitettu rivi luettelee joet.
2. Lähtö- ja loppupaikka paikannetaan: jokaiselle reitin nimelle (lähtö, kohde,
   joet) haetaan ehdokkaat ja valitaan se ehdokas, jonka lähellä (25 km) on eniten
   reitin muita nimiä. Vuosilisäysten otsikon kunta rajaa ehdokkaat.
3. Ajomatka Oulusta lähtöpaikalle lasketaan OSRM:llä.
4. Melontapäivän virtaama haetaan SYKE:n asemalta, jonka nimessä on reitin joen
   nimi ja joka on enintään 60 km:n päässä reitistä.
5. LISATIEDOT-sanakirjan muista lähteistä kootut tiedot liitetään reitin nimen mukaan.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

UA = {"User-Agent": "melontapaikat/1.0 (https://github.com/gobi196761-stack/melontapaikat)"}
OULU = (65.0121, 25.4651)
SYKE = "https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata"

# Sovelluksen pisteytetyt paikat samalla joella: joen nimi -> (osoite, nimi)
PAIKKASIVUT = {
    "Lieksajoki": ("/paikka/lieksanjoki-matkalahti-siikakoski", "Lieksanjoki (Matkalahti – Siikakoski)"),
    "Kiiminkijoki": ("/paikka/koiteli-kiiminkijoki", "Koiteli (Kiiminkijoki)"),
    "Simojoki": ("/paikka/simojoki", "Simojoki"),
    "Iijoki": ("/paikka/kipina-iijoki", "Kipinä (Iijoki)"),
    "Raudanjoki": ("/paikka/vikakongas-raudanjoki", "Vikaköngäs (Raudanjoki)"),
    "Vikajoki": ("/paikka/vikakongas-raudanjoki", "Vikaköngäs (Raudanjoki)"),
    "Ounasjoki": ("/paikka/marraskoski-ounasjoki", "Marraskoski (Ounasjoki)"),
    "Torniojoki": ("/paikka/kattilakoski-tornionjoki", "Kattilakoski (Tornionjoki)"),
    "Pyhäjoki": ("/paikka/pyhajoki", "Pyhäjoki"),
    "Siikajoki": ("/paikka/siikajoki-poyryn-pato", "Siikajoki (Pöyryn pato)"),
}

MH_OULANKA = ("Metsähallitus: Oulangan melontaesite",
              "https://julkaisut.metsa.fi/assets/pdf/lp/Esitteet/oulankamelonta-en.pdf")
LISATIEDOT: dict[str, list[tuple[str, str, str]]] = {
    "Sallan suunnasta Kuusamon puolelle": [
        ("Metsähallituksen mukaan Oulankajoen yläosan melontareitti Savilammelta Taivalkönkäälle on 3,7 km. "
         "Taivalköngäs on ohitettava kävellen, ja Kiutakönkään laskeminen kanootilla on hengenvaarallista. "
         "Sallan puolella on merkitty Savinajoen melontareitti (14 km).", *MH_OULANKA),
        ("Luontoon.fi: Oulankajoen koskimelontareitti Savilampi – Kiutakönkään leirintäalue, 13,4 km (Kuusamo, Salla).",
         "luontoon.fi: Oulankajoen koskimelontareitti",
         "https://www.luontoon.fi/en/trails/oulankajoen-koskimelontareitti-savilampi-kiutakonkaan-leirintaalue-kuusamo-500518-en"),
    ],
    "Niemelä – Niitselyksentien silta": [
        ("Sallan puolella on merkitty Savinajoen melontareitti, pituus 14 km.", *MH_OULANKA),
    ],
    "Oulanka – Venojärvi": [
        ("Oulankajoen kansallispuiston melontareitit: yläosan reitti Savilampi – Oulangan luontokeskus noin 13 km "
         "(Taivalköngäs ohitetaan kävellen) ja alaosan reitti Kiutakönkään alapuolelta Jäkälämutkaan 25 km.", *MH_OULANKA),
    ],
    "Kajakilla kahden Kuusamon kylän väliä": [
        ("Metsähallituksen esitteen mukaan Kitkajoen yläosan melontareitti on 21 km.", *MH_OULANKA),
        ("Käylän ja Juuman välillä on seitsemän koskea, joista yksi on III-luokan putous; Juuman alapuolella "
         "oleva Jyrävä on VI-luokkaa ja ohitetaan maitse.", "Ruka: koskenlasku Kitkajoella",
         "https://www.ruka.fi/en/experiences/water-activities/rafting"),
        ("Kitkajoki alkaa Ala-Kitkasta ja laskee Oulankajokeen lähellä itärajaa.", "Wikipedia: Kitkajoki",
         "https://en.wikipedia.org/wiki/Kitkajoki"),
    ],
    "Kuusamon itäpuolelta kohti kaakkoa": [
        ("Kuusinkijoen melontareitti on Metsähallituksen esitteen mukaan 17,5 km.", *MH_OULANKA),
    ],
    "Ensimmäinen syksyinen tuntuma": [
        ("Naruskajoen melontareitti on kaikkiaan 58 km: Auermajoen sillalta Naruskajärvelle 13 km ja "
         "Naruskajärveltä Tenniöjoelle 45 km. Maltiojoen reitti on 21 km. Reiteistä on julkaistu "
         "Naruska- ja Tenniöjoen melontareittikartta.", *MH_OULANKA),
    ],
    "Toinen keväinen koetus": [
        ("Naruskajoen melontareitti on kaikkiaan 58 km: Auermajoen sillalta Naruskajärvelle 13 km ja "
         "Naruskajärveltä Tenniöjoelle 45 km.", *MH_OULANKA),
    ],
    "Naruskajoen latvoilla": [
        ("Naruskajoen melontareitin yläosa Auermajoen sillalta Naruskajärvelle on 13 km.", *MH_OULANKA),
    ],
    "Kuolajokea pitkin Saijan kylälle": [
        ("Kuolajoen melontareitti on Metsähallituksen esitteen mukaan 24,5 km.", *MH_OULANKA),
    ],
    "Vastavirtaan sivujoelle": [
        ("Kuolajoen melontareitti on Metsähallituksen esitteen mukaan 24,5 km.", *MH_OULANKA),
    ],
    "Aatsingin haudalta pohjoiseen": [
        ("Aatsinkijoen melontareitti on Metsähallituksen esitteen mukaan 14 km.", *MH_OULANKA),
    ],
    "Hukkala - Värtsilä": [
        ("Jänisjoen melontareitti on noin 100 km. Ruskeakosken, Vihtakosken, Saarion ja Vääräkosken "
         "voimalaitokset ohitetaan maitse; alkukesällä vettä on yleensä hyvin, loppukesällä koskiosuudet "
         "madaltuvat.", "luontoon.fi: Jänisjoen melontareitti",
         "https://www.luontoon.fi/en/trails/janisjoen-melontareitti-tohmajarvi-tohmajarvi-526376-en"),
    ],
    "Jänisjoen latvoilla": [
        ("Jänisjoen melontareitti on noin 100 km, ja Reki- ja Kuuttijoen haarassa on erityisen kivikkoinen osuus.",
         "luontoon.fi: Jänisjoen melontareitti",
         "https://www.luontoon.fi/en/trails/janisjoen-melontareitti-tohmajarvi-tohmajarvi-526376-en"),
    ],
    "Varajoki – Lentuan leirintäalue": [
        ("Lentuankoski on kaksiosainen (Iso ja Pikku Lentuankoski), yhteensä noin 1 200 m. Koskelle on "
         "Kuhmon keskustasta noin 15 km: Kuhmo–Suomussalmi-tieltä Lentuankoskentielle.",
         "Visit Finland: Lentua rapids and Lentua lake",
         "https://www.visitfinland.com/fr/produit/fa82ed4d-14f2-439e-9fa5-f151f5763625/lentua-rapids-and-lentua-lake/"),
    ],
    "Siltakoski – Pälvekoski": [
        ("Jongunjoen melontareitti Kuhmon Jonkerista Lieksan Nurmijärvelle on 62,9 km ja vaativa; pudotusta on "
         "80 m. Osuuksia (esim. Teljon silta – Aittokoski, Aittokoski – Viitakoski) voi meloa erikseen.",
         "VisitKarelia: Jongunjoen melontareitti",
         "https://www.visitkarelia.fi/en/hiking-routes/jongunjoki-canoeing-route-kuhmo-jonkeri-lieksa-nurmijarvi"),
    ],
    "Suolajoki- Jongunjoki": [
        ("Jongunjoen melontareitti Kuhmon Jonkerista Lieksan Nurmijärvelle on 62,9 km ja vaativa; pudotusta on 80 m.",
         "VisitKarelia: Jongunjoen melontareitti",
         "https://www.visitkarelia.fi/en/hiking-routes/jongunjoki-canoeing-route-kuhmo-jonkeri-lieksa-nurmijarvi"),
    ],
    "Koitajoki – Oinassalmi": [
        ("VisitKarelian yli 100 km:n reitti kulkee Nehvonniemeltä Petkeljärven kautta Koitajokeen ja Koitereelle. "
         "Lylykoskella on varottava: kevättulvalla porras voi olla melottavissa, muuten maihin ennen koskea. "
         "Möhkössä ja Petkeljärvellä on kesäisin välinevuokrausta ja majoitusta.",
         "VisitKarelia: Nehvonniemi – Petkeljärvi – Koitajoki – Koitere",
         "https://www.visitkarelia.fi/en/hiking-routes/over-100-km-paddling-route-from-nehvonniemi-through-petkeljarvi-to-koitajoki-and-koitere"),
    ],
    "Ala-Koitajoki": [
        ("Koitajoki alkaa Ilomantsin itärajalta, virtaa Venäjän Karjalan kautta ja palaa Suomeen; alajuoksulla "
         "valtaosa vedestä johdetaan tunnelissa Pamilon voimalaitokselle.", "Wikipedia: Koitajoki",
         "https://en.wikipedia.org/wiki/Koitajoki"),
    ],
    "Ruunaalla": [
        ("Ruunaan pisin koskireitti Matkalahdelta Naarajoen sillalle on noin 30 km. Ruunaan luontokeskus on "
         "Naarajoella, 13 km Pankakoskelta.", "luontoon.fi: Lieksanjoen melontareitti",
         "https://www.luontoon.fi/en/trails/lieksanjoen-melontareitti-lieksa-526310-en"),
    ],
    "Vettä pitkin pohjanlahteen": [
        ("Kiiminkijoki on noin 170 km pitkä ja laskee Perämereen Haukiputaalla.", "Wikipedia: Kiiminkijoki",
         "https://en.wikipedia.org/wiki/Kiiminkijoki"),
        ("Perinteinen Kiiminkijoen melontaretki kulkee Ylikiimingin Vengasrannasta Koitelinkoskelle, noin 25 km.",
         "Kaleva", "https://www.kaleva.fi/kiiminkijokimelonta-paattyy-tana-vuonna-koiteliin-/4571359"),
    ],
    "Kainuun korvessa kiantajärven latvoilla": [
        ("Hossa – Juntusranta -melontareitti on noin 40 km, josta koskia 7 km; retkeen kuluu 2–3 päivää. Reitin "
         "voi aloittaa esimerkiksi Matalajoelta. Hossanjoen kosket ovat kivikkoisia, eikä reittiä suositella "
         "matalalla vedellä kokemattomille.", "nationalparks.fi: Hossa Canoeing Routes",
         "https://www.nationalparks.fi/hossa/canoeingroutes"),
    ],
    "Iso-Peranka – Paloranta": [
        ("Metsähallituksen Peranka – Hossa -melontareitti Iso-Perankajärveltä Papinpetäjän rantautumispaikalle "
         "on 37 km, kaksipäiväinen ja keskivaativa–vaativa; matalalla vedellä haastava.",
         "Metsähallitus: Peranka – Hossa -melontaesite",
         "https://julkaisut.metsa.fi/wp-content/uploads/sites/2/2021/07/hossa_perankamelontaeng.pdf"),
    ],
    "Kemijoen latvoilla Pelkosenniemellä": [
        ("Kitinen on 235 km pitkä, Suomen neljänneksi pisin joki.", "Wikipedia: Kitinen",
         "https://en.wikipedia.org/wiki/Kitinen"),
    ],
    "Inarijärven latvoilla": [
        ("Juutuanjoki virtaa Solojärvestä Inarijärveen. Jäniskoskella on riippusilta ja joen pohjoispuolella "
         "laavu; Juutuan reitti (6,3 km) kulkee Siidasta joen vartta Jäniskoskelle.",
         "Metsähallitus: Inarin retkireitit", "https://julkaisut.metsa.fi/wp-content/uploads/sites/2/2024/12/inarinretkireititfineng.pdf"),
    ],
    "Alainenjärämä – Vikkuri": [
        ("Könkämäeno alkaa Kilpisjärvestä ja muodostaa Muonionjoen ja Tornionjoen kanssa Suomen ja Ruotsin rajan.",
         "Wikipedia: Könkämäeno", "https://en.wikipedia.org/wiki/K%C3%B6nk%C3%A4m%C3%A4eno"),
    ],
    "Silamus - Kangaskoski": [
        ("Hiitolanjoen kolme voimalaitospatoa (Kangaskoski, Ritakoski ja Lahnasenkoski) on purettu Laatokan "
         "järvilohen vaellusreitin avaamiseksi; Kangaskoski purettiin ensimmäisenä.",
         "Dam Removal Europe: Hiitolanjoki", "https://damremoval.eu/portfolio/kangaskoski-finland/"),
    ],
    "Rautjärvi – Purnujärvi": [
        ("Helisevänjoki saa alkunsa Ruokolahden järviltä, ylittää valtakunnanrajan ja laskee Vuokseen.",
         "Etelä-Karjala: Helisevänjoki", "https://www.ekarjala.fi/?p=1387"),
    ],
    "Ämmänkoski": [
        ("Ämmäkosken ohitusuoma ja kalatie avattiin 30.11.2022; ohitusuomaan juoksutetaan 5 m³/s ja 3,5 hehtaarin "
         "koskialueelle 10 m³/s. Kunnostus paransi koskialueen virkistyskäyttöä.",
         "Valtioneuvosto: Vesi virtaa Ämmäkosken ohitusuomassa",
         "https://valtioneuvosto.fi/-/1410837/vesi-virtaa-ammakosken-ohitusuomassa"),
    ],
    "Kuusaankoskella": [
        ("Kuusaankoski on suosittu kalastuskoski kulttuurimaisemassa Keski-Suomessa.", "Wikipedia: Kuusaankoski",
         "https://en.wikipedia.org/wiki/Kuusaankoski"),
    ],
    "Simunankoskella": [
        ("Simunankoski on Kynsivesi–Leivonveden laskujoki Kuusveteen ja kuuluu Rautalammin reittiin; "
         "kosken kalataloudellinen kunnostus 1995 lähes kolminkertaisti taimenen poikastiheyden.",
         "Luke: raportti 210", "https://jukuri.luke.fi/bitstream/10024/536464/1/raportti210.pdf"),
    ],
    "Kalkkistenkoskella": [
        ("Kalkkistenkoski on yksi Etelä-Suomen harvoista luonnontilaisista suurista koskista, ja rannat ja "
         "saaret kuuluvat Kalkkistenkosken luonnonsuojelualueeseen. Viereinen Kalkkisten kanava (1878) yhdistää "
         "Päijänteen ja Ruotsalaisen.", "Visit Päijänne: Attractions in Asikkala and Vääksy",
         "https://visitpaijanne.fi/wp-content/uploads/2017/11/Attractions-in-Asikkala-and-V%C3%A4%C3%A4ksy.pdf"),
    ],
    "Kolkunjärveltä Keiteleelle": [
        ("Kolima–Keitele-koskireitin Kymönkoskea, Kellankoskea ja Kärnänkoskea kunnostettiin 2018; "
         "Kymönkoskella ovat Karoliinan portaat.", "Eräluvat: Kolima-Keitele rapids route",
         "https://www.eraluvat.fi/en/fishing/fishing-permits/angling-permit/alueet/kolima-keitele-rapids-route.html"),
    ],
    "Palokinkosket": [
        ("Palokki on kansallisen kalatiestrategian ja Vuoksen vesienhoitosuunnitelman kohde; Heinäveden reitin "
         "koskia kunnostettiin yli kymmenen vuotta sitten.", "Selvitys Palokin koskireitistä (2023)",
         "https://www.sll.fi/app/uploads/sites/133/2023/02/Selvitystyo-Palokin-koskireitin-ja-vesivoimalaitoksen-kalatalousratkaisuihin-kytkeytyvista-kehittamismahdollisuuksista-Teemu-Hentinen-POSELY_4.2.2023.pdf"),
    ],
    "Tunnetulla melontajoella": [
        ("Meltausjoki virtaa vapaana Unarijärvestä Rovaniemen luoteisosan halki ja on suosittu melontajoki; "
         "Unarinkönkään alapuolella on yksityinen osuus.", "Eräluvat: Meltausjoki",
         "https://www.eraluvat.fi/en/fishing/fishing-permits/angling-permit/alueet/river-meltausjoki.html"),
    ],
}


# ---------------------------------------------------------------------------
# 1. Jäsennys

KENTTA = re.compile(r'^(Lähtö ja kohde|Lähtö|Kohde|Korkeuserot?|Matka|Aika)\s*:?\s*(.*)$')
AVAIN = {"Lähtö ja kohde": "lahto", "Lähtö": "lahto", "Kohde": "kohde", "Korkeusero": "korkeusero",
         "Korkeuserot": "korkeusero", "Matka": "matka", "Aika": "aika"}


def _isot(t: str) -> bool:
    k = re.sub(r'[^A-Za-zÅÄÖåäö]', '', t)
    return len(k) > 3 and k.isupper()


def kappaleet(docx: str) -> list[str]:
    x = zipfile.ZipFile(docx).read('word/document.xml').decode()
    out = []
    for p in re.findall(r'<w:p[ >].*?</w:p>', x, re.S):
        t = html.unescape(''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p))).strip()
        if t:
            out.append(re.sub(r'\s+', ' ', t))
    loppu = next(i for i, t in enumerate(out) if t.replace(" ", "").startswith("P-Savo"))
    return out[1:loppu]


def jasenna(paras: list[str]) -> list[dict]:
    reitit, kesken, cur, kokoelma, osio, suljettu = [], [], None, "Melottuja jokireittejä", None, True
    for t in paras:
        m = KENTTA.match(t)
        if m:
            if suljettu or cur is None:
                otsikot, ryhma = list(kesken), None
                if len(otsikot) > 1 and not re.match(r'^(\d+\.|[A-Z]\))', otsikot[0]) and re.match(r'^\d+\.', otsikot[1]):
                    ryhma = otsikot.pop(0)
                cur = {"kokoelma": kokoelma, "osio": osio, "ryhma": ryhma, "otsikot": otsikot,
                       "kentat": {}, "teksti": [], "joet": []}
                reitit.append(cur)
                kesken, suljettu = [], False
            k = AVAIN[m.group(1)]
            cur["kentat"][k] = (cur["kentat"][k] + " / " if k in cur["kentat"] else "") + m.group(2).strip()
            if m.group(1) == "Lähtö ja kohde":
                cur["kentat"]["kohde"] = m.group(2).strip()
            continue
        if t.startswith("MUUN SUOMEN JOKIREITTEJÄ"):
            kokoelma, osio, suljettu, kesken = "Muun Suomen jokireittejä", None, True, []
            continue
        my = re.match(r'^(20\d\d) \(\d+\)$', t)
        if my:
            kokoelma, osio, suljettu, kesken = f"Melotut {my.group(1)}", None, True, []
            continue
        mo = re.match(r'^(\d+)\.\s*(.+)$', t)
        if kokoelma.startswith("Muun") and mo and _isot(mo.group(2)):
            osio, suljettu, kesken = mo.group(2).strip(), True, []
            continue
        if (_isot(t) and not re.match(r'^(\d+\.|[A-Z]\))', t) and "," not in t[-25:]) or \
                (_isot(t) and cur and not suljettu and cur["teksti"]):
            if cur:
                cur["joet"].append(t)
                suljettu = True
            continue
        otsikkomainen = bool(re.match(r'^(\d+\.|[A-Z]\))', t) or re.search(r', [A-ZÄÖÅ][A-ZÄÖÅ-]+$', t))
        if cur is None or suljettu or otsikkomainen or kesken:
            if otsikkomainen and cur:
                suljettu = True
            kesken.append(t)
        else:
            cur["teksti"].append(t)
    for r in reitit:
        nimi = " / ".join(re.sub(r'^(\d+\.|[A-Z]\))\s*', '', o) for o in r["otsikot"]) or (r["osio"] or "").capitalize()
        km = re.search(r', ([A-ZÄÖÅ][A-ZÄÖÅ -]+)$', nimi)
        r["kunta"] = km.group(1).title() if km else None
        r["nimi"] = (nimi[:km.start()] if km else nimi).strip()
    for a, b in zip(reitit, reitit[1:]):   # A-kohta ilman omaa tekstiä: sama kuvaus kuin B-kohdalla
        if not a["teksti"] and not a["joet"] and a["osio"] and a["osio"] == b["osio"]:
            a["teksti"], a["joet"] = b["teksti"], b["joet"]
    return reitit


def jokilista(r: dict) -> list[str]:
    out = []
    for rivi in r["joet"]:
        for osa in re.split(r'\s*[–,]\s*|\s+-\s*|\s*-\s+|(?<=JOKI)-|(?<=PURO)-', rivi):
            osa = osa.strip(" -").title()
            if osa and osa not in out:
                out.append(osa)
    return out


def tunniste(nimi: str, kaytetyt: set[str]) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", nimi).encode("ascii", "ignore").decode().lower()).strip("-")
    perus, i = t, 2
    while t in kaytetyt:
        t, i = f"{perus}-{i}", i + 1
    kaytetyt.add(t)
    return t


# ---------------------------------------------------------------------------
# 2. Paikannus

def paikan_nimi(teksti: str) -> str:
    t = re.split(r'\s+(n\.|\d)', teksti)[0]
    return re.sub(r',.*$', '', t).strip(" .")


def etaisyys(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def photon(nimi: str, valimuisti: dict) -> list[dict]:
    if nimi not in valimuisti:
        u = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": nimi, "limit": 15, "bbox": "19,59.5,32,70.2"})
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as v:
            valimuisti[nimi] = [{"lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0],
                                 **{k: f["properties"].get(k) for k in ("name", "osm_key", "osm_value", "city", "county", "state", "district", "country")}}
                                for f in json.load(v)["features"] if f["properties"].get("countrycode") in ("FI", "SE", "NO")]
        time.sleep(0.6)
    return valimuisti[nimi]


def _nimi_osuu(ehdokas: dict, nimi: str) -> bool:
    return (ehdokas.get("name") or "").lower().startswith(nimi.lower()[:max(4, len(nimi) - 3)])


def paikanna(r: dict, valimuisti: dict) -> dict:
    nimet = {"lahto": paikan_nimi(r["kentat"].get("lahto", "")), "kohde": paikan_nimi(r["kentat"].get("kohde", ""))}
    joet = r["jokilista"]
    kunnat = [k.strip().lower() for k in re.split(r"[-–]", r["kunta"] or "") if k.strip()]
    ehdokkaat: dict[str, list[dict]] = {}
    for avain, nimi in [*nimet.items(), *((f"joki{i}", j) for i, j in enumerate(joet))]:
        if not nimi or len(nimi) < 3:
            continue
        lista = [c for c in photon(nimi, valimuisti) if _nimi_osuu(c, nimi)]
        if kunnat:
            rajattu = [c for c in lista if (c.get("city") or "").lower() in kunnat or (c.get("county") or "").lower() in kunnat]
            lista = rajattu or lista
        if lista:
            ehdokkaat[avain] = lista
    paras, paras_pisteet = None, -1
    for avain, lista in ehdokkaat.items():
        for c in lista:
            p = (c["lat"], c["lon"])
            pisteet = sum(1 for a2, l2 in ehdokkaat.items() if a2 != avain
                          and any(etaisyys(p, (d["lat"], d["lon"])) < 25 for d in l2))
            pisteet += 0.5 if avain.startswith("joki") and c.get("osm_value") in ("river", "stream", "canal") else 0
            if pisteet > paras_pisteet:
                paras, paras_pisteet = c, pisteet
    tulos = {"keskus": None, "lahto": None, "kohde": None}
    if paras is None or (paras_pisteet < 1 and len(ehdokkaat) > 1 and not kunnat):
        return tulos
    keskus = (paras["lat"], paras["lon"])
    tulos["keskus"] = paras
    for avain in ("lahto", "kohde"):
        lahin = min(ehdokkaat.get(avain, []), key=lambda c: etaisyys(keskus, (c["lat"], c["lon"])), default=None)
        if lahin and etaisyys(keskus, (lahin["lat"], lahin["lon"])) < 40:
            tulos[avain] = lahin
    return tulos


# ---------------------------------------------------------------------------
# 3. Ajomatkat ja 4. virtaamat

def ajomatkat(pisteet: list[tuple[float, float]]) -> list[dict | None]:
    tulos: list[dict | None] = []
    for i in range(0, len(pisteet), 90):
        osa = pisteet[i:i + 90]
        koord = ";".join(f"{p[1]:.5f},{p[0]:.5f}" for p in [OULU, *osa])
        u = (f"https://router.project-osrm.org/table/v1/driving/{koord}?sources=0"
             "&annotations=distance,duration")
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))
        for m, s in zip(d["distances"][0][1:], d["durations"][0][1:]):
            tulos.append({"km": round(m / 1000), "min": round(s / 60)} if m is not None else None)
        time.sleep(2)
    return tulos


def paiva(aika: str | None) -> dt.date | None:
    if not aika:
        return None
    m = re.search(r'(\d{1,2})\.(?:\s*-\s*\d{1,2}\.)?(\d{1,2})\.(\d{2,4})', aika) or \
        re.search(r'(\d{1,2})-\d{1,2}\.(\d{1,2})\.(\d{2,4})', aika)
    if not m or "–" in aika and "useina" in aika:
        return None
    v = int(m.group(3))
    v = v + 2000 if v < 50 else v + 1900 if v < 100 else v
    try:
        return dt.date(v, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _dms(s: str) -> float:
    s = s.zfill(6)
    return int(s[:-4]) + int(s[-4:-2]) / 60 + int(s[-2:]) / 3600


def virtaama(r: dict, keskus, paiva_: dt.date | None, asemat: list[dict], valimuisti: dict) -> str | None:
    if not keskus or not paiva_:
        return None
    joet = [j for j in r["jokilista"] if j.lower().endswith(("joki", "jokea", "eno"))]
    ehdokkaat = []
    for a in asemat:
        if a["Suure_Id"] != 2 or not a.get("KoordLat"):
            continue
        nimi = a["Nimi"].lower()
        if any(j.lower() in nimi for j in joet):
            d = etaisyys(keskus, (_dms(a["KoordLat"]), _dms(a["KoordLong"])))
            if d < 60:
                ehdokkaat.append((d, a))
    for d, a in sorted(ehdokkaat, key=lambda x: x[0]):
        avain = f"{a['Paikka_Id']}/{paiva_}"
        if avain not in valimuisti:
            u = (f"{SYKE}/Virtaama?$filter=Paikka_Id%20eq%20{a['Paikka_Id']}%20and%20Aika%20eq%20"
                 f"datetime'{paiva_}T00:00:00'")
            arvot = json.load(urllib.request.urlopen(u, timeout=60))["value"]
            valimuisti[avain] = float(arvot[0]["Arvo"]) if arvot else None
        if valimuisti[avain] is not None:
            q = valimuisti[avain]
            luku = f"{q:.1f}" if q < 20 else f"{q:.0f}"
            return f"SYKE {paiva_.day}.{paiva_.month}.{paiva_.year}: {a['Nimi']} {luku} m³/s (vuorokausiarvo)"
    return None


# ---------------------------------------------------------------------------

def _kunta(c: dict | None) -> str | None:
    return (c or {}).get("city") or (c or {}).get("county")


def main(docx: str, hakemisto: str) -> None:
    hak = Path(hakemisto)
    hak.mkdir(exist_ok=True)
    pv = hak / "photon.json"
    sv = hak / "syke_virtaamat.json"
    valimuisti = json.loads(pv.read_text()) if pv.exists() else {}
    syke_vm = json.loads(sv.read_text()) if sv.exists() else {}
    asemat = json.loads((hak / "syke_asemat.json").read_text())
    reitit = jasenna(kappaleet(docx))
    kaytetyt: set[str] = set()
    out = []
    for r in reitit:
        r["jokilista"] = jokilista(r)
        sij = paikanna(r, valimuisti)
        keskus = (sij["keskus"]["lat"], sij["keskus"]["lon"]) if sij["keskus"] else None
        k = r["kentat"]
        kohde = {
            "tunniste": tunniste(r["nimi"] + (f"-{r['jokilista'][0]}" if r["nimi"] in {x['nimi'] for x in out} and r["jokilista"] else ""), kaytetyt),
            "nimi": r["nimi"] + (f" ({r['kunta']})" if r["kunta"] else ""),
            "kokoelma": r["kokoelma"], "osio": r["osio"], "ryhma": r["ryhma"],
            "lahto": k.get("lahto"), "kohde": k.get("kohde"), "korkeusero": k.get("korkeusero") or None,
            "matka": k.get("matka"), "aika": k.get("aika"),
            "kuvaus": r["teksti"], "joet": r["jokilista"],
            "lahto_sijainti": [round(sij["lahto"]["lat"], 5), round(sij["lahto"]["lon"], 5)] if sij["lahto"] else None,
            "kohde_sijainti": [round(sij["kohde"]["lat"], 5), round(sij["kohde"]["lon"], 5)] if sij["kohde"] else None,
            "lahto_kunta": _kunta(sij["lahto"]) or _kunta(sij["keskus"]) or r["kunta"],
            "kohde_kunta": _kunta(sij["kohde"]),
            "alue": [round(keskus[0], 5), round(keskus[1], 5)] if keskus else None,
            "vesi": virtaama(r, keskus, paiva(k.get("aika")), asemat, syke_vm),
            "lisatiedot": [{"teksti": t, "lahde": l, "url": u} for t, l, u in LISATIEDOT.get(r["nimi"], [])],
        }
        for joki in r["jokilista"]:
            if joki in PAIKKASIVUT:
                kohde["paikkasivu"] = list(PAIKKASIVUT[joki])
                break
        out.append(kohde)
        pv.write_text(json.dumps(valimuisti, ensure_ascii=False))
        sv.write_text(json.dumps(syke_vm, ensure_ascii=False))
    lahdot = [(i, x["lahto_sijainti"] or x["alue"]) for i, x in enumerate(out) if x["lahto_sijainti"] or x["alue"]]
    for (i, _), ajo in zip(lahdot, ajomatkat([tuple(p) for _, p in lahdot])):
        out[i]["ajo"] = ajo
    tiedosto = Path(__file__).resolve().parent.parent / "muut_kohteet.json"
    tiedosto.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(out), "reittiä;", sum(1 for x in out if x["lahto_sijainti"]), "lähtöpaikkaa,",
          sum(1 for x in out if x["kohde_sijainti"]), "loppupaikkaa,", sum(1 for x in out if x["vesi"]), "virtaamaa")


if __name__ == "__main__":
    main(*sys.argv[1:3])
