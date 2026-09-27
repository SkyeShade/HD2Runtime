"""Generate runtime/authoring views from schemas/sdk.json. No game or Lua needed."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def lua(value):
    if isinstance(value, dict):
        return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in value.items())+'}'
    if isinstance(value, list): return '{'+','.join(map(lua,value))+'}'
    if value is None: return 'nil'
    if isinstance(value, bool): return str(value).lower()
    return json.dumps(value,ensure_ascii=True)


def ident(name): return name.replace('.', '_')


def outputs():
    # Match Git's LF-normalized source on every checkout, including Windows.
    raw=(ROOT/'schemas/sdk.json').read_text(encoding='utf-8').encode('utf-8')
    schema=json.loads(raw)
    player_schema=json.loads((ROOT/'schemas/player_weapon_fields.json').read_text())
    player_capabilities=json.loads((ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
    composition=json.loads((ROOT/'schemas/player_weapon_composition_catalog.json').read_text())
    support=json.loads((ROOT/'sdk/SupportWeaponCapabilities.json').read_text())
    player_aliases={item['alias']:item['canonical'] for item in player_capabilities['semanticAliases']}
    digest=hashlib.sha256(raw).hexdigest()
    types=schema['types']; resources=schema['resources']
    fields={domain:{} for domain in types}
    catalog={}
    for key,r in resources.items():
        catalog[key]={}
        for name,f in r['fields'].items():
            assert f['name']==name and f['domain'] in types
            assert all(e in f['evidence'] for e in schema['evidence_categories'])
            assert not f['evidence']['current_live_ownership_proven'], 'Static schema cannot prove current ownership'
            assert f['value_type'] in ('integer','number') and f['storage'] in ('u32','i32','f32')
            for attribute in ('readable','writable','semantic_range','enum'): assert attribute in f
            constant=ident(name)
            assert fields[f['domain']].get(constant,name)==name, 'Constant collision'
            fields[f['domain']][constant]=name
            catalog[key][name]=f
    player_field_ids=sorted({field['semanticFieldId']
        for weapon in player_capabilities['weapons'] for field in weapon['fields']}|
        {field['id'] for field in player_capabilities['fieldDefinitions']})
    for field_id in player_field_ids:
        domain,name=field_id.split('.',1)
        constant=ident(name)
        if constant in fields.setdefault(domain,{}) and fields[domain][constant]!=field_id:
            constant='player_'+constant
        fields[domain][constant]=field_id
    header='-- Generated from schemas/sdk.json; do not edit. SHA256 '+digest+'\n'
    metadata={'version':schema['runtime_version'],'api_version':schema['api_version'],
              'types':types,'builders':schema['builders'],
              'player_weapon_authoring':player_capabilities['summary'],
              'support_weapon_contract':support['contract'],
              'support_weapon_summary':support['summary'],
              'resources':{k:{n:v for n,v in r.items() if n!='fields'} for k,r in resources.items()}}
    constants={'fields':fields,'enums':{k:v['values'] for k,v in schema['enums'].items()},
               'resources':{k:k for k in resources}}
    stub=['---@meta',
          '-- Generated authoring definitions. Never package or execute this file.',
          '-- Schema SHA256 '+digest,'']
    def alias(name,values):
        stub.append('---@alias '+name+' '+'|'.join(json.dumps(v) for v in sorted(set(values))))
    alias('HD2Resource',list(resources)+[r['resource'] for r in resources.values()])
    alias('HD2PatchField',[schema['contracts']['patch']['field']])
    alias('HD2TransactionField',list(schema['contracts']['transaction']['fields']))
    for name,entries in schema['api']['classes'].items():
        stub.append('\n---@class '+name)
        for field,kind in entries.items(): stub.append('---@field '+field+' '+kind)
    for domain,t in types.items():
        stub+=['','---@class '+t['class'],'---@field resource HD2Resource','---@field path string',
               'local '+t['class']+' = {}']
        for method,target in t['methods'].items():
            supported=[r['label'] for r in resources.values() if domain in r['domains'] and target in r['domains']]
            stub+=['---Available for: '+', '.join(supported)+'.','---@return '+types[target]['class'],
                   'function '+t['class']+':'+method+'() end']
        for method,spec in schema['api']['target_methods'].items():
            stub+=['---'+spec['doc'],'---@return '+spec['returns'],
                   'function '+t['class']+':'+method+'() end']
    attack_roles=sorted({attack['role'] for weapon in composition['weapons'].values()
        for attack in weapon['attacks']})
    alias('HD2AttackRole',attack_roles+['primary','alternate'])
    stub+=['','---@class HD2PlayerAttack','---@field resource "player_weapon"',
        '---@field path "attack"','---@field weapon HD2WeaponName','---@field attack HD2AttackRole',
        'local HD2PlayerAttack = {}','---@return HD2ProjectileReference',
        'function HD2PlayerAttack:projectile() end','---@return table',
        'function HD2PlayerAttack:describe() end','',
        '---@class HD2ProjectileReference','---@field resource "player_weapon"',
        '---@field path "projectile_reference"','---@field weapon HD2WeaponName',
        '---@field attack HD2AttackRole','local HD2ProjectileReference = {}',
        '---@param phase "impact"|"expiry"','---@return HD2TerminalAction',
        'function HD2ProjectileReference:terminal_action(phase) end','---@return table',
        'function HD2ProjectileReference:describe() end','',
        '---@class HD2TerminalAction','---@field resource "player_weapon"',
        '---@field path "terminal_action"','---@field weapon HD2WeaponName',
        '---@field attack HD2AttackRole','---@field phase "impact"|"expiry"',
        'local HD2TerminalAction = {}','---@return table',
        'function HD2TerminalAction:describe() end','---@return HD2Explosion',
        'function HD2TerminalAction:explosion() end','---@return HD2NoExplosion',
        'function HD2TerminalAction:no_explosion() end','',
        '---@class HD2NoExplosion','---@field resource "player_weapon"',
        '---@field path "no_explosion"','---@field weapon HD2WeaponName',
        '---@field attack HD2AttackRole','---@field phase "impact"|"expiry"',
        'local HD2NoExplosion = {}','',
        '---@class HD2Explosion','---@field resource "player_weapon"',
        '---@field path "explosion"','---@field weapon HD2WeaponName',
        '---@field attack HD2AttackRole','---@field phase "impact"|"expiry"',
        'local HD2Explosion = {}','---@return table','function HD2Explosion:describe() end',
        '---@return HD2Explosion','function HD2Explosion:damage() end',
        '---@return table','function HD2Explosion:shrapnel() end','',
        '---@class HD2MagazineOption','---@field resource "player_weapon"',
        '---@field path "magazine_option"','---@field weapon HD2WeaponName',
        '---@field option string','local HD2MagazineOption = {}','---@return table',
        'function HD2MagazineOption:describe() end','',
        '---@class HD2AttachmentOption','---@field resource "player_weapon"',
        '---@field path "attachment_option"','---@field weapon HD2WeaponName',
        '---@field category string','---@field option string','local HD2AttachmentOption = {}',
        '---@return table','function HD2AttachmentOption:describe() end','',
        '---@alias HD2AuthoringTarget HD2Weapon|HD2DamageProfile|HD2Stratagem|HD2PlayerAttack|HD2ProjectileReference|HD2TerminalAction|HD2Explosion','',
        '---@param role HD2AttackRole','---@return HD2PlayerAttack',
        'function HD2Weapon:attack(role) end','---@return HD2PlayerAttack[]',
        'function HD2Weapon:attacks() end','---@return table',
        'function HD2Weapon:fire_modes() end','---@return HD2MagazineOption[]',
        'function HD2Weapon:magazine_options() end','---@return HD2MagazineOption?',
        'function HD2Weapon:default_magazine() end','---@param identity string',
        '---@return HD2MagazineOption','function HD2Weapon:magazine(identity) end',
        '---@param category string','---@return HD2AttachmentOption[]',
        'function HD2Weapon:attachment_options(category) end','---@param category string',
        '---@param identity string','---@return HD2AttachmentOption',
        'function HD2Weapon:attachment(category, identity) end']
    alias('HD2SupportWeaponName',list(support['weapons']))
    support_attack_names=[attack['name'] for weapon in support['weapons'].values()
        for attack in weapon['attackGraph']]
    alias('HD2SupportAttackName',support_attack_names)
    stub+=['','---@class HD2SupportAttack','---@field resource "support_weapon"',
        '---@field path "attack"','---@field weapon HD2SupportWeaponName',
        '---@field attack_index integer','local HD2SupportAttack = {}','---@return table',
        'function HD2SupportAttack:describe() end','',
        '---@class HD2SupportWeapon','---@field resource "support_weapon"',
        '---@field path "weapon"','---@field weapon HD2SupportWeaponName',
        'local HD2SupportWeapon = {}','---@return table',
        'function HD2SupportWeapon:describe() end','---@return HD2SupportAttack[]',
        'function HD2SupportWeapon:attacks() end','---@param identity integer|HD2SupportAttackName',
        '---@return HD2SupportAttack','function HD2SupportWeapon:attack(identity) end']
    for domain,names in fields.items():
        stub+=['','---@class HD2Fields_'+domain]
        for constant,name in names.items():
            relevant=[(r['label'],f) for r in resources.values() for n,f in r['fields'].items() if n==name and f['domain']==domain]
            note='; '.join(label+': '+('reviewed writable' if f['writable'] else 'read-only')+', '+f['value_type'] for label,f in relevant)
            if name in player_aliases:
                note=('Deprecated compatibility alias; use hd2.fields.'
                    +player_aliases[name]+('. '+note if note else '.'))
            stub.append(('---@field '+constant+' '+json.dumps(name)+' '+note).rstrip())
    stub+=['','---@class HD2Fields']
    for domain in fields: stub.append('---@field '+domain+' HD2Fields_'+domain)
    for enum,spec in schema['enums'].items():
        stub+=['','---@class HD2Enum_'+enum]
        for key,value in spec['values'].items(): stub.append('---@field '+key+' '+str(value))
    stub+=['','---@class HD2Enums']
    for enum in schema['enums']: stub.append('---@field '+enum+' HD2Enum_'+enum)
    stub+=['','---@class HD2Resources']
    for key in resources: stub.append('---@field '+key+' '+json.dumps(key))
    stub+=['','---@class HD2Runtime','---@field fields HD2Fields','---@field enums HD2Enums',
           '---@field resources HD2Resources','---@field version string','---@field api_version integer','local hd2 = {}']
    for method,domain in schema['builders'].items():
        names=[n for r in resources.values() if r['kind']==domain for n in r['aliases']]
        if domain=='weapon':names+= [w['name'] for w in player_capabilities['weapons']]
        alias('HD2'+method.title()+'Name',names)
        stub+=['---@param name HD2'+method.title()+'Name','---@return '+types[domain]['class'],
               'function hd2.'+method+'(name) end']
    stub+=['---@param name HD2SupportWeaponName','---@return HD2SupportWeapon',
        'function hd2.support_weapon(name) end']
    for method,spec in schema['api']['functions'].items():
        stub+=['---'+spec['doc']]
        for name,kind in spec['params']:stub.append('---@param '+name+' '+kind)
        stub+=['---@return '+spec['returns'],'function hd2.'+method+'('+','.join(n for n,_ in spec['params'])+') end']
    stub+=['',"if rawget(_G,'CowboyBingusModLoader') then",
           '    error("HD2Runtime SDK stubs are authoring-only; install the runtime package in-game")',
           'end','return hd2','']
    doc=['# Generated HD2Runtime API reference','',schema['evidence_note'],'',
         'Canonical source: `schemas/sdk.json`. Unknown semantic ranges remain unknown. Storage limits are not gameplay ranges.','',
         'Writable means an enabled, reviewed transition for that resource; it does not mean arbitrary values are allowed.','',
         '## Operations','']
    for method,spec in schema['api']['functions'].items():doc+=['- `hd2.'+method+'(...)`: '+spec['doc']]
    for domain,t in types.items():
        doc+=['','## '+t['class'],'']
        for method,to in t['methods'].items():doc+=['- `:'+method+'()` → `'+types[to]['class']+'` (only where mapped).']
        doc+=['- `:describe()` → offline field metadata; `:read_target()` → descriptor for `hd2.read/observe`.']
    for key,r in resources.items():
        doc+=['','## '+r['label'],'',r['resource']+' (`hd2.resources.'+key+'`)','',
              '| Field constant | Domain / value type | Access | Baseline | Evidence | Semantic range | Enum | Source |',
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
        for name,f in r['fields'].items():
            evidence=', '.join(k for k in schema['evidence_categories'] if f['evidence'][k])
            if f['evidence'].get('prior_live_confirmation'):evidence+=', prior live confirmation'
            doc+=['| `hd2.fields.'+f['domain']+'.'+ident(name)+'` | '+types[f['domain']]['name']+' / '+f['value_type']+' | '+('read / reviewed write' if f['writable'] else 'read')+' | '+str(f['expected'])+' | '+evidence+' | '+(json.dumps(f['semantic_range']) if f['semantic_range'] else 'unknown')+' | '+(f['enum'] or 'none')+' | '+f['evidence']['source']+' |']
    doc+=['','## Known enum members','']
    for enum,spec in schema['enums'].items():
        doc+=['- `hd2.enums.'+enum+'`: '+json.dumps(spec['values'])+'; partial catalog, source: '+spec['source']]
    doc+=['','## Reviewed write contracts','', '```json',json.dumps(schema['contracts'],indent=2),'```','']
    return {'domains/catalog.lua':header+'return '+lua(catalog)+'\n',
            'domains/constants.lua':header+'return '+lua(constants)+'\n',
            'domains/metadata.lua':header+'return '+lua(metadata)+'\n',
            'sdk/metadata.json':json.dumps(schema,indent=2)+'\n',
            'sdk/stubs/mods/skyeshade/hd2runtime.lua':'\n'.join(stub),
            'starter/stubs/mods/skyeshade/hd2runtime.lua':'\n'.join(stub),
            'sdk/docs/api.md':'\n'.join(doc),
            'sdk/docs/player-weapon-composition.md':(ROOT/'docs/player-weapon-composition.md').read_text(),
            'sdk/docs/support-weapon-api.md':(ROOT/'docs/support-weapon-api.md').read_text(),
            'sdk/tools/hd2_archive.py':(ROOT/'scripts/hd2_archive.py').read_text()}


def generate(check=False):
    stale=[]
    for name,body in outputs().items():
        path=ROOT/name
        if not path.exists() or path.read_bytes()!=body.encode():
            stale.append(name)
            if not check:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(body.encode())
    if check and stale:raise RuntimeError('Stale generated files: '+', '.join(stale))
    return stale


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    print('Generated metadata: '+(', '.join(generate(args.check)) or 'up to date'))
