# Changelog

Alle noemenswaardige wijzigingen. Nieuwste bovenaan. Nog geen versienummers: er is nog geen gepubliceerde release.

## 2026-11-13

### Toegevoegd
- Eerste versie van de pijplijn: oogst, schema.org-mapping, SHACL-validatie en een GitHub Action (planning: elke maandag 03:00 UTC)
  die per bron naar een vaste graph in `rce/bibliotheek` publiceert.
- **Boeken** uit het Adlib-API (reeks en deelnummer, uitgever en plaats apart, CHT-IRI's, ISBN, monumentnummers), met de OAI-set `books`
  als selectie van wat openbaar is.
- **Artikelen**: titel en onderwerpen uit het API, samengevoegd met tijdschrift, jaargang, aflevering, jaar en pagina's uit de OAI.
- Kwaliteitspoorten: volledigheid tegen `completeListSize` en `diagnostic/hits`, detectie van dubbele API-records, boekhouding van elk
  record, grenzen voor transformatiefouten en voor records die in de OAI maar niet in het API staan.
- SHACL-shapes in de stijl van het CN-profiel, met negatieve tests.
- Licentie van de code: GPL-3.0 (`LICENSE`), dezelfde als de kunst-ETL.
- Documentatie in `docs/` en `README.md`; echte voorbeelden in `docs/voorbeelden/` (gegenereerd en door een test bewaakt);
  voorbeeld-SPARQL-query's die op de testrecords worden uitgevoerd.

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
