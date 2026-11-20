# Besluiten en open punten

Twee lijsten: wat nog besloten of uitgezocht moet worden, en welke keuzes zijn gemaakt en waarom.

## Open besluiten en vragen

| # | Onderwerp | Wat is er aan de hand | Bij wie | Gevolg tot dan |
|---|---|---|---|---|
| 1 | **Welke records publiceren we?** | Beantwoord door de beheerder (17 november): de OAI-sets zijn geen publicatievlag maar een zoekopdracht op een pointerfile. `books` = records met een exemplaarnummer (`exemplaar.nummer = "*"`), `article` = artikelen met `bron.Repository` gevuld. Het API geeft alle records terug, behalve wat een medewerker heeft uitgesloten (bij boeken komt dat volgens hem niet voor). Daarmee zijn de aantallen verklaard: van de ongeveer 216.900 API-records in het boekenbereik staan er 155.422 in de OAI; de ongeveer 61.500 overige hebben geen exemplaar (13.956 onder 2e8, 10.427 vooral tijdschriftrecords in 4e8-5e8, 31.245 rapporten in 5e8-6e8, 5.835 vanaf 6e8). Open: moet de dataset alle API-records bevatten, of alleen boeken met een exemplaar? Op 20 november meldde een afnemer dat 43% van de oude catalogus in het nieuwe model ontbreekt (zie [Terugmelding van de afnemer](#terugmelding-van-de-afnemer-20-november-2026)). | RCE | Doel gesteld op 20 november: een zo compleet mogelijke dataset, zodat het oude model kan vervallen. Daarom staat `scope` nu op `api` (alles wat het API oplevert, ongeveer 337.000 records); nog niet gedraaid en nog niet bevestigd door RCE. Terugzetten is `scope: oai`. |
| 2 | **Reeksen in de OAI** | Was weg door een wijziging in de datastructuur; de beheerder heeft dat hersteld en wij hebben het gecontroleerd: `oai_dc_book` bevat nu `dc:series` (naam en deelnummer als twee elementen). Het API blijft rijker (plaats en uitgever apart, CHT-IRI's, monumenten), dus de boeken blijven uit het API komen. | n.v.t. | opgelost; geen wijziging nodig |
| 3 | **Tijdschrift bij een artikel** | Opgelost. Een artikelrecord heeft een groep `Source` met `source.title.lref`: het priref van het tijdschriftrecord. Die groep komt alleen mee met de juiste alias: `archrep` met `fields=…` (zie [architectuur.md](architectuur.md)). Artikelen komen nu volledig uit het API; de OAI is alleen de selectie. | n.v.t. | opgelost |
| 4 | **Licentie van de metadata** | `LICENSE_URI` is leeg: records hebben geen `schema:license`. | RCE | geen licentie in de data |
| 5 | **Oude graphs in `rce/bibliotheek`** | `bib`, `bib-aut`, `bib-corpaut`, `bib-publishers`, `bib-series`, `bib-thesaurus` bevatten een oudere conversie. De boeken staan daardoor tijdelijk dubbel. | RCE | oude graphs blijven ongemoeid |
| 6 | **NDE Datasetregister** | De dataset moet nog met een beschrijving worden aangemeld, zoals bij de andere RCE-datasets. Los van deze pijplijn. | RCE | n.v.t. |
| 7 | **Testdataset vóór livegang** | De Triply-dataset staat vast in de workflow (`rce/bibliotheek`). Een eerste run naar een aparte testdataset zou veiliger zijn. | beheerder van de pijplijn | eerst `publish` uit |
| 8 | **Tweede volledige run** | De eerste publicatie is gelukt: 155.422 boeken en 26.265 artikelen staan in `…/graphs/books` en `…/graphs/article`. Nog niet gezien: dat een tweede run (`--mode overwrite`) de aantallen gelijk laat, en de werkelijke looptijd van een run met tijdvakken. | beheerder van de pijplijn | zie [beheer.md](beheer.md) |
| 9 | **710 artikelen alleen in de OAI-set `books`** | Verklaard: het zijn artikelen met een exemplaarnummer (dus in `books`) maar zonder `bron.Repository` (dus niet in `article`). Steekproef van 40: allemaal `source.Repository` leeg, maar mét tijdschrift (`source.title` en `source.title.lref`); bij 40 artikelen uit beide sets is `source.Repository` altijd `x`. Het zijn dus gewone artikelen met tijdschrift. Publiceren? | RCE | worden niet gepubliceerd |
| 10 | **Tijdschriftartikelen zonder `source.Repository`** | Gemeten op 20 november in het Adlib-API (priref 2e8 tot 3e8): 120.455 artikelen, waarvan 26.566 met `source.Repository` en 93.889 zonder. De selectie `article` (pointer 1970, 26.265 records) bevat alleen de eerste groep. De rest, 94.190 artikelen buiten pointer 1970, zijn gewone tijdschriftartikelen: bijna allemaal met tijdschrift (`source.title`; 214 van de 120.455 niet), vaak met onderwerpen en CHT-koppelingen (voorbeelden: *Archaeometry*, *Mannus*, *Nieuwe Drentse Volksalmanak*). De OAI kent ze wel: `document:200052267` bestaat (datestamp 10 september 2024), alleen niet in de set `article`. Het catalogusrecord 200052267 is openbaar. Het oude model (maart 2025) bevatte ze. Niet bekend wat `source.Repository` voor de bibliotheek betekent: een publicatievlag of een aanduiding dat het artikel in het eigen bezit is? Een omzetting is alleen een configuratiewijziging (`scope: api` bij de bron `article`; `api_search` staat al op 2e8 tot 3e8), maar ook dan haalt de run records binnen die nu bewust niet gepubliceerd worden. | beheerder (betekenis van `source.Repository`), daarna RCE | Klaargezet met `scope: api` voor artikelen, zie besluit 1. De volledigheidscontrole eiste voor artikelen nog de OAI-teller; dat is aangepast. Steekproef op 480 echte records uit de nieuwe reeksen (artikelen buiten pointer 1970 en boeken buiten pointer 1964, in vijf nummerreeksen): geen transformatiefouten, geen SHACL-Violations, wel waarschuwingen voor ontbrekende auteur, uitgever of jaar (bij de rapporten uit het begin van de 5e8-reeks ontbreken die ook in Adlib zelf). |
| 11 | **Records die het API niet kan uitleveren** | Gemeten op 20 november met een scan van het hele boekenbereik (alleen priref's opgevraagd, 6,5 minuten): vier records geven een foutmelding van de server, ook bij een directe opvraag: **143525, 143526, 143527** (`Tag 'b%' not found in database 'document'`) en **450004680** (`Invalid integer value '76, 85' for Field 't3'`). De overige 216.883 records van 216.887 zijn leesbaar; in de artikelreeks is er geen. Deze vier staan niet in het nieuwe model en worden bij elke run in het manifest genoemd (`unreadable_ids`). Staan ze wel in het oude model? Dat is nog niet nagegaan. | beheerder (herstellen in Adlib) | overgeslagen; de run faalt pas bij meer dan `MAX_UNREADABLE_IN_API` (10) |

## Terugmelding van de afnemer (20 november 2026)

Meting via de SPARQL-ingang van `rce/bibliotheek`, na de upload van 17 november. De getallen komen uit die terugmelding en zijn hier niet opnieuw gemeten.
Kern: het nieuwe model (`graphs/books` 155.422 + `graphs/article` 26.923 = 182.335 records) is een deel van de catalogus; het oude model
(`graph/bib`, maart 2025) heeft 320.652 records, waarvan 138.327 alleen daar. Voor de demo gebruiken de Elastic-service en de koppeling met
monumenten daarom het oude model.

| Punt uit de terugmelding | Wat het hier betekent | Bij wie |
|---|---|---|
| **43% van de catalogus ontbreekt** (138.327 records alleen in het oude model; vooral 2xxxxxxxx: 92.182 van 118.447, en 5xxxxxxxx: 31.191 van 62.823) | Dit is het gevolg van besluit 1 (`scope: oai`), zie besluit 10 voor de artikelen. Gemeten op 20 november in het Adlib-API: de 2xxxxxxxx-reeks heeft 120.455 records, de selectie `article` (pointer 1970) 26.265; 118.447 − 26.265 = 92.182, dus precies het gat in het rapport. In de 5xxxxxxxx-reeks vallen 31.243 records buiten pointer 1964 (het rapport: 31.191 ontbrekend), dezelfde rapporten zonder exemplaar als in besluit 1. Het rapport telt 26.923 records in de articlegraph; dat zijn 26.265 artikelen plus 658 tijdschriften (`schema:Periodical`). | RCE besluit over de scope |
| **Monument zonder link naar de CHO-URI** (alleen een `rijksmonumentnummer`; het oude model had `ceo:rijksmonumentnummer` op het record) | Adlib heeft alleen het nummer, geen CHO-id. Koppelen kan door per nummer de CHO-URI op te zoeken in de CHO-dataset en als `schema:sameAs` op de monument-node te zetten. Of ook `ceo:rijksmonumentnummer` op het record komt, is een keuze. | wij, na akkoord RCE |
| **9.825 eigen termen zonder thesaurus** | Zelfde punt als "Trefwoorden als thesaurus-URI's" hieronder: `Keyword` is tekst. Voorstel: label-match met de CHT en alleen bij een eenduidige treffer `skos:exactMatch`. | wij |
| **Geen `schema:sameAs` naar de AKB** | Het AKB-nummer is het catalogusnummer, maar welke records archeologische rapporten zijn, staat niet vanzelf in ons record. Eerst bij de beheerder navragen welk veld of welke reeks dat bepaalt. | beheerder, dan wij |
| **Verschillende `sdDatePublished` (oktober 2024 tot juli 2026)** | Bedoeld: de datum waarop het metadatarecord voor het laatst is gewijzigd. Het NDE-applicatieprofiel (versie 1.11.0, 13 november 2026) stelt `sdDatePublished` verplicht, precies één per record, en definieert het zo. Het is geen oogstdatum. Eén datum per levering past daar niet op; als dat gewenst is, hoort die op de dataset (bijvoorbeeld `schema:dateModified`), niet op de records. | RCE |
| **Twee modellen in één dataset** | Is open besluit 5. Het nieuwe model heeft pas de volledige catalogus als besluit 1 is genomen; tot dan blijft het oude model staan. | RCE |
| **863 verkeerde links in het oude model** (backslashes) | Niet van deze pijplijn: `Digital_reference` publiceren wij niet. | beheerder oude conversie |

### Wat nodig is om het oude model (`graph/bib`) te kunnen verwijderen

Doel: één geldend model met de hele catalogus. Dat kan pas als het volgende klopt; de onderste drie punten hangen aan de demo
(Elastic-service en monumentkoppeling).

1. De volledige run met `scope: api` is gedraaid en de aantallen zijn gecontroleerd: het nieuwe model heeft minstens elk catalogusnummer dat het oude had (vergelijking per priref, niet alleen per aantal).
2. Het monument is aan de CHO-URI te koppelen, of staat minstens als `ceo:rijksmonumentnummer` op het record (zie de tabel hierboven).
3. De eigen termen verwijzen waar mogelijk naar de CHT (`skos:exactMatch`).
4. De archeologische rapporten verwijzen met `schema:sameAs` naar de AKB.
5. Wat het oude model had en het nieuwe niet: de plaats bij een uitgever (`schema:location`, zie hieronder).
6. RCE besluit over het archiveren of verwijderen van de oude graphs (open besluit 5).

## Mogelijke vervolgstappen

- **Selectie via het API in plaats van de OAI.** Het API begrijpt de pointerfiles van de OAI-sets: `pointer 1964` (182.397 records) en
  `pointer 1970` (26.265) geven id voor id dezelfde records als de OAI-sets `books` en `article` (gemeten 17 november). Het ophalen kost
  dan ongeveer 4 minuten in plaats van ongeveer een uur, en de OAI en de tijdvakken zijn niet meer nodig. Nadeel: de tweede bron
  (`completeListSize`) als kruiscontrole vervalt, en we leunen op de pointerfiles 1964 en 1970. De zoekopdracht uit de toelichting van
  de beheerder (`copy.number=*`, `source.Repository=*`) geeft niet dezelfde aantallen; alleen `pointer N` klopt. Nog niet gedaan.
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
| **`schema:author` én `schema:creator`** | `author` is specifieker; de shapes toetsen op `creator`. Een extra triple per auteur. |
| **Type `Book`/`Article` plus `CreativeWork`** | het NDE-applicatieprofiel gaat uit van `CreativeWork`. |
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
