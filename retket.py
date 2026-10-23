"""Retkiehdotukset (/retki/<tunniste>): useamman paikan viikonloppuretket.

Koottu melontaseuran retkisuunnitelmasta; henkilö- ja ryhmäkohtaiset tiedot (päivämäärät,
majoitusvaraukset, hinnat, sopimukset) on jätetty pois. Paikkojen vesitilanne ja rajat
tulevat paikkasivuilta.
"""

from __future__ import annotations

import html

e = html.escape

RETKET: dict[str, dict] = {
    "kuusamon-tulvajoet": {
        "nimi": "Kuusamon tulvajoet – pitkä viikonloppu",
        "johdanto": (
            "Kitkajokea vähemmän tunnetut Kuusinki- ja Savinajoki ovat pienempiä, tulvalla melottavia koskijokia "
            "Kuusamossa ja Sallassa. Molempien varrella on jylhiä kallioita. Pidempään viikonloppuun, esimerkiksi "
            "helatorstaina, mahtuu kummankin joen lasku – tulvan mukaan useampaankin kertaan – ja kävelyretki "
            "Oulangan maisemissa. Majoitukseksi sopii mökki Rukan lähistöltä."),
        "osiot": [
            ("Ajankohta",
             "Kummankin joen paras aika on kevättulva toukokuun puolivälistä loppuun. Kesällä Savinajoki on "
             "vähävetinen ja kivinen, ja Kuusinkijokea suositellaan melottavaksi vain korkealla vedellä. Tulvan "
             "ajoitus vaihtelee vuosittain: 25.5.2024 Kuusinkijoessa oli noin 50 m³/s, 18.5.2025 vain 28 m³/s, "
             "kun taas Savinajoessa oli 2025 selvästi enemmän vettä kuin 2024 (yläpuolinen järvi suli myöhemmin). "
             "Seuraa SYKE:n ennustetta paikkasivuilta muutama viikko ennen lähtöä."),
            ("Päiväohjelma",
             "1. päivä: siirtyminen Oulusta Kuusamoon (noin 250 km). Iltapäivällä Kitkajoki (Käylä – Juuma) tai "
             "kävely Pienellä Karhunkierroksella; illalla sauna.\n\n"
             "2. päivä: Kuusinkijoki Myllykoskelta Koivumutkaan (noin 12–17 km, 2,5–3 h melontaa). Autojen siirto "
             "ennen melontaa.\n\n"
             "3. päivä: Savinajoki Niitselyksentieltä Savilammelle (15,5 km, noin 3 h) ja kajakkien kanto noin "
             "1 km pysäköintialueelle (40 min). Halutessa katsotaan Kiutakönkään yläpuolinen pieni, mahdollisesti "
             "surffattava aalto.\n\n"
             "4.–5. päivä: uusinnat vesitilanteen mukaan ja paluu Ouluun."),
            ("Varusteet",
             "Vesi on erittäin kylmää ja kosket pitkähköjä, osin jyrkkien kalliorantojen välissä, joten kuivapuku "
             "on välttämätön. Kuusinkijoki on kivinen: muovikajakki. Savilammen kantoon liina tai muu vetoköysi. "
             "Kävelyä varten retkeilyvarusteet (Pieni Karhunkierros on lähellä)."),
            ("Autot",
             "Kuusinkijoella autojen siirto hiekkamontulta Koivumutkan lopetuspaikalle on noin 28 km (40 min). "
             "Lyhyempi siirto Lohipyörteen lopetuspaikalle on noin 9 km, mutta tie on osin erittäin huono ja "
             "kajakkien kanto pitkä. Saunavaarantien loppuosa oli 2025 niin huonossa kunnossa, että autot "
             "jätettiin noin 2 km rannasta."),
        ],
        "paikat": [("/paikka/kuusinkijoki", "Kuusinkijoki – kosket, rajat ja vesitilanne"),
                   ("/paikka/savinajoki", "Savinajoki – rajat ja vesitilanne"),
                   ("/muut/kajakilla-kahden-kuusamon-kylan-valia", "Kitkajoki, Käylä – Juuma (Muut kohteet)")],
        "lahteet": [("Retkisuunnitelma: Kuusinki- ja Savinajoki 2026 (koskikuvaukset ja melojien vesihavainnot "
                     "2024–2025)", None),
                    ("Metsähallitus: Oulangan melontaesite",
                     "https://julkaisut.metsa.fi/assets/pdf/lp/Esitteet/oulankamelonta-en.pdf")],
    },
}


def sivu(tunniste: str, tyyli: str) -> str | None:
    r = RETKET.get(tunniste)
    if r is None:
        return None
    osiot = "".join(f"<h2>{e(o)}</h2>" + "".join(f"<p>{e(k)}</p>" for k in t.split("\n\n")) for o, t in r["osiot"])
    paikat = "".join(f'<li><a href="{e(u)}">{e(n)}</a></li>' for u, n in r["paikat"])
    lahteet = "".join(f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a></li>' if u
                      else f"<li>{e(n)}</li>" for n, u in r["lahteet"])
    return f"""<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(r["nimi"])} – Melontapaikat</title>
<link rel="icon" type="image/png" href="/kuvake-192.png">
<style>{tyyli}</style>
</head>
<body><main class="kuvaus">
<a class="takaisin" href="/">← Melontatilanne</a>
<h1>{e(r["nimi"])}</h1>
<div class="meta">retkiehdotus</div>
<p>{e(r["johdanto"])}</p>
<h2>Paikat ja vesitilanne</h2>
<ul>{paikat}</ul>
{osiot}
<h2>Lähteet</h2>
<ul class="lahteet">{lahteet}</ul>
</main>
</body>
</html>"""
