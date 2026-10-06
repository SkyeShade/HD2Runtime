"""The common provenance model of custom stratagem calls (runtime/custom_provenance.lua; 0.30 internal consolidation):
CustomCall and ProvenanceEntity records, roles, the mission registry and its summary. Behaviour-neutral bookkeeping."""
import unittest

from support import run


class CustomProvenanceTests(unittest.TestCase):
    def test_calls_entities_roles_and_the_registry(self):
        self.assertEqual(run(r"""
local P=require('hd2runtime/runtime/custom_provenance');P.reset()
local c=assert(P.call({custom_id='eat17g_clone',call_id='eat17g_clone#1',seq=1,caller_peer='AAAA',slot=2,
    carrier_stable_id=2934950455,beacon_network=4117,position={x=1,y=2,z=3},authority='caller'}))
assert(c.custom_id=='eat17g_clone'and c.position.y==2 and c.authority=='caller')
assert(P.call({})==nil and P.call({custom_id='x',authority='anyone'})==nil)
-- A call's entities: two launchers, a Pelican and its turret (parent), a barrage.
assert(P.entity({network_id=4119,custom_id='eat17g_clone',call=c.call_id,role='launcher',entity=760,realized=true}))
assert(P.entity({network_id=4120,custom_id='eat17g_clone',call=c.call_id,role='launcher',entity=761}))
assert(P.entity({network_id=4170,custom_id='pelican_close_air_support',call=4160,role='vehicle'}))
assert(P.entity({network_id=4171,custom_id='pelican_close_air_support',call=4160,role='turret',parent_network_id=4170}))
assert(P.entity({network_id=4300,custom_id='orbital_gas_barrage',call=4114,role='barrage'}))
assert(P.entity({network_id=1,custom_id='x',role='spaceship'})==nil,'an unknown role is refused')
assert(#P.list()==5 and#P.list({custom_id='eat17g_clone'})==2 and P.list({role='turret'})[1].parent_network_id==4170)
assert(P.realized(4120,761)and P.get(4120).realized and not P.realized(9999))
assert(P.summary()=='5 entities (barrage 1, launcher 2, turret 1, vehicle 1), 2 realized here',P.summary())
-- A network id the game reuses names its newest entity.
P.entity({network_id=4119,custom_id='eat17g_clone',call='eat17g_clone#2',role='launcher',entity=801})
assert(#P.list()==5 and P.get(4119).call=='eat17g_clone#2')
P.reset()
assert(#P.list()==0)
return 'ok'
"""), b'ok')


if __name__ == '__main__':
    unittest.main()
