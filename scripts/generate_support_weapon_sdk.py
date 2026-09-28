"""Publish the reviewed support-weapon graph as a stable read-only SDK contract."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research/support-weapon-runtime-F5FEE03DCFDB.json'
JSON_OUTPUT=ROOT/'sdk/SupportWeaponCapabilities.json'
LUA_OUTPUT=ROOT/'domains/support_weapon_catalog.lua'


def lua(value):
    if isinstance(value,dict):
        return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in sorted(value.items()))+'}'
    if isinstance(value,list):return '{'+','.join(lua(item) for item in value)+'}'
    if isinstance(value,bool):return 'true' if value else 'false'
    if value is None:return 'nil'
    if isinstance(value,(int,float)):return repr(value)
    return json.dumps(str(value),ensure_ascii=False)


def build():
    source=json.loads(SOURCE.read_text())
    weapons={}
    for item in source['weapons']:
        name=item['catalogIdentity']
        weapons[name]={key:item.get(key) for key in (
            'catalogIdentity','slot','sourceSection','weaponType','traits','confidence',
            'identityResolution','identityResolutionBasis','resourceHashes','canonicalResourceHash',
            'weaponComponents','attackGraph','runtimeAttacks','relationships','chargeCadence',
            'ownershipChain','attackOwnerResourceHash','ammoFeedMagazine','backpackDependent',
            'expendable','firingModes','selectableAmmoModes','sharedness','unresolvedLinks',
            'readOnlyResolutionReady','guardedAuthoringReady','authoringReason')}
    return {'schemaVersion':1,'contract':'hd2runtime.support_weapon.read_only.v1',
        'hd2RuntimeVersion':(ROOT/'VERSION').read_text().strip(),
        'gameFingerprints':source['gameFingerprints'],
        'safety':{'writes':0,'protectionChanges':0,'fixtureFallback':'disabled'},
        'summary':source['summary'],'sharedSettingsGroups':source['sharedSettingsGroups'],
        'weapons':weapons}


def outputs():
    value=build()
    return {JSON_OUTPUT:json.dumps(value,indent=2)+'\n',
        LUA_OUTPUT:'-- Generated read-only support-weapon SDK contract; do not edit.\nreturn '+lua(value)+'\n'}


def generate(check=False):
    stale=[]
    for path,body in outputs().items():
        if not path.exists()or path.read_text()!=body:
            stale.append(str(path.relative_to(ROOT)))
            if not check:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,newline='\n')
    if check and stale:raise RuntimeError('Stale support weapon SDK: '+', '.join(stale))
    return stale


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();print(', '.join(generate(args.check))or'up to date')
