"""Correlate simple wiki weapon fields against complete records in an HD2SNAP.

The existing mapper report is the identity gate. Runtime extraction uses the
production SnapshotMemoryReader, discovery, settings, and entity catalog code.
"""
from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'))
from tools.lua_runner import execute
from tools.snapshot_scan import lua,module_sources
from tools.wiki_primary import compact

STRUCTURES={'WeaponDataComponentData':1232,'ProjectileWeaponComponentData':616,
            'ProjectileSettings':272}
PRIMITIVES={
    'u32':lambda body,offset:struct.unpack_from('<I',body,offset)[0],
    'i32':lambda body,offset:struct.unpack_from('<i',body,offset)[0],
    'f32':lambda body,offset:struct.unpack_from('<f',body,offset)[0],
}
FIELD_RULES={
    'fire_rate':{'tolerance':1.0,'transforms':{
        'identity':lambda value:value,
        'per_second_x60':lambda value:value*60,
        'seconds_per_shot_60_div_x':lambda value:60/value if value else None,
        'milliseconds_per_shot_60000_div_x':lambda value:60000/value if value else None,
        'rpm_div_60':lambda value:value/60}},
    'capacity':{'tolerance':0.0,'transforms':{'identity':lambda value:value}},
    'projectile_velocity':{'tolerance':2.0,'transforms':{
        'identity':lambda value:value,'centimeters_to_meters':lambda value:value/100,
        'meters_to_centimeters':lambda value:value*100}},
    'projectile_mass':{'tolerance':0.1,'transforms':{
        'identity':lambda value:value,'kilograms_to_grams':lambda value:value*1000,
        'milligrams_to_grams':lambda value:value/1000}},
    'drag':{'tolerance':0.01,'transforms':{
        'identity':lambda value:value,'percent_to_fraction':lambda value:value/100,
        'fraction_to_percent':lambda value:value*100}},
    'gravity':{'tolerance':0.01,'transforms':{
        'identity':lambda value:value,'percent_to_fraction':lambda value:value/100,
        'fraction_to_percent':lambda value:value*100}},
    'pellet_count':{'tolerance':0.0,'transforms':{'identity':lambda value:value}},
}


def extract_records(snapshot:Path,selected:dict[str,str],lua_dll:Path|None=None):
    sources=module_sources()
    preload='\n'.join('package.preload['+lua(name)+']=function(...) return assert(loadstring('
        +lua(body)+','+lua(name)+'))(...) end' for name,body in sources.items())
    program=preload+'''\nlocal worker=coroutine.create(function()
local profile=require('hd2runtime/schemas/current')
local b=require('hd2runtime/core/bytes')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open('''+lua(str(snapshot.resolve()))+''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local reader=require('hd2runtime/runtime/reader').new(source)
local roots=require('hd2runtime/runtime/discover').locate(source,reader,profile,
 {entity=true,projectile=true,damage=true})
local catalog=require('hd2runtime/core/entity_catalog').capture(reader,roots.entity,profile,
 {'ProjectileWeaponComponentData','WeaponDataComponentData'})
local selected='''+lua(selected)+'''
local out={}
for _,candidate in ipairs(catalog.candidates)do
 local identity=selected[candidate.resourceHash]
 if identity then
  local item={resourceHash=candidate.resourceHash,wikiIdentity=identity,entityRow=candidate.entityRow,
   ownership=candidate.ownership,records={}}
  local weapon_data=catalog.record(candidate,'WeaponDataComponentData')
  item.records.WeaponDataComponentData={length=#weapon_data.bytes,hex=b.hex(weapon_data.bytes)}
  local weapon=catalog.record(candidate,'ProjectileWeaponComponentData')
  item.records.ProjectileWeaponComponentData={length=#weapon.bytes,hex=b.hex(weapon.bytes)}
  local projectile_type=b.u32(weapon.bytes,0)
  local projectile=assert(roots.projectile.records[projectile_type],'selected projectile settings absent')
  item.projectileType=projectile_type
  item.records.ProjectileSettings={length=#projectile.bytes,hex=b.hex(projectile.bytes),
   group=projectile.group,row=projectile.row,recordType=projectile.kind,
   settingsType=projectile.settings_type}
  local damage_type=b.u32(projectile.bytes,60)
  local damage=assert(roots.damage.records[damage_type],'selected damage settings absent')
  item.damageType=damage_type
  item.damageInfo={group=damage.group,row=damage.row,recordType=damage.kind,
   settingsType=damage.settings_type,length=#damage.bytes,hex=b.hex(damage.bytes)}
  out[#out+1]=item
 end
end
assert(#out==''' + str(len(selected)) + ''','identity-gated candidate extraction count changed')
reader.stage='correlation:stable_reread';reader.verify()
local result={metadata=source.metadata,records=out,diagnostics={queries=reader.queries,bytes=reader.bytes}}
source.close()
return require('hd2runtime/primary_mapper/json').encode(result)
end)
local ok,result
repeat ok,result=coroutine.resume(worker);assert(ok,result)until coroutine.status(worker)=='dead'
return result
'''
    return json.loads(execute(program.encode(),lua_dll))


def is_exact(actual,expected):
    if isinstance(actual,int)and isinstance(expected,int):return actual==expected
    return abs(actual-expected)<=1e-7*max(1,abs(expected))


def classify(actual,expected,tolerance):
    if is_exact(actual,expected):return'exact'
    if abs(actual-expected)<=tolerance:return'tolerant'
    return'mismatch'


def evaluate(field,structure,offset,primitive,transform_name,transform,by_identity,wiki_by,
             include_comparisons=False):
    tolerance=FIELD_RULES[field]['tolerance']
    counts={'exact_matches':0,'tolerant_matches':0,'mismatches':0,'missing_comparisons':0,
            'candidate_exact_matches':0,'candidate_tolerant_matches':0,
            'candidate_mismatches':0,'candidate_missing_comparisons':0,
            'identities_with_any_matching_variant':0}
    comparisons=[]
    for identity,items in sorted(by_identity.items()):
        expected=wiki_by[identity].get(field)
        if not isinstance(expected,(int,float)):
            counts['missing_comparisons']+=1
            counts['candidate_missing_comparisons']+=len(items)
            continue
        values=[];results=[]
        for item in items:
            entry=item['records'].get(structure)
            if not entry:
                results.append('missing');continue
            value=PRIMITIVES[primitive](bytes.fromhex(entry['hex']),offset)
            if primitive=='f32'and not math.isfinite(value):
                results.append('missing');continue
            try:value=transform(value)
            except (ArithmeticError,OverflowError):value=None
            if value is None or not math.isfinite(value)or abs(value)>1e12:
                results.append('missing');continue
            values.append(value);results.append(classify(value,expected,tolerance))
        for result in results:
            counts['candidate_'+({'exact':'exact_matches','tolerant':'tolerant_matches',
                'mismatch':'mismatches','missing':'missing_comparisons'}[result])]+=1
        matches=[result in('exact','tolerant')for result in results]
        if any(matches):counts['identities_with_any_matching_variant']+=1
        if results and all(result=='exact'for result in results):aggregate='exact';counts['exact_matches']+=1
        elif results and all(result in('exact','tolerant')for result in results):
            aggregate='tolerant';counts['tolerant_matches']+=1
        elif not results or all(result=='missing'for result in results):
            aggregate='missing';counts['missing_comparisons']+=1
        else:aggregate='mismatch';counts['mismatches']+=1
        if include_comparisons:
            comparisons.append({'identity':identity,'expected':expected,'actual':values,
                'variant_results':results,'aggregate_result':aggregate})
    result={'structure':structure,'offset':offset,'primitive_type':primitive,
        'transformation':transform_name,**counts}
    result['matches']=counts['exact_matches']+counts['tolerant_matches']
    result['comparison_count']=result['matches']+counts['mismatches']
    if include_comparisons:result['comparisons']=comparisons
    return result


def correlation_key(result):
    primitive_rank={'f32':0,'u32':1,'i32':2}
    return(-result['matches'],result['mismatches'],
        -result['identities_with_any_matching_variant'],result['missing_comparisons'],
        result['structure'],result['offset'],primitive_rank[result['primitive_type']],result['transformation'])


def accepted(field,best,present):
    physical=(best['structure'],best['offset'],best['primitive_type'],best['transformation'])
    expected={
        'fire_rate':('ProjectileWeaponComponentData',8,'f32','identity'),
        'projectile_velocity':('ProjectileSettings',32,'f32','identity'),
        'projectile_mass':('ProjectileSettings',36,'f32','identity'),
        'drag':('ProjectileSettings',40,'f32','identity'),
        'gravity':('ProjectileSettings',44,'f32','identity'),
        'pellet_count':('ProjectileSettings',28,'u32','identity'),
    }.get(field)
    if physical!=expected:return False
    if field=='fire_rate':return best['identities_with_any_matching_variant']==present and best['candidate_exact_matches']>=40
    if field=='pellet_count':return present>=5 and best['matches']==present and best['mismatches']==0
    return present>=20 and best['matches']>=present-1 and best['mismatches']<=1


def aligned_differences(items,structure):
    bodies=[bytes.fromhex(item['records'][structure]['hex'])for item in items]
    offsets=[]
    for offset in range(0,len(bodies[0]),4):
        values={body[offset:offset+4].hex()for body in bodies}
        if len(values)>1:offsets.append({'offset':offset,'raw_values':sorted(values)})
    return offsets


def record_summary(item):
    result={}
    for structure,record in item['records'].items():
        body=bytes.fromhex(record['hex'])
        result[structure]={'length':len(body),'sha256':hashlib.sha256(body).hexdigest().upper()}
        for key in('group','row','recordType','settingsType'):
            if key in record:result[structure][key]=record[key]
    body=bytes.fromhex(item['damageInfo']['hex'])
    result['DamageInfo']={'length':len(body),'sha256':hashlib.sha256(body).hexdigest().upper(),
        **{key:item['damageInfo'][key]for key in('group','row','recordType','settingsType')}}
    return result


def mapper_summary(report):
    states=('EXACT','STRONG','AMBIGUOUS','UNMATCHED')
    counts={state:sum(candidate['status']==state for candidate in report['runtimeCandidates'])for state in states}
    identities=defaultdict(list)
    for candidate in report['runtimeCandidates']:
        if candidate['status']in('EXACT','STRONG'):
            identities[candidate['rankedWikiMatches'][0]['name']].append(candidate['resourceHash'])
    return {'status_counts':counts,'resolved_unique_wiki_identities':len(identities),
        'resolved_identities':{name:resources for name,resources in sorted(identities.items())},
        'duplicate_identity_groups':{name:resources for name,resources in sorted(identities.items())if len(resources)>1}}


def mapper_comparison(before,after):
    before_summary,after_summary=mapper_summary(before),mapper_summary(after)
    old={candidate['resourceHash']:candidate for candidate in before['runtimeCandidates']}
    transitions=[]
    for candidate in after['runtimeCandidates']:
        previous=old[candidate['resourceHash']]
        if previous['status']!=candidate['status']or previous['rankedWikiMatches'][0]['name']!=candidate['rankedWikiMatches'][0]['name']:
            transitions.append({'resource_hash':candidate['resourceHash'],'before_status':previous['status'],
                'after_status':candidate['status'],'before_top_identity':previous['rankedWikiMatches'][0]['name'],
                'after_top_identity':candidate['rankedWikiMatches'][0]['name']})
    before_names=set(before_summary['resolved_identities']);after_names=set(after_summary['resolved_identities'])
    return {'before':before_summary,'after':after_summary,
        'newly_resolved_identities':sorted(after_names-before_names),
        'no_longer_resolved_identities':sorted(before_names-after_names),
        'candidate_transitions':transitions}


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path);parser.add_argument('wiki',type=Path)
    parser.add_argument('baseline',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--raw-records',type=Path);parser.add_argument('--lua-dll',type=Path)
    parser.add_argument('--after-report',type=Path,
        help='Optional mapper output after promoted fields, for deterministic before/after metrics')
    args=parser.parse_args()
    baseline=json.loads(args.baseline.read_text())
    exact_candidates=[candidate for candidate in baseline['runtimeCandidates']if candidate['status']=='EXACT']
    selected={candidate['resourceHash']:candidate['rankedWikiMatches'][0]['name']for candidate in exact_candidates}
    extraction=extract_records(args.snapshot,selected,args.lua_dll)
    records=extraction['records']
    if args.raw_records:args.raw_records.write_text(json.dumps(extraction,indent=2)+'\n')
    dataset=compact(args.wiki)
    wiki_by={weapon['name']:weapon['primary']for weapon in dataset['weapons']}
    by_identity=defaultdict(list)
    for record in records:by_identity[record['wikiIdentity']].append(record)
    report={'schema_version':1,'mode':'offline_snapshot_correlation','snapshot':{
        'path':str(args.snapshot.resolve()),'format_version':extraction['metadata']['format_version'],
        'captured_at':extraction['metadata']['captured_at'],
        'hd2runtime_version':extraction['metadata']['hd2runtime_version'],
        'executable_sha256':extraction['metadata']['executable_sha256'],
        'game_dll_sha256':extraction['metadata']['game_dll_sha256']},
        'wiki':{'path':str(args.wiki.resolve()),'weapon_count':dataset['weapon_count'],
            'source_sha256':dataset['source_sha256']},
        'identity_gate':{'source_report':str(args.baseline.resolve()),
            'exact_runtime_candidates':len(records),'unique_wiki_identities':len(by_identity),
            'rule':'Only pre-existing EXACT mapper results; duplicate identities are never collapsed to an arbitrary resource.'},
        'extraction':{'structures':STRUCTURES,'queries':extraction['diagnostics']['queries'],
            'bytes_read':extraction['diagnostics']['bytes'],'writes':0,'protection_changes':0},
        'fields':{},'duplicate_identity_groups':{}}
    accepted_candidates={}
    for field,spec in FIELD_RULES.items():
        candidates=[]
        for structure,length in STRUCTURES.items():
            for offset in range(0,length,4):
                for primitive in PRIMITIVES:
                    for transform_name,transform in spec['transforms'].items():
                        candidates.append(evaluate(field,structure,offset,primitive,transform_name,
                            transform,by_identity,wiki_by))
        candidates.sort(key=correlation_key);summary=candidates[0]
        transform=spec['transforms'][summary['transformation']]
        best=evaluate(field,summary['structure'],summary['offset'],summary['primitive_type'],
            summary['transformation'],transform,by_identity,wiki_by,True)
        present=sum(isinstance(wiki_by[name].get(field),(int,float))for name in by_identity)
        promote=accepted(field,best,present)
        minimum_candidate_matches=max(3,math.ceil(present*0.5))
        plausible=[candidate for candidate in candidates
            if candidate['matches']>=minimum_candidate_matches]
        reason=('Unique aligned correlation with adequate independent identity coverage; pending gameplay confirmation.'
            if promote else 'No compelling aligned scalar correlation in the reviewed structures.')
        if promote:accepted_candidates[field]=best
        report['fields'][field]={'wiki_values_present':present,
            'tolerance':spec['tolerance'],'evaluated_candidate_count':len(candidates),
            'best_candidate':best,'competing_offsets':candidates[1:16],
            'candidate_offset_minimum_matches':minimum_candidate_matches,
            'candidate_offsets':plausible,'promoted':promote,
            'provenance':'structural/correlation-proven; pending gameplay confirmation'if promote else'not mapped',
            'confidence_evidence':reason}
    for identity,items in sorted(by_identity.items()):
        if len(items)<2:continue
        group={'wiki_expected':{field:wiki_by[identity].get(field)for field in FIELD_RULES},
            'resources':[],'structures':{},'shared_damage_type':len({item['damageType']for item in items})==1,
            'shared_projectile_type':len({item['projectileType']for item in items})==1}
        for structure in STRUCTURES:
            group['structures'][structure]={'record_variant_count':len({item['records'][structure]['hex']for item in items}),
                'differing_aligned_offsets':aligned_differences(items,structure)}
        for item in items:
            values={}
            matches={}
            for field,candidate in accepted_candidates.items():
                body=bytes.fromhex(item['records'][candidate['structure']]['hex'])
                raw=PRIMITIVES[candidate['primitive_type']](body,candidate['offset'])
                value=FIELD_RULES[field]['transforms'][candidate['transformation']](raw)
                values[field]=value
                expected=wiki_by[identity].get(field)
                matches[field]=None if not isinstance(expected,(int,float))else classify(
                    value,expected,FIELD_RULES[field]['tolerance'])in('exact','tolerant')
            group['resources'].append({'resource_hash':item['resourceHash'],'entity_row':item['entityRow'],
                'ownership':item['ownership'],'projectile_type':item['projectileType'],
                'damage_type':item['damageType'],'records':record_summary(item),
                'correlated_values':values,'wiki_matches':matches,
                'matches_all_available_promoted_fields':all(value is not False for value in matches.values())})
        matching=[item['resource_hash']for item in group['resources']if item['matches_all_available_promoted_fields']]
        group['resources_matching_all_available_promoted_fields']=matching
        group['distinguished_to_unique_resource']=len(matching)==1
        report['duplicate_identity_groups'][identity]=group
    if args.after_report:
        report['mapper_comparison']=mapper_comparison(baseline,json.loads(args.after_report.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(args.output)


if __name__=='__main__':main()
