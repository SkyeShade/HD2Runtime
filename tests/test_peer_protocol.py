"""The Runtime peer protocol hd2rt/1 (runtime/peer_protocol.lua; research/docs/runtime-peer-messaging-F5FEE03DCFDB.md,
section 3): the one lobby member value each Runtime publishes. Pure: it encodes and decodes semantic state only (a
version, hashes, a counter, custom stratagem ids) and refuses anything else whole."""
import unittest

from support import run

PRELUDE = r"""
local P=require('hd2runtime/runtime/peer_protocol')
local function refused(text,code,known)
    local s,c,why=P.decode(text,known)
    assert(s==nil and c==code,('%q: expected %s, got %s %s'):format(text,code,tostring(c),tostring(why)))
end
"""


class PeerProtocolTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body + "\nreturn 'ok'"), b'ok')

    def test_fnv1a_matches_the_reference_vectors(self):
        self.lua(r"""
assert(P.fnv1a('')=='811C9DC5')
assert(P.fnv1a('a')=='E40C292C')
assert(P.fnv1a('foobar')=='BF9CF968')
assert(P.fnv1a(string.rep('\255',64))==P.fnv1a(string.rep('\255',64)))   -- exact in doubles: deterministic
""")

    def test_a_state_round_trips_and_its_text_is_exactly_the_grammar(self):
        self.lua(r"""
local text=assert(P.encode({version='0.30.0-dev',registry='0A1B2C3D',seq=7,
    slots={'orbital_gas_barrage',false,'pelican_close_air_support'},host={table='DEADBEEF',carrier='01234567'}}))
assert(text=='hd2rt/1;0.30.0-dev;0A1B2C3D;7;orbital_gas_barrage,-,pelican_close_air_support,-;host:DEADBEEF:01234567',
    text)
local s=assert(P.decode(text,{orbital_gas_barrage=true,pelican_close_air_support=true}))
assert(s.protocol=='hd2rt/1'and s.version=='0.30.0-dev'and s.registry=='0A1B2C3D'and s.seq==7)
assert(s.slots[1]=='orbital_gas_barrage'and s.slots[2]==false and s.slots[3]=='pelican_close_air_support'
    and s.slots[4]==false)
assert(s.host.table=='DEADBEEF'and s.host.carrier=='01234567')
-- Without the host field, and grammar-only (no registry given).
local plain=assert(P.encode({version='0.30.0-dev',registry='811C9DC5',seq=1}))
assert(plain=='hd2rt/1;0.30.0-dev;811C9DC5;1;-,-,-,-')
assert(P.decode(plain).host==nil)
-- The longest legal value (four 48-character ids) stays well inside the channel's 512 bytes.
local long=string.rep('a',48)
local max=assert(P.encode({version=string.rep('9',32),registry='FFFFFFFF',seq=P.MAX_SEQ,slots={long,long,long,long},
    host={table='FFFFFFFF',carrier='FFFFFFFF'}}))
assert(#max<P.MAX and P.decode(max,{[long]=true}).slots[4]==long,#max)
""")

    def test_encode_refuses_what_the_grammar_cannot_carry(self):
        self.lua(r"""
local function bad(state,what)
    local t,c=P.encode(state)
    assert(t==nil and c=='INVALID',what)
end
local ok={version='0.30.0-dev',registry='0A1B2C3D',seq=1}
bad({version='0.30 dev',registry='0A1B2C3D',seq=1},'a space in the version')
bad({version='0.30.0-dev',registry='0a1b2c3d',seq=1},'a lowercase hash')
bad({version='0.30.0-dev',registry='0A1B2C3D',seq=0},'seq 0')
bad({version='0.30.0-dev',registry='0A1B2C3D',seq=1.5},'a fractional seq')
bad({version='0.30.0-dev',registry='0A1B2C3D',seq=1,slots={'Gas'}},'an uppercase id')
bad({version='0.30.0-dev',registry='0A1B2C3D',seq=1,slots={string.rep('a',49)}},'a 49-character id')
bad({version='0.30.0-dev',registry='0A1B2C3D',seq=1,slots={'a;b'}},'a separator in an id')
bad({version='0.30.0-dev',registry='0A1B2C3D',seq=1,host={table='DEADBEEF'}},'half a host field')
assert(P.encode(ok))
""")

    def test_decode_refuses_anything_but_the_grammar_whole(self):
        self.lua(r"""
local good='hd2rt/1;0.30.0-dev;0A1B2C3D;3;orbital_gas_barrage,-,-,-'
assert(P.decode(good))
refused('','MALFORMED')
refused('hello','MALFORMED')
refused('hd2rt/2;0.30.0-dev;0A1B2C3D;3;-,-,-,-','PROTOCOL')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-','MALFORMED')                 -- three slots
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,-,-','MALFORMED')             -- five
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;03;-,-,-,-','MALFORMED')              -- a leading zero
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;0;-,-,-,-','MALFORMED')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;2147483648;-,-,-,-','MALFORMED')      -- above the counter's range
refused('hd2rt/1;0.30.0-dev;0a1b2c3d;3;-,-,-,-','MALFORMED')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,-;host:DEADBEEF','MALFORMED')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,-;extra','MALFORMED')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,-;host:DEADBEEF:01234567;x','MALFORMED')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,-\0','MALFORMED')            -- not printable
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,'..string.rep('a',600),'MALFORMED')
-- Nothing address- or write-like is a value: an id starts with a letter and is lowercase [a-z0-9_].
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;0x7ff6086d0000,-,-,-','MALFORMED')
refused('hd2rt/1;0.30.0-dev;0A1B2C3D;3;+0xD4=2,-,-,-','MALFORMED')
-- An id this machine has not registered is never guessed at.
refused(good,'UNKNOWN_ID',{pelican_close_air_support=true})
assert(P.decode(good,{orbital_gas_barrage=true}))
""")

    def test_call_items_carry_only_ids_and_network_ids(self):
        self.lua(r"""
-- In a mission: this member's own calls' delivered items (custom id, the call's beacon network id, the launchers'
-- network ids), after the host field when there is one.
local state={version='0.30.0-dev',registry='0A1B2C3D',seq=9,slots={'eat17_gas',false,false,false},
    host={table='DEADBEEF',carrier='01234567'},items={{id='eat17_gas',beacon=4114,items={4117,4118}},
    {id='eat17_gas',beacon=4137,items={4139,4140}}}}
local text=assert(P.encode(state))
assert(text=='hd2rt/1;0.30.0-dev;0A1B2C3D;9;eat17_gas,-,-,-;host:DEADBEEF:01234567;items:eat17_gas@4114=4117+4118,'
    ..'eat17_gas@4137=4139+4140',text)
local s=assert(P.decode(text,{eat17_gas=true}))
assert(s.host.table=='DEADBEEF'and#s.items==2 and s.items[1].id=='eat17_gas'and s.items[1].beacon==4114
    and s.items[1].items[1]==4117 and s.items[1].items[2]==4118 and s.items[2].beacon==4137)
-- Without the host field; none (an empty list is no field at all).
state.host=nil
local t2=assert(P.encode(state))
assert(t2:find(';eat17_gas,-,-,-;items:eat17_gas@4114=',1,true)and#assert(P.decode(t2)).items==2)
state.items={}
local t3=assert(P.encode(state))
assert(t3=='hd2rt/1;0.30.0-dev;0A1B2C3D;9;eat17_gas,-,-,-'and#assert(P.decode(t3)).items==0)
-- Refused whole: anything but ids and network ids (1..32766), too many calls or items, a beacon twice, the wrong order,
-- an unregistered id.
local base='hd2rt/1;0.30.0-dev;0A1B2C3D;3;-,-,-,-;'
assert(P.decode(base..'items:eat17_gas@1=2'))
refused(base..'items:eat17_gas@0=2','MALFORMED')
refused(base..'items:eat17_gas@32767=2','MALFORMED')                       -- the game's "none"
refused(base..'items:eat17_gas@4114=04117','MALFORMED')                    -- a leading zero
refused(base..'items:eat17_gas@4114=0x1015','MALFORMED')
refused(base..'items:eat17_gas@4114=+0x7C','MALFORMED')
refused(base..'items:eat17_gas@4114=','MALFORMED')
refused(base..'items:EAT@4114=1','MALFORMED')
refused(base..'items:eat17_gas@4114=1+2+3+4+5+6+7+8+9','MALFORMED')       -- a rack holds 8
refused(base..'items:a@1=1,a@2=1,a@3=1,a@4=1,a@5=1','MALFORMED')          -- 4 calls at most
refused(base..'items:a@1=1,b@1=2','MALFORMED')                            -- one beacon, one call
refused(base..'items:a@1=1;host:DEADBEEF:01234567','MALFORMED')           -- host first
refused(base..'items:a@1=1;items:a@2=1','MALFORMED')
refused(base..'items:eat17_gas@4114=4117','UNKNOWN_ID',{pelican_close_air_support=true})
for _,bad in ipairs({{{id='eat17_gas',beacon=0,items={1}}},{{id='eat17_gas',beacon=1,items={}}},
        {{id='eat17_gas',beacon=1,items={32767}}},{{id='Bad',beacon=1,items={1}}},{{id='a',beacon=1,items={1.5}}}})do
    local v,c=P.encode({version='0.30.0-dev',registry='0A1B2C3D',seq=1,slots={},items=bad})
    assert(v==nil and c=='INVALID')
end
""")

    def test_hashes_are_order_independent_and_compatibility_is_exact(self):
        self.lua(r"""
local a=P.registry_hash({{id='orbital_gas_barrage',policy='offensive',family='orbital'},
    {id='pelican_close_air_support',policy='offensive',family=''}})
local b=P.registry_hash({{id='pelican_close_air_support',policy='offensive',family=''},
    {id='orbital_gas_barrage',policy='offensive',family='orbital'}})
assert(a==b and a~=P.registry_hash({{id='orbital_gas_barrage',policy='support',family='orbital'}}))
assert(P.registry_hash({})=='811C9DC5')
local t1=P.table_hash({['1111222233334444']={[0]='orbital_gas_barrage',[2]=false},
    ['5555666677778888']={[1]='orbital_gas_barrage'}})
local t2=P.table_hash({['5555666677778888']={[1]='orbital_gas_barrage'},
    ['1111222233334444']={[0]='orbital_gas_barrage'}})
assert(t1==t2,'an empty slot is not part of the table')
assert(P.carrier_hash({orbital_gas_barrage=1046219416,eat17_gas=3})==P.carrier_hash({eat17_gas=3,
    orbital_gas_barrage=1046219416}))
local mine={version='0.30.0-dev',registry=a}
assert(P.compatible(mine,{version='0.30.0-dev',registry=a}))
local ok,field=P.compatible(mine,{version='0.30.1-dev',registry=a});assert(not ok and field=='runtime version')
ok,field=P.compatible(mine,{version='0.30.0-dev',registry='00000000'});assert(not ok and field=='registry hash')
""")


if __name__ == '__main__':
    unittest.main()
