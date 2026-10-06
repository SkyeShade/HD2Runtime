"""Runtime-owned custom projectile rows (docs/custom-projectile-rows.md): the hybrid-row policy on plain Lua strings,
definitions and guarded spawns on the offline fixture world, and the real native adapter's descriptor through an FFI
callback standing in for SpawnProjectile. Nothing here touches a game process."""
import json
import sys
import unittest

from support import ROOT, run, modules
from test_event_scripting import PRELUDE, SDK

sys.path.insert(0, str(ROOT / 'scripts'))
from lua_offline import execute  # noqa: E402
from reference_format import lua  # noqa: E402

ROWS = r'''
local rows=require('hd2runtime/core/projectile_rows')
local b=require('hd2runtime/core/bytes')
local function le(n,width)
    local out={}
    for _=1,width do out[#out+1]=string.char(n%256);n=math.floor(n/256)end
    return table.concat(out)
end
local function put(row,offset,bytes)return row:sub(1,offset)..bytes..row:sub(offset+#bytes+1)end
local function flip(row,offset,mask)
    local value=row:byte(offset+1)
    local flipped=0
    for bit=0,7 do
        local weight=2^bit
        local on=math.floor(value/weight)%2==1
        if math.floor(mask/weight)%2==1 then on=not on end
        if on then flipped=flipped+weight end
    end
    return put(row,offset,string.char(flipped))
end
local function f32(v)
    local m,e=math.frexp(v)
    return le((e+126)*8388608+math.floor((m*2-1)*8388608+0.5),4)
end
-- Talon-like vanilla rows: the type, one pellet, velocity, direct damage, the spawn effect and its parameter, the
-- +0xF0 flags, collision and overlap filters and a unit-less +0xFC.
local function row_of(kind,damage,effect,parameter)
    local r=string.rep('\0',272)
    r=put(r,0,le(kind,4));r=put(r,0x1C,le(1,4));r=put(r,0x20,f32(1300));r=put(r,0x3C,le(damage,4))
    r=put(r,0x48,effect);r=put(r,0x58,f32(parameter));r=put(r,0x70,le(0x89DA8C55,4)..le(0xB75BDEC7,4))
    r=put(r,0xF0,string.char(0x7D,0x00));r=put(r,0xF4,le(2,4));r=put(r,0xF8,le(960337176,4))
    return r
end
local TALON=row_of(144,54,le(0xA36A96FB,4)..le(0xAA3E9927,4),0.05)
local SCORCHER=row_of(142,56,le(0x01659524,4)..le(0x5747E232,4),0.01)
local RAILGUN=row_of(186,64,le(0x04030201,4)..le(0x08070605,4),0.02)
local function classes(report)
    local out={}
    for _,v in ipairs(report.violations)do out[#out+1]=v.class..':'..tostring(v.label)end
    return table.concat(out,',')
end
'''


class HybridRowPolicyTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(execute((modules() + ROWS + body).encode()), b'ok')

    def test_the_policy_covers_every_byte_and_names_the_research_members(self):
        self.lua(r'''
local domain=require('hd2runtime/domains/projectile_rows')
assert(rows.SIZE==272 and domain.row.size==272)
local covered,copied={},{}
for _,e in ipairs(domain.members)do
    for o=e.offset,e.offset+e.width-1 do covered[o]=true end
    if e.class=='COPIED_AT_SPAWN'then copied[#copied+1]=string.format('0x%X',e.offset)end
end
for o=0,271 do assert(covered[o],'uncovered byte '..o)end
assert(table.concat(copied,',')=='0x18,0x20,0x24,0x28,0x2C,0x38,0x3C,0x40,0x48,0x50,0x58,0x60,0x68,0x70,0x78,0x90',
    table.concat(copied,','))
local function class_of(offset,mask)
    for _,e in ipairs(domain.members)do if e.offset==offset and e.mask==mask then return e.class,e.label,e.unit end end
end
-- The confirmed ballistics and explosion members carry their names and units.
local named={[0x18]={'diameter','millimeters'},[0x20]={'speed','meters_per_second'},[0x24]={'mass','grams'},
    [0x28]={'drag','factor'},[0x2C]={'gravity','factor'},[0x38]={'lifetime_variance','fraction'},
    [0x40]={'penetration_slowdown','factor'},[0x90]={'impact_explosion'}}
for offset,want in pairs(named)do
    local class,label,unit=class_of(offset)
    assert(class=='COPIED_AT_SPAWN'and label==want[1]and unit==want[2],string.format('+0x%X %s %s %s',offset,
        tostring(class),tostring(label),tostring(unit)))
end
assert(class_of(0x0)=='BASE_TYPE')
assert(class_of(0xF4)=='LATE_LOOKUP'and class_of(0xF8)=='LATE_LOOKUP'and class_of(0x80)=='LATE_LOOKUP')
assert(class_of(0x100)=='LATE_LOOKUP'and class_of(0xF0,0x1000)=='LATE_LOOKUP')
assert(class_of(0xFC,1)=='LATE_LOOKUP'and class_of(0xFC,2)=='LATE_LOOKUP')
assert(class_of(0x1C)=='FIRE_PATH_LOOKUP')
-- Members read at spawn without the evidence to promote them stay conservative.
for _,offset in ipairs({0x30,0x34,0x88,0x94,0x98,0x9C,0xA8,0xE4,0xE8,0xEC})do
    assert(class_of(offset)=='UNKNOWN',string.format('+0x%X',offset))
end
assert(class_of(0xF0,1)=='UNKNOWN'and class_of(0x8C,1)=='UNKNOWN','bitfield bits stay conservative')
-- Why a member can or cannot differ, from the policy.
local why=rows.describe(0xF4)
assert(#why==1 and why[1].class=='LATE_LOOKUP'and why[1].reason:find('every frame',1,true))
assert(rows.describe(0x3C)[1].class=='COPIED_AT_SPAWN')
return 'ok'
''')

    def test_a_clone_preserves_every_byte_and_changes_never_reach_the_base(self):
        self.lua(r'''
local clone=assert(rows.clone(TALON,144))
assert(clone==TALON and #clone==272)
local changed=assert(rows.apply(clone,{{member='direct_damage',bytes=le(64,4)}}))
assert(changed~=clone and clone==TALON and b.u32(TALON,0x3C)==54,'the base row is never changed')
for o=0,271 do
    if o<0x3C or o>=0x40 then assert(changed:byte(o+1)==TALON:byte(o+1),'byte '..o..' changed')end
end
-- A clone starts only from the base row of its own type.
local none,code=rows.clone(TALON,142)
assert(none==nil and code=='INVALID_BASE_ROW',code)
assert(select(2,rows.clone(TALON:sub(2),144))=='INVALID_BASE_ROW')
assert(select(2,rows.clone(TALON,0))=='INVALID_BASE_TYPE'and select(2,rows.clone(TALON,351))=='INVALID_BASE_TYPE')
return 'ok'
''')

    def test_an_unchanged_clone_and_permitted_changes_are_valid(self):
        self.lua(r'''
local report=rows.validate(assert(rows.clone(TALON,144)),TALON,144)
assert(report.status=='VALID'and#report.changes==0 and#report.violations==0,report.summary)
local custom=assert(rows.apply(TALON,{{member='direct_damage',bytes=RAILGUN:sub(0x3D,0x40)},
    {member='spawn_effect',bytes=SCORCHER:sub(0x49,0x50)},{member=0x58,bytes=SCORCHER:sub(0x59,0x5C)},
    {member='record_resource_70',bytes=string.rep('\0',8)},{member='spawn_effect_secondary',bytes=le(7,8)}}))
report=rows.validate(custom,TALON,144)
assert(report.status=='VALID'and#report.changes==5,report.summary)
assert(report.summary:find('+0x3C direct_damage',1,true)and report.summary:find('+0x48 spawn_effect',1,true))
assert(report.changes[1].offset==0x3C and report.changes[1].base=='36000000'and report.changes[1].value=='40000000')
return 'ok'
''')

    def test_late_lookup_fire_path_and_unknown_members_are_rejected(self):
        self.lua(r'''
local function rejected(custom,expect)
    local report=rows.validate(custom,TALON,144)
    assert(report.status=='INVALID',expect..': '..report.summary)
    assert(classes(report):find(expect,1,true),expect..' not in '..classes(report))
    return report
end
rejected(put(TALON,0xF4,le(3,4)),'LATE_LOOKUP:collision_filter')
rejected(put(TALON,0xF8,le(0,4)),'LATE_LOOKUP:overlap_filter')
rejected(flip(TALON,0xFC,0x01),'LATE_LOOKUP:damage_hit_flag')
rejected(flip(TALON,0xFC,0x02),'LATE_LOOKUP:unit_handoff_flag')
rejected(flip(TALON,0xFC,0x10),'UNKNOWN:nil')
-- +0xF0 bit 12 is the impact-effect late lookup; the word's other bits are unknown, never permitted.
local report=rejected(flip(TALON,0xF1,0x10),'LATE_LOOKUP:impact_effect_bit12')
assert(#report.violations==1 and report.violations[1].mask==0x1000,classes(report))
rejected(flip(TALON,0xF0,0x01),'UNKNOWN:nil')
-- Unit fields: the resource and every byte of +0x100..+0x10B.
rejected(put(TALON,0x80,le(0xE27FEF7C,4)..le(0xF21E8DD5,4)),'LATE_LOOKUP:unit')
for o=0x100,0x10B do rejected(put(TALON,o,'\1'),'LATE_LOOKUP:unit_offset')end
-- Pellet count: read through the vanilla table on the fire path.
rejected(put(TALON,0x1C,le(8,4)),'FIRE_PATH_LOOKUP:pellet_count')
-- Unpromoted members (lifetime, expiry explosion, the +0x30 u32, the +0x94 overlap gate) and padding stay equal.
rejected(put(TALON,0x34,f32(3)),'UNKNOWN:nil')
rejected(put(TALON,0x9C,le(97,4)),'UNKNOWN:nil')
rejected(put(TALON,0x30,le(2,4)),'UNKNOWN:nil')
rejected(put(TALON,0x94,f32(1)),'UNKNOWN:nil')
rejected(put(TALON,0x44,'\1'),'UNKNOWN:nil')
rejected(put(TALON,0x10C,'\1'),'UNKNOWN:nil')
return 'ok'
''')

    def test_ballistics_and_the_impact_explosion_may_differ_member_by_member(self):
        self.lua(r'''
local permitted={{'diameter',0x18,f32(40)},{'speed',0x20,f32(80)},{'mass',0x24,f32(230)},{'drag',0x28,f32(0.3)},
    {'gravity',0x2C,f32(1)},{'lifetime_variance',0x38,f32(0.25)},{'penetration_slowdown',0x40,f32(0.5)},
    {'impact_explosion',0x90,le(158,4)}}
local all={}
for _,item in ipairs(permitted)do
    local label,offset,bytes=item[1],item[2],item[3]
    -- By label and by offset, alone: VALID, reported as exactly that change, every other byte the base's.
    for _,member in ipairs({label,offset})do
        local custom=assert(rows.apply(TALON,{{member=member,bytes=bytes}}))
        local report=rows.validate(custom,TALON,144)
        assert(report.status=='VALID'and#report.changes==1 and report.changes[1].label==label,label..' '
            ..report.summary)
        for o=0,271 do
            if o<offset or o>=offset+4 then assert(custom:byte(o+1)==TALON:byte(o+1),label..' touched '..o)end
        end
    end
    -- Written directly (not through apply) the member is still permitted by the validation.
    assert(rows.validate(put(TALON,offset,bytes),TALON,144).status=='VALID',label)
    all[#all+1]={member=label,bytes=bytes}
end
local custom=assert(rows.apply(TALON,all))
local report=rows.validate(custom,TALON,144)
assert(report.status=='VALID'and#report.changes==#permitted,report.summary)
assert(report.summary:find('+0x20 speed',1,true)and report.summary:find('+0x90 impact_explosion',1,true))
-- Together with the visual and damage members, still VALID; one late-lookup byte more makes the whole row INVALID.
custom=assert(rows.apply(custom,{{member='direct_damage',bytes=le(64,4)},{member='spawn_effect',bytes=le(7,8)}}))
assert(rows.validate(custom,TALON,144).status=='VALID')
report=rows.validate(put(custom,0xF4,le(3,4)),TALON,144)
assert(report.status=='INVALID'and classes(report)=='LATE_LOOKUP:collision_filter',classes(report))
-- The units and meanings are published with the policy.
local speed=rows.describe(0x20)[1]
assert(speed.class=='COPIED_AT_SPAWN'and speed.label=='speed'and speed.reason:find('ballistics record',1,true))
assert(rows.describe(0x48)[1].reason:find('No member is a colour or tint',1,true))
return 'ok'
''')

    def test_the_base_type_cannot_change_and_restricted_members_cannot_be_applied(self):
        self.lua(r'''
local report=rows.validate(put(TALON,0,le(142,4)),TALON,144)
assert(report.status=='INVALID'and report.violations[1].class=='BASE_TYPE',report.summary)
report=rows.validate(put(TALON,0,le(0,4)),TALON,144)
assert(report.status=='INVALID'and report.summary:find('not the base type 144',1,true),report.summary)
-- Validated against a row of another type (the base must be the vanilla row of the base type).
assert(rows.validate(SCORCHER,SCORCHER,144).violations[1].class=='BASE_TYPE')
for _,member in ipairs({0,0x1C,0xF4,0xF8,0x80,0x100,0x30,0x34,0x94,0x9C,'collision_filter','pellet_count',
        'unit','lifetime','expiry_explosion'})do
    local out,code,reason=rows.apply(TALON,{{member=member,bytes=string.rep('\0',4)}})
    assert(out==nil and code=='RESTRICTED_MEMBER',tostring(member)..' '..tostring(code))
end
local _,code,reason=rows.apply(TALON,{{member=0xF4,bytes=le(3,4)}})
assert(reason:find('LATE_LOOKUP',1,true),reason)
assert(select(2,rows.apply(TALON,{{member='direct_damage',bytes='\1'}}))=='INVALID_CHANGE')
return 'ok'
''')


class ComponentDescriptorTests(unittest.TestCase):
    """The semantic component descriptors and component-specific copying, on plain rows."""

    def lua(self, body):
        self.assertEqual(execute((modules() + ROWS + body).encode()), b'ok')

    def test_each_descriptor_owns_only_proven_copied_members(self):
        self.lua(r'''
local want={visual={'ProjectileVisual','spawn_effect,spawn_effect_alternate,spawn_effect_parameter,'
        ..'spawn_effect_secondary,spawn_effect_record','donor'},
    damage={'ProjectileDamage','direct_damage','donor'},
    impact_explosion={'ProjectileImpactExplosion','impact_explosion','donor'},
    ballistics={'ProjectileBallistics','diameter,speed,mass,drag,gravity,lifetime_variance,penetration_slowdown','none'}}
assert(table.concat(rows.COMPONENT_ORDER,',')=='visual,damage,impact_explosion,ballistics')
local owned={}
for id,expect in pairs(want)do
    local component=assert(rows.component(id),id)
    local labels={}
    for _,member in ipairs(component.members)do
        labels[#labels+1]=member.label
        assert(not owned[member.offset],'a member belongs to two components')
        owned[member.offset]=true
        local entry=rows.describe(member.offset)[1]
        assert(entry.class=='COPIED_AT_SPAWN'and entry.label==member.label and not entry.mask,member.label)
    end
    assert(component.name==expect[1]and table.concat(labels,',')==expect[2]and component.assets==expect[3],id)
end
-- No component owns a locked member, and the two copied members without a meaning belong to none.
for _,offset in ipairs({0x00,0x1C,0x34,0x70,0x78,0x80,0x94,0x9C,0xF0,0xF4,0xF8,0xFC,0x100})do
    assert(not owned[offset],string.format('+0x%X is owned by a component',offset))
end
assert(rows.component('visual').constraints[1]=='donor_unit_matches_base')
assert(rows.component('colour')==nil,'there is no colour component')
return 'ok'
''')

    def test_a_component_copies_exactly_its_members_and_nothing_else(self):
        self.lua(r'''
-- A donor that differs from the Talon in every byte except its type and unit.
local donor=put(put(string.rep('\171',272),0,le(99,4)),0x80,string.rep('\0',8))
for _,id in ipairs(rows.COMPONENT_ORDER)do
    local component=rows.component(id)
    local changes=assert(rows.component_changes(id,donor,TALON))
    local custom=assert(rows.apply(TALON,changes))
    local owned={}
    for _,member in ipairs(component.members)do
        for o=member.offset,member.offset+member.width-1 do owned[o]=true end
    end
    for o=0,271 do
        if owned[o]then assert(custom:byte(o+1)==171,id..' did not copy byte '..o)
        else assert(custom:byte(o+1)==TALON:byte(o+1),id..' changed byte '..o..' it does not own')end
    end
    local report=rows.validate(custom,TALON,144)
    assert(report.status=='VALID'and#report.changes==#component.members,id..' '..report.summary)
    for _,change in ipairs(changes)do assert(change.component==id)end
end
-- All four together: every owned member from the donor, the rest the Talon's, still VALID.
local all={}
for _,id in ipairs(rows.COMPONENT_ORDER)do
    for _,change in ipairs(assert(rows.component_changes(id,donor,TALON)))do all[#all+1]=change end
end
local composed=assert(rows.apply(TALON,all))
local report=rows.validate(composed,TALON,144)
assert(report.status=='VALID'and#report.changes==14,report.summary)
assert(composed:sub(0x71,0x80)==TALON:sub(0x71,0x80),'+0x70 / +0x78 belong to no component')
-- The visual of a projectile with a unit cannot go on a unit-less base; other components ignore the unit.
local with_unit=put(donor,0x80,le(7,8))
local none,code,reason=rows.component_changes('visual',with_unit,TALON)
assert(none==nil and code=='COMPONENT_CONSTRAINT'and reason:find('unit',1,true),tostring(code))
assert(rows.component_changes('ballistics',with_unit,TALON)and rows.component_changes('damage',with_unit,TALON))
assert(select(2,rows.component_changes('colour',donor,TALON))=='UNKNOWN_COMPONENT')
assert(select(2,rows.component_changes('visual',donor:sub(2),TALON))=='INVALID_ROW')
return 'ok'
''')


PROOF = PRELUDE + ROWS + r'''
local custom=require('hd2runtime/runtime/custom_projectiles')
local scheduler=require('hd2runtime/runtime/scheduler')
custom.reset_for_tests()
local T=W.projectile_row(144,TALON)
local S=W.projectile_row(142,SCORCHER)
local R=W.projectile_row(186,RAILGUN)
local SPEC=custom.DEVELOPMENT_PROOF
local function in_update(fn)
    local out
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()out={fn()};watch.status='complete'end
    scheduler.attach(watch)
    update(0.1)
    return unpack(out or{})
end
local function fire(opts,id)
    local action
    in_update(function()
        hd2.events.run_as('mods/t/proof',function()
            action=actions.spawn_custom_projectile(id or SPEC.id,opts or{position={x=1,y=2,z=3},
                direction={x=0,y=0,z=-2}})
        end)
    end)
    return action
end
'''


class CustomProjectileWorldTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PROOF + body), b'ok')

    def test_the_development_proof_row_is_a_runtime_owned_valid_hybrid(self):
        self.lua(r'''
local def,code,reason=custom.define(SPEC)
assert(def,tostring(code)..' '..tostring(reason))
assert(def.id=='dev/talon_hybrid_proof'and def.base.type==144 and def.base.weapon=='LAS-58 Talon')
assert(def.validation.status=='VALID',def.validation.summary)
-- The row is the Runtime's own block, never a vanilla row, and holds the clone with the three permitted changes.
assert(W.runtime.owned[def.row.address]==272 and def.row.address~=T and def.row.address~=S and def.row.address~=R)
local bytes=W.read(def.row.address,272)
assert(bytes==def.bytes and b.u32(bytes,0)==144 and b.u32(bytes,0x3C)==64 and bytes:sub(0x49,0x50)==SCORCHER:sub(0x49,0x50))
assert(bytes:sub(0x59,0x5C)==SCORCHER:sub(0x59,0x5C)and bytes:sub(0xF1,0x110)==TALON:sub(0xF1,0x110))
local labels={}
for _,c in ipairs(def.changes)do if c.base~=c.value then labels[#labels+1]=c.label end end
assert(table.concat(labels,',')=='spawn_effect,spawn_effect_parameter,direct_damage',table.concat(labels,','))
-- No vanilla row was written.
assert(W.read(T,272)==TALON and W.read(S,272)==SCORCHER and W.read(R,272)==RAILGUN)
-- Every package the row's resources come from: the base's and each donor's.
assert(#def.dependencies==3,#def.dependencies)
-- Defining the same spec again returns the same definition; a different spec under the same id is refused.
assert(custom.define(SPEC)==def)
local other={id=SPEC.id,base=SPEC.base,changes={{member='direct_damage',from='output/v1/projectile/plas-1-scorcher'}}}
assert(select(2,custom.define(other))=='DUPLICATE_DEFINITION')
assert(custom.line(def):find('custom projectile dev/talon_hybrid_proof base type=144 base identity=LAS-58 Talon custom row=0x',1,true))
assert(custom.line(def):find('hybrid compatibility=VALID',1,true)and custom.line(def):find('+0x3C direct_damage 54 -> 64',1,true))
return 'ok'
''')

    def test_ballistics_and_impact_explosion_donors_copy_only_their_members(self):
        self.lua(r'''
local outputs=require('hd2runtime/domains/attack_outputs').outputs
local eruptor=outputs['output/v1/projectile/r-36-eruptor']
local impact=eruptor.slotFields['projectile.impact_explosion'].currentDefault
assert(type(impact)=='number'and impact>0,'the Eruptor output has a catalogued impact explosion')
local ERUPTOR=put(row_of(eruptor.currentDefault,70,le(0x11111111,4)..le(0x22222222,4),0.03),0x90,le(impact,4))
local E=W.projectile_row(eruptor.currentDefault,ERUPTOR)
-- A heavy, slow, arcing donor: every flight member differs from the Talon's.
local SLOW=put(put(put(put(put(RAILGUN,0x18,f32(40)),0x20,f32(80)),0x24,f32(230)),0x28,f32(0.3)),0x2C,f32(1))
W.projectile_row(186,SLOW)
local spec={id='dev/talon_lobbed',base='output/v1/projectile/las-58-talon',changes={
    {members={'diameter','speed','mass','drag','gravity'},from='output/v1/projectile/rs-422-railgun'},
    {member='impact_explosion',from='output/v1/projectile/r-36-eruptor'}}}
local def,code,reason=custom.define(spec)
assert(def,tostring(code)..' '..tostring(reason))
assert(def.validation.status=='VALID',def.validation.summary)
local labels={}
for _,c in ipairs(def.changes)do labels[#labels+1]=c.label end
assert(table.concat(labels,',')=='diameter,speed,mass,drag,gravity,impact_explosion',table.concat(labels,','))
-- Only the owned members differ from the Talon; the donor's damage, effects and unit-less rest are not copied.
for o=0,271 do
    local owned=(o>=0x18 and o<0x1C)or(o>=0x20 and o<0x30)or(o>=0x90 and o<0x94)
    if not owned then assert(def.bytes:byte(o+1)==TALON:byte(o+1),'byte '..o..' copied')end
end
assert(b.u32(def.bytes,0x90)==impact and def.bytes:sub(0x21,0x24)==f32(80))
assert(custom.line(def):find('+0x90 impact_explosion 0 -> '..impact..' (R-36 Eruptor)',1,true),custom.line(def))
-- It spawns like any definition, and no vanilla row changed.
mission({host=true})
local a=fire(nil,'dev/talon_lobbed')
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
assert(W.runtime.custom_projectiles[1].bytes==W.read(def.row.address,272))
assert(W.read(T,272)==TALON and W.read(E,272)==ERUPTOR and W.read(R,272)==SLOW)
-- A donor whose live impact explosion is not its catalogued one is refused.
W.projectile_row(eruptor.currentDefault,put(ERUPTOR,0x90,le(impact+1,4)))
local _,refused=custom.define({id='dev/talon_eruptor',base=spec.base,changes={{member='impact_explosion',
    from='output/v1/projectile/r-36-eruptor'}}})
assert(refused=='DONOR_CHANGED',tostring(refused))
return 'ok'
''')

    def test_definitions_fail_closed(self):
        self.lua(r'''
local function refused(spec,expect)
    local def,code,reason=custom.define(spec)
    assert(def==nil and code==expect,tostring(code)..' '..tostring(reason)..' (expected '..expect..')')
    return reason
end
local talon='output/v1/projectile/las-58-talon'
refused({id='bad id',base=talon},'INVALID_DEFINITION')
refused({id='dev/x',base=144},'UNKNOWN_PROJECTILE')
refused({id='dev/x',base='output/v1/projectile/s-11-speargun-spare-twin'},'BORROWED_ROW')
refused({id='dev/x',base=talon,changes={{member='collision_filter',from='output/v1/projectile/plas-1-scorcher'}}},
    'RESTRICTED_MEMBER')
refused({id='dev/x',base=talon,changes={{member='pellet_count',from='output/v1/projectile/plas-1-scorcher'}}},
    'RESTRICTED_MEMBER')
refused({id='dev/x',base=talon,changes={{member=0,from='output/v1/projectile/plas-1-scorcher'}}},'RESTRICTED_MEMBER')
refused({id='dev/x',base=talon,changes={{member='direct_damage',from='output/v1/projectile/plas-1-scorcher',x=1}}},
    'INVALID_DEFINITION')
-- A donor whose live direct damage is not its catalogued one is refused (the donor row is re-proven live).
W.projectile_row(186,put(RAILGUN,0x3C,le(65,4)))
refused({id='dev/x',base=talon,changes={{member='direct_damage',from='output/v1/projectile/rs-422-railgun'}}},
    'DONOR_CHANGED')
W.projectile_row(186,RAILGUN)
-- A settings entry that does not carry its type never becomes a base.
W.projectile_row(144,put(TALON,0,le(143,4)))
refused({id='dev/x',base=talon},'UNKNOWN_PROJECTILE')
W.projectile_row(144,TALON)
-- An adapter that cannot own memory refuses instead of falling back to a vanilla row.
local owned=W.runtime.owned_block
W.runtime.owned_block=nil
refused(SPEC,'CUSTOM_PROJECTILE_UNAVAILABLE')
W.runtime.owned_block=owned
assert(W.read(144 and W.projectile_row(144),272)==TALON)
return 'ok'
''')

    def test_a_custom_projectile_spawns_only_when_every_guard_holds(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
hd2.events.run_as('mods/t/proof',function()hd2.events.on('mission_started',function()end)end)
assert(fire().code=='NOT_IN_MISSION')
mission({host=false})
assert(fire().code=='HOST_ONLY')
W.state(3);tick()
mission({host=true})
local a=fire()
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
local shot=W.runtime.custom_projectiles[1]
assert(shot.row==def.row.address and shot.kind==2 and shot.source==100 and shot.owner==100,shot.row)
assert(shot.peer==LOCAL and shot.dz==-1 and shot.dx==0 and shot.x==1 and shot.z==3)
local layout=shot.layout
assert(layout.position==0 and layout.direction==8 and layout.row==16 and layout.source==24 and layout.owner==28
    and layout.creditor==32 and layout.kind==40)
assert(shot.bytes==def.bytes and a.slot==41 and a.report.status=='VALID'and a.base_unchanged)
assert(count('custom projectile dev/talon_hybrid_proof base type=144 base identity=LAS-58 Talon custom row=0x')==1)
assert(count('hybrid compatibility=VALID')==1 and count('native spawn result=slot 41 vanilla base row unchanged')==1)
-- Nothing was fired through the catalogued projectile wrapper, and no vanilla row changed.
assert(#W.runtime.projectiles==0 and W.read(T,272)==TALON and W.read(S,272)==SCORCHER and W.read(R,272)==RAILGUN)
return 'ok'
''')

    def test_a_changed_row_function_or_thread_refuses_before_any_call(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=true})
assert(fire().status=='requested')
local function refused(expect)
    local a=fire()
    assert(a.status=='refused'and a.code==expect,tostring(a.code)..' '..tostring(a.reason)..' (expected '..expect..')')
    return a
end
-- Tampering with the Runtime-owned row in a late-lookup member (never done by Runtime) refuses.
W.write(def.row.address+0xF4,le(3,4))
local a=refused('HYBRID_INCOMPATIBLE')
assert(a.reason:find('collision_filter',1,true)and a.report.status=='INVALID',a.reason)
W.write(def.row.address+0xF4,le(2,4))
-- The live base row changed in a restricted member (another mod's edit): the definition no longer matches it.
W.write(T+0x1C,le(8,4))
assert(refused('HYBRID_INCOMPATIBLE').reason:find('pellet_count',1,true))
W.write(T+0x1C,le(1,4))
-- A copied member of the base changed: still valid (the row carries its own), reported as a changed base.
W.write(T+0x48,le(1,8))
local changed=fire()
assert(changed.status=='requested'and changed.base_unchanged==false)
assert(count('vanilla base row CHANGED since the definition')==1)
W.write(T,TALON)
-- The base row no longer resolves.
local entry=W.read(W.GAME+require('hd2runtime/domains/event_natives').projectile.settingsTable+144*8,8)
W.write(W.GAME+require('hd2runtime/domains/event_natives').projectile.settingsTable+144*8,string.rep('\0',8))
refused('UNKNOWN_PROJECTILE')
W.write(W.GAME+require('hd2runtime/domains/event_natives').projectile.settingsTable+144*8,entry)
-- The projectile system inactive.
W.projectiles_active(false);refused('NOT_IN_MISSION');W.projectiles_active(true)
-- Outside the game update (not on the game thread): refused by the native layer itself.
local world=assert(world_module.open())
local result,why=world_module.spawn_projectile_row(world,{row=def.row.address,base_type=144,x=1,y=2,z=3,dx=1,dy=0,
    dz=0,source=100,owner=100,peer_lo=0,peer_hi=0})
assert(result==nil and why:find('^NOT_GAME_THREAD'),why)
-- A changed SpawnProjectile prologue.
local rows_domain=require('hd2runtime/domains/projectile_rows')
W.write(W.GAME+rows_domain.spawn.rva,string.char(0xCC))
refused('CUSTOM_PROJECTILE_UNAVAILABLE')
W.write(W.GAME+rows_domain.spawn.rva,b.unhex(rows_domain.spawn.prologue))
-- A changed late-lookup pin (re-proven once per loaded game.dll: a fresh world).
local pin
for _,p in ipairs(rows_domain.pins)do if p.label:find('+0xF4',1,true)then pin=p end end
W.write(W.GAME+pin.rva,string.char(0xCC))
world_module.set_runtime(W.runtime)
a=refused('CUSTOM_PROJECTILE_UNAVAILABLE')
assert(a.reason:find('native projectile structure changed',1,true),a.reason)
W.write(W.GAME+pin.rva,b.unhex(pin.hex))
world_module.set_runtime(W.runtime)
-- An adapter that cannot call game functions.
local native=W.runtime.native_spawn_projectile
W.runtime.native_spawn_projectile=nil
refused('CUSTOM_PROJECTILE_UNAVAILABLE')
W.runtime.native_spawn_projectile=native
-- Invalid requests and an unknown definition.
hd2.events.run_as('mods/t/proof',function()
    assert(actions.spawn_custom_projectile('dev/none',{position={x=0,y=0,z=0},direction={x=1,y=0,z=0}}).code
        =='UNKNOWN_CUSTOM_PROJECTILE')
end)
assert(fire({position={x=0/0,y=0,z=0},direction={x=1,y=0,z=0}}).code=='INVALID_POSITION')
assert(fire({position={x=0,y=0,z=0},direction={x=0,y=0,z=0}}).code=='INVALID_DIRECTION')
assert(#W.runtime.custom_projectiles==2,#W.runtime.custom_projectiles)
assert(W.read(T,272)==TALON and W.read(S,272)==SCORCHER and W.read(R,272)==RAILGUN)
return 'ok'
''')

    def test_packages_load_first_and_the_rate_limit_is_shared(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=true})
-- One burst inside one update: the projectile rate limit (12 at once) applies to custom projectiles too.
local codes={}
in_update(function()
    hd2.events.run_as('mods/t/proof',function()
        for _=1,13 do
            codes[#codes+1]=actions.spawn_custom_projectile(SPEC.id,{position={x=1,y=2,z=3},
                direction={x=1,y=0,z=0}}).code or'ok'
        end
    end)
end)
assert(codes[12]=='ok'and codes[13]=='RATE_LIMITED',table.concat(codes,','))
assert(#W.runtime.custom_projectiles==12)
actions.reset_for_tests()
-- Every package of the definition (the base's and each donor's) must be resident first.
for package in pairs(require('hd2runtime/domains/package_residency').packages)do W.runtime.packages[package]='absent'end
local a=fire()
assert(a.status=='waiting_for_assets',a.status)
tick(8)
-- The fixture has no package system to request through: the gate refuses, and nothing is spawned.
assert(a.status=='refused'and a.code=='ASSET_UNAVAILABLE',a.status..' '..tostring(a.code))
assert(#W.runtime.custom_projectiles==12)
return 'ok'
''')


class AimTests(unittest.TestCase):
    """The read-only pose helpers the development proof aims with (runtime/event_world.lua unit_pose, entity_unit)."""

    def test_unit_pose_and_the_held_weapon_unit(self):
        self.assertEqual(run(PROOF + r'''
mission({host=true})
local world=assert(world_module.open())
-- The avatar (fixture unit 7100): an upright identity rotation at the origin.
local body=assert(world_module.unit_pose(world,7100))
assert(body.forward.y==1 and body.up.z==1 and body.right.x==1 and body.position.x==0)
-- A weapon pitched up by about 5.7 degrees, held 1.1 m up and 0.25 m to the right.
local s,c=0.0998,0.9950
W.unit(8605,0.25,0.05,1.1,{{x=1,y=0,z=0},{x=0,y=c,z=s},{x=0,y=-s,z=c}})
W.hold(100,605,LIBERATOR,1,8605)
assert(world_module.entity_unit(world,605)==8605 and world_module.entity_unit(world,999)==nil)
local weapon=assert(world_module.unit_pose(world,8605))
assert(math.abs(weapon.forward.z-s)<1e-4 and math.abs(weapon.position.z-1.1)<1e-6)
-- A scaled or corrupt rotation is refused (nil), never used as an aim.
W.unit(8606,0,0,0,{{x=2,y=0,z=0},{x=0,y=1,z=0},{x=0,y=0,z=1}})
assert(world_module.unit_pose(world,8606)==nil)
W.unit(8607,0,0,0,{{x=1,y=0,z=0},{x=1,y=0,z=0},{x=0,y=0,z=1}})
assert(world_module.unit_pose(world,8607)==nil)
-- A destroyed unit has no pose; unit_position still agrees with the pose translation.
W.remove_unit(8605)
assert(world_module.unit_pose(world,8605)==nil)
assert(world_module.unit_position(world,7100).z==body.position.z)
return 'ok'
'''), b'ok')


REPLACEMENT = r'''
local replacement=require('hd2runtime/runtime/projectile_replacement')
replacement.reset_for_tests()
local CARRIER='output/v1/projectile/td-110-maelstrom-slot-2'
local REPRIMAND='94BD931B5FB4EE95'
-- The carrier: type 324, no effect, damage type 0, no impact (+0x90) or expiry (+0x9C) explosion.
local CARRIER_ROW=row_of(324,0,string.rep('\0',8),0)
local C=W.projectile_row(324,CARRIER_ROW)
local function bind(definition,opts)
    local action
    hd2.events.run_as('mods/t/replacement',function()
        action=actions.replace_projectiles(definition,opts or{carrier=CARRIER,weapon='SMG-32 Reprimand'})
    end)
    return action
end
-- A carrier the local player's Reprimand (entity 605) fired: at (10, 20, 1.5) after 8 m along +Y.
local function carrier(overrides)
    local spec={type=324,position={x=10,y=20,z=1.5},velocity={x=0,y=480,z=0},speed=500,distance=8,
        creditor=LOCAL,owner=100,source=605}
    for key,value in pairs(overrides or{})do spec[key]=value end
    return W.spawn_projectile(spec)
end
'''


class ProjectileReplacementTests(unittest.TestCase):
    """Weapon projectile replacement (runtime/projectile_replacement.lua) on the offline fixture world."""

    def lua(self, body):
        self.assertEqual(run(PROOF + REPLACEMENT + body), b'ok')

    def test_the_pool_reader_reads_what_spawn_projectile_wrote(self):
        self.lua(r'''
mission({host=true})
local world=assert(world_module.open())
local counter,system=world_module.projectile_counter(world)
assert(counter==0 and system==W.projectile_system,tostring(counter))
local first=carrier()
local second=carrier({type=144,position={x=-1,y=-2,z=-3},velocity={x=0,y=0,z=-1300},speed=1300,distance=0,
    lifetime=6,creditor=OTHER,owner=200,source=201})
counter=world_module.projectile_counter(world)
local types=assert(world_module.projectile_types(world,system,0,counter))
assert(counter==2 and #types==2 and types[1].slot==first and types[1].type==324 and types[2].type==144)
local record=assert(world_module.projectile_slot(world,system,first))
assert(record.position.x==10 and record.position.y==20 and record.position.z==1.5 and record.velocity.y==480)
assert(record.speed==500 and record.distance==8 and record.lifetime==0 and record.owner==100 and record.source==605)
assert(string.format('%08X%08X',record.creditor_hi,record.creditor_lo)==LOCAL)
record=assert(world_module.projectile_slot(world,system,second))
assert(record.lifetime==6 and record.owner==200 and string.format('%08X%08X',record.creditor_hi,record.creditor_lo)
    ==OTHER)
-- The pool is a ring: slots wrap at 2048, read in two parts.
W.pool_counter(2047)
carrier();carrier()
types=assert(world_module.projectile_types(world,system,2047,2))
assert(types[1].slot==2047 and types[2].slot==0 and types[1].type==324 and types[2].type==324)
assert(world_module.projectile_types(world,system,0,2049)==nil,'never more than the pool')
-- Inactive, and a changed pool pin (re-proven once per loaded game.dll: a fresh world).
W.projectiles_active(false)
local none,why=world_module.projectile_counter(world)
assert(none==nil and why:find('^NOT_IN_MISSION'),why)
W.projectiles_active(true)
local pin=require('hd2runtime/domains/projectile_rows').pool.pins[1]
W.write(W.GAME+pin.rva,string.char(0xCC))
world_module.set_runtime(W.runtime)
none,why=world_module.projectile_counter(assert(world_module.open()))
assert(none==nil and why:find('^PROJECTILE_POOL_UNAVAILABLE: native projectile pool changed'),why)
W.write(W.GAME+pin.rva,b.unhex(pin.hex))
return 'ok'
''')

    def test_each_carrier_the_local_reprimand_fires_is_replaced_from_its_spawn_point(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=true})
W.hold(100,605,REPRIMAND,1)
W.hold(300,606,LIBERATOR,1)
carrier()                                       -- fired before the binding: never replaced
local action=bind(def)
assert(action.status=='bound',tostring(action.code)..' '..tostring(action.reason))
assert(count('projectile replacement: TD-110 Maelstrom / slot_2 (type 324) shots from the SMG-32 Reprimand are '
    ..'replaced by custom projectile dev/talon_hybrid_proof')==1)
tick()
assert(#W.runtime.custom_projectiles==0,'a binding starts from the counter it reads')
carrier()
tick()
local shot=W.runtime.custom_projectiles[1]
assert(#W.runtime.custom_projectiles==1 and shot.row==def.row.address and shot.bytes==def.bytes)
-- From the carrier's spawn point (its position less the 8 m it travelled), along its direction, credited to the
-- local player's avatar.
assert(shot.x==10 and shot.y==12 and shot.z==1.5 and shot.dx==0 and shot.dy==1 and shot.dz==0,shot.y)
assert(shot.source==100 and shot.owner==100 and shot.peer==LOCAL and shot.kind==2)
assert(count('TD-110 Maelstrom / slot_2 shot 1: carrier slot 1 (type 324) at (10.00, 20.00, 1.50) travelled 8.00 m')
    ==1)
assert(count('source 605 (SMG-32 Reprimand); custom dev/talon_hybrid_proof from (10.00, 12.00, 1.50) along '
    ..'(0.00, 1.00, 0.00) -> slot 41')==1)
-- Not replaced: another projectile type, another player's carrier, a carrier from another weapon.
carrier({type=144});carrier({creditor=OTHER,owner=300,source=606});carrier({source=606})
-- A carrier that already hit something right away still leads back to the muzzle.
carrier({position={x=0,y=0.5,z=1},velocity={x=0,y=0,z=-50},distance=0.5})
tick()
assert(#W.runtime.custom_projectiles==2)
shot=W.runtime.custom_projectiles[2]
assert(shot.z==1.5 and shot.dz==-1,shot.z)
local status=replacement.list()[1]
assert(status.replaced==2 and status.foreign==1 and status.other_weapons==1 and status.refused==0)
-- Several in one update, wrapping the ring: each replaced once, in order.
W.pool_counter(2046)
tick()
for i=1,4 do carrier({position={x=i,y=20,z=1.5}})end
tick()
assert(#W.runtime.custom_projectiles==6 and W.runtime.custom_projectiles[6].x==4)
-- A new mission restarts the counter: nothing older is replaced, new carriers are.
W.state(3);tick()
W.pool_counter(0)
W.state(4,{host=true});tick()
assert(#W.runtime.custom_projectiles==6)
carrier();tick()
assert(#W.runtime.custom_projectiles==7)
-- Unbound: carriers stay carriers, and the counts are logged.
assert(actions.stop_replacing_projectiles(CARRIER)==true and replacement.list()[1]==nil)
assert(count('TD-110 Maelstrom / slot_2 -> dev/talon_hybrid_proof: 7 carriers, 7 replaced (')==1)
assert(count('0 dropped (rate), 0 refused, 1 not the local player\'s, 1 other weapons')==1)
carrier();tick()
assert(#W.runtime.custom_projectiles==7)
assert(W.read(C,272)==CARRIER_ROW and W.read(T,272)==TALON,'no vanilla row is written')
return 'ok'
''')

    def test_the_rate_limit_and_the_authority_bound_every_update(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=true})
W.hold(100,605,REPRIMAND,1)
assert(bind(def).status=='bound')
tick()
-- At most MAX_PER_TICK in one update, and a burst of BURST: the rest are dropped, never queued.
for _=1,30 do carrier()end
tick()
assert(#W.runtime.custom_projectiles==replacement.MAX_PER_TICK,#W.runtime.custom_projectiles)
assert(replacement.list()[1].dropped==30-replacement.MAX_PER_TICK)
for _=1,30 do carrier()end
tick(1,0)
assert(#W.runtime.custom_projectiles==replacement.BURST,'the burst is spent')
-- No longer the host: carriers are counted as refused and logged once.
W.state(4,{host=false});tick()
carrier();carrier();tick()
assert(#W.runtime.custom_projectiles==replacement.BURST)
assert(count('carrier shots are not replaced: not the host')==1)
return 'ok'
''')

    def test_a_mode_aware_binding_never_replaces_the_normal_projectile_and_measures_the_cadence(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=true})
W.hold(100,605,REPRIMAND,1)
W.hold(300,606,LIBERATOR,1)
local NATIVE=W.projectile_row(123,row_of(123,96,string.rep('\0',8),0))
local a=bind(def,{carrier=CARRIER,weapon='SMG-32 Reprimand',unreplaced='output/v1/projectile/smg-32-reprimand',
    detail_logs=math.huge})
assert(a.status=='bound',tostring(a.code))
assert(count('SMG-32 Reprimand (type 123) shots are counted and never replaced')==1)
tick()
-- Normal mode: the native projectile is counted and logged, never replaced.
carrier({type=123});carrier({type=123})
tick()
assert(#W.runtime.custom_projectiles==0)
assert(count('normal mode: SMG-32 Reprimand shot 1: native projectile slot 0 (type 123) at (10.00, 20.00, 1.50) '
    ..'travelled 8.00 m; owner 100, source 605 (SMG-32 Reprimand) -> no replacement')==1)
assert(count('normal mode: SMG-32 Reprimand shot 2:')==1)
-- Another player's or another weapon's native projectile is not this weapon's normal mode.
carrier({type=123,creditor=OTHER,owner=300,source=606});carrier({type=123,source=606})
tick()
assert(replacement.list()[1].normal==2)
tick(5,0.1)                                     -- a pause: the next burst is the custom one alone
-- Custom mode at 1500 rpm: one shot every 0.04 s for a 50-round magazine, every shot replaced and logged.
for _=1,50 do carrier();tick(1,0.04)end
assert(#W.runtime.custom_projectiles==50,#W.runtime.custom_projectiles)
assert(count('custom mode: TD-110 Maelstrom / slot_2 shot 50: carrier slot')==1)
tick(10,0.1)
local status=replacement.list()[1]
assert(status.replaced==50 and status.dropped==0 and status.refused==0 and status.last_mode=='custom')
assert(status.last_burst.shots==50 and status.last_burst.custom==50 and math.abs(status.last_burst.rpm-1500)<1,
    tostring(status.last_burst.rpm))
assert(count('SMG-32 Reprimand burst: 50 shots (50 custom, 0 normal) over 1.96 s = 1500 rpm')==1)
-- Switching modes inside one burst: both kinds counted in it.
carrier({type=123});tick(1,0.1);carrier();tick(1,0.1);carrier({type=123});tick(5,0.1)
status=replacement.list()[1]
assert(status.last_burst.shots==3 and status.last_burst.normal==2 and status.last_burst.custom==1)
assert(status.normal==4 and status.replaced==51 and status.last_mode=='normal')
assert(W.read(NATIVE,272)==row_of(123,96,string.rep('\0',8),0),'the native row is never written')
-- The unreplaced projectile must be another type than the carrier.
assert(bind(def,{carrier=CARRIER,unreplaced=CARRIER}).code=='INVALID_UNREPLACED')
assert(bind(def,{carrier=CARRIER,detail_logs=-1}).code=='INVALID_DETAIL_LOGS')
return 'ok'
''')

    def test_a_source_bound_carrier_is_replaced_once_confirmed_and_the_native_projectile_watched(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=true})
W.pool_spawns(true)
local HOST='output/v1/projectile/exo-45-patriot-exosuit-right-gun'
local GUN,EXOSUIT,SENTRY='08F6089289C83D22','1111111111111111','2222222222222222'
W.hold(300,700,GUN,1);W.hold(301,701,EXOSUIT,1);W.hold(302,702,SENTRY,1);W.hold(100,605,REPRIMAND,1)
local NATIVE=assert(custom.output(HOST,false)).type
local a=bind(def,{carrier=CARRIER,source=HOST,suppressed=HOST,credit='local_or_none',attribute=true,
    detail_logs=math.huge})
assert(a.status=='bound',tostring(a.code)..' '..tostring(a.reason))
assert(count('shots from EXO-45 Patriot Exosuit / right_gun ('..HOST..', native type '..NATIVE..') are replaced by '
    ..'custom projectile dev/talon_hybrid_proof')==1)
assert(count('credited to the local peer or to no peer; the native EXO-45 Patriot Exosuit / right_gun projectile '
    ..'(type '..NATIVE..') must not appear')==1)
tick()
-- A minigun carrier credited to no peer, owned by the exosuit: replaced, with its attribution and latency logged.
carrier({source=700,owner=701,creditor='0000000000000000'})
tick()
assert(#W.runtime.custom_projectiles==1)
assert(count('; creditor none; owner 701 (type '..EXOSUIT..'); source 700 (type '..GUN..' EXO-45 Patriot Exosuit / '
    ..'right_gun); projectile type 324 in EXO-45 Patriot Exosuit / right_gun ('..HOST..', native type '..NATIVE
    ..'); latency one game update (dt 125.0 ms), carrier flew 8.00 m = 16.7 ms before the read')==1)
-- The next update finds the custom projectile in the pool: exactly one per carrier.
tick()
local status=replacement.list()[1]
assert(status.carriers==1 and status.replaced==1 and status.confirmed==1 and status.unconfirmed==0)
-- 1200 rpm for 3 s: 60 carriers, 60 replacements, 60 confirmed, none dropped; the burst reads 1200 rpm.
tick(5,0.1)
for _=1,60 do carrier({source=700,owner=100,creditor=LOCAL});tick(1,0.05)end
tick(10,0.1)
status=replacement.list()[1]
assert(status.carriers==61 and status.replaced==61 and status.confirmed==61 and status.dropped==0,status.dropped)
assert(#W.runtime.custom_projectiles==61 and math.abs(status.last_burst.rpm-1200)<1,status.last_burst.rpm)
assert(count('EXO-45 Patriot Exosuit / right_gun (output/v1/projectile/exo-45-patriot-exosuit-right-gun, native type '
    ..NATIVE..') burst: 60 shots (60 custom, 0 native) over 2.95 s = 1200 rpm')==1)
-- Other sources and other players: not replaced. The native bullet from another source (a sentry) is not counted.
carrier({source=605});carrier({source=702});carrier({source=700,creditor=OTHER})
carrier({type=NATIVE,source=702})
tick();tick()
status=replacement.list()[1]
assert(status.replaced==61 and status.other_weapons==2 and status.foreign==1 and status.normal==0)
-- The native bullet from the minigun itself: a suppression failure, logged and never replaced.
carrier({type=NATIVE,source=700,owner=100,creditor=LOCAL})
tick()
assert(count('SUPPRESSION FAILED: native EXO-45 Patriot Exosuit / right_gun projectile 1: slot')==1)
assert(replacement.list()[1].normal==1 and #W.runtime.custom_projectiles==61)
actions.stop_replacing_projectiles(CARRIER)
assert(count('-> dev/talon_hybrid_proof: 61 carriers, 61 replaced (61 confirmed in the pool, 0 not), 0 dropped (rate), '
    ..'0 refused, 1 not the local player\'s, 2 other weapons; 1 native EXO-45 Patriot Exosuit / right_gun shots seen '
    ..'(suppression FAILED); latency one game update: mean')==1)
-- Refusals of the new options.
assert(bind(def,{carrier=CARRIER,source='output/v1/projectile/none'}).code=='UNKNOWN_PROJECTILE')
assert(bind(def,{carrier=CARRIER,unreplaced=HOST,suppressed=HOST}).code=='INVALID_UNREPLACED')
assert(bind(def,{carrier=CARRIER,suppressed=CARRIER}).code=='INVALID_UNREPLACED')
assert(bind(def,{carrier=CARRIER,credit='anyone'}).code=='INVALID_CREDIT')
return 'ok'
''')

    def test_unsafe_carriers_unknown_definitions_and_clients_are_refused(self):
        self.lua(r'''
local def=assert(custom.define(SPEC))
mission({host=false})
assert(bind(def).code=='HOST_ONLY')
W.state(4,{host=true});tick()
assert(bind('dev/none').code=='UNKNOWN_CUSTOM_PROJECTILE')
assert(bind(def,{carrier='output/v1/projectile/none'}).code=='UNKNOWN_PROJECTILE')
assert(bind(def,{carrier=CARRIER,weapon=5}).code=='INVALID_WEAPON')
-- A carrier with an explosion could be skipped into while it is pending: refused.
W.projectile_row(324,put(CARRIER_ROW,0x90,le(158,4)))
local a=bind(def)
assert(a.code=='CARRIER_HAS_EXPLOSION'and a.reason:find('impact',1,true),tostring(a.reason))
W.projectile_row(324,put(CARRIER_ROW,0x9C,le(12,4)))
assert(bind(def).code=='CARRIER_HAS_EXPLOSION')
W.projectile_row(324,CARRIER_ROW)
-- The definition's packages load first; the fixture has none to load, so the gate refuses.
for package in pairs(require('hd2runtime/domains/package_residency').packages)do W.runtime.packages[package]='absent'end
a=bind(def)
assert(a.status=='waiting_for_assets')
tick(800)
assert(a.status=='refused'and a.code=='ASSET_UNAVAILABLE',a.status)
assert(replacement.list()[1]==nil)
return 'ok'
''')


def proof_addon():
    """The development proof's addon exactly as the SDK builds it."""
    folder = ROOT / 'proof/CustomProjectileRowProof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class ProofAddonTests(unittest.TestCase):
    def test_the_avatar_is_followed_across_waiting_death_reinforcement_and_missions(self):
        resource, addon = proof_addon()
        self.assertEqual(run(PROOF + COMPONENT_WORLD + 'local ADDON=' + lua(addon) + '\nlocal RESOURCE='
            + lua(resource) + r'''
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(key)keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;tick()end
assert(loadstring(ADDON,'@'..RESOURCE))()
local function fired()return #W.runtime.custom_projectiles+#W.runtime.projectiles end
-- A mission announced before the Helldiver has landed: definitions ready, the avatar awaited, keys refused.
W.players({{peer=LOCAL}},LOCAL)
W.state(4,{host=true});tick()
assert(count('mission started: 5 of 5 custom projectiles defined; vanilla table baseline taken (350 rows); '
    ..'waiting for avatar')==1)
press('F7');press('F8')
assert(count('F7: waiting for avatar (the player has no avatar now)')==1)
assert(count('F8: waiting for avatar (the player has no avatar now)')==1 and fired()==0)
tick(90)
assert(count('still waiting for avatar after 10 s: the player has no avatar now')==1)
-- The avatar lands: announced once, and every key works without a restart.
W.players({{peer=LOCAL,avatar=100}},LOCAL)
W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
W.unit(7100,0,0,0)
tick(8)
assert(count('avatar became available: entity 100 (via the player list); F5 F6 F7 F8 F10 F11 ready')==1)
for _,key in ipairs({'F7','F5','F6','F10','F11','F8'})do press(key)end
assert(#W.runtime.custom_projectiles==5 and #W.runtime.projectiles==1,fired())
assert(count('became available')==1,'announced once')
-- Death: the avatar is lost and keys wait again.
W.set(100,{life=2,health=0})
tick(8)
assert(count('avatar lost: avatar entity 100 is dead; waiting for avatar')==1)
press('F5')
assert(count('F5: waiting for avatar (avatar entity 100 is dead)')==1 and #W.runtime.custom_projectiles==5)
-- Reinforcement: a new avatar entity in the same player slot.
W.players({{peer=LOCAL,avatar=101}},LOCAL)
W.add{entity=101,type=W.AVATAR,unit=7101,health=125,owned=true}
W.unit(7101,5,5,0)
tick(8)
assert(count('avatar restored: entity 101 replaces entity 100 (via the player list); F5 F6 F7 F8 F10 F11 ready')==1)
press('F6')
local shot=W.runtime.custom_projectiles[6]
assert(shot and shot.x==5 and shot.y==6 and shot.bytes==custom.get('dev/talon_ballistics').bytes)
-- The mission ends; the next one needs no restart and redefines nothing.
W.state(3);tick(8)
assert(count('mission ended: the custom projectiles stay defined for the next one')==1)
press('F7')
assert(count('F7: waiting for avatar (not in a mission)')==1)
W.state(4,{host=true});tick(8)
assert(count('mission started: 5 of 5 custom projectiles defined')==2)
assert(count('defined: custom projectile dev/talon_visual')==1,'definitions are kept, not rebuilt')
assert(count('avatar became available: entity 101')==1)
press('F10')
assert(#W.runtime.custom_projectiles==7)
-- An avatar Runtime's action layer does not pick (not among the owned health records it scans): found through the
-- player list, and the note says so once.
W.players({{peer=LOCAL,avatar=102}},LOCAL)
W.add{entity=102,type=W.AVATAR,unit=7102,health=125,owned=false}
W.unit(7102,0,0,0)
W.set(101,{life=2,health=0})
tick(8)
assert(count('avatar restored: entity 102 replaces entity 101 (via the player list)')==1)
assert(count('note: Runtime\'s action layer does not see entity 102')==1)
tick(8)
assert(count('does not see entity 102')==1,'the note is logged once per avatar')
return 'ok'
'''), b'ok')

    def test_f7_and_f8_leave_from_the_weapon_and_f9_verifies_the_table(self):
        resource, addon = proof_addon()
        self.assertEqual(run(PROOF + COMPONENT_WORLD + 'local ADDON=' + lua(addon) + '\nlocal RESOURCE='
            + lua(resource) + r'''
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(key)keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;tick()end
assert(loadstring(ADDON,'@'..RESOURCE))()
assert(count('F7 visual, F5 damage, F6 ballistics, F10 impact explosion, F11 all four')==1)
mission({host=true})
for _,id in ipairs({'dev/talon_visual','dev/talon_damage','dev/talon_ballistics','dev/talon_impact',
        'dev/talon_combined'})do
    assert(count('defined: custom projectile '..id..' base type=144')==1,id)
end
assert(count('mission started: 5 of 5 custom projectiles defined; vanilla table baseline taken (350 rows)')==1)
-- The weapon in hand: pitched up, 1.1 m up and 0.25 m to the right of the avatar.
local s,c=0.0998,0.9950
W.unit(8605,0.25,0.05,1.1,{{x=1,y=0,z=0},{x=0,y=c,z=s},{x=0,y=-s,z=c}})
W.hold(100,605,LIBERATOR,1,8605)
press('F7');press('F8')
local custom_shot,vanilla=W.runtime.custom_projectiles[1],W.runtime.projectiles[1]
assert(custom_shot and vanilla,'both shots fired')
for _,shot in ipairs({custom_shot,vanilla})do
    assert(math.abs(shot.x-0.25)<1e-3 and math.abs(shot.y-(0.05+c))<1e-3 and math.abs(shot.z-(1.1+s))<1e-3,
        shot.x..' '..shot.y..' '..shot.z)
    assert(math.abs(shot.dx)<1e-3 and math.abs(shot.dy-c)<1e-3 and math.abs(shot.dz-s)<1e-3)
end
assert(vanilla.type==144 and custom_shot.kind==2)
assert(custom_shot.bytes==custom.get('dev/talon_visual').bytes)
assert(count('F7: dev/talon_visual (visual from PLAS-1 Scorcher) from')==1)
assert(count('[held weapon pose]: requested')==2,'F7 and F8 name their origin')
-- Each other key fires its own variant, and its log names the component and its source.
local expect={F5={'dev/talon_damage','damage from RS-422 Railgun'},
    F6={'dev/talon_ballistics','ballistics from GL-21 Grenade Launcher'},
    F10={'dev/talon_impact','impact_explosion from R-36 Eruptor'},
    F11={'dev/talon_combined','visual from PLAS-1 Scorcher + damage from RS-422 Railgun + impact_explosion from '
        ..'R-36 Eruptor + ballistics from GL-21 Grenade Launcher'}}
local fired=#W.runtime.custom_projectiles
for _,key in ipairs({'F5','F6','F10','F11'})do
    press(key)
    fired=fired+1
    local shot=W.runtime.custom_projectiles[fired]
    assert(shot and shot.bytes==custom.get(expect[key][1]).bytes,key)
    assert(count(key..': '..expect[key][1]..' ('..expect[key][2]..') from')==1,key)
end
-- The weapon is not in the hands (4.7 m away, facing back: the pose seen just before a death): the avatar's facing.
W.unit(8605,0,-4.7,0.9,{{x=-1,y=0,z=0},{x=0,y=-1,z=0},{x=0,y=0,z=1}})
press('F7')
local fallback=W.runtime.custom_projectiles[fired+1]
assert(fallback.x==0 and fallback.y==1 and math.abs(fallback.z-1.4)<1e-6 and fallback.dy==1 and fallback.dz==0)
assert(count('avatar facing (the held weapon is not in the hands (4.8 m from the avatar, heading alignment -1.00)')==1)
-- Nothing in hand.
W.hold(100,0)
press('F8')
assert(W.runtime.projectiles[2].dy==1 and count('avatar facing (nothing in hand)')==1)
-- F9: every vanilla row and the table edges as at the mission start; every custom row unchanged.
press('F9')
assert(count('F9: 350 vanilla rows compared: all byte-identical to the mission start; row 144 byte-identical; '
    ..'table entries 0 and 351 unchanged')==1)
assert(count('unchanged since its definition')==5)
W.write(T+0x20,le(1,4))
press('F9')
assert(count('CHANGED: 144')==1,'a changed vanilla row is reported')
return 'ok'
'''), b'ok')


COMPONENT_WORLD = r'''
local outputs=require('hd2runtime/domains/attack_outputs').outputs
local eruptor_output=outputs['output/v1/projectile/r-36-eruptor']
local grenade_output=outputs['output/v1/projectile/gl-21-grenade-launcher']
local IMPACT=eruptor_output.slotFields['projectile.impact_explosion'].currentDefault
local ERUPTOR=put(row_of(eruptor_output.currentDefault,70,le(0x11111111,4)..le(0x22222222,4),0.03),0x90,le(IMPACT,4))
-- The GL-21: a grenade lob (100 m/s, gravity 1, drag 1.2) and a unit (its visible grenade).
local GRENADE=row_of(grenade_output.currentDefault,80,le(0x33333333,4)..le(0x44444444,4),0.02)
for _,v in ipairs({{0x18,f32(40)},{0x20,f32(100)},{0x24,f32(50)},{0x28,f32(1.2)},{0x2C,f32(1)},{0x38,f32(0.1)},
        {0x40,f32(0.5)},{0x80,le(0x5555,8)}})do GRENADE=put(GRENADE,v[1],v[2])end
local E=W.projectile_row(eruptor_output.currentDefault,ERUPTOR)
local G=W.projectile_row(grenade_output.currentDefault,GRENADE)
local function owned_offsets(ids)
    local owned={}
    for _,id in ipairs(ids)do
        for _,member in ipairs(rows.component(id).members)do
            for o=member.offset,member.offset+member.width-1 do owned[o]=true end
        end
    end
    return owned
end
local function differs_only_in(def,ids)
    local owned=owned_offsets(ids)
    for o=0,271 do
        if not owned[o]then assert(def.bytes:byte(o+1)==TALON:byte(o+1),def.id..' changed byte '..o)end
    end
end
local function packages(def)
    local out={}
    for _,dependency in ipairs(def.dependencies)do out[#out+1]=dependency.key end
    return table.concat(out,',')
end
'''


class ComponentCompositionTests(unittest.TestCase):
    """The component proof variants on the offline fixture world."""

    def lua(self, body):
        self.assertEqual(run(PROOF + COMPONENT_WORLD + body), b'ok')

    def test_each_variant_differs_only_in_its_component(self):
        self.lua(r'''
local variants={}
for _,spec in ipairs(custom.DEVELOPMENT_VARIANTS)do variants[spec.id]=spec end
local expect={
    ['dev/talon_visual']={{'visual'},'player_weapon/LAS-58 Talon,player_weapon/PLAS-1 Scorcher',
        'spawn_effect,spawn_effect_parameter'},
    ['dev/talon_damage']={{'damage'},'player_weapon/LAS-58 Talon,support_weapon/RS-422 Railgun','direct_damage'},
    ['dev/talon_ballistics']={{'ballistics'},'player_weapon/LAS-58 Talon',
        'diameter,speed,mass,drag,gravity,lifetime_variance,penetration_slowdown'},
    ['dev/talon_impact']={{'impact_explosion'},'player_weapon/LAS-58 Talon,player_weapon/R-36 Eruptor',
        'impact_explosion'},
    ['dev/talon_combined']={{'visual','damage','impact_explosion','ballistics'},'player_weapon/LAS-58 Talon,'
        ..'player_weapon/PLAS-1 Scorcher,support_weapon/RS-422 Railgun,player_weapon/R-36 Eruptor',
        'spawn_effect,spawn_effect_parameter,direct_damage,impact_explosion,diameter,speed,mass,drag,gravity,'
        ..'lifetime_variance,penetration_slowdown'},
}
assert(#custom.DEVELOPMENT_VARIANTS==5)
for id,want in pairs(expect)do
    local def,code,reason=custom.define(assert(variants[id],id))
    assert(def,id..': '..tostring(code)..' '..tostring(reason))
    assert(def.validation.status=='VALID',id..' '..def.validation.summary)
    differs_only_in(def,want[1])
    assert(packages(def)==want[2],id..' packages '..packages(def))
    local labels={}
    for _,change in ipairs(def.changes)do labels[#labels+1]=change.label end
    assert(table.concat(labels,',')==want[3],id..' '..table.concat(labels,','))
    for _,summary in ipairs(def.components)do assert(summary.differs,id..' '..summary.id)end
end
-- The copied values are the donors' own.
local combined=custom.get('dev/talon_combined')
assert(combined.bytes:sub(0x21,0x24)==f32(100)and combined.bytes:sub(0x2D,0x30)==f32(1))
assert(b.u32(combined.bytes,0x90)==IMPACT and b.u32(combined.bytes,0x3C)==64)
assert(combined.bytes:sub(0x49,0x50)==SCORCHER:sub(0x49,0x50))
-- The GL-21 has a unit: its ballistics are copied, its unit is not.
assert(custom.get('dev/talon_ballistics').bytes:sub(0x81,0x88)==TALON:sub(0x81,0x88))
-- The logs name each component, its source projectile and exactly the members that differ.
local line=custom.line(combined)
assert(line:find('components: visual from PLAS-1 Scorcher (+0x48 spawn_effect',1,true),line)
assert(line:find('damage from RS-422 Railgun (+0x3C direct_damage 54 -> 64)',1,true),line)
assert(line:find('impact_explosion from R-36 Eruptor (+0x90 impact_explosion 0 -> '..IMPACT..')',1,true),line)
assert(line:find('ballistics from GL-21 Grenade Launcher (+0x18 diameter 0 -> 40; +0x20 speed 1300 -> 100;',1,true),
    line)
-- No vanilla row was written.
assert(W.read(T,272)==TALON and W.read(S,272)==SCORCHER and W.read(R,272)==RAILGUN)
assert(W.read(E,272)==ERUPTOR and W.read(G,272)==GRENADE)
return 'ok'
''')

    def test_packages_are_unioned_once_and_ballistics_need_none(self):
        self.lua(r'''
-- Two components from one donor load its package once; a ballistics donor adds no package at all.
local same=assert(custom.define({id='dev/same_donor',base='LAS-58 Talon',
    components={visual='PLAS-1 Scorcher',damage='PLAS-1 Scorcher'}}))
assert(packages(same)=='player_weapon/LAS-58 Talon,player_weapon/PLAS-1 Scorcher',packages(same))
local base_donor=assert(custom.define({id='dev/talon_self',base='LAS-58 Talon',components={visual='LAS-58 Talon',
    ballistics='LAS-58 Talon'}}))
assert(packages(base_donor)=='player_weapon/LAS-58 Talon'and#base_donor.changes==0)
assert(custom.line(base_donor):find('visual from LAS-58 Talon (same as the base), ballistics from LAS-58 Talon '
    ..'(same as the base)',1,true),custom.line(base_donor))
-- Donors are named by weapon or by output id; the same spec again returns the same definition.
local by_id=assert(custom.define({id='dev/by_output_id',base='output/v1/projectile/las-58-talon',
    components={impact_explosion='output/v1/projectile/r-36-eruptor'}}))
assert(by_id.bytes==assert(custom.define({id='dev/by_weapon_name',base='LAS-58 Talon',
    components={impact_explosion='R-36 Eruptor'}})).bytes)
assert(custom.define({id='dev/by_output_id',base='output/v1/projectile/las-58-talon',
    components={impact_explosion='output/v1/projectile/r-36-eruptor'}})==by_id)
return 'ok'
''')

    def test_component_definitions_fail_closed(self):
        self.lua(r'''
local function refused(spec,expect)
    local def,code,reason=custom.define(spec)
    assert(def==nil and code==expect,tostring(code)..' '..tostring(reason)..' (expected '..expect..')')
    return reason
end
refused({id='dev/x',base='LAS-58 Talon',components={colour='PLAS-1 Scorcher'}},'UNKNOWN_COMPONENT')
refused({id='dev/x',base='LAS-58 Talon',components={visual=142}},'INVALID_DEFINITION')
refused({id='dev/x',base='LAS-58 Talon',components={visual='No Such Weapon'}},'UNKNOWN_PROJECTILE')
refused({id='dev/x',base='No Such Weapon'},'UNKNOWN_PROJECTILE')
-- The GL-21's visual is its unit: refused on the unit-less Talon.
assert(refused({id='dev/x',base='LAS-58 Talon',components={visual='GL-21 Grenade Launcher'}},
    'COMPONENT_CONSTRAINT'):find('unit',1,true))
-- An impact explosion donor whose live value is not its catalogued one is refused.
W.projectile_row(eruptor_output.currentDefault,put(ERUPTOR,0x90,le(IMPACT+1,4)))
refused({id='dev/x',base='LAS-58 Talon',components={impact_explosion='R-36 Eruptor'}},'DONOR_CHANGED')
W.projectile_row(eruptor_output.currentDefault,ERUPTOR)
assert(W.read(T,272)==TALON)
return 'ok'
''')

    def test_every_variant_spawns_and_leaves_the_vanilla_rows_unchanged(self):
        self.lua(r'''
mission({host=true})
for index,spec in ipairs(custom.DEVELOPMENT_VARIANTS)do
    local def=assert(custom.define(spec))
    local a=fire(nil,spec.id)
    assert(a.status=='requested',spec.id..' '..tostring(a.code)..' '..tostring(a.reason))
    local shot=W.runtime.custom_projectiles[index]
    assert(shot.row==def.row.address and shot.bytes==def.bytes and shot.kind==2)
    assert(count('custom projectile '..spec.id..' base type=144 base identity=LAS-58 Talon')==1)
end
assert(count('components: ballistics from GL-21 Grenade Launcher')==1)
assert(#W.runtime.projectiles==0,'nothing went through the vanilla wrapper')
assert(W.read(T,272)==TALON and W.read(S,272)==SCORCHER and W.read(R,272)==RAILGUN)
assert(W.read(E,272)==ERUPTOR and W.read(G,272)==GRENADE)
return 'ok'
''')


def replacement_addon():
    folder = ROOT / 'proof/ReprimandCustomProjectileProof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class ReplacementProofAddonTests(unittest.TestCase):
    def test_the_reprimand_proof_swaps_to_the_carrier_and_replaces_its_shots(self):
        resource, addon = replacement_addon()
        self.assertEqual(run(PROOF + COMPONENT_WORLD + REPLACEMENT + 'local ADDON=' + lua(addon)
            + '\nlocal RESOURCE=' + lua(resource) + r'''
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(key)keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;tick()end
-- The carrier swap is an ordinary ensure: recorded here (the write path has its own tests).
local requests={}
hd2.ensure=function(request)requests[#requests+1]=request;return{status='recorded'}end
assert(loadstring(ADDON,'@'..RESOURCE))()
local swap=requests[1] and requests[1].transaction
assert(#requests==1 and swap.id=='reprimand-carrier'and #swap.changes==1)
assert(swap.changes[1].field=='attack.projectile'and swap.changes[1].value.output==CARRIER)
assert(swap.allow_shared==nil and swap.allow_unverified_effect==nil and swap.allow_unverified_reference==nil,
    'the proof adds no acknowledgement')
assert(count('loaded: the SMG-32 Reprimand fires dev/talon_combined')==1)
mission({host=true})
assert(count('mission started: SMG-32 Reprimand carrier shots -> dev/talon_combined: bound')==1)
W.hold(100,605,REPRIMAND,1)
tick()
carrier();tick()
local combined=custom.get('dev/talon_combined')
assert(#W.runtime.custom_projectiles==1 and W.runtime.custom_projectiles[1].bytes==combined.bytes)
assert(W.runtime.custom_projectiles[1].y==12)
-- F12 off: the carrier alone; F12 on again: replaced again. F9 logs the counts.
press('F12')
assert(count('F12: replacement off')==1)
carrier();tick()
assert(#W.runtime.custom_projectiles==1)
press('F12')
assert(count('F12: SMG-32 Reprimand carrier shots -> dev/talon_combined: bound')==1)
tick()
carrier();tick()
assert(#W.runtime.custom_projectiles==2)
press('F9')
assert(count('F9: TD-110 Maelstrom / slot_2 (type 324) -> dev/talon_combined: 1 replaced')==1)
-- The next mission binds again without a restart; the definition is kept.
W.state(3);tick()
W.pool_counter(0)
W.state(4,{host=true});tick()
assert(count('mission started: SMG-32 Reprimand carrier shots -> dev/talon_combined: bound')==2)
assert(custom.get('dev/talon_combined')==combined,'the definition is kept, not rebuilt')
return 'ok'
'''), b'ok')


def firemode_addon():
    folder = ROOT / 'proof/ReprimandFireModeProof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class FireModeProofAddonTests(unittest.TestCase):
    def test_the_fire_mode_proof_configures_modes_rate_and_magazine_and_replaces_only_custom_shots(self):
        resource, addon = firemode_addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_reprimand_firemode_proof')
        self.assertEqual(run(PROOF + COMPONENT_WORLD + REPLACEMENT + 'local ADDON=' + lua(addon)
            + '\nlocal RESOURCE=' + lua(resource) + r'''
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(key)keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;tick()end
local requests={}
hd2.ensure=function(request)requests[#requests+1]=request;return{status='recorded'}end
assert(loadstring(ADDON,'@'..RESOURCE))()
local by={}
for _,request in ipairs(requests)do
    local body=request.transaction or request.patch
    by[body.id]={request=request,body=body}
end
-- The modes: the ProgrammableAmmo selector on the free left input, firing the carrier, with exactly the
-- acknowledgements the feed requires.
local mode=assert(by['reprimand-custom-mode-mode']).body
assert(mode.changes[1].field=='weapon_function.left'and mode.changes[1].expect=='none'
    and mode.changes[1].value=='programmable_ammo')
assert(mode.changes[2].field=='function_ammo.projectile'and mode.changes[2].expect=='none'
    and mode.changes[2].value.output==CARRIER)
assert(mode.allow_unverified_effect and mode.allow_unverified_reference and not mode.allow_shared)
-- Labels: Normal STANDARD on the native projectile, Custom HE on the carrier, icon auto (never the placeholder).
local custom_label=assert(by['reprimand-mode-labels-label'])
local normal_label=assert(by['reprimand-mode-labels-primary-label'])
assert(custom_label.body.target.output==CARRIER and custom_label.body.changes[1].value=='he'
    and custom_label.body.changes[2].value=='auto'and custom_label.request.enabled~=nil)
assert(normal_label.body.target.output=='output/v1/projectile/smg-32-reprimand'
    and normal_label.body.changes[1].value=='standard'and normal_label.body.changes[2].value=='auto')
-- Fire rate (a choice of 490 / 872 / 1500 rpm on weapon.fire_rate) and the magazine (25 -> 50), no acknowledgement.
local rate=assert(by['reprimand-fire-rate']).body
assert(rate.field=='weapon.fire_rate'and rate.expect==490 and rate.value:get()==1500)
local values=rate.value:describe().values
assert(values[1]==490 and values[2]==872 and values[3]==1500 and #values==3)
local magazine=assert(by['reprimand-magazine']).body
assert(magazine.field=='magazine.capacity'and magazine.expect==25 and magazine.value==50)
for _,item in pairs({rate,magazine})do assert(not item.allow_unverified_effect and not item.allow_shared)end
assert(#requests==5)
-- Startup diagnostics.
assert(count('fire modes: weapon_function.left none -> programmable_ammo (Normal / Custom selector); '
    ..'weapon_function.right fire_mode unchanged')==1)
assert(count('mode Normal: output/v1/projectile/smg-32-reprimand (type 123, ProjectileWeapon +0), never replaced; '
    ..'mode Custom: function_ammo.projectile (ProjectileWeapon +576) none -> carrier '..CARRIER..' (type 324) -> '
    ..'dev/talon_combined')==1)
assert(count('fire rate: weapon.fire_rate (ProjectileWeapon +8, rpm) 490 -> 1500 (choices 490 / 872 / 1500; 1500 '
    ..'rpm = 25 shots/s, one every 40 ms, 50 rounds in 1.96 s)')==1)
assert(count('magazine: magazine.capacity (WeaponMagazine +136) 25 -> 50; reserve unchanged')==1)
-- In a mission: bound with the native projectile as the unreplaced Normal mode.
mission({host=true})
assert(count('mission started: custom replacement binding: Custom mode carrier '..CARRIER..' -> dev/talon_combined; '
    ..'Normal mode output/v1/projectile/smg-32-reprimand -> no replacement: bound')==1)
W.hold(100,605,REPRIMAND,1)
tick()
-- Normal mode: the native bullet, never replaced. Custom mode: the carrier, replaced by dev/talon_combined.
carrier({type=123});tick()
assert(#W.runtime.custom_projectiles==0 and count('normal mode: SMG-32 Reprimand shot 1:')==1)
carrier();tick()
local combined=custom.get('dev/talon_combined')
assert(#W.runtime.custom_projectiles==1 and W.runtime.custom_projectiles[1].bytes==combined.bytes)
assert(count('custom mode: TD-110 Maelstrom / slot_2 shot 1:')==1)
-- F12 off: Custom mode fires the carrier alone; on again: replaced.
press('F12')
assert(count('F12: custom replacement off')==1)
carrier();tick()
assert(#W.runtime.custom_projectiles==1)
press('F12')
tick()
carrier();tick()
assert(#W.runtime.custom_projectiles==2)
tick(5)
press('F9')
assert(count('F9: Custom mode: 1 replaced, 0 dropped (rate), 0 refused, 0 not yours; Normal mode: 0 not replaced; '
    ..'last shot mode: Custom (carrier)')==1)
assert(count('configured: fire rate 1500 rpm (Mod Options), magazine 50')==1)
return 'ok'
'''), b'ok')


def concussive_addon():
    folder = ROOT / 'proof/LiberatorConcussiveFireModeProof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class ConcussiveFireModeProofAddonTests(unittest.TestCase):
    def test_the_two_fire_mode_proofs_differ_only_in_their_config(self):
        import re
        bodies = [(ROOT / ('proof/%s/src/addon.lua' % name)).read_text(encoding='utf-8')
            for name in ('ReprimandFireModeProof', 'LiberatorConcussiveFireModeProof')]
        shared = [re.sub(r'\nlocal CONFIG=\{\n.*?\n\}\n', '\n<CONFIG>\n', body, count=1, flags=re.S) for body in bodies]
        self.assertIn('<CONFIG>', shared[0])
        self.assertEqual(shared[0], shared[1])

    def test_the_concussive_proof_uses_its_drum_magazine_and_replaces_only_custom_shots(self):
        resource, addon = concussive_addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_liberator_concussive_firemode_proof')
        self.assertEqual(run(PROOF + COMPONENT_WORLD + REPLACEMENT + 'local ADDON=' + lua(addon)
            + '\nlocal RESOURCE=' + lua(resource) + r'''
local CONCUSSIVE='CF5F176E0E322BE1'
local NATIVE_OUTPUT='output/v1/projectile/ar-23c-liberator-concussive'
local NATIVE=assert(custom.output(NATIVE_OUTPUT,false)).type
local requests={}
hd2.ensure=function(request)requests[#requests+1]=request;return{status='recorded'}end
assert(loadstring(ADDON,'@'..RESOURCE))()
local by={}
for _,request in ipairs(requests)do
    local body=request.transaction or request.patch
    by[body.id]={request=request,body=body}
end
assert(#requests==5)
local mode=assert(by['concussive-custom-mode-mode']).body
assert(mode.target.weapon=='AR-23C Liberator Concussive'and mode.changes[1].field=='weapon_function.left'
    and mode.changes[1].value=='programmable_ammo'and mode.changes[2].value.output==CARRIER)
assert(mode.allow_unverified_effect and mode.allow_unverified_reference and not mode.allow_shared)
-- The labels: the Concussive round is shared, acknowledged explicitly by the proof's CONFIG.
local normal_label=assert(by['concussive-mode-labels-primary-label']).body
assert(normal_label.target.output==NATIVE_OUTPUT and normal_label.allow_shared and normal_label.changes[1].value
    =='standard'and normal_label.changes[2].value=='auto')
-- The fire rate: 400 (native) / 640 / 1500 on weapon.fire_rate.
local rate=assert(by['concussive-fire-rate']).body
assert(rate.field=='weapon.fire_rate'and rate.expect==400 and rate.value:get()==1500)
local values=rate.value:describe().values
assert(values[1]==400 and values[2]==640 and values[3]==1500)
-- The magazine: its default Drum attachment owns the capacity (shared, own toggle), 60 -> 50.
local magazine=assert(by['concussive-magazine'])
assert(magazine.body.field=='attachment.magazine_capacity'and magazine.body.expect==60 and magazine.body.value==50)
assert(magazine.body.target:describe().name=='Rifle 5,5x50mm. Drum'and magazine.body.allow_shared
    and magazine.body.allow_unverified_effect and magazine.request.enabled~=nil)
assert(count('magazine: attachment.magazine_capacity (Rifle 5,5x50mm. Drum, the default magazine; shared: every '
    ..'weapon that equips it) 60 -> 50; reserve unchanged')==1)
assert(count('fire rate: weapon.fire_rate (ProjectileWeapon +8, rpm) 400 -> 1500 (choices 400 / 640 / 1500')==1)
assert(count('mode Normal: '..NATIVE_OUTPUT..' (type '..NATIVE..', ProjectileWeapon +0), never replaced')==1)
-- In a mission: Normal shots (the Concussive round) are never replaced; Custom shots (the carrier) are.
mission({host=true})
assert(count('mission started: custom replacement binding: Custom mode carrier '..CARRIER..' -> dev/talon_combined; '
    ..'Normal mode '..NATIVE_OUTPUT..' -> no replacement: bound')==1)
W.hold(100,607,CONCUSSIVE,1)
tick()
W.projectile_row(NATIVE,row_of(NATIVE,96,string.rep('\0',8),0))
carrier({type=NATIVE,source=607});tick()
assert(#W.runtime.custom_projectiles==0 and count('normal mode: AR-23C Liberator Concussive shot 1:')==1)
carrier({source=607});tick()
assert(#W.runtime.custom_projectiles==1
    and W.runtime.custom_projectiles[1].bytes==custom.get('dev/talon_combined').bytes)
-- A Reprimand's carrier is another weapon's: not replaced by this binding.
W.hold(100,605,REPRIMAND,1)
carrier({source=605});tick()
assert(#W.runtime.custom_projectiles==1 and replacement.list()[1].other_weapons==1)
return 'ok'
'''), b'ok')


def patriot_addon():
    folder = ROOT / 'proof/PatriotCustomProjectileProof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class PatriotProofAddonTests(unittest.TestCase):
    def test_the_patriot_proof_suppresses_the_minigun_bullet_and_replaces_every_carrier_once(self):
        resource, addon = patriot_addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_patriot_custom_projectile_proof')
        self.assertEqual(run(PROOF + COMPONENT_WORLD + REPLACEMENT + 'local ADDON=' + lua(addon)
            + '\nlocal RESOURCE=' + lua(resource) + r'''
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(key)keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;tick()end
local HOST='output/v1/projectile/exo-45-patriot-exosuit-right-gun'
local NATIVE=assert(custom.output(HOST,false)).type
local requests={}
hd2.ensure=function(request)requests[#requests+1]=request;return{status='recorded'}end
assert(loadstring(ADDON,'@'..RESOURCE))()
-- The suppression: one swap of the minigun's projectile to the carrier, acknowledged explicitly.
local swap=assert(requests[1]and requests[1].transaction)
assert(#requests==1 and swap.id=='patriot-carrier'and swap.target.weapon=='EXO-45 Patriot Exosuit / right_gun')
assert(swap.changes[1].field=='attack.projectile'and swap.changes[1].value.output==CARRIER)
assert(swap.allow_unverified_effect==true and swap.allow_unverified_reference==nil and swap.allow_shared==nil)
assert(count('host: EXO-45 Patriot Exosuit / right_gun, output '..HOST..', native projectile type '..NATIVE
    ..', source identity entity type 0x08F6089289C83D22')==1)
mission({host=true})
W.pool_spawns(true)
assert(count('mission started: replacement binding: carrier '..CARRIER..' (type 324) from EXO-45 Patriot Exosuit / '
    ..'right_gun -> dev/talon_combined; native '..HOST..' (type '..NATIVE..') suppressed: bound')==1)
W.hold(300,700,'08F6089289C83D22',1)
tick()
for _=1,20 do carrier({source=700,owner=100,creditor=LOCAL});tick(1,0.05)end
tick(10,0.1)
local combined=custom.get('dev/talon_combined')
assert(#W.runtime.custom_projectiles==20)
for _,shot in ipairs(W.runtime.custom_projectiles)do assert(shot.bytes==combined.bytes)end
press('F9')
assert(count('F9: 20 carriers -> 20 replaced (20 confirmed in the pool, 0 not), 0 dropped (rate), 0 refused, 0 not the '
    ..'local player\'s, 0 other sources; native bullets seen: 0 (suppression held); latency one game update: mean')==1)
assert(count('last burst: 20 shots over 0.95 s = 1200 rpm')==1)
-- F12 off: the carrier alone; on again: replaced.
press('F12')
carrier({source=700,owner=100,creditor=LOCAL});tick()
assert(#W.runtime.custom_projectiles==20 and count('F12: replacement off')==1)
press('F12');tick()
carrier({source=700,owner=100,creditor=LOCAL});tick()
assert(#W.runtime.custom_projectiles==21)
return 'ok'
'''), b'ok')


class NativeAdapterTests(unittest.TestCase):
    def test_owned_rows_and_the_spawn_descriptor_on_the_real_adapter(self):
        self.assertEqual(execute((modules() + r'''
local ffi=require('ffi')
local runtime=require('hd2runtime/runtime/windows_write').create()
local layout=require('hd2runtime/domains/projectile_rows').spawn.descriptor
local row=runtime.owned_block(272)
assert(row%16==0)
assert(runtime.read(row,272)==string.rep('\0',272),'a new block is zeroed')
local content=string.rep('\7',272)
assert(runtime.owned_write(row,content)and runtime.read(row,272)==content)
assert(not pcall(runtime.owned_write,row+16,content),'only a whole owned block is written')
assert(not pcall(runtime.owned_write,row,content:sub(2)),'only a whole owned block is written')
local seen
local callback=ffi.cast('uint32_t (*)(void *, const void *, const void *)',function(system,descriptor,extra)
    local d=ffi.cast('const uint8_t *',descriptor)
    local function u32(o)return tonumber(ffi.cast('const uint32_t *',d+o)[0])end
    local function ptr(o)return ffi.cast('const uintptr_t *',d+o)[0]end
    local position=ffi.cast('const float *',ptr(layout.position))
    local direction=ffi.cast('const float *',ptr(layout.direction))
    seen={system=tonumber(ffi.cast('uintptr_t',system)),extra_null=extra==nil,row=tonumber(ptr(layout.row)),
        source=u32(layout.source),owner=u32(layout.owner),lo=u32(layout.creditor),hi=u32(layout.creditor+4),
        kind=u32(layout.kind),x=position[0],y=position[1],z=position[2],dx=direction[0],dy=direction[1],
        dz=direction[2],first=ffi.cast('const uint8_t *',ptr(layout.row))[0]}
    return 9
end)
local entry=tonumber(ffi.cast('uintptr_t',callback))
local slot=runtime.native_spawn_projectile(entry,0x10000,row,1,2,3,0,0,1,100,101,0x33334444,0x11112222,2,layout)
assert(slot==9 and seen.system==0x10000 and seen.extra_null and seen.row==row and seen.first==7)
assert(seen.source==100 and seen.owner==101 and seen.lo==0x33334444 and seen.hi==0x11112222 and seen.kind==2)
assert(seen.x==1 and seen.y==2 and seen.z==3 and seen.dx==0 and seen.dy==0 and seen.dz==1)
-- Never a row the adapter does not own, never a non-unit direction.
seen=nil
assert(not pcall(runtime.native_spawn_projectile,entry,0x10000,row+16,1,2,3,0,0,1,100,101,0,0,2,layout))
assert(not pcall(runtime.native_spawn_projectile,entry,0x10000,row,1,2,3,0,0,2,100,101,0,0,2,layout))
assert(seen==nil,'a refused call never reaches the function')
callback:free()
return 'ok'
''').encode()), b'ok')


class GeneratedDomainTests(unittest.TestCase):
    def test_the_projectile_row_domain_is_generated_from_the_research(self):
        import generate_projectile_rows
        self.assertFalse(generate_projectile_rows.generate(check=True))

    def test_the_component_catalogue_report_is_generated_from_the_research(self):
        import generate_projectile_catalogue_report
        self.assertFalse(generate_projectile_catalogue_report.generate(check=True))

    def test_the_component_catalogue_is_consistent(self):
        import json as _json
        data = _json.loads((ROOT / 'research/projectile-components-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        s = data['summary']
        self.assertEqual((s['rows'], s['liveRowsMatchingDatalibrary'], data['liveMismatches']), (350, 350, []))
        domain = (ROOT / 'domains/projectile_rows.lua').read_text(encoding='utf-8')
        for cid, component in data['components'].items():
            groups = component['groups']
            # Every row is in exactly one group per component, and the unique counts are the non-empty groups.
            self.assertEqual(sorted(t for g in groups for t in g['types']), list(range(1, 351)), cid)
            self.assertEqual(s['unique'][cid], sum(1 for g in groups if not g['none']), cid)
            self.assertEqual(s['uniqueAmongRuntimeDonors'][cid], sum(1 for g in groups if not g['none'] and g['donors']))
            self.assertEqual(len({g['key'] for g in groups}), len(groups), cid)
            # A group key is exactly the owned members' bytes.
            width = sum(m['width'] for m in component['members'])
            self.assertTrue(all(len(g['key']) == 2 * width for g in groups), cid)
            for member in component['members']:
                self.assertIn('["label"]="%s",["offset"]=%d' % (member['label'], member['offset']), domain)
            for group in groups:
                # Unit-less donors are exactly the donors whose own row has no unit.
                self.assertEqual({(d['name'], d['type']) for d in group['unitlessDonors']},
                    {(d['name'], d['type']) for d in group['donors'] if d['type'] not in group['unitTypes']})
                if component['descriptor']['assets'] == 'donor' and group['donors']:
                    self.assertTrue(group['packages'], cid + ' donor group without a package')
        rows = {row['type']: row for row in data['rows']}
        talon = rows[144]
        self.assertFalse(talon['unit'])
        self.assertIn('LAS-58 Talon', talon['runtimeDonors'])
        self.assertEqual(talon['components']['ballistics']['values']['speed'], 1300.0)
        self.assertEqual(rows[40]['components']['impact_explosion']['values']['impact_explosion'], 158)
        grenade = [r for r in data['rows'] if 'GL-21 Grenade Launcher' in r['runtimeDonors']][0]
        self.assertTrue(grenade['unit'])
        self.assertEqual((grenade['components']['ballistics']['values']['speed'],
            grenade['components']['ballistics']['values']['gravity']), (100.0, 1.0))


if __name__ == '__main__':
    unittest.main()
