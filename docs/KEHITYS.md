# Kehittäjän muistiinpanot: miten luvut lasketaan

Tämä tiedosto kertoo, mistä sivun luvut tulevat ja missä ne lasketaan. Lue se ennen kuin muutat
pisteytystä, ennusteita, arviomalleja tai kaavioita. Käyttöohje on README.md:ssä.

## Tiedostot ja vastuut

| Tiedosto | Vastuu |
|---|---|
| `paikat.py` | Paikat, mittarit (`Mittari`: kaavio, SMHI-asema) ja kohteet (`Kohde`). Kohteella on `toimii`- ja `paras`-alue (ala, ylä; `None` = avoin), `muuttuja` (arvo/tulvaindeksi), `laatu`, `kajakit`, `huom` ja `lahde`. `SIJAINNIT` sisältää koordinaatit. |
| `osm.py` | osm.fi-sivujen haku ja kaavioiden URL-avaimet (`<alue>/<asema>/<kuva>.png`). |
| `syke_kaavio.py` | `KaavioLukija` lukee SYKE:n PNG-kaavioista pikseleistä havainnon, mallin, ennusteen ja välin. `Kaaviolukema` on yhden mittarin tila. |
| `syke_data.py` | SYKE:n ajo.json (`taydenna` korvaa kuvasta luetut arvot datalla), reaaliaikamittaukset, Hawa'Ii-arviomallit ja tuntiarviot. |
| `smhi_data.py` | SMHI:n hydroobs- ja HydroNu-data (Ruotsi). |
| `arviointi.py` | Pisteytys: kohteet → paikka, sekä päivät +1…+14. |
| `melonta.py` | `kerää_tilanne` hakee kaiken rinnakkain. Sisältää myös CLI:n. |
| `kaavio_svg.py` | Omat SVG-kaaviot (SYKE, SMHI, kuvasta luettu, Hawa'Ii-arvio ja tuntikaavio). |
| `app.py` | WSGI-sivu ja API, sää, ajomatkat, surffi sekä sivun JS (`SKRIPTI`). |
| `ennustearkisto.py` | Päivittäinen arkisto Firestoreen. Vercel Cron kutsuu `/api/arkistoi` klo 18 UTC. |
| `kielet.py` | Englanninkielinen käyttöliittymä (sanakirja ja regex). Uusi suomenkielinen teksti tarvitsee käännöksen tänne. |
| `paikkakunnat.py` | Kuntalista lähtöpaikkakentälle. |

Testit ovat `tests/`-hakemistossa, ja ne ajetaan komennolla `uv run pytest`. Testien pitää mennä läpi ennen committia.

## Lukeman muodostus (SYKE)

1. Kaavion PNG luetaan `KaavioLukija.lue`:lla. Tuloksena saadaan havainto, malli (tämän päivän arvo), ennuste[n] ja 5–95 %:n väli.
2. `syke_data.taydenna` korvaa luvut ajo.jsonin tarkoilla arvoilla (`wwwi2.ymparisto.fi/i2/<alue>/<asema>/ajo.json`):
   - Sarjat ovat `qhav`/`whav` (havainnot) ja `qinlask_ka`/`wlask_ka` (malli). Tämä päivä = `ennustepvm_www`.
   - Havainnoksi kelpaa enintään 3 päivää vanha arvo (`HAVAINTO_MAX_IKA`).
   - Jos ajo.jsonin malli poikkeaa kuvasta yli toleranssin, käytetään kuvaa ja annetaan varoitus.
3. Päivän arvo (`lukema.arvo`) on havainto, jos sellainen on. Muuten se on malli.

## Pisteytys (`arviointi.py`)

- `pisteyta_kohde` laskee kohteelle pisteet 0–100:
  - Paras-alueella pisteet ovat 100.
  - Toimii-alueella pisteet ovat 60–100. Ne kasvavat lineaarisesti parhaan alueen reunaa kohti.
  - Toimii-alueen ulkopuolella pisteet ovat 45 → 0, ja ne laskevat marginaalin matkalla.
  - Tulos kerrotaan `kohde.laatu`-kertoimella.
- Oletusmarginaali on 0.3 m vedenkorkeudelle, 30 % suurimmasta rajasta virtaamalle ja 0.25 tulvaindeksille. Kohteen `Mittari.marginaali` ohittaa oletuksen.
- `_yhdista` laskee paikan pisteet: paras kohde + 2 pistettä jokaisesta muusta toimivasta kohteesta. Lisä on enintään 6 ja kokonaisuus enintään 100.
- Tulvaindeksi = (arvo − MNQ/MNW) / (MHQ/MHW − MNQ/MNW). Tunnusluvut tulevat aseman sivulta.

## Ennustepäivät (+1…+14)

- `ENNUSTEPAIVAT = 1..14` (`syke_data.ENNUSTE_PAIVIA`, kaavioiden ennusteen pituus). Päivän n arvo on `Kaaviolukema.ennuste_korjattu(n) = arvo + (ennuste[n] − malli)`.
  - Ennustetta ei siis käytetä sellaisenaan. Siitä otetaan vain muutos, joka ankkuroidaan tämän päivän havaintoon.
  - Syy: SYKE:n malli voi olla harhainen, mutta sen muutos on luotettava.
- Sivulla on jokaisesta päivästä 0..14 oma versio (`data-paiva`). JS valitsee version lähtöajan perusteella; jos paikan ennuste on lyhyempi (SMHI 10 pv), käytetään sen viimeistä päivää ennen lähtöpäivää. Lähtöaika tallennetaan sessionStorageen, ja tyhjennys palauttaa nykyhetken.
- Kaavioissa (`kaavio_svg._jatka_havainnosta`) on sama periaate:
  - Ennusteviiva alkaa viimeisestä havainnosta, ja sitä siirretään erotuksella (havainto − malli). Myös 5–95 %:n väli siirretään samalla erotuksella.
  - Mallin menneitä arvoja ei piirretä.
  - X-akseli alkaa aina 10 päivää taaksepäin (`HISTORIA_PAIVIA`).

## Hawa'Ii (Maalismaa 61/q6101750y)

Maalismaa on PVO:n voimala, joten aseman oma päivän arvo julkaistaan vasta seuraavana päivänä, eikä sille ole reaaliaikadataa. Siksi asemalle on kaksi arviomallia (`syke_data.py`).

**Ensisijainen arvio, `ARVIOMALLIT`** ("Pudasjärvi + Siurua, eilinen korjaus"). Tämä ohjaa pisteitä.
- Kaava: `Q = vakio + a·Q_Siurua + b·((H2 − 10590)/100)³ + c·ΔH + α^n·(havainto − malli n päivää sitten)`.
- H on Pudasjärven (Tuulisalmi, N43) vedenkorkeus senttimetreinä. H2 on tämän päivän ja eilisen keskiarvo, ja ΔH on tämän päivän ja eilisen erotus.
- Kertoimet valitaan tuoreimman havainnon mukaan: eri kertoimet alle ja yli 450 m³/s.
- Ristiinvalidoitu keskivirhe on 15.9 m³/s.

**Toinen arvio, `TARKENNETUT`/`Syotemalli`** ("Siurua + Kurenalus + Livojoki + Pudasjärvi"). Tämä näytetään vain tekstinä ja kaaviossa.
- Selittäjät: `[1, Q_{t−1}, Q_{t−2}, S, K, L, S', K', L', ((H2−h0)/100)³, ΔH, ti…su]`.
  - Q on Maalismaan oma virtaama. S, K ja L ovat Siuruan, Kurenaluksen ja Livojoen virtaamat. Pilkulliset (') ovat eilisiä arvoja.
  - Viikonpäivämuuttujat ovat mukana, koska säännöstelty voimala ajaa arkisin eri tavalla.
- Kertoimet valitaan eilisen virtaaman mukaan: eri kertoimet alle ja yli 350 m³/s.
- Puuttuvan oman eilisen arvon tilalle lasketaan mallin oma rekursiivinen arvio.
- Ristiinvalidoitu keskivirhe on 13.8 m³/s, ja yli 500 m³/s:n virtaamilla 12.9 (ensisijaisella mallilla 14.1).

**Syötteen arvo (`syotteen_arvo`)** valitaan tässä järjestyksessä:
1. ajo.jsonin havainto
2. tämän päivän reaaliaikamittausten keskiarvo (`<asema>/reaaliaika`)
3. tuoreimpaan havaintoon korjattu SYKE-ennuste

**Mallien sovitus**:
- Data: SYKE:n OData (`rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata`), päiväarvot vuosilta 2003–2026, toukokuusta 15.11. asti.
- Malli ristiinvalidoidaan vuosittain.
- Kertoimia vaihtaessa päivitä myös syke_datan kommentti ja virheluvut.

**Tuntiarvio (`tuntiarviot`)** käyttää TARKENNETUT-mallia syötteiden tuntimittauksiin.
- Loppupäivän syöte jatkaa viimeisen 6 tunnin lineaarista trendiä (`TUNTITRENDI`).
- Malli on sovitettu päiväarvoihin, joten tuntiarvo kertoo, mihin päivän keskiarvo on menossa.

## Reaaliaikamittaukset (SYKE)

- Osoite on `wwwi3.ymparisto.fi/i3/RealTime/data/{Q<nro>|W<nro>_<N43|NN|N60>}.txt`.
  - Rivit ovat muotoa `pp.kk.vvvv;hh:mm;arvo;`. Uusin rivi on ensimmäisenä, ja tiedosto kattaa noin 3 kuukautta.
  - Data on validoimatonta.
- Asemalistat ovat aluesivuilla `.../RealTime/PPO.htm`, `LAP.htm` jne.
- `REAALIAIKA_MITTARIT` kytkee kaavion reaaliaikatiedostoon. Kytketyn mittarin kaavion alle pinotaan (`pinoa`) tuntikaavio (`mittarin_tunnit`).
- Korkeusjärjestelmän pitää vastata ajo.jsonia (esim. Pudasjärvi N43, Länkelä NN). Tarkista se ennen uuden mittarin lisäämistä.

## Sää, ajomatkat ja surffi (`app.py`)

- Ajomatkat haetaan OSRM:n table-rajapinnasta (`distance,duration`), ja ne näytetään muodossa "km / kesto". Lähtöpaikka pyöristetään 0.01°:een, ja vastauksen cache on 1 vrk. `?v=2` ohittaa selaimeen jääneet vanhat vastaukset.
  - Valhallan "shortest" hylättiin, koska se ohjaa pikkuteille.
- Perilläoloaika = lähtö + ajoaika + 30 min (`LISAAIKA_MIN`). Sää perillä otetaan Open-Meteon tuntiennusteesta (10 vrk).
- Jos ukkoskoodi 95/96/99 osuu 4 tunnin sisään perilläolosta, ilma-linkki muuttuu punaiseksi.
- yr.no-linkki käyttää parametria `?i=<päiväsiirto>`.
- Surffi tulee Surffiennustajan rajapinnasta (`/api/forecast`). Merivesi tulee Open-Meteo Marinesta.

## Kaavioiden muoto

- Kaavio on oletuksena pystymallinen (`kaavio_svg.muoto` = "pysty", leveys 440). Otsikot, alueiden tekstit ja selite rivittyvät, ja kuva täyttää näytön leveyden.
  - SVG-tiedostolla ei ole viewport-määritystä, joten puhelin näyttää sen 980 pikselin virtuaalinäkymässä. Siksi pystymallilla ei ole max-widthiä.
- `?muoto=vaaka` antaa vanhan 900 pikselin vaakamallin. Pääsivun JS (`kaavionMuoto`) lisää parametrin kaaviolinkkeihin, kun näyttö on vähintään 700 px leveä ja leveämpi kuin korkea.
- Testit, jotka etsivät tekstejä yhtenä merkkijonona, käyttävät fixturea `vaaka` (tests/conftest.py).

## Kaavioiden alueet

- Vaalea vyöhyke on toimii-alue ja tumma paras-alue.
- Tekstit noudattavat yleissääntöä "nimi toimii (paras x–y)".
- Asteikon ulkopuoliset alueet piirretään nuolina oikeaan reunaan (↑/↓), ja nuoli viittaa toimii-rajaan.
- Tulvaindeksialueet muunnetaan MNQ/MHQ:lla arvoiksi.
- Tämän päivän lukema näkyy oranssina vinoneliönä.
- Reissu-osoitin (`kaavio_svg._reissu_osoitin`) näkyy aina, ja sitä voi vetää sormella tai hiirellä. Kaavion SVG:ssä on oma skripti, joten tämä toimii, kun kaavio avataan omana sivunaan.
  - Osoitin alkaa parametrin `?reissu=` ajasta (perilläoloaika 15 minuutin tarkkuudella), muuten nykyhetkestä.
  - Se näyttää ajankohdan ja arvon, joka interpoloidaan havainnoista ja niistä jatkuvasta ennusteesta.
  - `?matka=` on matka-aika minuutteina (ajo + 30 min). Kun osoitinta vedetään, lähtöaika = osoittimen aika − matka-aika tallennetaan sessionStorageen ja localStorageen avaimella `melonta-lahtoaika`. Pääsivu ottaa sen käyttöön `pageshow`- ja `storage`-tapahtumissa. Lähtöaika rajataan samaan ylärajaan kuin sivun lähtöaikakenttä (+14 pv klo 23.45, `syke_data.ENNUSTE_PAIVIA`, kaavioiden ennusteen pituus), joten osoitinta voi vetää enintään siihen + matka-aika. Pääsivu tuo rajan ylittävän arvon rajalle.

## Kohteiden rajojen lähteet

Rajat ovat peräisin paikkakuvauksista (osm.fi), paikallisilta melojilta (`lahde="meloja"`, mm. mpahkala.kapsi.fi-raportti) tai omasta tulkinnasta (`lahde="arvio"`). Merkitse lähde `huom`-kenttään, kun lisäät tai muutat rajoja.

## Kajakkisuositukset

`paikat.kohteen_kajakit` valitsee kohteelle suositellut kajakit. Jos kohteelle on määritetty `kajakit`, käytetään sitä. Muuten oletukset ovat nämä:
- retkikohteet: slice ja river runner
- Neitikoski: freestyle
- pelipaikkojen hontot ja stopparit (tunnistetaan nimestä) sekä `ISOT_SURFFIT`: freestyle
- muut pelipaikkojen kohteet: slice

Kuvakkeet (`app.KAJAKKI_KUVAKKEET`) erottuvat värin ja asennon perusteella:
- freestyle: oranssi, ylösalaisin
- slice: violetti, keula pystyssä
- river runner: sininen, oikein päin

Kohdelistassa näkyvät kaikki toimivat kohteet. Toimimattomat ovat piilossa "Eivät toimi nyt" -otsikon alla.

## Välimuisti ja julkaisu

- Prosessin sisäinen välimuisti on 15 min (`VALIMUISTI_S`). CDN-välimuisti asetetaan `CACHE_CONTROL`-otsakkeella.
- Main-haaraan pushattu muutos julkaistaan Verceliin automaattisesti. Tarkista julkaisu sivulta https://melontapaikat.vercel.app.
