"""runtime/pelican_gatling.lua (the Gatling turret experiment, live-proven by PelicanGatlingProof 0.2.0, whose source is
kept in proof/PelicanGatlingProof/archive; research/docs/pelican-cas-F5FEE03DCFDB.md section 16): one Runtime-spawned
Pelican's chin turret replaced by a Gatling turret entity (REPLACE) or given its own Gatling weapon record (WEAPON),
through the game's own routines, on the offline Pelican world of tests/test_pelicans.py. The game's
routines are simulated (they record their calls and do what the research found they do); the guards, the guarded
write and the read-back are the Runtime's own."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS

GATLING = r"""
local gatling=require('hd2runtime/runtime/pelican_gatling')
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function chord(key)
    keys[0x11]=true;keys[0x10]=true;keys[input.keys[key]]=true;tick()
    keys[input.keys[key]]=false;keys[0x10]=false;keys[0x11]=false;tick()
end
local scheduler=require('hd2runtime/runtime/scheduler')
gatling.reset()
local GD,TW,A=PE.gatling,PE.turretWeapon,PE.attachment
for _,name in ipairs({'attach','remove','unlink','copy','destroy'})do W.write(W.GAME+GD[name].rva,b.unhex(GD[name].prologue))end
local CHIN=b.unhex(GD.chinTurretResource):reverse()
local GAT=b.unhex(GD.gatlingResource):reverse()
local GX={calls={},removed={},link=0x400100}
-- Runs fn once inside the Runtime's own update (as the proof's timer does).
local function in_update(fn)
    local o={status='active'}
    function o.tick()if o.status~='complete'then o.status='complete';GX.ret={fn()}end end
    function o.cancel()o.status='cancelled'end
    scheduler.attach(o);tick()
    local ret=GX.ret or{};GX.ret=nil
    return unpack(ret)
end
local function mapof(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end
-- The managers, allocated once (several entities each).
local function manager(c,size)
    local comp=W.alloc(size or 0x200);W.write(W.GAME+c.global,W.u64(comp))
    return comp,map(comp,mapof(c.map))
end
local MT=GD.mount
local MCOMP,mkey=manager(MT)
local MCHILD=W.alloc(0x1000);W.write(MCOMP+MT.children,W.u64(MCHILD))
local ACOMP,akey=manager({global=A.global,map=A.map})
local ARECS=W.alloc(0x2000);W.write(ACOMP+A.records,W.u64(ARECS))
local PW,MG,WP=TW.projectileWeapon,TW.magazine,TW.weapon
local PCOMP,pkey=manager(PW)
local PHANDLES,PINST,PROF,PCUR=W.alloc(0x100),W.alloc(0x800),W.alloc(0x200),W.alloc(0x1000)
W.write(PCOMP+0x68,W.u64(PHANDLES));W.write(PCOMP+PW.instances,W.u64(PINST));W.write(PCOMP+PW.rof,W.u64(PROF))
W.write(PCOMP+PW.current,W.u64(PCUR))
local ckey=map(PCOMP,mapof(PW.copies))
local PCOPIES=W.alloc(0x1000);W.write(PCOMP+PW.copyRecords,W.u64(PCOPIES))
W.write(PCOMP+GD.copyCapacity,W.u32(128));W.write(PCOMP+PW.copyCount,W.u32(0))
local WCOMP,wkey=manager(WP)
local WRECS=W.alloc(0x200);W.write(WCOMP+WP.records,W.u64(WRECS))
local MGCOMP,mgkey=manager(MG)
map(MGCOMP,mapof(MG.copies))
local MGRECS=W.alloc(0x1000);W.write(MGCOMP+MG.records,W.u64(MGRECS))
-- Its replicated entries (12 bytes: spare magazines, the authoritative rounds, the chamber-empty flag).
local AMD=PE.ammo
local MGENTS=W.alloc(0x1000);W.write(MGCOMP+AMD.entries,W.u64(MGENTS))
manager(TW.heat)
local _,ukey=manager(TW.windUp)
-- Where the bullets go (research "aim"): WeaponData (its instance records 0x3F0), the targeting state and the wielder.
local AIMD=PE.aim
local WDCOMP,wdkey=manager(AIMD.weaponData)
local WDRECS=W.alloc(0x2000);W.write(WDCOMP+AIMD.weaponData.records,W.u64(WDRECS))
local TGCOMP,tgkey=manager(AIMD.targeting)
local TGRECS=W.alloc(0x1000);W.write(TGCOMP+AIMD.targeting.records,W.u64(TGRECS))
local WLCOMP,wlkey=manager(AIMD.wielder)
local WLRECS=W.alloc(0x1000);W.write(WLCOMP+AIMD.wielder.records,W.u64(WLRECS))
-- The type tables (component world): the chin turret and the Gatling in the ProjectileWeapon and magazine tables, and
-- the Gatling's behaviour (213) in the behaviour settings.
local CW=SPAWN.world
local function type_table(t,entries)
    local tab=W.alloc(t.records+4*t.stride+0x100);W.write(CW+t.offset,W.u64(tab))
    for k,e in ipairs(entries)do
        local lo,hi=b.u32(e.key,0),b.u32(e.key,4)
        local slot=((hi%t.slots)*(4294967296%t.slots)+lo%t.slots)%t.slots
        W.write(tab+slot*16,e.key..W.u32(k-1)..W.u32(0))
        W.write(tab+t.records+(k-1)*t.stride,e.bytes..string.rep('\0',t.stride-#e.bytes))
    end
    return tab
end
-- Each type's ProjectileWeapon record: projectile, RPM slots and the fire effects block (+0xA0..+0xDF) as observed: effect
-- A's node and the casing's nodes "ejector", the casing particles and parameters.
local CSD=PE.casing
local function pwrec(projectile,rpm,o)
    local raw=W.u32(projectile)..f32(0)..f32(rpm)..f32(0)
    raw=raw..string.rep('\0',CSD.effectsEnd-#raw)
    local function put(at,bytes)raw=raw:sub(1,at)..bytes..raw:sub(at+#bytes+1)end
    put(CSD.effects+8,b.unhex(CSD.ejectorNode):reverse())
    put(CSD.particles,b.unhex(o.particles):reverse())
    for k,n in ipairs(o.nodes)do put(CSD.nodes+(k-1)*4,b.unhex(n):reverse())end
    for k,v in ipairs(o.parameters)do put(CSD.parameters+(k-1)*4,W.u32(v))end
    return raw
end
local CHIN_PW=pwrec(120,300,CSD.observed.chinTurret)
local GAT_PW=pwrec(148,1600,CSD.observed.gatlingSentry)
local PWTAB=type_table(GD.pwTypes,{{key=CHIN,bytes=CHIN_PW},{key=GAT,bytes=GAT_PW}})
-- Each type's magazine: the pattern, then the observed capacity, spare magazines, refill, maximum and chamber flag.
local function magrec(head,o)
    local raw=head..string.rep('\0',GD.magazineTypes.stride-#head)
    local function put(at,bytes)raw=raw:sub(1,at)..bytes..raw:sub(at+#bytes+1)end
    put(AMD.capacity,W.u32(o.capacity));put(AMD.spareMagazines,W.u32(o.spareMagazines))
    put(AMD.perResupply,W.u32(o.perResupply));put(AMD.maxSpareMagazines,W.u32(o.maxSpareMagazines))
    put(AMD.chamber,string.char(o.chamber))
    return raw
end
-- Each type's WeaponData: recoil blocks A (+0x00) and B (+0x1C), spread (+0x54), as observed.
local function wdrec(o)
    local raw=''
    for _,v in ipairs(o.blockA)do raw=raw..f32(v)end
    for _,v in ipairs(o.blockB)do raw=raw..f32(v)end
    raw=raw..string.rep('\0',0x54-#raw)..f32(o.spread[1])..f32(o.spread[2])
    return raw
end
type_table(AIMD.weaponData.types,{{key=CHIN,bytes=wdrec(AIMD.observed.chinTurret)},
    {key=GAT,bytes=wdrec(AIMD.observed.gatlingSentry)}})
-- The projectile rows (the projectile settings table, research "apDonor"): the standard round 148 and the AP4 donor 275
-- (type, velocity +0x20, mass +0x24, damage id +0x3C).
local PJTABLE=require('hd2runtime/domains/event_natives').projectile.settingsTable
local function projectile_row(kind,velocity,mass,damage)
    local row=W.alloc(272)
    W.write(row,W.u32(kind));W.write(row+0x20,f32(velocity)..f32(mass));W.write(row+0x3C,W.u32(damage))
    W.write(W.GAME+PJTABLE+kind*8,W.u64(row))
    return row
end
local ROW148,ROW275=projectile_row(148,820,11,125),projectile_row(275,980,52,205)
-- Attribution (research "attribution"): the Tag component (64-bit masks; the AI's entity flags), the faction component
-- (32-bit masks) and the Wieldable component (a weapon's wielder).
local AT=PE.attribution
local TAGCOMP,tagkey=manager(AT.tags)
local TAGVALS=W.alloc(0x1000);W.write(TAGCOMP+AT.tags.values,W.u64(TAGVALS))
local tagged,tagnext={},0
local function tags(entity,lo,hi)
    local i=tagged[entity]
    if not i then i=tagnext;tagnext=tagnext+1;tagged[entity]=i;tagkey(entity,i)end
    W.write(TAGVALS+i*8,W.u32(lo)..W.u32(hi or 0))
    return TAGVALS+i*8
end
local FACCOMP,fackey=manager(PE.targetSet.faction,PE.targetSet.faction.masks+0x10)
local FACMASKS=W.alloc(0x400);W.write(FACCOMP+PE.targetSet.faction.masks,W.u64(FACMASKS))
local factioned,factionnext={},0
local function faction(entity,mask)
    local i=factioned[entity]
    if not i then i=factionnext;factionnext=factionnext+1;factioned[entity]=i;fackey(entity,i)end
    W.write(FACMASKS+i*4,W.u32(mask))
end
local WIELDCOMP,wieldkey=manager(AT.wieldable)
local WIELDERS=W.alloc(0x200);W.write(WIELDCOMP+AT.wieldable.wielder,W.u64(WIELDERS))
local MAGTYPES=type_table(GD.magazineTypes,{{key=CHIN,bytes=magrec(W.u32(0),AMD.observed.chinTurret)},
    {key=GAT,bytes=magrec(W.u32(1)..W.u32(148)..W.u32(148)..W.u32(148)..W.u32(242)..W.u32(148),
        AMD.observed.gatlingSentry)}})
do
    local VS=PE.variants.settings
    local tab=W.alloc(VS.entries+0x100);W.write(CW+VS.offset,W.u64(tab))
    local lo,hi=b.u32(GAT,0),b.u32(GAT,4)
    local slot=((hi%VS.slots)*(4294967296%VS.slots)+lo%VS.slots)%VS.slots
    W.write(tab+slot*16,GAT..W.u32(0)..W.u32(0))
    W.write(tab+VS.entries,W.u32(213)..f32(0)..W.u32(0))
end
-- The Runtime's asset loader with a simulated native loader (as tests/test_asset_loading.py does): each request
-- counted; the Gatling Sentry's package resident unless GX.absent.
local core_assets=require('hd2runtime/core/assets')
core_assets.reset()
local LOADER_MAP=W.alloc(0x1000)                          -- an empty reference map (16 entries of 16 zero bytes)
local LOADER=W.alloc(0x100);W.write(LOADER,W.u64(LOADER_MAP)..W.u64(LOADER_MAP)..W.u64(LOADER_MAP)..W.u64(LOADER_MAP))
core_assets.prove=function()return {instance=LOADER,request=2,capacity=16}end
GX.requests=0
W.runtime.package_request=function()GX.requests=GX.requests+1 end
-- The Gatling Sentry's package: resident unless GX.absent.
local GPACK=require('hd2runtime/core/assets').dependency_for_stratagem(GD.gatlingStratagem).package
local previous_state=W.runtime.package_state
W.runtime.package_state=function(hex)
    if hex==GPACK then return GX.absent and'absent'or'resident'end
    return previous_state and previous_state(hex)or'resident'
end
-- A weapon entity (index wi in the weapon managers).
local function weapon(entity,wi,o)
    pkey(entity,wi);wkey(entity,wi);mgkey(entity,wi)
    local handle=W.alloc(0x20);W.write(handle,o.resource..W.u32(entity));W.write(PHANDLES+wi*8,W.u64(handle))
    W.write(PINST+wi*PW.instanceStride+PW.interval,f32(60/o.rpm))
    W.write(PROF+wi*PW.rofStride+PW.rofSlots,f32(0)..f32(o.rpm)..f32(0)..W.u32(1))
    W.write(PCUR+wi*PW.currentStride+PW.currentRpm,f32(o.rpm))
    W.write(WRECS+wi*WP.stride,W.u32(0xC0))
    -- As the game spawns a magazine: capacity - 1 rounds and one chambered.
    W.write(MGRECS+wi*MG.stride,W.u32(499)..W.u32(o.pattern and 1 or 0)..W.u32(o.chambered)..W.u32(o.pattern and 5 or 0))
    W.write(MGENTS+wi*AMD.entryStride,W.u32(o.spares or 0)..W.u32(499)..W.u32(0))
    if o.windUp then ukey(entity,wi)end
    -- Its WeaponData instance record: its type's aim recoil (block B) copied in, as at creation.
    wdkey(entity,wi);tgkey(entity,wi);wlkey(entity,wi)
    local kind=o.resource==CHIN and AIMD.observed.chinTurret or AIMD.observed.gatlingSentry
    local blockB=''
    for _,v in ipairs(kind.blockB)do blockB=blockB..f32(v)end
    W.write(WDRECS+wi*AIMD.weaponData.stride+AIMD.weaponData.recoilB,blockB)
    -- Its spread: its type's times its own multipliers (1, as for every weapon in the snapshots), as at creation.
    local SPR=PE.spread
    W.write(WDRECS+wi*AIMD.weaponData.stride+SPR.instance,f32(kind.spread[1])..f32(kind.spread[2])..W.u32(0))
    W.write(WDRECS+wi*AIMD.weaponData.stride+SPR.multipliers[1],f32(1))
    W.write(WDRECS+wi*AIMD.weaponData.stride+SPR.multipliers[2],f32(1))
end
local weapon_entity=weapon
local anext=0
local function attachable(entity,link,node,o)
    o=o or{}
    akey(entity,anext)
    local rec=ARECS+anext*A.stride
    W.write(rec,W.u32(link)..W.u32(node))
    W.write(rec+A.worldPosition,f32(o.x or 0)..f32(o.y or 0)..f32(o.z or 0))
    W.write(rec+GD.attachable.offset,f32(0)..f32(1.5)..f32(-2))
    W.write(rec+GD.attachable.rotation,f32(0)..f32(0)..f32(0)..f32(1))
    anext=anext+1
end
local function drop_entity(id)
    local keys=b.pointer(W.read(BCOMP+BC.keys,8),0)
    for k=0,63 do if b.u32(W.read(keys+k*8,4),0)==id then W.write(keys+k*8,W.u32(4294967295)..W.u32(0))end end
end
-- The game's routines, simulated.
W.runtime.native_spawn_gatling=function(entry,x,y,z,fx,fy)
    GX.calls[#GX.calls+1]={'spawn',entry,x,y,z,fx,fy}
    if GX.spawn_fails then return 0 end
    local id=9701
    transport(5,id,{resource=GAT,behaviour=213});stage(5,1,0);position(5,x,y,z)
    W.write(b.pointer(W.read(BHANDLES+5*8,8),0),GAT..W.u32(id)..W.u32(GX.link)..W.u32(0x7fff))
    attachable(id,0,0,{x=x,y=y,z=z})
    weapon(id,1,{resource=GAT,rpm=1600,pattern=true,chambered=148,windUp=true})
    return id
end
W.runtime.native_attach=function(entry,manager_,child,link,node,offset,rotation)
    GX.calls[#GX.calls+1]={'attach',entry,manager_,child,link,node,offset,rotation}
    if GX.attach_ignored then return true end
    local i=pelicans.index_of(world_module.open(),ACOMP,mapof(A.map),child)
    W.write(ARECS+i*A.stride,W.u32(link)..W.u32(node))
    return true
end
W.runtime.native_relation_unlink=function(entry,child,owner,parent)
    GX.calls[#GX.calls+1]={'unlink',entry,child,owner,parent};return true
end
W.runtime.native_remove_entity=function(entry,world_,entity)
    GX.calls[#GX.calls+1]={'remove',entry,world_,entity}
    if GX.remove_deferred and entity==8102 then return true end   -- a flagged network object: only a request is sent
    GX.removed[entity]=true;drop_entity(entity);return true
end
W.runtime.native_destroy_entity=function(entry,world_,record)
    GX.calls[#GX.calls+1]={'destroy',entry,world_,record}
    local entity=b.u32(W.read(record+8,4),0)
    GX.removed[entity]=true;drop_entity(entity);return true
end
W.runtime.native_weapon_copy=function(entry,manager_,handle)
    GX.calls[#GX.calls+1]={'copy',entry,manager_,handle}
    local entity=b.u32(W.read(handle+8,4),0)
    ckey(entity,0)
    W.write(PCOPIES,W.read(PWTAB+GD.pwTypes.records,PW.copyStride))
    W.write(PCOMP+PW.copyCount,W.u32(1))
    return true
end
-- The scene: a Runtime Pelican (9501, unit link 0x40007D) hovering, its chin turret 8102 at node 41, the Pelican's mount
-- record naming the turret in slot 0.
local function scene()
    pelicans.request({x=10,y=20,z=5,fx=0,fy=1,ax=60,ay=70,az=2,owner='mods/test/pelican'},function()end)
    tick()
    stage(0,6,0);position(0,60,70,15)
    W.write(b.pointer(W.read(BHANDLES,8),0),PELICAN..W.u32(9501)..W.u32(0x40007D)..W.u32(700))
    transport(1,8102,{resource=CHIN,behaviour=645});stage(1,1,0);position(1,60,70,12)
    W.write(b.pointer(W.read(BHANDLES+8,8),0),CHIN..W.u32(8102)..W.u32(0x40007E)..W.u32(701)..W.u32(1))  -- the host's
    attachable(8102,0x40007D,41,{x=60,y=70,z=12})
    weapon(8102,0,{resource=CHIN,rpm=300,chambered=120,spares=6})
    -- Its muzzle where the turret is (its transform record keeps its creation point, never updated for a mounted child;
    -- its WeaponData's muzzle follows it), pointing east and a little down.
    W.write(WDRECS+AIMD.weaponData.aim,f32(160)..f32(70)..f32(0))
    W.write(WDRECS+AIMD.weaponData.muzzle,f32(60)..f32(70)..f32(12))
    -- As the chin turret's data makes it: it wields itself, faction 1, tags {4, 0x2000000, 0x10000000 (no credit)}.
    wieldkey(8102,0);W.write(WIELDERS,W.u32(8102))
    faction(8102,1)
    tags(8102,0x12000004)
    mkey(9501,0);W.write(MCHILD,W.u32(8102)..string.rep('\0',20))
    tcount(1)
end
"""


class PelicanGatlingTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + body
            + '\nend)()\n'), b'ok')

    def test_the_research_and_domain(self):
        research = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        pinned = {p['rva'] for p in research['pins']['gatlingTurret']}
        # The mount callbacks, the attach call and its routine, the teardown's unlink and removal, the type tables.
        self.assertTrue({0x548F1A, 0x548F23, 0x5A8BFD, 0x812EA1, 0x5A83E7, 0x5A84A6, 0x5A858E, 0xFDC399, 0x514C1F,
            0x4F32FF} <= pinned)
        g = research['gatling']
        self.assertEqual((g['attach']['rva'], g['remove']['rva'], g['unlink']['rva'], g['copy']['rva']),
            (0x812540, 0xFDC310, 0xB0B020, 0x61AF10))
        self.assertEqual(research['attachment']['observedPair']['mountChildren'][0],
            research['attachment']['observedPair']['child'])

    def test_the_adapters_are_narrow(self):
        source = (ROOT / 'runtime/windows_write.lua').read_text(encoding='utf-8')
        for name in ('native_spawn_gatling', 'native_attach', 'native_relation_unlink', 'native_remove_entity',
                'native_weapon_copy'):
            self.assertIn('function runtime.' + name + '(', source)
        # The Gatling spawn names the gatling_turret entity only; nothing public exposes these calls.
        self.assertIn("local GATLING='\\112\\29\\227\\88\\207\\214\\133\\239'", source)
        for path in list((ROOT / 'api').glob('*.lua')):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('pelican_gatling', text, path.name)
            self.assertNotIn('native_attach', text, path.name)

    def test_replace(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local before=gatling.shared(world)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return gatling.replace(world,9501,'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.original==8102 and r.gatling==9701 and r.node==41 and r.slot==0 and r.writes==1)
-- The calls, in order: spawn at the chin turret, attach to the Pelican's unit at node 41, unlink and remove the chin turret.
local kinds={};for k,c in ipairs(GX.calls)do kinds[k]=c[1]end
assert(table.concat(kinds,',')=='spawn,attach,unlink,remove',table.concat(kinds,','))
local s,a,u,m=GX.calls[1],GX.calls[2],GX.calls[3],GX.calls[4]
assert(s[2]==W.GAME+PE.spawn.rva and math.abs(s[3]-60)<1e-3 and math.abs(s[5]-12)<1e-3)
assert(a[2]==W.GAME+GD.attach.rva and a[3]==ACOMP and a[4]==9701 and a[5]==0x40007D and a[6]==41
    and math.abs(a[7].y-1.5)<1e-3 and a[8].w==1)
assert(u[2]==W.GAME+GD.unlink.rva and u[3]==8102 and u[4]==MCOMP and u[5]==9501)
assert(m[2]==W.GAME+GD.remove.rva and m[4]==8102 and m[3]==b.pointer(W.read(W.GAME+GD.world,8),0))
-- One write: the Pelican's own mount record, slot 0: 8102 -> 9701.
assert(#W.runtime.writes==writes+1 and b.u32(W.read(MCHILD,4),0)==9701)
local state=gatling.inspect(world,9501)
assert(#state.attached==1 and state.turret.entity==9701 and state.turret.node==41 and state.mount.slot==0)
assert(state.turret.weapon.magazine.pattern and state.turret.weapon.windUp)
assert(gatling.shared_same(before,gatling.shared(world)))
return 'ok'
""")

    def test_replace_refusals(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local writes=#W.runtime.writes
-- Outside the Runtime's update: refused, nothing called.
local r,code=gatling.replace(world,9501,'test')
assert(r==nil and code=='NOT_GAME_THREAD'and #GX.calls==0)
-- Not hovering.
stage(0,3,0)
r,code=in_update(function()return gatling.replace(world,9501,'test')end)
assert(r==nil and code=='NOT_HOVERING'and #GX.calls==0,tostring(code))
stage(0,6,0)
-- Not a Runtime Pelican.
r,code=in_update(function()return gatling.replace(world,8102,'test')end)
assert(r==nil and code=='NOT_RUNTIME_PELICAN'and #GX.calls==0,tostring(code))
-- The Gatling Sentry's package not loaded.
GX.absent=true
r,code=in_update(function()return gatling.replace(world,9501,'test')end)
assert(r==nil and code=='GATLING_NOT_LOADED'and #GX.calls==0,tostring(code))
GX.absent=nil
-- The mount record no longer names the chin turret.
W.write(MCHILD,W.u32(1234))
r,code=in_update(function()return gatling.replace(world,9501,'test')end)
assert(r==nil and code=='MOUNT_UNEXPECTED'and #GX.calls==0,tostring(code))
W.write(MCHILD,W.u32(8102))
-- A routine's entry bytes changed: refused before any call.
W.write(W.GAME+GD.attach.rva,'\204')
r,code=in_update(function()return gatling.replace(world,9501,'test')end)
assert(r==nil and code=='UNSUPPORTED_BUILD'and #GX.calls==0,tostring(code))
W.write(W.GAME+GD.attach.rva,b.unhex(GD.attach.prologue))
-- The attach does not take: the Gatling is removed again, the chin turret and the mount record are left as they were.
GX.attach_ignored=true
r,code=in_update(function()return gatling.replace(world,9501,'test')end)
assert(r==nil and code=='ATTACH_FAILED',tostring(code))
assert(GX.calls[#GX.calls][1]=='remove'and GX.calls[#GX.calls][4]==9701 and not GX.removed[8102])
assert(#W.runtime.writes==writes and b.u32(W.read(MCHILD,4),0)==8102)
return 'ok'
""")

    def test_weapon(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return gatling.weapon(world,9501,'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.turret==8102 and r.copy==0 and r.writes==2)
assert(#GX.calls==1 and GX.calls[1][1]=='copy'and GX.calls[1][2]==W.GAME+GD.copy.rva and GX.calls[1][3]==PCOMP)
local w=pelicans.weapon_config(world,8102)
assert(w.copy.projectileType==148 and w.currentRpm==1600)
-- The type record is unchanged; only the turret's own copy and its own current RPM were written.
assert(b.u32(W.read(PWTAB+GD.pwTypes.records,4),0)==120 and #W.runtime.writes==writes+2)
-- Again: the turret now has its own record: refused.
local again,code2=in_update(function()return gatling.weapon(world,9501,'test')end)
assert(again==nil and code2=='COPY_EXISTS',tostring(code2))
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
