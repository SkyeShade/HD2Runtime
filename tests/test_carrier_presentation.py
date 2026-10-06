"""runtime/carrier_presentation.lua (docs/custom-stratagems.md, "The carrier presentation lifecycle"): a custom
stratagem carrier's MISSION presentation. The carrier is native aboard the ship; at mission start its exact native
name, cased name, description, icon and calldown code are captured and verified native, then the Runtime text (the
presentation module's guarded text path), the custom icon and the custom code (one guarded transaction through the
stratagem write domain) are written. The restore writes back exactly the captured bytes, only where the row still holds
what was written (another writer's bytes are a CONFLICT and stay), the text only while the presentation module's state is
the one applied; the token (Orbital Precision Strike) is never a target. Offline, on the event world of the proofs."""
import unittest

from support import lua as lua_literal, run
from test_stratagem_calldown_code import WORLD, PROOF
from test_stratagem_slot_conversion import SLOT
from test_gas_barrage_mission_proof import HARNESS, FLOW
from test_gas_barrage_payload_proof import addon

MODULE = r"""
local CP=require('hd2runtime/runtime/carrier_presentation');CP.reset_for_tests()
local NAME=texts.handle('orbital_gas_barrage_name','ORBITAL GAS BARRAGE',RESOURCE)
local CASED=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RESOURCE)
local DESCRIPTION=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE)
local ICON=images.handle('orbital_gas_barrage_masks',RESOURCE)
local UUDD={'up','up','down','down'}
local NAPALM='Orbital Napalm Barrage'
local SPEC={carrier=NAPALM,text={name=NAME,nameCased=CASED,description=DESCRIPTION},icon=ICON,code=UUDD}
local function wait(handle)for _=1,400 do if handle.status~='pending'then break end;tick()end;return handle end
-- The Napalm row's members as the game reads them.
local function held(kind)
    local row=W.read(ROW[kind],400)
    local count=b.u32(row,0x48)
    local array=b.pointer(row,0x40)
    local values={}
    for i=0,count-1 do values[#values+1]=b.u32(W.read(array+i*4,4),0)end
    return {name=row:sub(0x29,0x2C),nameCased=row:sub(0x2D,0x30),description=row:sub(0x31,0x34),icon=row:sub(0xB1,0xB8),
        code=table.concat(values,',')}
end
local function custom(kind)
    local h=held(kind)
    return h.name==texts.id_bytes(NAME)and h.nameCased==texts.id_bytes(CASED)and h.description==texts.id_bytes(DESCRIPTION)
        and h.icon==CUSTOM and h.code=='1,1,3,3'
end
"""


class CarrierPresentationTests(unittest.TestCase):
    def lua(self, body):
        resource, wrapped = addon()
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(wrapped) + '\nlocal RESOURCE='
            + lua_literal(resource) + PROOF + HARNESS + FLOW + MODULE + body + '\ndone()\nreturn "ok"'), b'ok')

    def test_applied_exactly_then_restored_to_the_captured_bytes_with_the_token_byte_identical(self):
        self.lua(r'''
local writes=#W.runtime.writes
local h=wait(CP.apply(SPEC))
assert(h.status=='applied',tostring(h.code)..': '..tostring(h.reason))
assert(custom(106),'the carrier holds the Runtime text, the custom icon and UUDD')
assert(h.verify.identity and h.verify.text and h.verify.icon and h.verify.code and h.verify.others)
assert(W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW,'the token and the donor never written')
assert(CP.applied())
assert(count('carrier presentation APPLIED: Orbital Napalm Barrage (type 106, stable id 2902516083) was native (its '
    ..'own name, cased name, description, icon and code right right down left right up)')==1,table.concat(logged,' | '))
-- The restore: the whole carrier row byte-identical to the row before the apply.
local r=CP.restore_now()
assert(r and r.status=='restored'and r.verify.exact and r.verify.native and r.verify.identity,tostring(r))
assert(W.read(ROW106,400)==CARRIER_ROW,'the carrier row is exactly its native row again')
assert(W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
assert(not CP.applied())
assert(count('carrier presentation RESTORED (in one tick): Orbital Napalm Barrage presents as itself again: name, '
    ..'cased name, description, icon and code back to the bytes captured before the mission: exact true; native true '
    ..'(code right right down left right up); identity unchanged (type 106, stable id 2902516083): true')==1,
    table.concat(logged,' | '))
-- Idempotent: a second restore (another loadout opening) writes nothing.
local n=#W.runtime.writes
for _=1,3 do
    local again,code=CP.restore_now()
    assert(again==nil and code=='NOT_APPLIED')
end
assert(#W.runtime.writes==n and W.read(ROW106,400)==CARRIER_ROW)
-- No stale text: the Runtime table is no longer registered while no row shows it.
assert(require('hd2runtime/runtime/text_resources').state().index==nil)
''')

    def test_applied_again_for_the_next_mission_and_restored_again(self):
        self.lua(r'''
for round=1,3 do
    local h=wait(CP.apply(SPEC))
    assert(h.status=='applied'and custom(106),round..': '..tostring(h.code)..': '..tostring(h.reason))
    local r=wait(CP.restore())
    assert(r.status=='restored'and r.verify.exact and W.read(ROW106,400)==CARRIER_ROW,round..': '..tostring(r.reason))
    assert(W.read(ROW118,400)==PRECISION_ROW)
end
''')

    def test_a_carrier_that_is_not_native_is_refused_with_nothing_written(self):
        self.lua(r'''
local presentation=require('hd2runtime/runtime/stratagem_presentation')
-- A stale icon on the carrier: refused before anything is written.
W.write(ROW106+0xB0,CUSTOM)
local writes=#W.runtime.writes
local h=wait(CP.apply(SPEC))
assert(h.status=='refused'and h.code=='NOT_NATIVE'and tostring(h.reason):find('(icon)',1,true),tostring(h.reason))
assert(#W.runtime.writes==writes and not CP.applied()and presentation.state()==nil)
W.write(ROW106+0xB0,CARRIER_ROW:sub(0xB1,0xB8))
-- Another code on the carrier.
W.write(ROW106+0x48,W.u32(3))
h=wait(CP.apply(SPEC))
assert(h.status=='refused'and h.code=='NOT_NATIVE'and tostring(h.reason):find('calldown code',1,true),tostring(h.reason))
W.write(ROW106+0x48,CARRIER_ROW:sub(0x49,0x4C))
assert(W.read(ROW106,400)==CARRIER_ROW)
''')

    def test_another_writers_bytes_are_never_restored_over(self):
        self.lua(r'''
local h=wait(CP.apply(SPEC))
assert(h.status=='applied')
-- Another writer replaces the icon: the icon and code part is refused, the text (still this module's) is restored.
local OTHER=W.u32(0x11111111)..W.u32(0x22222222)
W.write(ROW106+0xB0,OTHER)
local r,code,reason=CP.restore_now()
assert(r==nil and code=='CONFLICT'and tostring(reason):find('the icon and code: CONFLICT: the carrier Orbital Napalm '
    ..'Barrage stratagem.presentation.icon no longer holds what this presentation wrote (another writer owns it): not '
    ..'restored',1,true)
    and tostring(reason):find('the other part restored',1,true),tostring(reason))
assert(W.read(ROW106+0xB0,8)==OTHER,'the other writer\'s icon stays')
assert(held(106).code=='1,1,3,3','the code is not restored without the icon: one guarded part')
assert(held(106).name==CARRIER_ROW:sub(0x29,0x2C),'the text, still this module\'s, is native again')
assert(CP.applied(),'the state is kept for a later restore')
-- The other writer's value gone again: the kept state restores the rest exactly.
W.write(ROW106+0xB0,CUSTOM)
r=CP.restore_now()
assert(r and r.status=='restored'and r.verify.exact and W.read(ROW106,400)==CARRIER_ROW,tostring(r))
''')

    def test_the_text_owned_by_another_presentation_is_not_restored(self):
        self.lua(r'''
local presentation=require('hd2runtime/runtime/stratagem_presentation')
local h=wait(CP.apply(SPEC))
assert(h.status=='applied')
-- The presentation module's text state replaced by another owner (its restore ran, a new apply took it).
local mine=presentation.state()
local r=wait(presentation.restore())
assert(r.status=='restored')
local other=wait(presentation.apply_text({carrier=NAPALM,name=NAME}))
assert(other.status=='applied'and presentation.state()~=mine)
local res,code,reason=CP.restore_now()
assert(res==nil and code=='CONFLICT'and tostring(reason):find('another Runtime presentation owns the Orbital Napalm '
    ..'Barrage text now: not restored',1,true),tostring(reason))
assert(held(106).name==texts.id_bytes(NAME),'the other owner\'s text stays')
assert(held(106).icon==CARRIER_ROW:sub(0xB1,0xB8)and held(106).code=='2,2,3,4,2,1','the icon and code, this '
    ..'module\'s, are restored')
assert(wait(presentation.restore()).status=='restored')
''')

    def test_a_refused_icon_and_code_leave_nothing_written(self):
        self.lua(r'''
local presentation=require('hd2runtime/runtime/stratagem_presentation')
-- The icon family not loaded: the icon and code are refused after the text was written; the text is restored.
W.icon_resources({textures={},materials={FONT},fonts={FONT}})
local h=wait(CP.apply(SPEC))
assert(h.status=='refused'and h.code=='ASSET_UNAVAILABLE',tostring(h.code)..': '..tostring(h.reason))
assert(W.read(ROW106,400)==CARRIER_ROW and not CP.applied()and presentation.state().restored)
assert(W.read(ROW118,400)==PRECISION_ROW)
''')

    def test_uses_per_rearm_only_for_an_eagle_carrier_and_with_the_icon_or_code(self):
        self.lua(r'''
-- The reviewed native uses: the write domain's eagle.uses_per_rearm current value, on Eagles only.
assert(CP.native_uses('Eagle 110mm Rocket Pods')==3 and CP.native_uses('Eagle 500kg Bomb')==1)
assert(CP.native_uses(NAPALM)==nil)
local writes=#W.runtime.writes
local h=wait(CP.apply({carrier=NAPALM,icon=ICON,code=UUDD,uses=5}))
assert(h.status=='refused'and h.code=='NOT_AN_EAGLE',tostring(h.code)..': '..tostring(h.reason))
h=wait(CP.apply({carrier='Eagle 110mm Rocket Pods',text={name=NAME},uses=5}))
assert(h.status=='refused'and h.code=='INVALID'and tostring(h.reason):find('one transaction',1,true),tostring(h.reason))
h=wait(CP.apply({carrier='Eagle 110mm Rocket Pods',icon=ICON,code=UUDD,uses=21}))
assert(h.status=='refused'and h.code=='INVALID'and tostring(h.reason):find('uses must be 1..20',1,true))
assert(#W.runtime.writes==writes and W.read(ROW106,400)==CARRIER_ROW,'nothing written')
''')

    def test_restore_now_supersedes_a_restore_job_in_flight(self):
        self.lua(r'''
local h=wait(CP.apply(SPEC))
assert(h.status=='applied')
-- The ship's restore job started (between its reads), then the loadout screen opens: restored in this tick, the job
-- superseded (its callback never runs), nothing written twice.
local called=false
local job=CP.restore(function()called=true end)
local n=#W.runtime.writes
local r=CP.restore_now()
assert(r and r.status=='restored'and r.verify.exact and W.read(ROW106,400)==CARRIER_ROW,tostring(r))
assert(job.status=='superseded')
local after=#W.runtime.writes
tick(40)
assert(not called and#W.runtime.writes==after and W.read(ROW106,400)==CARRIER_ROW)
''')

    def test_the_lua_state_closing_restores(self):
        self.lua(r'''
local h=wait(CP.apply(SPEC))
assert(h.status=='applied'and custom(106))
CP.finalize_for_tests()
assert(W.read(ROW106,400)==CARRIER_ROW and not CP.applied())
''')


if __name__ == '__main__':
    unittest.main()
