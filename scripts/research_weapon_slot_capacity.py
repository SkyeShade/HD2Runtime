"""Run the production snapshot mapper and summarize slot/capacity evidence."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'))
from tools.snapshot_scan import scan_player_weapons
from tools.wiki_player import compact


def summary_values(value):
    keys=('primariesResolvedUnique','secondariesResolvedUnique','totalUniqueResolved',
          'primaryIdentitiesResolved','secondaryIdentitiesResolved','totalIdentitiesResolved',
          'statusCounts')
    return {key:value[key] for key in keys}


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path);parser.add_argument('catalog',type=Path)
    parser.add_argument('baseline_report',type=Path);parser.add_argument('baseline_mapping',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--lua-dll',type=Path)
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    output=args.output_dir/'PlayerWeaponRuntimeMap.json'
    summary_path=args.output_dir/'player_weapon_identity_summary.json'
    output,mapping_path,_=scan_player_weapons(args.snapshot,args.catalog,output,
        lua_dll=args.lua_dll,summary_output=summary_path)
    before=json.loads(args.baseline_report.read_text());after=json.loads(output.read_text())
    baseline_mapping=json.loads(args.baseline_mapping.read_text())
    after_mapping=json.loads(mapping_path.read_text());after_summary=json.loads(summary_path.read_text())
    wiki={item['name']:item for item in compact(args.catalog)['weapons']}
    candidates={item['resourceHash']:item for item in after['runtimeCandidates']}
    anchors={name:item['bestCandidate']['resourceHash'] for name,item in baseline_mapping.items()
             if item['resolution']=='UNIQUE'}

    slot_counts=Counter();slot_mismatches=[];slot_missing=[]
    capacity_counts=Counter();capacity_rows=[]
    for name,resource in sorted(anchors.items()):
        candidate=candidates[resource];resolved=candidate['resolvedFields']
        slot=(resolved.get('weapon_slot')or{}).get('value')
        if slot is None:slot_missing.append(name)
        elif slot==wiki[name]['slot']:slot_counts[slot]+=1
        else:slot_mismatches.append({'name':name,'expected':wiki[name]['slot'],'actual':slot})
        capacity=candidate.get('capacity')or{'status':'UNMAPPED'}
        expected=wiki[name].get('capacity');actual=capacity.get('value')
        result='missing_wiki'if expected is None else'exact'if actual==expected else'unresolved'if actual is None else'mismatch'
        capacity_counts[(capacity['status'],result)]+=1
        capacity_rows.append({'name':name,'resourceHash':resource,'expected':expected,
            'actual':actual,'baseValue':capacity.get('baseValue'),'status':capacity['status'],
            'source':capacity.get('source'),'chambered':capacity.get('chambered'),
            'defaultMagazineCustomization':capacity.get('defaultMagazineCustomization'),
            'result':result})

    all_slots=Counter((item.get('resolvedFields',{}).get('weapon_slot')or{}).get('value','unclassified')
                      for item in after['runtimeCandidates'])
    duplicate_metadata=[]
    for group in after_summary['duplicateIdentityGroups']:
        rows=[]
        for resource in group['resources']:
            candidate=candidates[resource]
            rows.append({'resourceHash':resource,
                'weaponSlot':(candidate['resolvedFields'].get('weapon_slot')or{}).get('value'),
                'capacity':candidate.get('capacity')})
        duplicate_metadata.append({'name':group['name'],'resources':rows})
    result={'schemaVersion':1,'mode':'offline_snapshot_correlation',
        'snapshot':{'path':str(args.snapshot.resolve()),'fingerprints':after['gameFingerprints']},
        'catalog':{'path':str(args.catalog.resolve()),'weapons':after['wikiDataset']['weaponCount']},
        'identityGate':{'source':str(args.baseline_mapping.resolve()),'uniqueAnchors':len(anchors),
            'primaryAnchors':sum(wiki[name]['slot']=='primary'for name in anchors),
            'secondaryAnchors':sum(wiki[name]['slot']=='secondary'for name in anchors)},
        'weaponSlot':{'promoted':True,'structure':'LoadoutPackageComponentData','path':'BundleTag',
            'offset':0,'primitive':'U32 thin hash','encoding':{'0x82C32E74':'primary','0x89747DEC':'secondary'},
            'exactSeparation':sum(slot_counts.values()),'primaryExact':slot_counts['primary'],
            'secondaryExact':slot_counts['secondary'],'mismatches':slot_mismatches,
            'missing':slot_missing,'allRuntimeCandidateClassifications':dict(sorted(all_slots.items())),
            'unlabelledCandidatesUsingKnownTags':all_slots['primary']+all_slots['secondary']-len(anchors),
            'falsePositiveAssessment':'44 tagged candidates are outside the unique-anchor training set; they are not labelled as proven non-player resources, so a false-positive count cannot be asserted',
            'provenance':'schema-labelled BundleTag; structural/correlation-proven slot meaning; pending gameplay/native-consumer confirmation'},
        'capacity':{'promoted':True,'effectiveValueFailClosed':True,
            'paths':[{'structure':'WeaponMagazineComponentData','path':'Capacity','offset':136,'primitive':'U32','transformation':'identity','guard':'no default Magazine customization'},
                     {'structure':'WeaponRoundsComponentData','path':'MagazineCapacity[0]','offset':72,'primitive':'FP32 integral','transformation':'identity'}],
            'customizationGuard':{'structure':'WeaponCustomizationComponentData','path':'DefaultCustomizations[slot=Magazine]','offset':0,'entryStride':8,'entries':10,'unresolvedReason':'attachment AddPath effective capacity is not yet resolved'},
            'chambering':{'magazineOffset':156,'roundsOffset':104,'transformation':'none','reason':'catalog capacity is magazine capacity; chambered is reported separately'},
            'counts':{status+'_'+comparison:count for(status,comparison),count in sorted(capacity_counts.items())},
            'anchors':capacity_rows,
            'duplicateResourceEvidence':duplicate_metadata,
            'provenance':'schema-labelled fields; structural/correlation-proven; pending gameplay/native-consumer confirmation'},
        'implementationFamilyComponents':[
            {'family':'arc','component':'ArcWeaponComponentData','componentIndex':265,'typeHash':'0xB87BA9ED','recordStride':80},
            {'family':'melee','component':'MeleeWeaponComponentData','componentIndex':268,'typeHash':'0xBBA9003F','recordStride':192},
            {'family':'beam','component':'BeamWeaponComponentData','componentIndex':270,'typeHash':'0xF0721C2C','recordStride':120},
            {'family':'spray/flame','component':'SprayWeaponComponentData','componentIndex':315,'typeHash':'0x8E551126','recordStride':224},
            {'family':'shotgun/feed variants','component':'WeaponRoundsComponentData','componentIndex':117,'typeHash':'0x66081072','recordStride':136},
            {'family':'conventional projectile','component':'ProjectileWeaponComponentData','componentIndex':321,'typeHash':'0x45171B68','recordStride':616}],
        'matcherComparison':{'before':summary_values(before['identitySummary']),
            'after':summary_values(after_summary)},
        'duplicateIdentityGroups':after_summary['duplicateIdentityGroups'],
        'runtimeCandidatesMatchingMultipleCatalogWeapons':after_summary['runtimeCandidatesMatchingMultipleCatalogWeapons'],
        'unresolvedCatalogWeapons':after_summary['unresolvedCatalogWeapons'],
        'unresolvedImplementationFamilies':after_summary['unresolvedImplementationFamilies'],
        'regressionAnchors':{name:after_mapping[name] for name in ('JAR-5 Dominator','PLAS-101 Purifier',
            'PLAS-15 Loyalist','PLAS-1 Scorcher','PLAS-39 Accelerator Rifle','AR-23 Liberator',
            'AR-23A Liberator Carbine','AR-23P Liberator Penetrator','SMG-37 Defender','GP-31 Grenade Pistol')},
        'focusFindings':{
            'AR-23P Liberator Penetrator':'slot and capacity evidence reduce five formerly credible resource matches to one exact resource; four remain partial only',
            'SMG-37 Defender':'both resources retain the same base magazine/customization identity; one has a primary BundleTag and the other is unclassified, which is insufficient to choose canonically',
            'GP-31 Grenade Pistol':'both resources resolve capacity 1 through WeaponRounds; one has a secondary BundleTag and the other is unclassified, which is insufficient to choose canonically',
            'Liberator/Carbine/StA-52 partial resources':'four resources still match all three identities; capacity values are absent, customized, or conflicting and do not establish a unique identity'},
        'safety':{'writes':0,'protectionChanges':0,'fixtureFallback':'disabled','gameLaunched':False}}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(output);print(mapping_path);print(summary_path);print(args.report)


if __name__=='__main__':main()
