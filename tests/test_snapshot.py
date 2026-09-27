from pathlib import Path
import json
import sys
import tempfile
import unittest

from support import ROOT, run, lua
from snapshot_support import snapshot_bytes, materialized_mapper_regions, RESERVE


class SnapshotReaderTests(unittest.TestCase):
    def test_header_exact_reads_boundaries_allocation_modules_and_pointer(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            path=Path(folder)/'basic.hd2snap'
            pointer=(0x3000).to_bytes(8,'little')
            regions=[
                {'base':0x2000,'allocation_base':0x1000,'size':16,'data':pointer+b'ABCDEFGH'},
                {'base':0x3000,'allocation_base':0x3000,'size':8,'data':b'TARGET!!'},
                {'base':0x4000,'allocation_base':0x4000,'size':16,'status':4,'error_code':299,'data':b'PART'},
            ]
            snapshot_bytes(path,regions)
            result=run(f"""
local p=require('hd2runtime/schemas/current')
local s=require('hd2runtime/runtime/snapshot_memory_reader').open({lua(str(path))},
 {{expected_exe_sha=p.exe_sha,expected_dll_sha=p.dll_sha}})
assert(s.mode=='snapshot' and s.metadata.format_version==1 and s.metadata.region_count==3)
assert(s.read(0x2008,8)=='ABCDEFGH')
local raw=assert(s.read(0x2000,8));local at=require('hd2runtime/core/bytes').pointer(raw,0)
assert(at==0x3000 and s.read(at,8)=='TARGET!!')
local r=s.query(0x2004);assert(r.allocation_base==0x1000 and r.base==0x2000)
assert(s.module(nil)==0x10000000 and s.module('game.dll')==0x10001000)
assert(s.module_metadata('game.dll').sha256==p.dll_sha)
local value,why=s.read(0x200F,2);assert(not value and why:find('boundary',1,true))
value,why=s.read(0x4000,1);assert(not value and why:find('not fully captured',1,true))
assert(s.query(0x4000).error_code==299 and s.query(0x4000).capture_status==4)
s.close();return 'ok'
""")
            self.assertEqual(result,b'ok')

    def test_fingerprint_mismatch_requires_explicit_historical_mode(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            path=snapshot_bytes(Path(folder)/'old.hd2snap',[
                {'base':0x2000,'size':4,'data':b'abcd'}],exe_sha='A'*64,dll_sha='B'*64)
            run(f"""
local open=require('hd2runtime/runtime/snapshot_memory_reader').open
local ok,why=pcall(open,{lua(str(path))},{{expected_exe_sha='C'..string.rep('A',63),expected_dll_sha=string.rep('B',64)}})
assert(not ok and tostring(why):find('fingerprint differs',1,true))
local s=open({lua(str(path))},{{expected_exe_sha=string.rep('C',64),expected_dll_sha=string.rep('D',64),historical_analysis=true}})
assert(s.historical_analysis);s.close();return 'ok'
""")

    def test_malformed_truncated_duplicate_and_overlapping_regions_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            folder=Path(folder)
            good=snapshot_bytes(folder/'good.hd2snap',[{'base':0x2000,'size':8,'data':b'12345678'}])
            truncated=folder/'truncated.hd2snap';truncated.write_bytes(good.read_bytes()[:100])
            bad_version=folder/'version.hd2snap';raw=bytearray(good.read_bytes());raw[8:12]=(99).to_bytes(4,'little');bad_version.write_bytes(raw)
            overlap=snapshot_bytes(folder/'overlap.hd2snap',[],region_order=[
                {'base':0x2000,'size':16,'data':b'A'*16},{'base':0x2008,'size':16,'data':b'B'*16}])
            for path,needle in ((truncated,'snapshot'),(bad_version,'version'),(overlap,'overlapping')):
                run(f"""local ok,why=pcall(require('hd2runtime/runtime/snapshot_memory_reader').open,{lua(str(path))},{{historical_analysis=true}});assert(not ok and tostring(why):find({lua(needle)},1,true),tostring(why));return'ok'""")

    def test_region_index_is_deterministic_and_unsorted_input_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            folder=Path(folder);regions=[{'base':0x2000,'size':4,'data':b'abcd'},
                {'base':0x3000,'size':4,'data':b'efgh'}]
            a=snapshot_bytes(folder/'a.hd2snap',regions);b=snapshot_bytes(folder/'b.hd2snap',regions)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            bad=snapshot_bytes(folder/'bad.hd2snap',[],region_order=list(reversed(regions)))
            run(f"""local ok,why=pcall(require('hd2runtime/runtime/snapshot_memory_reader').open,{lua(str(bad))},{{historical_analysis=true}});assert(not ok and tostring(why):find('overlapping',1,true));return'ok'""")


class SnapshotCaptureTests(unittest.TestCase):
    def test_capture_is_incremental_read_only_and_round_trips_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            path=Path(folder)/'captured.hd2snap'
            run(f"""
local p=require('hd2runtime/schemas/current')
local rows={{{{base=0x10000,size=0x10000,allocation_base=0x10000,state=0x1000,type=0x1000000,protect=2}},
 {{base=0x20000,size=0x10000,allocation_base=0x20000,state=0x1000,type=0x1000000,protect=2}},
 {{base=0x30000,size=0x10000,allocation_base=0x30000,state=0x1000,type=0x20000,protect=4}},
 {{base=0x40000,size=0x10000,allocation_base=0,state=0x1000,type=0x20000,protect=1}}}}
local rt={{mode='live',tick_bytes=0,total_bytes=0}}
function rt.module(name)return name and 0x20000 or 0x10000 end
function rt.address(value)return value end
function rt.module_hash(value)return value==0x10000 and p.exe_sha or p.dll_sha end
function rt.system_info()return 4096,0x50000 end
function rt.query(at)for _,r in ipairs(rows)do if at>=r.base and at<r.base+r.size then return r end end end
function rt.read(at,n)rt.tick_bytes=rt.tick_bytes+n;rt.total_bytes=rt.total_bytes+n;return string.rep(string.char(math.floor(at/0x10000)),n)end
function rt.monotonic_time()return rt.total_bytes/1048576 end
function rt.ensure_directory(path)return path end
local logs={{}}
local w=require('hd2runtime/api/snapshot_capture').start(rt,function(x)logs[#logs+1]=x end,
 {{output_path={lua(str(path))},capture_delay_seconds=0,bytes_per_tick=65536,chunk_bytes=65536}})
local ticks=0
while w.status=='running'do rt.tick_bytes=0;w.tick();ticks=ticks+1;assert(rt.tick_bytes<=65536)end
assert(w.status=='complete',w.error);assert(ticks>=3 and rt.total_bytes==3*65536)
assert(w.result.writes==0 and w.result.protection_changes==0)
local s=require('hd2runtime/runtime/snapshot_memory_reader').open({lua(str(path))},
 {{expected_exe_sha=p.exe_sha,expected_dll_sha=p.dll_sha}})
assert(s.metadata.executable_base==0x10000 and s.metadata.game_dll_base==0x20000)
assert(s.metadata.diagnostics.mem_image_bytes==0x20000 and s.metadata.diagnostics.mem_private_bytes==0x10000)
assert(s.metadata.diagnostics.skipped_noaccess_bytes==0x10000)
assert(s.read(0x30000,4)==string.rep(string.char(3),4))
assert(logs[1]:find('scheduled delay_seconds=0.000',1,true))
assert(table.concat(logs,'\\n'):find('capture_start=',1,true))
assert(table.concat(logs,'\\n'):find('MiB_per_second=',1,true))
s.close();return'ok'
""")

    def test_default_delay_defers_enumeration_and_file_creation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            path=Path(folder)/'delayed.hd2snap'
            run(f"""
local p=require('hd2runtime/schemas/current')
local rows={{{{base=0x10000,size=0x10000,allocation_base=0x10000,state=0x1000,type=0x1000000,protect=2}},
 {{base=0x20000,size=0x10000,allocation_base=0x20000,state=0x1000,type=0x1000000,protect=2}}}}
local rt={{mode='live',queries=0,module_calls=0}}
function rt.module(name)rt.module_calls=rt.module_calls+1;return name and 0x20000 or 0x10000 end
function rt.address(value)return value end
function rt.module_hash(value)return value==0x10000 and p.exe_sha or p.dll_sha end
function rt.system_info()return 4096,0x30000 end
function rt.query(at)rt.queries=rt.queries+1;for _,r in ipairs(rows)do if at>=r.base and at<r.base+r.size then return r end end end
function rt.read(at,n)return string.rep('x',n)end
function rt.monotonic_time()return 0 end
function rt.ensure_directory(value)return value end
local logs={{}}
local w=require('hd2runtime/api/snapshot_capture').start(rt,function(x)logs[#logs+1]=x end,
 {{output_path={lua(str(path))},bytes_per_tick=65536,chunk_bytes=65536}})
assert(w.status=='waiting'and w.scheduled_delay_seconds==60,'initial wait')
assert(rt.queries==0 and rt.module_calls==0 and io.open({lua(str(path))},'rb')==nil,'early work')
w.tick(30);w.tick(29.999)
assert(w.status=='waiting'and rt.queries==0 and rt.module_calls==0,'work before deadline')
assert(io.open({lua(str(path)+'.partial')},'rb')==nil,'partial before deadline')
w.tick(0.002)
assert(w.status=='running'and rt.queries>0 and rt.module_calls>0,'capture did not start')
local partial=io.open({lua(str(path)+'.partial')},'rb');assert(partial,'partial absent after start');partial:close()
local joined=table.concat(logs,'\\n')
assert(joined:find('scheduled delay_seconds=60.000',1,true))
assert(joined:find('capture_start=',1,true))
assert(joined:find('actual_delay_seconds=60.001',1,true),'actual delay log absent')
w.cancel();return'ok'
""")


class SnapshotScannerParityTests(unittest.TestCase):
    def test_live_and_snapshot_sources_produce_identical_scanner_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            folder=Path(folder);regions,snapshot=materialized_mapper_regions(folder)
            source_rows=[]
            for i,r in enumerate(regions):
                source_rows.append({'base':r['base'],'allocation_base':r['allocation_base'],'size':r['size'],
                    'state':r.get('state',0x1000),'type':r.get('type',0x20000),'protect':r.get('protect',2),
                    'path':str(folder/f'region{i}.bin')})
            run(f"""
local p=require('hd2runtime/schemas/current')
local rows={lua(source_rows)}
local live={{mode='live'}};local handles={{}}
function live.module(name)return name and 0x10001000 or 0x10000000 end
function live.address(v)return v end
function live.module_hash(v)return v==0x10000000 and p.exe_sha or p.dll_sha end
function live.system_info()return 4096,0x10002000 end
function live.query(at)
 for _,r in ipairs(rows)do if at>=r.base and at<r.base+r.size then return r end end
 local next_at=0x10002000;for _,r in ipairs(rows)do if r.base>at then next_at=math.min(next_at,r.base)end end
 return{{base=at,size=next_at-at,allocation_base=0,state=0x10000,type=0,protect=0}}
end
function live.read(at,n)
 for i,r in ipairs(rows)do if at>=r.base and at+n<=r.base+r.size then
  local f=handles[i]or assert(io.open(r.path,'rb'));handles[i]=f;assert(f:seek('set',at-r.base));return f:read(n)
 end end;return nil,'outside'
end
local snapshot=require('hd2runtime/runtime/snapshot_memory_reader').open({lua(str(snapshot))},
 {{expected_exe_sha=p.exe_sha,expected_dll_sha=p.dll_sha}})
local start=require('hd2runtime/api/weapon_mapper').start
local function finish(source)local j=start(source,function()end,{{}});for _=1,20000 do if j.step()then break end end;assert(j.status=='complete',j.error);return j.result end
local a,b=finish(live),finish(snapshot)
assert(a.metrics.candidateCount==b.metrics.candidateCount and a.metrics.candidateCount==365)
local function indexed(result)local out={{}};for _,c in ipairs(result.runtimeCandidates)do out[c.resourceHash]=c end;return out end
local ai,bi=indexed(a),indexed(b)
for hash,x in pairs(ai)do
 local y=assert(bi[hash]);assert(x.entityRow==y.entityRow and x.resolutionStatus==y.resolutionStatus)
 for name,field in pairs(x.resolvedFields)do assert(y.resolvedFields[name]and y.resolvedFields[name].value==field.value,name)end
 for name in pairs(y.resolvedFields)do assert(x.resolvedFields[name],name)end
 for i,attack in ipairs(x.attacks)do
  local other=y.attacks[i];assert(other and other.kind==attack.kind and other.role==attack.role and other.projectileType==attack.projectileType)
  if attack.damageInfo then assert(other.damageInfo and other.damageInfo.row==attack.damageInfo.row and other.damageInfo.recordType==attack.damageInfo.recordType)else assert(other.damageInfo==nil)end
 end
end
for _,f in pairs(handles)do f:close()end;snapshot.close();return'ok'
""")

    def test_sdk_offline_command_runs_production_scanner_modules(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            folder=Path(folder);_,snapshot=materialized_mapper_regions(folder)
            sys.path.insert(0,str(ROOT/'sdk'))
            from tools.snapshot_scan import scan
            output,mapping=scan(snapshot,ROOT/'data/wiki_primary_weapons.json',folder/'map.json')
            report=json.loads(output.read_text());identities=json.loads(mapping.read_text())
            self.assertEqual(report['scanMetrics']['candidateCount'],365)
            self.assertEqual(report['mode'],'snapshot')
            self.assertEqual(report['hd2RuntimeVersion'],'0.14.0')
            self.assertEqual(identities['JAR-5 Dominator']['status'],'EXACT')

    def test_combined_player_catalog_command_is_snapshot_only_and_read_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            folder=Path(folder);_,snapshot=materialized_mapper_regions(folder)
            sys.path.insert(0,str(ROOT/'sdk'))
            from tools.snapshot_scan import scan_player_weapons
            output,mapping,summary=scan_player_weapons(snapshot,ROOT/'data/wiki_player_weapons.json',
                folder/'PlayerWeaponRuntimeMap.json',summary_output=folder/'player_weapon_identity_summary.json')
            report=json.loads(output.read_text());identities=json.loads(mapping.read_text())
            identity_summary=json.loads(summary.read_text())
            self.assertEqual(report['wikiDataset']['weaponCount'],80)
            self.assertEqual(report['wikiDataset']['slotCounts'],{'primary':55,'secondary':25})
            self.assertEqual((report['writes'],report['protectionChanges'],report['fixtureFallback']),
                (0,0,'disabled'))
            self.assertEqual(len(report['catalogIdentities']),80)
            self.assertEqual(identity_summary['catalogWeapons'],80)
            self.assertEqual(identities['JAR-5 Dominator']['bestCandidate']['resourceHash'],
                '0x80F1A156D9FA1E36')

    def test_capture_package_is_external_and_declarative(self):
        body=(ROOT/'snapshot_capture/addon.lua').read_bytes()
        self.assertIn(b'hd2.capture_snapshot',body)
        for token in (b'VirtualProtect',b'WriteProcessMemory',b'ReadProcessMemory',b'ffi.',b'update='):
            self.assertNotIn(token,body)
        sys.path.insert(0,str(ROOT/'scripts'))
        import build_snapshot_capture
        sources=build_snapshot_capture.resources()
        self.assertEqual(set(sources),{build_snapshot_capture.ENTRY})


if __name__=='__main__':unittest.main()
