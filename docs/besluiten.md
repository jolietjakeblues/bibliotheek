# Besluiten en open punten

Twee lijsten: wat nog besloten of uitgezocht moet worden, en welke keuzes zijn gemaakt en waarom.

## Open besluiten en vragen

| # | Onderwerp | Wat is er aan de hand | Bij wie | Gevolg tot dan |
|---|---|---|---|---|
| 1 | **Selectie van de OAI** | Het API bevat 337.345 records; de OAI publiceert 182.398 boeken en 26.265 artikelen. Het criterium van de OAI is niet bekend. Mogen alle records openbaar? | beheerder van de OAI/Adlib (`adminEmail` in `Identify`) | `scope: oai`: alleen wat de OAI al publiceert |
| 2 | **Reeksen in de OAI** | `oai_dc_book` bevat geen reeks; het API wel. | beheerder | reeksen komen uit het API; de OAI is alleen de selectie |
| 3 | **Tijdschrift bij een artikel in het API** | Het API-record van een artikel heeft geen tijdschrift, jaargang of pagina's; de OAI wel. Op welk veld hangt een artikel aan zijn tijdschrift? | beheerder | die gegevens komen uit de OAI |
| 4 | **Licentie van de metadata** | `LICENSE_URI` is leeg: records hebben geen `schema:license`. | RCE | geen licentie in de data |
| 5 | **Oude graphs in `rce/bibliotheek`** | `bib`, `bib-aut`, `bib-corpaut`, `bib-publishers`, `bib-series`, `bib-thesaurus` bevatten een oudere conversie. De boeken staan daardoor tijdelijk dubbel. | RCE | oude graphs blijven ongemoeid |
| 6 | **NDE Datasetregister** | De dataset moet nog met een beschrijving worden aangemeld, zoals bij de andere RCE-datasets. Los van deze pijplijn. | RCE | n.v.t. |
| 7 | **Testdataset vóór livegang** | De Triply-dataset staat vast in de workflow (`rce/bibliotheek`). Een eerste run naar een aparte testdataset zou veiliger zijn. | beheerder van de pijplijn | eerst `publish` uit |
| 8 | **Eerste volledige run** | Nog niet gedraaid. Looptijd, `missing_in_api` en het gedrag van `--mode overwrite` bij een tweede run zijn nog niet gezien. | beheerder van de pijplijn | zie [beheer.md](beheer.md) |

## Mogelijke vervolgstappen

- **Tijdschriften als eigen nodes.** In de catalogus zijn tijdschriften eigen records (bijvoorbeeld priref 400001781). Een artikel verwijst
  er niet naar; de koppeling kan alleen op naam, die in de OAI-tekst staat.
- **Reeksen koppelen aan de aparte database `series`** (11.282 reeksen met priref). Nu zijn het teksten met naam en deelnummer.
- **Authority-nummers voor auteurs** (NTA, VIAF), zodat gelijke namen niet langer worden samengevoegd.
- **Trefwoorden als thesaurus-URI's.** Alleen `Content_subject` verwijst nu naar de CHT; `Keyword` is tekst.
- **Plaats bij een uitgever.** De oude data had `schema:location` bij uitgevers; hier staat de plaats bij het boek.

## Genomen besluiten

| Besluit | Waarom |
|---|---|
| **Code onder GPL-3.0** | dezelfde licentie als de kunst-ETL ([LICENSE](../LICENSE)). Geldt voor de code; de licentie van de metadata staat apart open (zie boven). |
| **De OAI bepaalt de selectie, het API levert de inhoud** | de OAI is het kanaal dat de beheerder bewust openbaar maakt; het API bevat meer. Het API heeft de rijkere gegevens (reeks, plaats en uitgever apart, CHT). |
| **Artikelen: API plus OAI, samengevoegd op priref** | geen van beide bronnen heeft alles: het API mist het tijdschrift, de OAI mist de titel. |
| **Een artikel zonder API-record krijgt geen titel** | niets verzinnen. |
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
| **Een record dat het API niet kan leveren wordt overgeslagen, tot 10 stuks** | één kapot bronrecord (priref 450004680) liet de eerste volledige run na 3 uur omvallen. Elk overgeslagen record staat met priref in het manifest; `MAX_UNREADABLE_IN_API` is `0` te zetten voor een strenge run. |
| **OAI-selectie in tijdvakken parallel** | de selectie duurde achter elkaar 3u12m. Tijdvakken overlappen op de grens (anders gaan records met fracties van een seconde verloren) en elk tijdvak en het totaal worden gecontroleerd. |
| **Tijdelijke serverfouten opnieuw proberen, syntaxisfouten niet** | de Adlib-server gaf in een GitHub Action eenmalig een interne fout. |
