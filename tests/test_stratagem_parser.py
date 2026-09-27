import json
import struct
import unittest

from support import ROOT, execute, lua, modules


def u64(value):
    return int(value,16) if isinstance(value,str) else value


def fixture():
    records=json.loads((ROOT/'tests/fixtures/stratagem_records.json').read_text())
    base=0x6000000
    groups=[]
    pointers=bytearray(150*8)
    offsets={}
    for key in ('shield_relay','orbital_laser'):
        item=records[key]
        payloads=[u64(value) for value in item['payloads']]
        body=bytearray(16+400+len(payloads)*8)
        root=sum(len(group) for group in groups)+4+24
        record_at=root+16
        payload_at=root+16+400
        row_pointer=base+record_at if key=='shield_relay' else 16
        payload_pointer=base+payload_at if key=='shield_relay' else 416
        struct.pack_into('<QII',body,0,row_pointer,1,0)
        if key=='shield_relay':
            record=bytearray.fromhex(item['record_hex'])
        else:
            record=bytearray(400)
            struct.pack_into('<II',record,0,item['type'],item['id'])
            struct.pack_into('<I',record,80,3)
            struct.pack_into('<f',record,104,300)
            struct.pack_into('<Q',record,168,u64(item['package']))
        struct.pack_into('<QII',record,152,payload_pointer,len(payloads),0)
        body[16:416]=record
        for index,value in enumerate(payloads):
            struct.pack_into('<Q',body,416+index*8,value)
        header=struct.pack('<4s5I',b'LDLD',1,0x30EB6399,len(body),1,0)
        groups.append(header+body)
        struct.pack_into('<Q',pointers,item['type']*8,base+record_at)
        offsets[key]={'record':record_at,'root':root,'payload':payload_at}
    source=struct.pack('<I',2)+b''.join(groups)
    spec={'size':len(source),'groups':2,'stride':400,'type':0x30EB6399,'version':1,
          'info_type':0x7BD60854,'entries':150,'payload_max':16,'total_records':2}
    targets={}
    for index,key in enumerate(('shield_relay','orbital_laser')):
        item=records[key]
        targets[key]={'resource':item['payloads'][0],'package':item['package'],'id':item['id'],
                      'current_type':item['type'],'group':index,'row':0,
                      'payload_count':len(item['payloads'])}
    return source,bytes(pointers),spec,targets,offsets,base


def run_lua(tail):
    source,pointers,spec,targets,offsets,base=fixture()
    script=modules()+f'''\nlocal source={lua(source)}
local pointers={lua(pointers)}
local spec={lua(spec)}
local targets={lua(targets)}
local offsets={lua(offsets)}
local base={base}
local parser=require('hd2runtime/core/stratagem')
'''+tail
    return execute(script.encode())


class StratagemParserTests(unittest.TestCase):
    def test_parse_all_preserves_payload_ownership(self):
        self.assertEqual(run_lua("""
local records=parser.parse_all(source,base,pointers,spec)
assert(#records==2 and records[1].record_kind==22 and records[2].record_kind==105)
assert(records[1].payloads[1]=='0xED13DDC480EC6910')
assert(records[2].payloads[1]=='0xEC3575E7A93793BB')
assert(records[1].payload_pointer=='relocated_absolute')
assert(records[2].payload_pointer=='serialized_group_relative')
return'ok'
"""),b'ok')

    def test_relocated_two_payload_shield_and_relative_orbital(self):
        self.assertEqual(run_lua("""
local shield=parser.parse(source,base,pointers,spec,targets.shield_relay)
assert(shield.index==22 and shield.group==0 and shield.row==0)
assert(shield.identity.payload_count==2)
assert(shield.identity.payload_pointer=='relocated_absolute')
assert(shield.identity.row_pointer=='relocated_absolute')
assert(shield.identity.payloads[1]=='0xED13DDC480EC6910')
assert(shield.identity.payloads[2]=='0x73F8498BFFDCF415')
local laser=parser.parse(source,base,pointers,spec,targets.orbital_laser)
assert(laser.index==105 and laser.group==1 and laser.row==0)
assert(laser.identity.payload_count==1)
assert(laser.identity.payload_pointer=='serialized_group_relative')
assert(laser.identity.row_pointer=='serialized_group_relative')
assert(laser.identity.payloads[1]=='0xEC3575E7A93793BB')
return 'ok'
"""),b'ok')

    def rejected(self,mutation,reason,target='shield_relay'):
        self.assertEqual(run_lua(mutation+f"\nlocal ok,why=pcall(parser.parse,source,base,pointers,spec,targets.{target});assert(not ok and tostring(why):find({lua(reason)},1,true),why);return 'ok'"),b'ok')

    def test_count_is_u32_and_reserved_must_be_zero(self):
        self.rejected("source=source:sub(1,offsets.shield_relay.record+164)..string.char(1,0,0,0)..source:sub(offsets.shield_relay.record+169)",'payload count/reserved')

    def test_payload_count_is_pinned_per_target(self):
        self.rejected("source=source:sub(1,offsets.shield_relay.record+160)..string.char(1,0,0,0)..source:sub(offsets.shield_relay.record+165)",'payload count changed')

    def test_payload_pointer_cannot_leave_group(self):
        self.rejected("source=source:sub(1,offsets.shield_relay.record+152)..string.char(0,0,0,7,0,0,0,0)..source:sub(offsets.shield_relay.record+161)",'payload list pointer outside/ambiguous')

    def test_target_payload_must_appear_exactly_once(self):
        self.rejected("local at=offsets.shield_relay.payload+8;source=source:sub(1,at)..source:sub(offsets.shield_relay.payload+1,offsets.shield_relay.payload+8)..source:sub(at+9)",'target payload absent/ambiguous')

    def test_row_pointer_support_does_not_weaken_bounds(self):
        self.rejected("local at=offsets.orbital_laser.root;source=source:sub(1,at)..string.char(8,0,0,0,0,0,0,0)..source:sub(at+9)",'stratagem rows pointer outside/ambiguous',target='orbital_laser')

    def test_group_record_version_and_schema_remain_pinned(self):
        self.rejected("source=source:sub(1,8)..string.char(2,0,0,0)..source:sub(13)",'stratagem framing')
        self.rejected("spec.info_type=0",'unsupported StratagemSettings/StratagemInfo schema')


if __name__=='__main__':
    unittest.main()
