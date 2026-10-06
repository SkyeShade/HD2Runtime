"""Vehicle tuning fields: exosuit body rotation (RotationComponent) and wheeled/tracked steering (VehicleMotion) on
hd2.vehicle(name), and mounted-weapon turret motion (TurretComponent) on hd2.vehicle(name):weapon(mount).

Source: the authoring section of research/vehicle-mech-components-F5FEE03DCFDB.json (scripts/
research_vehicle_mech_components.py): every backing record identity (record, index row, owners), the reviewed
baseline, the range and its reason, and the lifecycle each member has in native code. Vehicle turrets reuse the sentry
turret field ids on the same TurretComponent members (one semantic layer); sentry live evidence does not transfer to
vehicles, so every field here requires allow_unverified_effect.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/vehicle-mech-components-F5FEE03DCFDB.json'
UNVERIFIED = ('Native-code proven (research/vehicle-mech-components-F5FEE03DCFDB.json: the reading routine and its '
    'units are pinned), but not yet shown in game on a vehicle. Sentry live evidence for the same turret ids does not '
    'apply to vehicles.')
ACTIVE = {'entity_spawn': 'ACTIVE_AT_INSTANTIATION', 'every_update': 'ACTIVE_EVERY_UPDATE',
    'every_frame': 'ACTIVE_EVERY_FRAME'}


def load() -> dict:
    return json.loads(RESEARCH.read_text(encoding='utf-8'))['authoring']


def contract_extra(contract: dict) -> dict:
    """Range, acknowledgement, lifecycle and evidence shared by every instance of one field."""
    applies = contract['appliesWhen']
    return {'min': contract['min'], 'max': contract['max'], 'rangeReason': contract['rangeReason'],
        'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': UNVERIFIED,
        'lifecycle': contract['lifecycle'], 'appliesWhen': applies,
        'order': contract.get('order'),
        'effect': {'activeSource': ACTIVE[applies], 'activeSourceProven': True, 'appliesWhen': applies,
            'instantiationOnly': applies == 'entity_spawn', 'lifecycle': contract['lifecycle']},
        'notices': [{'kind': 'lifecycle', 'text': contract['lifecycle']}]}


def vehicle_items(research: dict, vehicle: str, resource: str) -> list[dict]:
    """The reviewed rotation/steering instances of one catalog vehicle (identity checked against the entity
    research's own resource)."""
    items = [item for item in research['vehicleFields'] if item['vehicle'] == vehicle]
    for item in items:
        if item['resource'].upper() != resource.upper():
            raise ValueError(f'{vehicle}: tuning research names another entity ({item["resource"]})')
        if not item['uniqueOwner'] or item['ownerResources'] != [item['resource']]:
            raise ValueError(f'{vehicle}: {item["component"]} record is shared; re-prove the scope')
    return items


def build(builder, name: str, target: dict, resource: str, research: dict) -> list[str]:
    """Add the vehicle's tuning descriptors to the entity Builder; returns their instance keys."""
    keys = []
    for item in vehicle_items(research, name, resource):
        contract = research['fieldContracts'][item['field']]
        backing = {'component': item['component'], 'resource': resource, 'recordIndex': item['recordIndex'],
            'indexRow': item['indexRow'], 'ownerCount': item['ownerCount'], 'uniqueOwner': item['uniqueOwner'],
            'offset': item['offset'], 'storage': 'f32', 'width': 4, 'semanticOwners': [name]}
        extra = contract_extra(contract)
        extra['evidence'] = {'tier': 'native_consumer_proven', 'referenceMod': None,
            'proof': 'research/vehicle-mech-components-F5FEE03DCFDB.json', 'provenOn': [], 'sharedTypedSchema': False}
        descriptor = builder.add(name, target, item['field'], item['baseline'], backing, extra=extra)
        keys.append(descriptor['instanceKey'])
    return keys


def mount_items(research: dict, weapon: str, resource: str) -> list[dict]:
    """The reviewed turret instances of one mounted weapon (key 'Vehicle / mount')."""
    items = [item for item in research['mountFields'] if item['weapon'] == weapon]
    for item in items:
        if item['resource'].upper() != resource.upper():
            raise ValueError(f'{weapon}: turret research names another entity ({item["resource"]})')
        if not item['uniqueOwner'] or item['ownerResources'] != [item['resource']]:
            raise ValueError(f'{weapon}: TurretComponent record is shared; re-prove the scope')
    return items
