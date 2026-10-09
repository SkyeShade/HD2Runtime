"""The weapon firing-sound field weapon.sound (docs/weapon-sounds.md "A weapon's own firing sound"; scripts/
weapon_sound_fields.py; domains/player_weapon_writes.lua). Offline only: nothing here is live-tested.

  * published on every player and support weapon with a ProjectileWeapon record, its expect the weapon's own catalogued
    sound and its reviewed baseline the type's record; refused (with the reason) for fire mode 4/7, suppressed or
    silenced, an event-override table, and no ProjectileWeapon record;
  * the value is a catalogue sound name: a shot writes +260 and +237 and clears +252/+256, a loop writes +252/+256 and
    clears +260 and +237; allow_unverified_effect is required except to restore the weapon's own sound;
  * every other sound names its bank's package (asset_dependencies) and is gated before the write; resident-only and
    unknown sounds are refused;
  * the plan: three event slots and the MIDI flag, one conflict-checked value; the snapshot overlay validation
    (validation/weapon-sound-snapshot.json) pins the exact bytes of a shot and a loop.
"""
import json
import sys
import unittest

from support import ROOT, execute, modules, run
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_weapon_sounds  # noqa: E402
import validate_migration  # noqa: E402


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


PLAYER = load('sdk/PlayerWeaponAuthoringCapabilities.json')
SUPPORT = load('sdk/SupportWeaponAuthoringCapabilities.json')


def player_fields():
    return {w['name']: f for w in PLAYER['weapons'] for f in w['fields'] if f['semanticFieldId'] == 'weapon.sound'}


class RenamedSoundTests(unittest.TestCase):
    def test_names_published_before_the_0_30_2_roots_resolve_to_the_same_sound(self):
        # The Defender and GP-31 resolved to their proven roots, so their former second roots' sounds (the SEAF SMG,
        # the One-Two underbarrel) lost the weapon name; the published names stay as aliases of the same sound.
        self.assertEqual(run(r'''
local sounds=require('hd2runtime/runtime/weapon_sounds')
for old,new in pairs({['primary/smg37/seaf']='seaf/3',['secondary/gp31/alt']='other/wep_grenadier_rifle/1'})do
    local canonical,entry=sounds.resolve(old)
    assert(canonical==new and entry==sounds.entry(new),old)
end
assert(sounds.entry('primary/smg37/seaf').resource=='CA4BBEF63C869C18')   -- the SEAF SMG root
return 'ok'
'''), b'ok')


class MetadataTests(unittest.TestCase):
    def test_player_weapons(self):
        fields = player_fields()
        self.assertEqual(len(fields), 80)
        editable = {name for name, f in fields.items() if f['editable']}
        self.assertEqual(len(editable), 55)   # + the SMG-37 Defender and P-72 Crisper (0.30.2: the seven DUPLICATE weapons resolved to their proven roots, research/weapon-roots)
        sounds = generate_weapon_sounds.build()['sounds']
        for name, field in fields.items():
            if field['currentDefault'] is not None:
                self.assertIn(field['currentDefault'], sounds, name)
                block = field['nativeSound']['block']
                self.assertEqual(len(block), 24)
            if field['editable']:
                self.assertEqual((field['backing']['component'], field['backing']['offset'], field['backing']['width']),
                    ('ProjectileWeaponComponentData', 252, 12))
                self.assertEqual((field['midiOffset'], field['acknowledgement']), (237, 'allow_unverified_effect'))
                self.assertIn('not been live-tested', field['acknowledgementReason'])
                self.assertTrue(field['effect']['instantiationOnly'])
                self.assertFalse(field['effect']['gameplayEffectProven'])
                self.assertFalse(field.get('liveEvidence'))
        self.assertEqual(fields['AR-23 Liberator']['currentDefault'], 'primary/ar23')
        self.assertEqual(fields['AR-23 Liberator']['nativeSound'], {'block': '0000000000000000fb5f6bac', 'midi': 1,
            'kind': 'shot'})
        reasons = {name: f['reason'] for name, f in fields.items() if not f['editable']}
        for name in ('VG-70 Variable', 'DBS-2 Double Freedom', 'SG-22 Bushwhacker'):
            self.assertIn('Fire mode', reasons[name])
        for name in ('AR-59 Suppressor', 'M6C/SOCOM Pistol', 'M7S SMG', 'R-72 Censor'):
            self.assertIn('suppressed', reasons[name])
        for name in ('SG-20 Halt', 'SG-8 Punisher', 'R-6 Deadeye'):
            self.assertIn('event-override', reasons[name])
        for name in ('LAS-5 Scythe', 'FLAM-66 Torcher', 'CQC-2 Saber'):
            self.assertIn('no ProjectileWeapon record', reasons[name])

    def test_support_weapons(self):
        fields = {f['supportWeapon']: f for f in SUPPORT['fieldInstances'] if f['semanticFieldId'] == 'weapon.sound'}
        self.assertEqual(len(fields), 21)
        self.assertIn('M-1000 Maxigun', fields)
        blocked = {w['name']: b['reason'] for w in SUPPORT['weapons'] for b in w['blockedFields']
            if b['field'] == 'weapon.sound'}
        self.assertIn('Fire mode', blocked['MGX-42 Bullet Storm'])
        self.assertIn('Fire mode', blocked['SG-88 Break-Action Shotgun'])
        self.assertIn('no ProjectileWeapon record', blocked['FLAM-40 Flamethrower'])
        self.assertIn('no ProjectileWeapon record', blocked['LAS-98 Laser Cannon'])

    def test_the_constant_and_the_migration_validator(self):
        self.assertIn('validate_weapon_sound_snapshot', validate_migration.SNAPSHOT_VALIDATORS)
        constants = (ROOT / 'domains/constants.lua').read_text(encoding='utf-8')
        self.assertIn('["sound"]="weapon.sound"', constants)


class SnapshotValidationTests(unittest.TestCase):
    def test_the_snapshot_overlay_validation(self):
        result = load('validation/weapon-sound-snapshot.json')
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertEqual(result['fixtureFallback'], 'disabled')
        # Every writable sound restores as an ALREADY_DESIRED no-op without the acknowledgement: the reviewed
        # baseline is the snapshot's record.
        self.assertEqual(result['checked'], {'player': 55, 'support': 21})   # (0.30.2: the seven weapons resolved to their proven roots)
        self.assertEqual((result['noops'], result['acknowledgementRejections']), (76, 76))
        self.assertEqual((result['rollbacks'], result['conflictRejections'], result['adversarialRejections']),
            (4, 2, 9))
        self.assertTrue(result['ownedTransition'])
        self.assertEqual(result['assetGate'], {'dependencies': 1, 'refused': 'ASSET_UNAVAILABLE'})
        pins = result['pins']
        # A MIDI shot taking another MIDI shot: only the per-shot event.
        self.assertEqual(pins['mg43_mg206']['before'], {'+237': '01', '+252': '00000000', '+256': '00000000',
            '+260': 'd0136483'})
        self.assertEqual(pins['mg43_mg206']['after'], {'+237': '01', '+252': '00000000', '+256': '00000000',
            '+260': '11675e82'})
        self.assertEqual(pins['mg43_mg206']['changedParts'], 1)
        # A loop: the start and stop, the per-shot event and the MIDI flag cleared.
        self.assertEqual(pins['mg43_gatling']['after'], {'+237': '00', '+252': '8b8df198', '+256': '29a55c0c',
            '+260': '00000000'})
        self.assertEqual(pins['mg43_gatling']['packages'], ['call-in package of A/G-16 Gatling Sentry'])
        # A plain shot taking a MIDI shot: the event and the MIDI flag.
        self.assertEqual(pins['gl15_maelstrom']['after'], {'+237': '01', '+252': '00000000', '+256': '00000000',
            '+260': '4519cae5'})
        self.assertEqual(pins['gl15_maelstrom']['changedParts'], 2)
        # The Maxigun's loop replaced by a shot.
        self.assertEqual(pins['maxigun_mg206']['before'], {'+237': '00', '+252': '4f1cd622', '+256': 'd5c01660',
            '+260': '00000000'})
        self.assertEqual(pins['maxigun_mg206']['after'], {'+237': '01', '+252': '00000000', '+256': '00000000',
            '+260': '11675e82'})


class LuaTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local w=require('hd2runtime/domains/player_weapon_writes')
local b=require('hd2runtime/core/bytes')
local assets=require('hd2runtime/core/assets')
local F=hd2.fields
assert(F.weapon.sound=='weapon.sound')
local function rejected(fn,needle)
 local ok,why=pcall(fn);assert(not ok,'accepted');assert(tostring(why):find(needle,1,true),tostring(why))
end
local mg43=hd2.support_weapon('MG-43 Machine Gun')
local function patch(target,expect,value,ack)
 return w.validate_patch({id='s',target=target,field=F.weapon.sound,expect=expect,value=value,
  allow_unverified_effect=ack})
end
-- A MIDI shot: +252/+256 cleared, +260 the event (little-endian), +237 the MIDI flag.
local shot=patch(mg43,'support/mg43','support/mg206',true)
assert(b.hex(shot.changes[1].expected)=='0000000000000000d013648301')
assert(b.hex(shot.changes[1].desired)=='000000000000000011675e8201')
assert(#shot.asset_dependencies==1 and shot.asset_dependencies[1].name=='call-in package of E/MG-101 HMG Emplacement')
-- A loop: start and stop, +260 and +237 cleared.
local loop=patch(mg43,'support/mg43','sentry/gatling',true)
assert(b.hex(loop.changes[1].desired)=='8b8df19829a55c0c0000000000')
assert(loop.asset_dependencies[1].name=='call-in package of A/G-16 Gatling Sentry')
-- A plain shot taking a MIDI one sets the flag; the transaction carries the package too.
local evictor=hd2.weapon('GL-15 Evictor')
local tx=w.validate_transaction({id='t',target=evictor,allow_unverified_effect=true,changes={
 {field=F.weapon.sound,expect='primary/gl15',value='vehicle/maelstrom/main_gun'}}})
assert(b.hex(tx.changes[1].expected)=='0000000000000000613fe6ef00')
assert(b.hex(tx.changes[1].desired)=='00000000000000004519cae501')
assert(tx.asset_dependencies[1].name=='call-in package of TD-110 Maelstrom')
-- Restoring the weapon's own sound: its reviewed bytes, no package, no acknowledgement.
local restore=patch(mg43,'support/mg43','support/mg43')
assert(restore.changes[1].desired==restore.changes[1].expected and#restore.asset_dependencies==0)
-- The Maxigun's own loop.
local maxigun=hd2.support_weapon('M-1000 Maxigun')
assert(b.hex(patch(maxigun,'support/m1000','support/m1000').changes[1].expected)=='4f1cd622d5c016600000000000')
-- Refusals: the acknowledgement, unknown, resident-only, raw ids, a stale expect, refused weapons.
rejected(function()patch(mg43,'support/mg43','support/mg206')end,'allow_unverified_effect')
rejected(function()patch(mg43,'support/mg43','support/mg206',false)end,'allow_unverified_effect')
rejected(function()patch(mg43,'support/mg43','sentry/nothing',true)end,'UNKNOWN_SOUND')
rejected(function()patch(mg43,'support/mg43','primary/ar23',true)end,'RESIDENT_ONLY_SOUND')
rejected(function()patch(mg43,'support/mg43','pelican/chin_autocannon',true)end,'RESIDENT_ONLY_SOUND')
rejected(function()patch(mg43,'support/mg43',0x825E6711,true)end,'catalogued sound name')
rejected(function()patch(mg43,'support/mg206','sentry/gatling',true)end,'expect differs')
rejected(function()patch(mg43,nil,'sentry/gatling',true)end,'expect differs')
rejected(function()patch(hd2.weapon('VG-70 Variable'),'primary/vg70','sentry/gatling',true)end,'Fire mode 4 / 7')
rejected(function()patch(hd2.support_weapon('MGX-42 Bullet Storm'),'support/mgx42','sentry/gatling',true)end,
 'Fire mode 4 / 7')
rejected(function()patch(hd2.weapon('M7S SMG'),'primary/m7s','sentry/gatling',true)end,'suppressed')
rejected(function()patch(hd2.weapon('SG-8 Punisher'),'primary/sg8','sentry/gatling',true)end,'event-override')
rejected(function()patch(hd2.support_weapon('FLAM-40 Flamethrower'),'x','sentry/gatling',true)end,
 'no ProjectileWeapon record')
rejected(function()patch(hd2.weapon('LAS-13 Trident'),'x','sentry/gatling',true)end,'no ProjectileWeapon record')
-- (No player weapon resolves to two roots since 0.30.2, so the Ambiguous refusal has no catalogued example.)
-- The asset gate: a sound's package is requested before the write, and a runtime that cannot request packages
-- refuses the operation (nothing is written); the weapon's own sound needs none.
local gate=assets.gate({mode='offline'},loop,nil)
assert(gate.state=='waiting'and#gate.dependencies==1)
local state,reason=gate.tick(1)
assert(state=='failed'and tostring(reason):find('ASSET_UNAVAILABLE',1,true),tostring(state))
assert(assets.gate({mode='offline'},restore,nil).state=='ready')
-- Through the public scheduler: a sound write waits for its assets.
local watch=hd2.patch({id='sound-wait',target=mg43,field=F.weapon.sound,expect='support/mg43',value='sentry/gatling',
 allow_unverified_effect=true})
assert(#watch.asset_dependencies==1)
return 'ok'
'''), b'ok')

    def test_plan_on_a_synthetic_record(self):
        script = modules() + r'''
local b=require('hd2runtime/core/bytes')
local writes=require('hd2runtime/domains/player_weapon_writes')
local guard=require('hd2runtime/core/guarded_transaction')
local target={resource='support_weapon',path='weapon',weapon='MG-43 Machine Gun'}
local spec=writes.validate_patch{id='sound',target=target,field='weapon.sound',expect='support/mg43',
 value='sentry/gatling',allow_unverified_effect=true}
local backing=spec.changes[1].descriptor.backing
local owner={base=0x200000,size=8192,type=0x20000,protect=2}
local record_offset=4096-256   -- the record straddles a page: no part may cross it
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local record_bytes=string.rep('\0',616)
record_bytes=splice(record_bytes,237,string.char(1))
record_bytes=splice(record_bytes,260,b.unhex('d0136483'))
local memory=string.rep('\0',owner.size);memory=splice(memory,record_offset,record_bytes)
local function record()
 return {owner=owner,offset=record_offset,bytes=memory:sub(record_offset+1,record_offset+616),identity={
  componentType=1,recordIndex=backing.recordIndex,indexRow=backing.indexRow,uniqueOwner=backing.uniqueOwner,
  ownerCount=backing.ownerCount}}
end
local function reader()
 return {snapshots={{owner=owner,offset=record_offset,bytes=record().bytes}}}
end
local function resolved()
 return {candidate={},catalog={record=function(_,component)
  assert(component=='ProjectileWeaponComponentData');return record()end}}
end
local protection={}   -- per page
local runtime={}
function runtime.system_info()return 4096,0x1000000 end
function runtime.query(address)local page=address-address%4096
 return {base=page,size=4096,allocation_base=owner.base,state=0x1000,type=owner.type,protect=protection[page]or 2}end
function runtime.read(address,length)local offset=address-owner.base
 return memory:sub(offset+1,offset+length)end
function runtime.protect(address,length,value)local page=address-address%4096
 local old=protection[page]or 2;protection[page]=value;return old end
function runtime.write(address,value)memory=splice(memory,address-owner.base,value);return true,nil,#value end
local plan=writes.prepare(resolved(),reader(),spec)
assert(#plan.changes==4)
local sizes={}
for _,part in ipairs(plan.changes)do sizes[#sizes+1]=part.field_offset..':'..#part.desired end
assert(table.concat(sizes,',')=='252:4,256:4,260:4,237:1',table.concat(sizes,','))
local result=guard.apply(runtime,plan)
assert(result.status=='APPLIED'and result.writes==4,tostring(result.reason))
local now=memory:sub(record_offset+1,record_offset+616)
assert(b.hex(now:sub(253,264))=='8b8df19829a55c0c00000000'and now:byte(238)==0)
-- Applied again: already desired. A third-party event in between is a conflict.
assert(guard.apply(runtime,writes.prepare(resolved(),reader(),spec)).status=='ALREADY_DESIRED')
memory=splice(memory,record_offset+260,b.unhex('01020304'))
local ok,why=pcall(writes.prepare,resolved(),reader(),spec)
assert(not ok and tostring(why):find('CONFLICT',1,true),tostring(why))
return 'ok'
'''
        self.assertEqual(execute(script.encode()), b'ok')


if __name__ == '__main__':
    unittest.main()
