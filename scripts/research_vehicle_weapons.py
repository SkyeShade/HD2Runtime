"""Trace every catalog vehicle's mounted weapons to their native owners. Read-only.

Chain (all structural):
  vehicle entity -> MountComponentData slot (24-byte MountInfo: path, attach node, ...)
    -> mounted weapon entity (the slot path), which owns its own components:
       WeaponDataComponentData, ProjectileWeaponComponentData, WeaponMagazineComponentData,
       WeaponReloadComponentData, WeaponHeatComponentData, HealthComponentData, TurretComponentData,
       Spray/Beam/Arc weapon components
    -> ProjectileWeaponComponentData.projectile_type (+0) -> ProjectileSettings row
       -> damage_type (+60) -> DamageInfo row; impact/expiry explosion (+144/+156) -> ExplosionSettings

Guard Dog drones are carriers too (research/equipment-coverage-F5FEE03DCFDB.json): backpack DepositComponent +24
-> drone entity -> drone MountComponentData slot -> drone weapon. Their beam (Rover) and arc (K-9) weapons resolve
BeamWeapon +0 -> BeamSettings -> DamageInfo (+12) and ArcWeapon +0 -> ArcSettings -> DamageInfo (+36).

Weapon-local values live in the mounted weapon's own component records (one owner each, proven here).
Projectile, DamageInfo and ExplosionSettings rows are shared settings: every other entity that fires the
same projectile type is published as a consumer. Settings row identities come from the production
resolver run against the retained snapshot.

Output: research/vehicle-weapons-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import research_entity_authoring as entity_research
from research_attachment_presets import _module_sources, _lua
from tools.lua_runner import execute

OUTPUT = ROOT / 'research/vehicle-weapons-F5FEE03DCFDB.json'
ENTITY_RESEARCH = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
EQUIPMENT_RESEARCH = ROOT / 'research/equipment-coverage-F5FEE03DCFDB.json'
SNAPSHOT = build_profile.SNAPSHOT
COMPONENTS = ('WeaponDataComponentData', 'ProjectileWeaponComponentData', 'WeaponMagazineComponentData',
    'WeaponReloadComponentData', 'WeaponHeatComponentData', 'HealthComponentData', 'TurretComponentData',
    'WeaponRoundsComponentData', 'SprayWeaponComponentData', 'BeamWeaponComponentData', 'ArcWeaponComponentData',
    'WeaponChargeComponentData', 'MountComponentData')
MOUNT_SLOT, MOUNT_SLOTS = 24, 5


def f32(body, at):
    return round(struct.unpack_from('<f', body, at)[0], 6)


def u32(body, at):
    return struct.unpack_from('<I', body, at)[0]


def index_rows(native, component):
    body, capacity, _, _, _ = native.table(component)
    rows = {}
    for row in range(capacity):
        resource, record, _ = struct.unpack_from('<QII', body, row * 16)
        if resource:
            rows.setdefault(resource, []).append((row, record))
    return rows


def main():
    native = entity_research.Native()
    research = json.loads(ENTITY_RESEARCH.read_text())
    owners = {c: native.owners(c) for c in COMPONENTS}
    rows = {c: index_rows(native, c) for c in COMPONENTS}
    names = {}
    for weapon in json.loads((ROOT / 'schemas/player_weapon_authoring_catalog.json').read_text())['weapons']:
        for resource in weapon['resources']:
            names[int(resource, 16)] = ('player_weapon', weapon['name'])
    for weapon in json.loads((ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json').read_text())['weapons']:
        identity = weapon['catalogIdentity']
        for resource in weapon['resourceHashes']:
            names.setdefault(int(resource, 16), ('support_weapon', identity['name'] if isinstance(identity, dict) else identity))

    def ownership(resource):
        result = {}
        for component in COMPONENTS:
            found = rows[component].get(resource, [])
            if len(found) == 1:
                row, record = found[0]
                result[component] = {'recordIndex': record, 'indexRow': row,
                    'ownerCount': len(owners[component].get(record, [])),
                    'uniqueOwner': len(owners[component].get(record, [])) == 1}
            elif len(found) > 1:
                result[component] = {'ambiguous': True}
        return result

    # Every entity that fires a given projectile type (for shared-scope publication).
    fired_by = defaultdict(list)
    for record, resources in owners['ProjectileWeaponComponentData'].items():
        projectile_type = u32(native.record('ProjectileWeaponComponentData', record), 0)
        for resource in resources:
            fired_by[projectile_type].append(resource)

    vehicles, mounted_labels = [], {}
    # Catalog vehicles, then the Guard Dog drones (carrier: the backpack that deploys them).
    carriers = []
    for vehicle in research['vehicles']:
        carriers.append({'name': vehicle['name'], 'resource': vehicle['resource'],
            'reviewed': {item['slot']: item for item in vehicle['mount']['slots']}, 'carrier': None})
    for item in json.loads(EQUIPMENT_RESEARCH.read_text())['guardDogs']['drones']:
        drone = item['drone']
        carriers.append({'name': item['backpack'], 'resource': drone['resource'],
            'reviewed': {slot['slot']: {'slot': slot['slot'], 'path': slot['resource'], 'name': slot['name'],
                'attachNodeName': slot['attachNode']} for slot in drone['mount']['slots']},
            'carrier': {'kind': 'backpack_drone', 'backpack': item['backpack'], 'backpackResource':
                item['backpackResource'], 'link': {'component': 'DepositComponentData', 'offset': 24,
                    'recordIndex': item['deposit']['recordIndex'], 'indexRow': item['deposit']['indexRow'],
                    'ownerCount': item['deposit']['ownerCount']}, 'droneEntityRow': drone['entityRow']}})
    for vehicle in carriers:
        resource = int(vehicle['resource'], 16)
        own = ownership(resource)
        mount = own.get('MountComponentData')
        slots = []
        if mount and not mount.get('ambiguous'):
            body = native.record('MountComponentData', mount['recordIndex'])
            reviewed = vehicle['reviewed']
            for index in range(MOUNT_SLOTS):
                path = struct.unpack_from('<Q', body, index * MOUNT_SLOT)[0]
                if not path:
                    continue
                if index not in reviewed or int(reviewed[index]['path'], 16) != path:
                    raise ValueError(f"{vehicle['name']}: mount slot {index} differs from the reviewed mount record")
                weapon_own = ownership(path)
                slot = {'slot': index, 'path': f'0x{path:016X}', 'nativePath': native.path(path),
                    'name': reviewed[index].get('name'), 'attachNodeName': reviewed[index].get('attachNodeName'),
                    'ownership': weapon_own}
                slot['isWeapon'] = 'WeaponDataComponentData' in weapon_own and any(
                    c in weapon_own for c in ('ProjectileWeaponComponentData', 'SprayWeaponComponentData',
                        'BeamWeaponComponentData', 'ArcWeaponComponentData'))
                if slot['isWeapon']:
                    mounted_labels[path] = (vehicle['name'], index, reviewed[index].get('name'))
                    values = {}
                    if 'ProjectileWeaponComponentData' in weapon_own:
                        body_pw = native.record('ProjectileWeaponComponentData', weapon_own['ProjectileWeaponComponentData']['recordIndex'])
                        values['projectileType'] = u32(body_pw, 0)
                        values['fireRate'] = f32(body_pw, 8)
                        values['fireRateVector'] = [f32(body_pw, 4), f32(body_pw, 8), f32(body_pw, 12)]
                        values['infiniteAmmo'] = body_pw[36]
                        values['speedMultiplier'] = f32(body_pw, 124)
                        values['addends128'] = [f32(body_pw, 128), f32(body_pw, 132)]
                        values['addends136'] = [f32(body_pw, 136), f32(body_pw, 140)]
                    if 'SprayWeaponComponentData' in weapon_own:
                        values['sprayDamageType'] = u32(native.record('SprayWeaponComponentData',
                            weapon_own['SprayWeaponComponentData']['recordIndex']), 200)
                    if 'BeamWeaponComponentData' in weapon_own:
                        body_b = native.record('BeamWeaponComponentData', weapon_own['BeamWeaponComponentData']['recordIndex'])
                        values['beamType'] = u32(body_b, 0)
                        values['beamFireRate'] = struct.unpack_from('<i', body_b, 104)[0]
                    if 'ArcWeaponComponentData' in weapon_own:
                        values['arcType'] = u32(native.record('ArcWeaponComponentData',
                            weapon_own['ArcWeaponComponentData']['recordIndex']), 0)
                    if 'WeaponMagazineComponentData' in weapon_own:
                        body_m = native.record('WeaponMagazineComponentData', weapon_own['WeaponMagazineComponentData']['recordIndex'])
                        values['magazine'] = {'capacity': u32(body_m, 136), 'magazines': u32(body_m, 140),
                            'refill': u32(body_m, 144), 'max': u32(body_m, 148), 'reloadThreshold': u32(body_m, 152)}
                    if 'WeaponReloadComponentData' in weapon_own:
                        values['reloadDuration'] = f32(native.record('WeaponReloadComponentData',
                            weapon_own['WeaponReloadComponentData']['recordIndex']), 56)
                    if 'WeaponHeatComponentData' in weapon_own:
                        body_h = native.record('WeaponHeatComponentData', weapon_own['WeaponHeatComponentData']['recordIndex'])
                        values['heat'] = {'capacity': f32(body_h, 96), 'heatPerShot': f32(body_h, 116),
                            'heatPerSecond': f32(body_h, 120), 'coolPerSecond': f32(body_h, 128)}
                    if 'HealthComponentData' in weapon_own:
                        body_hp = native.record('HealthComponentData', weapon_own['HealthComponentData']['recordIndex'])
                        values['health'] = struct.unpack_from('<i', body_hp, 0)[0]
                        values['armor'] = u32(body_hp, 280)
                        # Populated damage zones (38 x 552 bytes from +520; name hash at +96).
                        values['zones'] = [{'index': index, 'nameHash': u32(body_hp, 520 + index * 552 + 96),
                            'armor': u32(body_hp, 520 + index * 552 + 216),
                            'health': struct.unpack_from('<i', body_hp, 520 + index * 552 + 232)[0]}
                            for index in range(38) if u32(body_hp, 520 + index * 552 + 96)]
                    body_wd = native.record('WeaponDataComponentData', weapon_own['WeaponDataComponentData']['recordIndex'])
                    values['ergonomics'] = f32(body_wd, 356)
                    slot['values'] = values
                slots.append(slot)
        vehicles.append({'name': vehicle['name'], 'resource': vehicle['resource'], 'slots': slots,
            **({'carrier': vehicle['carrier']} if vehicle['carrier'] else {})})

    projectile_types = sorted({slot['values']['projectileType'] for v in vehicles for slot in v['slots']
        if slot.get('isWeapon') and 'projectileType' in slot.get('values', {})})
    spray_types = sorted({slot['values']['sprayDamageType'] for v in vehicles for slot in v['slots']
        if slot.get('isWeapon') and 'sprayDamageType' in slot.get('values', {})})
    beam_types = sorted({slot['values']['beamType'] for v in vehicles for slot in v['slots']
        if slot.get('isWeapon') and 'beamType' in slot.get('values', {})})
    arc_types = sorted({slot['values']['arcType'] for v in vehicles for slot in v['slots']
        if slot.get('isWeapon') and 'arcType' in slot.get('values', {})})
    preload = '\n'.join('package.preload[' + _lua(name) + ']=function(...) return assert(loadstring(' + _lua(body)
        + ',' + _lua(name) + '))(...) end' for name, body in _module_sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(SNAPSHOT)) + r''',{
  expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
 local reader=Reader.new(source)
 local roots=discover.locate(source,reader,profile,{projectile=true,damage=true,explosion=true,beam=true,arc=true})
 local function id(r)return r and {group=r.group,row=r.row,recordType=r.kind,settingsType=r.settings_type}end
 local damage_users,explosion_users={},{}
 for t,r in pairs(roots.projectile.records)do
  local d=b.u32(r.bytes,60);damage_users[d]=(damage_users[d]or 0)+1
  for _,o in ipairs({144,156})do local e=b.u32(r.bytes,o);if e~=0 then explosion_users[e]=(explosion_users[e]or 0)+1 end end
 end
 local out={projectiles={},spray={},beams={},arcs={}}
 local function damage_values(dr)
  return {standard_damage=b.value(dr.bytes,4,'i32'),durable_damage=b.value(dr.bytes,8,'i32'),
   ap_direct=b.u32(dr.bytes,12),ap_slight=b.u32(dr.bytes,16),ap_large=b.u32(dr.bytes,20),ap_extreme=b.u32(dr.bytes,24),
   demolition=b.u32(dr.bytes,28),stagger=b.u32(dr.bytes,32),push_force=b.u32(dr.bytes,36)}
 end
 for _,t in ipairs(''' + _lua(beam_types) + r''')do
  local r=roots.beam.records[t];local item={type=t,settings=id(r)}
  if r then
   item.values={radius=b.value(r.bytes,4,'f32'),length=b.value(r.bytes,8,'f32')}
   local d=b.u32(r.bytes,12);local dr=roots.damage.records[d]
   item.damage={type=d,settings=id(dr)};if dr then item.damage.values=damage_values(dr)end
  end
  out.beams[#out.beams+1]=item
 end
 for _,t in ipairs(''' + _lua(arc_types) + r''')do
  local r=roots.arc.records[t];local item={type=t,settings=id(r)}
  if r then
   item.values={velocity=b.value(r.bytes,4,'f32'),range=b.value(r.bytes,8,'f32'),
    distance_at_max_spread=b.value(r.bytes,12,'f32'),max_angle_spread=b.value(r.bytes,20,'f32'),
    chain_count=b.u32(r.bytes,28),max_split=b.u32(r.bytes,32)}
   local d=b.u32(r.bytes,36);local dr=roots.damage.records[d]
   item.damage={type=d,settings=id(dr)};if dr then item.damage.values=damage_values(dr)end
  end
  out.arcs[#out.arcs+1]=item
 end
 for _,t in ipairs(''' + _lua(spray_types) + r''')do
  local dr=roots.damage.records[t];local item={type=t,settings=id(dr)}
  if dr then item.values={standard_damage=b.value(dr.bytes,4,'i32'),durable_damage=b.value(dr.bytes,8,'i32'),
   ap_direct=b.u32(dr.bytes,12),ap_slight=b.u32(dr.bytes,16),ap_large=b.u32(dr.bytes,20),ap_extreme=b.u32(dr.bytes,24),
   demolition=b.u32(dr.bytes,28),stagger=b.u32(dr.bytes,32),push_force=b.u32(dr.bytes,36)}end
  out.spray[#out.spray+1]=item
 end
 for _,t in ipairs(''' + _lua(projectile_types) + r''')do
  local p=roots.projectile.records[t]
  local item={type=t,settings=id(p)}
  if p then
   item.values={pellet_count=b.u32(p.bytes,28),velocity=b.value(p.bytes,32,'f32'),mass=b.value(p.bytes,36,'f32'),
    drag=b.value(p.bytes,40,'f32'),gravity=b.value(p.bytes,44,'f32'),lifetime=b.value(p.bytes,52,'f32'),
    penetration_slowdown=b.value(p.bytes,64,'f32')}
   local d=b.u32(p.bytes,60);local dr=roots.damage.records[d]
   item.damage={type=d,settings=id(dr),projectileUsers=damage_users[d]}
   if dr then item.damage.values={standard_damage=b.value(dr.bytes,4,'i32'),durable_damage=b.value(dr.bytes,8,'i32'),
    ap_direct=b.u32(dr.bytes,12),ap_slight=b.u32(dr.bytes,16),ap_large=b.u32(dr.bytes,20),ap_extreme=b.u32(dr.bytes,24),
    demolition=b.u32(dr.bytes,28),stagger=b.u32(dr.bytes,32),push_force=b.u32(dr.bytes,36)}end
   item.explosions={}
   for phase,o in pairs({impact=144,expiry=156})do
    local e=b.u32(p.bytes,o)
    if e~=0 then
     local er=roots.explosion.records[e];local x={type=e,settings=id(er),projectileUsers=explosion_users[e]}
     if er then
      x.values={inner_radius=b.value(er.bytes,16,'f32'),outer_radius=b.value(er.bytes,20,'f32'),
       shockwave_radius=b.value(er.bytes,24,'f32')}
      local ed=b.u32(er.bytes,4);local edr=roots.damage.records[ed]
      x.damage={type=ed,settings=id(edr)}
      if edr then x.damage.values={standard_damage=b.value(edr.bytes,4,'i32'),durable_damage=b.value(edr.bytes,8,'i32'),
       ap_direct=b.u32(edr.bytes,12),ap_slight=b.u32(edr.bytes,16),ap_large=b.u32(edr.bytes,20),ap_extreme=b.u32(edr.bytes,24),
       demolition=b.u32(edr.bytes,28),stagger=b.u32(edr.bytes,32),push_force=b.u32(edr.bytes,36)}end
     end
     item.explosions[phase]=x
    end
   end
  end
  out.projectiles[#out.projectiles+1]=item
 end
 reader.verify();source.close()
 return out
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''
    settings = json.loads(execute(program.encode()))
    projectiles = {item['type']: item for item in settings['projectiles']}
    sprays = {item['type']: item for item in settings['spray']}
    beams = {item['type']: item for item in settings['beams']}
    arcs = {item['type']: item for item in settings['arcs']}
    component_users = {name: defaultdict(list) for name in ('BeamWeaponComponentData', 'ArcWeaponComponentData')}
    for name in component_users:
        for record, resources in owners[name].items():
            kind = u32(native.record(name, record), 0)
            for resource in resources:
                component_users[name][kind].append(resource)

    def users_of(resources):
        users = []
        for resource in resources:
            if resource in mounted_labels:
                users.append({'kind': 'vehicle_weapon', 'vehicle': mounted_labels[resource][0],
                    'slot': mounted_labels[resource][1]})
            elif resource in names:
                users.append({'kind': names[resource][0], 'name': names[resource][1]})
            else:
                users.append({'kind': 'entity', 'path': native.path(resource)})
        return users
    spray_users = defaultdict(list)
    for record, resources in owners['SprayWeaponComponentData'].items():
        spray_type = u32(native.record('SprayWeaponComponentData', record), 200)
        for resource in resources:
            spray_users[spray_type].append(resource)
    for vehicle in vehicles:
        for slot in vehicle['slots']:
            values = slot.get('values') or {}
            if 'sprayDamageType' in values:
                t = values['sprayDamageType']
                users = []
                for resource in spray_users[t]:
                    if resource in mounted_labels:
                        users.append({'kind': 'vehicle_weapon', 'vehicle': mounted_labels[resource][0],
                            'slot': mounted_labels[resource][1]})
                    elif resource in names:
                        users.append({'kind': names[resource][0], 'name': names[resource][1]})
                    else:
                        users.append({'kind': 'entity', 'path': native.path(resource)})
                slot['spray'] = dict(sprays.get(t) or {'type': t}, usedBy=users)
            if 'beamType' in values:
                t = values['beamType']
                slot['beam'] = dict(beams.get(t) or {'type': t},
                    usedBy=users_of(component_users['BeamWeaponComponentData'][t]))
            if 'arcType' in values:
                t = values['arcType']
                slot['arc'] = dict(arcs.get(t) or {'type': t},
                    usedBy=users_of(component_users['ArcWeaponComponentData'][t]))
            if 'projectileType' in values:
                t = values['projectileType']
                consumers = []
                for resource in fired_by[t]:
                    if resource in mounted_labels:
                        label = mounted_labels[resource]
                        consumers.append({'kind': 'vehicle_weapon', 'vehicle': label[0], 'slot': label[1]})
                    elif resource in names:
                        consumers.append({'kind': names[resource][0], 'name': names[resource][1]})
                    else:
                        consumers.append({'kind': 'entity', 'path': native.path(resource)})
                slot['projectile'] = dict(projectiles.get(t) or {'type': t}, firedBy=consumers)
    report = {'schemaVersion': 1, 'snapshot': SNAPSHOT.name, 'entitiesSha256': entity_research.ENTITY_SHA256,
        'mountSlotBytes': MOUNT_SLOT, 'vehicles': vehicles}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    for vehicle in vehicles:
        for slot in vehicle['slots']:
            v = slot.get('values') or {}
            print(vehicle['name'], slot['slot'], slot.get('name'), slot['isWeapon'], sorted(slot['ownership']),
                {k: v.get(k) for k in ('fireRate', 'magazine', 'reloadDuration', 'health')},
                (slot.get('projectile') or {}).get('type'), len((slot.get('projectile') or {}).get('firedBy', [])))


if __name__ == '__main__':
    main()
