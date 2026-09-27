from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from snapshot_support import snapshot_bytes
from support import ROOT


spec = importlib.util.spec_from_file_location(
    "attachment_selection_candidates",
    ROOT / "scripts/research_attachment_selection_candidates.py",
)
candidate_research = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = candidate_research
spec.loader.exec_module(candidate_research)


EXTENDED_ID = 0x536662C0
SHORT_ID = 0x33EAAA65
STANDARD_ID = 0x9FE412AD
EXTENDED_PATH = 0x37C2891774B38C87
SHORT_PATH = 0x986E6696B34B8902
STANDARD_PATH = 0x462FC89D4903B33D
CENSOR_RESOURCE = 0xF0338468DCDB6A6C


def descriptor(lead_target: int, option_id: int, add_path: int) -> bytes:
    data = bytearray(0x58)
    struct.pack_into("<Q", data, 0, lead_target)
    struct.pack_into("<I", data, 8, option_id)
    struct.pack_into("<III", data, 12, 0x900C9879, 0x887E442D, 0x0BBE112B)
    struct.pack_into("<Q", data, 0x20, add_path)
    struct.pack_into("<Q", data, 0x30, 1)
    return bytes(data)


class AttachmentSelectionCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_snapshots(self) -> tuple[Path, Path]:
        canonical_a_base = 0x200000
        canonical_b_base = 0x500000
        canonical_a = bytearray(0x3000)
        canonical_b = bytearray(0x3000)
        canonical_a[0x1000:0x1058] = descriptor(
            canonical_a_base + 0x1800, EXTENDED_ID, EXTENDED_PATH
        )
        canonical_a[0x1058:0x10B0] = descriptor(
            canonical_a_base + 0x1840, SHORT_ID, SHORT_PATH
        )
        canonical_b[0x1000:0x1058] = descriptor(
            canonical_b_base + 0x1800, EXTENDED_ID, EXTENDED_PATH
        )
        canonical_b[0x1058:0x10B0] = descriptor(
            canonical_b_base + 0x1840, SHORT_ID, SHORT_PATH
        )

        copied = bytearray(0x2000)
        copied[0x800:0x858] = descriptor(
            canonical_a_base + 0x17C0, STANDARD_ID, STANDARD_PATH
        )
        copied[0x858:0x8B0] = descriptor(
            canonical_a_base + 0x1800, EXTENDED_ID, EXTENDED_PATH
        )
        extended = snapshot_bytes(
            self.folder / "extended.hd2snap",
            [
                {
                    "base": canonical_a_base,
                    "size": len(canonical_a),
                    "data": bytes(canonical_a),
                },
                {"base": 0x300000, "size": len(copied), "data": bytes(copied)},
            ],
        )
        short = snapshot_bytes(
            self.folder / "short.hd2snap",
            [
                {
                    "base": canonical_b_base,
                    "size": len(canonical_b),
                    "data": bytes(canonical_b),
                },
                {"base": 0x600000, "size": 0x2000, "data": bytes(0x2000)},
            ],
        )
        return extended, short

    def args(self, extended: Path, short: Path) -> argparse.Namespace:
        return argparse.Namespace(
            extended=extended,
            short=short,
            extended_option_id=EXTENDED_ID,
            short_option_id=SHORT_ID,
            extended_add_path=EXTENDED_PATH,
            short_add_path=SHORT_PATH,
            default_option_id=STANDARD_ID,
            default_add_path=STANDARD_PATH,
            weapon_resource=CENSOR_RESOURCE,
            output=self.folder / "report.json",
        )

    def test_exact_scan_maps_a_hit_that_crosses_a_chunk_boundary(self):
        data = bytearray(64)
        struct.pack_into("<Q", data, 14, EXTENDED_PATH)
        path = snapshot_bytes(
            self.folder / "boundary.hd2snap",
            [{"base": 0x700000, "size": len(data), "data": bytes(data)}],
        )
        snapshot = candidate_research.parse_snapshot(path)
        original_chunk = candidate_research.SCAN_CHUNK
        candidate_research.SCAN_CHUNK = 16
        try:
            hits = candidate_research.scan_exact(
                snapshot,
                [candidate_research.Needle("extendedAddPath", 8, EXTENDED_PATH)],
                "test",
            )
        finally:
            candidate_research.SCAN_CHUNK = original_chunk
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].va, 0x700000 + 14)
        self.assertEqual(hits[0].allocation_offset, 14)

    def test_rebased_table_and_asymmetric_copy_do_not_prove_selection_owner(self):
        extended, short = self.make_snapshots()
        report = candidate_research.compare(self.args(extended, short))

        self.assertTrue(report["snapshots"]["buildFingerprintsMatch"])
        self.assertEqual(report["occurrenceCounts"]["extendedOptionId"]["extendedSnapshot"], 2)
        self.assertEqual(report["occurrenceCounts"]["extendedOptionId"]["shortSnapshot"], 1)
        self.assertEqual(report["occurrenceCounts"]["shortOptionId"]["extendedSnapshot"], 1)
        self.assertEqual(report["occurrenceCounts"]["shortOptionId"]["shortSnapshot"], 1)

        tables = report["descriptorEvidence"]
        self.assertIsNotNone(tables["extendedSnapshot"]["canonicalAdjacentTable"])
        self.assertIsNotNone(tables["shortSnapshot"]["canonicalAdjacentTable"])
        candidates = report["changingCandidates"]
        self.assertEqual(len(candidates["extendedSnapshotOnly"]), 1)
        self.assertEqual(len(candidates["shortSnapshotOnly"]), 0)
        copied = candidates["extendedSnapshotOnly"][0]
        self.assertEqual(copied["completeExtendedDescriptorCopies"], 1)
        self.assertEqual(len(copied["standardOptionIdOccurrences"]), 1)
        self.assertEqual(copied["shortOptionIdOccurrences"], [])
        self.assertEqual(copied["weaponResourceOccurrences"], [])
        self.assertEqual(copied["adjacentSlotOptionPairs"], [])

        references = report["derivedReferencePass"]["counts"]
        self.assertEqual(references["extendedDescriptorStartReference"]["extendedSnapshot"], 0)
        self.assertEqual(references["shortDescriptorStartReference"]["shortSnapshot"], 0)
        incoming = report["candidateIncomingReferencePass"]
        self.assertEqual(incoming["extendedSnapshot"]["rawHitCount"], 0)
        self.assertEqual(incoming["extendedSnapshot"]["alignedPointerHitCount"], 0)
        self.assertFalse(incoming["shortSnapshot"]["performed"])
        self.assertFalse(report["conclusion"]["candidateOwnerFound"])
        self.assertFalse(report["conclusion"]["writePathPromoted"])
        self.assertEqual(report["safety"]["researchWrites"], 0)
        self.assertEqual(report["safety"]["protectionChanges"], 0)
        self.assertEqual(report["safety"]["fixtureFallback"], "disabled")

    def test_committed_report_remains_read_only_and_fail_closed(self):
        report = json.loads(
            (ROOT / "research/attachment-selection-candidates-F5FEE03DCFDB.json").read_text()
        )
        self.assertEqual(report["scope"]["unrestrictedSemanticScan"], False)
        self.assertEqual(report["scope"]["fixtureFallback"], False)
        self.assertFalse(report["conclusion"]["candidateOwnerFound"])
        self.assertFalse(report["conclusion"]["writePathPromoted"])
        self.assertEqual(report["safety"]["researchWrites"], 0)
        self.assertEqual(report["safety"]["protectionChanges"], 0)
        self.assertEqual(report["safety"]["fixtureFallback"], "disabled")


if __name__ == "__main__":
    unittest.main()
