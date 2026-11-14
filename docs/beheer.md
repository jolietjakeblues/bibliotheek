# Beheer

Praktische handleiding voor wie de pijplijn draaiend houdt. Hoe het in elkaar zit staat in [architectuur.md](architectuur.md).

## 1. Eenmalige inrichting

1. **Repository:** de code staat in `jolietjakeblues/bibliotheek`. De workflow staat in `.github/workflows/harvest_bibliotheek.yml`
   en moet op de standaardbranch (`main`) staan, anders draait de planning niet.
2. **Secret `LDV_API_TOKEN`:** een TriplyDB-token met schrijfrechten op `rce/bibliotheek`. Toevoegen onder *Settings → Secrets and
   variables → Actions → New repository secret*. Het token wordt nergens afgedrukt en hoort nooit in een bestand of in de chat.
3. **Actions aan:** onder *Settings → Actions → General* moeten workflows zijn toegestaan.
4. **Eerste keer:** doe eerst een testrun en een volledige run zonder publiceren (zie 2) voordat de planning iets publiceert.

## 2. Een run starten

*Actions → RCE Bibliotheek ETL → Run workflow*. Drie invoervelden:

| Veld | Standaard | Betekenis |
|---|---|---|
| `chunks` | `7000` | aantal records per JSON-LD-bestand |
| `testmode` | uit | oogst alleen 100 records per bron, en publiceer **niet** |
| `publish` | aan | publiceer naar Triply (alleen als `testmode` uit staat) |

Aanbevolen volgorde voor een nieuwe of gewijzigde pijplijn:

| Stap | `testmode` | `publish` | Wat het bewijst | Duur (geschat) |
|---|---|---|---|---|
| 1. Testrun | aan | n.v.t. | de omgeving werkt, de tests slagen, de bronnen zijn bereikbaar | enkele minuten |
| 2. Volledige run zonder publicatie | uit | uit | alle controles op volledigheid slagen; de uitvoer staat 7 dagen als artifact | nog niet gemeten met tijdvakken |
| 3. Publiceren | uit | aan | de data staat in Triply | idem, plus import |

> Gemeten: de eerste volledige run haalde de boekenselectie uit de OAI achter elkaar op en deed er 3 uur 12 minuten over, daarna
> viel hij om op een kapot record (zie [architectuur.md](architectuur.md)). Lokaal kostten de API-records van de boeken (217.000)
> ongeveer 26 minuten en de artikelen (OAI plus API) ongeveer 23 minuten. Sindsdien wordt de OAI in tijdvakken opgehaald: de boekenselectie
> (182.397 records, 60 tijdvakken, 3 werkers) duurde 66 minuten. Noteer hier de duur van de eerstvolgende volledige run.

Een testrun slaat de volledigheidscontrole bewust over (er is immers maar een deel opgehaald). De echte controle zie je bij stap 2.

### Wat er gebeurt

| Job | Doet |
|---|---|
| `test` | draait alle tests (`pytest`) |
| `harvest` (twee keer: `books`, `article`) | oogst en transformeert, valideert met SHACL, zet de uitvoer als artifact klaar (`bibliotheek-books`, `bibliotheek-article`) |
| `publish` | haalt de TriplyDB-CLI op en importeert per bron in een vaste graph; draait alleen zonder `testmode` en met `publish` (of bij de planning) |
| `sync` | synchroniseert de SPARQL-service van de dataset |

Er draait nooit meer dan één run tegelijk (`concurrency`); een tweede run wacht.

## 3. De planning

De workflow draait elke **maandag 03:00 UTC** (04:00 of 05:00 Nederlandse tijd) en publiceert dan direct, zonder `testmode`.

**Planning tijdelijk uitzetten:** zet de regel onder `schedule:` in de workflow in commentaar, of schakel de workflow uit onder
*Actions → de workflow → ⋯ → Disable workflow*.

GitHub schakelt geplande workflows uit na 60 dagen zonder activiteit in de repository.

## 4. De uitkomst lezen

Elke `harvest`-job schrijft een samenvatting (*Summary* bovenaan de run) met het manifest van de bron:

```json
{
  "oai_seen": 182398, "oai_expected": 182398, "oai_windows": 40,
  "api_seen": 216901, "api_hits": 216902, "api_duplicates": 0, "api_unreadable": 1, "unreadable_in_scope": 1,
  "intended": 182398, "written": 182398, "files": 27,
  "errors": 0, "skipped": 0, "skipped_reasons": {},
  "out_of_scope": 34504, "missing_in_api": 0, "unreadable_ids": ["450004680"],
  "complete": true
}
```

(De cijfers zijn een illustratie van de vorm, geen meting.)

| Sleutel | Betekenis |
|---|---|
| `oai_seen` / `oai_expected` | records uit de OAI die we kregen / die de OAI aankondigde (`completeListSize`). Moeten gelijk zijn. |
| `oai_windows` | aantal tijdvakken waarin de OAI-lijst is opgehaald (leeg bij een beperkte run) |
| `api_seen` / `api_hits` | records uit het API die we kregen / die het API aankondigde. Samen met `api_unreadable` moeten ze gelijk zijn aan `api_hits`. |
| `api_unreadable`, `unreadable_in_scope`, `unreadable_ids` | records die het API zelf niet kon uitleveren (kapot in de bron), hoeveel daarvan gepubliceerd hadden moeten worden, en welke. |
| `api_duplicates` | records die het API dubbel leverde. Moet `0` zijn. |
| `intended` | records die we wilden schrijven (de selectie) |
| `written` | records die in een bestand staan |
| `files` | aantal JSON-LD-bestanden |
| `errors`, `error_ids` | records die niet getransformeerd konden worden, en welke |
| `skipped`, `skipped_reasons` | records die de OAI als verwijderd of zonder metadata meldt |
| `out_of_scope` | API-records die niet in de OAI-selectie zitten (niet gepubliceerd, geen fout) |
| `missing_in_api`, `missing_ids` | records die de OAI publiceert maar het API niet leverde |
| `complete` | `true` alleen als alle controles slagen. Alleen dan mag er gepubliceerd worden. |

De SHACL-stap toont per chunk het aantal Violations en Warnings en onderaan een overzicht per melding. Violations laten de job falen.
Warnings (bijvoorbeeld "Book: schema:author ontbreekt") zijn bekende hiaten in de bron en geen reden tot ingrijpen.

## 5. Foutmeldingen en wat te doen

| Melding | Oorzaak | Wat te doen |
|---|---|---|
| `Serverfout van het API (poging 1/5): An item with the same key has already been added.` | tijdelijke interne fout van de Adlib-server | niets: het verzoek wordt opnieuw geprobeerd. Faalt de run toch, start hem dan opnieuw. |
| `AdlibError: Unexpected token ... (search='...')` | de zoekopdracht `api_search` klopt niet (syntaxis) | corrigeer `api_search` in `config.yml` |
| `OaiError: cannotDisseminateFormat` | combinatie van set en `metadataPrefix` wordt niet ondersteund | controleer `oai` bij de bron; per set werkt maar één formaat |
| `ONVOLLEDIG (OAI): bron kondigt N records aan, M opgehaald.` | OAI-pagina's gemist, of de bron veranderde tijdens de run | start opnieuw; blijft het gebeuren, onderzoek dan de bron |
| `ONVOLLEDIG (API): ... (K dubbel geleverd)` | paginering van het API klopt niet | zie `adlib_client.py` (`startfrom` telt vanaf 1); meld het als dit na een wijziging gebeurt |
| `Record N is dubbel geleverd door het API` | idem | idem |
| `Record N is onleesbaar in het API en wordt overgeslagen: Invalid integer value ...` | het record staat in de bron fout (bijvoorbeeld tekst in een getalveld) | niets aan de pijplijn; geef het priref door aan de beheerder van de catalogus. Het record wordt niet gepubliceerd. |
| `N te publiceren records waren in het API onleesbaar (toegestaan: 10): ...` | meer kapotte records dan `MAX_UNREADABLE_IN_API` | lees `unreadable_ids`, laat de records herstellen; verhoog de grens alleen bewust |
| `Tijdvak ...: N records opgehaald, M verwacht` of `De tijdvakken bevatten samen ...` | de OAI veranderde tijdens het plannen of de run (een record kreeg een nieuwe datestamp) | start de run opnieuw; blijft het gebeuren, zet `SRC_OAI_WORKERS` op 1 |
| `N records staan in de OAI maar niet in het API (toegestaan: 0): ...` | records buiten `api_search`, of echt niet in het API | zie `missing_ids` in het manifest en de uitleg hieronder |
| `N records konden niet getransformeerd worden` | een record geeft een fout in de mapping | zoek in de log naar `Fout bij transformatie van <id>`; bekijk dat record |
| `Rekenfout: weggeschreven (..) + fouten (..) + niet in API (..) != beoogd (..)` | een bug in de boekhouding | meld het; publiceer niet |
| `De OAI gaf geen completeListSize` | de OAI-server antwoordt anders dan verwacht | onderzoek de bron |
| SHACL `Violation: ...` | een record voldoet niet aan de shapes | de melding noemt de eigenschap en een voorbeeld-node; herstel de mapping of de shapes |
| Fout in `publish` (Triply) | token ongeldig of verlopen, of de dataset bestaat niet | de stap toont `.triplydb-js.err`; controleer `LDV_API_TOKEN` |
| Fout in `sync` | de service-naam of het token klopt niet | de stap toont het antwoord van de server |

### Records in de OAI maar niet in het API

Eerst `missing_ids` in het manifest bekijken, en dan:

- **Liggen ze buiten `api_search`?** (bijvoorbeeld een boek met priref in het artikelbereik) Pas dan `api_search` aan zodat ze erin vallen.
- **Bestaan ze echt niet in het API?** Vraag de beheerder van de catalogus waarom. Is het een klein aantal en acceptabel, verhoog dan
  `MAX_MISSING_IN_API`. Bij boeken worden zulke records dan **niet** gepubliceerd; bij artikelen wel (zonder titel).

## 6. Controleren na publicatie

Voer de controlequery's in [sparql.md](sparql.md) uit op `https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/bibliotheek/sparql`:

- aantallen per type: ongeveer het aantal in `written` van het manifest;
- een steekproef van een reeks, een auteur en een monument;
- de koppeling met de oude data via de catalogus-link.

Controleer na de tweede publicatie ook dat de aantallen **niet verdubbelen**: dat bewijst dat `--mode overwrite` de graph echt vervangt.
Dat is in deze opzet nog niet in Triply gezien.

## 7. Terugdraaien

In deze opzet wordt de graph van de vorige run vervangen en bewaart de pijplijn zelf geen eerdere versie. De artifacts van een
eerdere run (7 dagen bewaard, als ze niet verlopen zijn) bevatten de vorige uitvoer. Die is met dezelfde CLI-aanroepen als in de
workflow opnieuw te importeren. Is dat niet nodig of kan het niet meer, dan is de oplossing een nieuwe, goede run.

## 8. Een wijziging doorvoeren

1. Pas de code, de shapes of de config aan.
2. Draai `python -m pytest`. Verandert de mapping, dan falen de tests in `tests/test_docs.py` tot je de voorbeelden vernieuwt:
   `python tools/maak_voorbeelden.py`.
3. Werk de documentatie bij ([mapping.md](mapping.md), [configuratie.md](configuratie.md)).
4. Commit en push. Doe daarna eerst een testrun (stap 1 hierboven).

Zie ook [CONTRIBUTING.md](../CONTRIBUTING.md).

## 9. Een bron of veld toevoegen

- **Een veld uit een bestaande bron:** voeg de mapping toe in `transform_service.py`, een testrecord in `tests/fixtures/` en een
  test; pas zo nodig de shapes aan en werk [mapping.md](mapping.md) bij.
- **Een nieuwe bron** (bijvoorbeeld tijdschriften als eigen records): voeg een blok toe onder `SOURCES` in `config.yml` met een eigen
  `kind`, schrijf een transformatie, registreer die in `harvest_service.py` en voeg de bron toe aan de `matrix` in de workflow.

## 10. Het token vernieuwen

Maak in TriplyDB een nieuw token en vervang het secret `LDV_API_TOKEN` in GitHub. Er hoeft niets te worden aangepast in de code.

## 11. Kosten en limieten

- Is de repository openbaar, dan zijn GitHub Actions gratis; bij een privé-repository tellen de minuten mee in het abonnement.
- Een `harvest`-job heeft een time-out van 300 minuten; GitHub zelf staat maximaal 6 uur per job toe.
- Artifacts worden 7 dagen bewaard.
