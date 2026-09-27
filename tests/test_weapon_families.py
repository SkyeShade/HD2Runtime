import json
import unittest

from support import ROOT,run


class WeaponFamilySchemaTests(unittest.TestCase):
    def test_reviewed_family_paths_and_provenance(self):
        run("""
local s=require('hd2runtime/schemas/weapon_mapper').fields
assert(s.arc_type.structure=='ArcWeaponComponentData'and s.arc_type.offset==0)
assert(s.arc_fire_rate.offset==4 and s.arc_velocity.structure=='ArcSettings')
assert(s.beam_type.structure=='BeamWeaponComponentData'and s.beam_range.offset==8)
assert(s.spray_damage_type.offset==200 and s.spray_damage_type.linked_structure=='DamageInfo')
assert(s.melee_damage_type.offset==12 and s.melee_damage_type.linked_structure=='DamageInfo')
assert(s.rounds_primary_projectile_type.offset==64)
assert(s.rounds_alternate_projectile_type.offset==68)
for _,name in ipairs({'arc_type','beam_type','spray_damage_type','melee_damage_type',
 'rounds_primary_projectile_type','rounds_alternate_projectile_type','ergonomics',
 'primary_fire_mode','is_suppressed','horizontal_recoil','vertical_recoil','recoil'})do
 local e=s[name].evidence
 assert(e.structural_candidate and e.schema_labelled and e.pending_gameplay_confirmation)
 assert(not e.gameplay_proven and not e.native_consumer_proven)
end
return'ok'
""")

    def test_attack_family_compatibility_is_hard(self):
        run("""
local m=require('hd2runtime/primary_mapper/matcher')
local function attack(kind)return {name=kind,kind=kind,standard_damage=50,durable_damage=25,
 ap_direct=3,ap_slight=3,ap_large=3}end
local weapons={}
for _,kind in ipairs({'Arc','Beam','Spray','Melee','Projectile'})do
 weapons[#weapons+1]={name=kind,slot='secondary',attacks={attack(kind)}}
end
for _,kind in ipairs({'Arc','Beam','Spray','Melee','Projectile'})do
 local r=m.rank({attack_kind=kind,weapon_slot='secondary',standard_damage=50,durable_damage=25,
  ap_direct=3,ap_slight=3,ap_large=3},{weapons=weapons})
 assert(r.rankedWikiMatches[1].name==kind)
 for _,match in ipairs(r.allWikiMatches)do
  if match.name~=kind then assert(not match.structurallyCompatible)end
 end
end
return'ok'
""")

    def test_round_feed_primary_and_alternate_are_ranked_independently(self):
        run("""
local m=require('hd2runtime/primary_mapper/matcher')
local runtime={weapon_slot='primary',fire_rate=100,runtime_attacks={
 {kind='Projectile',role='feed_primary',projectileType=1,resolvedFields={standard_damage=10,
  durable_damage=5,ap_direct=2,ap_slight=2,ap_large=2,projectile_velocity=300}},
 {kind='Projectile',role='feed_alternate',projectileType=2,resolvedFields={standard_damage=80,
  durable_damage=40,ap_direct=3,ap_slight=3,ap_large=3,projectile_velocity=500}}}}
local primary={name='primary',kind='Projectile',standard_damage=10,durable_damage=5,
 ap_direct=2,ap_slight=2,ap_large=2,projectile_velocity=300}
local alternate={name='alternate',kind='Projectile',standard_damage=80,durable_damage=40,
 ap_direct=3,ap_slight=3,ap_large=3,projectile_velocity=500}
local r=m.rank(runtime,{weapons={{name='Feed weapon',slot='primary',fire_rate=100,
 attacks={alternate}},{name='Other',slot='primary',fire_rate=100,attacks={primary}}}})
local top=r.rankedWikiMatches[1]
assert(top.name=='Feed weapon'and top.runtimeAttackRole=='feed_alternate')
assert(top.matchedAttackBranch=='alternate')
return'ok'
""")

    def test_weapon_data_only_evidence_requires_player_slot(self):
        run("""
local m=require('hd2runtime/primary_mapper/matcher')
local dataset={weapons={{name='Pistol',slot='secondary',fire_rate=900,ergonomics=100,sway=1,
 spread_horizontal=10,spread_vertical=10,attacks={{name='P',kind='Projectile'}}}}}
local fields={weapon_data_only=true,attack_kind='Projectile',fire_rate=900,ergonomics=100,sway=1,
 spread_horizontal=10,spread_vertical=10}
assert(m.rank(fields,dataset).status=='UNMATCHED')
fields.weapon_slot='secondary'
assert(m.rank(fields,dataset).status=='STRONG')
return'ok'
""")

    def test_read_only_family_mapper_has_no_write_or_protection_capability(self):
        body='\n'.join((ROOT/path).read_text() for path in ('api/weapon_mapper.lua',
            'runtime/discover.lua','schemas/weapon_mapper.lua'))
        for token in ('VirtualProtect','WriteProcessMemory','windows_write','guarded_write'):
            self.assertNotIn(token,body)

    def test_damage_status_effect_layout_is_schema_bounded(self):
        body=(ROOT/'api/weapon_mapper.lua').read_text()
        self.assertIn('local offset=44+index*8',body)
        self.assertIn("strength=b.value(damage_bytes,offset+4,'f32')",body)


class WeaponFamilyResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'research/weapon-family-expansion-F5FEE03DCFDB.json').read_text())

    def test_family_gains_and_remaining_are_pinned(self):
        report=self.report
        self.assertEqual(report['safety'],{'writes':0,'protectionChanges':0,
            'fixtureFallback':'disabled','mode':'snapshot'})
        self.assertEqual(report['final']['totalIdentitiesResolved'],75)
        self.assertEqual(report['final']['totalUniqueResolved'],68)
        gains=report['resolutionGains']
        self.assertEqual(gains['ArcWeaponComponentData'],['ARC-12 Blitzer'])
        self.assertIn('LAS-13 Trident',gains['BeamWeaponComponentData'])
        self.assertEqual(len(gains['MeleeWeaponComponentData']),6)
        self.assertIn('SG-22 Bushwhacker',gains['WeaponRoundsComponentData'])
        self.assertEqual(report['remainingUnresolvedWeapons'],['P-2 Peacemaker','SG-20 Halt',
            'SG-451 Cookout','SG-8 Punisher','SG-8S Slugger'])

    def test_shared_projectiles_keep_resources_and_weapon_data_distinct(self):
        groups=self.report['sharedProjectileGroups']
        liberator=next(group for group in groups
            if {'AR-23 Liberator','AR-23A Liberator Carbine','StA-52 Assault Rifle'}
            <=set(group['catalogIdentities']))
        resolved=[item for item in liberator['resources'] if item['status'] in {'EXACT','STRONG'}]
        self.assertEqual(len(resolved),3)
        self.assertGreaterEqual(liberator['distinctWeaponDataRecords'],3)
        self.assertFalse(liberator['ambiguousAtWeaponLevel'])
        values={item['resourceHash']:item['weaponLevelFields']['fire_rate']
            for item in resolved}
        self.assertEqual(set(values.values()),{640,790,920})
        shotgun=next(group for group in groups if 'SG-8 Punisher'in group['catalogIdentities'])
        self.assertTrue(shotgun['ambiguousAtWeaponLevel'])

    def test_regression_anchors_remain_unique(self):
        anchors=self.report['regressionAnchors']
        self.assertEqual(anchors['JAR-5 Dominator']['resourceHash'],'0x80F1A156D9FA1E36')
        self.assertTrue(all(value['resolution']=='UNIQUE'and value['status']=='EXACT'
            for value in anchors.values()))


if __name__=='__main__':unittest.main()
