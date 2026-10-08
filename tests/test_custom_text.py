"""Runtime-owned custom stratagem text (docs/custom-text.md; research/stratagem-text-F5FEE03DCFDB.json): the game's text
table format, the Runtime's own table and its registration into the game's text registry (runtime/text_resources.lua),
and the development presentation path (runtime/stratagem_presentation.lua apply_text). Offline: Python for the format
and the research, the offline event world for the Runtime side. Nothing here touches a game process."""
import json
import sys
import unittest

from support import ROOT, run
from test_stratagem_presentation import WORLD, PUBLIC

sys.path.insert(0, str(ROOT / 'scripts'))
import hd2_text  # noqa: E402

RESEARCH = json.loads((ROOT / 'research/stratagem-text-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
MOD = 'mods/test/text_mod'
# Two keys of MOD whose ids share their upper 32 bits (found offline): the Runtime must refuse the second.
COLLIDING = ('t1035', 't186533')


class FormatTests(unittest.TestCase):
    def test_tables_round_trip_and_the_lookup_takes_the_first_table(self):
        us, fr = hd2_text.language_hash('us'), hd2_text.language_hash('fr')
        a = hd2_text.build({us: {1: 'one', 2: 'two'}, fr: {1: 'un'}})
        b = hd2_text.build({us: {2: 'deux?', 3: 'three'}})
        self.assertEqual(hd2_text.parse(a), {us: {1: 'one', 2: 'two'}, fr: {1: 'un'}})
        self.assertEqual(hd2_text.build(hd2_text.parse(a)), a)
        self.assertEqual(hd2_text.lookup([a, b], 2, us), 'two')        # the first table holding it wins
        self.assertEqual(hd2_text.lookup([a, b], 3, us), 'three')
        self.assertEqual(hd2_text.lookup([a, b], 2, fr), '')           # no table has (fr, 2): empty
        self.assertEqual(hd2_text.lookup([a, b], 9, us), '')
        self.assertEqual(a.count(b'one\0'), 1)

    def test_the_research_proves_the_format_registry_and_registrar(self):
        fmt = RESEARCH['format']
        self.assertEqual((fmt['vanillaTables'], fmt['rebuiltByteForByte']), (264, 264))
        self.assertEqual(fmt['languagesPerTable'], [[1, 264]])
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual([item['code'] for item in RESEARCH['languages']], list(hd2_text.LANGUAGES))
        self.assertTrue(all(item['sample120mmName'] for item in RESEARCH['languages']))
        registry = RESEARCH['registry']
        self.assertEqual(registry['gameSlotUseFunctions']['add'], ['0x12FED80', '0x12FEDC0'])
        self.assertEqual(registry['gameSlotUseFunctions']['clear'], ['0x12FEDC0'])
        self.assertEqual(registry['gameSlotUseFunctions']['set language'], ['0x12FF050'])
        for consumer in ('0x1837087', '0x1838D72', '0x1300905', '0x1300795'):
            self.assertIn(consumer, registry['gameSlotUses']['lookup(id)'])
        for snapshot in RESEARCH['snapshots']:
            self.assertEqual((snapshot['count'], snapshot['capacity'], snapshot['currentLanguage']), (17, 18, 'us'))
            self.assertEqual(snapshot['tables'][1]['resource'], 'localization/strings_glossary_us')
        texts = RESEARCH['proofText']['texts']
        self.assertFalse(any(item['vanillaCollision'] for item in texts.values()))
        self.assertTrue(all(item['id'] != item['otherModId'] for item in texts.values()))
        self.assertEqual(texts['orbital_gas_barrage_description']['text'], 'Calls down a barrage of gas shells.')

    def test_the_domain_is_generated_from_the_research(self):
        import generate_text_resources
        self.assertEqual(generate_text_resources.generate(check=True), [])

    def test_the_colliding_pair_really_collides(self):
        ids = {hd2_text.text_id(hd2_text.custom_key(MOD, key)) for key in COLLIDING}
        self.assertEqual(len(ids), 1)


# The Runtime side: the stratagem world (120mm row), the public session, and the text module.
TEXT = r"""
local texts=require('hd2runtime/runtime/text_resources')
local TXT=require('hd2runtime/domains/text_resources')
local scheduler=require('hd2runtime/runtime/scheduler')
texts.reset_for_tests()
local MOD='mods/test/text_mod'
local function text(id,value,mod)return texts.handle(id,value,mod or MOD)end
local function hex(s)return(s:gsub('.',function(c)return string.format('%02x',c:byte())end))end
local NAME,CASED,DESC=0x4FAAD695,0x628B5A83,0x35FEBFE6
local function count(pattern)local n=0;for _,line in ipairs(logged)do if line:find(pattern,1,true)then n=n+1 end end;return n end
"""


def lua(body):
    return run(WORLD + PUBLIC + TEXT + body)


class TableTests(unittest.TestCase):
    def test_the_lua_table_is_the_python_table(self):
        out = lua(r'''
local a=text('gas_name','ORBITAL GAS BARRAGE')
local d=text('gas_desc',{default='Calls down a barrage of gas shells.',fr='Une salve de gaz.',jp='ガス弾幕'})
return hex(texts.table_bytes())
''').decode()
        key = lambda t: hd2_text.text_id(hd2_text.custom_key(MOD, t))
        entries = {}
        for code in hd2_text.LANGUAGES:
            desc = {'fr': 'Une salve de gaz.', 'jp': 'ガス弾幕'}.get(code, 'Calls down a barrage of gas shells.')
            entries[hd2_text.language_hash(code)] = {key('gas_name'): 'ORBITAL GAS BARRAGE', key('gas_desc'): desc}
        self.assertEqual(bytes.fromhex(out), hd2_text.build(entries))

    def test_handles_values_and_duplicates(self):
        self.assertEqual(lua(r'''
local a=text('gas_name','ORBITAL GAS BARRAGE')
assert(texts.issued(a)and tostring(a)=="text 'gas_name' of "..MOD)
local d=a:describe()
assert(d.kind=='text'and d.id=='gas_name'and d.mod==MOD)
for key in pairs(a)do assert(key=='resource'or key=='text'or key=='mod',key)end      -- no id, no key
-- The same id with the same text is the same handle; with other text it is refused.
assert(text('gas_name','ORBITAL GAS BARRAGE')==a)
local ok,why=pcall(text,'gas_name','OTHER')
assert(not ok and tostring(why):find('already defined with other text',1,true),tostring(why))
-- Another mod's id is another text.
assert(text('gas_name','ORBITAL GAS BARRAGE','mods/other/mod')~=a)
-- Languages: the game's codes and default; anything else is refused.
local t=text('table',{default='Default',fr='Français',ru='Русский'})
assert(texts.text(t,'fr')=='Français'and texts.text(t,'ru')=='Русский'and texts.text(t,'de')=='Default')
assert(texts.text(t,'us')=='Default')
for _,bad in ipairs({{fr='x'},{default='x',en='x'},{default=''},{default=string.rep('x',513)},
        {default='a\0b'},{default='tab\there'},{default='\255'},{default='\237\160\128'},5,setmetatable({},{})})do
    assert(not pcall(text,'bad',bad))
end
assert(pcall(text,'newline','line one\nline two'))
for _,bad in ipairs({'','Name','a-b','a/b',string.rep('x',65)})do assert(not pcall(text,bad,'x'),bad)end
assert(not pcall(texts.handle,'x','x','unknown'))
-- Two keys of one mod with the same 32-bit id: the second is refused.
text(''' + "'" + COLLIDING[0] + "'" + r''','first')
ok,why=pcall(text,''' + "'" + COLLIDING[1] + "'" + r''','second')
assert(not ok and tostring(why):find('has the same text id as',1,true),tostring(why))
return 'ok'
'''), b'ok')


class RegistryTests(unittest.TestCase):
    """The Runtime table in the game's text registry: appended into spare capacity (slot, then count), exact, and
    refused with nothing written when anything is off."""

    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_appended_after_the_games_tables_and_every_id_exact(self):
        self.check(r'''
local reg=W.text_registry({tables={{us={[NAME]='ORBITAL 120MM HE BARRAGE'}},{us={[DESC]='A barrage.'},fr={[DESC]='Un.'}}},
    capacity=4,stale=W.u64(0x123456789A)})
local a=text('gas_name','ORBITAL GAS BARRAGE')
local d=text('gas_desc',{default='Calls down a barrage of gas shells.',fr='Une salve de gaz.'})
local ok,info,why=texts.ensure(W.runtime)
assert(ok,tostring(info)..': '..tostring(why))
assert(info.action=='appended'and info.index==3 and info.count==3 and info.capacity==4 and info.language=='us')
-- Two writes, the slot first, then the count.
assert(#W.runtime.writes==2 and W.runtime.writes[1].address==reg.array+16 and W.runtime.writes[2].address==reg.list)
assert(reg.count()==3 and reg.slot(2)==W.runtime.permanent[1].address)
assert(reg.slot(0)==reg.tables[1]and reg.slot(1)==reg.tables[2]and reg.slot(3)==0)
assert(texts.resolves(W.runtime,a)and texts.resolves(W.runtime,d))
-- Registered already: nothing written.
ok,info=texts.ensure(W.runtime)
assert(ok and info.action=='present'and#W.runtime.writes==2)
-- In French: the French text, the default where none was given.
reg.set_language('fr')
assert(texts.resolves(W.runtime,a)and texts.resolves(W.runtime,d)and texts.text(d,'fr')=='Une salve de gaz.')
-- Unregistered when it is the last entry: the count back, the table still allocated.
assert(texts.unregister(W.runtime)==true and reg.count()==2 and#W.runtime.writes==3)
return 'ok'
''')

    def test_a_full_registry_is_described_once_and_nothing_is_written(self):
        # 0.30.2 (a report of REGISTRY_FULL 18 of 18; every retained snapshot holds 17 of 18): a read-only description
        # of what holds each place, logged once per distinct result.
        self.check(r'''
local a=text('gas_name','ORBITAL GAS BARRAGE')
-- A game table of the size of strings_glossary_us (6 ids), and a table in the Runtime format (every language).
local glossary={}
for k=1,6 do glossary[0x1000+k]='G'..k end
local everywhere={}
for _,code in ipairs(texts.LANGUAGES)do everywhere[code]={[0x2222]='X'}end
local reg=W.text_registry({tables={{us=glossary},everywhere},capacity=2})
local before=#(W.runtime.writes or{})
local ok,code=texts.ensure(W.runtime)
assert(not ok and code=='REGISTRY_FULL'and#(W.runtime.writes or{})==before,'nothing written')
assert(count('REGISTRY FULL (read-only diagnostic')==1,'logged')
assert(count('1: game text localization/strings_glossary (6 ids)')==1,table.concat(logged,' | '))
assert(count('2: a table in the Runtime format (all 15 languages, 1 texts')==1,table.concat(logged,' | '))
texts.ensure(W.runtime)
assert(count('REGISTRY FULL (read-only diagnostic')==1,'the same result is logged once')
local report=texts.registry_report(W.runtime,{count=2,capacity=2,tables={reg.tables[1],reg.tables[2]}})
assert(report.slots[1].kind=='game'and report.slots[2].kind=='runtime_other')
return 'ok'
''')

    def test_a_full_registry_grows_as_the_game_grows_it(self):
        # 0.30.2: the add's own policy and allocator (research registry.growth): one allocate on the game thread, the
        # pointers copied, the array then the capacity; the old array untouched; then the normal append.
        self.check(r'''
local function in_update(fn)
    local out
    local w={status='active'}
    function w.cancel()w.status='cancelled'end
    function w.tick()out={fn()};w.status='complete'end;w.perf_owner='test'
    scheduler.attach(w);tick(1,0.1);assert(out,'not ticked: '..table.concat(logged,' | '):sub(-900))
    return unpack(out)
end
local a=text('gas_name','ORBITAL GAS BARRAGE')
local reg=W.text_registry({tables={{us={[NAME]='ORBITAL 120MM HE BARRAGE'}},{us={[DESC]='A barrage.'}}},capacity=2})
local G=TXT.growth
local allocator=W.alloc(64)
W.write(allocator,W.u64(W.EXE+G.vtable))
W.write(W.EXE+G.vtable+0x30,W.u64(W.EXE+G.allocate))
W.write(reg.list+G.allocator,W.u64(allocator))
local calls={}
texts.native.allocate=function(runtime,entry,object,size)
    calls[#calls+1]={entry=entry,object=object,size=size}
    return W.alloc(4096)
end
local old=W.read(reg.array,16)
-- Outside the Runtime's update: never grown, nothing written.
local before=#(W.runtime.writes or{})
local ok,code=texts.ensure(W.runtime)
assert(not ok and code=='REGISTRY_FULL'and#calls==0 and#(W.runtime.writes or{})==before)
-- Inside it: grown (2 -> 8, the add's minimum) and appended.
local done,info=in_update(function()return texts.ensure(W.runtime)end)
assert(done and info.action=='appended'and info.capacity==8 and info.count==3,tostring(info))
assert(#calls==1 and calls[1].entry==W.EXE+G.allocate and calls[1].object==allocator and calls[1].size==64)
assert(W.read(reg.array,16)==old,'the old array untouched (kept allocated)')
assert(reg.slot(0)~=0 and texts.resolves(W.runtime,a),'resolves')
assert(count('REGISTRY GROWN')==1 and count('capacity 2 -> 8, 2 tables kept in order')==1,table.concat(logged,' | '))
-- Another allocator: never called, still REGISTRY_FULL.
texts.reset_for_tests()
a=text('gas_name','ORBITAL GAS BARRAGE')
reg=W.text_registry({tables={{us={[NAME]='X'}}},capacity=1})
local other=W.alloc(64);W.write(other,W.u64(W.EXE+0x1000))
W.write(reg.list+G.allocator,W.u64(other))
calls={}
before=#(W.runtime.writes or{})
local ok2,code2=in_update(function()return texts.ensure(W.runtime)end)
assert(not ok2 and code2=='REGISTRY_FULL'and#calls==0 and#(W.runtime.writes or{})==before)
assert(count('the full registry was not grown (ALLOCATOR_CHANGED')==1)
return 'ok'
''')

    def test_every_refusal_writes_nothing(self):
        self.check(r'''
local function refused(code,text_)
    local before=#(W.runtime.writes or{})
    local ok,got,why=texts.ensure(W.runtime)
    assert(not ok and got==code and(text_==nil or tostring(why):find(text_,1,true)),
        code..' expected, got '..tostring(got)..': '..tostring(why))
    assert(#(W.runtime.writes or{})==before and#W.runtime.permanent==0,code)
end
refused('NO_TEXT')
local a=text('gas_name','ORBITAL GAS BARRAGE')
-- No registry yet (the language is set).
W.write(W.EXE+TXT.currentLanguage,W.u32(W.LANGUAGE_HASH.us))
W.write(W.EXE+TXT.registry.global,W.u64(0))
refused('UNAVAILABLE','not registered its text yet')
-- Full: the Runtime never grows the game's array.
local reg=W.text_registry({capacity=1})
refused('REGISTRY_FULL','no spare capacity (1 of 1)')
-- A game table already holds a Runtime id (in the current language).
local h=texts.id_bytes(a)
local id=h:byte(1)+h:byte(2)*256+h:byte(3)*65536+h:byte(4)*16777216
reg=W.text_registry({tables={{us={[NAME]='X'}},{us={[id]='SOMETHING ELSE'}}},capacity=3})
refused('ID_COLLISION',"text 'gas_name' of "..MOD)
-- Not one of the game's 15 languages.
reg=W.text_registry({capacity=3,language=0x12345678})
refused('UNSUPPORTED_LANGUAGE','not one of its 15 known languages')
reg.set_language(0)
refused('UNAVAILABLE','no text language yet')
-- Another build: one pinned instruction differs.
reg=W.text_registry({capacity=3})
texts.reset_for_tests();a=text('gas_name','ORBITAL GAS BARRAGE')
local pin=TXT.pins[1]
local at=(pin.module=='exe'and W.EXE or W.GAME)+pin.rva
local original=W.read(at,1)
W.write(at,string.char(0xCC))
refused('UNSUPPORTED_BUILD','text code changed')
W.write(at,original)
-- An unreadable registry is transient, never a write.
texts.reset_for_tests();a=text('gas_name','ORBITAL GAS BARRAGE')
W.write(reg.list+8,W.u64(0x7FFFFFFF0000))
local ok,why=pcall(texts.ensure,W.runtime)
assert(not ok and tostring(why):find('TARGET_UNAVAILABLE',1,true),tostring(why))
return 'ok'
''')

    def test_a_language_change_drops_it_and_the_watch_registers_it_again(self):
        self.check(r'''
local VANILLA={us={[NAME]='ORBITAL 120MM HE BARRAGE'}}
local reg=W.text_registry({tables={VANILLA,VANILLA},capacity=4})
local a=text('gas_name',{default='ORBITAL GAS BARRAGE',de='ORBITALES GASSPERRFEUER'})
assert(texts.ensure(W.runtime))
local lost
texts.keep(W.runtime,function(code,reason)lost={code,reason}end)
for _=1,5 do tick()end
assert(#W.runtime.writes==2 and texts.keeping())
-- The game's language change: German, the registry cleared and its own tables registered again.
reg.set_language('de')
reg.rebuild({{de={[NAME]='120-MM'}},{de={[NAME]='120-MM'}}})
assert(not texts.resolves(W.runtime,a))
tick()                                   -- the change is seen; one more update to be sure it settled
assert(#W.runtime.writes==2)
tick()
-- The game's rebuild left the Runtime table in the slot after its own (beyond the count): only the count is written.
assert(#W.runtime.writes==3 and reg.count()==3 and reg.slot(2)==W.runtime.permanent[1].address
    and texts.resolves(W.runtime,a),#W.runtime.writes)
assert(count('the game rebuilt its text registry (language us -> de); Runtime text registered again (table 3 of 3)')==1)
assert(texts.text(a,'de')=='ORBITALES GASSPERRFEUER')
-- No spare capacity after the next change: lost, reported once.
reg.set_language('fr')
reg.rebuild({{fr={[NAME]='A'}},{fr={[NAME]='B'}},{fr={[NAME]='C'}},{fr={[NAME]='D'}}})
for _=1,4 do tick()end
assert(lost and lost[1]=='REGISTRY_FULL'and not texts.keeping()and#W.runtime.writes==3)
assert(count('Runtime text could not stay registered (REGISTRY_FULL')==1)
return 'ok'
''')

    def test_new_text_replaces_the_runtime_table_and_never_a_game_entry(self):
        self.check(r'''
local reg=W.text_registry({capacity=3})
local a=text('gas_name','ORBITAL GAS BARRAGE')
assert(texts.ensure(W.runtime))
local first=reg.slot(1)
local b=text('gas_desc','Calls down a barrage of gas shells.')
local ok,info=texts.ensure(W.runtime)
assert(ok and info.action=='replaced'and info.index==2 and reg.count()==2,tostring(info))
assert(#W.runtime.writes==3 and W.runtime.writes[3].address==reg.array+8 and reg.slot(1)~=first)
assert(reg.slot(0)==reg.tables[1])                       -- the game's table untouched
assert(W.read(first,4)==W.u32(TXT.table.magic))         -- the old table stays allocated
assert(texts.resolves(W.runtime,a)and texts.resolves(W.runtime,b))
return 'ok'
''')


class PresentationTextTests(unittest.TestCase):
    """The development custom text path: the 120mm's name, cased name and description from Runtime text, after every
    guard; exact restore."""

    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_text_members_are_written_verified_and_restored(self):
        self.check(r'''
local reg=W.text_registry({capacity=3})
local name=text('orbital_gas_barrage_name','ORBITAL GAS BARRAGE')
local cased=text('orbital_gas_barrage_name_cased','Orbital Gas Barrage')
local desc=text('orbital_gas_barrage_description','Calls down a barrage of gas shells.')
local NATIVE=W.read(ROW,400)
local job=settle(presentation.apply_text({carrier=BIGNAME,name=name,nameCased=cased,description=desc}))
assert(job.status=='applied',tostring(job.code)..': '..tostring(job.reason))
for key,value in pairs(job.verify)do assert(value==true,key)end
-- 2 registry writes, then the 3 members; only their 12 bytes changed in the settings.
assert(writes()==5 and reg.count()==2)
assert(field(ROW,'name')==texts.id_bytes(name)and field(ROW,'nameCased')==texts.id_bytes(cased)
    and field(ROW,'description')==texts.id_bytes(desc))
for _,at in ipairs(changed())do assert(at>=ROW+0x28 and at<ROW+0x34,string.format('byte %X changed',at))end
assert(identity()and field(ROW,'icon')==presentation.reviewed(BIG,'icon'))
assert(count('stratagem presentation custom text APPLIED: Orbital 120mm HE Barrage (type 136, stable id 1063322614): '
    ..'name 0x4FAAD695 -> '..texts.id_hex(name)..' "ORBITAL GAS BARRAGE"; nameCased 0x628B5A83 -> '..texts.id_hex(cased)
    ..' "Orbital Gas Barrage"; description 0x35FEBFE6 -> '..texts.id_hex(desc)..' "Calls down a barrage of gas shells."; '
    ..'3 write; Runtime text table appended (table 2 of 2, language us); read back true; each resolves to exactly its '
    ..'text: true; identity unchanged: true; icon unchanged: true; other text members native: true; non-target bytes '
    ..'unchanged true; protection restored true')==1)
assert(texts.keeping())
-- The public fields still refuse Runtime text.
rejects({id='t',target=session.stratagem(BIGNAME),field=F.presentation_name,expect=BIGNAME,value=name},
    'custom text is not yet a public presentation value')
-- Restore: the native ids, the Runtime table out of the registry.
local restored=settle(presentation.restore())
assert(restored.status=='restored'and restored.verify.exact and restored.verify.allNative and restored.verify.identity)
assert(W.read(ROW,400)==NATIVE and#changed()==0 and reg.count()==1 and not texts.keeping())
assert(count('RESTORED: Orbital 120mm HE Barrage presents as itself again: 3 writes; restored values read back exactly: '
    ..'true; name, cased name and description native: true; identity unchanged (type 136, stable id 1063322614): true; '
    ..'non-target bytes unchanged true; protection restored true; Runtime text table unregistered')==1)
-- Applied again: the same table is registered again (no new allocation); the finalizer restores.
assert(settle(presentation.apply_text({carrier=BIGNAME,name=name})).status=='applied'and#W.runtime.permanent==1)
presentation.finalize_for_tests()
assert(W.read(ROW,400)==NATIVE and reg.count()==1)
return 'ok'
''')

    def test_a_custom_icon_stays_and_only_the_given_members_change(self):
        self.check(r'''
local reg=W.text_registry({capacity=3})
local cased=text('cased','Orbital Gas Barrage')
-- Another writer's icon (a public presentation_icon value) is not this path's: left as it is.
W.write(ROW+0xB0,presentation.reviewed(GAS,'icon'))
local job=settle(presentation.apply_text({carrier=BIGNAME,nameCased=cased}))
assert(job.status=='applied'and writes()==3,tostring(job.code)..': '..tostring(job.reason))
assert(field(ROW,'name')==presentation.reviewed(BIG,'name')and field(ROW,'icon')==presentation.reviewed(GAS,'icon'))
assert(settle(presentation.restore()).status=='restored'and field(ROW,'nameCased')==presentation.reviewed(BIG,'nameCased'))
return 'ok'
''')

    def test_every_failed_guard_refuses_with_nothing_written(self):
        self.check(r'''
local name=text('orbital_gas_barrage_name','ORBITAL GAS BARRAGE')
local function refused(spec,code,text_)
    local before=writes()
    local job=settle(presentation.apply_text(spec))
    assert(job.status=='refused'and job.code==code and(text_==nil or tostring(job.reason):find(text_,1,true)),
        code..' expected, got '..tostring(job.code)..': '..tostring(job.reason))
    assert(writes()==before,code)
end
local reg=W.text_registry({capacity=1})
refused({carrier=BIGNAME,name=name},'REGISTRY_FULL')
reg=W.text_registry({capacity=2,language=0x12345678})
refused({carrier=BIGNAME,name=name},'UNSUPPORTED_LANGUAGE')
reg=W.text_registry({capacity=2})
refused({carrier=BIGNAME,name={resource='text',text='x',mod=MOD}},'NOT_TEXT')
refused({carrier=BIGNAME,icon=name},'UNSUPPORTED_FIELD')
refused({carrier=BIGNAME},'NOTHING_TO_CHANGE')
refused({carrier='No Such Stratagem',name=name},'UNKNOWN_STRATAGEM')
-- The carrier's name is not its native id (another writer): a conflict.
local NATIVE_NAME=W.read(ROW+0x28,4)
W.write(ROW+0x28,W.u32(12345))
refused({carrier=BIGNAME,name=name},'CONFLICT')
W.write(ROW+0x28,NATIVE_NAME)
assert(#changed()==0)
-- A game table has the id.
local h=texts.id_bytes(name)
local id=h:byte(1)+h:byte(2)*256+h:byte(3)*65536+h:byte(4)*16777216
reg=W.text_registry({tables={{us={[id]='TAKEN'}}},capacity=2})
refused({carrier=BIGNAME,name=name},'ID_COLLISION')
-- Another build of the presentation readers.
reg=W.text_registry({capacity=2})
local pin=require('hd2runtime/domains/stratagem_calldown').presentation.pins[1]
local original=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,string.char(0xCC))
refused({carrier=BIGNAME,name=name},'UNSUPPORTED_BUILD')
W.write(W.GAME+pin.rva,original)
assert(#W.runtime.permanent==0)
-- Applied once: a second apply is refused until restored.
assert(settle(presentation.apply_text({carrier=BIGNAME,name=name})).status=='applied')
local job=settle(presentation.apply_text({carrier=BIGNAME,name=name}))
assert(job.status=='refused'and job.code=='ALREADY_APPLIED')
assert(settle(presentation.restore()).status=='restored'and#changed()==0)
return 'ok'
''')

    def test_a_lost_registration_restores_the_carriers_own_text(self):
        self.check(r'''
local reg=W.text_registry({capacity=2})
local name=text('orbital_gas_barrage_name','ORBITAL GAS BARRAGE')
local NATIVE=W.read(ROW,400)
assert(settle(presentation.apply_text({carrier=BIGNAME,name=name})).status=='applied')
-- A language change to a language the game does not have in its table: the Runtime cannot register for it.
reg.set_language(0x12345678)
reg.rebuild({{us={[NAME]='X'}}})
for _=1,20 do tick()end
assert(W.read(ROW,400)==NATIVE and#changed()==0,'the native text is back')
assert(count('custom text LOST (UNSUPPORTED_LANGUAGE')==1)
assert(count('RESTORED: Orbital 120mm HE Barrage presents as itself again')==1)
return 'ok'
''')

    def test_custom_text_is_not_public(self):
        self.check(r'''
local api=require('mods/skyeshade/hd2runtime')
assert(api.resources.text==nil and api.resources.image~=nil)
return 'ok'
''')
        stub = (ROOT / 'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8')
        self.assertNotIn('HD2Resources.text', stub)


class GrowthAdapterTests(unittest.TestCase):
    def test_the_allocate_call_passes_the_game_arguments_and_reads_the_result(self):
        # The real FFI adapter against a Lua callback standing in for the registry allocator's allocate (vtable +0x30):
        # (self, out {pointer, size}, bytes, 8) -> out. Nothing of the game runs.
        from lua_offline import execute
        from support import modules
        self.assertEqual(execute((modules() + r'''
local ffi=require('ffi')
local texts=require('hd2runtime/runtime/text_resources')
local seen
local backing=ffi.new('uint8_t[256]')
local cb=ffi.cast('void *(*)(void *, void *, uint64_t, uint64_t)',function(self_,out,size,align)
    seen={self=tonumber(ffi.cast('uintptr_t',self_)),size=tonumber(size),align=tonumber(align)}
    local o=ffi.cast('uint64_t *',out)
    o[0]=ffi.cast('uint64_t',ffi.cast('uintptr_t',backing));o[1]=size
    return out
end)
local entry=tonumber(ffi.cast('uintptr_t',cb))
assert(texts.native.allocate({mode='snapshot'},entry,0x5000,216)==nil,'never on a snapshot')
local pointer=texts.native.allocate({mode='live'},entry,0x5000,216)
assert(pointer==tonumber(ffi.cast('uintptr_t',backing)),'the result pointer')
assert(seen.self==0x5000 and seen.size==216 and seen.align==8,'the game arguments')
local bad=ffi.cast('void *(*)(void *, void *, uint64_t, uint64_t)',function(self_,out,size,align)
    ffi.cast('uint64_t *',out)[0]=0;return out end)
assert(texts.native.allocate({mode='live'},tonumber(ffi.cast('uintptr_t',bad)),0x5000,216)==nil,'no memory: refused')
cb:free();bad:free()
return 'ok'
''').encode()), b'ok')


if __name__ == '__main__':
    unittest.main()
