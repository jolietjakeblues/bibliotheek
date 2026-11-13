# Meewerken aan de code

Deze pagina is voor wie de code wijzigt. Voor het draaien en beheren van de pijplijn: [docs/beheer.md](docs/beheer.md).

## Omgeving

Python 3.12 of nieuwer.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python -m pytest
```

De tests gebruiken geen netwerk: de bronnen worden nagebootst, en de inhoud komt uit echte records in `tests/fixtures/`.

## Wat is waar

| Map | Inhoud |
|---|---|
| `src/` | de pijplijn; zie [docs/architectuur.md](docs/architectuur.md) voor wie wat doet |
| `shacl/` | de shapes |
| `config/` | de instellingen; zie [docs/configuratie.md](docs/configuratie.md) |
| `tests/` | `test_transform_*` (mapping), `test_*_client` (OAI en API), `test_harvest_completeness` (volledigheid en foutgevallen), `test_shacl` (shapes, ook negatief), `test_docs` (documentatie klopt met de code) |
| `tools/` | `maak_voorbeelden.py` genereert `docs/voorbeelden/` |
| `docs/` | documentatie |

## Een wijziging in de mapping

1. Pas `src/transform_service.py` aan.
2. Is een geval nieuw, voeg dan een **echt record** toe aan `tests/fixtures/` (een API-record in `api_books.xml` of `api_articles.xml`,
   een OAI-record in `article_page.xml`) en schrijf er een test voor in `tests/test_transform_*.py`. Liever een echt record dan een
   verzonnen: de bronnen hebben veel eigenaardigheden.
3. Pas zo nodig `shacl/bibliotheek.shacl.ttl` aan, met een negatieve test in `tests/test_shacl.py` (kapotte data moet worden afgekeurd).
4. Vernieuw de voorbeelden: `python tools/maak_voorbeelden.py`. `tests/test_docs.py` faalt zolang `docs/voorbeelden/` niet klopt met de code.
5. Werk [docs/mapping.md](docs/mapping.md) bij, en [docs/configuratie.md](docs/configuratie.md) als je een instelling toevoegt (ook dat
   wordt getest).
6. Draai `python -m pytest`.

## Conventies

- **Taal:** documentatie, commentaar, logmeldingen en SHACL-berichten zijn in het Nederlands; namen in de code zijn Engels of
  Nederlands, zoals de bestaande code.
- **SHACL-berichten** volgen het CN-profiel: `<Klasse>: <eigenschap> ontbreekt.`, `... moet een URI zijn.`, `... moet tekst met taalcode zijn`.
- **Violation of Warning:** een Violation betekent dat de data fout of onbruikbaar is en de publicatie stopt; een Warning is een bekend
  hiaat in de bron. Maak geen Violation van iets wat in de catalogus gewoon voorkomt.
- **Faal liever dan stilzwijgend onvolledig:** een nieuwe teller hoort tegen de bron gecontroleerd te worden.
- **Niets verzinnen:** ontbreekt een gegeven in de bron, laat het dan weg.
- **Gedeelde nodes** (een auteur, een uitgever) mogen per taal maar één naam hebben. Zet geen eigenschap met een wisselende waarde op een
  gedeelde node (zie het monument in [docs/mapping.md](docs/mapping.md)).

## Wat nooit in de repository hoort

- Tokens, wachtwoorden of andere geheimen. `LDV_API_TOKEN` staat als GitHub-secret.
- De uitvoer van een run (`data/` staat in `.gitignore`).
- Velden die bewust niet worden gepubliceerd (zie "Wat bewust niet wordt gepubliceerd" in [docs/mapping.md](docs/mapping.md)).
- Echte records in `tests/fixtures/` mogen alleen uit de openbare catalogus komen.

## Licentie

De code valt onder de [GPL-3.0](LICENSE). Met een bijdrage ga je ermee akkoord dat die onder dezelfde licentie valt. Gebruik alleen
afhankelijkheden met een licentie die daarmee samengaat.

## Een wijziging voorstellen

Maak een branch, houd een wijziging klein en gericht, en beschrijf in de commitboodschap wat er verandert en waarom. Draai de tests
voor je pusht. Na een wijziging aan de oogst of de mapping hoort een testrun in GitHub Actions (`testmode` aan, zie
[docs/beheer.md](docs/beheer.md)).
