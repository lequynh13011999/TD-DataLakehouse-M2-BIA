# -*- coding: utf-8 -*-
"""TD GDM – Phase 3.2 : aide au rapprochement des entreprises.
Lecture seule des métadonnées ; aucune correspondance approximative n'est validée automatiquement.
"""
from pathlib import Path
from collections import defaultdict, Counter
from difflib import SequenceMatcher
import csv
import re
import unicodedata

ROOT = Path(r"C:\TD_DATALAKE\DATALAKE")
META = ROOT / "2_CURATED_ZONE" / "METADONNEES"
OUT = ROOT / "3_PRODUCTION_ZONE" / "linked_data_phase3"


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        mandatory = {"OBJET_ID", "COLONNE", "VALEUR"}
        if not reader.fieldnames or not mandatory.issubset(set(reader.fieldnames)):
            raise ValueError(f"Colonnes attendues {mandatory} dans {path}; trouvees : {reader.fieldnames}")
        return list(reader)


def key_name(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("&", " et ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def main():
    tech = read_csv(META / "metadonnee_technique.csv")
    desc = read_csv(META / "metadonnee_descriptive.csv")
    cats = {}
    for r in tech:
        if r["COLONNE"] == "categorie":
            cats[r["OBJET_ID"]] = r["VALEUR"].strip()
    names = defaultdict(set)
    for r in desc:
        if r["COLONNE"] != "nom_entreprise":
            continue
        val = r["VALEUR"].strip()
        cat = cats.get(r["OBJET_ID"])
        if cat in {"INFO-EMP", "INFO-SOC", "AVIS-SOC"} and val and val.upper() != "NULL":
            names[cat].add(val)

    emp = sorted(names["INFO-EMP"], key=str.casefold)
    soc = sorted(names["INFO-SOC"], key=str.casefold)
    avi = sorted(names["AVIS-SOC"], key=str.casefold)
    soc_keys = defaultdict(list)
    for n in soc:
        soc_keys[key_name(n)].append(n)
    avi_keys = defaultdict(list)
    for n in avi:
        avi_keys[key_name(n)].append(n)

    mapping = []
    suggestions = []
    collision = []
    for source, idx in [("SOC", soc_keys), ("AVI", avi_keys)]:
        for k, vals in sorted(idx.items()):
            if len(vals) > 1:
                collision.append({"SOURCE": source, "CLE_NORMALISEE": k, "NOMS_CONCERNES": " | ".join(vals)})

    for original in emp:
        k = key_name(original)
        if original in names["INFO-SOC"]:
            status, method, suggestion = "A_VALIDER", "EXACT", original
        elif len(soc_keys[k]) == 1:
            status, method, suggestion = "A_VALIDER", "NORMALISE", soc_keys[k][0]
        elif len(soc_keys[k]) > 1:
            status, method, suggestion = "AMBIGU", "CLE_MULTIPLE", " | ".join(soc_keys[k])
        else:
            status, method, suggestion = "A_RECHERCHER", "NON_TROUVE", ""
            matches = sorted(((SequenceMatcher(None, k, key_name(s)).ratio(), s) for s in soc), reverse=True)[:3]
            for rank, (score, candidate) in enumerate(matches, 1):
                if score >= .65:
                    suggestions.append({"NOM_EMP": original, "RANG": rank, "NOM_SOC_CANDIDAT": candidate,
                                        "SIMILARITE": f"{score:.3f}", "DECISION_HUMAINE": ""})
        mapping.append({"NOM_EMP": original, "CLE_NORMALISEE_EMP": k,
                        "NOM_SOC_PROPOSE": suggestion, "METHODE": method,
                        "STATUT_VALIDATION": status, "NOM_ENTREPRISE_VALIDE": "", "COMMENTAIRE": ""})

    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "correspondances_emp_soc_a_valider.csv",
              ["NOM_EMP", "CLE_NORMALISEE_EMP", "NOM_SOC_PROPOSE", "METHODE", "STATUT_VALIDATION", "NOM_ENTREPRISE_VALIDE", "COMMENTAIRE"], mapping)
    write_csv(OUT / "suggestions_fuzzy_a_verifier.csv",
              ["NOM_EMP", "RANG", "NOM_SOC_CANDIDAT", "SIMILARITE", "DECISION_HUMAINE"], suggestions)
    write_csv(OUT / "collisions_cles_normalisees.csv",
              ["SOURCE", "CLE_NORMALISEE", "NOMS_CONCERNES"], collision)

    print("=== PHASE 3B - LINKED DATA : DIAGNOSTIC ===")
    print(f"Noms distincts : EMP={len(emp)}, SOC={len(soc)}, AVI={len(avi)}")
    print("Methodes de correspondance EMP -> SOC (non validees) :")
    for method, n in sorted(Counter(m["METHODE"] for m in mapping).items()):
        print(f"  {method}: {n}")
    print(f"Suggestions fuzzy a verifier : {len(suggestions)}")
    print(f"Collisions de cles normalisees : {len(collision)}")
    print("Correspondances SOC/AVI :")
    print(f"  Noms exacts communs : {len(names['INFO-SOC'] & names['AVIS-SOC'])}")
    print(f"  Cles communes : {len(set(soc_keys) & set(avi_keys))}")
    print(f"Fichiers generes : {OUT}")
    for name in ["correspondances_emp_soc_a_valider.csv", "suggestions_fuzzy_a_verifier.csv", "collisions_cles_normalisees.csv"]:
        print(f"  - {name}")
    print("ATTENTION : aucune jointure fuzzy n'a ete validee automatiquement.")


if __name__ == "__main__":
    main()
