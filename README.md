# Melontapaikkojen päivän tilanne (osm.fi)

Ohjelma lukee [Oulun Seudun Melojien](https://www.osm.fi/melontapaikat/)
melontapaikkojen sivujen lopussa olevista SYKE:n vesistöennustekaavioista
(vedenkorkeus/virtaama) tämän päivän tilanteen, vertaa sitä kunkin paikan
kuvauksesta analysoituihin optimiolosuhteisiin ja järjestää paikat
optimijärjestykseen. Mukana on myös kaksi Ruotsin paikkaa (Trollforsarna ja
Pahakurkkio), joiden virtaama ja ennuste haetaan SMHI:ltä; ne näkyvät vain omalla
Ruotsi-välilehdellään. Lisäksi mukana ovat Rovaniemen koskikohteet Roimeloo ry:n
foorumilta (Vikaköngäs, Korpikoski, Vaattunkiköngäs, Marraskoski ja Molkoköngäs).

```
$ uv run melonta.py
Melontapaikkojen tilanne 18.10.2026 – osm.fi + SYKE:n vesistöennusteet
Veden lämpötila (Kipinä): 2.8 °C  – kylmää vettä, pukeudu uintia varten!

 1. Koiteli (Kiiminkijoki)                      96/100     ~25 km   peli
      Haukipudas (Kiiminkijoki) vedenkorkeus 10.53 m (havainto), 3 pv: ↘ 10.47 m, tulvaindeksi 0.45
      pisteet lähipäivinä (+1/+2/+3 pv): 96 / 96 / 96
      ★ Etuaalto: parhaimmillaan
      ✓ Helmihontto: toimii (0.12 m alle parhaan)
      ★ Tukkirännin surffiaalto: parhaimmillaan
 2. Neitikoski (Lieksanjoki)                    90/100    ~390 km   peli
 3. Kipinä (Iijoki)                             80/100     ~60 km   peli
      ★ Oikean silta-aukon surffiaalto: parhaimmillaan
 ...
19. Kattilakoski (Tornionjoki)                   0/100    ~230 km   peli
      ✗ Hevosenkenkä: liian vähän vettä (puuttuu 0.60 m)
```

## Asennus ja käyttö

Tarvitset vain [uv](https://docs.astral.sh/uv/). Riippuvuudet (numpy, Pillow) on
määritelty `melonta.py`:n alussa (PEP 723), joten uv asentaa ne automaattisesti
ensimmäisellä ajokerralla – myös silloin, kun skripti ajetaan toisesta kansiosta.

```bash
uv run melonta.py                       # päivän järjestys
uv run melonta.py -v                    # kaikki kohteet, huomiot ja sivujen muut kaaviot
uv run melonta.py --tyyppi peli         # vain pelipaikat (tai: retki)
uv run melonta.py --max-km 100          # vain enintään 100 km päässä Oulusta
uv run melonta.py --json > tilanne.json # koneluettava tulos
uv run melonta.py --tallenna aineisto/  # tallenna haetut sivut ja kuvat
uv run melonta.py --offline aineisto/ --paiva 2026-10-18   # aja tallennetulla aineistolla
./melonta.py                            # sama suoraan (shebang käyttää uv:ta)
```

Kehitys (projektin ympäristö `uv.lock`-tiedoston mukaan):

```bash
uv sync                                 # luo .venv:n riippuvuuksineen ja kehitystyökaluineen
uv run pytest                           # testit
uv run tyokalut/rakenna_glyfit.py       # glyfimallien uudelleenrakennus
```

## Verkkosivuna (Vercel)

`app.py` on riippuvuudeton WSGI-sovellus: `/` näyttää järjestyksen taulukkona ja
`/api` antaa saman JSON-muodossa. Molemmat hyväksyvät suodattimet
`?tyyppi=peli|retki|ruotsi` ja `?max_km=N`. Ilman tyyppiä ("Kaikki") ja
pelipaikoissa/retkissä näytetään vain Suomen paikat; Ruotsin paikat ovat vain
`?tyyppi=ruotsi`-välilehdellä (komentorivillä `--tyyppi ruotsi`).

```bash
uv run app.py                           # paikallisesti: http://localhost:8000
npx vercel deploy                       # tai yhdistä GitHub-repo Vercel-projektiin
```

Vercel löytää `app.py`:n ja sen `app`-muuttujan automaattisesti ja asentaa
riippuvuudet `pyproject.toml`/`uv.lock`-tiedostoista. `vercel.json` ajaa funktion
Tukholmassa (`arn1`) lähellä osm.fi:tä ja SYKE:ä ja jättää testit pois paketista.

- Yksi laskenta kestää noin 20–30 s, yhdellä ytimellä mitattuna 18 s. Siinä haetaan
  23 sivua ja noin 35 kaaviota, ja kaaviot luetaan peräkkäin, koska Vercelissä
  (AWS Lambda) ei voi käynnistää prosessipoolia.
- Tulos pidetään funktion muistissa tunnin, joten `/`, `/api` ja suodattimet
  käyttävät samaa laskentaa. Lisäksi CDN tallentaa vastauksen
  (`s-maxage=3600, stale-while-revalidate=3600`), joten useimmat kävijät saavat
  sivun heti.
- Jos yhtään kaaviota ei saada luettua, vastaus on `503` eikä sitä tallenneta
  välimuistiin. CDN näyttää silloin edellisen onnistuneen version
  (`stale-if-error`).

## Miten se toimii

1. **Sivut** (`osm_sivut.py`): jokaisen melontapaikan sivu haetaan ja sen
   lopusta poimitaan SYKE-kaavioiden osoitteet (`wwwi2.ymparisto.fi/i2/...`).
   Jos sivun kaavio vaihtuu tai melontapaikat-hakemistoon ilmestyy uusi paikka,
   ohjelma huomauttaa siitä.
2. **Kaaviot** (`syke_kaavio.py`): SYKE:n kaaviot ovat vakiomuotoisia
   2700×1200 px PNG-kuvia, joissa on 9 puhdasta väriä ilman reunanpehmennystä,
   joten ne voidaan lukea pikselitarkasti:
   - y-asteikko: akselin tikit + tikkien numeroiden tunnistus glyfimalleilla
     (`glyfit.json`, rakennetaan `tyokalut/rakenna_glyfit.py`:llä);
     väärin luettu tikki hylätään suoran sovituksessa
   - **tänään** = syaani katkoviiva ("Ennusteen alku")
   - **havainto** = musta vinoneliö päiväviivalla (tänään, tai tuorein enintään 3 pv vanha)
   - **malli ja ennuste** = sininen käyrä; ennusteen *muutos* lisätään havaintoon,
     koska malli voi poiketa havainnosta (esim. Pudasjärvi: havainto 108.59 m, malli 108.44 m)
   - **historiallinen vaihteluväli** (harmaa), **mediaani** (magenta)
   - **tunnusluvut** MHW/MNW tai MHQ/MNQ selitteestä → *tulvaindeksi*
     (0 = keskimääräinen vuoden alivesi, 1 = keskimääräinen kevättulvan huippu)
   - x-akselin päivänumero tarkistetaan, jottei vanhaa kaaviota käytetä huomaamatta
3. **SYKE-data** (`syke_data.py`): kaavioiden luvut ovat myös numeroina aseman
   `ajo.json`-tiedostossa (`wwwi2.ymparisto.fi/i2/<alue>/<asema>/ajo.json`, jota
   vesi.fi käyttää). Sieltä otetaan havainto, malli ja ennuste, jos JSONin malli
   täsmää kuvasta luettuun; tunnusluvut tulevat edelleen kuvasta.
   - **Arviomalli Hawa'Iille:** Maalismaan virtaaman päiväarvo julkaistaan vasta
     seuraavana päivänä. Silloin tämän päivän arvo lasketaan Siuruanjoen virtaamasta
     (Q₁₆₀₀) ja Pudasjärven vedenkorkeudesta (Tuulisalmi 6100710, H cm, N43):

     Q = a + b·Q₁₆₀₀ + c·((H₂ − 10590)/100)³ + d·ΔH + α·(M′ − Q′)

     H₂ = (H + H′)/2 ja ΔH = H − H′ (tänään ja eilen); M′ on Maalismaan eilinen
     havainto ja Q′ kaavan eilinen arvo (eilisen virheen korjaus; jos havainto on
     n päivää vanha, paino on αⁿ). Kertoimet valitaan eilisen havainnon mukaan:

     | M′ | a | b | c | d | α |
     |---|---|---|---|---|---|
     | < 450 m³/s | 68.83 | 1.452 | 12.54 | −0.973 | 0.655 |
     | ≥ 450 m³/s | 208.23 | 1.054 | 6.454 | −1.116 | 0.858 |

     Kaavan muoto on peräisin toisesta analyysista (210 + 1,05·Q₁₆₀₀ + 6,43·((H₂−10590)/100)³
     − 1,24·ΔH, Q ≥ 450); kertoimet on sovitettu uudelleen SYKE:n päiväarvoihin
     touko–15.11. 2003–2026. Vuosittain ristiinvalidoitu keskivirhe 15.8 m³/s
     (600–800 m³/s: 11.6, yli 800: 19.6); ilman eilisen virheen korjausta 22.3 ja
     aiempi Pahkakoski + Siurua -malli (Pahkakoski julkaistaan vasta seuraavana
     päivänä) 18.9 m³/s. Virheenkorjauksen painon jakaminen 50 m³/s:n luokkiin ei
     parantanut tulosta merkittävästi (15.6), ja yli 800 m³/s se huononi.
4. **SMHI** (`smhi_data.py`): Ruotsin paikoilla ei ole osm.fi-sivua eikä
   SYKE-kaaviota, vaan mittari on muotoa `smhi/<asema>/<piste>`. Havainto on
   SMHI:n avoimen hydroobs-rajapinnan tuorein 15 minuutin virtaama (parametri 2,
   `opendata-download-hydroobs.smhi.se/.../station/<asema>/period/latest-day/data.json`)
   ja ennuste HydroNu-mallin päiväarvot (`vattenwebb.smhi.se/hydronu/data/point?subid=<piste>`,
   jonka `chartData` on sama kuin `data/chart?subid=&productionTime=`). Ennuste
   lasketaan kuten SYKE-datalla: havainto + (malli[t+n] − malli[t]). Tunnusluvut
   MQ/MHQ/MLQ ovat mallin; MLQ toimii tulvaindeksin alarajana (MNQ).
5. **Arviointi** (`arviointi.py`): jokaisen kohteen pisteet ovat 100 parhaalla
   alueella, 60–100 toimivalla alueella ja 45→0 toimivan alueen ulkopuolella
   (marginaalin matkalla). Pisteet kerrotaan kohteen laatukertoimella (esim.
   "paras pelipaikka" 1.0, retkimelonta 0.6), ja jokainen muu toimiva kohde
   tuo +2 (enintään +6). Sama lasketaan ennusteesta seuraaville kolmelle päivälle.
   Järjestys: pisteet (5 pisteen tarkkuudella), tasapisteissä lähempi paikka ensin.

## Ennusteiden arkisto ja tarkkuus

SYKE ei säilytä vanhoja ennusteitaan, joten niiden tarkkuutta voi verrata vain
omasta arkistosta. Kerran päivässä Maalismaan, Pahkakosken, Siuruan, Kurenaluksen
ja Livojoen ajo.jsonista tallennetaan ennuste (`qinlask_ka`, `qinlask_5`,
`qinlask_95`) seuraavalle 7 päivälle, havainnot (`qhav`) viimeiseltä 7 päivältä
ja sovelluksen oma Hawa'Ii-arvio ennusteineen (`ennustearkisto.py`).

Verkossa **Vercel Cron** kutsuu joka ilta klo 18 UTC (`vercel.json`) reittiä
`/api/arkistoi`, joka tallentaa päivän Firestoreen dokumentiksi
`ennusteet/YYYY-MM-DD` (`firestore.py`, REST-rajapinta palvelutilin avaimella).
Käyttöönotto:

1. Luo Firebase-projekti ja siihen Firestore-tietokanta (tuotantotila: säännöt
   estävät selainkäytön, palvelutili ohittaa ne).
2. Luo Google Cloud Consolessa (IAM → Service Accounts) palvelutili roolilla
   *Cloud Datastore User* ja sille JSON-avain. Firebase-konsolin
   "Generate new private key" käy myös, mutta sen oikeudet ovat laajemmat.
3. Lisää Vercel-projektin ympäristömuuttujiksi `FIREBASE_SERVICE_ACCOUNT`
   (avaintiedoston koko sisältö) ja `CRON_SECRET` (pitkä satunnainen merkkijono;
   Vercel lähettää sen cron-kutsun `Authorization`-otsakkeessa). Valinnaiset:
   `FIREBASE_PROJECT_ID`, `FIRESTORE_DATABASE`, `FIRESTORE_KOKOELMA`.
4. Julkaise uudelleen. Kokeile: `curl -H "Authorization: Bearer $CRON_SECRET" https://<osoite>/api/arkistoi`.

Paikallisesti samat työkalut (`FIREBASE_SERVICE_ACCOUNT` voi olla myös polku avaintiedostoon):

```bash
uv run tyokalut/arkistoi_ennusteet.py               # -> aineisto/ennusteet/YYYY-MM-DD.json
uv run tyokalut/arkistoi_ennusteet.py --firestore   # -> Firestore
uv run tyokalut/vertaa_ennusteet.py --firestore     # RMSE ja harha +1/+2/+3 pv:lle (tai --kansio, --json)
```

Vertailu laskee virheen myöhemmin julkaistuun havaintoon SYKE:n ennusteelle
sellaisenaan, SYKE:n ennusteen muutokselle tuoreimmasta havainnosta,
sovelluksen omalle ennusteelle ja vertailukohdaksi pysyvyysennusteelle
(tuorein havainto pysyy samana) sekä osuuden havainnoista SYKE:n 5–95 %:n
välillä.

## Hälytys hyvistä oloista (push-ilmoitus)

Sivun kohdasta **🔔 Hälytys hyvistä oloista** voi tilata ilmoituksen puhelimeen.
Tilaukseen lisätään yksi tai useampi ehto:

- **Paikka** ("Mikä tahansa kohde"): *toimii* = jokin kohde toimii, *optimi* =
  jokin kohde on parhaimmillaan, tai *pisteraja* (80 / 60 / 30) paikan pisteille.
- **Kohde**: *toimii* tai *optimi*. Jos kohteella ei ole toimintarajaa (se toimii
  kaikilla vesillä), toimii-ehdon tilalla on pisteraja kohteen omille pisteille.

Lisäksi valitaan, kuinka pitkälle ennustetta katsotaan (tänään … 14 päivää).
Ilmoitus kertoo ensimmäisen päivän, jona ehto täyttyy. Tilauksen jälkeen tulee
heti vahvistusilmoitus. Samasta ehdosta ilmoitetaan uudelleen vasta, kun se on
välillä lakannut täyttymästä.

- Ilmoitukset ovat selaimen Web Push -ilmoituksia (`halytykset.py`, service
  worker `/sw.js`). Ne toimivat Androidin Chromessa ja muissa työpöytäselaimissa.
  iPhonessa (iOS 16.4+) sivu lisätään ensin Safarissa Koti-valikkoon (Jaa → Lisää
  Koti-valikkoon) ja hälytys tilataan Koti-valikosta avatusta sovelluksesta. Tätä
  varten sivulla on sovellusmääritys `/manifest.webmanifest` ja kuvakkeet
  `/kuvake-<koko>.png` (`sovellus.py`).
- Tilaukset tallennetaan Firestoreen (kokoelma `halytykset`), joten käyttöönotto
  vaatii saman `FIREBASE_SERVICE_ACCOUNT`- ja `CRON_SECRET`-asetuksen kuin
  ennusteiden arkisto (yllä). Ilman Firestorea hälytysosiota ei näytetä.
- **Vercel Cron** kutsuu joka aamu klo 5 UTC reittiä `/api/halyta`, joka laskee
  päivän tilanteen ja lähettää ilmoitukset. Vanhentuneet tilaukset poistetaan.
- VAPID-avainparin palvelin luo itse ensimmäisellä kerralla ja tallentaa sen
  Firestoreen (`asetukset/vapid`). Halutessaan sen voi antaa
  ympäristömuuttujina `VAPID_PUBLIC_KEY` ja `VAPID_PRIVATE_KEY`.
  `VAPID_SUBJECT` (esim. `mailto:oma@osoite.fi`) on push-palvelulle annettava
  yhteystieto.

## Ehdota uutta kohdetta tai täydennä paikkaa

Etusivun luukusta (merkintöjen alla) pääsee lomakkeelle `/ehdota` (`ehdotukset.py`):
uusi kohde (nimi, SYKE-aseman numero tai kaavion linkki, sijainti) tai täydennys
olemassa olevaan paikkaan, kohteet toimii- ja optimirajoineen (olemassa olevan
kohteen nimellä rajakorjaus), julkaistavat vesitieto-, video- ja muut linkit,
linkit vain sivun rakentamiseen (esim. henkilökohtaiset; ei näytetä eikä linkitetä,
näkyvät vain ylläpitäjälle, täydennys ei saa julkaista niitä) sekä oma teksti.
Sähköpostia ei kerätä.

- Ehdotus tallentuu Firestoreen (kokoelma `ehdotukset`), ja ehdottaja ohjataan
  esikatseluun `/ehdotus/<salainen tunniste>`: päivän tilanne ja kaavio
  ehdotetuilla rajoilla (`/kaavio/ehdotus/<tunniste>`). Esikatselusta voi tilata
  push-ilmoituksen käsittelystä.
- Ylläpitäjä kirjautuu sivulla `/yllapito` salasanalla, joka asetetaan Vercelin
  ympäristömuuttujaan **`YLLAPITO_SALASANA`**, ja tilaa sieltä push-ilmoitukset
  uusista ehdotuksista (puhelin tai tietokoneen selain). Ilmoituksesta pääsee
  esikatseluun, jossa on Hyväksy- ja Hylkää-napit.
- Hyväksytyt uudet kohteet tulevat paikkalistaan (`kaikki_paikat()`): ne pisteytetään
  mittarin ja rajojen mukaan, saavat sään ja ajomatkan sijainnista ja ovat hälytysten
  valinnoissa; sivu on `/ehdotus/<tunniste>`. Ne listataan myös etusivun luukussa.
  Täydennykset näkyvät paikkasivun osiossa "Käyttäjien lisäykset".
- Kaksoiskappaleet: uutta kohdetta verrataan sovelluksen paikkoihin, Muihin kohteisiin
  ja muihin ehdotuksiin nimen ja sijainnin (alle 3 km) perusteella; mahdolliset osumat
  näkyvät esikatselussa ja ylläpitäjän ilmoituksessa.
- Jos uusi kohde onkin sovelluksen olemassa oleva paikka, ylläpitäjä voi esikatselussa
  muuttaa sen yhdellä napilla paikan täydennykseksi: ehdotuksen uudet pelipaikat lisätään
  paikan kohteiksi ja samannimiset rajakorjauksiksi (eri mittari lisätään paikalle).
- Roskapostin esto: piilokenttä, enintään 5 ehdotusta tunnissa samasta
  osoitteesta ja enintään 100 odottavaa ehdotusta.

### Täydennys Claude Codella (Täydennä-nappi)

Kun ehdotuksessa on vain nimi tai linkki, ylläpitäjä voi painaa **Täydennä**
(push-ilmoituksen nappi tai esikatselun ylläpitonapit). Sovellus käynnistää
GitHub Actions -ajon `.github/workflows/taydenna.yml`, jossa Claude Code
täydentää ehdotuksen ohjeen `tyokalut/TAYDENNYS.md` mukaan: lukee linkit ja muut
lähteet, etsii lähtö- ja loppupaikat, lähimmän SYKE-aseman ja vesitiedot
melontapäiviltä, arvioi rajat ja kirjoittaa kuvauksen omin sanoin. Ehdottajan
omat tiedot säilyvät sellaisinaan. Työkalu `tyokalut/taydenna_ehdotus.py`
tallentaa täydennyksen ehdotukseen, ja sovellus ilmoittaa ylläpitäjälle
(hyväksy tai hylkää) ja ehdottajalle (esikatselu valmis).

Asetukset (kerran):

| Missä | Nimi | Arvo |
|---|---|---|
| GitHub: Settings → Secrets and variables → Actions | `ANTHROPIC_API_KEY` | API-avain (console.anthropic.com, käytön mukaan) – tai `CLAUDE_CODE_OAUTH_TOKEN` = komennon `claude setup-token` tulos (Pro/Max) |
| GitHub: sama | `FIREBASE_SERVICE_ACCOUNT` | melontapaikkojen Firebase-palvelutilin JSON |
| Vercel: Environment Variables | `GITHUB_TAYDENNYS_TOKEN` | fine-grained token, vain tämä repo, *Actions: Read and write* |

## Optimiolosuhteiden analyysi

Rajat ovat sivujen kuvauksista (`paikat.py`). *Arvio* = kuvauksessa ei ole
suoraa lukua, tulkinta perusteltu sarakkeessa. Ruotsin paikoilla ei ole
osm.fi-sivua: Trollforsarnan rajat ovat paikalliselta kokeneelta melojalta
(`lahde="meloja"`). Pahakurkkion rajat ovat arvioita blogien käyntipäivistä:
Männikön virtaama on SMHI:n korjatusta päiväarkistosta (asema 11, parametri 1).
Tuomas Vaaralan [melontapäiväkirjan](https://tuorala.wordpress.com/) kesäkuun
2013 luvut (136, 125, 117, 115) täsmäävät SMHI:n Kaalasjärven (1456) päiväarvoihin
6.–9.6.2013, joten postauksen otsikon "4–9.5." on oltava kesäkuu. Kuvaukset
täydennetty ruotsalaisesta Forsguidenista (forsguiden.com, Wayback-arkisto 2004).

### Pelipaikat

| Paikka | Mittari (sivun kuva) | Kohde | Toimii | Parhaimmillaan | Peruste |
|---|---|---|---|---|---|
| **Kipinä** | Pudasjärvi vedenkorkeus | Keskimmäisen silta-aukon hontto (paras pelipaikka) | 107.7–108.1 m | 107.85–108.1 m | "toiminut erinomaisesti 107.7–108.1", yli 107.85 surffattava aalto-osa |
| | | Oikean silta-aukon surffiaalto | 108.1–108.9 m | = | "Korkealla vedellä 108.1–108.9" |
| | | Ala-aallot | 106.8–107.8 m | < 107.3 m | "parhaimmillaan kun mittari laskee alle 107.3" |
| | | *tulva* | | | "Tulva-aikaan Kipinä on tasainen" |
| **Kattilakoski** | Pello vedenkorkeus | Hevosenkenkä | 78.05–78.50 m | 78.15–78.25 m | sivun taulukko = [Tuoralan vedenkorkeusreferenssi](https://tuorala.wordpress.com/2011/05/25/kattilakosken-definitiivinen-vedenkorkeusreferenssi/) |
| | | Kakkosaalto | 78.35–78.50 m | 78.35–78.40 m | Tuorala: 78.35 parhaimmillaan, 78.50 kaatuu pohjalle |
| | | Suomenpuolen väliportaan hontto | 78.20–78.30 m | ~78.25 m | Tuorala: "äärimmäisen aliarvostettu" |
| | | Mega-aalto | 78.85–79.15 m | ~79.00 m | |
| | | Ala-aalto | 78.25 ja 78.85–79.00 m | 78.85 m | |
| | | Grillikodan hontto / Parkkihontto | ~79 m / > 79.5 m | | "mitä enemmän sen parempi" |
| | | Finnvågen | > 80.20 m | | yli 2500–3000 m³/s |
| | | Svansteinin stoppari | > 78.00 m | > 79 m | |
| **Matkakoski** | Matkakoski vedenkorkeus | Peliajan paikat | < 28.0 m | 27.5–27.8 m | alle 28 m takaisin melomalla |
| | | Isolla vedellä | 28–31 m | | pudotettava ylhäältä, kantaen |
| | | Tulva "Zambezi" | > 31 m | | kallio peittyy (autom. 500 cm) |
| **Vuentokoski** | Matkakoski | Vuento–Matkakoski | > 28.2 m | > 28.7 m | "28.2 ei juuri kannata"; [Tuorala](https://tuorala.wordpress.com/2010/06/04/vuennonkoski-ja-matkakoski-25-5-2010/): yli 2000 m³/s (n. 31 m) klassikko |
| **Kukkolankoski** | Matkakoski | Hontto + surffiaalto | 28.0–29.0 m | 28.0–28.7 m | 29.2 m liikaa |
| **Koiteli** | Haukipudas vedenkorkeus | Helmihontto | 10.3–11.0 m | ~10.7 m | |
| | | Etuaalto | 10.3–11.0 m | ≥ 10.4 m | kärryttely 10.4 m:stä |
| | | Takaköngäs | 10.5–11.05 m | 10.8–11.05 m (arvio) | "hyvä n. 11.0 ja sen alle", 10.5 kolisee |
| | | Tulikurkku (aloittelijoille) | 10.3–11.0 m (arvio) | ~10.7 m | |
| | | Tukkirännin surffiaalto | ~10.5 m | | |
| **Hawa'Ii** | Maalismaa virtaama | Murtuva aalto | > 600 m³/s | > 850 m³/s | "850 tosi hyvä ja vain paranee" |
| **Pyhäjoki** | Tolpankoski virtaama | Ruukinkoski | 45–75 m³/s | = | |
| | | Saunarannan aalto | 80–150 m³/s | ~140 m³/s | 170 liikaa |
| **Siikajoki** | Länkelä virtaama | Vaahtokylpy (murtuva aalto) | > 250 m³/s | 300–400 m³/s | |
| | | Vaahtokylpy, toinen puoli | 140–250 m³/s | ~150 m³/s (arvio) | hontto, syvyyttä volteille |
| | | Kalliosaaren paikat | 70–250 m³/s | | |
| | | Aalto 5 km alavirtaan | > 150 m³/s | | |
| **Niskakoski** | Saarenpää **virtaama** (lisäkaavio) | Stoppari / + aalto | > 50 / > 85 m³/s | | sivulla on vedenkorkeuskuva, rajat virtaamana → saman aseman virtaamakaavio |
| **Neitikoski** | Lieksanjoki, Ruunaa **virtaama** (lisäkaavio; vedenkorkeus näytetään myös) | Aalto (aaltoliikkeet) | > 40 m³/s | > 120 m³/s | [koskimelonta.com](https://koskimelonta.com/kosket/lieksanjoki-neitikoski/): yli 120 (laituri n. 9,5) jyrkempi aalto, liikkeet helpompia; meloa voi vielä 40 (laituri n. −1) |
| | | Murtuva aalto (voltit) | 100–125 m³/s | 105–120 m³/s | yli 110 (sillan mittari n. 8) murtuu pohjalle, oivallinen volttien harjoitteluun |
| | | Metsänlaidan hontto ja laiturin puolen aalto | 40–100 m³/s | = | alle 100 metsänlaitaan hontto, keskelle kieli |
| **Taivalkoski** | – | säännöstelty, vettä voi tilata | | | ei kaaviota |
| **Vikaköngäs** (Rovaniemi, Raudanjoki) | Olkkajärven tulovirtaama (l657121001y) | Akanvirrat ja treeni | 15–450 m³/s | 20–50 m³/s | [Roimeloo](https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=12): toimii koko kauden; akanvirrat parhaimmillaan alle 50, 15–20 melko kivinen |
| | | Isot aallot (kevättulva) | 200–450 m³/s | 300–350 m³/s | Roimeloo: tulvalla suisteet veden alla, 300–350 parhaimmillaan isommille aalloille |
| **Korpikoski** (Rovaniemi, Raudanjoki, tie 82) | Olkkajärven tulovirtaama | Virranrajat (kurssit, tekniikka) | aina | < 30 m³/s | [Roimeloo](https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=15): alle 30 kivi nousee ja jakaa virran kahteen virranrajaan |
| **Vaattunkiköngäs** (Rovaniemi, Raudanjoki) | Olkkajärven tulovirtaama | Akanvirrat, virranylitykset | 200–250 m³/s | = | [Roimeloo](https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=16): alle 250; alaraja (50 m³/s rajan alla ei enää hyvä) käyttäjän tarkennus |
| | | Isompi aallokko (tulva) | > 250 m³/s | = | Roimeloo: "vähäsen tuntumaa isomman aallokon melontaan" |
| **Marraskoski** (Rovaniemi, Ounasjoki) | Marraskosken virtaama (q6503600y) | Stoppari ja akanvirta (kesäsurffi) | 100–250 m³/s | 160–250 m³/s (laatukerroin 0.8 → enintään 80 p.) | [Roimeloo](https://roimeloo.net/keskustelu/viewtopic.php?f=15&t=13): yli 250 kova työ, alle 100 stoppari matala; [Tuorala 2011](https://tuorala.wordpress.com/2011/05/20/kevaan-marraskoski-sessiot/): aalto toimii n. 160–250 |
| | | Soulwave (kevättulva) | > 800 m³/s | > 1000 m³/s (100 p.) | Roimeloo: yli 800; [Tuorala 2012](https://tuorala.wordpress.com/2012/05/28/marraskoski-soul-wave/): leveä aalto yli 1000 |
| **Molkoköngäs** (Ounasjoki, tie 79) | Kaukosen virtaama (q6503300y) | Molkoaalto (surffiaaltojono) | 220–280 m³/s | 260–270 m³/s | [Tuorala 5.6.2012](https://tuorala.wordpress.com/2012/06/07/molkokongas-5-6-2012/): "toiminee virtaamilla 220-280m3 Kaukosessa", paras n. 260–270; Roimeloo: alle 300 |

### Retki- ja laskupätkät

| Paikka | Mittari | Toimii | Parhaimmillaan | Peruste |
|---|---|---|---|---|
| **Sanginjoki** | Sanginjoki virtaama | > 8 m³/s | > 12 m³/s | "ainakin 8 kuutiolla", "reilusti yli 10" |
| **Kuivajoki** | Ravaska vedenkorkeus | > 27.9 m (arvio) | > 28.4 m (arvio) | "n. 28: pienempää aaltoa ja kivien kiertelyä"; pelipätkä tulvalla (indeksi > 0.7) |
| **Olhavajoki** | Ravaska (lisäkaavio) | tulvaindeksi > 0.75 | > 0.9 | vettä 1–2 vk jäidenlähdöstä, laskee Kuivajokea nopeammin |
| **Simojoki** | Simo vedenkorkeus | retki: indeksi 0.1–0.7 | 0.2–0.6 | kesävedellä aloittelijoille |
| | | kosket + Kalliokoski: > 0.7 | > 0.85 | tulvalla vain kokeneille |
| **Lieksanjoki** | Lieksanjoki vedenkorkeus | indeksi > 0.05 | > 0.25 | kulkukelpoisuus hyvä–erinomainen, kuivalla kivistä |
| **Liminganjoki** | Tyrnävänjoki virtaama (lisäkaavio) | > 4 m³/s (arvio) | > 8 m³/s (arvio) | "Tyrnävällä 2.5 m³/s liian vähän"; sivun kuva on rikki (404) |
| **Muhosjoki** | Tyrnävänjoki virtaama (lisäkaavio) | > 3.3 m³/s | > 6 m³/s (arvio) | "syysvesillä (Tyrnävä noin 33 m/s) hiukan matalia" – tulkittu 3.3 m³/s:ksi, koska Tyrnävänjoen MHQ on vain 21.8 m³/s |
| | Tyrnävänjoki vedenkorkeus | Suokylän koskijakso: indeksi > 0.7 | > 0.85 | "voisi sopia kevättulvalla pelimelontahenkisille" |
| **Temmesjoki** | Temmesjoki virtaama + Tyrnävänjoki (lisä) | Tyrnävän indeksi > 0.2 | > 0.5 | "heti jäiden lähdettyä"; Temmesjoen kaaviossa ei tunnuslukuja |
| **Kutujoki** (alkupää – Järvikylä 17 km) | Otermajärven lähtövirtaama (q5903470y, lisäkaavio); rinnalla järven vedenkorkeus (l592621001y) | 4–30 m³/s (arvio) | 7–16 m³/s (arvio) | sivulla ei lukuja eikä kaaviota; Vaalan kunta: paras "erityisesti alkukesällä", jolloin mediaani on n. 8–10 m³/s; heinä–elokuun 2–3 m³/s (MNQ 1.2) kapealle joelle kivikkoista; yläraja MHQ 18.1 m³/s:n yli, HQ 44 m³/s |
| | | II-luokan kosket (Myllykoski, Monisaarikoski, Petäjäkoski): 5–30 m³/s (arvio) | 8–18 m³/s (arvio) | vähällä vedellä kivisiä; osm.fi: "inkkarilla saattaa tulva-aikaan jokunen aalto mennä paattiin" |
| **Tervajoki** (Vaala, Pienanjärvi – Otermanjärvi 14 km) | Otermanjärven tulovirtaama, 4 vrk ka (l592621001y, lisäkaavio) | 4–40 m³/s (arvio) | 7–20 m³/s (arvio) | ei omaa SYKE-asemaa; Tervajoki on järven päätulovirta (lisäksi Paatinjoki). Tulovirtaama on vesitaseesta laskettu, ei tunnuslukuja; mediaani toukokuussa n. 17, kesä–heinäkuussa 1–2 m³/s. [Visit Vaala](https://visitvaala.fi/retkeilykohteet/tervajoen-kutujoen-melontareitti/): paras alkukesällä; osm.fi: "ei yllätyskoskia" |
| **Kuusinkijoki** (Kuusamo, Myllykoski – Koivumutka 17 km) | Myllykosken laskennallinen virtaama (q7300350y, lisäkaavio; asemalla ei havaintoja – kaaviokuvaa ei saada luettua, joten luvut ajo.jsonista) | > 23 m³/s | > 28 m³/s (retkien vedet) | melojien havainnot: 26.6.2020 23 m³/s packraftilla (Retkipaikka), 25.5.2024 n. 50 m³/s isot aallot ja stopparit, 18.5.2025 28 m³/s kosket matalia mutta Hanhivirta ja Paljakat vielä hyviä; MHQ 42,3 m³/s. Vain korkealla vedellä ja muovikajakilla |
| **Savinajoki** (Salla–Kuusamo, Niitselyksentie – Savilampi 15,5 km) | Oulankajoen virtaama alavirrassa (q7300100y, lisäkaavio; Savinajoella ei omaa asemaa) | > 24 m³/s | > 99 m³/s (retkien vedet) | 24.6.2020 Oulankajoki 24 m³/s packraftilla helppoa I-luokkaa (Retkipaikka), 26.5.2024 Oulankajoki 99 m³/s melottu, 18.5.2025 135 m³/s "huomattavasti isompi vesi"; kesällä vähävetinen ja kivinen |
| **Oulujoki, Oulun edustan saaret** | – | | | ei kaaviota (meri: tuuli ratkaisee) |
| **Siiponjoki** (Kalajoki, Pleunan laavu – Siiponkylän silta 7 km / Konikarvo 15 km) | – | | | ei ennusteasemaa (Kurikkalassa vain havaintoasema 5300810 ilman kaaviota) |

### Ruotsi (oma välilehti `?tyyppi=ruotsi`)

| Paikka | Mittari | Kohde | Toimii | Parhaimmillaan | Peruste |
|---|---|---|---|---|---|
| **Trollforsarna** (Piteälven; tyyppi peli) | SMHI Gransel 1387 virtaama, ennuste HydroNu 31914 (sama kohta) | Paltvalsen (iso aalto) | > 170 m³/s | 190–240 m³/s | paikallinen kokenut meloja |
| | | Glashällen (pieni aalto) | > 220 m³/s | ~340 m³/s (320–360) | meloja: toimii n. 220–400+, ylärajaa ei tiedetä |
| | | Yläpätkä (Delta / keskiränni) | 140–300 m³/s | = | meloja: yli 300 "karvainen" |
| | | Satumaa (Sagoland) | 140–300 m³/s | = | meloja: samat vedet kuin Yläpätkä, helpompi |
| | | Alapätkä (Nedre Trollforsarna) | aina | > 300 m³/s | meloja: aina hyvä, parempi yli 300 |
| | | Benbrytarforsen | < 150 m³/s | < 130 m³/s | meloja: hyvä alle 130, enintään n. 150; [Forsguiden](https://web.archive.org/web/20040722032025/http://www.forsguiden.com/river.asp?id=3&mode=print): IV–VI, pyörteiset akanvirrat |
| **Pahakurkkio** (Kalixälven, Saittarova; tyyppi retki) | SMHI Männikkö 11 virtaama (n. 15 km alavirtaan, valuma-alue 5 856 km²), ennuste HydroNu 35732 (malli/mitattu kesällä mediaani 0.98) | Åretsvågen (ykköskönkään surffiaalto) | 180–260 m³/s (arvio) | 190–235 m³/s (arvio) | Männikkö: [25.7.2010](https://tuorala.wordpress.com/2010/08/10/aaltomelontaa-matkakoskella-ja-pahakurkkiolla-23-ja-25-7-2010/) 218 aalto toimi hyvin; [2.6.2012](https://tuorala.wordpress.com/2012/06/04/grillausta-ja-veden-parsketta/) 212 "hieman optimia korkeammalla", 3.6. 191 optimi; [6.–9.6.2013](https://tuorala.wordpress.com/2013/06/11/viikko-aaltoja-4-9-5-2013/) 226–239 "parhaimmillaan" laskevalla vedellä |
| | | Koskisarja 1–7 | 70–220 m³/s (arvio) | 80–190 m³/s (arvio) | [17.–19.9.2010](https://tuorala.wordpress.com/2010/09/20/pahakurkkio-17-19-9-2010/) 77–87 syysvesi helpottaa sarjaa; blogi Pohjoista melontaa 28.8.2010 96 "lähes optimaalinen"; 3.6.2012 191 koko koski hyvällä vedellä, "iso muttei kaoottinen"; heinäkuun 2010 huippu 218 "poikkeuksellisen paljon", vitonen V → yli n. 220 varoitus. Kosket 1–3 n. III, 4 hontto oikealla, 5 vaikein, 6–7 IV |
| | | Ykköskönkään hontto ja aalto matalalla | 65–110 m³/s (arvio) | 72–90 m³/s (arvio) | 17.–19.9.2010 77–87: lähes kaikki honttoliikkeet, aalto parhaimmillaan matalimmalla; [Forsguiden](https://web.archive.org/web/20041116174352/http://forsguiden.com/river.asp?id=8&mode=print): ykköspudotuksessa hontto matalalla ja iso murtuva aalto korkealla vedellä (Lappesuandon asteikolla, ei m³/s) |

## Rajoitukset

- Pisteet kuvaavat vain **vesimäärää** suhteessa kuvauksiin. Tuulta, jäätilannetta,
  kaatuneita puita, veden lämpötilaa (näytetään Kipinän kaaviosta) tai omaa
  taitotasoa ohjelma ei arvioi.
- Etäisyydet ovat likimääräisiä ajomatkoja Oulusta; ne vaikuttavat vain tasapisteissä.
- Kuvausten luvut ovat osin vuosien takaa (esim. Kipinän pelipaikat muuttuvat jäiden
  mukana). Rajat on helppo päivittää `paikat.py`:hin.
- Jos SYKE muuttaa kaavioiden ulkoasua tai fonttia, lukija antaa selkeän virheen;
  fontin muuttuessa glyfimallit rakennetaan uudelleen `tyokalut/rakenna_glyfit.py`:llä.
