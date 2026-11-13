# -*- coding: utf-8 -*-
"""TD GDM - Phase 2 : metadonnees descriptives des HTML Landing Zone.
S'appuie sur les selecteurs de l'exemple de M. Eric KLOECKLE.
Les champs non extraits sont consignes dans l'audit, pas inventes.
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import re
from bs4 import BeautifulSoup

ROOT = Path(r'C:\TD_DATALAKE\DATALAKE')
META_DIR = ROOT / '2_CURATED_ZONE' / 'METADONNEES'
TECH = META_DIR / 'metadonnee_technique.csv'
DESCRIPTIVE = META_DIR / 'metadonnee_descriptive.csv'
AUDIT = META_DIR / 'audit_extraction.csv'


def clean(text):
    """Normaliser les espaces SANS modifier les sources HTML."""
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def text_of(node):
    return clean(node.get_text(' ', strip=True)) if node else ''


def first_text(soup, *selectors):
    for selector in selectors:
        val = text_of(soup.select_one(selector))
        if val:
            return val
    return ''


def info_entity(soup, index):
    blocks = soup.select('div.infoEntity')
    return text_of(blocks[index].select_one('span')) if len(blocks) > index else ''


def extract_emp(soup):
    # Selecteurs repris/adaptes du support Python du professeur.
    return {
        'libelle_emploi': first_text(soup, 'h1.topcard__title'),
        'nom_entreprise': first_text(soup, 'span.topcard__flavor:not(.topcard__flavor--bullet)'),
        'ville_emploi': first_text(soup, 'span.topcard__flavor--bullet'),
        'description_emploi': first_text(soup, 'div.description__text--rich'),
    }


def extract_soc(soup):
    return {
        'nom_entreprise': first_text(soup, 'h1.strong.tightAll span', 'h1.strong.tightAll'),
        'ville_entreprise': info_entity(soup, 1),
        'taille_entreprise': info_entity(soup, 2),
        # Champs additionnels : seulement si une balise correspond.
        'description_entreprise': first_text(soup, '#EmpBasicInfo'),
    }


def review_text_fallback(review):
    """Fallback pour les anciennes pages Glassdoor avec Avantages/Inconvénients.

    Ne s'applique que lorsque le selecteur HTML original ne retourne rien.
    """
    whole = text_of(review)
    # La page source peut contenir des avis avec leurs labels traduits.
    match = re.search(
        r'\bAvantages\b\s*(.*?)\s*\bInconvénients\b\s*(.*?)'
        r'(?=\s*(?:Continuer à lire|Partagez sur|Utile|Signaler comme inapproprié)|$)',
        whole, flags=re.IGNORECASE | re.DOTALL
    )
    if not match:
        return '', '', ''
    pros, cons = clean(match.group(1)), clean(match.group(2))
    pieces = []
    if pros:
        pieces.append('Avantages: ' + pros)
    if cons:
        pieces.append('Inconvénients: ' + cons)
    return ' | '.join(pieces), pros, cons


def extract_avi(soup):
    values = {
        'nom_entreprise': first_text(soup, 'div.header.cell.info span'),
        'note_moyenne_entreprise': first_text(
            soup, 'div.v2__EIReviewsRatingsStylesV2__ratingNum.v2__EIReviewsRatingsStylesV2__large',
            'div.v2__EIReviewsRatingsStylesV2__ratingNum'),
    }
    reviews = soup.select('li.empReview')
    values['nombre_avis_page'] = str(len(reviews))
    for index, review in enumerate(reviews, start=1):
        prefix = f'avis_{index:03d}_'
        values[prefix + 'poste_auteur'] = first_text(review, 'span.authorJobTitle.middle.reviewer')
        # Champ facultatif: l'auteur ne fournit pas toujours son lieu.
        values[prefix + 'localisation_auteur'] = first_text(review, 'span.authorLocation')
        values[prefix + 'titre'] = first_text(review, 'p.mainText.mb-0')
        original = first_text(review, 'div.mt-md.common__EiReviewTextStyles__allowLineBreaks')
        fallback, pros, cons = review_text_fallback(review) if not original else ('', '', '')
        values[prefix + 'texte'] = original or fallback
        # Ces deux champs sont facultatifs et n'ont pas a etre renseignes
        # si le selecteur original a deja extrait une description exploitable.
        values[prefix + 'avantages'] = pros
        values[prefix + 'inconvenients'] = cons
    return values


def champs_obligatoires_manquants(category, fields):
    """Ne confond pas donnee absente et erreur de parsing."""
    missing = []
    for key, val in fields.items():
        if category == 'AVIS-SOC':
            # Champs optionnels: localisation et sous-sections avantages/inconvenients.
            if key.endswith(('_localisation_auteur', '_avantages', '_inconvenients')):
                continue
        if not val:
            missing.append(key)
    return missing


def load_objects():
    grouped = defaultdict(dict)
    with TECH.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        required = {'OBJET_ID', 'COLONNE', 'VALEUR'}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f'Colonnes attendues dans {TECH}: {required}')
        for row in reader:
            grouped[row['OBJET_ID']][row['COLONNE']] = row['VALEUR']
    return grouped


def main():
    if not TECH.is_file():
        raise SystemExit(f'Metadonnees techniques introuvables : {TECH}')
    META_DIR.mkdir(parents=True, exist_ok=True)
    objects = load_objects()
    functions = {'INFO-EMP': extract_emp, 'INFO-SOC': extract_soc, 'AVIS-SOC': extract_avi}
    rows, audits, counts = [], [], Counter()
    for oid, metadata in sorted(objects.items(), key=lambda x: int(x[0])):
        category = metadata.get('categorie', '')
        location = metadata.get('path_name_file_cible', '')
        filename = metadata.get('nom_fichier_source', '')
        file = Path(location)
        if category not in functions or not file.is_file():
            audits.append([oid, category, filename, 'ERREUR', 'Catégorie inconnue ou fichier absent'])
            counts['ERREUR'] += 1
            continue
        try:
            html = file.read_bytes().decode('utf-8-sig', errors='replace')
            soup = BeautifulSoup(html, 'lxml')
            fields = functions[category](soup)
            missing = champs_obligatoires_manquants(category, fields)
            for key, value in fields.items():
                rows.append([oid, key, value if value else 'NULL'])
            status = 'OK' if not missing else 'PARTIEL'
            audits.append([oid, category, filename, status, ', '.join(missing)])
            counts[category] += 1
            counts[status] += 1
        except Exception as exc:
            audits.append([oid, category, filename, 'ERREUR', str(exc)[:400]])
            counts['ERREUR'] += 1

    with DESCRIPTIVE.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        writer.writerow(['OBJET_ID', 'COLONNE', 'VALEUR'])
        writer.writerows(rows)
    with AUDIT.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['OBJET_ID', 'CATEGORIE', 'FICHIER', 'STATUT', 'CHAMPS_ABSENTS_OU_ERREUR'])
        writer.writerows(audits)

    print(f'Objets en metadonnees techniques : {len(objects)}')
    for category in functions:
        print(f'{category}: {counts[category]} fichier(s) traites')
    print(f"OK: {counts['OK']} | PARTIEL: {counts['PARTIEL']} | ERREUR: {counts['ERREUR']}")
    print(f'Lignes descriptives: {len(rows)}')
    print('CSV:', DESCRIPTIVE)
    print('Audit:', AUDIT)
    print('IMPORTANT : examiner les PARTIEL et ERREUR dans audit_extraction.csv.')


if __name__ == '__main__':
    main()
