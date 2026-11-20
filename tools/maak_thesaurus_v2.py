"""Maakt config/thesaurus_v2.json.gz: de uuid's van alle begrippen in ABR 2 en RN 2.

Adlib levert bij onderwerpen (`Content_subject/RNA_URI`) de URI uit de thesaurus. Voor de CHT is dat de geldende URI, maar voor
het ABR en het Referentienetwerk is het de oude vorm zonder versie: `…/term/id/abr/<uuid>` en `…/term/id/rn/<uuid>`. Geldend zijn
`…/term/id/abr/2/<uuid>` en `…/term/id/rn/2/<uuid>`, met dezelfde uuid. Gemeten op 20 november 2026 in rce/bibliotheek: van de
101 ABR-begrippen bestaan er 99 in ABR 2 en 1 in RN 2 (Adlib zet het onder het ABR), van de 21 RN-begrippen alle 21 in RN 2.

De transformatie zet een URI alleen om als de uuid in deze lijst staat. Een begrip zonder versie 2 houdt de URI uit de bron;
er wordt nooit naar een begrip verwezen dat niet bestaat.

Gebruik:  python tools/maak_thesaurus_v2.py          (vernieuwt config/thesaurus_v2.json.gz; kost ongeveer een minuut)
"""
import datetime
import gzip
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'config' / 'thesaurus_v2.json.gz'
API = 'https://api.linkeddata.cultureelerfgoed.nl/datasets'
# namespace in de URI -> (dataset met de thesaurus, graph van versie 2)
THESAURI = {
    'abr': ('thesauri/archeologischbasisregister', 'https://data.cultureelerfgoed.nl/term/id/abr/2/thesaurus'),
    'rn': ('thesauri/referentienetwerk', 'https://data.cultureelerfgoed.nl/term/id/rn/2/thesaurus'),
}
PAGE = 10000
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
# een begrip dat in beide versie 2-thesauri hoort te staan ("archeologisch: booronderzoek"), als controle op de download
KNOWN = 'e06a84fa-62e8-42ff-8f38-0ddfe9485a15'


def query(dataset: str, text: str) -> list:
    req = urllib.request.Request(f'{API}/{dataset}/sparql', data=urllib.parse.urlencode({'query': text}).encode(),
                                 headers={'Accept': 'application/sparql-results+json'})
    return json.load(urllib.request.urlopen(req, timeout=600))['results']['bindings']


def concepts(ns: str) -> list:
    """Alle uuid's van skos:Concept in de graph van versie 2, per pagina op volgorde van ?c (geen OFFSET)."""
    dataset, graph = THESAURI[ns]
    pattern = re.compile(rf'^https://data\.cultureelerfgoed\.nl/term/id/{ns}/2/({UUID})$')
    found, last = set(), None
    while True:
        flt = f'FILTER(STR(?c) > "{last}")' if last else ''
        rows = query(dataset, f'SELECT DISTINCT ?c WHERE {{ GRAPH <{graph}> {{ ?c a <http://www.w3.org/2004/02/skos/core#Concept> }} '
                              f'{flt} }} ORDER BY STR(?c) LIMIT {PAGE}')
        for r in rows:
            m = pattern.match(r['c']['value'])
            if m:
                found.add(m.group(1))
        if len(rows) < PAGE:
            return sorted(found)
        last = rows[-1]['c']['value']


def main() -> int:
    data = {ns: concepts(ns) for ns in THESAURI}
    for ns, uuids in data.items():
        print(f'{ns}/2: {len(uuids)} begrippen')
        if KNOWN not in uuids or len(uuids) < 1000:
            print(f'Download van {ns}/2 klopt niet (controlebegrip ontbreekt of te weinig begrippen); bestand niet geschreven.')
            return 1
    out = {'gemaakt': datetime.date.today().isoformat(),
           'bron': {ns: f'{API}/{dataset} graph {graph}' for ns, (dataset, graph) in THESAURI.items()},
           'concepts': data}
    with gzip.open(OUT, 'wt', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f'geschreven: {OUT.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
