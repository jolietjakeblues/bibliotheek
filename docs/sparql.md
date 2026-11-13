# SPARQL-voorbeelden

Voorbeeldvragen op de data, voor het endpoint
`https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/bibliotheek/sparql`.

**Wat getest is:** de query's met de opmerking `# test: lokaal` staan in `tests/test_docs.py` en worden daar uitgevoerd op de
voorbeeldrecords in `tests/fixtures/` (ze moeten minstens één rij opleveren). Ze zijn **niet** uitgevoerd op de volledige dataset in
Triply, want die is nog niet gepubliceerd. De vermelde namen komen uit die voorbeeldrecords; vervang ze door wat je zoekt.
De query's met `# test: overslaan` raken andere graphs en zijn dus niet lokaal te toetsen.

Alle query's gebruiken:

```sparql
PREFIX schema: <https://schema.org/>
```

## Controle na publicatie

### Aantallen per type

Vergelijk met `written` in het manifest (boeken) en het aantal artikelen.

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?type (COUNT(DISTINCT ?s) AS ?aantal) WHERE {
  VALUES ?type { schema:Book schema:Article schema:Periodical schema:CreativeWorkSeries schema:Person schema:Organization }
  ?s a ?type .
} GROUP BY ?type ORDER BY DESC(?aantal)
```

### Records zonder titel, auteur of uitgever

Dit zijn de bekende hiaten (de SHACL-Warnings). Artikelen die de OAI wel kent maar het API niet, hebben geen titel.

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?type (COUNT(?w) AS ?zonderAuteur) WHERE {
  VALUES ?type { schema:Book schema:Article }
  ?w a ?type .
  FILTER NOT EXISTS { ?w schema:author ?a }
} GROUP BY ?type
```

## Boeken

### Alle boeken uit een reeks

De reden dat de API-route nodig was: de OAI levert geen reeksen.

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?deel ?titel ?boek WHERE {
  ?reeks a schema:CreativeWorkSeries ; schema:name "Advies Vromraad"@nl .
  ?boek schema:isPartOf ?reeks ; schema:name ?titel .
  OPTIONAL { ?boek schema:position ?deel }
} ORDER BY ?deel
```

### Reeksen met de meeste boeken

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?reeks (COUNT(?boek) AS ?boeken) WHERE {
  ?r a schema:CreativeWorkSeries ; schema:name ?reeks .
  ?boek schema:isPartOf ?r .
} GROUP BY ?reeks ORDER BY DESC(?boeken) LIMIT 20
```

### Alles van of uitgegeven door een organisatie

Een organisatie heeft één adres, ook als ze auteur én uitgever is.

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?rol ?titel WHERE {
  ?org a schema:Organization ; schema:name "Interprovinciaal Overleg"@nl .
  { ?werk schema:author ?org . BIND("auteur" AS ?rol) }
  UNION
  { ?werk schema:publisher ?org . BIND("uitgever" AS ?rol) }
  ?werk schema:name ?titel .
}
```

### Boeken en artikelen van een auteur

Een auteur is dezelfde node in alle records met dezelfde naam (`Achternaam, Initialen`).

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?type ?titel ?jaar WHERE {
  ?auteur a schema:Person ; schema:name "Berrevoets, W.D."@nl .
  ?werk schema:author ?auteur ; a ?type ; schema:name ?titel .
  FILTER(?type IN (schema:Book, schema:Article))
  OPTIONAL { ?werk schema:datePublished ?jaar }
}
```

### Auteurs met de meeste werken

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?auteur (COUNT(?werk) AS ?werken) WHERE {
  ?a a schema:Person ; schema:name ?auteur .
  ?werk schema:author ?a .
} GROUP BY ?auteur ORDER BY DESC(?werken) LIMIT 20
```

## Onderwerpen en plaatsen

### Boeken over een CHT-term, met het label

Het onderwerp is rechtstreeks de CHT-IRI. Het label staat in de CHT-graph van dezelfde dataset (bij een lokale test niet, daarom
`OPTIONAL`). Vervang de IRI door een term uit [CHT](https://data.cultureelerfgoed.nl/term/id/cht/).

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?titel ?label WHERE {
  VALUES ?term { <https://data.cultureelerfgoed.nl/term/id/cht/1130e375-3469-4e63-a8d4-5fcb339f7536> }
  ?boek schema:about ?term ; schema:name ?titel .
  OPTIONAL { ?term skos:prefLabel ?label }
}
```

### Werken over een plaats

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?type ?titel WHERE {
  ?plaats a schema:Place ; schema:name "Schouwen-Duiveland"@nl .
  ?werk schema:spatialCoverage ?plaats ; a ?type ; schema:name ?titel .
  FILTER(?type IN (schema:Book, schema:Article))
}
```

### Boeken over een rijksmonument

Het rijksmonumentnummer is niet het getal in de URI van het monument in de CHO-data. Koppel daarom op het nummer. Zoek eerst in de
CHO-dataset (`rce/cho`) het monument met `ceo:rijksmonumentnummer "10081"` en gebruik hier hetzelfde nummer:

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?titel WHERE {
  ?monument a schema:LandmarksOrHistoricalBuildings ;
            schema:identifier ?id .
  ?id schema:propertyID "rijksmonumentnummer" ; schema:value ?nummer .
  FILTER(STR(?nummer) = "10081")
  ?boek schema:about ?monument ; schema:name ?titel .
}
```

## Artikelen en tijdschriften

### Artikelen per tijdschrift

Het tijdschrift hangt via jaargang en aflevering aan het artikel (`schema:isPartOf` herhaald, vandaar het `+`).

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
SELECT ?tijdschrift (COUNT(DISTINCT ?artikel) AS ?artikelen) WHERE {
  ?artikel a schema:Article ; schema:isPartOf+ ?p .
  ?p a schema:Periodical ; schema:name ?tijdschrift .
} GROUP BY ?tijdschrift ORDER BY DESC(?artikelen)
```

### De artikelen van een tijdschrift, met jaargang, aflevering en pagina's

```sparql
# test: lokaal
PREFIX schema: <https://schema.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?titel ?jaargang ?aflevering ?van ?tot WHERE {
  ?p a schema:Periodical ; schema:name ?naam .
  FILTER(STRSTARTS(STR(?naam), "Stad en lande"))
  ?artikel a schema:Article ; schema:isPartOf+ ?p ; schema:name ?titel .
  OPTIONAL { ?artikel schema:pageStart ?van ; schema:pageEnd ?tot }
  OPTIONAL { ?artikel schema:isPartOf/schema:issueNumber ?aflevering }
  OPTIONAL { ?artikel schema:isPartOf*/schema:volumeNumber ?jaargang }
} ORDER BY ?jaargang ?aflevering xsd:integer(?van)
```

## Koppeling met de oude conversie

De oude graphs in dezelfde dataset hebben als `schema:sameAs` de catalogus-link; de nieuwe records hebben dezelfde link in
`schema:url`. Zo zijn oud en nieuw te koppelen, bijvoorbeeld om de reeksen uit de oude graph `bib-series` erbij te halen.

```sparql
# test: overslaan (raakt de oude graph; de nieuwe data staat nog niet in Triply)
PREFIX schema: <https://schema.org/>
SELECT ?nieuw ?oud WHERE {
  GRAPH <https://linkeddata.cultureelerfgoed.nl/graph/bib> { ?oud schema:sameAs ?url }
  GRAPH <https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/graphs/books> { ?nieuw schema:url ?url }
} LIMIT 10
```
