import json
import unittest

from support import ROOT,run


class WeaponMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'research/weapon-slot-capacity-F5FEE03DCFDB.json').read_text())

    def test_primary_secondary_and_unknown_slot_classification(self):
        run("""
local m=require('hd2runtime/core/weapon_metadata')
local s=require('hd2runtime/schemas/weapon_mapper')
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local primary,pa=m.weapon_slot(u32(0x82C32E74)..string.rep('\0',28),s)
local secondary,sa=m.weapon_slot(u32(0x89747DEC)..string.rep('\0',28),s)
local unknown,ua=m.weapon_slot(u32(0x12345678)..string.rep('\0',28),s)
assert(primary=='primary'and secondary=='secondary'and unknown==nil)
assert(pa.status=='RESOLVED'and sa.status=='RESOLVED'and ua.status=='UNCLASSIFIED')
return'ok'
""")

    def test_direct_capacity_chamber_and_customization_fail_closed(self):
        run("""
local m=require('hd2runtime/core/weapon_metadata')
local s=require('hd2runtime/schemas/weapon_mapper')
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function put(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local magazine=put(string.rep('\0',160),136,u32(15));magazine=put(magazine,156,string.char(1))
local direct=m.capacity({WeaponMagazineComponentData=magazine},s)
assert(direct.status=='RESOLVED'and direct.value==15 and direct.chambered)
assert(direct.transformation=='identity','chamber must not add one to catalog capacity')
local custom=string.rep('\0',4872);custom=put(custom,0,u32(5)..u32(0x11223344))
local blocked=m.capacity({WeaponMagazineComponentData=magazine,
 WeaponCustomizationComponentData=custom},s)
assert(blocked.status=='CUSTOMIZED_UNRESOLVED'and blocked.value==nil and blocked.baseValue==15)
local empty=put(string.rep('\0',4872),0,u32(5)..u32(0))
assert(m.capacity({WeaponMagazineComponentData=magazine,WeaponCustomizationComponentData=empty},s).value==15)
local ammo=m.ammo({WeaponMagazineComponentData=magazine},s)
assert(ammo.kind=='magazine'and ammo.capacity.value==15)
return'ok'
""")

    def test_detachable_magazine_reserve_fields_and_ammo_box_derivation(self):
        run("""
local m=require('hd2runtime/core/weapon_metadata')
local s=require('hd2runtime/schemas/weapon_mapper')
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function put(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local magazine=string.rep('\0',160)
for _,item in ipairs({{136,15},{140,4},{144,7},{148,6}})do magazine=put(magazine,item[1],u32(item[2]))end
local ammo=m.ammo({WeaponMagazineComponentData=magazine},s)
assert(ammo.capacity_value==15 and ammo.starting_magazines==4 and ammo.spare_magazines==6)
assert(ammo.magazines_from_supply==7 and ammo.magazines_from_ammo_box==3)
local custom=put(string.rep('\0',4872),0,u32(5)..u32(0x116E8A0F))
local blocked=m.ammo({WeaponMagazineComponentData=magazine,WeaponCustomizationComponentData=custom},s)
assert(blocked.capacity.status=='CUSTOMIZED_UNRESOLVED'and blocked.base.capacity==15)
assert(blocked.base.starting_magazines==4 and blocked.base.spare_magazines==6)
return'ok'
""")

    def test_rounds_feed_capacity_and_family_classification(self):
        run("""
local m=require('hd2runtime/core/weapon_metadata')
local s=require('hd2runtime/schemas/weapon_mapper')
local rounds=string.rep('\0',72)..string.char(0,0,0,65)..string.char(0,0,0,65)..string.rep('\0',56)
local value=m.capacity({WeaponRoundsComponentData=rounds},s)
assert(value.status=='RESOLVED'and value.value==16 and value.source:find('MagazineCapacity',1,true))
assert(value.transformation=='sum_feed_capacities'and value.feedValues[1]==8 and value.feedValues[2]==8)
local ammo=m.ammo({WeaponRoundsComponentData=rounds:sub(1,80)..string.char(60,0,0,0)..
 string.char(60,0,0,0)..string.char(32,0,0,0)..rounds:sub(93)},s)
assert(ammo.spare_rounds==60 and ammo.rounds_from_supply==60 and ammo.starting_rounds==32)
assert(ammo.rounds_from_ammo_box==30)
local f=m.implementation_families({ProjectileWeaponComponentData={},WeaponRoundsComponentData={}})
assert(#f==2 and f[1]=='conventional_projectile'and f[2]=='rounds_feed')
assert(m.implementation_families({BeamWeaponComponentData={}})[1]=='beam')
return'ok'
""")

    def test_research_evidence_and_read_only_invariants(self):
        report=self.report
        self.assertEqual(report['weaponSlot']['exactSeparation'],54)
        self.assertEqual((report['weaponSlot']['primaryExact'],report['weaponSlot']['secondaryExact']),(43,11))
        self.assertEqual(report['weaponSlot']['mismatches'],[])
        self.assertEqual(report['capacity']['counts']['RESOLVED_exact'],35)
        self.assertEqual(report['capacity']['counts']['CUSTOMIZED_UNRESOLVED_unresolved'],15)
        self.assertEqual(report['safety'],{'writes':0,'protectionChanges':0,
            'fixtureFallback':'disabled','gameLaunched':False})

    def test_matcher_uses_known_slot_and_capacity_but_preserves_unknown_slot(self):
        run("""
local matcher=require('hd2runtime/primary_mapper/matcher')
local attack={name='P',kind='Projectile',standard_damage=90,durable_damage=22,ap_direct=2,
 ap_slight=2,ap_large=2,projectile_velocity=900}
local dataset={weapons={
 {name='Primary 30',slot='primary',capacity=30,attacks={attack}},
 {name='Primary 45',slot='primary',capacity=45,attacks={attack}},
 {name='Secondary 45',slot='secondary',capacity=45,attacks={attack}}}}
local known=matcher.rank({attack_kind='Projectile',weapon_slot='primary',capacity=45,
 standard_damage=90,durable_damage=22,ap_direct=2,ap_slight=2,ap_large=2,projectile_velocity=900},dataset)
assert(known.rankedWikiMatches[1].name=='Primary 45')
for _,v in ipairs(known.rankedWikiMatches)do
 if v.name=='Secondary 45'then assert(not v.structurallyCompatible)end end
local unknown=matcher.rank({attack_kind='Projectile',capacity=45,standard_damage=90,
 durable_damage=22,ap_direct=2,ap_slight=2,ap_large=2,projectile_velocity=900},dataset)
assert(#unknown.credibleWikiIdentities==2,'unknown slot must not force classification')
return'ok'
""")

    def test_duplicate_and_unresolved_family_results_are_deterministic(self):
        report=self.report
        after=report['matcherComparison']['after']
        self.assertEqual(after['totalUniqueResolved'],55)
        self.assertEqual([x['name'] for x in report['duplicateIdentityGroups']],
            ['GP-31 Grenade Pistol','SMG-37 Defender'])
        families=report['unresolvedImplementationFamilies']
        self.assertEqual(families['arc'],['ARC-12 Blitzer'])
        self.assertEqual(families['spray/flame'],['FLAM-66 Torcher','P-72 Crisper'])
        self.assertIn('LAS-7 Dagger',families['beam'])


if __name__=='__main__':unittest.main()
