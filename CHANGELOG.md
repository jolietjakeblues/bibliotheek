# Changelog

Alle noemenswaardige wijzigingen. Nieuwste bovenaan. Nog geen versienummers: er is nog geen gepubliceerde release.

## 2026-11-20

### Gewijzigd
- **`scope: api` voor boeken en artikelen** (was `oai`): alles wat het Adlib-API oplevert wordt gepubliceerd, niet alleen de OAI-sets. Reden:
  de OAI-sets laten ongeveer 156.000 records weg (94.190 artikelen zonder `source.Repository`, ongeveer 61.500 boekrecords zonder exemplaar)
  en het doel is een zo compleet mogelijke dataset, zodat het oude model kan vervallen. Nog niet gedraaid; zie `docs/besluiten.md`.
- De volledigheidscontrole eist bij `scope: api` ook voor artikelen geen OAI-teller meer.
- De volledigheidscontrole van het API accepteert een catalogus die tijdens de oogst groeit. De eerste volledige run met `scope: api` mislukte
  na 13 minuten op "bron kondigt 120456 records aan, 120457 opgehaald": er was in die tijd een artikel bijgekomen. Het aantal treffers
  wordt nu ook aan het eind opgehaald (`api_hits_end` in het manifest) en telt mee als de bron gegroeid is. Kromp hij, dan blijft de run falen.
- GitHub Action: `fail-fast: false` bij de oogst. Een mislukte bron annuleert de andere niet meer; publiceren blijft geblokkeerd zolang een bron mislukt.
- Verwijzingen naar het "CN-profiel" vervangen door het NDE-applicatieprofiel.

## 2026-11-13

### Toegevoegd
- Eerste versie van de pijplijn: oogst, schema.org-mapping, SHACL-validatie en een GitHub Action (planning: elke maandag 03:00 UTC)
  die per bron naar een vaste graph in `rce/bibliotheek` publiceert.
- **Boeken** uit het Adlib-API (reeks en deelnummer, uitgever en plaats apart, CHT-IRI's, ISBN, monumentnummers), met de OAI-set `books`
  als selectie van wat openbaar is.
- **Artikelen**: titel en onderwerpen uit het API, samengevoegd met tijdschrift, jaargang, aflevering, jaar en pagina's uit de OAI.
- Kwaliteitspoorten: volledigheid tegen `completeListSize` en `diagnostic/hits`, detectie van dubbele API-records, boekhouding van elk
  record, grenzen voor transformatiefouten en voor records die in de OAI maar niet in het API staan.
- SHACL-shapes op basis van het NDE-applicatieprofiel, met negatieve tests.
- Licentie van de code: GPL-3.0 (`LICENSE`), dezelfde als de kunst-ETL.
- Documentatie in `docs/` en `README.md`; echte voorbeelden in `docs/voorbeelden/` (gegenereerd en door een test bewaakt);
  voorbeeld-SPARQL-query's die op de testrecords worden uitgevoerd.

### Artikelen volledig uit het API (17 november)
- Artikelen komen nu volledig uit het API; de OAI is voor artikelen alleen nog de selectie (`ListIdentifiers`). Het samenvoegen met
  `ListRecords` en het ontleden van BibTeX-tekst vervalt. Een artikelrecord heeft een groep `Source` met `source.title.lref`, het priref
  van het tijdschriftrecord.
- Het tijdschrift heeft nu één adres per tijdschrift (zijn priref) en een `schema:url` naar zijn catalogusrecord; eerder was het adres
  de naam. Een artikel heeft nu ook een aflevering waar de OAI alleen een jaargang gaf (bijvoorbeeld 200000001).
- **Aliassen:** de eerste versie gebruikte de alias `article`, omdat die bij één record 55 velden geeft. In een oogst (veel treffers)
  geeft het API de `brieffields`: de alias `article` leverde dan geen `lead_word`, geen CHT-koppelingen en geen `source.title.lref`. Een
  droge run op het echte API liet dat zien (0 tijdschriften met adres); de testrecords kwamen uit een opvraag van één record. Nu: alias
  `archrep` (alle velden in een oogst) met `api_fields` (alleen wat we publiceren). Gecontroleerd: dezelfde graph als de volledige
  weergave van het losse record (80 van 80).
- Interne velden (`Edit` met gebruikersnamen, `record_access.owner`, `shelf_mark`) worden niet opgevraagd en niet gepubliceerd.
- Nieuwe bewaking: `MAX_UNLINKED_JOURNAL_PERCENT` (2) laat de run falen als artikelen het tijdschriftadres missen.
- Een artikel dat het API niet levert, wordt niet meer uit de OAI alleen geschreven (zoals bij boeken).
- Testrecords van artikelen zijn opgehaald zoals de oogst het doet (alias en velden uit de config).
- Gecorrigeerd: de docs beweerden dat alle API-aliassen dezelfde velden geven, en dat de OAI het tijdschrift nodig had.

### Antwoorden van de beheerder (17 november)
- De OAI-sets zijn een zoekopdracht op een pointerfile: `books` = records met een exemplaarnummer, `article` = `bron.Repository` gevuld. Het
  API geeft alle records terug. De 710 artikelen alleen in de boekenset hebben een tijdschrift maar geen `bron.Repository`.
- De reeks staat weer in `oai_dc_book` (gecontroleerd).
- Gevonden bij het nalopen van de API-configuratie: een artikelrecord heeft een groep `Source` met `source.title.lref`, het priref van
  het tijdschriftrecord. Verwerkt in de pijplijn, zie hierboven.

### Eerste volledige run (mislukt) en wat eruit volgde
- De publicatie naar Triply slaagde; alleen de laatste stap, `sync`, faalde met `Service not found`. De dataset gebruikt Speedy en
  heeft geen service met een eigen naam (de stap was overgenomen uit kunstcollecties-etl). De stap kijkt nu eerst of de dataset een
  service heeft en slaat de sync over als dat niet zo is (zoals in de beeldbank-ETL). Komt er later een service bij, dan wordt die
  vanzelf gesynchroniseerd.
- De run viel na 3u26m om op één record in het API (priref 450004680, tekst `76, 85` in een getalveld). Het API weigert dan de hele
  pagina. Nu wordt zo'n pagina gesplitst tot het ene record overblijft; dat wordt overgeslagen en met priref in het manifest
  genoemd (`MAX_UNREADABLE_IN_API`, nu 10). Een droge run op het hele API liet zien dat er voor de boeken en artikelen verder geen
  kapotte records en geen transformatiefouten zijn.
- De tweede volledige run viel om op 26.975 records "in de OAI maar niet in het API": de OAI-set `books` bevat ook alle
  tijdschriftartikelen (priref 2e8-3e8). De boekenbron slaat dat bereik nu over (`exclude_priref`) met reden in het manifest. Van
  die artikelen staan er 710 niet in de OAI-set `article`; zie [docs/besluiten.md](docs/besluiten.md).
- De derde run slaagde in de oogst; SHACL vond één Violation: een boek met pagination `0 p.` kreeg `numberOfPages 0`. Een aantal
  pagina's wordt nu alleen gezet bij 1 of meer; de tekst blijft in `schema:size`. Alle andere 217.000 boeken en alle artikelen
  hadden geen Violations.
- De boekenselectie uit de OAI duurde 3u12m. De OAI-lijst wordt nu in tijdvakken (`from`/`until`) parallel opgehaald
  (`SRC_OAI_WORKERS`, `SRC_OAI_WINDOW`), met controle op elk tijdvak en op het totaal. Gemeten op de echte server: 182.397 records, precies het aangekondigde aantal, in
  66 minuten in plaats van 3u12m. Datestamps hebben fracties van een seconde:
  zonder overlap tussen tijdvakken gingen records verloren.

### Gevonden tijdens de bouw
- `startfrom` van het API telt vanaf 1; stappen van 0, 500, 1000 lieten pagina's één record overlappen en leverden een record dubbel.
- Het API stuurt gzip-gecomprimeerde antwoorden; zonder uitpakken gaf elke pagina een parsefout.
- Eén monumentnummer kwam met verschillende namen voor, waardoor de gedeelde node twee namen kreeg (SHACL-Violation op 3.000 echte boeken).
  De naam staat nu niet meer op de monument-node.
- Een tijdelijke serverfout van de Adlib-server (`An item with the same key has already been added.`) liet de eerste testrun in GitHub
  Actions falen. De client probeert zulke fouten nu opnieuw (getest met nagebootste antwoorden, nog niet bevestigd in GitHub Actions); een
  syntaxisfout in de zoekopdracht niet.

### Nog niet gedaan
- Een volledige run en de eerste publicatie naar Triply.
- Zie [docs/besluiten.md](docs/besluiten.md) voor open besluiten, onder meer de selectie van de OAI en de licentie van de metadata.
