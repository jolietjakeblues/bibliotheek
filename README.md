# Bibliotheek RCE ETL

Haalt de boeken en tijdschriftartikelen van de bibliotheek van de Rijksdienst voor het Cultureel Erfgoed op, zet ze om naar
schema.org (JSON-LD), toetst ze aan SHACL en publiceert ze met een GitHub Action en de TriplyDB-CLI in de Linked Data Voorziening.

- Dataset: <https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek>
- SPARQL: <https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/bibliotheek/sparql>
- Opzet gevolgd van [kunstcollecties-etl](https://github.com/cultureelerfgoed/kunstcollecties-etl); de OAI-logica is
  afgeleid van [oai_harvester](https://github.com/cultureelerfgoed/oai_harvester-voor-Collectie-Nederland), zonder het interactieve deel.

## Inhoud

| Map / bestand | Doel |
|---|---|
| `config/config.yml` | bronnen, zoekopdrachten, URI-basis, organisatie, kwaliteitsgrenzen |
| `src/adlib_client.py` | Adlib-API (`wwwopac.ashx`): volledige records, parallel gepagineerd |
| `src/oai_client.py` | OAI-PMH `ListRecords` en `ListIdentifiers` met retries, resumption tokens en `completeListSize` |
| `src/transform_service.py` | de mapping naar schema.org |
| `src/harvest_service.py` | oogst, scope, samenvoegen, chunks, volledigheidscontrole, `manifest-*.json` |
| `src/validate_service.py` | toetst JSON-LD aan de SHACL-shapes |
| `shacl/bibliotheek.shacl.ttl` | de shapes |
| `tests/` | pytest: mapping, clients, volledigheid, SHACL (inclusief negatieve tests); echte records in `tests/fixtures/` |
| `.github/workflows/harvest_bibliotheek.yml` | wekelijkse run: test → oogst → valideer → publiceer → sync |

## Bronnen

Twee kanalen van dezelfde Adlib-catalogus, met elk wat het ander mist.

| Kanaal | Adres | Levert |
|---|---|---|
| Adlib-API | `https://rce.adlibhosting.com/harvest/wwwopac.ashx` | volledige records: titel, auteurs, uitgever en plaats apart, reeks, ISBN, trefwoorden, CHT-URI's, monumentnummers |
| OAI-PMH | `https://rce.adlibhosting.com/oaiapi/oai.ashx` | welke records openbaar zijn (de sets) en, bij artikelen, tijdschrift, jaargang, jaar en pagina's |

| Bron | Records in de OAI | schema.org | Samenstelling |
|---|---|---|---|
| `books` | 182.398 (set `books`, `oai_dc_book`) | `schema:Book` | API-record; de OAI bepaalt welke records worden gepubliceerd |
| `article` | 26.265 (set `article`, `oai_dc`) | `schema:Article` | API-record (titel, onderwerpen) plus OAI-record (tijdschrift, jaar, pagina's), samengevoegd op priref |

Het API bevat meer records dan de OAI publiceert (337.345, waarvan 120.443 in het bereik van de artikelen). Met `scope: oai` in de
config wordt alleen gepubliceerd wat de OAI-set bevat. Met `scope: api` wordt alles gepubliceerd wat `api_search` oplevert;
wijzig dat alleen als de beheerder bevestigt dat de overige records openbaar mogen.

Over de OAI: de server noemt vijf formaten, maar elke set accepteert er één (`article` alleen `oai_dc`, zonder titel). `GetRecord`
werkt niet. Het API pagineert met `startfrom` **vanaf 1**; stappen van 0, 500, 1000 laten elke pagina één record overlappen.
De client gebruikt 1, 501, 1001 en telt dubbel geleverde records; die laten de run falen.

## Mapping

Alles wordt getypeerd als het specifieke type **en** `schema:CreativeWork`, omdat het CN-profiel op `CreativeWork` toetst.
Elk record krijgt `schema:isPartOf <dataset>`, `schema:sdPublisher <RCE>`, `schema:sdDatePublished` (laatste wijziging in de bron),
`schema:url` (catalogus-link) en `schema:identifier` (PropertyValue met het priref).

### Boeken (API)

| API-veld | schema.org | Opmerking |
|---|---|---|
| `Title/lead_word` + `title` | `schema:name` @nl | `De` + `provincie : ...` wordt `De provincie : ...`; `L'` + `Oeil` wordt `L'Oeil` |
| `Author/author.name` | `schema:author` + `schema:creator` | `Person` of `Organization` (afgeleid van de naam), gedeeld per naam |
| `Corporate_author` | idem | altijd `Organization` |
| `Publisher/publisher` | `schema:publisher` (Organization) | gedeeld per naam |
| `Publisher/place_of_publication_2` | `schema:locationCreated` (Place) | |
| `Publisher/year_of_publication` | `schema:datePublished` (`xsd:gYear`) | |
| `Series_title` | `schema:isPartOf` → `schema:CreativeWorkSeries`, deelnummer in `schema:position` | reeks gedeeld per naam; nummer alleen bij één reeks |
| `Isbn` | `schema:isbn` | genormaliseerd; een ongeldige ISBN wordt een PropertyValue |
| `pagination`, `illustrations`, `dimensions` | `schema:size` (tekst) en `schema:numberOfPages` | aantal pagina's alleen als het een los getal is |
| `edition` | `schema:bookEdition` | |
| `Keyword` | `schema:about` → `DefinedTerm` | trefwoorden als tekst |
| `Content_subject/RNA_URI` | `schema:about` → CHT-IRI | rechtstreeks de IRI; het label staat in de thesaurus-graph van dezelfde dataset |
| `Person_keyword` | `schema:about` → Person/Organization | |
| `geographical_keyword`, `monument.*` | `schema:spatialCoverage` → `Place` | |
| `Monumentnumber` | `schema:about` → `LandmarksOrHistoricalBuildings` met rijksmonumentnummer | zie "Monumenten" |
| `notes`, `abstract` | `schema:description`, `schema:abstract` @nl | |

Niet overgenomen, bewust: `comments` (interne notities over de collectie), `Digital_reference` (externe links, deels via een
instellingsproxy), `shelf_mark`, `conference`, `table_of_contents`, `accompanying_material`.

### Artikelen (API + OAI)

| Bron | schema.org |
|---|---|
| API `Title`, `Author`, `Corporate_author` | `schema:name`, `schema:author` + `schema:creator` |
| API onderwerpen, plaatsen, notities | zoals bij boeken |
| OAI `dc:source` `journal = {..} ; vol (jaar), aflevering, pagina's` | `schema:isPartOf` → `PublicationIssue` → `PublicationVolume` → `Periodical` (alleen de niveaus waarvoor gegevens zijn) |
| OAI pagina's | `schema:pageStart` / `schema:pageEnd`, anders `schema:pagination` |
| OAI `Source.materiaal` | `schema:additionalType` op de Periodical |
| OAI `year = {..}` | `schema:datePublished` (`xsd:gYear`) |

Tijdschrift, jaargang en pagina's staan alleen in de OAI; het API-record bevat er geen veld voor. Een tijdschrift is in de catalogus
een eigen record (bijvoorbeeld priref 400001781, "De Bewaarsman"), maar een artikelrecord verwijst er niet naar. De koppeling gaat dus
op de tijdschriftnaam in de OAI-tekst; de tijdschriftrecords zelf worden nog niet gepubliceerd.

### Monumenten
Het rijksmonumentnummer uit de catalogus is niet het getal in de URI van het monument (`.../cho-kennis/id/rijksmonument/33556` heeft
nummer `10081`). De monument-node heeft daarom een `schema:identifier` met `propertyID` `rijksmonumentnummer`; koppelen aan de
CHO-data gaat in SPARQL via `ceo:rijksmonumentnummer`. De naam staat niet op die node, omdat hetzelfde nummer in verschillende
records met een andere schrijfwijze voorkomt; de naam blijft als plaats bij het boek.

## URI's

`{BASE_URI}{COLLECTION_ID}/id/{klasse}/{uuid3}`, bijvoorbeeld
`https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/id/book/0b3a9512-4f41-3903-8705-2df4c7427ce3`. De UUID is afgeleid van het
priref (record) of van een naam (auteur, uitgever, tijdschrift, reeks, term, plaats), dus een tweede run levert dezelfde adressen op.

Auteurs en uitgevers delen één adres per naam, zodat "alle boeken van X" werkt, zoals in de oude graphs `bib-aut`, `bib-corpaut`
en `bib-publishers`. Een organisatie die zowel auteur als uitgever is (bijvoorbeeld het Frans Halsmuseum) heeft in beide rollen
dezelfde URI. Gelijke naam betekent gelijke persoon: de naam is de genormaliseerde ingang uit de catalogus, maar de feed bevat
geen authority-nummer, dus twee verschillende auteurs met precies dezelfde ingang worden samengevoegd.
Dit is bewust een ander pad dan de oude conversie (`/bib/id/<uuid>`), zodat er geen adressen botsen.

## Kwaliteitsbewaking

Een run faalt, en publiceert dan niets, als:

1. het aantal opgehaalde records niet gelijk is aan `completeListSize` (OAI) of `diagnostic/hits` (API);
2. het API een record dubbel levert (dan klopt de paginering niet);
3. weggeschreven + fouten + niet-gevonden niet gelijk is aan wat beoogd was;
4. meer dan `MAX_MISSING_IN_API` records in de OAI staan maar niet in het API (standaard 0);
5. meer dan `MAX_RECORD_ERRORS` records niet getransformeerd kunnen worden (standaard 0; een mislukt record laat geen halve triples achter);
6. een chunk een SHACL-**Violation** bevat.

SHACL-**Warnings** laten de run slagen maar staan in de log en de samenvatting. De shapes volgen de conventies van het
[CN-profiel](https://github.com/cultureelerfgoed/collectie-nederland-schema-profile) (berichten, Violation/Warning).
Ze zijn bewust strenger op de catalogus-link: alleen `https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/<nummer>`.

## Bekende hiaten

- **Selectie**: de OAI bepaalt wat openbaar is (zie "Bronnen"). Hoe de OAI die selectie maakt, is niet bekend; het API bevat
  veel meer records. Dit moet de beheerder bevestigen.
- **Tijdschriften** als eigen records zijn nog niet opgenomen (zie "Artikelen").
- **Reeksen** zijn tekst (naam en deelnummer) zonder verwijzing naar het record in de aparte database `series` (11.282 reeksen met priref); koppelen kan nu alleen op naam.
- **Auteurs**: persoon of organisatie wordt geraden op de naam; er zijn geen authority-URI's (NTA/VIAF) in de bron.
- **Trefwoorden** zijn tekst, geen thesaurus-URI's; alleen `Content_subject` verwijst naar de CHT.
- **`deletedRecord = No`**: de OAI meldt geen verwijderde records. Daarom oogsten we steeds alles en vervangt de graph de vorige.
- **Licentie** (`LICENSE_URI` in de config) is leeg tot er een besluit is.

## Lokaal draaien

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pytest                                        # tests
python src/harvest_service.py --source all --max-records 100   # snelle test, schrijft naar data/
python src/validate_service.py data/*.jsonld            # SHACL
```

Looptijd (geschat uit een steekproef van 15.000 boeken; een volledige run is nog niet gedraaid): de selectie van de boeken uit de
OAI is het zwaarste deel (18.000+ pagina's met 10 identifiers, ongeveer 0,3 s per pagina), daarna volgen ongeveer 217.000
API-records en de validatie (ongeveer 8 s per chunk van 5.000 records). Reken op een tot twee uur voor de boeken en een half uur voor de artikelen.

## GitHub Action

`.github/workflows/harvest_bibliotheek.yml` draait elke maandag om 03:00 UTC en is ook handmatig te starten
(`workflow_dispatch`, met een testmodus die niets publiceert).

- **Secret**: `LDV_API_TOKEN` (TriplyDB-token met schrijfrechten op `rce/bibliotheek`) onder *Settings → Secrets and variables → Actions*.
- **Jobs**: `test` → `harvest` (boeken en artikelen parallel, elk met SHACL) → `publish` → `sync`.
- **Publicatie**: per bron één vaste graph, `https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/graphs/books` en `.../articles`.
  Het eerste bestand gaat met `--mode overwrite` (vervangt de graph van de vorige run), de overige met `--mode merge`.
  Er is dus geen ophoping van graphs. Tijdens het publiceren is een graph kort onvolledig.
- **Let op**: GitHub schakelt geplande workflows uit na 60 dagen zonder activiteit in de repository, en voert ze alleen uit vanaf de standaardbranch.
- **Let op, oude conversie**: de dataset `rce/bibliotheek` bevat al een oudere conversie (graphs `…/graph/bib`, `bib-aut`,
  `bib-corpaut`, `bib-publishers`, `bib-series`, `bib-thesaurus`). Deze pijplijn raakt die graphs niet aan, dus de boeken staan
  tijdelijk dubbel in de dataset, onder andere URI's. Wat er mee moet gebeuren is aan de beheerder:
  - `bib-aut`, `bib-corpaut` en `bib-publishers` bevatten alleen `rdf:type` en `schema:name` (gemeten); de gedeelde URI per
    auteur of uitgever hebben de nieuwe records ook. Niet meegenomen: de plaats bij een uitgever (`schema:location` in de oude data).
  - Reeksen zitten nu wel in de nieuwe data (via het API), alleen niet gekoppeld aan de reeks-URI's in `bib-series`.
  - Oude en nieuwe boeken zijn te koppelen zonder aanpassing: het oude `schema:sameAs` en het nieuwe `schema:url` zijn dezelfde
    catalogus-link (`https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/<priref>`; gecontroleerd voor priref 3, 17 en 308).
