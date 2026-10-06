"""Custom stratagem projects (docs/custom-stratagem-builder.md).

custom_stratagems.json is the structured form of a mod's custom stratagems that a tool (the future ModBuilder) edits.
This module validates it against CustomStratagemSchema.json (the fields, limits and donor catalogues the Runtime itself
enforces) and compiles it into the mod's src/addon.lua (hd2.custom_stratagem.register calls), which the normal SDK
build (`hd2.py build`) then packs with the mod's images. The Runtime does not read the JSON in game.

Only data is representable: Lua callbacks (on_activate, ctx:barrage, hd2.pelican.spawn, ...) stay the advanced escape
hatch of a hand-written src/addon.lua. A compiled addon starts with GENERATED_HEADER; a hand-written one is never
overwritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

FORMAT = 'hd2runtime-custom-stratagems/1'
PROJECT_FILE = 'custom_stratagems.json'
GENERATED_HEADER = '-- Generated from custom_stratagems.json by the HD2Runtime SDK'
SDK = Path(__file__).resolve().parents[1]


def load_schema(sdk: Path | None = None) -> dict:
    return json.loads(((sdk or SDK) / 'CustomStratagemSchema.json').read_text(encoding='utf-8'))


def _lua_string(s: str) -> str:
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == "'":
            out.append("\\'")
        elif ch == '\n':
            out.append('\\n')
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append('\\%03d' % ord(ch))
        else:
            out.append(ch)
    return "'" + ''.join(out) + "'"


def _lua_key(k: str) -> str:
    return k if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) else '[' + _lua_string(k) + ']'


def _lua_value(v) -> str:
    if type(v).__name__ == '_Expr':
        return str(v)
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v) if v != int(v) else str(int(v))
    if isinstance(v, str):
        return _lua_string(v)
    if isinstance(v, list):
        return '{' + ','.join(_lua_value(x) for x in v) + '}'
    if isinstance(v, tuple):          # an ordered table: ((key, value), ...)
        return '{' + ','.join(_lua_key(k) + '=' + _lua_value(x) for k, x in v) + '}'
    raise TypeError('unsupported value: %r' % (v,))


# -------------------------------------------------------------------------------------------------- validation --
class Problems(list):
    def add(self, where, text):
        self.append('%s: %s' % (where, text))


def _number(problems, where, value, field, required=False):
    if value is None:
        if required:
            problems.add(where, 'required')
        return
    integer = field.get('type') == 'integer'
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (integer and value != int(value)):
        problems.add(where, 'must be %s' % ('a whole number' if integer else 'a number'))
        return
    lo, hi = field.get('min'), field.get('max')
    if lo is not None and (value <= lo if field.get('exclusiveMin') else value < lo):
        problems.add(where, 'must be %s %s' % ('above' if field.get('exclusiveMin') else 'at least', lo))
    if hi is not None and value > hi:
        problems.add(where, 'must be at most %s' % hi)


def _names(schema, catalog, predicate=None):
    return {item['name']: item for item in schema['catalogs'][catalog] if predicate is None or predicate(item)}


def _relation(a, b):
    if a == b:
        return 'equal'
    if a[:len(b)] == b or b[:len(a)] == a:
        return 'a prefix'
    return None


def _only_keys(problems, where, value, keys):
    if not isinstance(value, dict):
        problems.add(where, 'must be an object')
        return False
    for key in value:
        if key not in keys:
            problems.add(where, 'unsupported field %s (supported: %s)' % (key, ', '.join(sorted(keys))))
    return True


def _families(schema):
    # Every payload family a project may use: the families list, the carrier pod family (podFamily) and each family's
    # options (familyOptions: the expendable family's pod), merged into its fields.
    out = {}
    for f in schema['families'] + ([schema['podFamily']] if schema.get('podFamily') else []):
        f = dict(f)
        options = schema.get('familyOptions', {}).get(f['family'], {})
        if options:
            f['fields'] = dict(f['fields'])
            for key, field in options.items():
                if key == 'carrier':
                    f['carrier'] = dict(f.get('carrier', {}), **field)
                else:
                    f['fields'][key] = field
        out[f['family']] = f
    return out


def _weapon(problems, where, value, schema, family):
    fields = _families(schema)[family]
    fields = (fields['fields']['items']['item']['modify']['fields'] if family in ('support', 'pod')
        else fields['fields']['modify']['fields'] if family == 'expendable' else fields['fields']['weapon']['fields'])
    if not _only_keys(problems, where, value, set(fields)):
        return
    projectiles = _names(schema, 'projectileDonors')
    explosions = _names(schema, 'explosionDonors')
    for key, v in value.items():
        f = fields.get(key)
        if f is None:
            continue                   # reported by _only_keys
        if key == 'projectile':
            if v not in projectiles:
                problems.add(where + '.projectile', 'must name a support weapon with a reviewed round '
                    '(CustomStratagemSchema catalogs.projectileDonors)')
        elif key == 'impact_explosion':
            if v not in explosions:
                problems.add(where + '.impact_explosion', 'must be a reviewed explosion donor: '
                    + ', '.join(sorted(explosions)))
        elif key == 'recoil':
            if v not in f['values']:
                problems.add(where + '.recoil', "must be 'zero'")
        else:
            _number(problems, where + '.' + key, v, f)


PAYLOAD_KEYS = {'support': 'support', 'pod': 'pod', 'expendable': 'expendable', 'sentry': 'sentry', 'eagle': 'eagle',
    'silo': 'silo'}


def _payload_key(payload):
    family = payload.get('family')
    if family == 'orbital':
        return 'orbital_native' if payload.get('native') is True else 'orbital'
    return PAYLOAD_KEYS.get(family, family)


def _family_carrier(problems, where, carrier, family_spec, schema=None, payload=None):
    want = family_spec.get('carrier', {})
    beacons = want.get('beacon')
    group = carrier.get('group')
    groups = {g['name']: g for g in (schema or {}).get('catalogs', {}).get('carrierGroups', [])}
    beacon = carrier.get('beacon')
    if group is not None:
        g = groups.get(group)
        if not g:
            problems.add(where + '.carrier.group', 'must be one of ' + ', '.join(groups))
            return
        key = _payload_key(payload or {})
        if key not in g['payloads']:
            problems.add(where + '.carrier.group', 'the group %s cannot carry a %s payload (it carries: %s)' % (group,
                key, ', '.join(g['payloads'])))
        if beacon is not None and g['beacon'] != 'any' and beacon != g['beacon']:
            problems.add(where + '.carrier.beacon', 'the group %s throws a %s beacon' % (group, g['beacon']))
        if beacon is None and g['beacon'] != 'any':
            beacon = g['beacon']
        for key in ('prefer_families', 'allow_families'):
            for f in carrier.get(key) or []:
                if g.get('families') and f not in g['families']:
                    problems.add(where + '.carrier.' + key, '%s is outside the group %s' % (f, group))
    if 'slots' in carrier:
        if group is None or not (groups.get(group) or {}).get('pod') and not (groups.get(group) or {}).get('weapon'):
            problems.add(where + '.carrier.slots', 'a pod capacity: only with the support_pod or expendable group')
    want_groups = want.get('groups')
    if want_groups and group is not None and group not in want_groups:
        problems.add(where + '.carrier.group', 'a %s payload needs the group %s' % (family_spec['family'],
            ' or '.join(want_groups)))
    if beacons and beacon not in beacons:
        problems.add(where + '.carrier.beacon', 'a %s payload needs a %s beacon' % (family_spec['family'],
            ' or '.join(beacons)))
    only = want.get('allowFamilies')
    if only:
        allowed = carrier.get('allow_families') or carrier.get('prefer_families')
        if not allowed or any(f not in only for f in allowed):
            problems.add(where + '.carrier', 'a %s payload allows the %s family only: set allow_families to %s' % (
                family_spec['family'], '/'.join(only), only))


def _pod_items(problems, where, lst, schema, field, clone_ok):
    items = {i['key']: i for i in schema['catalogs']['podItems']}
    if not (isinstance(lst, list) and field['min'] <= len(lst) <= field['max']):
        problems.add(where, 'must list %d to %d items' % (field['min'], field['max']))
        return
    seen, total, clones = set(), 0, 0
    for k, item in enumerate(lst):
        at = '%s[%d]' % (where, k)
        if not _only_keys(problems, at, item, set(field['item'])):
            continue
        key = item.get('item')
        count = item.get('count', 1)
        _number(problems, at + '.count', count, field['item']['count'])
        if key == 'clone':
            if not clone_ok:
                problems.add(at + '.item', '"clone" is an expendable pod\'s carrier weapon only')
            elif 'modify' in item:
                problems.add(at + '.modify', 'the clone takes the payload\'s modify')
            clones += count if isinstance(count, int) else 0
        else:
            entry = items.get(key)
            if not entry:
                problems.add(at + '.item', 'must be "clone" (expendable) or a podItems key (support_weapon/<name>, '
                    'backpack/<name>, player_weapon/<name>)')
                continue
            if entry['status'] == 'unverified' and item.get('allow_unverified_effect') is not True:
                problems.add(at + '.allow_unverified_effect', '%s (%s) is not live-tested in a pod: it needs '
                    'allow_unverified_effect = true' % (entry['name'], entry['kind']))
            if entry['status'] != 'unverified' and 'allow_unverified_effect' in item:
                problems.add(at + '.allow_unverified_effect', 'only an unverified kind takes it')
            if 'modify' in item:
                if entry['kind'] == 'backpack':
                    problems.add(at + '.modify', 'a backpack: no instance-local backpack field is reviewed')
                else:
                    _weapon(problems, at + '.modify', item['modify'], schema, 'pod')
                    _rate_selector(problems, at + '.modify', item['modify'], entry)
        if key in seen:
            problems.add(at + '.item', 'listed twice (give it a count)')
        seen.add(key)
        total += count if isinstance(count, int) else 0
    if total > field['item']['count']['max']:
        problems.add(where, '%d items in all; at most %d' % (total, field['item']['count']['max']))
    if clone_ok and clones < 1:
        problems.add(where, 'must hold the clone ({"item": "clone", "count": n})')


def _rate_selector(problems, where, modify, donor):
    # A weapon whose type binds the rate-of-fire selector rebuilds its rate from its type's three slots: the Runtime
    # refuses a per-call rpm for it (its modes are hd2.fields.fire_rate.modes).
    if isinstance(modify, dict) and 'rpm' in modify and donor and donor.get('rateSelector'):
        problems.add(where + '.rpm', 'the %s binds the rate-of-fire selector: a per-call rpm is refused (its modes '
            'are hd2.fields.fire_rate.modes)' % donor['name'])


def _pelican_gun(problems, where, gun, fields, schema):
    for key in ('round', 'behave_as', 'rate_multiplier', 'casing', 'recoil', 'unlimited_ammo', 'face_target', 'sound'):
        if key in gun and gun[key] not in fields[key]['values']:
            problems.add(where + '.' + key, 'must be ' + ', '.join(json.dumps(v) for v in fields[key]['values'][:12])
                + (' (the pelicanSounds catalogue)' if key == 'sound' else ''))
    for key in ('rpm', 'spread', 'aim_height'):
        _number(problems, where + '.' + key, gun.get(key), fields[key])
    gatling = gun.get('behave_as') == 'gatling_sentry'
    for key, text in (('rpm', 'the Gatling AI\'s rate'), ('face_target', 'the Gatling AI\'s target'),
            ('aim_height', 'the Gatling AI\'s target')):
        if key in gun and not gatling and not (key == 'aim_height' and gun[key] == 0):
            problems.add(where + '.' + key, 'follows %s: it needs behave_as = "gatling_sentry"' % text)
    if gun.get('rate_multiplier', 1) != 1 and not gatling:
        problems.add(where + '.rate_multiplier', 'multiplies the Gatling rate: it needs behave_as = "gatling_sentry"')
    if 'rpm' in gun and gun.get('rate_multiplier', 1) != 1:
        problems.add(where + '.rpm', 'replaces the Gatling rate: no rate_multiplier')
    if gun.get('casing') == 'gatling' and not gatling:
        problems.add(where + '.casing', '"gatling" goes with behave_as = "gatling_sentry"')
    if 'impact_explosion' in gun:
        donor = _names(schema, 'pelicanExplosionDonors').get(gun['impact_explosion'])
        if not donor:
            problems.add(where + '.impact_explosion', 'must be a pelicanExplosionDonors entry')
        elif donor['kind'] == 'slow' and not (isinstance(gun.get('rpm'), (int, float))
                and gun['rpm'] <= donor['maxRpm']):
            problems.add(where + '.impact_explosion', '%s is a slow donor: it needs rpm at most %d' % (donor['name'],
                donor['maxRpm']))


def validate(project: dict, schema: dict) -> list[str]:
    """Every problem of a project, as 'where: what' lines (empty when it compiles). The Runtime checks everything again
    when the mod loads; this catches a builder's mistakes before the build."""
    problems = Problems()
    if not isinstance(project, dict):
        return ['project: must be an object']
    _only_keys(problems, 'project', project, {'format', 'log', 'stratagems'})
    if project.get('format') != FORMAT:
        problems.add('project.format', 'must be ' + FORMAT)
    if 'log' in project and not (isinstance(project['log'], str) and 0 < len(project['log']) <= 160):
        problems.add('project.log', 'must be a string of 1 to 160 characters')
    items = project.get('stratagems')
    if not isinstance(items, list) or not 1 <= len(items) <= schema['limits']['definitions']:
        problems.add('project.stratagems', 'must list 1 to %d custom stratagems' % schema['limits']['definitions'])
        return problems
    M, C = schema['metadata'], schema['carrier']
    families = _families(schema)
    stratagems = set(schema['catalogs']['stratagems'])
    carrier_families = set(schema['catalogs']['carrierFamilies'])
    seen_ids, codes = set(), []
    for index, s in enumerate(items):
        where = 'stratagems[%d]' % index
        if not _only_keys(problems, where, s, {'id', 'name', 'name_cased', 'description', 'icon', 'code', 'cooldown',
                'uses', 'traits', 'assets', 'carrier', 'payload'}):
            continue
        sid = s.get('id')
        if not (isinstance(sid, str) and re.fullmatch(M['id']['pattern'].strip('^$'), sid) and len(sid) <= M['id']['maxLength']):
            problems.add(where + '.id', 'must be 1-%d characters of a-z, 0-9 and _, starting with a letter'
                % M['id']['maxLength'])
        elif sid in seen_ids:
            problems.add(where + '.id', 'is used twice')
        seen_ids.add(sid)
        where = 'stratagems[%s]' % (sid if isinstance(sid, str) else index)
        for key in ('name', 'name_cased', 'description'):
            v = s.get(key)
            if v is None and key == 'name_cased':
                continue
            if not (isinstance(v, str) and 1 <= len(v) <= M[key]['maxLength'] and not re.search(r'[\x00-\x1f\x7f]', v)):
                problems.add(where + '.' + key, 'must be a string of 1 to %d characters' % M[key]['maxLength'])
        icon = s.get('icon')
        if not (isinstance(icon, dict) and set(icon) <= {'image', 'source'} and isinstance(icon.get('image'), str)
                and re.fullmatch(r'[a-z0-9_]{1,64}', icon['image'])
                and icon.get('source', 'images/%s.png' % icon['image']) == 'images/%s.png' % icon['image']):
            problems.add(where + '.icon', 'must be {"image": "<id>", "source": "images/<id>.png"}: the mod\'s editable '
                'PNG (the source is optional and always images/<id>.png)')
        code = s.get('code')
        directions = set(schema['catalogs']['directions'])
        if not (isinstance(code, list) and M['code']['min'] <= len(code) <= M['code']['max']
                and all(c in directions for c in code)):
            problems.add(where + '.code', 'must be %d to %d of %s' % (M['code']['min'], M['code']['max'],
                ', '.join(sorted(directions))))
        else:
            for other_id, other in codes:
                rel = _relation(code, other)
                if rel:
                    problems.add(where + '.code', 'collides with %s\'s code (%s)' % (other_id, rel))
            codes.append((sid, code))
            # The native codes, as the Runtime checks them: an equal one is refused at registration; one that starts
            # or extends a catalogued (selectable) stratagem's is refused in every mission where it can be picked.
            for native in schema['catalogs'].get('nativeCodes', []):
                rel = _relation(code, native['code'])
                if rel == 'equal' or (rel and native['catalogued']):
                    problems.add(where + '.code', '%s %s\'s native code (%s): %s' % (
                        'equals' if rel == 'equal' else 'is the start of' if len(code) < len(native['code'])
                        else 'starts with',
                        native.get('name') or 'stable id %d' % native['stableId'], ' '.join(native['code']),
                        'the game would call that stratagem instead' if rel == 'equal' else
                        'refused in every mission where it can be picked'))
        _number(problems, where + '.cooldown', s.get('cooldown'), M['cooldown'])
        _number(problems, where + '.uses', s.get('uses'), M['uses'])
        if 'traits' in s:
            traits = s['traits']
            if not (isinstance(traits, list) and len(traits) <= M['traits']['max'] and all(isinstance(t, str)
                    and 1 <= len(t) <= M['traits']['item']['maxLength'] and re.fullmatch(r'[\x20-\x7e]+', t)
                    for t in traits)):
                problems.add(where + '.traits', 'must list at most %d labels of 1 to %d printable characters (CUSTOM '
                    'STRATAGEM comes first by itself)' % (M['traits']['max'], M['traits']['item']['maxLength']))
        for k, asset in enumerate(s.get('assets') or []):
            if asset not in stratagems:
                problems.add(where + '.assets[%d]' % k, 'must name a catalogued stratagem')
        carrier = s.get('carrier')
        if not _only_keys(problems, where + '.carrier', carrier, set(C)):
            continue
        if carrier.get('beacon') not in schema['catalogs']['beacons'] and not ('group' in carrier
                and 'beacon' not in carrier):
            problems.add(where + '.carrier.beacon', 'must be ' + ', '.join(schema['catalogs']['beacons']))
        if 'slots' in carrier:
            _number(problems, where + '.carrier.slots', carrier['slots'], C['slots'])
        for key in ('prefer_families', 'allow_families'):
            for f in carrier.get(key) or []:
                if f not in carrier_families:
                    problems.add(where + '.carrier.' + key, 'unknown family ' + str(f))
        for name in carrier.get('exclude') or []:
            if name not in stratagems:
                problems.add(where + '.carrier.exclude', 'unknown stratagem ' + str(name))
        payload = s.get('payload')
        if not isinstance(payload, dict) or payload.get('family') not in families or not families[payload['family']]['builder']:
            problems.add(where + '.payload.family', 'must be one of ' + ', '.join(
                f['family'] for f in families.values() if f['builder']))
            continue
        fam = families[payload['family']]
        pw = where + '.payload'
        _family_carrier(problems, where, carrier, fam, schema, payload)
        fields = fam['fields']
        _only_keys(problems, pw, payload, set(fields) | {'family'})
        if fam['family'] == 'support':
            donors = _names(schema, 'supportDonors', lambda d: d['deliverable'])
            lst = payload.get('items')
            if not (isinstance(lst, list) and len(lst) == 1):
                problems.add(pw + '.items', 'must list exactly one donor (one native pod delivers one rack)')
                continue
            item = lst[0]
            if not _only_keys(problems, pw + '.items[0]', item, set(fields['items']['item'])):
                continue
            donor = donors.get(item.get('donor'))
            if not donor:
                problems.add(pw + '.items[0].donor', 'must be a support weapon or backpack with a reviewed pod rack')
                continue
            if 'count' in item and item['count'] != donor['count']:
                problems.add(pw + '.items[0].count', 'the %s pod holds %d; another count is not supported'
                    % (donor['name'], donor['count']))
            if 'modify' in item:
                if not donor.get('modifiable'):
                    problems.add(pw + '.items[0].modify', donor['name'] + ' delivers no weapon; no backpack field '
                        'is reviewed')
                else:
                    _weapon(problems, pw + '.items[0].modify', item['modify'], schema, 'support')
                    _rate_selector(problems, pw + '.items[0].modify', item['modify'], donor)
        elif fam['family'] == 'pod':
            _pod_items(problems, pw + '.items', payload.get('items'), schema, fields['items'], False)
        elif fam['family'] == 'expendable':
            if 'pod' in payload:
                _pod_items(problems, pw + '.pod', payload['pod'], schema, fields['pod'], True)
            if payload.get('weapon') not in _names(schema, 'cloneDonors'):
                problems.add(pw + '.weapon', 'must be a support weapon with a reviewed expendable clone class: '
                    + ', '.join(sorted(_names(schema, 'cloneDonors'))))
            if 'level' in payload and payload['level'] not in fields['level']['values']:
                problems.add(pw + '.level', 'must be ' + ', '.join(fields['level']['values']))
            pres = payload.get('presentation')
            if pres is not None and _only_keys(problems, pw + '.presentation', pres, set(fields['presentation']['fields'])):
                name = pres.get('name')
                if name is not None and not (isinstance(name, str) and 1 <= len(name) <= M['name']['maxLength']
                        and not re.search(r'[\x00-\x1f\x7f]', name)):
                    problems.add(pw + '.presentation.name', 'must be a string of 1 to %d characters, or "donor"'
                        % M['name']['maxLength'])
                icon_id = pres.get('icon')
                if icon_id is not None and not (isinstance(icon_id, str) and re.fullmatch(r'[a-z0-9_]{1,64}', icon_id)):
                    problems.add(pw + '.presentation.icon', 'must be an image id (images/<id>.png) or "donor"')
            if 'modify' in payload:
                _weapon(problems, pw + '.modify', payload['modify'], schema, 'expendable')
            if 'round' in payload:
                clone = _names(schema, 'cloneDonors').get(payload.get('weapon'))
                rounds = clone.get('rounds', []) if clone else []
                if payload['round'] not in rounds:
                    problems.add(pw + '.round', 'must be a round reviewed for the %s\'s clone: %s' % (
                        payload.get('weapon'), ', '.join(rounds) or 'none'))
                elif isinstance(payload.get('modify'), dict) and 'impact_explosion' in payload['modify']:
                    problems.add(pw + '.round', 'not with modify.impact_explosion: the round has its own explosions')
        elif fam['family'] == 'sentry':
            if payload.get('donor') not in _names(schema, 'sentryDonors', lambda d: d['supported']):
                problems.add(pw + '.donor', 'must be a catalogued sentry')
            if 'weapon' in payload:
                _weapon(problems, pw + '.weapon', payload['weapon'], schema, 'sentry')
        elif fam['family'] == 'silo':
            if payload.get('donor') not in _names(schema, 'siloDonors', lambda d: d['packageKnown']):
                problems.add(pw + '.donor', 'must be a reviewed missile silo: ' + ', '.join(sorted(_names(schema,
                    'siloDonors'))))
            blasts = _names(schema, 'blastExplosions')
            for key in ('blast', 'fallback'):
                if key in payload and payload[key] not in blasts:
                    problems.add(pw + '.' + key, 'must be a catalogued explosion whose packages are known '
                        '(catalogs.blastExplosions)')
            if 'blast' not in payload:
                problems.add(pw + '.blast', 'is required: the explosion requested where the missile detonates')
            elif payload.get('fallback') == payload['blast']:
                problems.add(pw + '.fallback', 'must be another explosion than the blast')
        elif fam['family'] == 'eagle':
            eagles = _names(schema, 'eagleDonors')
            donor = eagles.get(payload.get('donor'))
            if not donor:
                problems.add(pw + '.donor', 'must be a reviewed Eagle')
            _number(problems, pw + '.uses', payload.get('uses'), fields['uses'])
            _number(problems, pw + '.rearm_seconds', payload.get('rearm_seconds'), fields['rearm_seconds'])
            if 'payload' in payload:
                inner = payload['payload']
                if _only_keys(problems, pw + '.payload', inner, set(fields['payload']['fields'])):
                    impact = inner.get('impact_explosion')
                    if impact is not None:
                        if impact not in _names(schema, 'explosionDonors'):
                            problems.add(pw + '.payload.impact_explosion', 'must be a reviewed explosion donor')
                        elif donor and not donor['impactExplosionReplaceable']:
                            problems.add(pw + '.payload.impact_explosion', donor['name'] + '\'s strike projectile has '
                                'no impact explosion only: its impact cannot be replaced')
            if s.get('cooldown') is not None:
                problems.add(where + '.cooldown', 'an Eagle keeps its native cooldown and rearm: no cooldown')
            if s.get('uses') is not None:
                problems.add(where + '.uses', 'an Eagle\'s uses are per rearm: payload.uses')
        elif fam['family'] == 'pelican':
            _number(problems, pw + '.hover', payload.get('hover'), fields['hover'], required=True)
            for key in ('orbit', 'approach'):
                part = payload.get(key)
                if part is not None and _only_keys(problems, pw + '.' + key, part, set(fields[key]['fields'])):
                    for k, v in part.items():
                        _number(problems, pw + '.%s.%s' % (key, k), v, fields[key]['fields'][k])
            orbit = payload.get('orbit')
            if isinstance(orbit, dict) and isinstance(orbit.get('entry'), (int, float)):
                duration = orbit.get('duration', fields['orbit']['fields']['duration']['default'])
                if isinstance(duration, (int, float)) and orbit['entry'] >= duration:
                    problems.add(pw + '.orbit.entry', 'must be shorter than orbit.duration')
            gun = payload.get('gun')
            if gun is not None and _only_keys(problems, pw + '.gun', gun, set(fields['gun']['fields'])):
                _pelican_gun(problems, pw + '.gun', gun, fields['gun']['fields'], schema)
        elif fam['family'] == 'orbital' and payload.get('native') is not None:
            orbitals = _names(schema, 'orbitals')
            if payload.get('native') is not True:
                problems.add(pw + '.native', 'must be true (or absent)')
            for key in payload:
                if key not in ('family', 'native', 'pattern', 'impact_explosion'):
                    problems.add(pw + '.' + key, 'not supported with native = true: the donor\'s own barrage is used '
                        'exactly as the game reads it')
            pattern = orbitals.get(payload.get('pattern'))
            if not (pattern and pattern.get('pattern')):
                problems.add(pw + '.pattern', 'must be a reviewed orbital bombardment')
            if payload.get('impact_explosion') not in _names(schema, 'explosionDonors'):
                problems.add(pw + '.impact_explosion', 'is required with native = true: a reviewed explosion donor')
        elif fam['family'] == 'orbital':
            orbitals = _names(schema, 'orbitals')
            shell = orbitals.get(payload.get('shell'))
            if not shell:
                problems.add(pw + '.shell', 'must be a reviewed orbital')
            pattern = orbitals.get(payload.get('pattern', fields['pattern']['default']))
            if not pattern:
                problems.add(pw + '.pattern', 'must be a reviewed orbital')
            for key in ('salvos', 'shells_per_salvo', 'shell_interval', 'salvo_interval', 'scatter', 'salvo_scatter'):
                _number(problems, pw + '.' + key, payload.get(key), fields[key])
            if 'impact_explosion' in payload and payload['impact_explosion'] not in _names(schema, 'explosionDonors'):
                problems.add(pw + '.impact_explosion', 'must be a reviewed explosion donor')
            if pattern:
                total = payload.get('salvos', pattern['pattern']['salvos']) * payload.get('shells_per_salvo',
                    pattern['pattern']['shells_per_salvo'])
                if isinstance(total, (int, float)) and total > schema['limits']['orbitalShells']:
                    problems.add(pw, '%d shells in all; at most %d' % (total, schema['limits']['orbitalShells']))
    return list(problems)


# ---------------------------------------------------------------------------------------------------- compiling --
def _ordered(table: dict, order) -> tuple:
    """((key, value), ...): the known keys in their canonical order, then any other key sorted (the compiled addon is
    faithful: the Runtime refuses what it does not support, exactly as for a hand-written one)."""
    return tuple((k, table[k]) for k in order if k in table) + tuple((k, table[k]) for k in sorted(table)
        if k not in order)


WEAPON_ORDER = ('projectile', 'rpm', 'spread', 'ammo', 'recoil', 'impact_explosion', 'rounds')
PELICAN_GUN_ORDER = ('behave_as', 'rate_multiplier', 'rpm', 'round', 'casing', 'spread', 'recoil', 'unlimited_ammo',
    'face_target', 'sound', 'impact_explosion', 'aim_height')


class _Expr(str):
    # A Lua expression emitted as is (a typed handle).
    pass


def _handle(key):
    if key == 'clone':
        return 'clone'
    kind, _, name = key.partition('/')
    fn = {'support_weapon': 'hd2.support_weapon', 'backpack': 'hd2.backpack', 'player_weapon': 'hd2.weapon'}[kind]
    return _Expr('%s(%s)' % (fn, _lua_string(name)))


def _pod_lua(lst):
    out = []
    for item in lst:
        item = dict(item)
        item['item'] = _handle(item['item'])
        if isinstance(item.get('modify'), dict):
            item['modify'] = _ordered(item['modify'], WEAPON_ORDER)
        out.append(_ordered(item, ('item', 'count', 'modify', 'allow_unverified_effect')))
    return out


def _payload_lua(payload: dict) -> tuple[str, str]:
    family = payload['family']
    if family == 'support':
        items = []
        for item in payload['items']:
            item = dict(item)
            if isinstance(item.get('modify'), dict):
                item['modify'] = _ordered(item['modify'], WEAPON_ORDER)
            items.append(_ordered(item, ('donor', 'count', 'modify')))
        return 'delivery', _lua_value((('family', 'support'), ('items', items)))
    if family == 'pod':
        return 'delivery', _lua_value((('family', 'support'), ('items', _pod_lua(payload['items']))))
    body = {k: v for k, v in payload.items() if k != 'family'}
    if family == 'expendable':
        if isinstance(body.get('modify'), dict):
            body['modify'] = _ordered(body['modify'], WEAPON_ORDER)
        if isinstance(body.get('presentation'), dict):
            body['presentation'] = _ordered(body['presentation'], ('name', 'icon'))
        if isinstance(body.get('pod'), list):
            body['pod'] = _pod_lua(body['pod'])
        return 'delivery', _lua_value((('family', 'expendable'),) + _ordered(body, ('weapon', 'presentation', 'modify',
            'round', 'level', 'pod')))
    if family == 'pelican':
        for key, order in (('orbit', ('radius', 'altitude', 'duration', 'period', 'entry')),
                ('approach', ('distance', 'height')), ('gun', PELICAN_GUN_ORDER)):
            if isinstance(body.get(key), dict):
                body[key] = _ordered(body[key], order)
        return 'pelican', _lua_value(_ordered(body, ('hover', 'orbit', 'gun', 'approach')))
    if family == 'sentry':
        if isinstance(body.get('weapon'), dict):
            body['weapon'] = _ordered(body['weapon'], WEAPON_ORDER)
        return 'sentry', _lua_value(_ordered(body, ('donor', 'weapon')))
    if family == 'silo':
        return 'silo', _lua_value(_ordered(body, ('donor', 'blast', 'fallback')))
    if family == 'eagle':
        if isinstance(body.get('payload'), dict):
            body['payload'] = _ordered(body['payload'], ('impact_explosion',))
        return 'eagle', _lua_value(_ordered(body, ('donor', 'uses', 'rearm_seconds', 'payload')))
    if family == 'orbital':
        return 'orbital', _lua_value(_ordered(body, ('native', 'shell', 'pattern', 'salvos', 'shells_per_salvo',
            'shell_interval', 'salvo_interval', 'scatter', 'salvo_scatter', 'impact_explosion')))
    raise ValueError('unsupported payload family ' + str(family))


def compile_lua(project: dict, source_sha256: str = '') -> str:
    """The mod's src/addon.lua for a VALID project (validate first): deterministic, one register call per stratagem."""
    lines = [GENERATED_HEADER + ' (hd2.py custom-stratagem compile; format ' + FORMAT + ').',
        '-- Edit custom_stratagems.json, not this file: the build compiles it again.'
        + (' Source SHA-256 ' + source_sha256 + '.' if source_sha256 else ''),
        "local hd2=require('mods/skyeshade/hd2runtime')"]
    if project.get('log'):
        lines += ['local mod=hd2.mod()', 'mod:log(' + _lua_string(project['log']) + ')']
    for s in project['stratagems']:
        body = [('id', s['id']), ('name', s['name'])]
        if 'name_cased' in s:
            body.append(('name_cased', s['name_cased']))
        body.append(('description', s['description']))
        lines.append('hd2.custom_stratagem.register({')
        for k, v in body:
            lines.append('    %s=%s,' % (k, _lua_value(v)))
        lines.append('    icon=hd2.resources.image(%s),' % _lua_string(s['icon']['image']))
        lines.append('    code=%s,' % _lua_value(s['code']))
        if s.get('cooldown') is not None:
            lines.append('    cooldown=%s,' % _lua_value(s['cooldown']))
        if s.get('uses') is not None:
            lines.append('    uses=%s,' % _lua_value(s['uses']))
        if s.get('traits'):
            lines.append('    traits=%s,' % _lua_value(s['traits']))
        carrier = s['carrier']
        lines.append('    carrier=%s,' % _lua_value(_ordered(carrier, ('group', 'slots', 'beacon', 'prefer_families',
            'allow_families', 'exclude'))))
        key, value = _payload_lua(s['payload'])
        lines.append('    %s=%s,' % (key, value))
        if s.get('assets'):
            lines.append('    assets=%s,' % _lua_value(s['assets']))
        lines.append('})')
    return '\n'.join(lines) + '\n'


def compile_project(project_dir, sdk: Path | None = None, write: bool = True) -> dict:
    """Validates <project>/custom_stratagems.json and (write) compiles it into <project>/src/addon.lua. Refuses to
    overwrite a hand-written addon (no GENERATED_HEADER). Returns {source, sha256, addon, ids, images, written}; raises
    ValueError with every problem."""
    project_dir = Path(project_dir)
    source = project_dir / PROJECT_FILE
    raw = source.read_bytes()
    project = json.loads(raw.decode('utf-8-sig'))
    schema = load_schema(sdk)
    problems = validate(project, schema)
    for s in project.get('stratagems') or []:
        image = isinstance(s, dict) and isinstance(s.get('icon'), dict) and s['icon'].get('image')
        if isinstance(image, str) and not (project_dir / 'images' / (image + '.png')).is_file():
            problems.append('stratagems[%s].icon: images/%s.png is missing (the build compiles it into the mod)'
                % (s.get('id'), image))
        payload = isinstance(s, dict) and s.get('payload')
        pres = isinstance(payload, dict) and payload.get('family') == 'expendable' and payload.get('presentation')
        weapon_icon = isinstance(pres, dict) and pres.get('icon')
        if isinstance(weapon_icon, str) and weapon_icon != 'donor' \
                and not (project_dir / 'images' / (weapon_icon + '.png')).is_file():
            problems.append('stratagems[%s].payload.presentation.icon: images/%s.png is missing (the build compiles it '
                'into the mod)' % (s.get('id'), weapon_icon))
    if problems:
        raise ValueError('custom_stratagems.json is not valid:\n  ' + '\n  '.join(problems))
    sha = hashlib.sha256(raw).hexdigest()
    addon = project_dir / 'src/addon.lua'
    if addon.exists() and not addon.read_text(encoding='utf-8-sig').startswith(GENERATED_HEADER):
        raise ValueError('src/addon.lua is hand-written (no generated header): it is never overwritten; remove it or '
            'remove custom_stratagems.json')
    text = compile_lua(project, sha)
    written = False
    if write and (not addon.exists() or addon.read_text(encoding='utf-8-sig') != text):
        addon.parent.mkdir(parents=True, exist_ok=True)
        addon.write_text(text, encoding='utf-8', newline='\n')
        written = True
    return {'source': PROJECT_FILE, 'sha256': sha, 'addon': 'src/addon.lua', 'written': written,
        'ids': [s['id'] for s in project['stratagems']],
        'images': sorted({s['icon']['image'] for s in project['stratagems']} | {
            s['payload']['presentation']['icon'] for s in project['stratagems']
            if s['payload'].get('family') == 'expendable' and isinstance(s['payload'].get('presentation'), dict)
            and s['payload']['presentation'].get('icon') not in (None, 'donor')})}
