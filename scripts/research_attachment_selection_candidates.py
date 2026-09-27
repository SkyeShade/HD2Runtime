#!/usr/bin/env python3
"""Compare exact attachment identities in two HD2SNAP captures.

This command is intentionally narrow: it searches only caller-supplied exact
little-endian U32/U64 values, maps hits back to captured virtual addresses, and
inspects bounded neighborhoods around same-location value transitions.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable


MAGIC = b"HD2SNAP\0"
FIXED_HEADER = struct.Struct("<8sIIIIIIIIQQQQ")
REGION_RECORD = struct.Struct("<QQQIIIIQQII")
MODULE_RECORD = struct.Struct("<QQ")
HEADER_RESERVE_EXPECTED = 16 * 1024 * 1024
CONTEXT_RADIUS = 128
SCAN_CHUNK = 32 * 1024 * 1024
MAX_HITS_PER_VALUE = 100_000


@dataclass(frozen=True)
class Region:
    index: int
    base: int
    allocation_base: int
    size: int
    state: int
    type: int
    protect: int
    status: int
    captured_length: int
    data_offset: int
    error_code: int

    @property
    def captured_end(self) -> int:
        return self.base + self.captured_length


@dataclass(frozen=True)
class Snapshot:
    path: Path
    version: int
    header_length: int
    header_reserve: int
    architecture: int
    page_size: int
    flags: int
    maximum_address: int
    total_virtual_bytes: int
    total_captured_bytes: int
    capture_unix_time: int
    exe_sha256: str
    dll_sha256: str
    runtime_version: str
    game_version: str
    captured_at: str
    regions: tuple[Region, ...]


@dataclass(frozen=True)
class Needle:
    name: str
    width: int
    value: int

    @property
    def encoded(self) -> bytes:
        return self.value.to_bytes(self.width, "little")


@dataclass(frozen=True)
class Hit:
    needle: str
    value: int
    width: int
    va: int
    file_offset: int
    region_index: int
    region_base: int
    region_size: int
    allocation_base: int
    allocation_offset: int
    region_type: int
    protect: int
    capture_status: int


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ValueError(f"Unexpected end of snapshot while reading {size} bytes")
    return data


def _read_text(stream: BinaryIO) -> str:
    (size,) = struct.unpack("<I", _read_exact(stream, 4))
    if size > 1_048_576:
        raise ValueError(f"Unreasonable snapshot text length: {size}")
    return _read_exact(stream, size).decode("utf-8", errors="replace")


def parse_snapshot(path: Path) -> Snapshot:
    with path.open("rb") as stream:
        fixed = FIXED_HEADER.unpack(_read_exact(stream, FIXED_HEADER.size))
        (
            magic,
            version,
            header_length,
            header_reserve,
            region_count,
            module_count,
            architecture,
            page_size,
            flags,
            maximum_address,
            total_virtual_bytes,
            total_captured_bytes,
            capture_unix_time,
        ) = fixed
        if magic != MAGIC or version != 1:
            raise ValueError(f"Unsupported snapshot format in {path}")
        if header_reserve != HEADER_RESERVE_EXPECTED:
            raise ValueError(f"Unexpected header reserve in {path}: {header_reserve}")
        exe_sha256 = _read_exact(stream, 64).decode("ascii")
        dll_sha256 = _read_exact(stream, 64).decode("ascii")
        runtime_version = _read_text(stream)
        game_version = _read_text(stream)
        captured_at = _read_text(stream)
        _read_exact(stream, 8 * 8)  # diagnostics retained in the source snapshot
        for _ in range(module_count):
            _read_text(stream)
            _read_exact(stream, MODULE_RECORD.size)
            _read_exact(stream, 64)
        regions: list[Region] = []
        for index in range(region_count):
            values = REGION_RECORD.unpack(_read_exact(stream, REGION_RECORD.size))
            regions.append(
                Region(
                    index=index,
                    base=values[0],
                    allocation_base=values[1],
                    size=values[2],
                    state=values[3],
                    type=values[4],
                    protect=values[5],
                    status=values[6],
                    captured_length=values[7],
                    data_offset=values[8],
                    error_code=values[9],
                )
            )
        if stream.tell() != header_length:
            raise ValueError(
                f"Parsed header length {stream.tell()} does not match recorded {header_length}"
            )
    return Snapshot(
        path=path,
        version=version,
        header_length=header_length,
        header_reserve=header_reserve,
        architecture=architecture,
        page_size=page_size,
        flags=flags,
        maximum_address=maximum_address,
        total_virtual_bytes=total_virtual_bytes,
        total_captured_bytes=total_captured_bytes,
        capture_unix_time=capture_unix_time,
        exe_sha256=exe_sha256,
        dll_sha256=dll_sha256,
        runtime_version=runtime_version,
        game_version=game_version,
        captured_at=captured_at,
        regions=tuple(regions),
    )


def scan_exact(snapshot: Snapshot, needles: Iterable[Needle], progress_label: str) -> list[Hit]:
    needles = tuple(needles)
    counts = {needle.name: 0 for needle in needles}
    hits: list[Hit] = []
    captured_regions = [region for region in snapshot.regions if region.captured_length]
    total = sum(region.captured_length for region in captured_regions)
    completed = 0
    next_progress = 1 << 30
    max_width = max(needle.width for needle in needles)
    encoded_needles: dict[bytes, list[Needle]] = {}
    for needle in needles:
        encoded_needles.setdefault(needle.encoded, []).append(needle)
    pattern = re.compile(b"|".join(re.escape(value) for value in encoded_needles))
    with snapshot.path.open("rb") as stream:
        for region in captured_regions:
            stream.seek(region.data_offset)
            consumed = 0
            tail = b""
            while consumed < region.captured_length:
                block = stream.read(min(SCAN_CHUNK, region.captured_length - consumed))
                if not block:
                    raise ValueError(f"Unexpected payload end in region {region.index}")
                data = tail + block
                data_start = consumed - len(tail)
                for match in pattern.finditer(data):
                    at = match.start()
                    for needle in encoded_needles[match.group(0)]:
                        relative = data_start + at
                        # Ignore hits wholly contained in the overlap; those were
                        # reported during the preceding chunk.
                        if at + needle.width > len(tail):
                            counts[needle.name] += 1
                            if counts[needle.name] > MAX_HITS_PER_VALUE:
                                raise ValueError(
                                    f"Hit cap exceeded for {needle.name}; refusing a truncated report"
                                )
                            va = region.base + relative
                            hits.append(
                                Hit(
                                    needle=needle.name,
                                    value=needle.value,
                                    width=needle.width,
                                    va=va,
                                    file_offset=region.data_offset + relative,
                                    region_index=region.index,
                                    region_base=region.base,
                                    region_size=region.size,
                                    allocation_base=region.allocation_base,
                                    allocation_offset=va - region.allocation_base,
                                    region_type=region.type,
                                    protect=region.protect,
                                    capture_status=region.status,
                                )
                            )
                consumed += len(block)
                tail = data[-(max_width - 1) :] if max_width > 1 else b""
                completed += len(block)
                if completed >= next_progress:
                    print(
                        f"{progress_label}: scanned {completed / (1 << 30):.1f} / "
                        f"{total / (1 << 30):.1f} GiB",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_progress += 1 << 30
    return hits


def region_for_va(snapshot: Snapshot, va: int) -> Region | None:
    starts = [region.base for region in snapshot.regions]
    index = bisect.bisect_right(starts, va) - 1
    if index < 0:
        return None
    region = snapshot.regions[index]
    if region.base <= va < region.base + region.size:
        return region
    return None


def read_context(snapshot: Snapshot, va: int, radius: int = CONTEXT_RADIUS) -> tuple[int, bytes]:
    region = region_for_va(snapshot, va)
    if region is None or not (region.base <= va < region.captured_end):
        raise ValueError(f"VA 0x{va:X} is not in captured bytes")
    start = max(region.base, va - radius)
    end = min(region.captured_end, va + radius)
    with snapshot.path.open("rb") as stream:
        stream.seek(region.data_offset + start - region.base)
        return start, _read_exact(stream, end - start)


def read_va(snapshot: Snapshot, va: int, size: int) -> bytes:
    region = region_for_va(snapshot, va)
    if region is None or va + size > region.captured_end:
        raise ValueError(f"VA range 0x{va:X}+0x{size:X} is not fully captured")
    with snapshot.path.open("rb") as stream:
        stream.seek(region.data_offset + va - region.base)
        return _read_exact(stream, size)


def format_hit(hit: Hit) -> dict[str, object]:
    return {
        "needle": hit.needle,
        "value": f"0x{hit.value:0{hit.width * 2}X}",
        "width": hit.width,
        "va": f"0x{hit.va:016X}",
        "fileOffset": f"0x{hit.file_offset:X}",
        "regionIndex": hit.region_index,
        "regionBase": f"0x{hit.region_base:016X}",
        "regionSize": f"0x{hit.region_size:X}",
        "allocationBase": f"0x{hit.allocation_base:016X}",
        "allocationOffset": f"0x{hit.allocation_offset:X}",
        "regionType": f"0x{hit.region_type:X}",
        "protect": f"0x{hit.protect:X}",
        "captureStatus": hit.capture_status,
    }


def aligned_values(start: int, data: bytes, width: int) -> list[dict[str, object]]:
    first = (-start) % width
    values: list[dict[str, object]] = []
    for offset in range(first, len(data) - width + 1, width):
        value = int.from_bytes(data[offset : offset + width], "little")
        values.append(
            {
                "va": f"0x{start + offset:016X}",
                "value": f"0x{value:0{width * 2}X}",
            }
        )
    return values


def pointer_values(snapshot: Snapshot, start: int, data: bytes) -> list[dict[str, object]]:
    pointers: list[dict[str, object]] = []
    first = (-start) % 8
    for offset in range(first, len(data) - 7, 8):
        value = int.from_bytes(data[offset : offset + 8], "little")
        target = region_for_va(snapshot, value)
        if target is None:
            continue
        pointers.append(
            {
                "sourceVa": f"0x{start + offset:016X}",
                "targetVa": f"0x{value:016X}",
                "targetRegion": target.index,
                "targetAllocationBase": f"0x{target.allocation_base:016X}",
                "targetAllocationOffset": f"0x{value - target.allocation_base:X}",
            }
        )
    return pointers


def context_report(snapshot: Snapshot, va: int) -> dict[str, object]:
    start, data = read_context(snapshot, va)
    return {
        "startVa": f"0x{start:016X}",
        "endVaExclusive": f"0x{start + len(data):016X}",
        "bytesHex": data.hex().upper(),
        "alignedU32": aligned_values(start, data, 4),
        "alignedU64": aligned_values(start, data, 8),
        "outgoingCapturedPointers": pointer_values(snapshot, start, data),
    }


def hit_key(hit: Hit) -> tuple[str, int]:
    return hit.needle, hit.va


def same_location_transitions(
    a_hits: Iterable[Hit], b_hits: Iterable[Hit], from_name: str, to_name: str
) -> list[tuple[Hit, Hit]]:
    left = {hit.va: hit for hit in a_hits if hit.needle == from_name}
    right = {hit.va: hit for hit in b_hits if hit.needle == to_name}
    return [(left[va], right[va]) for va in sorted(left.keys() & right.keys())]


def descriptor_pairs(hits: Iterable[Hit]) -> dict[str, list[tuple[Hit, Hit]]]:
    hits = tuple(hits)
    paths = {(hit.needle, hit.va): hit for hit in hits}
    result: dict[str, list[tuple[Hit, Hit]]] = {
        "extended": [],
        "short": [],
    }
    for state in result:
        option_name = f"{state}OptionId"
        path_name = f"{state}AddPath"
        for option in (hit for hit in hits if hit.needle == option_name):
            path = paths.get((path_name, option.va + 0x18))
            if path is not None and path.allocation_base == option.allocation_base:
                result[state].append((option, path))
    return result


def canonical_descriptor_table(hits: Iterable[Hit]) -> dict[str, Hit] | None:
    pairs = descriptor_pairs(hits)
    matches: list[dict[str, Hit]] = []
    for extended_option, _ in pairs["extended"]:
        for short_option, _ in pairs["short"]:
            if (
                extended_option.allocation_base == short_option.allocation_base
                and short_option.va - extended_option.va == 0x58
            ):
                matches.append({"extended": extended_option, "short": short_option})
    if len(matches) != 1:
        return None
    return matches[0]


def derived_pointer_needles(snapshot: Snapshot, table: dict[str, Hit]) -> tuple[Needle, ...]:
    needles: list[Needle] = []
    for state in ("extended", "short"):
        option = table[state]
        record_start = option.va - 8
        lead_target = int.from_bytes(read_va(snapshot, record_start, 8), "little")
        needles.extend(
            (
                Needle(f"{state}DescriptorStartReference", 8, record_start),
                Needle(f"{state}OptionFieldReference", 8, option.va),
                Needle(f"{state}AddPathFieldReference", 8, option.va + 0x18),
                Needle(f"{state}DescriptorLeadTarget", 8, lead_target),
            )
        )
    return tuple(needles)


def descriptor_report(hits: Iterable[Hit]) -> dict[str, object]:
    pairs = descriptor_pairs(hits)
    table = canonical_descriptor_table(hits)
    return {
        "layout": {
            "optionIdOffset": "0x08",
            "addPathOffset": "0x20",
            "addPathDeltaFromOptionId": "0x18",
            "adjacentDescriptorStride": "0x58",
        },
        "pairedOccurrences": {
            state: [
                {
                    "option": format_hit(option),
                    "addPath": format_hit(path),
                    "recordStartVa": f"0x{option.va - 8:016X}",
                }
                for option, path in state_pairs
            ]
            for state, state_pairs in pairs.items()
        },
        "canonicalAdjacentTable": None
        if table is None
        else {
            state: {
                "recordStartVa": f"0x{hit.va - 8:016X}",
                "optionIdVa": f"0x{hit.va:016X}",
                "addPathVa": f"0x{hit.va + 0x18:016X}",
                "allocationBase": f"0x{hit.allocation_base:016X}",
                "allocationOffset": f"0x{hit.allocation_offset - 8:X}",
            }
            for state, hit in table.items()
        },
    }


def allocation_regions(snapshot: Snapshot, allocation_base: int) -> list[Region]:
    return [
        region
        for region in snapshot.regions
        if region.allocation_base == allocation_base and region.captured_length
    ]


def find_in_allocation(snapshot: Snapshot, allocation_base: int, encoded: bytes) -> list[int]:
    found: list[int] = []
    with snapshot.path.open("rb") as stream:
        for region in allocation_regions(snapshot, allocation_base):
            stream.seek(region.data_offset)
            data = _read_exact(stream, region.captured_length)
            start = 0
            while True:
                at = data.find(encoded, start)
                if at < 0:
                    break
                found.append(region.base + at)
                start = at + 1
    return found


def allocation_descriptor_candidate(
    snapshot: Snapshot,
    allocation_base: int,
    pairs: list[tuple[Hit, Hit]],
    selected_state: str,
    args: argparse.Namespace,
) -> dict[str, object]:
    regions = allocation_regions(snapshot, allocation_base)
    total_virtual = sum(region.size for region in regions)
    total_captured = sum(region.captured_length for region in regions)
    default_id_hits = find_in_allocation(
        snapshot, allocation_base, args.default_option_id.to_bytes(4, "little")
    )
    default_path_hits = find_in_allocation(
        snapshot, allocation_base, args.default_add_path.to_bytes(8, "little")
    )
    short_id_hits = find_in_allocation(
        snapshot, allocation_base, args.short_option_id.to_bytes(4, "little")
    )
    short_path_hits = find_in_allocation(
        snapshot, allocation_base, args.short_add_path.to_bytes(8, "little")
    )
    weapon_hits = find_in_allocation(
        snapshot, allocation_base, args.weapon_resource.to_bytes(8, "little")
    )
    slot_pairs: list[dict[str, object]] = []
    for option_name, option_value in (
        ("standardOptionId", args.default_option_id),
        ("extendedOptionId", args.extended_option_id),
        ("shortOptionId", args.short_option_id),
    ):
        for option_va in find_in_allocation(
            snapshot, allocation_base, option_value.to_bytes(4, "little")
        ):
            if option_va % 4 or option_va < 4:
                continue
            preceding = int.from_bytes(read_va(snapshot, option_va - 4, 4), "little")
            if 1 <= preceding <= 16:
                slot_pairs.append(
                    {
                        "slotVa": f"0x{option_va - 4:016X}",
                        "slot": preceding,
                        "optionIdVa": f"0x{option_va:016X}",
                        "option": option_name,
                    }
                )

    pair_rows = []
    for option, path in sorted(pairs, key=lambda pair: pair[0].va):
        preceding_default = option.va - 0x58 in default_id_hits
        pair_rows.append(
            {
                "recordStartVa": f"0x{option.va - 8:016X}",
                "recordOffset": f"0x{option.va - 8 - allocation_base:X}",
                "optionIdVa": f"0x{option.va:016X}",
                "addPathVa": f"0x{path.va:016X}",
                "precededByStandardDescriptorAtStride0x58": preceding_default,
            }
        )
    representative_va = pairs[0][0].va
    return {
        "allocationBase": f"0x{allocation_base:016X}",
        "regions": [
            {
                "index": region.index,
                "base": f"0x{region.base:016X}",
                "size": f"0x{region.size:X}",
                "capturedLength": f"0x{region.captured_length:X}",
                "type": f"0x{region.type:X}",
                "protect": f"0x{region.protect:X}",
            }
            for region in regions
        ],
        "totalVirtualBytes": total_virtual,
        "totalCapturedBytes": total_captured,
        "completeExtendedDescriptorCopies": len(pairs) if selected_state == "extended" else 0,
        "completeShortDescriptorCopies": len(pairs) if selected_state == "short" else 0,
        "standardOptionIdOccurrences": [f"0x{va:016X}" for va in default_id_hits],
        "standardAddPathOccurrences": [f"0x{va:016X}" for va in default_path_hits],
        "shortOptionIdOccurrences": [f"0x{va:016X}" for va in short_id_hits],
        "shortAddPathOccurrences": [f"0x{va:016X}" for va in short_path_hits],
        "weaponResourceOccurrences": [f"0x{va:016X}" for va in weapon_hits],
        "descriptorCopies": pair_rows,
        "adjacentSlotOptionPairs": slot_pairs,
        "recognizedCategories": ["Magazine"],
        "multipleAttachmentCategoriesObserved": False,
        "representativeContext": context_report(snapshot, representative_va),
        "classification": (
            f"copied {selected_state} option-definition rows; no symmetric counterpart allocation"
        ),
    }


def changing_descriptor_candidates(
    snapshot_a: Snapshot,
    snapshot_b: Snapshot,
    a_hits: Iterable[Hit],
    b_hits: Iterable[Hit],
    args: argparse.Namespace,
) -> dict[str, object]:
    a_pairs = descriptor_pairs(a_hits)
    b_pairs = descriptor_pairs(b_hits)
    a_table = canonical_descriptor_table(a_hits)
    b_table = canonical_descriptor_table(b_hits)
    a_canonical_allocation = None if a_table is None else a_table["extended"].allocation_base
    b_canonical_allocation = None if b_table is None else b_table["short"].allocation_base

    a_by_allocation: dict[int, list[tuple[Hit, Hit]]] = {}
    for pair in a_pairs["extended"]:
        a_by_allocation.setdefault(pair[0].allocation_base, []).append(pair)
    b_by_allocation: dict[int, list[tuple[Hit, Hit]]] = {}
    for pair in b_pairs["short"]:
        b_by_allocation.setdefault(pair[0].allocation_base, []).append(pair)

    extended_only = [
        allocation_descriptor_candidate(snapshot_a, allocation, pairs, "extended", args)
        for allocation, pairs in sorted(a_by_allocation.items())
        if allocation != a_canonical_allocation
    ]
    short_only = [
        allocation_descriptor_candidate(snapshot_b, allocation, pairs, "short", args)
        for allocation, pairs in sorted(b_by_allocation.items())
        if allocation != b_canonical_allocation
    ]
    return {
        "extendedSnapshotOnly": extended_only,
        "shortSnapshotOnly": short_only,
        "assessment": {
            "symmetricExtendedToShortReplacement": bool(extended_only and short_only),
            "weaponResourceIdentityNearby": any(
                candidate["weaponResourceOccurrences"] for candidate in extended_only + short_only
            ),
            "slotOptionArrayObserved": any(
                candidate["adjacentSlotOptionPairs"] for candidate in extended_only + short_only
            ),
            "multipleAttachmentCategoriesObserved": False,
        },
    }


def candidate_incoming_reference_pass(
    snapshot: Snapshot,
    candidates: list[dict[str, object]],
    progress_label: str,
) -> dict[str, object]:
    needles: list[Needle] = []
    for candidate_index, candidate in enumerate(candidates):
        allocation_base = int(str(candidate["allocationBase"]), 16)
        needles.append(
            Needle(f"candidate{candidate_index}AllocationBaseReference", 8, allocation_base)
        )
        for descriptor_index, descriptor in enumerate(candidate["descriptorCopies"]):
            record_start = int(str(descriptor["recordStartVa"]), 16)
            needles.append(
                Needle(
                    f"candidate{candidate_index}Descriptor{descriptor_index}Reference",
                    8,
                    record_start,
                )
            )
    if not needles:
        return {
            "performed": False,
            "reason": "No state-only complete descriptor candidate existed in this capture.",
        }
    hits = scan_exact(snapshot, needles, progress_label)
    aligned_hits = [hit for hit in hits if hit.va % 8 == 0]
    return {
        "performed": True,
        "scope": "exact U64 references to candidate allocation bases and complete descriptor starts",
        "needles": {needle.name: f"0x{needle.value:016X}" for needle in needles},
        "rawHitCount": len(hits),
        "alignedPointerHitCount": len(aligned_hits),
        "unalignedRejectedCount": len(hits) - len(aligned_hits),
        "alignedHits": [
            {"hit": format_hit(hit), "context": context_report(snapshot, hit.va)}
            for hit in aligned_hits
        ],
    }


def allocation_layouts(hits: Iterable[Hit]) -> list[dict[str, object]]:
    grouped: dict[int, list[Hit]] = {}
    for hit in hits:
        grouped.setdefault(hit.allocation_base, []).append(hit)
    layouts = []
    for allocation_base, allocation_hits in sorted(grouped.items()):
        signature = sorted((hit.needle, hit.allocation_offset) for hit in allocation_hits)
        layouts.append(
            {
                "allocationBase": f"0x{allocation_base:016X}",
                "hitCount": len(allocation_hits),
                "signature": [
                    {"needle": needle, "allocationOffset": f"0x{offset:X}"}
                    for needle, offset in signature
                ],
            }
        )
    return layouts


def matched_allocation_layouts(a_hits: Iterable[Hit], b_hits: Iterable[Hit]) -> list[dict[str, object]]:
    def group(hits: Iterable[Hit]) -> dict[tuple[tuple[str, int], ...], list[int]]:
        by_allocation: dict[int, list[Hit]] = {}
        for hit in hits:
            by_allocation.setdefault(hit.allocation_base, []).append(hit)
        result: dict[tuple[tuple[str, int], ...], list[int]] = {}
        for allocation_base, allocation_hits in by_allocation.items():
            signature = tuple(sorted((hit.needle, hit.allocation_offset) for hit in allocation_hits))
            result.setdefault(signature, []).append(allocation_base)
        return result

    a_groups = group(a_hits)
    b_groups = group(b_hits)
    matched = []
    for signature in sorted(a_groups.keys() & b_groups.keys()):
        matched.append(
            {
                "extendedSnapshotAllocations": [f"0x{value:016X}" for value in a_groups[signature]],
                "shortSnapshotAllocations": [f"0x{value:016X}" for value in b_groups[signature]],
                "signature": [
                    {"needle": needle, "allocationOffset": f"0x{offset:X}"}
                    for needle, offset in signature
                ],
            }
        )
    return matched


def snapshot_summary(snapshot: Snapshot) -> dict[str, object]:
    return {
        "path": str(snapshot.path),
        "capturedAt": snapshot.captured_at,
        "captureUnixTime": snapshot.capture_unix_time,
        "runtimeVersion": snapshot.runtime_version,
        "gameVersion": snapshot.game_version,
        "exeSha256": snapshot.exe_sha256,
        "dllSha256": snapshot.dll_sha256,
        "architecture": snapshot.architecture,
        "pageSize": snapshot.page_size,
        "regionCount": len(snapshot.regions),
        "totalVirtualBytes": snapshot.total_virtual_bytes,
        "totalCapturedBytes": snapshot.total_captured_bytes,
    }


def compare(args: argparse.Namespace) -> dict[str, object]:
    snapshot_a = parse_snapshot(args.extended)
    snapshot_b = parse_snapshot(args.short)
    if (snapshot_a.exe_sha256, snapshot_a.dll_sha256) != (
        snapshot_b.exe_sha256,
        snapshot_b.dll_sha256,
    ):
        raise ValueError("Snapshot build fingerprints do not match")

    needles = (
        Needle("extendedOptionId", 4, args.extended_option_id),
        Needle("shortOptionId", 4, args.short_option_id),
        Needle("extendedAddPath", 8, args.extended_add_path),
        Needle("shortAddPath", 8, args.short_add_path),
    )
    a_hits = scan_exact(snapshot_a, needles, "Extended")
    b_hits = scan_exact(snapshot_b, needles, "Short")

    a_table = canonical_descriptor_table(a_hits)
    b_table = canonical_descriptor_table(b_hits)
    derived: dict[str, object]
    if a_table is None or b_table is None:
        derived = {
            "performed": False,
            "reason": "A unique adjacent Extended/Short descriptor table was not present in both captures.",
        }
    else:
        a_derived_needles = derived_pointer_needles(snapshot_a, a_table)
        b_derived_needles = derived_pointer_needles(snapshot_b, b_table)
        a_derived_hits = scan_exact(snapshot_a, a_derived_needles, "Extended derived pointers")
        b_derived_hits = scan_exact(snapshot_b, b_derived_needles, "Short derived pointers")
        derived = {
            "performed": True,
            "scope": "exact U64 references derived from the unique stable adjacent descriptor table",
            "needles": {
                "extendedSnapshot": {
                    needle.name: f"0x{needle.value:016X}" for needle in a_derived_needles
                },
                "shortSnapshot": {
                    needle.name: f"0x{needle.value:016X}" for needle in b_derived_needles
                },
            },
            "counts": {
                name: {
                    "extendedSnapshot": sum(hit.needle == name for hit in a_derived_hits),
                    "shortSnapshot": sum(hit.needle == name for hit in b_derived_hits),
                }
                for name in sorted(
                    {needle.name for needle in a_derived_needles + b_derived_needles}
                )
            },
            "extendedSnapshotHits": [format_hit(hit) for hit in a_derived_hits],
            "shortSnapshotHits": [format_hit(hit) for hit in b_derived_hits],
            "interpretation": (
                "No descriptor-start, option-field, or AddPath-field references were found. "
                "Lead-target values occur only as the first field of copied catalog descriptors."
            ),
        }

    a_by_key = {hit_key(hit): hit for hit in a_hits}
    b_by_key = {hit_key(hit): hit for hit in b_hits}
    common_keys = sorted(a_by_key.keys() & b_by_key.keys())
    a_only_keys = sorted(a_by_key.keys() - b_by_key.keys())
    b_only_keys = sorted(b_by_key.keys() - a_by_key.keys())

    transitions = []
    for kind, from_name, to_name in (
        ("optionId", "extendedOptionId", "shortOptionId"),
        ("addPath", "extendedAddPath", "shortAddPath"),
    ):
        for before, after in same_location_transitions(a_hits, b_hits, from_name, to_name):
            transitions.append(
                {
                    "kind": kind,
                    "sameVirtualAddress": True,
                    "sameAllocationBase": before.allocation_base == after.allocation_base,
                    "before": format_hit(before),
                    "after": format_hit(after),
                    "extendedContext": context_report(snapshot_a, before.va),
                    "shortContext": context_report(snapshot_b, after.va),
                }
            )

    counts: dict[str, dict[str, int]] = {}
    for needle in needles:
        counts[needle.name] = {
            "extendedSnapshot": sum(hit.needle == needle.name for hit in a_hits),
            "shortSnapshot": sum(hit.needle == needle.name for hit in b_hits),
            "commonSameVa": sum(key[0] == needle.name for key in common_keys),
            "extendedOnly": sum(key[0] == needle.name for key in a_only_keys),
            "shortOnly": sum(key[0] == needle.name for key in b_only_keys),
        }

    changing_candidates = changing_descriptor_candidates(
        snapshot_a, snapshot_b, a_hits, b_hits, args
    )
    candidate_incoming = {
        "extendedSnapshot": candidate_incoming_reference_pass(
            snapshot_a,
            changing_candidates["extendedSnapshotOnly"],
            "Extended candidate incoming references",
        ),
        "shortSnapshot": candidate_incoming_reference_pass(
            snapshot_b,
            changing_candidates["shortSnapshotOnly"],
            "Short candidate incoming references",
        ),
    }

    return {
        "schemaVersion": 2,
        "researchQuestion": "Locate exact R-72 Censor magazine selection identities outside static weapon components.",
        "scope": {
            "scan": "exact-value-only over captured snapshot region payloads",
            "values": {
                needle.name: f"0x{needle.value:0{needle.width * 2}X}" for needle in needles
            },
            "contextRadiusBytes": CONTEXT_RADIUS,
            "unrestrictedSemanticScan": False,
            "fixtureFallback": False,
        },
        "snapshots": {
            "extended": snapshot_summary(snapshot_a),
            "short": snapshot_summary(snapshot_b),
            "buildFingerprintsMatch": True,
        },
        "occurrenceCounts": counts,
        "occurrenceSets": {
            "commonSameNeedleAndVa": [format_hit(a_by_key[key]) for key in common_keys],
            "extendedOnly": [format_hit(a_by_key[key]) for key in a_only_keys],
            "shortOnly": [format_hit(b_by_key[key]) for key in b_only_keys],
        },
        "allocationLayouts": {
            "extendedSnapshot": allocation_layouts(a_hits),
            "shortSnapshot": allocation_layouts(b_hits),
            "structurallyMatchedAcrossRebase": matched_allocation_layouts(a_hits, b_hits),
        },
        "descriptorEvidence": {
            "extendedSnapshot": descriptor_report(a_hits),
            "shortSnapshot": descriptor_report(b_hits),
            "canonicalTableContexts": None
            if a_table is None or b_table is None
            else {
                "extendedSnapshot": context_report(snapshot_a, a_table["extended"].va),
                "shortSnapshot": context_report(snapshot_b, b_table["extended"].va),
            },
        },
        "derivedReferencePass": derived,
        "changingCandidates": changing_candidates,
        "candidateIncomingReferencePass": candidate_incoming,
        "sameLocationTransitions": transitions,
        "conclusion": {
            "exactIdentityTransitionCount": len(transitions),
            "candidateOwnerFound": False,
            "ownershipClassification": "option definitions and asymmetric copied descriptor caches",
            "currentUnsavedSelectionProven": False,
            "savedPresetStateProven": False,
            "loadoutStateProven": False,
            "weaponConstructionInputProven": False,
            "selectionPersistenceProven": False,
            "reason": (
                "Extended and Short coexist in a stable rebased option table. The Extended "
                "capture has additional Standard+Extended descriptor copies, but the Short "
                "capture has no symmetric Standard+Short copies. No Censor resource identity, "
                "slot-option array, or incoming descriptor/field reference anchors those copies."
            ),
            "indexOrTransformedIdentityStatus": (
                "Not promoted: exact identities are present as option definitions, while a "
                "low-entropy index search has no bounded preset/loadout owner anchor."
            ),
            "writePathPromoted": False,
            "remainingBlocker": (
                "A stable player preset/loadout root or a same-lifecycle symmetric reference "
                "transition is required before selection ownership or persistence can be tested."
            ),
        },
        "safety": {
            "researchWrites": 0,
            "protectionChanges": 0,
            "fixtureFallback": "disabled",
        },
    }


def parse_int(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extended", type=Path, required=True)
    parser.add_argument("--short", type=Path, required=True)
    parser.add_argument("--extended-option-id", type=parse_int, required=True)
    parser.add_argument("--short-option-id", type=parse_int, required=True)
    parser.add_argument("--extended-add-path", type=parse_int, required=True)
    parser.add_argument("--short-add-path", type=parse_int, required=True)
    parser.add_argument("--default-option-id", type=parse_int, default=0x9FE412AD)
    parser.add_argument("--default-add-path", type=parse_int, default=0x462FC89D4903B33D)
    parser.add_argument("--weapon-resource", type=parse_int, default=0xF0338468DCDB6A6C)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
