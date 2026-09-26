import copy
import json
import unittest

from support import ROOT, run


def lua_test(body):
    return run("""
local matcher=require('hd2runtime/primary_mapper/matcher')
local function weapon(name,primary,attacks)
 return {name=name,primary=primary,attacks=attacks or {primary}}
end
"""+body)


class MatcherTests(unittest.TestCase):
    def test_exact_unique_match(self):
        lua_test("""
local a={standard_damage=275,durable_damage=90,ap_direct=3,ap_slight=3,ap_large=3,ap_extreme=0,demolition=10,stagger=35,push_force=15}
local b={standard_damage=274,durable_damage=90,ap_direct=3,ap_slight=3,ap_large=3,ap_extreme=0,demolition=10,stagger=35,push_force=15}
local r=matcher.rank(a,{weapons={weapon('JAR-5 Dominator',a),weapon('Other',b)}})
assert(r.status=='EXACT' and r.rankedWikiMatches[1].name=='JAR-5 Dominator')
return 'ok'
""")

    def test_same_damage_distinguished_by_velocity(self):
        lua_test("""
local runtime={standard_damage=90,durable_damage=22,ap_direct=2,projectile_velocity=900,capacity=45}
local d={weapons={weapon('Slow',{standard_damage=90,durable_damage=22,ap_direct=2,projectile_velocity=700,capacity=45}),
 weapon('Fast',{standard_damage=90,durable_damage=22,ap_direct=2,projectile_velocity=900,capacity=45})}}
local r=matcher.rank(runtime,d);assert(r.rankedWikiMatches[1].name=='Fast' and r.status=='EXACT')
return 'ok'
""")

    def test_shotgun_distinguished_by_pellet_count(self):
        lua_test("""
local runtime={standard_damage=30,durable_damage=6,ap_direct=2,pellet_count=11,capacity=16}
local d={weapons={weapon('Eight',{standard_damage=30,durable_damage=6,ap_direct=2,pellet_count=8,capacity=16}),
 weapon('Eleven',{standard_damage=30,durable_damage=6,ap_direct=2,pellet_count=11,capacity=16})}}
local r=matcher.rank(runtime,d);assert(r.rankedWikiMatches[1].name=='Eleven' and r.status=='EXACT')
return 'ok'
""")

    def test_ambiguous_weapons(self):
        lua_test("""
local p={standard_damage=90,durable_damage=22,ap_direct=2,ap_slight=2,ap_large=2}
local r=matcher.rank(p,{weapons={weapon('A',p),weapon('B',p)}})
assert(r.status=='AMBIGUOUS' and r.scoreMargin==0 and r.rankedWikiMatches[1].name=='A')
return 'ok'
""")

    def test_missing_fields_reduce_evidence_without_mismatch(self):
        lua_test("""
local r=matcher.rank({standard_damage=90},{weapons={weapon('Sparse',{standard_damage=90}),
 weapon('Wiki Missing',{durable_damage=20})}})
local top=r.rankedWikiMatches[1]
assert(top.name=='Sparse' and top.compared==1 and #top.mismatched==0 and r.status=='AMBIGUOUS')
return 'ok'
""")

    def test_float_tolerance(self):
        lua_test("""
local r=matcher.rank({projectile_velocity=901.9,projectile_mass=4.59,drag=.309,gravity=1.009},
 {weapons={weapon('Rounded',{projectile_velocity=900,projectile_mass=4.5,drag=.3,gravity=1})}})
local top=r.rankedWikiMatches[1];assert(#top.mismatched==0 and top.compared==4)
return 'ok'
""")

    def test_multi_attack_and_underbarrel_do_not_replace_primary(self):
        lua_test("""
local primary={name='Rifle P',kind='Projectile',standard_damage=95,durable_damage=24,ap_direct=2,ap_slight=2,ap_large=2}
local underbarrel={name='Grenade P',kind='Projectile',standard_damage=250,durable_damage=250,ap_direct=3}
local other={name='Other P',kind='Projectile',standard_damage=250,durable_damage=250,ap_direct=3}
local d={weapons={weapon('One-Two',primary,{primary,underbarrel}),weapon('Other',other)}}
local r=matcher.rank({standard_damage=95,durable_damage=24,ap_direct=2,ap_slight=2,ap_large=2},d)
assert(r.rankedWikiMatches[1].name=='One-Two')
local r2=matcher.rank({standard_damage=250,durable_damage=250,ap_direct=3},d)
assert(r2.rankedWikiMatches[1].name=='Other')
return 'ok'
""")

    def test_no_plausible_match(self):
        lua_test("""
local r=matcher.rank({standard_damage=999,durable_damage=998,ap_direct=9},
 {weapons={weapon('Known',{standard_damage=90,durable_damage=22,ap_direct=2})}})
assert(r.status=='UNMATCHED' and r.rankedWikiMatches[1].score<0)
return 'ok'
""")

    def test_real_dataset_and_primary_stat_import(self):
        lua_test("""
local d=require('hd2runtime/primary_mapper/wiki_data');assert(d.weapon_count==55)
local jar,one
for _,w in ipairs(d.weapons)do if w.name=='JAR-5 Dominator'then jar=w elseif w.name=='AR/GL-21 One-Two'then one=w end end
assert(jar and jar.primary.standard_damage==275 and jar.primary.projectile_velocity==180)
assert(one and one.primary.standard_damage==95 and one.primary.fire_rate==650 and one.primary.capacity==40)
return 'ok'
""")


class RuntimeMapperTests(unittest.TestCase):
    def test_candidate_failure_does_not_abort_and_jar_anchor_is_generic(self):
        result=run("""
local job=hd2.enumerate_primary_weapons{}
for _=1,10000 do if job.step()then break end end
assert(job.status=='complete',job.error)
assert(job.result.writes==0 and job.result.protectionChanges==0 and job.result.fixtureFallback=='disabled')
assert(job.result.metrics.sharedDiscoveryPasses==1 and job.result.metrics.candidateFailures>0)
local jar
for _,candidate in ipairs(job.result.runtimeCandidates)do
 if candidate.resourceHash=='0x80F1A156D9FA1E36'then jar=candidate end
end
assert(jar and (jar.resolutionStatus=='RESOLVED' or jar.resolutionStatus=='PARTIAL'))
assert(jar.resolvedFields.projectile_type.value==177)
assert(jar.resolvedFields.standard_damage.value==275 and jar.resolvedFields.durable_damage.value==90)
assert(jar.resolvedFields.ap_direct.value==3 and jar.resolvedFields.ap_slight.value==3
 and jar.resolvedFields.ap_large.value==3 and jar.resolvedFields.ap_extreme.value==0)
assert(jar.resolvedFields.demolition.value==10 and jar.resolvedFields.stagger.value==35
 and jar.resolvedFields.push_force.value==15)
return tostring(job.result.metrics.candidateCount)
""").decode()
        self.assertEqual(int(result), 365)

    def test_output_deterministic_independent_of_candidate_order(self):
        run("""
local report=require('hd2runtime/primary_mapper/report')
local json=require('hd2runtime/primary_mapper/json')
local dataset={source='x',imported_at='t',source_sha256='a',summary_sha256='b',weapon_count=1,
 weapons={{name='Only',primary={standard_damage=10,durable_damage=2,ap_direct=1,ap_slight=1,ap_large=1}}}}
local function c(hash,damage)return {resourceHash=hash,ownership={},resolvedFields={},attacks={},diagnostics={},
 resolutionStatus='RESOLVED',matchFields={standard_damage=damage,durable_damage=2,ap_direct=1,ap_slight=1,ap_large=1}}end
local function raw(items)return {writes=0,protectionChanges=0,fixtureFallback='disabled',fingerprint={},mode='fixture',
 stableSnapshot=true,metrics={candidateCount=2,candidateFailures=0},runtimeCandidates=items,
 fieldsCurrentlyUsable={},fieldsNotRuntimeMapped={}}end
local a=report.compose(raw({c('0x02',10),c('0x01',10)}),dataset,{version='x',commit='c'})
local b=report.compose(raw({c('0x01',10),c('0x02',10)}),dataset,{version='x',commit='c'})
assert(json.encode(a)==json.encode(b))
return 'ok'
""")

    def test_diagnostic_package_has_no_runtime_or_native_capability(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        import build_primary_weapon_mapper as build_mapper
        sources=build_mapper.resources('test')
        self.assertIn(build_mapper.ENTRY,sources)
        self.assertFalse(any(name.startswith('hd2runtime/runtime/') or name.startswith('hd2runtime/core/')
                             for name in sources))
        body=b'\n'.join(sources.values())
        for token in (b'VirtualQuery',b'VirtualProtect',b'ReadProcessMemory',b'WriteProcessMemory',b'ffi.'):
            self.assertNotIn(token,body)


if __name__=='__main__':
    unittest.main()
