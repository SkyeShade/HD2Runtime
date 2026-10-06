"""Settings tables (projectile, damage, explosion, arc, beam) with flattened members (research only).

Each decoded settings file holds groups of one record type each; a row's first u32 is its native type id
(ProjectileType, DamageInfoType, ExplosionType, ...). ``SettingsView`` exposes the primary group of each kind (the
group native links point into) through the same flattened ``Member`` paths as component tables, so a family
comparison works on settings rows too (``rows_family``).
"""
from __future__ import annotations

from scan.tables import EntityTables, decode
from migration.build_view import SETTINGS_FILES, TypeLibrary, parse_settings, BuildView


class SettingsView:
    def __init__(self, tables: EntityTables):
        self.tables = tables
        self.view = BuildView()
        library = TypeLibrary(tables.typelib_bytes)
        for kind, name in SETTINGS_FILES.items():
            path = tables.folder / name
            if path.is_file():
                parse_settings(self.view, kind, path.read_bytes(), library)

    def kinds(self) -> list[str]:
        return sorted(self.view.settings)

    def table(self, kind: str):
        return self.view.settings[kind]

    def members(self, kind: str):
        return self.tables.flatten(self.table(kind).layout.type_hash)

    def row(self, kind: str, native_type: int) -> bytes | None:
        rows = self.table(kind).row_for_type(native_type)
        if len(rows) > 1:
            raise ValueError(f'{kind} type {native_type} has {len(rows)} rows')
        return rows[0][1] if rows else None

    def decode(self, kind: str, native_type: int) -> dict | None:
        raw = self.row(kind, native_type)
        if raw is None:
            return None
        return {member.path: decode(member, raw) for member in self.members(kind)}

    def rows_family(self, kind: str, types: dict[str, int]) -> dict[str, dict]:
        """label -> decoded row, for a labelled set of native types (compare them with compare.partition)."""
        return {label: self.decode(kind, native_type) for label, native_type in types.items()}
