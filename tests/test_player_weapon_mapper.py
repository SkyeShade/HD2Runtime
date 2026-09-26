import sys
import unittest

from support import ROOT, run

sys.path.insert(0,str(ROOT/'sdk'))
from tools.wiki_player import compact


def lua_match(body):
    return run("""
local matcher=require('hd2runtime/primary_mapper/matcher')
local function weapon(name,slot,fire,attacks)
 return {name=name,slot=slot,fire_rate=fire,attacks=attacks}
end
"""+body)


class PlayerCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=compact(ROOT/'data/wiki_player_weapons.json')

    def test_combined_catalog_preserves_slots_kinds_and_branches(self):
        data=self.data
        self.assertEqual(data['weapon_count'],80)
        self.assertEqual(data['slot_counts'],{'primary':55,'secondary':25})
        kinds={attack['kind'] for weapon in data['weapons'] for attack in weapon['attacks']}
        self.assertTrue({'Projectile','Explosion','Status','Melee','Beam','Arc','Spray'}<=kinds)
        purifier=next(w for w in data['weapons'] if w['name']=='PLAS-101 Purifier')
        self.assertEqual([a['name'] for a in purifier['attacks']],
            ['P','P IE','PLAS-101 P','PLAS-101 P IE'])
        self.assertEqual(purifier['attacks'][0]['explosion_branches'],['P_IE'])
        self.assertEqual(purifier['attacks'][2]['projectile_velocity'],350)
        melee=next(w for w in data['weapons'] if w['name']=='CQC-2 Saber')
        self.assertEqual(melee['attacks'][0]['kind'],'Melee')
        self.assertFalse(melee['attacks'][0]['projectile_branch'])

    def test_primary_only_catalog_compatibility(self):
        data=compact(ROOT/'data/wiki_primary_weapons.json')
        self.assertEqual(data['weapon_count'],55)
        self.assertEqual(data['slot_counts'],{'primary':55,'secondary':0})
        jar=next(w for w in data['weapons'] if w['name']=='JAR-5 Dominator')
        self.assertEqual(jar['primary']['standard_damage'],275)


class BranchMatcherTests(unittest.TestCase):
    def test_secondary_projectile_weapon(self):
        lua_match("""
local p={name='Pistol P',kind='Projectile',standard_damage=100,durable_damage=32,
 ap_direct=2,projectile_velocity=320,projectile_mass=7,drag=1.2,gravity=1}
local r=matcher.rank({attack_kind='Projectile',fire_rate=900,standard_damage=100,
 durable_damage=32,ap_direct=2,projectile_velocity=320,projectile_mass=7,drag=1.2,gravity=1},
 {weapons={weapon('Pistol','secondary',900,{p})}})
local top=r.rankedWikiMatches[1]
assert(r.status=='EXACT'and top.slot=='secondary'and top.matchedAttackBranch=='Pistol P')
return'ok'
""")

    def test_melee_secondary_uses_kind_compatibility(self):
        lua_match("""
local melee={name='Blade',kind='Melee',standard_damage=250,durable_damage=125,ap_direct=3,
 demolition=10,stagger=25,push_force=30}
local projectile={name='Bullet',kind='Projectile',standard_damage=250,durable_damage=125,ap_direct=3}
local r=matcher.rank({attack_kind='Melee',standard_damage=250,durable_damage=125,ap_direct=3,
 demolition=10,stagger=25,push_force=30},{weapons={weapon('Blade Secondary','secondary',nil,{melee}),
 weapon('Projectile Impostor','secondary',nil,{projectile})}})
assert(r.rankedWikiMatches[1].name=='Blade Secondary')
assert(r.rankedWikiMatches[2].structurallyCompatible==false)
return'ok'
""")

    def test_multi_projectile_charge_branch(self):
        lua_match("""
local p1={name='P1',kind='Projectile',standard_damage=150,durable_damage=75,
 projectile_velocity=550,projectile_mass=25,drag=1.5,gravity=1}
local p2={name='P2',kind='Projectile',standard_damage=150,durable_damage=75,
 projectile_velocity=350,projectile_mass=25,drag=1.5,gravity=1}
local r=matcher.rank({attack_kind='Projectile',fire_rate=1000,standard_damage=150,durable_damage=75,
 projectile_velocity=350,projectile_mass=25,drag=1.5,gravity=1},
 {weapons={weapon('Charged','secondary',1000,{p1,p2})}})
local top=r.rankedWikiMatches[1]
assert(top.matchedDamageBranch=='P1'and top.matchedProjectileBranch=='P2')
assert(top.branchMode=='composite'and #top.mismatched==0)
return'ok'
""")

    def test_explosion_sub_attack(self):
        lua_match("""
local p={name='P',kind='Projectile',standard_damage=100,durable_damage=50}
local e={name='P IE',kind='Explosion',standard_damage=400,durable_damage=400,
 ap_direct=3,demolition=30,stagger=25,push_force=30}
local r=matcher.rank({attack_kind='Explosion',standard_damage=400,durable_damage=400,
 ap_direct=3,demolition=30,stagger=25,push_force=30},
 {weapons={weapon('Exploder','secondary',900,{p,e})}})
local top=r.rankedWikiMatches[1]
assert(top.matchedAttackBranch=='P IE'and top.matchedDamageBranch=='P IE')
return'ok'
""")

    def test_purifier_uses_350_projectile_and_200_damage_branches(self):
        lua_match("""
local p={name='P',kind='Projectile',standard_damage=200,durable_damage=100,ap_direct=3,
 projectile_velocity=550,projectile_mass=25,drag=1.5,gravity=1,demolition=10,stagger=20,push_force=10}
local p2={name='PLAS-101 P',kind='Projectile',standard_damage=100,durable_damage=50,ap_direct=3,
 projectile_velocity=350,projectile_mass=25,drag=1.5,gravity=1,demolition=10,stagger=20,push_force=10}
local r=matcher.rank({attack_kind='Projectile',fire_rate=1000,standard_damage=200,durable_damage=100,
 ap_direct=3,projectile_velocity=350,projectile_mass=25,drag=1.5,gravity=1,
 demolition=10,stagger=20,push_force=10},{weapons={weapon('PLAS-101 Purifier','primary',1000,{p,p2})}})
local top=r.rankedWikiMatches[1]
assert(top.matchedDamageBranch=='P'and top.matchedProjectileBranch=='PLAS-101 P')
assert(top.branchMode=='composite'and #top.mismatched==0)
return'ok'
""")

    def test_loyalist_selects_its_distinct_branch(self):
        lua_match("""
local p1={name='P1',kind='Projectile',standard_damage=150,durable_damage=75,
 projectile_velocity=550,projectile_mass=25,drag=1.5,gravity=1}
local own={name='PLAS-15 P',kind='Projectile',standard_damage=100,durable_damage=50,
 projectile_velocity=550,projectile_mass=10,drag=1,gravity=.5}
local r=matcher.rank({attack_kind='Projectile',fire_rate=1000,standard_damage=100,durable_damage=50,
 projectile_velocity=550,projectile_mass=10,drag=1,gravity=.5},
 {weapons={weapon('PLAS-15 Loyalist','secondary',1000,{p1,own})}})
local top=r.rankedWikiMatches[1]
assert(top.matchedDamageBranch=='PLAS-15 P'and top.matchedProjectileBranch=='PLAS-15 P')
assert(top.branchMode=='single')
return'ok'
""")

    def test_ambiguous_identity_is_preserved(self):
        lua_match("""
local a={name='P',kind='Projectile',standard_damage=90,durable_damage=22,ap_direct=2,
 projectile_velocity=900}
local r=matcher.rank({attack_kind='Projectile',standard_damage=90,durable_damage=22,
 ap_direct=2,projectile_velocity=900},{weapons={weapon('A','primary',nil,{a}),
 weapon('B','secondary',nil,{a})}})
assert(r.status=='AMBIGUOUS'and #r.credibleWikiIdentities==2 and r.scoreMargin==0)
return'ok'
""")

    def test_missing_optional_fields_do_not_mismatch(self):
        lua_match("""
local a={name='P',kind='Projectile',standard_damage=90}
local r=matcher.rank({attack_kind='Projectile',standard_damage=90},{weapons={weapon('Sparse','primary',nil,{a})}})
local top=r.rankedWikiMatches[1]
assert(top.compared==1 and #top.mismatched==0 and r.status=='AMBIGUOUS')
return'ok'
""")

    def test_unmatched_candidate(self):
        lua_match("""
local a={name='P',kind='Projectile',standard_damage=90,durable_damage=22,ap_direct=2}
local r=matcher.rank({attack_kind='Projectile',standard_damage=999,durable_damage=998,ap_direct=9},
 {weapons={weapon('Known','primary',nil,{a})}})
assert(r.status=='UNMATCHED')
return'ok'
""")

    def test_report_keeps_duplicate_runtime_resources(self):
        run("""
local report=require('hd2runtime/primary_mapper/report')
local p={name='P',kind='Projectile',standard_damage=90,durable_damage=22,
 ap_direct=2,ap_slight=2,ap_large=2,projectile_velocity=900}
local dataset={weapon_count=1,slot_counts={primary=1,secondary=0},weapons={
 {name='Only',slot='primary',attacks={p}}}}
local function candidate(hash)return {resourceHash=hash,entityRow=1,ownership={},resolvedFields={},
 attacks={},diagnostics={},resolutionStatus='RESOLVED',matchFields={attack_kind='Projectile',
 standard_damage=90,durable_damage=22,ap_direct=2,ap_slight=2,ap_large=2,projectile_velocity=900}}
end
local raw={writes=0,protectionChanges=0,fixtureFallback='disabled',fingerprint={},mode='snapshot',
 stableSnapshot=true,metrics={candidateCount=2,candidateFailures=0},
 runtimeCandidates={candidate('0x02'),candidate('0x01')},fieldsCurrentlyUsable={},fieldsNotRuntimeMapped={}}
local full,mapping,summary=report.compose(raw,dataset,{version='x',commit='c'})
assert(mapping.Only.resolution=='DUPLICATE'and mapping.Only.runtimeCandidateMatches==2)
assert(mapping.Only.bestCandidate.resourceHash=='0x01')
assert(#summary.duplicateIdentityGroups==1 and #summary.duplicateIdentityGroups[1].resources==2)
return'ok'
""")


if __name__=='__main__':unittest.main()
