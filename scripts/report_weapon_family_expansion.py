"""Summarize the build-bound offline firing-family expansion results."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import json

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_BASELINE=ROOT/'build/snapshot-results-slot-capacity'
DEFAULT_FINAL=ROOT/'build/snapshot-results-firing-families'


def load(path):
    return json.loads(Path(path).read_text())


def identified(entry):
    return entry['resolution'] in {'UNIQUE','DUPLICATE'}


def metrics(summary):
    return {key:summary[key] for key in ('totalIdentitiesResolved','totalUniqueResolved',
        'primariesResolvedUnique','secondariesResolvedUnique','statusCounts')}


def projectile_key(attack):
    record=attack.get('projectileSettings')
    if not record:return None
    return f"{record['settingsType']}:{record['group']}:{record['row']}:{record['recordType']}"


def weapon_values(candidate):
    names=('fire_rate','capacity','crosshair_type','ergonomics','sway',
        'spread_horizontal','spread_vertical','primary_fire_mode')
    return {name:candidate['resolvedFields'][name]['value'] for name in names
        if name in candidate['resolvedFields']}


def compose(baseline_folder=DEFAULT_BASELINE,final_folder=DEFAULT_FINAL):
    baseline_folder=Path(baseline_folder);final_folder=Path(final_folder)
    baseline_summary=load(baseline_folder/'player_weapon_identity_summary.json')
    baseline_map=load(baseline_folder/'PlayerWeaponRuntimeMap.identity-candidates.json')
    final_report=load(final_folder/'PlayerWeaponRuntimeMap.json')
    final_summary=load(final_folder/'player_weapon_identity_summary.json')
    final_map=load(final_folder/'PlayerWeaponRuntimeMap.identity-candidates.json')
    gained=sorted(name for name,entry in final_map.items()
        if identified(entry) and not identified(baseline_map[name]))
    family_names={name:[] for name in ('ArcWeaponComponentData','BeamWeaponComponentData',
        'SprayWeaponComponentData','MeleeWeaponComponentData','WeaponRoundsComponentData',
        'WeaponDataComponentData')}
    component_for_family={'arc':'ArcWeaponComponentData','beam':'BeamWeaponComponentData',
        'spray_flame':'SprayWeaponComponentData','melee':'MeleeWeaponComponentData',
        'rounds_feed':'WeaponRoundsComponentData'}
    for name in gained:
        best=final_map[name].get('bestCandidate')or{}
        assigned=False
        for family in best.get('implementationFamilies')or[]:
            component=component_for_family.get(family)
            if component:
                family_names[component].append(name);assigned=True
        if not assigned:family_names['WeaponDataComponentData'].append(name)
    groups=defaultdict(list)
    for candidate in final_report['runtimeCandidates']:
        if candidate['status'] not in {'EXACT','STRONG','AMBIGUOUS'}:continue
        for attack in candidate.get('attacks')or[]:
            key=projectile_key(attack)
            if key:groups[key].append(candidate)
    shared=[]
    for key,candidates in sorted(groups.items()):
        unique={c['resourceHash']:c for c in candidates}
        if len(unique)<2:continue
        identities=sorted({name for c in unique.values() for name in c.get('credibleWikiIdentities')or[]})
        resources=[]
        for candidate in sorted(unique.values(),key=lambda value:value['resourceHash']):
            component_records={name:{'recordIndex':value.get('recordIndex'),
                'uniqueOwner':value.get('uniqueOwner')} for name,value in candidate['ownership'].items()
                if name in {'WeaponDataComponentData','ProjectileWeaponComponentData',
                    'WeaponRoundsComponentData','WeaponCustomizationComponentData'}}
            resources.append({'resourceHash':candidate['resourceHash'],
                'entityRow':candidate['entityRow'],'status':candidate['status'],
                'catalogIdentities':candidate.get('credibleWikiIdentities')or[],
                'weaponData':candidate.get('weaponData'),
                'componentRecordIdentities':component_records,
                'weaponLevelFields':weapon_values(candidate)})
        ambiguous=any(final_map[name]['resolution']!='UNIQUE' for name in identities)
        shared.append({'projectileSettingsIdentity':key,'resourceCount':len(resources),
            'catalogIdentities':identities,'resources':resources,
            'distinctWeaponDataRecords':len({(r.get('weaponData')or{}).get('recordIndex') for r in resources}),
            'ambiguousAtWeaponLevel':ambiguous})
    anchors={}
    for name in ('JAR-5 Dominator','PLAS-101 Purifier','PLAS-15 Loyalist','PLAS-1 Scorcher',
            'PLAS-39 Accelerator Rifle','AR-23 Liberator','AR-23A Liberator Carbine'):
        entry=final_map[name];best=entry.get('bestCandidate')or{}
        anchors[name]={'resolution':entry['resolution'],'status':entry['status'],
            'resourceHash':best.get('resourceHash')}
    return {'schema_version':1,'mode':'offline_snapshot_family_expansion',
        'snapshot':{'executable_sha256':final_report['gameFingerprints']['exe'],
            'game_dll_sha256':final_report['gameFingerprints']['dll']},
        'catalogWeapons':final_report['wikiDataset']['weaponCount'],
        'safety':{'writes':final_report['writes'],'protectionChanges':final_report['protectionChanges'],
            'fixtureFallback':final_report['fixtureFallback'],'mode':final_report['mode']},
        'baseline':metrics(baseline_summary),'final':metrics(final_summary),
        'resolutionGains':{component:sorted(names) for component,names in family_names.items()},
        'newlyResolvedIdentities':gained,
        'regressionAnchors':anchors,
        'remainingUnresolvedWeapons':[item['name'] for item in final_summary['unresolvedCatalogWeapons']],
        'duplicateIdentityGroups':final_summary['duplicateIdentityGroups'],
        'sharedProjectileGroups':shared,
        'components':{
            'ArcWeaponComponentData':{'typeOffset':0,'fireRateOffset':4,
                'settings':'ArcSettings','damageInfoTypeOffset':36},
            'BeamWeaponComponentData':{'typeOffset':0,'settings':'BeamSettings',
                'damageInfoTypeOffset':12},
            'SprayWeaponComponentData':{'damageInfoTypeOffset':200},
            'MeleeWeaponComponentData':{'damageInfoTypeOffset':12},
            'WeaponRoundsComponentData':{'primaryProjectileTypeOffset':64,
                'alternateProjectileTypeOffset':68},
            'WeaponDataComponentData':{'spreadOffsets':[84,88],'swayOffset':104,
                'primaryFireModeOffset':144,'ergonomicsOffset':356,
                'identityRoot':'record ownership plus weapon-level fields'}},
        'provenance':'schema-labelled structural evidence pending gameplay/native-consumer confirmation'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,default=DEFAULT_BASELINE)
    parser.add_argument('--final',type=Path,default=DEFAULT_FINAL)
    parser.add_argument('--output',type=Path,
        default=ROOT/'research/weapon-family-expansion-F5FEE03DCFDB.json')
    args=parser.parse_args();report=compose(args.baseline,args.final)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(args.output)


if __name__=='__main__':main()
