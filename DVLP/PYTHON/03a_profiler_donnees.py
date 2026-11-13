# -*- coding: utf-8 -*-
"""TD Data Lakehouse - Phase 3A: profiler les metadonnees (lecture seule).
Python standard uniquement; ne modifie pas les CSV des phases precedentes.
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import re
import unicodedata

ROOT = Path(r"C:\TD_DATALAKE\DATALAKE")
META = ROOT / "2_CURATED_ZONE" / "METADONNEES"
TECH = META / "metadonnee_technique.csv"
DESC = META / "metadonnee_descriptive.csv"
REPORT = ROOT / "3_PRODUCTION_ZONE" / "profiling_phase3"


def load_long_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {"OBJET_ID", "COLONNE", "VALEUR"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Colonnes incorrectes dans {path.name}: {reader.fieldnames}")
        return list(reader)


def fold_company(name):
    # Clé de rapprochement candidate: ne remplace jamais le nom original.
    name = unicodedata.normalize("NFKD", name.casefold())
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.replace("&", " et ")
    name = re.sub(r"[^a-z0-9]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    tech, desc = load_long_csv(TECH), load_long_csv(DESC)
    objects, fields = defaultdict(dict), defaultdict(dict)
    repeated = Counter()
    for record in tech:
        objects[record["OBJET_ID"]][record["COLONNE"]] = record["VALEUR"]
    for record in desc:
        oid, key, val = record["OBJET_ID"], record["COLONNE"], record["VALEUR"]
        if key in fields[oid]:
            repeated[(oid, key)] += 1
        fields[oid][key] = val

    REPORT.mkdir(parents=True, exist_ok=True)
    categories = {oid: obj.get("categorie", "INCONNUE") for oid, obj in objects.items()}
    counts = Counter(categories.values())
    print("=== PHASE 3A : PROFIL DES DONNEES ===")
    print(f"Objets techniques : {len(objects)}")
    print(f"Lignes descriptives : {len(desc)}")
    print(f"Objets avec descriptif : {len(fields)}")
    print(f"Paires (OBJET_ID, COLONNE) dupliquees : {len(repeated)}")
    for typ in ("INFO-EMP", "INFO-SOC", "AVIS-SOC"):
        print(f"{typ}: {counts[typ]} objets")

    field_stats = defaultdict(lambda: [0, 0])
    for oid, data in fields.items():
        cat = categories.get(oid, "INCONNUE")
        for key, val in data.items():
            s = field_stats[(cat, key)]
            s[0] += 1
            s[1] += int(not val.strip() or val.strip().upper() in {"NULL", "NONE", "N/A"})
    stat_rows = [(cat, key, present, missing) for (cat, key), (present, missing) in field_stats.items()]
    stat_rows.sort(key=lambda x: (x[0], x[1]))
    write_csv(REPORT / "profil_champs.csv", ["CATEGORIE", "COLONNE", "NB_PRESENT", "NB_NULL"], stat_rows)
    for typ in ("INFO-EMP", "INFO-SOC", "AVIS-SOC"):
        print(f"\n--- Champs {typ} (20 premiers) ---")
        sample = [(key, found, nulls) for cat, key, found, nulls in stat_rows if cat == typ]
        for key, n, nulls in sample[:20]:
            print(f"{key:39s} present={n:4d} NULL={nulls}")
        print(f"Nombre de champs distincts : {len(sample)}")

    companies = defaultdict(set)
    for oid, data in fields.items():
        cat = categories.get(oid, "INCONNUE")
        name = data.get("nom_entreprise", "").strip()
        if name and name.upper() != "NULL":
            companies[cat].add(name)
    emp, soc, avi = (companies[cat] for cat in ("INFO-EMP", "INFO-SOC", "AVIS-SOC"))
    print("\n=== LIENS POTENTIELS ENTRE ENTREPRISES ===")
    print(f"Noms distincts : EMP={len(emp)}, SOC={len(soc)}, AVI={len(avi)}")
    print(f"EMP ∩ SOC, noms exacts : {len(emp & soc)}")
    print(f"EMP ∩ AVI, noms exacts : {len(emp & avi)}")
    print(f"SOC ∩ AVI, noms exacts : {len(soc & avi)}")
    folded = {cat: {fold_company(x) for x in names} for cat, names in companies.items()}
    print(f"EMP ∩ SOC, cle normalisee : {len(folded['INFO-EMP'] & folded['INFO-SOC'])}")
    print(f"EMP ∩ AVI, cle normalisee : {len(folded['INFO-EMP'] & folded['AVIS-SOC'])}")
    print(f"SOC ∩ AVI, cle normalisee : {len(folded['INFO-SOC'] & folded['AVIS-SOC'])}")
    write_csv(REPORT / "noms_entreprises.csv", ["SOURCE", "NOM_ORIGINAL", "CLE_NORMALISEE"],
              [(cat, name, fold_company(name)) for cat, names in sorted(companies.items()) for name in sorted(names)])
    print("\nFichiers crees dans :", REPORT)
    print("- profil_champs.csv")
    print("- noms_entreprises.csv")
    print("Aucune correspondance automatique entre entreprises n'a ete validee.")


if __name__ == "__main__":
    main()
