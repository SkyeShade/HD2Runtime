"""Publish guarded armor perk tuning from the retained passive/consumer research."""
import argparse
import json
from pathlib import Path
from reference_format import lua
from generate_player_passives import build as passives, _utf8

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
 'leg_injury_immunity':'Leg injury immunity (0 / 1)',
 'movement_noise':'Movement noise multiplier', 'enemy_detection_range':'Detection range multiplier',
 'poi_identification_range':'Point of interest identification range multiplier',
 'stamina_when_damaged':'Stamina gained when damaged', 'chest_damage_resistance':'Chest damage multiplier',
 'explosive_resistance':'Explosive damage multiplier', 'fire_resistance':'Fire damage multiplier',
 'arc_resistance':'Arc damage multiplier', 'gas_resistance':'Gas damage multiplier',
 'elemental_resistance':'Elemental damage multiplier', 'impact_resistance':'Impact damage multiplier',
 'limb_injury_avoidance':'Limb injury avoidance value', 'death_explosion':'Death explosion value',
 'lethal_damage_survival':'Lethal damage survival value', 'knock_prone_resistance':'Knockdown multiplier',
 'limb_health':'Limb health multiplier', 'crouch_prone_recoil':'Crouched and prone recoil multiplier',
 'weapon_ergonomics':'Weapon ergonomics bonus', 'throw_range':'Throw range multiplier',
 'grenade_capacity':'Extra grenades', 'stim_capacity':'Extra stims', 'stim_duration':'Extra stim duration',
 'radar_scan_interval':'Marker radar scan interval', 'armor_rating':'Armor rating bonus',
 'melee_damage':'Melee damage multiplier', 'movement_speed':'Jog speed multiplier',
 'unknown_f6d67313':'Sprint speed multiplier', 'unknown_8933e7f4':'Arc status buildup multiplier',
}
STAT_LABELS = {11:'Unmapped stat 11',12:'Ammo capacity',13:'Primary reload speed',14:'Support reload speed',
               15:'Sidearm reload speed',16:'Sidearm draw and holster speed',17:'Sidearm recoil'}

def build():
    base=passives()
    raw=json.loads((ROOT/'research/player-attributes-F5FEE03DCFDB.json').read_text(encoding='utf8'))
    effects=json.loads((ROOT/'research/passive-effects-F5FEE03DCFDB.json').read_text(encoding='utf8'))
    assert not any(effects['pinnedBytesMismatchPerSnapshot'].values())
    pins={p['rva']:p for p in base['pins'] if not p['label'].startswith('writers:')}
    for group,items in effects['pins'].items():
        if group in ('passivePackageLoader','resolveDependencyPackage','tableSources','boosterPackageLoader'):continue
        for p in items:
            pins[p['rva']]={'rva':p['rva'],'hex':p['bytes'],'label':group+': '+p['role'][:80]}
    entries=[]
    for p in base['passives']:
        source=next(s for s in raw['passiveTable'] if s['id']==p['id'])
        e={k:p[k] for k in ('id','name','description','modifiers','stats','armorKits')}
        e.update(icon=source['icon'],nameId=source['nameId'],package=source['package'],fields=[])
        for i,m in enumerate(p['modifiers']):
            # Description-only values are NOT the gameplay stat. Presence/unknown Set rows are not numeric knobs.
            if m['reader'] in ('description-only','none found','no effect'):continue
            if m['type']=='Set'and m['key']!='B62B4AFD':continue
            if m['key']=='54A69284':continue  # death explosion checks presence, never this display duration
            key=m['key_name'];label=LABELS.get(key)
            if not label:continue
            minimum,maximum=0,10
            if key=='leg_injury_immunity':maximum=1
            unit='multiplier' if m['type']=='Multiply' else 'value'
            note='Shared by everyone using this perk. Gameplay effect not yet tested.'
            if key in ('grenade_capacity','stim_capacity'):maximum=20;unit='count'
            if key=='weapon_ergonomics':maximum=200
            if key in ('stim_duration','radar_scan_interval'):maximum=120;unit='seconds'
            if key=='radar_scan_interval':minimum=0.05
            if key=='armor_rating':note='Uses the worn armor kit, not a passive slot override. Re-equip or respawn after editing.'
            if key in ('limb_injury_avoidance','lethal_damage_survival','death_explosion'):
                note='Native perk value, not a percentage. Its gameplay response has not been tested.'
            if key=='unknown_8933e7f4':note='Scales element-2 status buildup; identification as arc is inferred from its consumers.'
            e['fields'].append(dict(semanticFieldId='perk.'+key,label=label,currentDefault=m['value'],
                min=minimum,max=maximum,unit=unit,type='integer' if key=='leg_injury_immunity' else 'number',editable=True,section='Perk bonuses',
                lifecycle=note,backing=dict(kind='armor_perk',part='modifier',index=i,offset=i*16+8,
                    storage='f32',width=4,passive=p['id'])))
        for i,s in enumerate(p['stats']):
            for member,offset in (('add',4),('mul',8)):
                label=STAT_LABELS[s['stat']]
                note='Uses the armor kit worn at spawn. Respawn after applying; passive slot overrides do not select these stats.'
                if s['stat']==11:note='Native stat 11 has a verified reader, but its gameplay meaning is unresolved. Respawn after applying.'
                e['fields'].append(dict(semanticFieldId='perk.stat_'+str(s['stat'])+'.'+member,
                    label=label+(' bonus' if member=='add' else ' multiplier'),currentDefault=s[member],
                    min=0,max=10,type='number',unit='value' if member=='add' else 'multiplier',editable=True,
                    section='Stats applied at spawn',lifecycle=note,
                    backing=dict(kind='armor_perk',part='stat',index=i,offset=i*12+offset,
                        storage='f32',width=4,passive=p['id'])))
        for f in e['fields']:
            f.update(shared=True,acknowledgement='allow_unverified_effect',operationGroup='armor_perk/'+str(p['id']),
                     target=dict(resource='armor_perk',armor_perk=p['id']))
        entries.append(e)
    return dict(gameDllSha256=base['source']['gameDllSha256'],manager=base['manager'],
                entries=entries,pins=sorted(pins.values(),key=lambda p:p['rva']))

def generate(check=False):
    d=build()
    public={'schemaVersion':1,'runtimeVersion':(ROOT/'VERSION').read_text(encoding='utf-8').strip(),'liveTested':False,'perks':[
        {k:v for k,v in e.items() if k not in ('nameId','package','modifiers')} for e in d['entries']]}
    outputs={'domains/armor_perks.lua':'-- Generated by scripts/generate_armor_perks.py.\nreturn '+lua(_utf8(d))+'\n',
             'sdk/ArmorPerkCapabilities.json':json.dumps(public,indent=2,ensure_ascii=False)+'\n'}
    changed=[]
    for name,body in outputs.items():
        p=ROOT/name
        if not p.exists() or p.read_text(encoding='utf8')!=body:
            changed.append(name)
            if not check:p.write_text(body,encoding='utf8')
    return changed

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    changed=generate(a.check);print('\n'.join(changed));raise SystemExit(bool(changed) if a.check else 0)
