"""A carrier's presentation borrowed from a vanilla donor (runtime/stratagem_presentation.lua, docs/custom-stratagems.md,
"Presentation"): the Orbital 120mm HE Barrage presents as the Orbital Gas Strike (name, cased name, description, icon)
while its type and stable id stay the 120mm's, on the offline event world. Nothing here touches a game process."""
import unittest

from support import run
from test_event_scripting import PRELUDE

WORLD = PRELUDE + r'''
local b=require('hd2runtime/core/bytes')
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local hud_module=require('hd2runtime/runtime/stratagem_hud')
local calldown=require('hd2runtime/runtime/calldown_codes')
local C=require('hd2runtime/domains/stratagem_calldown')
local P=C.presentation
presentation.reset_for_tests();loadout.reset_for_tests();calldown.reset_for_tests()
W.guarded_runtime()
local function pres(id)
    local v=P.values[tostring(id)]
    return {[0x28]=W.u32(v.name),[0x2C]=W.u32(v.nameCased),[0x30]=W.u32(v.description),
        [0xB0]=presentation.encode('icon',v.icon)}
end
local BIG,GAS,PRECISION=1063322614,3193297673,3523620028
local settings=W.stratagem_settings({
    {type=136,id=BIG,package='0x25B8CFF26C7C0112',payload='0x2D3BD00B1ED411B1',sequence={2,2,3,4,2,3},group=5,row=4,
        cooldown=180,fields=pres(BIG)},
    {type=41,id=GAS,package='0x6369816737A36A40',payload='0x05F3C83A91075766',sequence={2,2,3,2},group=5,row=1,
        cooldown=75,fields=pres(GAS)},
    {type=118,id=PRECISION,package='0xDBAE525060F06D70',payload='0xC897C0D84448AB2C',sequence={2,2,1},group=5,row=0,
        cooldown=80,fields=pres(PRECISION)},
})
world_module.set_runtime(W.runtime)
local ROW=settings.rows[136].address
local DONOR=settings.rows[41].address
local BEFORE=W.read(settings.base,settings.size)
local function changed()
    local now,out=W.read(settings.base,settings.size),{}
    for i=1,#now do if now:byte(i)~=BEFORE:byte(i)then out[#out+1]=settings.base+i-1 end end
    return out
end
local function settle(handle)for _=1,400 do if handle.status~='pending'then break end;tick()end;return handle end
local function writes()return#(W.runtime.writes or{})end
local function field(address,name)
    local f=P.fields[name]
    return W.read(address+f.offset,f.width)
end
local SPEC={carrier='Orbital 120mm HE Barrage',donor='Orbital Gas Strike'}
'''


def lua(body):
    return run(WORLD + body)


class PresentationWriteTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_name_description_and_icon_take_the_donor_values_and_the_identity_stays(self):
        self.check(r'''
local job=settle(presentation.apply(SPEC))
assert(job.status=='applied',tostring(job.code)..' '..tostring(job.reason))
-- Name, cased name, description (localization ids) and icon (64-bit image hash): the Gas Strike's values.
for _,name in ipairs({'name','nameCased','description','icon'})do
    assert(field(ROW,name)==field(DONOR,name),name)
end
assert(writes()==4 and job.report.non_target_bytes_unchanged and job.report.protection_restored)
-- Only those 20 bytes changed; the type (+0) and the stable id (+4) are the 120mm's.
local allowed={}
for _,name in ipairs({'name','nameCased','description','icon'})do
    local f=P.fields[name];for i=0,f.width-1 do allowed[ROW+f.offset+i]=true end
end
for _,at in ipairs(changed())do assert(allowed[at],string.format('byte %X changed',at))end
assert(b.u32(W.read(ROW,4),0)==136 and b.u32(W.read(ROW+4,4),0)==BIG)
-- The donor row is untouched (values are copied, nothing is shared).
assert(W.read(DONOR,400)==BEFORE:sub(DONOR-settings.base+1,DONOR-settings.base+400))
assert(count('stratagem presentation APPLIED: Orbital 120mm HE Barrage (type 136, stable id 1063322614) presents as '
    ..'Orbital Gas Strike: 4 writes (name, nameCased, description, icon), identity unchanged')==1)
-- Restore: the exact native bytes, the settings identical again.
local back=settle(presentation.restore())
assert(back.status=='restored'and writes()==8 and#changed()==0,tostring(back.reason))
assert(count('stratagem presentation RESTORED: Orbital 120mm HE Barrage presents as itself again: 4 writes')==1)
-- Applied again later: allowed once restored.
assert(settle(presentation.apply(SPEC)).status=='applied')
return 'ok'
''')

    def test_a_subset_of_fields_and_refusals(self):
        self.check(r'''
-- Only the name.
local job=settle(presentation.apply({carrier=SPEC.carrier,donor=SPEC.donor,fields={'name'}}))
assert(job.status=='applied'and writes()==1 and field(ROW,'name')==field(DONOR,'name'))
assert(field(ROW,'icon')~=field(DONOR,'icon'))
assert(settle(presentation.restore()).status=='restored'and#changed()==0)
-- Unsupported or unsafe members are refused, nothing written.
for _,name in ipairs({'category','beaconColour','type','id','debugName','loadingText'})do
    local refused=settle(presentation.apply({carrier=SPEC.carrier,donor=SPEC.donor,fields={name}}))
    assert(refused.status=='refused'and refused.code=='UNSUPPORTED_FIELD',name)
end
assert(settle(presentation.apply({carrier=SPEC.carrier,donor=SPEC.carrier})).code=='SAME_STRATAGEM')
assert(settle(presentation.apply({carrier=SPEC.carrier,donor='No Such Stratagem'})).code=='UNKNOWN_STRATAGEM')
assert(#changed()==0)
return 'ok'
''')

    def test_guards_refuse_another_writer_and_unsupported_builds(self):
        self.check(r'''
-- The carrier's name was changed by someone else: refused, nothing written.
local name=field(ROW,'name')
W.write(ROW+P.fields.name.offset,W.u32(12345))
local job=settle(presentation.apply(SPEC))
assert(job.status=='refused'and job.code=='CONFLICT'and tostring(job.reason):find('another writer',1,true))
W.write(ROW+P.fields.name.offset,name)
-- The donor's icon is not its reviewed value: refused.
local icon=field(DONOR,'icon')
W.write(DONOR+P.fields.icon.offset,string.rep('\1',8))
assert(settle(presentation.apply(SPEC)).code=='CONFLICT')
W.write(DONOR+P.fields.icon.offset,icon)
-- A changed reader (another game build): refused before anything is resolved.
local pin=P.pins[1]
local original=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,string.char(0xCC))
assert(settle(presentation.apply(SPEC)).code=='UNSUPPORTED_BUILD')
W.write(W.GAME+pin.rva,original)
assert(writes()==0)
-- Applied, then changed by someone else: the restore refuses rather than overwrite it.
assert(settle(presentation.apply(SPEC)).status=='applied')
W.write(ROW+P.fields.description.offset,W.u32(777))
local back=settle(presentation.restore())
assert(back.status=='refused'and back.code=='CONFLICT',tostring(back.code))
assert(W.read(ROW+P.fields.description.offset,4)==W.u32(777))
return 'ok'
''')

    def test_the_finalizer_restores_before_the_lua_state_closes(self):
        self.check(r'''
assert(settle(presentation.apply(SPEC)).status=='applied')
presentation.finalize_for_tests()
assert(#changed()==0 and presentation.state().restored)
return 'ok'
''')


class PresentationPipelineTests(unittest.TestCase):
    """The loadout pipeline still sees the 120mm: the saved loadout, the mission record and the HUD slot resolve its
    stable id and type, and the public calldown field still applies to it."""

    def test_identity_survives_ship_and_mission_and_the_calldown_still_applies(self):
        self.assertEqual(lua(r'''
assert(settle(presentation.apply(SPEC)).status=='applied')
local world=assert(world_module.open())
-- Ship: the saved loadout (stable ids) still resolves to the 120mm's type.
W.saved_loadout({{id=BIG},{id=PRECISION}})
local saved=assert(loadout.saved(world))
assert(saved.pairs[1].id==BIG and saved.pairs[1].type==136)
assert(loadout.type_of(world,BIG)==136 and loadout.id_of(world,136)==BIG)
-- Mission: the record entry and the HUD slot are the 120mm's type; the slot is built with the borrowed icon.
mission({host=true})
local HUD=W.stratagem_hud({peer=LOCAL,slots={{type=118,code={2,2,1}},{type=136,code={2,2,3,4,2,3}}}})
local record=assert(loadout.record(world))
assert(record[2].type==136 and record[2].id==BIG)
local located=assert(hud_module.locate(world,136))
assert(located.index==1)
-- The public calldown field on the carrier, with the presentation applied: the same 2 row writes.
package.loaded['hd2runtime/runtime/windows_write']={create=function()return W.runtime end}
local session=require('hd2runtime/api/session').new(W.runtime,function(line)logged[#logged+1]=line end)
local op=session.patch{id='p0',target=session.stratagem('Orbital 120mm HE Barrage'),
    field=session.fields.stratagem.calldown_code,expect={'right','right','down','left','right','down'},
    value={'up','up','down','down'}}
for _=1,400 do op.tick(0.125);if op.status=='complete'or op.status=='rejected'then break end end
assert(op.status=='complete',tostring(op.error))
assert(field(ROW,'icon')==field(DONOR,'icon')and b.u32(W.read(ROW+0x48,4),0)==4)
-- Restoring the presentation leaves the calldown code alone, and the reverse.
assert(settle(presentation.restore()).status=='restored')
assert(field(ROW,'icon')~=field(DONOR,'icon')and b.u32(W.read(ROW+0x48,4),0)==4)
return 'ok'
'''), b'ok')


# The public fields on the same offline world: hd2's write adapter is the fixture's.
PUBLIC = r"""
package.loaded['hd2runtime/runtime/windows_write']={create=function()return W.runtime end}
local session=require('hd2runtime/api/session').new(W.runtime,function(line)logged[#logged+1]=line end)
local F=session.fields.stratagem
local BIGNAME,GASNAME='Orbital 120mm HE Barrage','Orbital Gas Strike'
local function op_settle(op)
    for _=1,400 do op.tick(0.125);if op.status=='complete'or op.status=='rejected'or op.status=='failed'then break end end
    return op
end
local function rejects(request,text)
    local ok,why=pcall(require('hd2runtime/domains/patches').validate,request)
    assert(not ok and tostring(why):find(text,1,true),text..' expected, got '..tostring(why))
end
local MEMBERS={presentation_name='name',presentation_name_cased='nameCased',presentation_description='description',
    presentation_icon='icon'}
local function all_changes(value,expect)
    local out={}
    for constant in pairs(MEMBERS)do out[#out+1]={field=F[constant],expect=expect or BIGNAME,value=value}end
    table.sort(out,function(a,b)return a.field<b.field end)
    return out
end
local function presents_as(row_name)
    local id=row_name=='gas'and GAS or BIG
    for _,member in pairs(MEMBERS)do
        if field(ROW,member)~=presentation.reviewed(id,member)then return false end
    end
    return true
end
local function identity()return b.u32(W.read(ROW,4),0)==136 and b.u32(W.read(ROW+4,4),0)==BIG end
"""


def public(body):
    return run(WORLD + PUBLIC + body)


class PublicPresentationFieldTests(unittest.TestCase):
    """hd2.fields.stratagem.presentation_name / _name_cased / _description / _icon through patch, transaction, plan and
    ensure: a value names a catalogued stratagem whose vanilla resource the field takes."""

    def check(self, body):
        self.assertEqual(public(body), b'ok')

    def test_metadata_publishes_four_semantic_fields_per_call_in_stratagem(self):
        import json
        from support import ROOT
        catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text(encoding='utf-8'))
        ids = ('stratagem.presentation.name', 'stratagem.presentation.name_cased',
            'stratagem.presentation.description', 'stratagem.presentation.icon')
        for field_id in ids:
            fields = [x for x in catalog['fieldInstances'] if x['semanticFieldId'] == field_id]
            self.assertEqual(len(fields), 94, field_id)
            for field in fields:
                name = field['target']['stratagem']
                self.assertTrue(field['editable'] and not field['shared'], name)
                self.assertEqual(field['currentDefault'], name)          # its native value is its own
                self.assertEqual(field['type'], 'stratagem_presentation')
                self.assertEqual(field['resourceType'], 'image' if field_id.endswith('icon') else 'localization')
                self.assertEqual(field['apiFieldConstant'],
                    'hd2.fields.stratagem.' + field_id.split('.', 1)[1].replace('.', '_'))
                self.assertNotIn('backing', field)                       # no offsets, ids or hashes
                self.assertNotIn('acknowledgement', field)
            proven = sorted(x['target']['stratagem'] for x in fields if x.get('liveEvidence'))
            self.assertEqual(proven, ['Orbital 120mm HE Barrage'], field_id)
        self.assertEqual(catalog['summary']['presentationWritable'], 94)
        sources = catalog['presentationSources']['stratagems']
        self.assertEqual(len(sources), 94)
        self.assertIn('Orbital Gas Strike', sources)
        self.assertEqual(catalog['presentationSources']['excluded'],
            {'stratagem.presentation.name_cased': ['LIFT-860 Hover Pack']})
        text = json.dumps([x for x in catalog['fieldInstances'] if x['semanticFieldId'] in ids])
        for raw in ('4FAAD695', '9C9B3DCE316F1256', '0x28', '0xB0', '1336596117'):
            self.assertNotIn(raw, text.upper() if raw.isupper() else text)

    def test_each_field_writes_only_its_member_and_never_the_identity(self):
        self.check(r'''
local offsets={presentation_name=0x28,presentation_name_cased=0x2C,presentation_description=0x30,presentation_icon=0xB0}
for constant,member in pairs(MEMBERS)do
    local first=writes()
    local op=op_settle(session.patch{id=constant,target=session.stratagem(BIGNAME),field=F[constant],
        expect=BIGNAME,value=GASNAME})
    assert(op.status=='complete',constant..': '..tostring(op.error))
    assert(writes()==first+1 and W.runtime.writes[writes()].address==ROW+offsets[constant],constant)
    assert(field(ROW,member)==presentation.reviewed(GAS,member),constant)
end
assert(presents_as('gas')and identity())
-- Only the 20 presentation bytes changed in the whole settings buffer; the donor row is untouched.
local allowed={}
for constant,member in pairs(MEMBERS)do
    local f=P.fields[member];for i=0,f.width-1 do allowed[ROW+f.offset+i]=true end
end
for _,at in ipairs(changed())do assert(allowed[at],string.format('byte %X changed',at))end
assert(W.read(DONOR,400)==BEFORE:sub(DONOR-settings.base+1,DONOR-settings.base+400))
assert(count('stratagem.presentation.icon Orbital 120mm HE Barrage -> Orbital Gas Strike')==1)
return 'ok'
''')

    def test_transaction_plan_and_combined_operation_group(self):
        self.check(r'''
-- One transaction: all four members, a hd2.stratagem(name) value accepted too.
local changes=all_changes(GASNAME)
changes[1].value=session.stratagem(GASNAME)
local op=op_settle(session.transaction{id='look',target=session.stratagem(BIGNAME),changes=changes})
assert(op.status=='complete'and writes()==4 and presents_as('gas')and identity(),tostring(op.error))
-- A plan: the Precision Strike takes the 120mm's presentation while the 120mm also gets a cooldown (one group).
op=op_settle(session.plan{id='plan',operations={
    {id='precision',target=session.stratagem('Orbital Precision Strike'),field=F.presentation_icon,
        expect='Orbital Precision Strike',value=BIGNAME},
    {id='cooldown',target=session.stratagem(BIGNAME),field=F.definition_cooldown,expect=180,value=100}}})
assert(op.status=='complete',tostring(op.error))
local precision=settings.rows[118].address
assert(field(precision,'icon')==presentation.reviewed(BIG,'icon')and b.value(W.read(ROW+104,4),0,'f32')==100)
assert(writes()==6)
return 'ok'
''')

    def test_ensure_reapplies_and_its_toggle_restores_exactly(self):
        self.check(r'''
local options=require('hd2runtime/api/options')
local ensure_api=require('hd2runtime/api/ensure')
local scheduler=require('hd2runtime/runtime/scheduler')
options.reset()
local page=hd2.options({id='look',title='Look'})
local on=page:toggle({id='on',label='On',default=true})
local callbacks={}
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,get=function()return nil end,
    on_change=function(id,fn)callbacks[id]=fn;return true end,ready=function()return true end})
scheduler.attach(ensure_api.start(W.runtime,function(line)logged[#logged+1]=line end,{enabled=on,interval=1,
    startup_delay=0,transaction={id='look',target=session.stratagem(BIGNAME),changes=all_changes(GASNAME)}}))
for _=1,60 do tick()end
assert(presents_as('gas')and writes()==4)
-- Something else writes the native icon back: the ensure re-applies it, then stays quiet.
W.write(ROW+0xB0,presentation.reviewed(BIG,'icon'))
for _=1,200 do tick()end
assert(presents_as('gas'))
local settled=writes()
for _=1,200 do tick()end
assert(writes()==settled,'no continuous rewrite')
-- The toggle off: the reviewed native values, exactly; the settings byte-identical.
callbacks['look.on'](false,'look.on')
for _=1,60 do tick()end
assert(presents_as('own')and identity()and#changed()==0)
assert(count('restored the reviewed baseline and is disabled')==1)
return 'ok'
''')

    def test_refusals(self):
        self.check(r'''
local big=session.stratagem(BIGNAME)
-- expect must be the stratagem's own presentation (its name).
rejects({id='a',target=big,field=F.presentation_name,expect=GASNAME,value=GASNAME},'expect differs from reviewed')
-- Not a catalogued stratagem, a raw localization id or hash, another kind of target.
rejects({id='b',target=big,field=F.presentation_name,expect=BIGNAME,value='No Such Stratagem'},'not a catalogued')
rejects({id='c',target=big,field=F.presentation_name,expect=BIGNAME,value=0x34DEFEED},'raw localization ids')
rejects({id='d',target=big,field=F.presentation_icon,expect=BIGNAME,value='0x78F1E50B852CFB79'},'not a catalogued')
rejects({id='e',target=big,field=F.presentation_icon,expect=BIGNAME,value=session.weapon('AR-23 Liberator')},
    'must be a catalogued stratagem')
-- A source whose member does not resolve to displayed text (no registered strings entry) is refused for that member
-- only.
rejects({id='h',target=big,field=F.presentation_name_cased,expect=BIGNAME,value='LIFT-860 Hover Pack'},
    'does not resolve to displayed text')
require('hd2runtime/domains/patches').validate{id='i',target=big,field=F.presentation_name,expect=BIGNAME,
    value='LIFT-860 Hover Pack'}
-- Category and beacon colour are not fields.
assert(F.presentation_category==nil and F.presentation_beacon_colour==nil)
-- Another game build (a presentation reader changed): refused before anything is written. (Proven once per loaded
-- game.dll, so this runs before any other presentation write in this state.)
local pin=P.pins[1]
local original=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,string.char(0xCC))
local op=op_settle(session.patch{id='g',target=big,field=F.presentation_icon,expect=BIGNAME,value=GASNAME})
assert(op.status=='rejected'and tostring(op.error):find('presentation unavailable on this game build',1,true),
    tostring(op.error))
W.write(W.GAME+pin.rva,original)
-- Another writer changed the member: a conflict, nothing written.
W.write(ROW+0x28,W.u32(12345))
op=op_settle(session.patch{id='f',target=big,field=F.presentation_name,expect=BIGNAME,value=GASNAME})
assert(op.status=='rejected'and tostring(op.error):find('CONFLICT',1,true),tostring(op.error))
assert(writes()==0)
return 'ok'
''')

    def test_the_calldown_and_cooldown_are_unaffected(self):
        self.check(r'''
local op=op_settle(session.transaction{id='look',target=session.stratagem(BIGNAME),changes=all_changes(GASNAME)})
assert(op.status=='complete')
-- The calldown code and the cooldown keep their native bytes; the loadout reader still resolves the 120mm.
assert(b.u32(W.read(ROW+0x48,4),0)==6 and b.value(W.read(ROW+104,4),0,'f32')==180)
local world=assert(world_module.open())
assert(loadout.type_of(world,BIG)==136)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
