"""Toets JSON-LD-bestanden aan de SHACL-shapes.

Gebruik:
    python src/validate_service.py data/*.jsonld
    python src/validate_service.py --shapes shacl/bibliotheek.shacl.ttl --max-warnings 0 data/books-0000.jsonld

Afsluitcode 1 bij minstens één Violation (of meer Warnings dan --max-warnings, indien opgegeven).
Warnings en Info worden samengevat maar laten de run slagen; zo blijven bekende hiaten in de bron zichtbaar.
"""
import argparse
import collections
import logging
import sys

import pyshacl
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH

logger = logging.getLogger(__name__)

SEVERITY = {SH.Violation: 'Violation', SH.Warning: 'Warning', SH.Info: 'Info'}


def validate_graph(data: Graph, shapes: Graph) -> dict:
    """Valideer één graph; geeft {'Violation': Counter, 'Warning': Counter, 'Info': Counter} van bericht -> aantal
    plus voorbeelden onder 'examples' (bericht -> eerste focusnode)."""
    _, report, _ = pyshacl.validate(data, shacl_graph=shapes, inference='none', abort_on_first=False)
    summary = {'Violation': collections.Counter(), 'Warning': collections.Counter(), 'Info': collections.Counter(),
               'examples': {}}
    for result in report.subjects(RDF.type, SH.ValidationResult):
        severity = SEVERITY.get(report.value(result, SH.resultSeverity), 'Violation')
        message = str(report.value(result, SH.resultMessage) or report.value(result, SH.sourceConstraintComponent))
        summary[severity][message] += 1
        summary['examples'].setdefault(message, str(report.value(result, SH.focusNode)))
    return summary


def validate_files(paths: list, shapes_path: str) -> dict:
    shapes = Graph().parse(shapes_path, format='turtle')
    total = {'Violation': collections.Counter(), 'Warning': collections.Counter(), 'Info': collections.Counter(),
             'examples': {}, 'files': 0}
    for path in paths:
        data = Graph().parse(path, format='json-ld')
        result = validate_graph(data, shapes)
        total['files'] += 1
        for severity in ('Violation', 'Warning', 'Info'):
            total[severity].update(result[severity])
        for message, node in result['examples'].items():
            total['examples'].setdefault(message, node)
        logger.info('%s: %d triples, %d violations, %d warnings', path, len(data),
                    sum(result['Violation'].values()), sum(result['Warning'].values()))
    return total


def report(total: dict) -> None:
    for severity in ('Violation', 'Warning', 'Info'):
        if not total[severity]:
            continue
        logger.info('--- %s (%d) ---', severity, sum(total[severity].values()))
        for message, count in total[severity].most_common(25):
            logger.info('%6d  %s   (bijv. %s)', count, message, total['examples'].get(message))


def main(argv=None) -> int:
    logging.basicConfig(format='%(levelname)-8s %(message)s', level=logging.INFO)
    parser = argparse.ArgumentParser('Valideer JSON-LD tegen SHACL')
    parser.add_argument('files', nargs='+')
    parser.add_argument('--shapes', default='shacl/bibliotheek.shacl.ttl')
    parser.add_argument('--max-warnings', type=int, default=None,
                        help='Laat de run ook falen bij meer dan dit aantal warnings (standaard: warnings falen niet).')
    args = parser.parse_args(argv)

    total = validate_files(args.files, args.shapes)
    report(total)
    violations = sum(total['Violation'].values())
    warnings = sum(total['Warning'].values())
    logger.info('Klaar: %d bestand(en), %d violations, %d warnings', total['files'], violations, warnings)
    if violations or (args.max_warnings is not None and warnings > args.max_warnings):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
