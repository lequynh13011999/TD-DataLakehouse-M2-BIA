# -*- coding: utf-8 -*-
"""Phase 3.3 — Dictionnaire des données et modèle décisionnel (sans ETL).
TD Gestion de données massives — M2 BI&A — Lyon 2.
Ce script ne modifie pas les fichiers sources ni le mapping à valider.
"""
from collections import defaultdict, Counter
import csv
from pathlib import Path
import re

ROOT = Path(r"C:\TD_DATALAKE\DATALAKE")
META = ROOT / "2_CURATED_ZONE" / "METADONNEES"
LINK = ROOT / "3_PRODUCTION_ZONE" / "linked_data_phase3"
OUT = ROOT / "3_PRODUCTION_ZONE" / "modele_phase3"

# (table, colonne, type logique, rôle, source/règle, obligatoire, commentaire)
DICTIONNAIRE = [
    ("DimEntreprise", "EntrepriseID", "INTEGER", "PK", "Clé substitut générée par ETL", "OUI", "Une ligne par entreprise canonique retenue"),
    ("DimEntreprise", "NomEntreprise", "TEXT", "ATTRIBUT", "nom_entreprise (EMP/SOC/AVI) + correspondances validées", "OUI", "Ne jamais accepter une suggestion fuzzy sans validation"),
    ("DimEntreprise", "CleNormalisee", "TEXT", "ATTRIBUT", "Normalisation du nom de l'entreprise", "OUI", "Une même clé peut représenter plusieurs noms; vérifier les collisions"),
    ("DimEntreprise", "VilleEntreprise", "TEXT", "ATTRIBUT", "INFO-SOC.ville_entreprise", "NON", "NULL si entreprise sans fiche Glassdoor"),
    ("DimEntreprise", "TailleEntreprise", "TEXT", "ATTRIBUT", "INFO-SOC.taille_entreprise", "NON", "Garder le texte natif si pas de valeur numérique fiable"),
    ("DimEntreprise", "DescriptionEntreprise", "TEXT", "ATTRIBUT", "INFO-SOC.description_entreprise", "NON", "Description source"),
    ("DimEntreprise", "NoteMoyenneSource", "DECIMAL", "ATTRIBUT", "AVIS-SOC.note_moyenne_entreprise si disponible", "NON", "Note de page/entreprise; PAS une note par avis"),
    ("DimPoste", "PosteID", "INTEGER", "PK", "Clé substitut générée par ETL", "OUI", "Une ligne par libellé normalisé distinct"),
    ("DimPoste", "LibellePoste", "TEXT", "ATTRIBUT", "INFO-EMP.libelle_emploi", "OUI", "Conserver également la version originale si transformation"),
    ("DimLieu", "LieuID", "INTEGER", "PK", "Clé substitut générée par ETL", "OUI", "Une ligne par lieu d'offre distinct"),
    ("DimLieu", "VilleOffre", "TEXT", "ATTRIBUT", "INFO-EMP.ville_emploi", "OUI", "Ne pas confondre avec ville_entreprise"),
    ("FactOffres", "OffreID", "INTEGER", "PK", "Clé substitut générée par ETL", "OUI", "Granularité = 1 fichier HTML INFO-EMP / offre"),
    ("FactOffres", "ObjetIDSource", "TEXT", "TRACE", "OBJET_ID de l'HTML INFO-EMP", "OUI", "Unique dans FactOffres"),
    ("FactOffres", "EntrepriseID", "INTEGER", "FK", "DimEntreprise.EntrepriseID", "OUI", "Entreprise LinkedIn conservée même sans correspondance SOC"),
    ("FactOffres", "PosteID", "INTEGER", "FK", "DimPoste.PosteID", "OUI", ""),
    ("FactOffres", "LieuID", "INTEGER", "FK", "DimLieu.LieuID", "OUI", ""),
    ("FactOffres", "DescriptionOffre", "TEXT", "ATTRIBUT", "INFO-EMP.description_emploi", "NON", "Texte long; peut aussi être dans une table détail"),
    ("FactOffres", "NbOffres", "INTEGER", "MESURE", "Constante 1", "OUI", "SUM(NbOffres) = nombre d'offres"),
    ("FactAvis", "AvisID", "TEXT", "PK", "Concaténation stable ObjetIDSource + numéro d'avis", "OUI", "Granularité = 1 avis au sein d'un HTML AVIS-SOC"),
    ("FactAvis", "ObjetIDSource", "TEXT", "TRACE", "OBJET_ID de l'HTML AVIS-SOC", "OUI", "Répété pour plusieurs avis d'un fichier"),
    ("FactAvis", "NumeroAvisPage", "INTEGER", "TRACE", "Index avis_001, avis_002, ...", "OUI", "Ne pas assimiler à ID mondial unique d'un avis"),
    ("FactAvis", "EntrepriseID", "INTEGER", "FK", "DimEntreprise.EntrepriseID", "OUI", "Rattachement par nom SOC/AVI validé"),
    ("FactAvis", "TitreAvis", "TEXT", "ATTRIBUT", "AVIS-SOC.avis_NNN_titre", "NON", ""),
    ("FactAvis", "TexteAvis", "TEXT", "ATTRIBUT", "AVIS-SOC.avis_NNN_texte", "NON", ""),
    ("FactAvis", "Avantages", "TEXT", "ATTRIBUT", "AVIS-SOC.avis_NNN_avantages", "NON", "Nombreux NULL; ne pas exiger"),
    ("FactAvis", "Inconvenients", "TEXT", "ATTRIBUT", "AVIS-SOC.avis_NNN_inconvenients", "NON", "Nombreux NULL; ne pas exiger"),
    ("FactAvis", "PosteAuteur", "TEXT", "ATTRIBUT", "AVIS-SOC.avis_NNN_poste_auteur", "NON", "49 valeurs manquantes signalées en Phase 2"),
    ("FactAvis", "LocalisationAuteur", "TEXT", "ATTRIBUT", "AVIS-SOC.avis_NNN_localisation_auteur", "NON", "Ne pas confondre avec DimLieu des offres"),
    ("FactAvis", "NbAvis", "INTEGER", "MESURE", "Constante 1", "OUI", "SUM(NbAvis) = nombre d'avis"),
]

SCHEMA = r'''erDiagram
    DimEntreprise ||--o{ FactOffres : "EntrepriseID"
    DimEntreprise ||--o{ FactAvis : "EntrepriseID"
    DimPoste ||--o{ FactOffres : "PosteID"
    DimLieu ||--o{ FactOffres : "LieuID"
    DimEntreprise {
        int EntrepriseID PK
        string NomEntreprise
        string CleNormalisee
        string VilleEntreprise
        string TailleEntreprise
        string DescriptionEntreprise
        float NoteMoyenneSource
    }
    DimPoste {
        int PosteID PK
        string LibellePoste
    }
    DimLieu {
        int LieuID PK
        string VilleOffre
    }
    FactOffres {
        int OffreID PK
        string ObjetIDSource
        int EntrepriseID FK
        int PosteID FK
        int LieuID FK
        string DescriptionOffre
        int NbOffres
    }
    FactAvis {
        string AvisID PK
        string ObjetIDSource
        int NumeroAvisPage
        int EntrepriseID FK
        string TitreAvis
        string TexteAvis
        string Avantages
        string Inconvenients
        string PosteAuteur
        string LocalisationAuteur
        int NbAvis
    }
'''


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def write_csv(path, cols, data):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        w.writerows(data)


def main():
    tech = read_csv(META / "metadonnee_technique.csv")
    desc = read_csv(META / "metadonnee_descriptive.csv")
    mapping = read_csv(LINK / "correspondances_emp_soc_a_valider.csv")
    for dataset, expected in ((tech, {"OBJET_ID", "COLONNE", "VALEUR"}),
                              (desc, {"OBJET_ID", "COLONNE", "VALEUR"}),
                              (mapping, {"NOM_EMP", "METHODE", "STATUT_VALIDATION"})):
        if dataset and not expected.issubset(dataset[0]):
            raise ValueError(f"Colonnes requises absentes : {expected - set(dataset[0])}")
    cats = {r['OBJET_ID']:r['VALEUR'] for r in tech if r['COLONNE']=='categorie'}
    fields = defaultdict(dict)
    for r in desc:
        fields[r['OBJET_ID']][r['COLONNE']] = r['VALEUR']
    cnt = Counter(cats.values())
    reviews = 0
    review_pattern = re.compile(r'^avis_(\d{3})_titre$')
    for oid, f in fields.items():
        if cats.get(oid) == 'AVIS-SOC':
            reviews += sum(bool(review_pattern.match(k)) for k in f)
    methods = Counter(m.get('METHODE') for m in mapping)
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / 'dictionnaire_donnees.csv',
              ['TABLE', 'COLONNE', 'TYPE_LOGIQUE', 'ROLE', 'SOURCE_OU_REGLE', 'OBLIGATOIRE', 'COMMENTAIRE'], DICTIONNAIRE)
    (OUT / 'schema_decisionnel.mmd').write_text(SCHEMA, encoding='utf-8')
    notes = f'''# Phase 3.3 — Modèle décisionnel proposé

Ce document est une proposition de conception, pas une alimentation effective du DWH.

## Profil de départ (lu dans les CSV)
- INFO-EMP : {cnt['INFO-EMP']} objets HTML, granularité 1 offre / objet (à confirmer selon les données)
- INFO-SOC : {cnt['INFO-SOC']} objets HTML
- AVIS-SOC : {cnt['AVIS-SOC']} objets HTML
- Avis repérés via `avis_NNN_titre` : {reviews} (à confirmer pour les avis incomplets)
- Lignes de métadonnées descriptives : {len(desc)}

## Correspondances EMP -> SOC (non validées)
- EXACT : {methods['EXACT']}
- NORMALISE : {methods['NORMALISE']}
- NON_TROUVE : {methods['NON_TROUVE']}
- Autres : {sum(v for k,v in methods.items() if k not in ('EXACT','NORMALISE','NON_TROUVE'))}

Ne pas confondre nombre de noms appariés et nombre d'offres appariées.
Ne pas valider automatiquement les suggestions FUZZY. Les valeurs `A_VALIDER` du fichier de mapping restent des hypothèses.

## Granularité
- FactOffres : une ligne par offre INFO-EMP avec un `OBJET_ID` unique.
- FactAvis : une ligne par couple (OBJET_ID du fichier AVIS-SOC, index NNN de l'avis).
- DimEntreprise : une ligne par identité d'entreprise déterminée par les règles de rapprochement validées.
- DimPoste : une ligne par libellé de poste normalisé.
- DimLieu : une ligne par ville d'offre; ne pas y fusionner la localisation d'auteur d'avis.

## Mesures prévues
- NbOffres = 1 par offre.
- NbAvis = 1 par avis.
- NoteMoyenneSource est une note provenant de la page entreprise et NE doit PAS être assimilée à une note individuelle d'avis.

## Contrôles de phase 3.4
- FactOffres attendu : {cnt['INFO-EMP']} lignes si 1 offre par HTML.
- Aucun OBJET_ID dupliqué dans FactOffres.
- Pas de doublon (OBJET_ID, numéro d'avis) dans FactAvis.
- Toutes les clés étrangères doivent exister dans leurs dimensions.
- Préserver les offres sans profil SOC (ne pas utiliser de INNER JOIN filtrant).
- Garder une trace des noms sources, des correspondances et des cas non validés.
'''
    (OUT / 'notes_conception.md').write_text(notes, encoding='utf-8')
    print('=== PHASE 3.3 — DICTIONNAIRE ET MODELE ===')
    print('INFO-EMP:', cnt['INFO-EMP'], '| INFO-SOC:', cnt['INFO-SOC'], '| AVIS-SOC:', cnt['AVIS-SOC'])
    print('Avis reperes par les titres indexes:', reviews)
    print('Correspondances non validees:', dict(methods))
    print('Dictionnaire:', len(DICTIONNAIRE), 'colonnes sur 5 tables')
    print('Repertoire des livrables:', OUT)
    for name in ('dictionnaire_donnees.csv','schema_decisionnel.mmd','notes_conception.md'):
        print(' -', name)
    print('AUCUNE donnee metier transformee ni DWH cree a cette etape.')


if __name__ == '__main__':
    main()
