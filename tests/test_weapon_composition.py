import json
import sys
import unittest

from support import ROOT, execute, modules
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_weapon_composition


MAGAZINES = json.loads((ROOT / 'sdk/PlayerWeaponMagazineOptionGraph.json').read_text())
PROJECTILES = json.loads((ROOT / 'sdk/PlayerWeaponProjectileReferenceGraph.json').read_text())
FIRE_MODES = json.loads((ROOT / 'sdk/PlayerWeaponFireModeGraph.json').read_text())
TERMINALS = json.loads((ROOT / 'sdk/PlayerWeaponTerminalActionGraph.json').read_text())
EXPLOSIONS = json.loads((ROOT / 'sdk/ExplosionAuthoringCapabilities.json').read_text())
HEAT = json.loads((ROOT / 'sdk/PlayerWeaponHeatCapabilities.json').read_text())


class WeaponCompositionTests(unittest.TestCase):
    def test_generated_runtime_catalog_is_current(self):
        self.assertFalse(generate_weapon_composition.generate(check=True))

    def test_reports_cover_all_80_and_research_is_read_only(self):
        for report in (MAGAZINES, PROJECTILES, FIRE_MODES, TERMINALS, EXPLOSIONS, HEAT):
            self.assertEqual(report['catalogWeapons'], 80)
            self.assertEqual(report['safety'], {'writes': 0, 'protectionChanges': 0,
                'fixtureFallback': 'disabled', 'snapshotOnly': True})
            encoded=json.dumps(report).lower()
            self.assertNotIn('absoluteaddress',encoded)
            self.assertNotIn('baseaddress',encoded)
        self.assertEqual(MAGAZINES['summary']['nativeOptionIdentities'], 52)
        self.assertEqual(MAGAZINES['summary']['attachmentOptionsMapped'], 419)
        self.assertEqual(MAGAZINES['summary']['magazineOptionsWithNativeIdentity'], 13)
        self.assertEqual(MAGAZINES['summary']['perOptionAmmoOwnersProven'], 0)
        self.assertEqual(MAGAZINES['summary']['customizationRecordsScanned'], 191)
        self.assertEqual(MAGAZINES['summary']['nativeOptionIdsObservedInCorpus'], 20)
        self.assertEqual(MAGAZINES['summary']['nativeAddPathsObservedInCorpus'], 6)
        self.assertEqual(MAGAZINES['summary']['writableAttachmentSelections'], 0)
        self.assertEqual(MAGAZINES['summary']['alternateAllowedRelationshipsProven'], 0)
        self.assertEqual(PROJECTILES['summary']['projectileAttacks'], 67)
        self.assertEqual(PROJECTILES['summary']['writableTargetAttacks'], 59)   # 0.30.2: the seven DUPLICATE weapons resolved to their proven roots
        self.assertEqual(PROJECTILES['summary']['writableExplosiveSelectors'], 13)   # 0.30.2 roots
        self.assertEqual(FIRE_MODES['summary']['nativePrimaryValueReadable'], 80)
        self.assertEqual(FIRE_MODES['summary']['writableWeapons'], 22)   # 0.30.2 roots
        self.assertEqual(TERMINALS['summary']['readableActions'], 134)
        self.assertEqual(TERMINALS['summary']['writableActions'], 134)   # every readable action (0.30.2 roots)
        self.assertEqual((TERMINALS['summary']['writableImpactRefs'],
                          TERMINALS['summary']['writableExpiryRefs']),(67,67))
        self.assertEqual(EXPLOSIONS['summary']['explosionSettingsResolved'],13)
        self.assertEqual(EXPLOSIONS['summary']['explosionScalarFieldsWritable'],156)   # 0.30.2 roots
        self.assertEqual(EXPLOSIONS['summary']['shrapnelGraphsResolved'],1)
        self.assertEqual(HEAT['summary']['weaponsWithHeatMechanism'], 7)
        self.assertEqual(HEAT['summary']['weaponsWithHeatsinkMechanism'], 7)
        # 0.30.2 roots: the research counts the Scythe and Dagger members; the SDK keeps the Scythe's four
        # members its default Laser Heatsink overwrites read-only (generate_weapon_authoring block_overridden).
        self.assertEqual(HEAT['summary']['writableFieldInstances'], 42)
        self.assertEqual(HEAT['summary']['weaponsWithWritableHeatFields'], 7)

    def test_magazine_default_is_proven_but_option_values_fail_closed(self):
        weapons={item['weapon']:item for item in MAGAZINES['weapons']}
        liberator=weapons['AR-23 Liberator'];option=liberator['defaultOption']
        self.assertEqual(option['optionId'],'0x73CA1B5E')
        self.assertTrue(option['default'] and option['allowed'] and option['optionIdentityProven'])
        self.assertFalse(option['ammoValueOwnerProven'] or option['writable'])
        self.assertEqual(liberator['observedCustomizationOptions'][0]['optionIdOffsets'],[4])
        self.assertEqual(weapons['JAR-5 Dominator']['observedCustomizationOptions'],[])
        self.assertTrue(weapons['JAR-5 Dominator']['simpleMagazineApi'])
        self.assertEqual(weapons['SG-20 Halt']['backingDomain'],'WeaponRoundsComponentData')

    def test_jar_full_auto_remains_blocked_without_allowed_consumer_state(self):
        jar=next(item for item in FIRE_MODES['weapons']
            if item['weapon']=='JAR-5 Dominator')
        self.assertEqual(jar['nativeModeVector'],[2,3,0])
        self.assertEqual(jar['allowedModes'],[2])
        self.assertEqual(jar['defaultModeSemantics'],'semi_auto')
        self.assertFalse(jar['writable'])
        self.assertIn('both native 1 and 2',jar['reason'])
        meanings=FIRE_MODES['findings']['nativeValues']
        self.assertIn('Full Auto',meanings['1'])
        self.assertIn('Semi Auto',meanings['2'])
        self.assertIn('not sufficiently uniform',meanings['3'])

    def test_terminal_offsets_link_only_typed_explosion_records(self):
        self.assertEqual(TERMINALS['summary']['impactExplosionLinks'],13)
        self.assertEqual(TERMINALS['summary']['expiryExplosionLinks'],5)
        evidence={item['offset']:item for item in TERMINALS['neighborReferenceEvidence']}
        self.assertEqual(evidence[144]['nonzeroRecords'],evidence[144]['linkedExplosionRecords'])
        self.assertEqual(evidence[156]['nonzeroRecords'],evidence[156]['linkedExplosionRecords'])
        for offset,item in evidence.items():
            if offset not in (144,156):self.assertEqual(item['linkedExplosionRecords'],0)
        crossbow=next(item for item in TERMINALS['weapons']
            if item['weapon']=='CB-9 Exploding Crossbow')
        impact=crossbow['attacks'][0]['actions'][0]
        self.assertEqual((impact['phase'],impact['referenceType'],impact['actionKind']),('impact',59,'explosion'))
        self.assertTrue(impact['linkedExplosionRecord'] and impact['writable'])

    def test_public_composition_handles_and_reference_validation(self):
        script=modules()+r'''
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local jar=session.weapon('JAR-5 Dominator')
local attacks=jar:attacks();assert(#attacks==1)
local source=session.weapon('P-113 Verdict'):attack('primary'):projectile()
-- The JAR-5's ProjectileWeapon +0 is dormant (its default ammunition delta owns the fired projectile).
local ok,why=pcall(writes.validate_patch,{id='jar-verdict-projectile',target=jar:attack('primary'),
 field=session.fields.attack.projectile,expect=jar:attack('primary'):projectile(),value=source})
assert(not ok and tostring(why):find('DORMANT_PROJECTILE_REFERENCE',1,true),tostring(why))
local host=session.weapon('SMG-32 Reprimand')
local target=host:attack('primary');local current=target:projectile()
assert(current.weapon=='SMG-32 Reprimand'and current.attack=='primary')
local spec=writes.validate_patch{id='reprimand-verdict-projectile',target=target,
 field=session.fields.attack.projectile,expect=current,value=source}
assert(spec.attack=='primary'and spec.changes[1].descriptor.type=='projectile_reference')
assert(spec.changes[1].desired_selector.weapon=='P-113 Verdict')
ok=pcall(writes.validate_patch,{id='raw-id-rejected',target=target,
 field=session.fields.attack.projectile,expect=123,value=1})
assert(not ok)
local explosive=session.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
ok=pcall(writes.validate_patch,{id='class-rejected',target=target,
 field=session.fields.attack.projectile,expect=current,value=explosive})
assert(not ok)
local eruptor=session.weapon('R-36 Eruptor'):attack('primary')
local shrapnel=eruptor:projectile()
local explosive_spec=writes.validate_patch{id='eruptor-projectile',target=eruptor,
 field=session.fields.attack.projectile,expect=shrapnel,value=shrapnel}
assert(explosive_spec.changes[1].descriptor.compatibilityClass=='explosive_shrapnel')
local halt=session.weapon('SG-20 Halt'):attack('alternate')
assert(halt.attack=='feed_alternate'and halt:projectile().attack=='feed_alternate')
local fire=jar:fire_modes();assert(fire.nativeValue==2 and not fire.writable)
local liberator=session.weapon('AR-23 Liberator')
local magazine=assert(liberator:default_magazine());local described=magazine:describe()
assert(described.nativeOption.optionId=='0x73CA1B5E'and not described.writable)
assert(#liberator:magazine_options()==3)
local optics=liberator:attachment_options('Optics');assert(#optics>0)
assert(liberator:attachment('Optics',optics[1]:describe().name):describe().category=='Optics')
local terminal=session.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
 :terminal_action('impact')
local impact=terminal:describe();local explosion=terminal:explosion()
assert(impact.reference_type==59 and impact.action_kind=='explosion'and impact.writable)
assert(explosion:describe().explosionType==59 and explosion:damage()==explosion)
assert(explosion:shrapnel().count==0)
local radius=writes.validate_patch{id='crossbow-radius',target=explosion,
 field=session.fields.explosion.inner_radius,expect=3,value=4}
assert(radius.changes[1].descriptor.backing.settings=='explosion')
local source=session.weapon('PLAS-101 Purifier'):attack('primary'):projectile()
 :terminal_action('impact'):explosion()
local terminal_spec=writes.validate_patch{id='crossbow-explosion',target=terminal,
 field=session.fields.terminal.explosion,expect=explosion,value=source}
assert(terminal_spec.changes[1].descriptor.type=='explosion_reference')
ok=pcall(writes.validate_patch,{id='raw-explosion',target=terminal,
 field=session.fields.terminal.explosion,expect=59,value=191});assert(not ok)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_typed_reference_uses_guarded_exact_width_write(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
local writes=require('hd2runtime/domains/player_weapon_writes')
local guard=require('hd2runtime/core/guarded_transaction')
local session=require('hd2runtime/api/session').new({},function()end)
local target=session.weapon('SMG-32 Reprimand'):attack('primary')
local current=target:projectile()
local source=session.weapon('P-113 Verdict'):attack('primary'):projectile()
local spec=writes.validate_patch{id='typed-reference',target=target,
 field=session.fields.attack.projectile,expect=current,value=source}
local change=spec.changes[1];local tb=change.descriptor.backing;local sb=change.source_descriptor.backing
local source_type=change.source_descriptor.currentDefault.projectileType
local owner={base=0x200000,size=4096,type=0x20000,protect=2}
local target_offset,source_offset=64,1024
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local target_bytes=string.rep('\0',616);target_bytes=splice(target_bytes,tb.offset,b.encode(123,'u32'))
local source_bytes=string.rep('\0',616);source_bytes=splice(source_bytes,sb.offset,b.encode(source_type,'u32'))
local function record(backing,offset,bytes)return{owner=owner,offset=offset,bytes=bytes,identity={
 componentType=0x45171B68,recordIndex=backing.recordIndex,indexRow=backing.indexRow,
 uniqueOwner=backing.uniqueOwner,ownerCount=backing.ownerCount}}end
local target_candidate={kind='target'};local source_candidate={kind='source'}
local records={[target_candidate]=record(tb,target_offset,target_bytes),
 [source_candidate]=record(sb,source_offset,source_bytes)}
local settings=change.source_descriptor.referenceSettings
local resolved={candidate=target_candidate,reference_sources={[change.canonical_field]=source_candidate},
 catalog={record=function(candidate,component)
  assert(component=='ProjectileWeaponComponentData');return assert(records[candidate])end},
 roots={projectile={records={[source_type]={group=settings.group,row=settings.row,
  kind=settings.recordType,settings_type=settings.settingsType,bytes=string.rep('\0',272)}}}}}
local memory=string.rep('\0',owner.size)
memory=splice(memory,target_offset,target_bytes);memory=splice(memory,source_offset,source_bytes)
local plan=writes.prepare(resolved,{snapshots={{owner=owner,offset=target_offset,bytes=target_bytes},
 {owner=owner,offset=source_offset,bytes=source_bytes}}},spec)
assert(#plan.changes==1 and #plan.changes[1].chain==2)
assert(plan.changes[1].desired==b.encode(source_type,'u32'))
local protection,written=2,0;local runtime={}
function runtime.system_info()return 4096,0x1000000 end
function runtime.query(address)return{base=owner.base,size=owner.size,allocation_base=owner.base,
 state=0x1000,type=owner.type,protect=protection}end
function runtime.read(address,length)local offset=address-owner.base
 return memory:sub(offset+1,offset+length)end
function runtime.protect(address,length,value)local old=protection;protection=value;return old end
function runtime.write(address,value)written=written+1;memory=splice(memory,address-owner.base,value)
 return true,nil,#value end
local result=guard.apply(runtime,plan)
assert(result.status=='APPLIED'and result.writes==1 and result.bytes_written==4 and written==1)
assert(b.u32(memory,target_offset)==source_type and b.u32(memory,source_offset)==source_type)
assert(result.non_target_bytes_unchanged and result.protection_restored and protection==2)
-- The same declaration becomes an exact zero-write no-op after the selector is desired.
target_bytes=splice(target_bytes,tb.offset,b.encode(source_type,'u32'))
records[target_candidate].bytes=target_bytes
local no_op=writes.prepare(resolved,{snapshots={{owner=owner,offset=target_offset,bytes=target_bytes},
 {owner=owner,offset=source_offset,bytes=source_bytes}}},spec)
local before_writes=written;local already=guard.apply(runtime,no_op)
assert(already.status=='ALREADY_DESIRED'and written==before_writes
 and already.protection_changes==0 and already.protection_restored)
-- Unexpected target and changed source selectors both fail before the writer is called.
records[target_candidate].bytes=splice(target_bytes,tb.offset,b.encode(999,'u32'))
local ok=pcall(writes.prepare,resolved,{snapshots={}},spec);assert(not ok)
records[target_candidate].bytes=splice(target_bytes,tb.offset,b.encode(123,'u32'))
records[source_candidate].bytes=splice(source_bytes,sb.offset,b.encode(999,'u32'))
ok=pcall(writes.prepare,resolved,{snapshots={}},spec);assert(not ok)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_reference_patch_transaction_and_ensure_share_validation(self):
        script=modules()+r'''
local runtime={write=function()end,protect=function()end}
local session=require('hd2runtime/api/session').new(runtime,function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local attack=session.weapon('SMG-32 Reprimand'):attack('primary')
local source=session.weapon('P-113 Verdict'):attack('primary'):projectile()
local change={field=session.fields.attack.projectile,expect=attack:projectile(),value=source}
local transaction=writes.validate_transaction{id='reference-transaction',target=attack,changes={change}}
assert(transaction.kind=='player_weapon'and #transaction.changes==1)
local ensured=session.ensure{startup_delay=0,patch={id='reference-ensure',target=attack,
 field=change.field,expect=change.expect,value=change.value}}
assert(ensured.kind=='patch'and ensured.status=='waiting');ensured.cancel()
assert(ensured.status=='cancelled')
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_projectile_objects_follow_reference_and_require_shared_acknowledgement(self):
        script=modules()+r'''
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local projectile=session.weapon('JAR-5 Dominator'):attack('primary'):projectile()
local ok,why=pcall(writes.validate_patch,{id='shared-projectile',target=projectile,
 field=session.fields.projectile.velocity,expect=180,value=200})
assert(not ok and tostring(why):find('allow_shared=true',1,true))
local spec=writes.validate_patch{id='shared-projectile-ok',target=projectile,allow_shared=true,
 field=session.fields.projectile.velocity,expect=180,value=200}
assert(spec.target_path=='projectile_reference'and spec.changes[1].descriptor.dynamicConsumersPossible)
local reprimand=session.weapon('SMG-32 Reprimand'):attack('primary')
ok,why=pcall(writes.validate_transaction,{id='combined-composition',target=reprimand,
 allow_shared=true,changes={{field=session.fields.attack.projectile,
 expect=reprimand:projectile(),value=projectile},{field=session.fields.projectile.velocity,
 expect=400,value=200}}})
assert(not ok and tostring(why):find('COMPOSITION_TARGET_CHANGED',1,true))
local talon=session.weapon('LAS-58 Talon'):attack('primary'):projectile()
-- Talon's projectile needs the Talon's package: accepted, with that package as an asset dependency.
local talon_spec=writes.validate_patch{id='talon-residency',target=reprimand,
 field=session.fields.attack.projectile,expect=reprimand:projectile(),value=talon}
assert(#talon_spec.asset_dependencies==1 and talon_spec.asset_dependencies[1].name:find('laser_pistol',1,true))
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_support_weapon_read_only_contract_is_graph_aware(self):
        script=modules()+r'''
local session=require('hd2runtime/api/session').new({},function()end)
local arc=session.support_weapon('ARC-3 Arc Thrower')
local described=arc:describe();assert(described.identityResolution=='UNIQUE')
assert(#arc:attacks()==2 and arc:attack('primary'):describe().kind=='Arc')
local silo=session.support_weapon('MS-11 Solo Silo'):describe()
assert(#silo.ownershipChain==3 and silo.ownershipChain[1].kind=='stratagem_payload')
local c4=session.support_weapon('B/MD C4 Pack'):describe()
assert(c4.ownershipChain[1].kind=='placed_or_attack_entity')
local writes=require('hd2runtime/domains/player_weapon_writes')
local ok=pcall(writes.validate_patch,{id='support-write',target=arc,
 field=session.fields.weapon.fire_rate,expect=60,value=100});assert(not ok)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_explosion_scalar_and_terminal_reference_prepare_guarded_bytes(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local eruptor=session.weapon('R-36 Eruptor'):attack('primary'):projectile()
local impact=eruptor:terminal_action('impact');local explosion=impact:explosion()
local radius=writes.validate_patch{id='radius',target=explosion,
 field=session.fields.explosion.inner_radius,expect=4,value=5}
local source=session.weapon('GL-15 Evictor'):attack('primary'):projectile()
 :terminal_action('impact'):explosion()
local reference=writes.validate_patch{id='terminal',target=impact,
 field=session.fields.terminal.explosion,expect=explosion,value=source}
local removal=writes.validate_patch{id='terminal-remove',target=impact,
 field=session.fields.terminal.explosion,expect=explosion,value=impact:no_explosion()}
local target_candidate={ownership={ProjectileWeaponComponentData=true}}
local source_candidate={ownership={WeaponRoundsComponentData=true}}
local target_component=string.rep('\0',616);target_component=splice(target_component,0,b.encode(40,'u32'))
local source_component=string.rep('\0',136);source_component=splice(source_component,64,b.encode(297,'u32'))
local projectile40=string.rep('\0',272);projectile40=splice(projectile40,144,b.encode(158,'u32'))
local projectile297=string.rep('\0',272);projectile297=splice(projectile297,144,b.encode(268,'u32'))
local explosion158=string.rep('\0',152);explosion158=splice(explosion158,16,b.encode(4,'f32'))
local explosion268=string.rep('\0',152)
local function settings(bytes,metadata,offset,owner)return{bytes=bytes,group=metadata.group,row=metadata.row,
 kind=metadata.recordType,settings_type=metadata.settingsType,offset=offset,owner=owner}end
local projectile_owner={base=0x100000,size=4096};local explosion_owner={base=0x200000,size=4096}
local radius_descriptor=radius.changes[1].descriptor
local ref_descriptor=reference.changes[1].descriptor
local source_descriptor=reference.changes[1].source_descriptor
local roots={projectile={owner=projectile_owner,records={
 [40]=settings(projectile40,ref_descriptor.projectileSettings,64,projectile_owner),
 [297]=settings(projectile297,source_descriptor.projectileSettings,512,projectile_owner)}},
 explosion={owner=explosion_owner,records={
 [158]=settings(explosion158,radius_descriptor.backing,32,explosion_owner),
 [268]=settings(explosion268,source_descriptor.referenceSettings,512,explosion_owner)}}}
local catalog={record=function(candidate,component)
 if candidate==target_candidate then assert(component=='ProjectileWeaponComponentData')
  return{bytes=target_component}
 end
 assert(candidate==source_candidate and component=='WeaponRoundsComponentData');return{bytes=source_component}
end}
local resolved={candidate=target_candidate,catalog=catalog,roots=roots,reference_sources={
 [reference.changes[1].canonical_field]=source_candidate}}
local radius_plan=writes.prepare(resolved,{snapshots={}},radius)
assert(#radius_plan.changes==1 and radius_plan.changes[1].desired==b.encode(5,'f32'))
local reference_plan=writes.prepare(resolved,{snapshots={}},reference)
assert(#reference_plan.changes==1 and reference_plan.changes[1].desired==b.encode(268,'u32'))
assert(#reference_plan.changes[1].chain==2)
local removal_plan=writes.prepare({candidate=target_candidate,catalog=catalog,roots=roots,
 reference_sources={}},{snapshots={}},removal)
assert(#removal_plan.changes==1 and removal_plan.changes[1].desired==b.encode(0,'u32'))
local shared=session.weapon('P-33 Missile Pistol'):attack('primary'):projectile()
 :terminal_action('impact'):explosion()
local ok=pcall(writes.validate_patch,{id='shared',target=shared,
 field=session.fields.explosion.inner_radius,expect=2,value=3});assert(not ok)
-- The P-33 fires a spawned entity, so its projectile's explosion row is not established as what it fires.
ok,why=pcall(writes.validate_patch,{id='shared',target=shared,allow_shared=true,
 field=session.fields.explosion.inner_radius,expect=2,value=3})
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),tostring(why))
local allowed=writes.validate_patch{id='shared-ok',target=shared,allow_shared=true,allow_unverified_effect=true,
 field=session.fields.explosion.inner_radius,expect=2,value=3};assert(allowed.allow_shared)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_fire_mode_vector_and_typed_null_terminal_actions(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local jar=session.weapon('JAR-5 Dominator')
local ok=pcall(writes.validate_patch,{id='full-auto-blocked',target=jar,
 field=session.fields.weapon.default_fire_mode,expect=2,value=1})
assert(not ok)
local concussive=session.weapon('AR-23C Liberator Concussive')
local mode=writes.validate_patch{id='semi-mode',target=concussive,
 field=session.fields.weapon.default_fire_mode,expect=session.enums.fire_mode.full_auto,
 value=session.enums.fire_mode.semi_auto}
assert(mode.changes[1].descriptor.nativeModeVector[1]==1
 and mode.changes[1].descriptor.nativeModeVector[2]==2)
local backing=mode.changes[1].descriptor.backing
local owner={base=0x100000,size=4096};local bytes=string.rep('\0',500)
local function splice(value,offset,new)return value:sub(1,offset)..new..value:sub(offset+#new+1)end
bytes=splice(bytes,144,b.encode(1,'u32'));bytes=splice(bytes,148,b.encode(2,'u32'))
local record={bytes=bytes,offset=100,owner=owner,identity={componentType=1,
 recordIndex=backing.recordIndex,indexRow=backing.indexRow,uniqueOwner=true,ownerCount=1}}
local plan=writes.prepare({candidate={},roots={},catalog={record=function(_,component)
 assert(component=='WeaponDataComponentData');return record end}}, {snapshots={}},mode)
assert(#plan.changes==2 and b.u32(plan.changes[1].desired,0)==2
 and b.u32(plan.changes[2].desired,0)==1)
local projectile=session.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
local impact=projectile:terminal_action('impact');local expiry=projectile:terminal_action('expiry')
local none=expiry:no_explosion();local explosion=impact:explosion()
local add=writes.validate_patch{id='copy-impact',target=expiry,
 field=session.fields.terminal.explosion,expect=none,value=explosion}
assert(add.changes[1].desired_selector.is_null==false)
local remove=writes.validate_patch{id='remove-impact',target=impact,
 field=session.fields.terminal.explosion,expect=explosion,value=impact:no_explosion()}
assert(remove.changes[1].desired_selector.is_null)
ok=pcall(writes.validate_patch,{id='raw-null',target=impact,
 field=session.fields.terminal.explosion,expect=explosion,value=0});assert(not ok)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')


if __name__=='__main__':unittest.main()
