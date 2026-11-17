# Besluiten en open punten

Twee lijsten: wat nog besloten of uitgezocht moet worden, en welke keuzes zijn gemaakt en waarom.

## Open besluiten en vragen

| # | Onderwerp | Wat is er aan de hand | Bij wie | Gevolg tot dan |
|---|---|---|---|---|
| 1 | **Welke records publiceren we?** | Beantwoord door de beheerder (17 november): de OAI-sets zijn geen publicatievlag maar een zoekopdracht op een pointerfile. `books` = records met een exemplaarnummer (`exemplaar.nummer = "*"`), `article` = artikelen met `bron.Repository` gevuld. Het API geeft alle records terug, behalve wat een medewerker heeft uitgesloten (bij boeken komt dat volgens hem niet voor). Daarmee zijn de aantallen verklaard: van de ongeveer 216.900 API-records in het boekenbereik staan er 155.422 in de OAI; de ongeveer 61.500 overige hebben geen exemplaar (13.956 onder 2e8, 10.427 vooral tijdschriftrecords in 4e8-5e8, 31.245 rapporten in 5e8-6e8, 5.835 vanaf 6e8). Open: moet de dataset alle API-records bevatten, of alleen boeken met een exemplaar? | RCE | `scope: oai`: alleen records met een exemplaar (artikelen: met `bron.Repository`) |
| 2 | **Reeksen in de OAI** | Was weg door een wijziging in de datastructuur; de beheerder heeft dat hersteld en wij hebben het gecontroleerd: `oai_dc_book` bevat nu `dc:series` (naam en deelnummer als twee elementen). Het API blijft rijker (plaats en uitgever apart, CHT-IRI's, monumenten), dus de boeken blijven uit het API komen. | n.v.t. | opgelost; geen wijziging nodig |
| 3 | **Tijdschrift bij een artikel** | Opgelost. Een artikelrecord heeft een groep `Source` met `source.title.lref`: het priref van het tijdschriftrecord. Die groep komt alleen mee met de juiste alias: `archrep` met `fields=…` (zie [architectuur.md](architectuur.md)). Artikelen komen nu volledig uit het API; de OAI is alleen de selectie. | n.v.t. | opgelost |
| 4 | **Licentie van de metadata** | `LICENSE_URI` is leeg: records hebben geen `schema:license`. | RCE | geen licentie in de data |
| 5 | **Oude graphs in `rce/bibliotheek`** | `bib`, `bib-aut`, `bib-corpaut`, `bib-publishers`, `bib-series`, `bib-thesaurus` bevatten een oudere conversie. De boeken staan daardoor tijdelijk dubbel. | RCE | oude graphs blijven ongemoeid |
| 6 | **NDE Datasetregister** | De dataset moet nog met een beschrijving worden aangemeld, zoals bij de andere RCE-datasets. Los van deze pijplijn. | RCE | n.v.t. |
| 7 | **Testdataset vóór livegang** | De Triply-dataset staat vast in de workflow (`rce/bibliotheek`). Een eerste run naar een aparte testdataset zou veiliger zijn. | beheerder van de pijplijn | eerst `publish` uit |
| 8 | **Tweede volledige run** | De eerste publicatie is gelukt: 155.422 boeken en 26.265 artikelen staan in `…/graphs/books` en `…/graphs/article`. Nog niet gezien: dat een tweede run (`--mode overwrite`) de aantallen gelijk laat, en de werkelijke looptijd van een run met tijdvakken. | beheerder van de pijplijn | zie [beheer.md](beheer.md) |
| 9 | **710 artikelen alleen in de OAI-set `books`** | Verklaard: het zijn artikelen met een exemplaarnummer (dus in `books`) maar zonder `bron.Repository` (dus niet in `article`). Steekproef van 40: allemaal `source.Repository` leeg, maar mét tijdschrift (`source.title` en `source.title.lref`); bij 40 artikelen uit beide sets is `source.Repository` altijd `x`. Het zijn dus gewone artikelen met tijdschrift. Publiceren? | RCE | worden niet gepubliceerd |

## Mogelijke vervolgstappen

- **Tijdschriften als eigen nodes met hun eigen gegevens.** Het tijdschrift heeft nu een adres (zijn priref) en een link naar zijn
  catalogusrecord. Het tijdschriftrecord zelf (uitgever, plaats, ISSN) staat er nog niet bij; het is op te halen met `priref=400009141`.
- **Reeksen koppelen aan de aparte database `series`** (11.282 reeksen met priref). Nu zijn het teksten met naam en deelnummer.
- **Authority-nummers voor auteurs** (NTA, VIAF), zodat gelijke namen niet langer worden samengevoegd.
- **Trefwoorden als thesaurus-URI's.** Alleen `Content_subject` verwijst nu naar de CHT; `Keyword` is tekst.
- **Plaats bij een uitgever.** De oude data had `schema:location` bij uitgevers; hier staat de plaats bij het boek.

## Genomen besluiten

| Besluit | Waarom |
|---|---|
| **Code onder GPL-3.0** | dezelfde licentie als de kunst-ETL ([LICENSE](../LICENSE)). Geldt voor de code; de licentie van de metadata staat apart open (zie boven). |
| **De OAI bepaalt de selectie, het API levert de inhoud** | de OAI is het kanaal dat de beheerder bewust openbaar maakt; het API bevat meer. Het API heeft de rijkere gegevens (reeks, plaats en uitgever apart, CHT). |
| **Artikelen komen volledig uit het API (alias `archrep` met gekozen velden); de OAI geeft de selectie** | het API heeft titel, onderwerpen, CHT-koppelingen en de groep `Source` met het priref van het tijdschrift. Eerder werden API en OAI samengevoegd omdat de alias `books` het tijdschrift niet geeft. De alias `article` was geen oplossing: die geeft in een oogst geen `lead_word`, CHT-koppelingen of `lref` (de lijstvelden van die alias zijn beperkt; bij één record zijn het er meer). |
| **Velden kiezen met `api_fields`, en bewaken dat het tijdschriftadres meekomt** | `archrep` geeft alle velden, ook interne (gebruikersnamen, eigenaar, plankmarkering). Met `fields=` vraag je alleen op wat je publiceert, en het scheelt 70% omvang. Of een alias een veld teruggeeft, valt niet uit de configuratie af te leiden en bleek anders bij een oogst dan bij één record; daarom faalt de run als het adres van het tijdschrift ontbreekt. |
| **Een artikel dat het API niet levert, wordt niet gepubliceerd** | zoals bij boeken: geteld als `missing_in_api` of `unreadable`. Het werd eerder uit de OAI alleen geschreven, zonder titel. |
| **Auteurs en uitgevers delen één adres per naam** | zo werkt "alle boeken van X", zoals in de oude graphs `bib-aut` en `bib-publishers`. Nadeel: een homoniem wordt samengevoegd (er is geen authority-nummer). |
| **Organisatie als auteur en uitgever is één node** | het Frans Halsmuseum was in de oude data al zo (één URI voor beide rollen). |
| **`schema:author` én `schema:creator`** | `author` is specifieker; het CN-profiel toetst op `creator`. Een extra triple per auteur. |
| **Type `Book`/`Article` plus `CreativeWork`** | het CN-profiel toetst op `CreativeWork`. |
| **CHT-term rechtstreeks als IRI bij `schema:about`** | het API levert alleen de IRI; het label staat in de CHT-graph van dezelfde dataset. |
| **Reeksnummer in `schema:position`** | past bij `CreativeWorkSeries`; het nummer kan tekst zijn (`97/3`, `III.3`). |
| **Monument-node zonder naam** | hetzelfde monumentnummer komt met verschillende namen voor; een gedeelde node mag maar één naam per taal hebben. De validatie vond dit op 3.000 echte boeken. |
| **`comments`, `Digital_reference`, `shelf_mark` niet publiceren** | interne notities, externe links via een proxy, een magazijnnummer |
| **Interne links uit de OAI (`proza.ocw.local`) niet publiceren** | zijn alleen intern bereikbaar; een SHACL-patroon laat alleen de openbare catalogus toe |
| **Eén vaste graph per bron, `overwrite` + `merge`** | de graph van de vorige run wordt vervangen, er loopt niets op. Andere graphs worden niet geraakt. |
| **Elke run oogst alles** | de OAI meldt geen verwijderde records (`deletedRecord = No`). |
| **Een run faalt liever dan dat hij stilzwijgend onvolledig is** | tellers worden tegen de bron gecontroleerd; een deel publiceren is erger dan niets. |
| **Records die falen laten geen halve triples achter** | een record wordt eerst apart opgebouwd. |
| **Warnings blokkeren niet, Violations wel** | bekende hiaten in de bron (een boek zonder auteur) mogen publicatie niet tegenhouden. |
| **`startfrom` begint bij 1 en dubbelen laten de run falen** | het API laat anders pagina's overlappen (gevonden in een live steekproef). |
| **Artikelen in de OAI-set `books` lopen via de bron `article`** | de boekenset bevat ook alle artikelen (`exclude_priref`); zo staat elk artikel één keer, met tijdschriftgegevens uit de artikelset. |
| **Een record dat het API niet kan leveren wordt overgeslagen, tot 10 stuks** | één kapot bronrecord (priref 450004680) liet de eerste volledige run na 3 uur omvallen. Elk overgeslagen record staat met priref in het manifest; `MAX_UNREADABLE_IN_API` is `0` te zetten voor een strenge run. |
| **OAI-selectie in tijdvakken parallel** | de selectie duurde achter elkaar 3u12m. Tijdvakken overlappen op de grens (anders gaan records met fracties van een seconde verloren) en elk tijdvak en het totaal worden gecontroleerd. |
| **Tijdelijke serverfouten opnieuw proberen, syntaxisfouten niet** | de Adlib-server gaf in een GitHub Action eenmalig een interne fout. |
