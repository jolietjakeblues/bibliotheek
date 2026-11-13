# Mapping naar schema.org

Hoe een bibliotheekrecord in RDF wordt. De code staat in `src/transform_service.py` (`transform_book`, `transform_article`); de
shapes in `shacl/bibliotheek.shacl.ttl`. Echte uitvoer staat in [voorbeelden/](voorbeelden/):

| Voorbeeld | Laat zien |
|---|---|
| [boek-met-auteurs-en-uitgever.ttl](voorbeelden/boek-met-auteurs-en-uitgever.ttl) | persoon en organisatie als auteur, uitgever, plaats, ISBN, CHT-term |
| [boek-in-reeks.ttl](voorbeelden/boek-in-reeks.ttl) | reeks met deelnummer |
| [boek-over-monument.ttl](voorbeelden/boek-over-monument.ttl) | rijksmonumentnummer en plaatsen |
| [artikel.ttl](voorbeelden/artikel.ttl) | titel uit het API; tijdschrift, jaargang, aflevering en pagina's uit de OAI |

Deze bestanden worden gegenereerd met `python tools/maak_voorbeelden.py` en door een test bewaakt (`tests/test_docs.py`): verandert de
mapping, dan faalt die test tot de voorbeelden opnieuw zijn gemaakt.

## Voor elk record

| Eigenschap | Waarde |
|---|---|
| `rdf:type` | `schema:Book` of `schema:Article`, plus `schema:CreativeWork` (het CN-profiel toetst op `CreativeWork`) |
| `schema:isPartOf` | de dataset, `https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/` |
| `schema:sdPublisher` | de RCE |
| `schema:sdDatePublished` | datum van de laatste wijziging in de bron (`modification` in het API) |
| `schema:url` | de catalogus-link, `https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/<priref>` |
| `schema:identifier` | `PropertyValue` met `propertyID` `priref` |
| `schema:license` | alleen als `LICENSE_URI` is ingevuld (nu leeg) |

## Boeken (Adlib-API)

| API-veld | schema.org | Opmerking |
|---|---|---|
| `Title/lead_word` + `title` | `schema:name` @nl | `De` + `provincie : ...` wordt `De provincie : ...`; `L'` + `Oeil` wordt `L'Oeil` |
| `Author/author.name` | `schema:author` + `schema:creator` | `Person` of `Organization` (afgeleid van de naam), gedeeld per naam |
| `Corporate_author` | idem | altijd `Organization` |
| `Publisher/publisher` | `schema:publisher` (`Organization`) | gedeeld per naam |
| `Publisher/place_of_publication_2` | `schema:locationCreated` (`Place`) | |
| `Publisher/year_of_publication` | `schema:datePublished` (`xsd:gYear`) | het eerste jaartal in de waarde |
| `Series_title` | `schema:isPartOf` → `schema:CreativeWorkSeries`; deelnummer in `schema:position` | reeks gedeeld per naam; nummer alleen als het boek één reeks heeft |
| `Isbn` | `schema:isbn` | genormaliseerd (zonder streepjes); een ongeldige ISBN wordt een `PropertyValue` met `propertyID` `ISBN (ongeldig)` |
| `pagination`, `illustrations`, `dimensions` | `schema:size` (tekst, `;`-gescheiden) en `schema:numberOfPages` | aantal pagina's alleen als `pagination` een los getal is (`96 p`, `57 pagina's`) |
| `edition` | `schema:bookEdition` @nl | |
| `Keyword/keyword.contents` | `schema:about` → `DefinedTerm` | trefwoorden als tekst, gedeeld per tekst |
| `Content_subject/RNA_URI` | `schema:about` → CHT-IRI | rechtstreeks de IRI; het label staat in de CHT-graph van dezelfde dataset |
| `Person_keyword` | `schema:about` → `Person` of `Organization` | |
| `geographical_keyword`, `monument.*` | `schema:spatialCoverage` → `Place` | land, provincie, gemeente, plaats en monumentnaam |
| `Monumentnumber` | `schema:about` → `schema:LandmarksOrHistoricalBuildings` | zie "Monumenten" |
| `notes` | `schema:description` @nl | |
| `abstract` | `schema:abstract` @nl | |

## Artikelen (API + OAI)

| Bron | schema.org | Opmerking |
|---|---|---|
| API `Title` | `schema:name` @nl | zonder API-record ontbreekt de titel; er wordt niets verzonnen |
| API `Author`, `Corporate_author` | `schema:author` + `schema:creator` | zonder API-record: de auteurs uit de OAI (`author = {..},`) |
| API onderwerpen, plaatsen, notities | zoals bij boeken | notities uit API en OAI worden ontdubbeld |
| OAI `dc:source` | keten `schema:isPartOf`: `PublicationIssue` → `PublicationVolume` → `Periodical` | alleen de niveaus waarvoor gegevens zijn |
| OAI pagina's | `schema:pageStart` / `schema:pageEnd`, anders `schema:pagination` | `198-203` is een bereik, `8-9, 12` blijft tekst |
| OAI `Source.materiaal` | `schema:additionalType` (`DefinedTerm`) op de `Periodical` | `tijdschrift`, `jaarboek`, `jaarverslagen` |
| OAI `year = {..}` | `schema:datePublished` (`xsd:gYear`) | |

### Hoe de OAI-tekst van een artikel wordt gelezen

De OAI levert het tijdschrift als stukjes BibTeX-tekst in `dc:source`:

```
journal = {Stad en lande : historische bijdragen ... ; 27 (1990), 69, 198-203},
```

dat wordt: tijdschrift `Stad en lande : ...`, jaargang `27`, jaar `1990`, aflevering `69`, pagina's `198-203`. Bijzonderheden:

- een tijdschrifttitel met voorloop-lidwoord staat in twee stukken (`De` + `Bewaarsman`) en wordt samengevoegd;
- staat er maar één getal tussen komma's achter het jaar, dan is dat het paginanummer (een aflevering is dan niet te onderscheiden);
- begint dat deel met een bereik (`8-9, 12`), dan is het geheel een paginering en geen aflevering;
- wat niet te ontleden is, blijft leeg; het record blijft bestaan.

## Monumenten

Het rijksmonumentnummer uit de catalogus (bijvoorbeeld `10081`) is niet het getal in de URI van het monument in de CHO-data
(`.../cho-kennis/id/rijksmonument/33556` heeft nummer `10081`). De URI is dus niet af te leiden. Daarom krijgt een monument:

- een node met type `schema:LandmarksOrHistoricalBuildings`, gedeeld per nummer;
- een `schema:identifier` met `propertyID` `rijksmonumentnummer`.

Koppelen aan de CHO-data gaat in SPARQL via `ceo:rijksmonumentnummer`. **De naam staat niet op de monument-node**, omdat hetzelfde
nummer in verschillende records met een andere schrijfwijze voorkomt (`Slot Loevestein`, `Loevestein`) en een gedeelde node maar één
naam per taal mag hebben. De naam blijft als plaats bij het boek.

## Adressen

`{BASE_URI}{COLLECTION_ID}/id/{klasse}/{uuid3}`, bijvoorbeeld
`https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/id/book/0b3a9512-4f41-3903-8705-2df4c7427ce3`.

| Klasse (`{klasse}`) | Sleutel van de `uuid3` | Gedeeld? |
|---|---|---|
| `book`, `article` | priref | nee |
| `person` | naam | ja, over alle records |
| `organization` | naam | ja; één adres voor een organisatie als auteur én als uitgever |
| `series`, `periodical` | naam | ja |
| `term`, `place` | tekst | ja |
| `publicationvolume`, `publicationissue` | tijdschrift + jaargang/jaar (+ aflevering) | ja |
| `monument` | rijksmonumentnummer | ja |
| `propertyvalue` | priref (of nummer) + soort | nee |

Een persoon met dezelfde naam is dezelfde persoon: de naam is de genormaliseerde ingang uit de catalogus, maar de bron bevat geen
authority-nummer. Twee verschillende auteurs met precies dezelfde ingang worden dus samengevoegd.

Dit pad (`/rce/bibliotheek/id/...`) verschilt bewust van de oude conversie (`/bib/id/<uuid>`), zodat er geen adressen botsen.

## Wat bewust niet wordt gepubliceerd

| Veld | Reden |
|---|---|
| `comments` | interne notities over de collectie (bijvoorbeeld welke jaargangen aanwezig zijn) |
| `Digital_reference` | externe links, deels via een instellingsproxy (`go.openathens.net`) |
| `dcterms:isReferencedBy` (OAI) | interne documentlinks (`proza.ocw.local`) |
| `shelf_mark` | plaatsingsnummer in het magazijn |
| `conference`, `table_of_contents`, `accompanying_material` | nog niet gemapt |

## Auteur of organisatie?

De bron maakt geen onderscheid tussen persoon en organisatie bij auteurs en trefwoorden. `Corporate_author` is altijd een organisatie.
Voor de rest geldt een benadering op de naam (`is_organization` in `transform_service.py`):

1. begint de naam met een duidelijk organisatiewoord (Stichting, Ministerie, Gemeente, Museum, ...), dan is het een organisatie;
2. heeft de naam de vorm `Achternaam, Initialen` (een komma, dan een hoofdletter), dan is het een persoon, ook als de achternaam zelf
   een organisatiewoord is (`Bond, J.`);
3. bevat de naam anders een organisatiewoord of eindigt een samenstelling erop (`Frans Halsmuseum`), dan is het een organisatie;
4. anders is het een persoon.

Dit is een benadering; fouten komen voor. Een betere oplossing is een authority-nummer in de bron.
Uitgevers zijn altijd organisaties en delen het adres met een gelijknamige organisatie die auteur is.
