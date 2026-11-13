# TD Data Lakehouse - Phase 2A : inspection des vraies pages HTML
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(r'C:\TD_DATALAKE\DATALAKE\1_LANDING_ZONE')
GROUPES = {
    'INFO-EMP': (ROOT / 'LINKEDIN' / 'EMP', {
        'titre_emploi': 'h1.topcard__title',
        'entreprise': 'span.topcard__flavor',
        'ville_emploi': 'span.topcard__flavor--bullet',
        'description': 'div.description__text--rich',
    }),
    'INFO-SOC': (ROOT / 'GLASSDOOR' / 'SOC', {
        'entreprise': 'h1.strong.tightAll',
        'infos_entreprise': 'div.infoEntity',
        'description': '#EmpBasicInfo',
    }),
    'AVIS-SOC': (ROOT / 'GLASSDOOR' / 'AVI', {
        'entreprise': 'div.header.cell.info',
        'note_moyenne': 'div.v2__EIReviewsRatingsStylesV2__ratingNum',
        'bloc_avis': 'li.empReview',
        'texte_avis': 'p.mainText.mb-0',
        'localisation_auteur': 'span.authorLocation',
    }),
}

for type_source, (dossier, selecteurs) in GROUPES.items():
    fichiers = sorted(dossier.glob('*.html'))
    print('\n' + '=' * 85)
    print(f'{type_source} : {len(fichiers)} fichiers dans {dossier}')
    if not fichiers:
        continue
    fichier = fichiers[0]
    print('EXEMPLE :', fichier.name)
    # Les pages historiques ne sont pas toujours encodées en UTF-8.
    html = fichier.read_bytes().decode('utf-8-sig', errors='replace')
    soup = BeautifulSoup(html, 'lxml')
    print('TITRE HTML :', soup.title.get_text(' ', strip=True)[:180] if soup.title else 'ABSENT')
    for champ, css in selecteurs.items():
        matches = soup.select(css)
        exemple = matches[0].get_text(' ', strip=True)[:150] if matches else 'ABSENT'
        print(f'  {champ:22} {len(matches):3} résultat(s) | {exemple}')
    print('BALISES h1 :', [x.get_text(' ', strip=True)[:90] for x in soup.find_all('h1', limit=3)])

print('\nInspection terminée. Vérifier les valeurs avant de lancer l’extraction globale.')
