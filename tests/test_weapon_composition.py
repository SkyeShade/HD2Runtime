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


class WeaponCompositionTests(unittest.TestCase):
    def test_generated_runtime_catalog_is_current(self):
        self.assertFalse(generate_weapon_composition.generate(check=True))

    def test_four_reports_cover_all_80_and_are_read_only_research(self):
        for report in (MAGAZINES, PROJECTILES, FIRE_MODES, TERMINALS):
            self.assertEqual(report['catalogWeapons'], 80)
            self.assertEqual(report['safety'], {'writes': 0, 'protectionChanges': 0,
                'fixtureFallback': 'disabled', 'snapshotOnly': True})
            encoded=json.dumps(report).lower()
            self.assertNotIn('absoluteaddress',encoded)
            self.assertNotIn('baseaddress',encoded)
        self.assertEqual(MAGAZINES['summary']['nativeOptionIdentities'], 52)
        self.assertEqual(MAGAZINES['summary']['defaultRelationshipsProven'], 19)
        self.assertEqual(MAGAZINES['summary']['perOptionAmmoOwnersProven'], 0)
        self.assertEqual(PROJECTILES['summary']['projectileAttacks'], 67)
        self.assertEqual(PROJECTILES['summary']['writableTargetAttacks'], 45)
        self.assertEqual(FIRE_MODES['summary']['nativePrimaryValueReadable'], 80)
        self.assertEqual(FIRE_MODES['summary']['writableWeapons'], 0)
        self.assertEqual(TERMINALS['summary']['readableActions'], 134)
        self.assertEqual(TERMINALS['summary']['writableActions'], 0)

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
        self.assertTrue(impact['linkedExplosionRecord']);self.assertFalse(impact['writable'])

    def test_public_composition_handles_and_reference_validation(self):
        script=modules()+r'''
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local jar=session.weapon('JAR-5 Dominator')
local attacks=jar:attacks();assert(#attacks==1)
local target=jar:attack('primary');local current=target:projectile()
assert(current.weapon=='JAR-5 Dominator'and current.attack=='primary')
local source=session.weapon('P-113 Verdict'):attack('primary'):projectile()
local spec=writes.validate_patch{id='jar-verdict-projectile',target=target,
 field=session.fields.attack.projectile,expect=current,value=source}
assert(spec.attack=='primary'and spec.changes[1].descriptor.type=='projectile_reference')
assert(spec.changes[1].desired_selector.weapon=='P-113 Verdict')
local ok=pcall(writes.validate_patch,{id='raw-id-rejected',target=target,
 field=session.fields.attack.projectile,expect=177,value=1})
assert(not ok)
local explosive=session.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
ok=pcall(writes.validate_patch,{id='class-rejected',target=target,
 field=session.fields.attack.projectile,expect=current,value=explosive})
assert(not ok)
local halt=session.weapon('SG-20 Halt'):attack('alternate')
assert(halt.attack=='feed_alternate'and halt:projectile().attack=='feed_alternate')
local fire=jar:fire_modes();assert(fire.nativeValue==2 and not fire.writable)
local liberator=session.weapon('AR-23 Liberator')
local magazine=assert(liberator:default_magazine());local described=magazine:describe()
assert(described.optionId=='0x73CA1B5E'and not described.writable)
local impact=session.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
 :terminal_action('impact'):describe()
assert(impact.reference_type==59 and impact.action_kind=='explosion'and not impact.writable)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')

    def test_typed_reference_uses_guarded_exact_width_write(self):
        script=modules()+r'''
local b=require('hd2runtime/core/bytes')
local writes=require('hd2runtime/domains/player_weapon_writes')
local guard=require('hd2runtime/core/guarded_transaction')
local session=require('hd2runtime/api/session').new({},function()end)
local target=session.weapon('JAR-5 Dominator'):attack('primary')
local current=target:projectile()
local source=session.weapon('P-113 Verdict'):attack('primary'):projectile()
local spec=writes.validate_patch{id='typed-reference',target=target,
 field=session.fields.attack.projectile,expect=current,value=source}
local change=spec.changes[1];local tb=change.descriptor.backing;local sb=change.source_descriptor.backing
local source_type=change.source_descriptor.currentDefault.projectileType
local owner={base=0x200000,size=4096,type=0x20000,protect=2}
local target_offset,source_offset=64,1024
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local target_bytes=string.rep('\0',616);target_bytes=splice(target_bytes,tb.offset,b.encode(177,'u32'))
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
records[target_candidate].bytes=splice(target_bytes,tb.offset,b.encode(177,'u32'))
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
local attack=session.weapon('JAR-5 Dominator'):attack('primary')
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

    def test_fire_modes_and_terminal_actions_remain_unwritable(self):
        script=modules()+r'''
local session=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local jar=session.weapon('JAR-5 Dominator')
local ok=pcall(writes.validate_patch,{id='full-auto-blocked',target=jar,
 field=session.fields.weapon.primary_fire_mode,expect=2,value=1})
assert(not ok)
ok=pcall(writes.validate_patch,{id='terminal-blocked',target=jar:attack('primary'),
 field=session.fields.terminal.explosion,
 expect=jar:attack('primary'):projectile():terminal_action('impact'),
 value=jar:attack('primary'):projectile():terminal_action('expiry')})
assert(not ok)
return'ok'
'''
        self.assertEqual(execute(script.encode()),b'ok')


if __name__=='__main__':unittest.main()
