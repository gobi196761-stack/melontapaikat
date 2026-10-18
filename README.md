# Melontapaikkojen päivän tilanne (osm.fi)

Ohjelma lukee [Oulun Seudun Melojien](https://www.osm.fi/melontapaikat/)
melontapaikkojen sivujen lopussa olevista SYKE:n vesistöennustekaavioista
(vedenkorkeus/virtaama) tämän päivän tilanteen, vertaa sitä kunkin paikan
kuvauksesta analysoituihin optimiolosuhteisiin ja järjestää paikat
optimijärjestykseen.

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
`?tyyppi=peli|retki` ja `?max_km=N`.

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
- Tulos pidetään funktion muistissa 15 minuuttia, joten `/`, `/api` ja suodattimet
  käyttävät samaa laskentaa. Lisäksi CDN tallentaa vastauksen
  (`s-maxage=1800, stale-while-revalidate=3600`), joten useimmat kävijät saavat
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
     seuraavana päivänä. Silloin tämän päivän arvo lasketaan yläpuolisista asemista:
     Maalismaa = 1.078 × Pahkakoski + 0.911 × Siurua − 5.4 m³/s (Pahkakosken arvona
     tuorein havainto + SYKE:n ennusteen muutos). Sovitus SYKE:n päiväarvoihin
     avovesikausina 2003–2026; testijakson 2020–2026 keskivirhe 10.5 m³/s, kun
     Pudasjärven vedenkorkeus + Siurua antoi 18.8 m³/s.
4. **Arviointi** (`arviointi.py`): jokaisen kohteen pisteet ovat 100 parhaalla
   alueella, 60–100 toimivalla alueella ja 45→0 toimivan alueen ulkopuolella
   (marginaalin matkalla). Pisteet kerrotaan kohteen laatukertoimella (esim.
   "paras pelipaikka" 1.0, retkimelonta 0.6), ja jokainen muu toimiva kohde
   tuo +2 (enintään +6). Sama lasketaan ennusteesta seuraaville kolmelle päivälle.
   Järjestys: pisteet (5 pisteen tarkkuudella), tasapisteissä lähempi paikka ensin.

## Ennusteiden arkisto ja tarkkuus

SYKE ei säilytä vanhoja ennusteitaan, joten niiden tarkkuutta voi verrata vain
omasta arkistosta. `tyokalut/arkistoi_ennusteet.py` tallentaa kerran päivässä
Maalismaan, Pahkakosken, Siuruan, Kurenaluksen ja Livojoen ajo.jsonista
ennusteen (`qinlask_ka`, `qinlask_5`, `qinlask_95`) seuraavalle 7 päivälle,
havainnot (`qhav`) viimeiseltä 7 päivältä ja sovelluksen oman Hawa'Ii-arvion
ennusteineen tiedostoon `aineisto/ennusteet/YYYY-MM-DD.json`.

```bash
uv run tyokalut/arkistoi_ennusteet.py   # kerran päivässä, esim. illalla SYKE:n päivityksen jälkeen
uv run tyokalut/vertaa_ennusteet.py     # RMSE ja harha +1/+2/+3 pv:lle (--json koneluettavana)
```

Vertailu laskee virheen myöhemmin julkaistuun havaintoon SYKE:n ennusteelle
sellaisenaan, SYKE:n ennusteen muutokselle tuoreimmasta havainnosta,
sovelluksen omalle ennusteelle ja vertailukohdaksi pysyvyysennusteelle
(tuorein havainto pysyy samana) sekä osuuden havainnoista SYKE:n 5–95 %:n
välillä. `aineisto/` on `.gitignore`ssa, joten arkisto jää ajokoneelle.

## Optimiolosuhteiden analyysi

Rajat ovat sivujen kuvauksista (`paikat.py`). *Arvio* = kuvauksessa ei ole
suoraa lukua, tulkinta perusteltu sarakkeessa.

### Pelipaikat

| Paikka | Mittari (sivun kuva) | Kohde | Toimii | Parhaimmillaan | Peruste |
|---|---|---|---|---|---|
| **Kipinä** | Pudasjärvi vedenkorkeus | Keskimmäisen silta-aukon hontto (paras pelipaikka) | 107.7–108.1 m | 107.85–108.1 m | "toiminut erinomaisesti 107.7–108.1", yli 107.85 surffattava aalto-osa |
| | | Oikean silta-aukon surffiaalto | 108.1–108.9 m | = | "Korkealla vedellä 108.1–108.9" |
| | | Ala-aallot | 106.8–107.8 m | < 107.3 m | "parhaimmillaan kun mittari laskee alle 107.3" |
| | | *tulva* | | | "Tulva-aikaan Kipinä on tasainen" |
| **Kattilakoski** | Pello vedenkorkeus | Hevosenkenkä | 78.05–78.50 m | 78.15–78.25 m | sivun taulukko |
| | | Mega-aalto | 78.85–79.15 m | ~79.00 m | |
| | | Ala-aalto | 78.25 ja 78.85–79.00 m | 78.85 m | |
| | | Grillikodan hontto / Parkkihontto | ~79 m / > 79.5 m | | "mitä enemmän sen parempi" |
| | | Finnvågen | > 80.20 m | | yli 2500–3000 m³/s |
| | | Svansteinin stoppari | > 78.00 m | > 79 m | |
| **Matkakoski** | Matkakoski vedenkorkeus | Peliajan paikat | < 28.0 m | 27.5–27.8 m | alle 28 m takaisin melomalla |
| | | Isolla vedellä | 28–31 m | | pudotettava ylhäältä, kantaen |
| | | Tulva "Zambezi" | > 31 m | | kallio peittyy (autom. 500 cm) |
| **Vuentokoski** | Matkakoski | Vuento–Matkakoski | > 28.2 m | > 28.7 m | "28.2 ei juuri kannata" |
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
| **Neitikoski** | Lieksanjoki vedenkorkeus | Aalto/stoppari | aina | tulvaindeksi 0.2–0.9 (arvio) | tulvalla vaikea, matalalla stoppari |
| **Taivalkoski** | – | säännöstelty, vettä voi tilata | | | ei kaaviota |

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
| **Kutujoki, Oulujoki, Oulun edustan saaret** | – | | | ei kaaviota (meri: tuuli ratkaisee) |

## Rajoitukset

- Pisteet kuvaavat vain **vesimäärää** suhteessa kuvauksiin. Tuulta, jäätilannetta,
  kaatuneita puita, veden lämpötilaa (näytetään Kipinän kaaviosta) tai omaa
  taitotasoa ohjelma ei arvioi.
- Etäisyydet ovat likimääräisiä ajomatkoja Oulusta; ne vaikuttavat vain tasapisteissä.
- Kuvausten luvut ovat osin vuosien takaa (esim. Kipinän pelipaikat muuttuvat jäiden
  mukana). Rajat on helppo päivittää `paikat.py`:hin.
- Jos SYKE muuttaa kaavioiden ulkoasua tai fonttia, lukija antaa selkeän virheen;
  fontin muuttuessa glyfimallit rakennetaan uudelleen `tyokalut/rakenna_glyfit.py`:llä.
