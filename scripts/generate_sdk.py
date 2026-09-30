"""Generate runtime/authoring views from schemas/sdk.json. No game or Lua needed."""
import argparse
import hashlib
import json
import re
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


# Typed replacements for legacy fixed-resource constants, named in the stub notes.
LEGACY_TYPED={'armor_penetration':'hd2.fields.damage.ap_direct/ap_slight/ap_large/ap_extreme on '
    'weapon:attack(role):projectile()','standard_damage':'hd2.fields.damage.player_standard_damage',
    'durable_damage':'hd2.fields.damage.player_durable_damage'}


def outputs():
    # Match Git's LF-normalized source on every checkout, including Windows.
    raw=(ROOT/'schemas/sdk.json').read_text(encoding='utf-8').encode('utf-8')
    schema=json.loads(raw)
    player_schema=json.loads((ROOT/'schemas/player_weapon_fields.json').read_text())
    player_capabilities=json.loads((ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
    composition=json.loads((ROOT/'schemas/player_weapon_composition_catalog.json').read_text())
    support=json.loads((ROOT/'sdk/SupportWeaponCapabilities.json').read_text())
    support_authoring=json.loads((ROOT/'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
    stratagem_authoring=json.loads((ROOT/'sdk/StratagemAuthoringCapabilities.json').read_text())
    stratagem_fields=json.loads((ROOT/'schemas/stratagem_fields.json').read_text())
    entity_fields=json.loads((ROOT/'schemas/entity_fields.json').read_text())
    vehicle_authoring=json.loads((ROOT/'sdk/VehicleAuthoringCapabilities.json').read_text())
    backpack_authoring=json.loads((ROOT/'sdk/BackpackAuthoringCapabilities.json').read_text())
    booster_authoring=json.loads((ROOT/'sdk/BoosterAuthoringCapabilities.json').read_text())
    throwable_authoring=json.loads((ROOT/'sdk/ThrowableAuthoringCapabilities.json').read_text())
    enemy_authoring=json.loads((ROOT/'sdk/EnemyAuthoringCapabilities.json').read_text())
    attack_outputs=json.loads((ROOT/'sdk/AttackOutputCapabilities.json').read_text())
    asset_dependencies=json.loads((ROOT/'sdk/AssetDependencyCapabilities.json').read_text())
    weapon_movement=json.loads((ROOT/'sdk/WeaponMovementCapabilities.json').read_text())
    attachment_authoring=json.loads((ROOT/'sdk/MagazineAttachmentCapabilities.json').read_text())
    composition_plan=json.loads((ROOT/'schemas/composition_plan.json').read_text())
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
    # Status slot IDs that only support or mounted weapons carry (e.g. explosion.damage.status_1_type).
    for field_id in sorted({field['semanticFieldId'] for field in support_authoring['fieldInstances']}):
        domain,name=field_id.split('.',1)
        if re.search(r'status_\d+_(type|strength)$',name) and field_id not in fields.setdefault(domain,{}).values():
            fields[domain].setdefault(ident(name),field_id)
    for definition in stratagem_fields['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        constant=ident(name)
        if constant in fields.setdefault(domain,{}) and fields[domain][constant]!=field_id:
            constant='definition_'+constant
        fields[domain][constant]=field_id
    for definition in entity_fields['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        constant=ident(name)
        if constant in fields.setdefault(domain,{}) and fields[domain][constant]!=field_id:
            constant='entity_'+constant
        fields[domain][constant]=field_id
    for definition in json.loads((ROOT/'schemas/attachment_fields.json').read_text())['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        constant=ident(name)
        if constant in fields.setdefault(domain,{}) and fields[domain][constant]!=field_id:
            constant='attachment_'+constant
        fields[domain][constant]=field_id
    for definition in json.loads((ROOT/'schemas/payload_fields.json').read_text())['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        fields.setdefault(domain,{})[ident(name)]=field_id
    for definition in json.loads((ROOT/'schemas/booster_fields.json').read_text())['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        if field_id in fields.setdefault(domain,{}).values():continue
        constant=ident(name)
        if constant in fields.setdefault(domain,{}) and fields[domain][constant]!=field_id:
            constant='booster_'+constant
        fields[domain][constant]=field_id
    for definition in json.loads((ROOT/'schemas/enemy_fields.json').read_text())['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        if field_id in fields.setdefault(domain,{}).values():continue
        fields[domain].setdefault(ident(name),field_id)
    for definition in json.loads((ROOT/'schemas/throwable_fields.json').read_text())['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        if field_id in fields.setdefault(domain,{}).values():continue
        constant=ident(name)
        if constant in fields[domain] and fields[domain][constant]!=field_id:
            constant='throwable_'+constant
        fields[domain][constant]=field_id
    # Weapon-function mode presentation of attack outputs (domains/output_writes.lua).
    for definition in json.loads((ROOT/'schemas/output_fields.json').read_text())['fields']:
        field_id=definition['id'];domain,name=field_id.split('.',1)
        fields.setdefault(domain,{})[ident(name)]=field_id
    # A weapon's default ammunition projectile (domains/attack_outputs.lua `ammunition`).
    if attack_outputs['ammunitionSources']:
        fields.setdefault('ammunition',{})['projectile']='ammunition.projectile'
    header='-- Generated from schemas/sdk.json; do not edit. SHA256 '+digest+'\n'
    metadata={'version':schema['runtime_version'],'api_version':schema['api_version'],
              'types':types,'builders':schema['builders'],
              'player_weapon_authoring':player_capabilities['summary'],
              'support_weapon_contract':support_authoring['contract'],
              'support_weapon_schema_version':support_authoring['schemaVersion'],
              'support_weapon_instance_collection':'fieldInstances',
              'support_weapon_summary':support_authoring['summary'],
              'stratagem_authoring_contract':stratagem_authoring['contract'],
              'stratagem_authoring_summary':stratagem_authoring['summary'],
              'vehicle_authoring_contract':vehicle_authoring['contract'],
              'vehicle_authoring_summary':vehicle_authoring['summary'],
              'backpack_authoring_contract':backpack_authoring['contract'],
              'backpack_authoring_summary':backpack_authoring['summary'],
              'booster_authoring_contract':booster_authoring['contract'],
              'booster_authoring_summary':booster_authoring['summary'],
              'throwable_authoring_contract':throwable_authoring['contract'],
              'throwable_authoring_summary':throwable_authoring['summary'],
              'asset_dependencies_contract':asset_dependencies['contract'],
              'asset_dependencies_summary':asset_dependencies['summary'],
              'weapon_movement_contract':weapon_movement['contract'],
              'weapon_movement_summary':weapon_movement['summary'],
              'magazine_attachment_contract':attachment_authoring['contract'],
              'magazine_attachment_summary':attachment_authoring['summary'],
              'support_weapon_inspection_contract':support['contract'],
              'composition_plan_contract':composition_plan,
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
    acknowledgements=['---@field allow_unverified_effect? boolean Required only where the capability '
            'catalog names it (magazine attachments).',
        '---@field allow_unverified_reference? boolean Required only where the capability catalog '
            'names it (vehicle mount swaps).']
    for name,entries in schema['api']['classes'].items():
        stub.append('\n---@class '+name)
        for field,kind in entries.items(): stub.append('---@field '+field+' '+kind)
        if name in ('HD2PatchRequest','HD2TransactionRequest','HD2PlanOperation'):stub+=acknowledgements
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
        'function HD2PlayerAttack:describe() end',
        '---The output this attack emits, by native family (see sdk/AttackOutputCapabilities.json).',
        '---@return HD2AttackOutput','function HD2PlayerAttack:output() end',
        '---Where this attack\'s fired projectile lives: status (ACTIVE_DIRECT, INDIRECT, AMBIGUOUS, BLOCKED),',
        '---mechanism, reason and, when writable, the target, field and expect handle that change it.',
        '---@return HD2ProjectileSource','function HD2PlayerAttack:projectile_source() end','',
        '---@class HD2ProjectileSource','---@field weapon HD2WeaponName','---@field attack HD2AttackRole',
        '---@field status "ACTIVE_DIRECT"|"INDIRECT"|"DORMANT_OR_METADATA"|"AMBIGUOUS"|"BLOCKED"',
        '---@field mechanism "component"|"ammunition"|nil','---@field member string','---@field reason string',
        '---@field writable boolean True only where changing field on target changes the fired projectile.',
        '---@field target HD2PlayerAttack|HD2WeaponAmmunition|nil','---@field field string|nil',
        '---@field expect HD2ProjectileReference|HD2AmmunitionProjectile|nil','---@field acknowledgements string[]|nil',
        'local HD2ProjectileSource = {}','',
        '---@class HD2WeaponAmmunition','---@field resource "player_weapon"','---@field path "ammunition"',
        '---@field weapon HD2WeaponName','local HD2WeaponAmmunition = {}',
        '---The ammunition projectile handle: the expect of hd2.fields.ammunition.projectile, and the value that',
        '---restores the reviewed ammunition projectile.',
        '---@return HD2AmmunitionProjectile','function HD2WeaponAmmunition:projectile() end',
        '---@return table','function HD2WeaponAmmunition:describe() end','',
        '---@class HD2AmmunitionProjectile','---@field resource "player_weapon"',
        '---@field path "ammunition_projectile"','---@field weapon HD2WeaponName',
        'local HD2AmmunitionProjectile = {}','---@return table','function HD2AmmunitionProjectile:describe() end','',
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
        '---@alias HD2AuthoringTarget HD2Weapon|HD2DamageProfile|HD2Stratagem|HD2StratagemAttack|HD2EagleRearm|HD2PlayerAttack|HD2WeaponAmmunition|HD2ProjectileReference|HD2TerminalAction|HD2Explosion|HD2SupportWeapon|HD2SupportAttack|HD2SupportProjectile|HD2SupportExplosion|HD2DeployedEntity|HD2DeployedShield|HD2DeployedZone|HD2MountedWeapon|HD2VehicleEntity|HD2VehicleZone|HD2VehicleMount|HD2VehicleWeapon|HD2VehicleWeaponAttack|HD2Backpack|HD2BackpackZone|HD2BackpackLinked|HD2BackpackLinkedZone|HD2BoosterTarget|HD2WeaponAttachment|HD2PodRack|HD2PodSlot','',
        '---@param role HD2AttackRole','---@return HD2PlayerAttack',
        'function HD2Weapon:attack(role) end',
        '---The default ammunition that owns this weapon\'s fired projectile (its delta patches ProjectileWeapon +0',
        '---when the weapon is built). Only weapons whose projectile_source() is INDIRECT; write it with',
        '---hd2.fields.ammunition.projectile, allow_shared=true and allow_unverified_effect=true.',
        '---@return HD2WeaponAmmunition','function HD2Weapon:ammunition() end',
        '---@param role? HD2AttackRole Defaults to "primary".',
        '---@return HD2ProjectileSource','function HD2Weapon:projectile_source(role) end','---@return HD2PlayerAttack[]',
        'function HD2Weapon:attacks() end','---@return table',
        'function HD2Weapon:fire_modes() end','---@return HD2MagazineOption[]',
        'function HD2Weapon:magazine_options() end','---@return HD2MagazineOption?',
        'function HD2Weapon:default_magazine() end','---@param identity string',
        '---@return HD2MagazineOption','function HD2Weapon:magazine(identity) end',
        '---@param category string','---@return HD2AttachmentOption[]',
        'function HD2Weapon:attachment_options(category) end','---@param category string',
        '---@param identity string','---@return HD2AttachmentOption',
        'function HD2Weapon:attachment(category, identity) end',
        '','---@class HD2FireRateMode','---@field slot "x"|"y"|"z" The native slot',
        '---@field index integer Storage position (x = 1, y = 2, z = 3): the position in hd2.fields.fire_rate.modes',
        '---@field rpm number 0 = no mode in this slot','---@field enabled boolean rpm is not 0',
        '---@field default boolean The Y slot: the rate a weapon is built on (weapon.fire_rate)',
        '---@field menu integer? Position in the weapon menu (filled slots, X, Y, Z order)',
        '---@field presses integer? Selector presses from the default (0 = the default)','',
        '---@class HD2FireRateModes','---@field weapon string',
        '---@field state "selectable"|"addable"|"single_rate"|"blocked"|"absent"',
        '---@field modes HD2FireRateMode[] The filled slots in weapon-menu order (X, Y, Z)',
        '---@field slots HD2FireRateMode[] All three slots in storage order','---@field default HD2FireRateMode The Y slot',
        '---@field selectorOrder string[] The filled slots in the order the selector visits them (from y)',
        '---@field maxModes integer At most 3: the native storage',
        '---@field expect number[] {X, Y, Z}: the expect of hd2.fields.fire_rate.modes',
        '---@field selector table {bound, input, bindableInputs, order}',
        '---@field binding table? {field, expect, value}: the weapon_function change a selector-less weapon adds with 2+ rates',
        '---@field writable boolean','---@field reason string?','',
        '---The native rates of fire: three slots {X, Y, Z}, the order the weapon menu lists them. A weapon is built on',
        '---Y and each selector press moves Y -> Z -> X, skipping empty (0) slots. Write them with',
        '---hd2.fields.fire_rate.modes (allow_unverified_effect=true); weapons without a selector add one with the',
        '---returned binding in the same transaction.','---@return HD2FireRateModes',
        'function HD2Weapon:fire_rate_modes() end','---@param mode integer|"x"|"y"|"z" Menu position or slot',
        '---@return HD2FireRateMode','function HD2Weapon:fire_rate_mode(mode) end',
        '','---@class HD2Feed','---@field resource "player_weapon"|"support_weapon"','---@field path "feed"',
        '---@field weapon string','---@field feed "primary"|"alternate"|"programmable"','local HD2Feed = {}',
        '---mechanism (projectile, rounds_magazine, programmable_ammo), selector, capacity field, writability.',
        '---@return table','function HD2Feed:describe() end',
        '---The projectile this feed fires: its projectile/damage fields for projectile and rounds feeds, the',
        '---restore handle of a native programmable projectile.','---@return HD2ProjectileReference|table',
        'function HD2Feed:projectile() end',
        '---Where the feed projectile is written: {target, field, expect, binding?, acknowledgements, writable}.',
        '---@return table','function HD2Feed:source() end',
        '---Selectable ammunition/output sources: the normal projectile or two rounds magazines, then a',
        '---ProgrammableAmmo projectile (hd2.fields.function_ammo.projectile).','---@return HD2Feed[]',
        'function HD2Weapon:feeds() end','---@param id "primary"|"alternate"|"programmable"|integer',
        '---@return HD2Feed','function HD2Weapon:feed(id) end',
        '---The projectile builder for this weapon\'s ProgrammableAmmo mode (weapon:feed("programmable")).',
        '---@return HD2ProjectileBuilder','function HD2Weapon:programmable_ammo() end',
        '---The armory trait labels: {traits, armorPenetration, choices, writable, reason}; presentation only.',
        '---Write hd2.fields.presentation.armor_penetration or hd2.fields.presentation.traits.',
        '---@return table','function HD2Weapon:presentation() end',
        '---The underbarrel weapon: a separate weapon entity the host\'s underbarrel item names (AR/GL-21 One-Two',
        '---grenade launcher, AR-11 Arbitrator shotgun, SMG/FLAM-34 Stoker flamer). Its own spread, rounds and fire',
        '---rate are written on it with the ordinary field constants (allow_unverified_effect=true).',
        '---@return HD2Subweapon','function HD2Weapon:underbarrel() end',
        '','---@class HD2Subweapon','---@field resource "player_weapon"','---@field path "weapon"',
        '---@field weapon string "<host> / underbarrel"','local HD2Subweapon = {}',
        '---{name, kind, subweaponOf, link, sharedDefinitions, notExposed, fields}.','---@return table',
        'function HD2Subweapon:describe() end']
    alias('HD2SupportWeaponName',list(support['weapons']))
    support_attack_names=[attack['name'] for weapon in support['weapons'].values()
        for attack in weapon['attackGraph']]
    support_attack_names += [branch['runtimeRole'] for weapon in support_authoring['weapons']
        for branch in weapon['attackBranches'] if branch.get('runtimeRole')]
    alias('HD2SupportAttackName',support_attack_names)
    stub+=['','---@class HD2SupportAttack','---@field resource "support_weapon"',
        '---@field path "attack"|"attack_read_only"','---@field weapon HD2SupportWeaponName',
        '---@field attack string?','---@field attack_index integer?','local HD2SupportAttack = {}',
        '---@return table','function HD2SupportAttack:describe() end',
        '---@return HD2SupportProjectile','function HD2SupportAttack:projectile() end',
        '---@return HD2SupportExplosion','function HD2SupportAttack:explosion() end',
        '---@return HD2SupportAttack','function HD2SupportAttack:damage() end',
        '---@return HD2AttackOutput','function HD2SupportAttack:output() end',
        '---Where this attack\'s fired projectile lives and, for a support component host (magazine-fed, every shot',
        '---its own ProjectileWeapon +0), the target and field that change it (hd2.fields.attack.projectile, with',
        '---allow_unverified_effect=true; cross-class donors also allow_unverified_reference=true).',
        '---@return HD2ProjectileSource','function HD2SupportAttack:projectile_source() end','',
        '---@class HD2SupportProjectile','---@field resource "support_weapon"',
        '---@field path "projectile_reference"','---@field weapon HD2SupportWeaponName',
        '---@field attack string','local HD2SupportProjectile = {}','---@return table',
        'function HD2SupportProjectile:describe() end','---@return HD2SupportProjectile',
        'function HD2SupportProjectile:damage() end','',
        '---@class HD2SupportExplosion','---@field resource "support_weapon"',
        '---@field path "explosion"','---@field weapon HD2SupportWeaponName',
        '---@field attack string','local HD2SupportExplosion = {}','---@return table',
        'function HD2SupportExplosion:describe() end','---@return HD2SupportExplosion',
        'function HD2SupportExplosion:damage() end','',
        '---@class HD2SupportWeapon','---@field resource "support_weapon"',
        '---@field path "weapon"','---@field weapon HD2SupportWeaponName',
        'local HD2SupportWeapon = {}','---@return table',
        'function HD2SupportWeapon:describe() end','---@return HD2SupportAttack[]',
        'function HD2SupportWeapon:attacks() end','---@param identity integer|HD2SupportAttackName',
        '---@return HD2SupportAttack','function HD2SupportWeapon:attack(identity) end',
        '---@param identity integer|HD2SupportAttackName','---@return HD2SupportProjectile',
        'function HD2SupportWeapon:projectile(identity) end',
        '---@param identity integer|HD2SupportAttackName','---@return HD2SupportExplosion',
        'function HD2SupportWeapon:explosion(identity) end',
        '---The backpack that stores this weapon\'s ammunition (backpack-fed weapons only).',
        '---@return HD2Backpack','function HD2SupportWeapon:backpack() end',
        '---@return table','function HD2SupportWeapon:fire_modes() end',
        '---@return HD2FireRateModes','function HD2SupportWeapon:fire_rate_modes() end',
        '---@param mode integer|"x"|"y"|"z" Menu position or slot','---@return HD2FireRateMode',
        'function HD2SupportWeapon:fire_rate_mode(mode) end',
        '---@return HD2Feed[]','function HD2SupportWeapon:feeds() end',
        '---@param id "primary"|"alternate"|"programmable"|integer','---@return HD2Feed',
        'function HD2SupportWeapon:feed(id) end','---@return table','function HD2SupportWeapon:presentation() end',
        '---@param role? string Defaults to "primary".','---@return HD2ProjectileSource',
        'function HD2SupportWeapon:projectile_source(role) end',
        '---The projectile builder for this weapon\'s ProgrammableAmmo mode (weapon:feed("programmable")).',
        '---@return HD2ProjectileBuilder','function HD2SupportWeapon:programmable_ammo() end',
        '','---@class HD2ProjectileModeSpec',
        '---@field id string Operation id prefix (<id>-mode, <id>-slots, <id>-label, <id>-primary-label)',
        '---@field base? HD2AttackOutput|HD2Option The projectile the mode fires: an output, or a choice of outputs',
        '---@field direct_damage? HD2AttackOutputSlot Another output\'s direct-hit damage (a fixed base only)',
        '---@field impact_explosion? HD2AttackOutputSlot|"none" Another output\'s explosion, or none',
        '---@field expiry_explosion? HD2AttackOutputSlot|"none" Another output\'s explosion, or none',
        '---@field label? string|table<string, string> A native mode label; with a choice base, output name -> label',
        '---@field icon? string|table<string, string> A native icon; default "auto" (exact native icon, else the plain round)',
        '---@field primary_label? string The weapon\'s own mode label',
        '---@field primary_icon? string The weapon\'s own mode icon (default "auto")',
        '---@field enabled? HD2Option A toggle applied to every request',
        '---@field allow_shared? boolean Needed when the base (or the weapon\'s own) row is fired by more than one entity',
        '---@field allow_unverified_effect? boolean Passed on to every request (the builder never adds it)',
        '---@field allow_unverified_reference? boolean Passed on to the mode request (a function projectile needs it)',
        '','---@class HD2ProjectileBuilder',
        'local HD2ProjectileBuilder = {}',
        '---{weapon, writable, reason, binding, bases, slots, presentation, acknowledgements, note}.',
        '---@return table','function HD2ProjectileBuilder:describe() end',
        '---Every attack output a programmable mode can fire (projectile family, selectable, scoped for', '---function_ammo.projectile), spare twins included.',
        '---@return HD2AttackOutput[]','function HD2ProjectileBuilder:bases() end',
        '---The ensure requests that build a programmable mode from native pieces, one per backing object: the',
        '---binding and function projectile (<id>-mode), the base slots (<id>-slots), the base label and icon',
        '---(<id>-label[-n]) and the weapon\'s own mode (<id>-primary-label). No new native row is created; a spare',
        '---twin base is an independent native row, any other base changes every entity that fires it.',
        '---Pass each to hd2.ensure.','---@param spec HD2ProjectileModeSpec','---@return table[]',
        'function HD2ProjectileBuilder:operations(spec) end',
        '---Only the label and icon requests (base labels and the weapon\'s own mode), for a separate option.',
        '---@param spec HD2ProjectileModeSpec','---@return table[]','function HD2ProjectileBuilder:presentation(spec) end']
    stratagem_names=[item['name'] for item in stratagem_authoring['stratagems']]
    stratagem_roles=[item['role'] for item in stratagem_authoring['attacks']]
    alias('HD2StratagemAuthoringName',stratagem_names)
    alias('HD2StratagemAttackRole',stratagem_roles)
    stub+=['','---@class HD2StratagemAttack','---@field resource "stratagem"',
        '---@field path "attack"','---@field stratagem HD2StratagemAuthoringName',
        '---@field attack HD2StratagemAttackRole','local HD2StratagemAttack = {}',
        '---@return table','function HD2StratagemAttack:describe() end',
        '---@return HD2StratagemAttack','function HD2StratagemAttack:projectile() end',
        '---@return HD2StratagemAttack','function HD2StratagemAttack:explosion() end',
        '---@return HD2StratagemAttack','function HD2StratagemAttack:damage() end',
        '---@return HD2StratagemAttack','function HD2StratagemAttack:status() end',
        '---@return HD2StratagemAttack','function HD2StratagemAttack:arc() end',
        '---@return HD2StratagemAttack','function HD2StratagemAttack:beam() end',
        '','---@class HD2MountedWeapon','---@field resource "stratagem"',
        '---@field path "weapon"','---@field stratagem HD2StratagemAuthoringName',
        '---@field entity string','---@field weapon string','local HD2MountedWeapon = {}',
        '---@return table','function HD2MountedWeapon:describe() end',
        '---@return HD2StratagemAttack[]','function HD2MountedWeapon:attacks() end',
        '---@param role HD2StratagemAttackRole','---@return HD2StratagemAttack',
        'function HD2MountedWeapon:attack(role) end',
        '','---@class HD2DeployedEntity','---@field resource "stratagem"',
        '---@field path "deployed_entity"','---@field stratagem HD2StratagemAuthoringName',
        '---@field entity string','local HD2DeployedEntity = {}','---@return table',
        'function HD2DeployedEntity:describe() end','---@return HD2DeployedEntity',
        'function HD2DeployedEntity:health() end','---@param identity string',
        '---@return HD2MountedWeapon','function HD2DeployedEntity:weapon(identity) end',
        '---@return HD2MountedWeapon[]','function HD2DeployedEntity:weapons() end',
        '---@param role HD2StratagemAttackRole','---@return HD2StratagemAttack',
        'function HD2DeployedEntity:attack(role) end',
        '---@class HD2EagleRearm','---@field resource "stratagem"',
        '---@field path "eagle_rearm"','---@field stratagem HD2StratagemAuthoringName',
        'local HD2EagleRearm = {}','---@return table','function HD2EagleRearm:describe() end',
        '---@param role HD2StratagemAttackRole','---@return HD2StratagemAttack',
        'function HD2Stratagem:attack(role) end','---@return HD2StratagemAttack[]',
        'function HD2Stratagem:attacks() end','---@return HD2EagleRearm',
        'function HD2Stratagem:eagle_rearm() end',
        '---The deployed mines\' explosion of a mine stratagem (attack role "mine"; see docs/stratagem-authoring.md).',
        '---@return HD2StratagemAttack','function HD2Stratagem:mine() end','---@return HD2DeployedEntity',
        'function HD2Stratagem:deployed_entity() end',
        '---The drop pod this call-in delivers.','---@return HD2PodDelivery','function HD2Stratagem:delivery() end',
        '---@return HD2PodRack','function HD2Stratagem:payload() end',
        '','---@class HD2DeployedShield','---@field resource "stratagem"','---@field path "shield"',
        '---@field stratagem HD2StratagemAuthoringName','---@field entity string',
        'local HD2DeployedShield = {}','---@return table','function HD2DeployedShield:describe() end',
        '','---@class HD2DeployedZone','---@field resource "stratagem"','---@field path "damage_zone"',
        '---@field stratagem HD2StratagemAuthoringName','---@field entity string','---@field zone string',
        'local HD2DeployedZone = {}','---@return table','function HD2DeployedZone:describe() end',
        '---@return HD2DeployedShield','function HD2DeployedEntity:shield() end',
        '','---@class HD2DeployedTurret','---@field resource "stratagem"','---@field path "turret"','local HD2DeployedTurret = {}',
        '---Sentry turret motion: turret.yaw_speed/pitch_speed (degrees per second) and pitch_min/pitch_max/',
        '---yaw_min/yaw_max (degrees). Writes require allow_unverified_effect=true.',
        '---@return table','function HD2DeployedTurret:describe() end',
        '---@return HD2DeployedTurret','function HD2DeployedEntity:turret() end',
        '','---@class HD2DeployedTargeting','---@field resource "stratagem"','---@field path "targeting"','local HD2DeployedTargeting = {}',
        '---Sentry target acquisition: targeting.range (meters). Writes require allow_unverified_effect=true.',
        '---@return table','function HD2DeployedTargeting:describe() end',
        '---@return HD2DeployedTargeting','function HD2DeployedEntity:targeting() end',
        '','---@class HD2DeployedMinefield','---@field resource "stratagem"','---@field path "minefield"',
        'local HD2DeployedMinefield = {}',
        '---Mine deployer counts: minefield.salvos and minefield.mines_per_salvo (reductions only; one launch socket',
        '---per mine). Writes require allow_unverified_effect=true.',
        '---@return table','function HD2DeployedMinefield:describe() end',
        '---@return HD2DeployedMinefield','function HD2DeployedEntity:minefield() end',
        '---@return HD2DeployedZone[]','function HD2DeployedEntity:damage_zones() end',
        '---@param zone string','---@return HD2DeployedZone','function HD2DeployedEntity:damage_zone(zone) end']
    vehicle_names=[item['name'] for item in vehicle_authoring['vehicles']]
    backpack_names=[item['name'] for item in backpack_authoring['backpacks']]
    alias('HD2VehicleAuthoringName',vehicle_names)
    alias('HD2BackpackName',backpack_names)
    alias('HD2BoosterName',[item['name'] for item in booster_authoring['boosters']]
        +[item['semanticId'] for item in booster_authoring['boosters']])
    alias('HD2MountedWeaponId',[item['semanticId'] for item in vehicle_authoring['mountedWeapons']])
    stub+=['','---@class HD2VehicleEntity','---@field resource "vehicle"','---@field path "entity"',
        '---@field vehicle HD2VehicleAuthoringName','local HD2VehicleEntity = {}',
        '---@return table','function HD2VehicleEntity:describe() end',
        '','---@class HD2VehicleZone','---@field resource "vehicle"','---@field path "damage_zone"',
        '---@field vehicle HD2VehicleAuthoringName','---@field zone string','local HD2VehicleZone = {}',
        '---@return table','function HD2VehicleZone:describe() end',
        '','---@class HD2MountedWeaponIdentity','---@field semanticId HD2MountedWeaponId',
        '---@field displayName string','---@field attackFamily string',
        '','---@class HD2VehicleMount','---@field resource "vehicle"','---@field path "mount"',
        '---@field vehicle HD2VehicleAuthoringName','---@field mount string','local HD2VehicleMount = {}',
        '---@return table','function HD2VehicleMount:describe() end',
        '---@return HD2MountedWeaponIdentity?','function HD2VehicleMount:current() end',
        '---@return HD2MountedWeaponIdentity[]','function HD2VehicleMount:candidates() end',
        '---@param identity HD2MountedWeaponId|string','---@return HD2MountedWeaponIdentity',
        'function HD2VehicleMount:candidate(identity) end',
        '---@return HD2VehicleEntity','function HD2Vehicle:entity() end',
        '---@return HD2VehicleZone[]','function HD2Vehicle:damage_zones() end',
        '---@param zone string','---@return HD2VehicleZone','function HD2Vehicle:damage_zone(zone) end',
        '---@return HD2VehicleMount[]','function HD2Vehicle:mounts() end',
        '---@param mount string','---@return HD2VehicleMount','function HD2Vehicle:mount(mount) end',
        '','---@class HD2VehicleWeapon','---@field resource "vehicle_weapon"','---@field path "weapon"',
        '---@field weapon string','local HD2VehicleWeapon = {}',
        '---@return table','function HD2VehicleWeapon:describe() end',
        '---@return HD2VehicleWeaponAttack[]','function HD2VehicleWeapon:attacks() end',
        '---@param role string','---@return HD2VehicleWeaponAttack','function HD2VehicleWeapon:attack(role) end',
        '---@return HD2VehicleWeaponAttack','function HD2VehicleWeapon:projectile() end',
        '---Where the mount\'s fired projectile lives and, for a mounted component host (magazine-fed, every shot its',
        '---own ProjectileWeapon +0), the target and field that change it (hd2.fields.attack.projectile; the same donor',
        '---pool as player and support weapons; allow_shared when another mount carries the same weapon entity).',
        '---@param role? string Defaults to "primary".','---@return HD2ProjectileSource',
        'function HD2VehicleWeapon:projectile_source(role) end',
        '---@param phase? "impact"','---@return HD2VehicleWeaponAttack','function HD2VehicleWeapon:explosion(phase) end',
        '','---@class HD2VehicleWeaponAttack','---@field resource "vehicle_weapon"',
        '---@field path "projectile_reference"|"explosion"|"attack"','---@field weapon string','---@field attack string',
        'local HD2VehicleWeaponAttack = {}','---@return table','function HD2VehicleWeaponAttack:describe() end',
        '---@return HD2ProjectileSource','function HD2VehicleWeaponAttack:projectile_source() end',
        '---@return HD2VehicleWeapon[]','function HD2Vehicle:weapons() end',
        '---@param identity integer|string mount slot, mount label, weapon key or semanticId',
        '---@return HD2VehicleWeapon','function HD2Vehicle:weapon(identity) end',
        '---@return HD2VehicleWeapon','function HD2VehicleMount:weapon() end',
        '','---@class HD2Backpack','---@field resource "backpack"','---@field path "backpack"',
        '---@field backpack HD2BackpackName','local HD2Backpack = {}','---@return table',
        'function HD2Backpack:describe() end',
        '---The support weapon whose ammunition this backpack stores (weapon-fed backpacks only).',
        '---@return HD2SupportWeapon','function HD2Backpack:weapon() end',
        '---Reviewed damage zones (the SH-20 Ballistic Shield\'s "shield" plate zone).',
        '---@return HD2BackpackZone[]','function HD2Backpack:damage_zones() end',
        '---@param identity string|integer Zone id ("zone_0"), native zone name ("shield") or index.',
        '---@return HD2BackpackZone','function HD2Backpack:damage_zone(identity) end',
        '','---@class HD2BackpackZone','---@field resource "backpack"','---@field path "damage_zone"',
        '---@field backpack HD2BackpackName','---@field zone string','local HD2BackpackZone = {}',
        '---zone.armor: the armor every hit on the zone uses (copied into a backpack entity when it spawns).',
        '---@return table','function HD2BackpackZone:describe() end',
        '---The Guard Dog drone this backpack deploys (its own health and damage zone; the drone weapon).',
        '---The backpack -> drone link is re-proven before every write.',
        '---@return HD2BackpackLinked','function HD2Backpack:drone() end',
        '---The SH-51 energy barrier this backpack spawns (shield energy, delays, the barrier damage zone).',
        '---@return HD2BackpackLinked','function HD2Backpack:energy_shield() end',
        '---Names of the linked entities this backpack exposes ("drone", "energy_shield").',
        '---@return string[]','function HD2Backpack:linked() end',
        '','---@class HD2BackpackLinked','---@field resource "backpack"','---@field path "linked"',
        '---@field backpack HD2BackpackName','---@field linked "drone"|"energy_shield"','local HD2BackpackLinked = {}',
        '---@return table','function HD2BackpackLinked:describe() end',
        '---@return HD2BackpackLinkedZone[]','function HD2BackpackLinked:damage_zones() end',
        '---@param identity string|integer Zone id ("zone_0"), native zone name ("body_front") or index.',
        '---@return HD2BackpackLinkedZone','function HD2BackpackLinked:damage_zone(identity) end',
        '---The drone\'s mounted weapon (drones only; see sdk/VehicleWeaponCapabilities.json).',
        '---@return HD2VehicleWeapon','function HD2BackpackLinked:weapon() end',
        '','---@class HD2BackpackLinkedZone','---@field resource "backpack"','---@field path "damage_zone"',
        '---@field backpack HD2BackpackName','---@field linked "drone"|"energy_shield"','---@field zone string',
        'local HD2BackpackLinkedZone = {}','---@return table','function HD2BackpackLinkedZone:describe() end',
        '','---@class HD2BoosterTarget','---@field resource "booster"',
        '---@field path "tuning"|"explosion"|"status_effect"|"status_damage"|"granted_stratagem"|"deployed_entity"',
        '---@field booster string',
        'local HD2BoosterTarget = {}','---@return table','function HD2BoosterTarget:describe() end',
        '---Granted-stratagem targets only: the drop pod the granted stratagem delivers.',
        '---@return HD2PodDelivery','function HD2BoosterTarget:delivery() end',
        '---@return HD2PodRack','function HD2BoosterTarget:payload() end',
        '','---@class HD2PodDelivery','local HD2PodDelivery = {}','---@return HD2PodRack','function HD2PodDelivery:rack() end',
        '','---@class HD2PodRack','---@field resource "pod_rack"','---@field rack string','---@field path "rack"',
        'local HD2PodRack = {}','---@return table','function HD2PodRack:describe() end',
        '---@return HD2PodSlot[]','function HD2PodRack:slots() end',
        '---@param number integer','---@return HD2PodSlot','function HD2PodRack:slot(number) end',
        '','---@class HD2PodSlot','---@field resource "pod_rack"','---@field rack string','---@field path "slot"',
        '---@field slot integer','local HD2PodSlot = {}','---@return table','function HD2PodSlot:describe() end',
        '---@return HD2Pickup|"empty"','function HD2PodSlot:current() end',
        '','---@class HD2Pickup','---@field resource "pickup"','---@field semanticId string','---@field name string',
        '---@field category "support_weapon"|"backpack"|"ammo"|"stim"|"grenade"|"supply"',
        'local HD2Pickup = {}','---@return table','function HD2Pickup:describe() end',
        '','---@class HD2Booster','---@field resource "booster"','---@field path "booster"',
        '---@field booster string','local HD2Booster = {}',
        '---@return table','function HD2Booster:describe() end',
        '---Tuning scalar in the native Booster definition table of game.dll (booster-local).',
        '---@return HD2BoosterTarget','function HD2Booster:tuning() end',
        '---Extra hellpod-impact explosion the booster adds (ExplosionSettings and its DamageInfo).',
        '---@return HD2BoosterTarget','function HD2Booster:explosion() end',
        '---Status effect the booster applies (only where a native record is linked).',
        '---@return HD2BoosterTarget','function HD2Booster:status_effect() end',
        '---Damage of the status effect the booster applies (Dead Sprint drain).',
        '---@return HD2BoosterTarget','function HD2Booster:status_damage() end',
        '---Stratagem the booster grants (its native use count).',
        '---@return HD2BoosterTarget','function HD2Booster:granted_stratagem() end',
        '---Entity the booster deploys (only where a native record is linked).',
        '---@return HD2BoosterTarget','function HD2Booster:deployed_entity() end']
    alias('HD2ThrowableName',[item['name'] for item in throwable_authoring['throwables']]
        +[item['semanticId'] for item in throwable_authoring['throwables']])
    stub+=['','---@class HD2ThrowableTarget','---@field resource "throwable"',
        '---@field path "detonation"|"explosion"|"status_effect"|"shrapnel"|"bomblets"|"bomblet_explosion"|"damage"|"entity"|"shield"',
        '---@field throwable string','---@field status? string','local HD2ThrowableTarget = {}',
        '---@return table','function HD2ThrowableTarget:describe() end',
        '---Explosion targets: a status effect its DamageInfo applies (label such as "fire", or slot number).',
        '---@param identity string|integer','---@return HD2ThrowableTarget',
        'function HD2ThrowableTarget:status_effect(identity) end',
        '---@return HD2ThrowableTarget[]','function HD2ThrowableTarget:status_effects() end',
        '---Explosion targets: the shrapnel projectile the explosion spawns.',
        '---@return HD2ThrowableTarget','function HD2ThrowableTarget:shrapnel() end',
        '---Explosion targets: the bomblet projectile the explosion spawns.',
        '---@return HD2ThrowableTarget','function HD2ThrowableTarget:bomblets() end',
        '---Bomblet targets: the explosion each bomblet makes on impact/expiry.',
        '---@return HD2ThrowableTarget','function HD2ThrowableTarget:explosion() end',
        '','---@class HD2Throwable','---@field resource "throwable"','---@field path "throwable"',
        '---@field throwable string','local HD2Throwable = {}',
        '---Inventory counts (ThrowableComponent) and identity.',
        '---@return table','function HD2Throwable:describe() end',
        '---Fuse / detonation (ExplosiveComponent), where the throwable explodes.',
        '---@return HD2ThrowableTarget','function HD2Throwable:detonation() end',
        '---The explosion (ExplosionSettings and its DamageInfo).',
        '---@return HD2ThrowableTarget','function HD2Throwable:explosion() end',
        '---@param identity string|integer','---@return HD2ThrowableTarget',
        'function HD2Throwable:status_effect(identity) end',
        '---@return HD2ThrowableTarget[]','function HD2Throwable:status_effects() end',
        '---Shrapnel projectile (e.g. G-6 Frag, TM-1 Lure Mine). Shared with other sources.',
        '---@return HD2ThrowableTarget','function HD2Throwable:shrapnel() end',
        '---Bomblet projectile (G-7 Pineapple); :explosion() reaches the explosion of each bomblet.',
        '---@return HD2ThrowableTarget','function HD2Throwable:bomblets() end',
        '---Direct-hit damage (K-2 Throwing Knife; no explosion).',
        '---@return HD2ThrowableTarget','function HD2Throwable:damage() end',
        '---Health of the deployed entity (mines).',
        '---@return HD2ThrowableTarget','function HD2Throwable:entity() end',
        '---Shield of the deployed entity (G/SH-39 Shield).',
        '---@return HD2ThrowableTarget','function HD2Throwable:shield() end']
    alias('HD2EnemyName',sorted({n for item in enemy_authoring['classes'] if item['kind']=='enemy'
        for n in (item['name'],item['className'])}))
    alias('HD2StructureName',sorted({n for item in enemy_authoring['classes'] if item['kind']=='structure'
        for n in (item['name'],item['className'])}))
    stub+=['','---@class HD2EnemyZone','---@field resource "enemy"','---@field path "damage_zone"',
        '---@field enemy string','---@field zone string','local HD2EnemyZone = {}',
        '---Zone fields: zone.health/armor/affects_main_health (proven), zone.constitution/durable_resistance/',
        '---explosive_damage_percentage (allow_unverified_effect=true).',
        '---@return table','function HD2EnemyZone:describe() end',
        '','---@class HD2Enemy','---@field resource "enemy"','---@field path "entity"','---@field enemy string',
        'local HD2Enemy = {}',
        '---Identity (wiki name or native class, faction, kind), damage zones and main fields.',
        '---@return table','function HD2Enemy:describe() end',
        '---@return HD2EnemyZone[]','function HD2Enemy:zones() end',
        '---@param identity string|integer Zone id ("zone_0"), native zone name, wiki zone label or index.',
        '---@return HD2EnemyZone','function HD2Enemy:zone(identity) end',
        '---@return HD2EnemyZone[]','function HD2Enemy:damage_zones() end',
        '---@param identity string|integer','---@return HD2EnemyZone','function HD2Enemy:damage_zone(identity) end',
        '','---@class HD2EnemyAttack','---@field resource "enemy"','---@field path "attack"','---@field enemy string',
        '---@field attack string','local HD2EnemyAttack = {}',
        '---One settings row per attack: DamageInfo (slot_<n>, slot_<n>_impact, ...), ProjectileSettings',
        '---(slot_<n>_projectile: velocity, mass, drag, gravity, pellet_count) or ExplosionSettings (slot_<n>_impact_explosion: radii).',
        '---Shared settings rows: writes need allow_shared=true and allow_unverified_effect=true.',
        '---@return table','function HD2EnemyAttack:describe() end',
        '---@param identity string Attack id ("slot_0", "slot_0_impact", "slot_0_projectile", "slot_0_impact_explosion") or an exactly matched wiki attack name.',
        '---@return HD2EnemyAttack','function HD2Enemy:attack(identity) end',
        '---@return HD2EnemyAttack[]','function HD2Enemy:attacks() end']
    alias('HD2AttackOutputId',sorted({o['semanticId'] for o in attack_outputs['outputs']}
        |{o['owner']['name'] for o in attack_outputs['outputs']}))
    stub+=['','---@class HD2AttackOutput','---@field resource "attack_output"','---@field output string',
        'local HD2AttackOutput = {}',
        '---Family (projectile, beam, arc, spray, melee), owner, structural class and whether a projectile host can',
        '---reference it. Use as the value of hd2.fields.attack.projectile on weapon:attack(role); cross-class',
        '---outputs need allow_unverified_reference=true and allow_unverified_effect=true; beam and arc outputs',
        '---fail closed (INCOMPATIBLE_OUTPUT_FAMILY). A projectile output is also the target of its weapon-function',
        '---mode label and icon (hd2.fields.presentation.mode_label / mode_icon; describe().presentation).',
        '---@return table','function HD2AttackOutput:describe() end',
        '---The native mode labels hd2.fields.presentation.mode_label accepts.',
        '---@return string[]','function HD2AttackOutput:mode_labels() end',
        '---The native weapon-function icons hd2.fields.presentation.mode_icon accepts ("default" restores the',
        '---unlabelled placeholder, an empty spot in the menu; "auto" writes the label exact native icon, else the',
        '---plain round ammo_slug).',
        '---@return string[]','function HD2AttackOutput:mode_icons() end',
        '---The icon "auto" writes for a mode label: {icon, source="exact_native"|"generic_fallback"}.',
        '---@param label string','---@return table','function HD2AttackOutput:mode_icon_for(label) end',
        '---This output\'s direct-hit damage row, as a value for hd2.fields.projectile.direct_damage on another',
        '---output (the projectile builder). Selectable projectile outputs only.',
        '---@return HD2AttackOutputSlot','function HD2AttackOutput:direct_damage() end',
        '---The explosion this output releases when its projectile hits (none on some rows: see describe().slots).',
        '---@return HD2AttackOutputSlot','function HD2AttackOutput:impact_explosion() end',
        '---The explosion this output releases when its projectile expires (a stuck spear, a timed shell).',
        '---@return HD2AttackOutputSlot','function HD2AttackOutput:expiry_explosion() end',
        '','---@class HD2AttackOutputSlot','---@field resource "attack_output_slot"','---@field output string',
        '---@field slot "directDamage"|"impactExplosion"|"expiryExplosion"','local HD2AttackOutputSlot = {}',
        '---{output, slot, field, present, allowNone, shared}.','---@return table',
        'function HD2AttackOutputSlot:describe() end']
    # Event actions: the named explosions (Hellbombs) and the statuses hd2.status offers (domains/event_natives.lua).
    event_actions = json.loads((ROOT/'research/event-actions-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    alias('HD2ExplosionName',[item['name'] for item in event_actions['namedExplosions']]
        +['Hellbomb','Portable Hellbomb'])
    alias('HD2StatusId',[item['semanticId'] for item in event_actions['status']['allowlist']])
    alias('HD2MagazineAttachmentId',[item['semanticId'] for item in attachment_authoring['attachments']]
        +[item['name'] for item in attachment_authoring['attachments'] if item['nameUnique']])
    stub+=['','---@class HD2WeaponAttachment','---@field resource "weapon_attachment"','---@field path "magazine"',
        '---@field attachment string','local HD2WeaponAttachment = {}','---@return table',
        'function HD2WeaponAttachment:describe() end',
        '---Native default and uniquely proven magazine attachments for this weapon.',
        '---@return HD2WeaponAttachment[]','function HD2Weapon:magazine_attachments() end',
        '---@param identity? string Catalog option name, attachment semanticId, or "default".',
        '---@return HD2WeaponAttachment','function HD2Weapon:magazine_attachment(identity) end']
    for domain,names in fields.items():
        stub+=['','---@class HD2Fields_'+domain]
        for constant,name in names.items():
            relevant=[(r['label'],f) for r in resources.values() for n,f in r['fields'].items() if n==name and f['domain']==domain]
            note='; '.join(label+': '+('reviewed writable' if f['writable'] else 'read-only')+', '+f['value_type'] for label,f in relevant)
            if name in player_aliases:
                note=('Deprecated compatibility alias; use hd2.fields.'
                    +player_aliases[name]+('. '+note if note else '.'))
            elif relevant:
                # Original fixed-resource catalog field (short names such as 'JAR-5 Dominator').
                hint=LEGACY_TYPED.get(name)
                note=('Legacy fixed-resource field (original short-name catalog only). '
                    +('Typed targets use '+hint+'. ' if hint else '')+note)
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
    import generate_events
    event_classes,event_fields,event_functions=generate_events.stub_lines()
    stub+=event_classes
    stub+=['','---@class HD2Runtime','---@field fields HD2Fields','---@field enums HD2Enums',
           '---@field resources HD2Resources','---@field version string','---@field api_version integer',
           *event_fields,'local hd2 = {}']
    for method,domain in schema['builders'].items():
        names=[n for r in resources.values() if r['kind']==domain for n in r['aliases']]
        if domain=='weapon':names+= [w['name'] for w in player_capabilities['weapons']]
        if domain=='stratagem':names+=stratagem_names
        if domain=='vehicle':names+=vehicle_names
        alias('HD2'+method.title()+'Name',names)
        stub+=['---@param name HD2'+method.title()+'Name','---@return '+types[domain]['class'],
               'function hd2.'+method+'(name) end']
    stub+=['---@param name HD2SupportWeaponName','---@return HD2SupportWeapon',
        'function hd2.support_weapon(name) end',
        '---@param name HD2BackpackName','---@return HD2Backpack','function hd2.backpack(name) end',
        '---@param name HD2BoosterName','---@return HD2Booster','function hd2.booster(name) end',
        '---A throwable-slot item by name or semantic ID (see sdk/ThrowableAuthoringCapabilities.json).',
        '---@param name HD2ThrowableName','---@return HD2Throwable','function hd2.throwable(name) end',
        '---@param identity HD2MagazineAttachmentId','---@return HD2WeaponAttachment',
        'function hd2.weapon_attachment(identity) end',
        '---A drop-pod rack by name or semantic ID (see sdk/PodPayloadCapabilities.json).',
        '---@param identity string','---@return HD2PodRack','function hd2.pod_rack(identity) end',
        '---A reviewed replacement pickup by name or semantic ID.',
        '---@param identity string','---@return HD2Pickup','function hd2.pickup(identity) end',
        '---@param category? "support_weapon"|"backpack"|"ammo"|"stim"|"grenade"|"supply"',
        '---@return HD2Pickup[]','function hd2.pickups(category) end',
        '---An enemy class by wiki name (when proven) or native class name (see sdk/EnemyAuthoringCapabilities.json).',
        '---@param name HD2EnemyName','---@return HD2Enemy','function hd2.enemy(name) end',
        '---An enemy structure (fabricators, emplacements, objectives) by wiki or native class name.',
        '---@param name HD2StructureName','---@return HD2Enemy','function hd2.structure(name) end',
        '---Reviewed enemy / structure names, optionally filtered by kind and faction.',
        '---@param filter? {kind?: "enemy"|"structure", faction?: "terminids"|"automatons"|"illuminate"|"neutral"}',
        '---@return string[]','function hd2.enemies(filter) end',
        '---A catalogued attack output by semantic ID or owner weapon name (see docs/attack-outputs.md).',
        '---@param identity HD2AttackOutputId','---@return HD2AttackOutput','function hd2.attack_output(identity) end',
        '---Mods that need a newer HD2Runtime (HD2Runtime 0.28.0+). The SDK wrapper of every mod reports here before its',
        '---own version check fails closed; HD2Runtime logs each mod and shows one update warning per session on the ship.',
        'hd2.compatibility = {}',
        '---Record that `mod` needs `minimum` (SemVer); true when the installed HD2Runtime satisfies it.',
        '---@param mod string','---@param minimum string','---@param display string?','---@return boolean ok',
        '---@return string? reason','function hd2.compatibility.require_runtime(mod, minimum, display) end',
        '---SemVer precedence (-1, 0, 1; nil when malformed). A prerelease is older than its release.',
        '---@param a string','---@param b string','---@return integer?','function hd2.compatibility.compare(a, b) end',
        '---@return table[] {mod, display, required}','function hd2.compatibility.incompatible() end',
        '---@return string? highest','function hd2.compatibility.highest() end',
        '---@return table {incompatible, highest, shown, dialog}','function hd2.compatibility.status() end',
        '---Catalogued attack output IDs, optionally filtered.',
        '---@param filter? {family?: "projectile"|"beam"|"arc"|"spray"|"melee", selectable?: boolean}',
        '---@return string[]','function hd2.attack_outputs(filter) end',
        '','---@class HD2Diagnostics','local HD2Diagnostics = {}',
        '---Opt-in sampled timing (off by default): {enabled=true, report_seconds=60} logs, every interval, the average,',
        '---p95, p99 and maximum of the Runtime update, one ensure byte-check and event polling, with the active',
        '---ensures and re-applications. Returns {enabled, report_seconds, timed, sections}.',
        '---@param options? {enabled?: boolean, report_seconds?: number}','---@return table',
        'function HD2Diagnostics.telemetry(options) end',
        '---Ensure-owned targets something else keeps overwriting (always on; a warning is logged after 3 re-applications',
        '---in the operation\'s window): {operation, target, externalChanges, warnings, windowSeconds}[], most first.',
        '---@return table[]','function HD2Diagnostics.write_conflicts() end',
        '---@type HD2Diagnostics','hd2.diagnostics = {}']
    stub+=event_functions
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
            'sdk/CompositionPlanCapabilities.json':json.dumps(composition_plan,indent=2)+'\n',
            'sdk/stubs/mods/skyeshade/hd2runtime.lua':'\n'.join(stub),
            'starter/stubs/mods/skyeshade/hd2runtime.lua':'\n'.join(stub),
            'sdk/docs/api.md':'\n'.join(doc),
            'sdk/docs/player-weapon-composition.md':(ROOT/'docs/player-weapon-composition.md').read_text(encoding='utf-8'),
            'sdk/docs/composition-plans.md':(ROOT/'docs/composition-plans.md').read_text(encoding='utf-8'),
            'sdk/docs/attachment-preset-research.md':(ROOT/'docs/attachment-preset-research.md').read_text(encoding='utf-8'),
            'sdk/docs/support-weapon-api.md':(ROOT/'docs/support-weapon-api.md').read_text(encoding='utf-8'),
            'sdk/docs/stratagem-authoring.md':(ROOT/'docs/stratagem-authoring.md').read_text(encoding='utf-8'),
            'sdk/docs/vehicle-authoring.md':(ROOT/'docs/vehicle-authoring.md').read_text(encoding='utf-8'),
            'sdk/docs/backpack-authoring.md':(ROOT/'docs/backpack-authoring.md').read_text(encoding='utf-8'),
            'sdk/docs/backpack-ammo.md':(ROOT/'docs/backpack-ammo.md').read_text(encoding='utf-8'),
            'sdk/docs/pod-payloads.md':(ROOT/'docs/pod-payloads.md').read_text(encoding='utf-8'),
            'sdk/docs/booster-authoring.md':(ROOT/'docs/booster-authoring.md').read_text(encoding='utf-8'),
            'sdk/docs/throwable-authoring.md':(ROOT/'docs/throwable-authoring.md').read_text(encoding='utf-8'),
            'sdk/docs/asset-loading.md':(ROOT/'docs/asset-loading.md').read_text(encoding='utf-8'),
            'sdk/docs/weapon-movement.md':(ROOT/'docs/weapon-movement.md').read_text(encoding='utf-8'),
            'sdk/docs/status-effects.md':(ROOT/'docs/status-effects.md').read_text(encoding='utf-8'),
            'sdk/docs/enemy-authoring.md':(ROOT/'docs/enemy-authoring.md').read_text(encoding='utf-8'),
            'sdk/docs/live-evidence.md':(ROOT/'docs/live-evidence.md').read_text(encoding='utf-8'),
            'sdk/docs/attack-outputs.md':(ROOT/'docs/attack-outputs.md').read_text(encoding='utf-8'),
            'sdk/docs/magazine-attachments.md':(ROOT/'docs/magazine-attachments.md').read_text(encoding='utf-8'),
            'sdk/docs/getting-started.md':(ROOT/'docs/getting-started.md').read_text(encoding='utf-8'),
            'sdk/docs/events.md':(ROOT/'docs/events.md').read_text(encoding='utf-8'),
            'sdk/docs/event-scripting.md':(ROOT/'docs/event-scripting.md').read_text(encoding='utf-8'),
            'sdk/docs/options.md':(ROOT/'docs/options.md').read_text(encoding='utf-8'),
            'sdk/docs/weapon-reticles.md':(ROOT/'docs/weapon-reticles.md').read_text(encoding='utf-8'),
            'sdk/docs/fire-modes.md':(ROOT/'docs/fire-modes.md').read_text(encoding='utf-8'),
            'sdk/docs/fire-rate-modes.md':(ROOT/'docs/fire-rate-modes.md').read_text(encoding='utf-8'),
            'sdk/docs/weapon-feeds.md':(ROOT/'docs/weapon-feeds.md').read_text(encoding='utf-8'),
            'sdk/docs/weapon-presentation.md':(ROOT/'docs/weapon-presentation.md').read_text(encoding='utf-8'),
            'sdk/docs/vehicle-weapons.md':(ROOT/'docs/vehicle-weapons.md').read_text(encoding='utf-8'),
            'sdk/docs/stratagem-uses.md':(ROOT/'docs/stratagem-uses.md').read_text(encoding='utf-8'),
            'sdk/docs/diagnostics.md':(ROOT/'docs/diagnostics.md').read_text(encoding='utf-8'),
            'sdk/tools/hd2_archive.py':(ROOT/'scripts/hd2_archive.py').read_text(encoding='utf-8')}


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
