# Phase 3.3 — Modèle décisionnel proposé

Ce document est une proposition de conception, pas une alimentation effective du DWH.

## Profil de départ (lu dans les CSV)
- INFO-EMP : 254 objets HTML, granularité 1 offre / objet (à confirmer selon les données)
- INFO-SOC : 140 objets HTML
- AVIS-SOC : 209 objets HTML
- Avis repérés via `avis_NNN_titre` : 1537 (à confirmer pour les avis incomplets)
- Lignes de métadonnées descriptives : 11425

## Correspondances EMP -> SOC (non validées)
- EXACT : 37
- NORMALISE : 9
- NON_TROUVE : 140
- Autres : 0

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
- FactOffres attendu : 254 lignes si 1 offre par HTML.
- Aucun OBJET_ID dupliqué dans FactOffres.
- Pas de doublon (OBJET_ID, numéro d'avis) dans FactAvis.
- Toutes les clés étrangères doivent exister dans leurs dimensions.
- Préserver les offres sans profil SOC (ne pas utiliser de INNER JOIN filtrant).
- Garder une trace des noms sources, des correspondances et des cas non validés.
