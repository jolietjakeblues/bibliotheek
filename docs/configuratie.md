# Configuratie

Alle instellingen staan in `config/config.yml`. Dit document beschrijft elke sleutel. Een test (`tests/test_docs.py`) controleert dat
elke sleutel in het bestand hier voorkomt.

## Linked Data

| Sleutel | Waarde nu | Betekenis |
|---|---|---|
| `BASE_URI` | `https://linkeddata.cultureelerfgoed.nl/` | begin van alle adressen |
| `COLLECTION_ID` | `rce/bibliotheek` | pad van de collectie; adressen zijn `{BASE_URI}{COLLECTION_ID}/id/{klasse}/{uuid}` |
| `DATASET_URI` | `https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/` | de dataset-node; elk record verwijst ernaar met `schema:isPartOf` |
| `DATASET_NAME` | `Bibliotheek RCE` | naam van de dataset-node |
| `DATASET_DESCRIPTION` | tekst | beschrijving van de dataset-node |
| `LICENSE_URI` | leeg | IRI van de licentie van de metadata. Leeg betekent: geen `schema:license`. **Nog te besluiten** ([besluiten.md](besluiten.md)). |

## Adlib-API (volledige records)

| Sleutel | Waarde nu | Betekenis |
|---|---|---|
| `SRC_API` | `https://rce.adlibhosting.com/harvest/wwwopac.ashx` | adres van het API |
| `SRC_API_DATABASE` | `books` | databasenaam in de aanroep. Alle namen die werken (`books`, `article`, `document`) verwijzen naar dezelfde database. |
| `SRC_API_LIMIT` | `500` | records per pagina; een pagina duurt 5 tot 17 seconden |
| `SRC_API_WORKERS` | `3` | pagina's die tegelijk worden opgehaald. Een lagere waarde is vriendelijker voor de server, maar trager. |

## OAI-PMH

| Sleutel | Waarde nu | Betekenis |
|---|---|---|
| `SRC_URI` | `https://rce.adlibhosting.com/oaiapi/oai.ashx` | adres van de OAI |
| `SRC_SLEEP` | `0.05` | pauze in seconden tussen OAI-pagina's (10 records per pagina) |
| `SRC_OAI_WORKERS` | `3` | tijdvakken die tegelijk uit de OAI worden opgehaald (zie [architectuur.md](architectuur.md)). `1` haalt één lijst achter elkaar op. Een beperkte run (`--max-records`) doet dat altijd. |
| `SRC_OAI_WINDOW` | `10000` | grootste aantal records per tijdvak. Kleinere tijdvakken verdelen het werk gelijkmatiger, maar kosten meer tellingen vooraf. |
| `SRC_RETRIES` | `5` | pogingen per verzoek, voor OAI en API; ook het aantal pogingen bij een tijdelijke serverfout van het API |
| `SRC_BACKOFF` | `2.0` | basiswachttijd in seconden tussen pogingen (wordt per poging vermenigvuldigd) |

## Bronnen (`SOURCES`)

Elke bron heeft een naam (`books`, `article`) die ook in de bestandsnamen, het manifest en de naam van de graph terugkomt.

| Sleutel per bron | `books` | `article` | Betekenis |
|---|---|---|---|
| `kind` | `book` | `article` | welke transformatie wordt gebruikt (`book` of `article`) |
| `api_search` | `priref<200000000 or priref>=300000000` | `priref>=200000000 and priref<300000000` | zoekopdracht in het Adlib-API; alle treffers worden opgehaald |
| `scope` | `oai` | `oai` | `oai`: alleen records die de OAI-set bevat. `api`: alles wat `api_search` oplevert (alleen voor boeken; artikelen hebben de OAI altijd nodig). |
| `exclude_priref` | `[[200000000, 299999999]]` | niet ingesteld | priref-bereiken `[van, tot]` in de OAI-selectie die bij een andere bron horen. De OAI-set `books` bevat ook alle tijdschriftartikelen; die worden hier overgeslagen (met reden in `skipped_reasons`) en lopen via de bron `article`. |
| `oai` | set `books`, prefix `oai_dc_book` | set `article`, prefix `oai_dc` | set en `metadataPrefix` van de OAI |
| `catalog_url` | `https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/{priref}` | idem | sjabloon voor `schema:url` |

`api_search` is afgestemd op de priref-bereiken van de database: de artikelen liggen in 200.000.000 tot 300.000.000, de boeken eromheen.
Valt een record dat de OAI publiceert buiten die zoekopdracht, dan telt het als "niet in API" en faalt de run, tenzij het in
`exclude_priref` staat. De zoekopdracht is dus veilig aan te passen.

## Kwaliteitsbewaking

| Sleutel | Waarde nu | Betekenis |
|---|---|---|
| `MAX_RECORD_ERRORS` | `0` | aantal records dat bij de transformatie mag falen voordat de run mislukt |
| `MAX_MISSING_IN_API` | `0` | aantal records dat de OAI publiceert maar het API niet kent, voordat de run mislukt |
| `MAX_UNREADABLE_IN_API` | `10` | aantal te publiceren records dat het API zelf niet kan uitleveren omdat het record in de bron fout staat (zie [beheer.md](beheer.md)); zulke records worden overgeslagen en met priref in het manifest genoemd. `0` laat de run bij het eerste kapotte record falen. |

## Organisatie

Komt terug in de dataset-node en bij elk record (`schema:sdPublisher`).

| Sleutel | Waarde nu |
|---|---|
| `ORG_URI` | `https://www.cultureelerfgoed.nl/` |
| `ORG_NAME` | `Rijksdienst voor het Cultureel Erfgoed` |
| `ORG_SAME_AS` | `https://standaarden.overheid.nl/owms/terms/Rijksdienst_voor_het_Cultureel_Erfgoed` |
| `ORG_CONTACT_NAME` | `Infodesk van de RCE` |
| `ORG_CONTACT_EMAIL` | `thesauri@cultureelerfgoed.nl` |
| `ORG_ISIL` | `NL-AmfRCE` (de ISIL van de RCE; een eigen ISIL voor de bibliotheek is niet nagevraagd) |
| `ORG_ALTNAME` | `Cultural Heritage Agency of the Netherlands` |

## Omgevingsvariabelen

| Variabele | Standaard | Betekenis |
|---|---|---|
| `CONFIG_PATH` | `config/config.yml` | ander configuratiebestand |
| `CACHE_PATH` | `data/` | map voor de JSON-LD-bestanden en het manifest |

## GitHub Action

Instellingen van de workflow zelf (`.github/workflows/harvest_bibliotheek.yml`) staan in [beheer.md](beheer.md).
