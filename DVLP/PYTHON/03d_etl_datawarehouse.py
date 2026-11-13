# -*- coding: utf-8 -*-
"""Phase 3.4 — Construction du Data Warehouse CSV, TD Data Lakehouse M2 BI&A.

Entrées (lecture seule) : 2_CURATED_ZONE/METADONNEES/{metadonnee_technique,
metadonnee_descriptive}.csv et 3_PRODUCTION_ZONE/linked_data_phase3/
correspondances_emp_soc_a_valider.csv.

Politique de rapprochement conservatrice :
- SOC et AVI sont réunis sur leur clé normalisée (variantes de casse/accents).
- EMP est associé à SOC seulement si STATUT_VALIDATION vaut VALIDEE/VALIDE/
  CONFIRMEE/CONFIRME (avec ou sans accents), et que NOM_SOC_PROPOSE correspond
  de manière univoque à un nom SOC connu.
- En l'absence de validation, EMP garde son entreprise propre, même si son nom
  est identique à SOC : ne jamais transformer A_VALIDER en validation implicite.
- Aucune suggestion fuzzy n'est acceptée automatiquement.

Usage : python 03d_etl_datawarehouse.py
Option pour tests : python 03d_etl_datawarehouse.py --root C:/TD_DATALAKE/DATALAKE
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict, Counter
from pathlib import Path

NULLS = {'', 'NULL', 'N/A', 'NONE'}
REVIEW = re.compile(r'^avis_(\d{3})_titre$')
OUTPUTS = {
    'DimEntreprise': ['EntrepriseID','NomEntreprise','CleNormalisee','VilleEntreprise','TailleEntreprise','DescriptionEntreprise','NoteMoyenneSource'],
    'DimPoste': ['PosteID','LibellePoste'],
    'DimLieu': ['LieuID','VilleOffre'],
    'FactOffres': ['OffreID','ObjetIDSource','EntrepriseID','PosteID','LieuID','DescriptionOffre','NbOffres'],
    'FactAvis': ['AvisID','ObjetIDSource','NumeroAvisPage','EntrepriseID','TitreAvis','TexteAvis','Avantages','Inconvenients','PosteAuteur','LocalisationAuteur','NbAvis'],
}


def valid(value):
    v = str(value or '').strip()
    return v if v.upper() not in NULLS else ''


def normalise(value):
    s = unicodedata.normalize('NFKD', valid(value)).casefold()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('&', ' et ')
    return ' '.join(re.sub('[^a-z0-9]+', ' ', s).split())


def read_csv(path, required):
    if not path.is_file():
        raise FileNotFoundError(f'Fichier absent : {path}')
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';')
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f'Colonnes absentes dans {path}: {set(required)-set(reader.fieldnames or [])}')
        return list(reader)


def write_csv(path, cols, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=cols, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def load_object_rows(tech, desc):
    obj = defaultdict(lambda: {'meta': {}, 'fields': {}})
    for r in tech:
        if r['COLONNE'] in obj[r['OBJET_ID']]['meta']:
            raise ValueError(f"Doublon metadata technique: {r['OBJET_ID']} / {r['COLONNE']}")
        obj[r['OBJET_ID']]['meta'][r['COLONNE']] = r['VALEUR']
    for r in desc:
        if r['COLONNE'] in obj[r['OBJET_ID']]['fields']:
            raise ValueError(f"Doublon metadata descriptive: {r['OBJET_ID']} / {r['COLONNE']}")
        obj[r['OBJET_ID']]['fields'][r['COLONNE']] = r['VALEUR']
    return obj


def build(root):
    metadata = root/'2_CURATED_ZONE'/'METADONNEES'
    links = root/'3_PRODUCTION_ZONE'/'linked_data_phase3'/'correspondances_emp_soc_a_valider.csv'
    output = root/'3_PRODUCTION_ZONE'/'DWH_CSV'
    tech = read_csv(metadata/'metadonnee_technique.csv', ('OBJET_ID','COLONNE','VALEUR'))
    desc = read_csv(metadata/'metadonnee_descriptive.csv', ('OBJET_ID','COLONNE','VALEUR'))
    correspondences = read_csv(links, ('NOM_EMP','METHODE','STATUT_VALIDATION','NOM_SOC_PROPOSE'))
    objects = load_object_rows(tech, desc)
    categories = Counter(v['meta'].get('categorie') for v in objects.values())

    # Les pages SOC et AVI partagent une identité de référence par nom normalisé.
    soc_names = defaultdict(set)
    for item in objects.values():
        if item['meta'].get('categorie') == 'INFO-SOC':
            name = valid(item['fields'].get('nom_entreprise'))
            if name:
                soc_names[normalise(name)].add(name)

    validated = {}
    warnings = []
    for row in correspondences:
        raw = valid(row['NOM_EMP'])
        decision = normalise(row['STATUT_VALIDATION']).replace(' ', '')
        if decision not in {'valide','validee','confirme','confirmee'}:
            continue
        if row['METHODE'] not in {'EXACT','NORMALISE','FUZZY','MANUEL'}:
            warnings.append(('MAPPING_METHODE_NON_SUPPORTEE', raw, row['METHODE']))
            continue
        soc = valid(row['NOM_SOC_PROPOSE'])
        key = normalise(soc)
        if not raw or not soc or key not in soc_names:
            warnings.append(('MAPPING_CIBLE_SOC_ABSENTE',raw,soc))
            continue
        if row['METHODE'] == 'FUZZY':
            # Pour fuzzy, la validation humaine explicite a été inscrite dans la table.
            pass
        emp_key = normalise(raw)
        if emp_key in validated and validated[emp_key] != key:
            raise ValueError(
                f'Mappings contradictoires pour EMP {emp_key}: '
                f'{validated[emp_key]} et {key}'
            )
        # Plusieurs variantes du même nom EMP vers le même SOC sont acceptées.
        validated[emp_key] = key

    # Enterprise keys scope les entités hors SOC, pour éviter les jointures non vérifiées.
    def company_key(category, raw):
        key = normalise(raw)
        if not key:
            return None
        if category == 'INFO-EMP':
            target = validated.get(key)
            return 'SOC:'+target if target else 'EMP:'+key
        if category in ('INFO-SOC','AVIS-SOC'):
            return 'SOC:'+key
        return None

    ent = defaultdict(lambda: {'emp':set(),'soc':set(),'avi':set(),'attrs':{},'notes':set()})
    poste_names, lieu_names = {}, {}
    offers, reviews = [], []
    sorted_objects = sorted(objects.items(),key=lambda x:(int(x[0]) if x[0].isdigit() else 10**12,x[0]))
    for oid, data in sorted_objects:
        cat, f = data['meta'].get('categorie'), data['fields']
        name = valid(f.get('nom_entreprise'))
        ek = company_key(cat, name)
        if cat not in ('INFO-EMP','INFO-SOC','AVIS-SOC'):
            warnings.append(('CATEGORIE_INCONNUE',oid,str(cat)))
            continue
        if not ek:
            raise ValueError(f'Nom entreprise manquant: OBJET_ID {oid}, categorie {cat}')
        typ = {'INFO-EMP':'emp','INFO-SOC':'soc','AVIS-SOC':'avi'}[cat]
        ent[ek][typ].add(name)
        if cat == 'INFO-SOC':
            for col, src in (('VilleEntreprise','ville_entreprise'),('TailleEntreprise','taille_entreprise'),('DescriptionEntreprise','description_entreprise')):
                value = valid(f.get(src))
                if value:
                    old = ent[ek]['attrs'].get(col)
                    if old and old != value:
                        warnings.append(('ATTRIBUT_SOC_MULTIPLE',ek,col))
                    else:
                        ent[ek]['attrs'][col] = value
        if cat == 'AVIS-SOC':
            note = valid(f.get('note_moyenne_entreprise'))
            if note:
                try:
                    n = float(note.replace(',','.'))
                    if not (0<=n<=5): raise ValueError()
                    ent[ek]['notes'].add(n)
                except ValueError:
                    warnings.append(('NOTE_NON_NUMERIQUE',oid,note))
            titles = sorted(int(m.group(1)) for k in f if (m:=REVIEW.fullmatch(k)))
            if not titles:
                warnings.append(('AUCUN_AVIS',oid,name))
            for i in titles:
                prefix=f'avis_{i:03d}_'
                reviews.append({'AvisID':f'{oid}-{i:03d}','ObjetIDSource':oid,'NumeroAvisPage':i,
                                '_ek':ek,'TitreAvis':valid(f.get(prefix+'titre')),
                                'TexteAvis':valid(f.get(prefix+'texte')),
                                'Avantages':valid(f.get(prefix+'avantages')),
                                'Inconvenients':valid(f.get(prefix+'inconvenients')),
                                'PosteAuteur':valid(f.get(prefix+'poste_auteur')),
                                'LocalisationAuteur':valid(f.get(prefix+'localisation_auteur')),
                                'NbAvis':1})
        if cat == 'INFO-EMP':
            poste=valid(f.get('libelle_emploi'))
            lieu=valid(f.get('ville_emploi'))
            if not poste or not lieu:
                raise ValueError(f'Poste ou ville manquant pour OBJET_ID {oid}')
            poste_names.setdefault(normalise(poste),poste)
            lieu_names.setdefault(normalise(lieu),lieu)
            offers.append({'OffreID':len(offers)+1,'ObjetIDSource':oid,'_ek':ek,
                           '_pk':normalise(poste),'_lk':normalise(lieu),
                           'DescriptionOffre':valid(f.get('description_emploi')),'NbOffres':1})

    dim_ent=[]
    enterprise_ids={}
    for eid,key in enumerate(sorted(ent),start=1):
        data=ent[key]
        # Priorité aux noms SOC pour les entreprises rapprochées, sinon EMP, sinon AVI.
        name_candidates=data['soc'] or data['emp'] or data['avi']
        display=sorted(name_candidates,key=lambda x:(x.casefold(),x))[0]
        notes=data['notes']
        if len(notes)>1:
            warnings.append(('NOTES_SOURCES_DIVERGENTES',key,str(sorted(notes))))
        enterprise_ids[key]=eid
        dim_ent.append({'EntrepriseID':eid,'NomEntreprise':display,
                        'CleNormalisee':key.split(':',1)[1],
                        'VilleEntreprise':data['attrs'].get('VilleEntreprise',''),
                        'TailleEntreprise':data['attrs'].get('TailleEntreprise',''),
                        'DescriptionEntreprise':data['attrs'].get('DescriptionEntreprise',''),
                        'NoteMoyenneSource':next(iter(notes)) if len(notes)==1 else ''})
    dim_poste=[{'PosteID':i,'LibellePoste':poste_names[k]} for i,k in enumerate(sorted(poste_names),1)]
    dim_lieu=[{'LieuID':i,'VilleOffre':lieu_names[k]} for i,k in enumerate(sorted(lieu_names),1)]
    pids={normalise(x['LibellePoste']):x['PosteID'] for x in dim_poste}
    lids={normalise(x['VilleOffre']):x['LieuID'] for x in dim_lieu}
    for row in offers:
        row['EntrepriseID']=enterprise_ids[row.pop('_ek')]
        row['PosteID']=pids[row.pop('_pk')]
        row['LieuID']=lids[row.pop('_lk')]
    for row in reviews:
        row['EntrepriseID']=enterprise_ids[row.pop('_ek')]

    # Contrôles d'intégrité BLOQUANTS avant sortie, pour éviter un DWH partiellement faux.
    assert len(offers)==categories['INFO-EMP'], 'Nombre offres != nombre fichiers EMP'
    assert len({x['ObjetIDSource'] for x in offers})==len(offers), 'Offres ID source dupliqués'
    assert len({x['AvisID'] for x in reviews})==len(reviews), 'Avis ID dupliqués'
    assert len(enterprise_ids)==len(dim_ent)
    for row in offers+reviews:
        assert row['EntrepriseID'] in enterprise_ids.values()
    for row in offers:
        assert row['PosteID'] in pids.values() and row['LieuID'] in lids.values()
    assert sum(x['NbOffres'] for x in offers)==len(offers)
    assert sum(x['NbAvis'] for x in reviews)==len(reviews)

    output.mkdir(parents=True,exist_ok=True)
    for name,rows in [('DimEntreprise',dim_ent),('DimPoste',dim_poste),('DimLieu',dim_lieu),('FactOffres',offers),('FactAvis',reviews)]:
        write_csv(output/(name+'.csv'),OUTPUTS[name],rows)
    write_csv(output/'audit_etl.csv',['TYPE','IDENTIFIANT','DETAIL'],[dict(zip(['TYPE','IDENTIFIANT','DETAIL'],x)) for x in sorted(set(warnings))])
    matched_offers=sum(1 for x in offers if next(k for k,v in enterprise_ids.items() if v==x['EntrepriseID']).startswith('SOC:'))
    print('=== PHASE 3.4 — ETL DATA WAREHOUSE ===')
    for n,rows in [('DimEntreprise',dim_ent),('DimPoste',dim_poste),('DimLieu',dim_lieu),('FactOffres',offers),('FactAvis',reviews)]:
        print(f'{n}: {len(rows)} ligne(s)')
    print(f'Correspondances EMP->SOC validees et utilisees : {len(validated)}')
    print(f'Offres rattachees a SOC : {matched_offers}/{len(offers)}')
    print(f'Avertissements non bloquants : {len(set(warnings))}')
    print('Resultats :',output)
    print('CONTROLE: aucune fusion fuzzy ou A_VALIDER automatique.')
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',default=r'C:\TD_DATALAKE\DATALAKE')
    args=p.parse_args()
    try:
        build(Path(args.root))
    except Exception as e:
        print('ECHEC ETL :',e,file=sys.stderr)
        sys.exit(1)
