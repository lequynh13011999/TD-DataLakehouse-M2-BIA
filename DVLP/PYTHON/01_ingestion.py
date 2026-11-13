# -*- coding: utf-8 -*-
"""TD Data Lakehouse - Phase 1: ingestion HTML et métadonnées techniques."""
from pathlib import Path
from datetime import datetime
import csv
import hashlib
import os
import shutil
import tempfile

ROOT = Path(r"C:\TD_DATALAKE\DATALAKE")
SOURCE = ROOT / "0_SOURCE_WEB"
LANDING = ROOT / "1_LANDING_ZONE"
METADATA_DIR = ROOT / "2_CURATED_ZONE" / "METADONNEES"
METADATA_FILE = METADATA_DIR / "metadonnee_technique.csv"
LOG_FILE = ROOT.parent / "LOGFILES" / "ingestion_erreurs.log"

CATEGORIES = {
    "INFO-EMP": ("LINKEDIN", "EMP"),
    "INFO-SOC": ("GLASSDOOR", "SOC"),
    "AVIS-SOC": ("GLASSDOOR", "AVI"),
}


def empreinte_sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def type_fichier(nom):
    for motif, dossier in CATEGORIES.items():
        if motif in nom.upper():
            return motif, LANDING.joinpath(*dossier)
    return None, None


def main():
    if not SOURCE.is_dir():
        raise SystemExit(f"Répertoire source introuvable : {SOURCE}")

    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    for dossier in CATEGORIES.values():
        LANDING.joinpath(*dossier).mkdir(parents=True, exist_ok=True)

    fichiers = sorted(
        (p for p in SOURCE.iterdir() if p.is_file() and p.suffix.lower() == ".html"),
        key=lambda p: p.name.lower()
    )
    lignes = []
    erreurs = []
    compteurs = {categorie: 0 for categorie in CATEGORIES}

    # Identifiant déterministe par fichier dans cette liste triée.
    for objet_id, fichier_source in enumerate(fichiers, start=1):
        categorie, repertoire_cible = type_fichier(fichier_source.name)
        if categorie is None:
            erreurs.append(f"Fichier non reconnu : {fichier_source.name}")
            continue

        fichier_cible = repertoire_cible / fichier_source.name
        try:
            hash_source = empreinte_sha256(fichier_source)
            # La source n'est jamais déplacée ou modifiée.
            if fichier_cible.exists():
                if empreinte_sha256(fichier_cible) != hash_source:
                    raise ValueError("Destination déjà présente, contenu différent")
            else:
                shutil.copy2(fichier_source, fichier_cible)

            if empreinte_sha256(fichier_cible) != hash_source:
                raise ValueError("Échec du contrôle d'intégrité SHA-256")

            champs = {
                "date_ingestion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nom_fichier_source": fichier_source.name,
                "path_name_file_source": str(fichier_source),
                "path_name_file_cible": str(fichier_cible),
                "categorie": categorie,
                "type_fichier": fichier_source.suffix.lower().lstrip("."),
                "taille_octets": fichier_source.stat().st_size,
                "sha256": hash_source,
            }
            lignes.extend((objet_id, colonne, valeur) for colonne, valeur in champs.items())
            compteurs[categorie] += 1
        except (OSError, ValueError) as exc:
            erreurs.append(f"{fichier_source.name} : {exc}")

    # Écriture complète, sans doublons si le programme est relancé.
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=METADATA_DIR, suffix=".csv", delete=False) as tmp:
        chemin_tmp = Path(tmp.name)
        writer = csv.writer(tmp, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL)
        writer.writerow(["OBJET_ID", "COLONNE", "VALEUR"])
        writer.writerows(lignes)
    os.replace(chemin_tmp, METADATA_FILE)

    LOG_FILE.write_text("\n".join(erreurs) + ("\n" if erreurs else ""), encoding="utf-8")
    print(f"Fichiers HTML trouvés : {len(fichiers)}")
    for categorie, nombre in compteurs.items():
        print(f"{categorie} : {nombre} fichiers vérifiés")
    print(f"Erreurs : {len(erreurs)}")
    print(f"Métadonnées : {METADATA_FILE}")
    print(f"Journal : {LOG_FILE}")


if __name__ == "__main__":
    main()
