"""Phase 3.5 - Validation du Data Warehouse (CSV), TD Data Lakehouse.

Aucune modification des cinq tables. Sorties: validation_phase3/{rapport_validation.csv, bilan_validation.txt}.
Exécution: python 03e_validation_datawarehouse.py
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

BASE = Path(r'C:\TD_DATALAKE\DATALAKE\3_PRODUCTION_ZONE')
DWH = BASE / 'DWH_CSV'
OUT = BASE / 'validation_phase3'

SCHEMA = {
    'DimEntreprise': ['EntrepriseID', 'NomEntreprise', 'CleNormalisee', 'VilleEntreprise', 'TailleEntreprise', 'DescriptionEntreprise', 'NoteMoyenneSource'],
    'DimPoste': ['PosteID', 'LibellePoste'],
    'DimLieu': ['LieuID', 'VilleOffre'],
    'FactOffres': ['OffreID', 'ObjetIDSource', 'EntrepriseID', 'PosteID', 'LieuID', 'DescriptionOffre', 'NbOffres'],
    'FactAvis': ['AvisID', 'ObjetIDSource', 'NumeroAvisPage', 'EntrepriseID', 'TitreAvis', 'TexteAvis', 'Avantages', 'Inconvenients', 'PosteAuteur', 'LocalisationAuteur', 'NbAvis'],
}
PK = {'DimEntreprise': 'EntrepriseID', 'DimPoste': 'PosteID', 'DimLieu': 'LieuID', 'FactOffres': 'OffreID', 'FactAvis': 'AvisID'}
FK = [
    ('FactOffres', 'EntrepriseID', 'DimEntreprise', 'EntrepriseID'),
    ('FactOffres', 'PosteID', 'DimPoste', 'PosteID'),
    ('FactOffres', 'LieuID', 'DimLieu', 'LieuID'),
    ('FactAvis', 'EntrepriseID', 'DimEntreprise', 'EntrepriseID'),
]
issues = []
tables = {}

def check(category, control, status, details):
    issues.append({'CATEGORIE': category, 'CONTROLE': control, 'STATUT': status, 'DETAIL': str(details)})

def is_missing(v):
    return v is None or str(v).strip() == '' or str(v).strip().upper() == 'NULL'

def load(name):
    path = DWH / f'{name}.csv'
    if not path.exists():
        check('FICHIER', name, 'ECHEC', f'Absent: {path}')
        return None
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f, delimiter=';')
            fields = reader.fieldnames or []
            expected = SCHEMA[name]
            missing = [c for c in expected if c not in fields]
            extra = [c for c in fields if c not in expected]
            if missing:
                check('SCHEMA', name, 'ECHEC', f'Colonnes manquantes: {missing}')
                return None
            check('SCHEMA', name, 'OK' if not extra else 'AVERTISSEMENT', 'Colonnes attendues présentes' + (f'; supplémentaires: {extra}' if extra else ''))
            rows = list(reader)
            return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        check('FICHIER', name, 'ECHEC', f'{type(exc).__name__}: {exc}')
        return None

for table in SCHEMA:
    tables[table] = load(table)

for table, key in PK.items():
    rows = tables[table]
    if rows is None:
        continue
    vals = [row[key].strip() for row in rows]
    blanks = sum(is_missing(v) for v in vals)
    duplicates = sum(n-1 for n in Counter(v for v in vals if not is_missing(v)).values() if n > 1)
    check('CLE_PRIMAIRE', f'{table}.{key}', 'OK' if not blanks and not duplicates else 'ECHEC', f'lignes={len(rows)}; vides={blanks}; doublons={duplicates}')

for fact, col, dim, dimcol in FK:
    if tables[fact] is None or tables[dim] is None:
        continue
    known = {r[dimcol].strip() for r in tables[dim] if not is_missing(r[dimcol])}
    empty = sum(is_missing(r[col]) for r in tables[fact])
    orphan = sum(not is_missing(r[col]) and r[col].strip() not in known for r in tables[fact])
    check('CLE_ETRANGERE', f'{fact}.{col} -> {dim}.{dimcol}', 'OK' if not empty and not orphan else 'ECHEC', f'vides={empty}; orphelines={orphan}')

for table, expected in [('FactOffres', 254), ('FactAvis', 1537)]:
    if tables[table] is not None:
        n = len(tables[table])
        check('VOLUMETRIE', table, 'OK' if n == expected else 'ECHEC', f'observé={n}; référence Phase 3.3={expected}')

for table, measure in [('FactOffres', 'NbOffres'), ('FactAvis', 'NbAvis')]:
    rows = tables[table]
    if rows is None:
        continue
    bad = sum(row[measure].strip() not in {'1', '1.0'} for row in rows)
    check('MESURE', f'{table}.{measure}', 'OK' if not bad else 'ECHEC', f'valeurs différentes de 1: {bad}')
    src_empty = sum(is_missing(row['ObjetIDSource']) for row in rows)
    check('TRACABILITE', f'{table}.ObjetIDSource', 'OK' if not src_empty else 'ECHEC', f'Objets sources vides: {src_empty}')

if tables['FactOffres'] is not None:
    # Chaque INFO-EMP correspond à une offre selon le jeu de données utilisé.
    vals = [row['ObjetIDSource'].strip() for row in tables['FactOffres']]
    doubles = sum(n-1 for n in Counter(vals).values() if n > 1)
    check('GRANULARITE', 'FactOffres.ObjetIDSource', 'OK' if doubles == 0 else 'AVERTISSEMENT', f'Objets sources répétés: {doubles}')

if tables['FactAvis'] is not None:
    pairs = [(row['ObjetIDSource'].strip(), row['NumeroAvisPage'].strip()) for row in tables['FactAvis']]
    doubles = sum(n-1 for n in Counter(pairs).values() if n > 1)
    check('GRANULARITE', 'FactAvis.(ObjetIDSource,NumeroAvisPage)', 'OK' if doubles == 0 else 'ECHEC', f'Paires répétées: {doubles}')
    blank_text = sum(is_missing(row['TexteAvis']) for row in tables['FactAvis'])
    check('QUALITE', 'FactAvis.TexteAvis', 'OK' if blank_text == 0 else 'AVERTISSEMENT', f'Textes vides ou NULL: {blank_text}')

source_audit = DWH / 'audit_etl.csv'
if source_audit.exists():
    with source_audit.open('r', encoding='utf-8-sig', newline='') as f:
        warnings = list(csv.DictReader(f, delimiter=';'))
    check('AUDIT_SOURCE', 'audit_etl.csv', 'AVERTISSEMENT' if warnings else 'OK', f'{len(warnings)} avertissement(s) ETL existant(s), à documenter (non modifiés)')
else:
    check('AUDIT_SOURCE', 'audit_etl.csv', 'AVERTISSEMENT', 'Fichier non trouvé')

OUT.mkdir(parents=True, exist_ok=True)
report = OUT / 'rapport_validation.csv'
with report.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['CATEGORIE', 'CONTROLE', 'STATUT', 'DETAIL'], delimiter=';')
    writer.writeheader()
    writer.writerows(issues)

counts = Counter(x['STATUT'] for x in issues)
summary = [
    '=== PHASE 3.5 - VALIDATION FINALE DU DATA WAREHOUSE ===',
    *(f'{name}: {len(tables[name]) if tables[name] is not None else "NON CHARGÉ"} lignes' for name in SCHEMA),
    f'Controles OK: {counts["OK"]}',
    f'Avertissements: {counts["AVERTISSEMENT"]}',
    f'Echecs: {counts["ECHEC"]}',
    '',
    'Détails des avertissements et échecs:',
    *(f'- [{x["STATUT"]}] {x["CONTROLE"]}: {x["DETAIL"]}' for x in issues if x['STATUT'] != 'OK'),
    '',
    f'Rapport CSV: {report}',
]
text = '\n'.join(summary)
(OUT / 'bilan_validation.txt').write_text(text + '\n', encoding='utf-8')
print(text)
if counts['ECHEC']:
    raise SystemExit(1)
