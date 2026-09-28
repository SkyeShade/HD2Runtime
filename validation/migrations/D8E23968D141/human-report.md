# HD2Runtime build migration report

Source: HD2Runtime 0.26.1 (0.26.1 @ ccc9b4f86e3a), build F5FEE03DCFDB
Target: build D8E23968D141

| | Source | Target |
|---|---|---|
| Executable SHA-256 | `F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06` | `D8E23968D1412B07E06785321727D63EDF74E711214D6F6ADEB3BFCA95CA6827` |
| game.dll SHA-256 | `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E` | `73374BD4E38386BEB9A23BEF480082B67D457EBC77485FBEC5F488B4E95E201F` |
| Build profile | F5FEE03DCFDB | D8E23968D141 |

Target inputs: datalibrary `../JumpPackImprovements/local_research/dependencies/filediver/datalibrary`. Snapshot extraction cache: not used (datalibrary input).

## Confidence summary

- Previously writable fields: 6652
- Recovered automatically: 78.64% (439 carried, 4792 rebound)
- Downgraded to read-only: 21.36% (1421)
- Needing manual review: 15.8% (1051)
- Unsafe stale writes carried forward: 0

## Totals

| State | Fields |
|---|---|
| EXACT | 472 |
| MOVED | 4423 |
| BASELINE_CHANGED | 154 |
| LAYOUT_CHANGED | 1224 |
| AMBIGUOUS | 0 |
| LOST | 403 |
| BLOCKED | 592 |
| UNCHECKED | 271 |

## Recovered per category

| Category | Fields | Previously writable | Recovered | States |
|---|---|---|---|---|
| Magazine attachments | 233 | 233 | 233 | BASELINE_CHANGED 2, LAYOUT_CHANGED 24, MOVED 207 |
| Boosters | 42 | 42 | 2 | MOVED 2, UNCHECKED 40 |
| Vehicles and backpacks | 758 | 736 | 637 | EXACT 6, LOST 99, MOVED 653 |
| Player weapons | 3306 | 2457 | 2158 | BASELINE_CHANGED 152, EXACT 56, LAYOUT_CHANGED 988, LOST 194, MOVED 1916 |
| Drop-pod payloads | 248 | 240 | 240 | EXACT 248 |
| Stratagems | 1464 | 1456 | 646 | BLOCKED 592, EXACT 59, LOST 3, MOVED 587, UNCHECKED 223 |
| Support weapons | 1008 | 1008 | 942 | EXACT 85, LAYOUT_CHANGED 212, MOVED 703, UNCHECKED 8 |
| Vehicle weapons | 480 | 480 | 373 | EXACT 18, LOST 107, MOVED 355 |

## PREVIOUSLY SUPPORTED BUT NO LONGER SAFELY WRITABLE

1421 fields; grouped by object (first reason shown). Full evidence: writable-diff.json.

- **Concealed Insertion** (Boosters): 2 field(s) [UNCHECKED 2] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Dead Sprint** (Boosters): 3 field(s) [UNCHECKED 3] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Experimental Infusion** (Boosters): 3 field(s) [UNCHECKED 3] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Expert Extraction Pilot** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Firebomb Hellpods** (Boosters): 10 field(s) [UNCHECKED 10] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Flexible Reinforcement Budget** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Increased Reinforcement Budget** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Integrated Extinguishers** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Localization Confusion** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Motivational Shocks** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Muscle Enhancement** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Sample Extricator** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Sample Scanner** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Stamina Enhancement** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Stun Pods** (Boosters): 9 field(s) [UNCHECKED 9] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Surplus EAT Allocation** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **UAV Recon Booster** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **Vitality Enhancement** (Boosters): 1 field(s) [UNCHECKED 1] — UNCHECKED: game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- **TD-110 Maelstrom** (Vehicles and backpacks): 99 field(s) [LOST 99] — LOST: resource 0xB0C9FAF4AF8903F9 no longer exists
- **AR-11 Arbitrator** (Player weapons): 32 field(s) [LOST 32] — LOST: resource 0xA8A91EB54892B6B2 no longer exists
- **AR-2 Coyote** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-23 Liberator** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-23A Liberator Carbine** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-23C Liberator Concussive** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-23P Liberator Penetrator** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-32 Pacifier** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-59 Suppressor** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR-61 Tenderizer** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AR/GL-21 One-Two** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **ARC-12 Blitzer** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **BR-14 Adjudicator** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CB-9 Exploding Crossbow** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-19 Stun Lance** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-2 Saber** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-30 Stun Baton** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-5 Combat Hatchet** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **DBS-2 Double Freedom** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **FLAM-66 Torcher** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **GL-15 Evictor** (Player weapons): 47 field(s) [LOST 47] — LOST: resource 0x006E44327BB953FE no longer exists
- **GP-20 Ultimatum** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **JAR-5 Dominator** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **LAS-12 Sai** (Player weapons): 36 field(s) [LOST 36] — LOST: resource 0xC85F576D5E086147 no longer exists
- **LAS-13 Trident** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **LAS-16 Sickle** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **LAS-17 Double-Edge Sickle** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **LAS-58 Talon** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **M6C/SOCOM Pistol** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **M7S SMG** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **M90A Shotgun** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **MA5C Assault Rifle** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **MP-98 Knight** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-11 Stim Pistol** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-113 Verdict** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-19 Redeemer** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-2 Peacemaker** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-33 Missile Pistol** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-34 Breacher** (Player weapons): 46 field(s) [LOST 46] — LOST: resource 0xE91F569C2AD8AF01 no longer exists
- **P-35 Re-Educator** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-4 Senator** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-69 Veto** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P-92 Warrant** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **P/40-K Bolt Pistol** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **PLAS-1 Scorcher** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **PLAS-101 Purifier** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **PLAS-15 Loyalist** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **PLAS-39 Accelerator Rifle** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-2 Amendment** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-2124 Constitution** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-36 Eruptor** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-4 Hyena** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-6 Deadeye** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-63 Diligence** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-63CS Diligence Counter Sniper** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R-72 Censor** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **R/40-K Hot-Shot Marksman Rifle** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-20 Halt** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-22 Bushwhacker** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-225 Breaker** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-225IE Breaker Incendiary** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-225SP Breaker Spray&Pray** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-451 Cookout** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-8 Punisher** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-8P Punisher Plasma** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-8S Slugger** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-97 Sweeper** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SMG-203 Gallant** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SMG-32 Reprimand** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SMG-72 Pummeler** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SMG/FLAM-34 Stoker** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **StA-11 SMG** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **StA-52 Assault Rifle** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **VG-70 Variable** (Player weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **40-K Meltagun** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/AC-8 Autocannon Sentry** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/ARC-3 Tesla Tower** (Stratagems): 3 field(s) [UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/FLAM-40 Flame Sentry** (Stratagems): 5 field(s) [UNCHECKED 5] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/G-16 Gatling Sentry** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/GM-17 Gas Mortar Sentry** (Stratagems): 4 field(s) [UNCHECKED 4] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/LAS-98 Laser Sentry** (Stratagems): 3 field(s) [UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/M-12 Mortar Sentry** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/M-23 EMS Mortar Sentry** (Stratagems): 3 field(s) [UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/MG-43 Machine Gun Sentry** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **A/MLS-4X Rocket Sentry** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **AC-8 Autocannon** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **APW-1 Anti-Materiel Rifle** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **ARC-3 Arc Thrower** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **AX/AR-23 Guard Dog** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **AX/ARC-3 K-9** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **AX/FLAM-75 Hot Dog** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **AX/LAS-5 Rover** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **AX/TX-13 Dog Breath** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **B-1 Supply Pack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **B-100 Portable Hellbomb** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **B/FLAM-80 Cremator** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **B/MD C4 Pack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **CQC-1 One True Flag** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **CQC-20 Breaching Hammer** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **CQC-9 Defoliation Tool** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **E/AT-12 Anti-Tank Emplacement** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **E/GL-21 Grenadier Battlement** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **E/MG-101 HMG Emplacement** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EAT-17 Expendable Anti-Tank** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EAT-411 Leveller** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EAT-700 Expendable Napalm** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EXO-45 Patriot Exosuit** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EXO-49 Emancipator Exosuit** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EXO-51 Lumberer Exosuit** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **EXO-55 Breakthrough Exosuit** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle 110mm Rocket Pods** (Stratagems): 3 field(s) [UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle 500kg Bomb** (Stratagems): 41 field(s) [BLOCKED 38, UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle Airstrike** (Stratagems): 17 field(s) [BLOCKED 14, UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle Cluster Bomb** (Stratagems): 46 field(s) [BLOCKED 40, LOST 3, UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle Gas Airstrike** (Stratagems): 33 field(s) [BLOCKED 28, UNCHECKED 5] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle Napalm Airstrike** (Stratagems): 33 field(s) [BLOCKED 28, UNCHECKED 5] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle Smoke Strike** (Stratagems): 20 field(s) [BLOCKED 17, UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Eagle Strafing Run** (Stratagems): 3 field(s) [UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **FAF-14 Spear** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **FLAM-40 Flamethrower** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **FX-12 Shield Generator Relay** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **GL-21 Grenade Launcher** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **GL-28 Belt-Fed Grenade Launcher** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **GL-52 De-Escalator** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **GR-8 Recoilless Rifle** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **LAS-98 Laser Cannon** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **LAS-99 Quasar Cannon** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **LIFT-182 Warp Pack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **LIFT-850 Jump Pack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **LIFT-860 Hover Pack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **M-1000 Maxigun** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **M-102 Gunner FRV** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **M-103 Supply FRV** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **M-104 Incinerator FRV** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **M-105 Stalwart** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MD-17 Anti-Tank Mines** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MD-6 Anti-Personnel Minefield** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MD-8 Gas Mines** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MD-I4 Incendiary Mines** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MG-206 Heavy Machine Gun** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MG-43 Machine Gun** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MGX-42 Bullet Storm** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MLS-4X Commando** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **MS-11 Solo Silo** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital 120mm HE Barrage** (Stratagems): 80 field(s) [BLOCKED 78, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital 380mm HE Barrage** (Stratagems): 18 field(s) [BLOCKED 16, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Airburst Strike** (Stratagems): 92 field(s) [BLOCKED 90, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital EMS Strike** (Stratagems): 17 field(s) [BLOCKED 14, UNCHECKED 3] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Gas Strike** (Stratagems): 32 field(s) [BLOCKED 28, UNCHECKED 4] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Gatling Barrage** (Stratagems): 25 field(s) [BLOCKED 23, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Laser** (Stratagems): 11 field(s) [BLOCKED 9, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Napalm Barrage** (Stratagems): 92 field(s) [BLOCKED 84, UNCHECKED 8] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Precision Strike** (Stratagems): 28 field(s) [BLOCKED 26, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Railcannon Strike** (Stratagems): 28 field(s) [BLOCKED 26, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Smoke Strike** (Stratagems): 19 field(s) [BLOCKED 17, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **Orbital Walking Barrage** (Stratagems): 18 field(s) [BLOCKED 16, UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **PLAS-45 Epoch** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **RL-77 Airburst Rocket Launcher** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **RS-422 Railgun** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **S-11 Speargun** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **SH-20 Ballistic Shield Backpack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **SH-32 Shield Generator Pack** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **SH-51 Directional Shield** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **StA-X3 W.A.S.P. Launcher** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **TD-110 Maelstrom** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **TD-220 Bastion MK XVI** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **TX-41 Sterilizer** (Stratagems): 2 field(s) [UNCHECKED 2] — UNCHECKED: stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- **40-K Meltagun** (Support weapons): 3 field(s) [LAYOUT_CHANGED 1, MOVED 1, UNCHECKED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **AC-8 Autocannon** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **APW-1 Anti-Materiel Rifle** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **ARC-3 Arc Thrower** (Support weapons): 3 field(s) [LAYOUT_CHANGED 1, MOVED 1, UNCHECKED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-1 One True Flag** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-20 Breaching Hammer** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **CQC-9 Defoliation Tool** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **EAT-411 Leveller** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **EAT-700 Expendable Napalm** (Support weapons): 3 field(s) [LAYOUT_CHANGED 1, MOVED 1, UNCHECKED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **FAF-14 Spear** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **FLAM-40 Flamethrower** (Support weapons): 3 field(s) [LAYOUT_CHANGED 1, MOVED 1, UNCHECKED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **GL-21 Grenade Launcher** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **GL-28 Belt-Fed Grenade Launcher** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **GL-52 De-Escalator** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **GR-8 Recoilless Rifle** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **LAS-99 Quasar Cannon** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **M-1000 Maxigun** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **M-105 Stalwart** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **MG-206 Heavy Machine Gun** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **MG-43 Machine Gun** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **MGX-42 Bullet Storm** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **MLS-4X Commando** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **PLAS-45 Epoch** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **RL-77 Airburst Rocket Launcher** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **RS-422 Railgun** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **S-11 Speargun** (Support weapons): 4 field(s) [LAYOUT_CHANGED 1, MOVED 1, UNCHECKED 2] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **SG-88 Break-Action Shotgun** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **StA-X3 W.A.S.P. Launcher** (Support weapons): 2 field(s) [LAYOUT_CHANGED 1, MOVED 1] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **TX-41 Sterilizer** (Support weapons): 4 field(s) [LAYOUT_CHANGED 1, MOVED 1, UNCHECKED 2] — MOVED rests on layout-ordinal evidence, below the auto-apply threshold; review manually
- **TD-110 Maelstrom / attach_tank_gun** (Vehicle weapons): 23 field(s) [LOST 23] — LOST: resource 0xD58AE6A04EDB10DE no longer exists
- **TD-110 Maelstrom / slot_2** (Vehicle weapons): 14 field(s) [LOST 14] — LOST: resource 0x3A061009AA31E9CB no longer exists
- **TD-110 Maelstrom / slot_3** (Vehicle weapons): 35 field(s) [LOST 35] — LOST: resource 0x8AFF7F0793A5BCED no longer exists
- **TD-110 Maelstrom / slot_4** (Vehicle weapons): 35 field(s) [LOST 35] — LOST: resource 0x8AFF7F0793A5BCED no longer exists

## Changed baselines

- player_weapon:AR-2 Coyote:damage.type: 118 → 114
- player_weapon:AR-23 Liberator:attack.primary.projectile: 276 → 272
- player_weapon:AR-23 Liberator:projectile.type: 276 → 272
- player_weapon:AR-23 Liberator:damage.type: 108 → 104
- player_weapon:AR-23A Liberator Carbine:attack.primary.projectile: 276 → 272
- player_weapon:AR-23A Liberator Carbine:projectile.type: 276 → 272
- player_weapon:AR-23A Liberator Carbine:damage.type: 108 → 104
- player_weapon:AR-23C Liberator Concussive:attack.primary.projectile: 310 → 304
- player_weapon:AR-23C Liberator Concussive:projectile.type: 310 → 304
- player_weapon:AR-23C Liberator Concussive:damage.type: 107 → 103
- player_weapon:AR-23P Liberator Penetrator:damage.type: 105 → 101
- player_weapon:AR-32 Pacifier:damage.type: 116 → 112
- player_weapon:AR-59 Suppressor:damage.type: 114 → 110
- player_weapon:AR-61 Tenderizer:damage.type: 135 → 130
- player_weapon:AR/GL-21 One-Two:attack.primary.projectile: 334 → 327
- player_weapon:AR/GL-21 One-Two:projectile.type: 334 → 327
- player_weapon:AR/GL-21 One-Two:damage.type: 132 → 128
- player_weapon:ARC-12 Blitzer:damage.type: 199 → 193
- player_weapon:BR-14 Adjudicator:damage.type: 134 → 129
- player_weapon:CB-9 Exploding Crossbow:attack.primary.projectile: 249 → 247
- player_weapon:CB-9 Exploding Crossbow:terminal.primary.impact.explosion: 59 → 57
- player_weapon:CB-9 Exploding Crossbow:projectile.type: 249 → 247
- player_weapon:CB-9 Exploding Crossbow:damage.type: 208 → 202
- player_weapon:CQC-19 Stun Lance:damage.type: 558 → 548
- player_weapon:CQC-2 Saber:damage.type: 552 → 542
- player_weapon:CQC-30 Stun Baton:damage.type: 559 → 549
- player_weapon:CQC-42 Machete:damage.type: 553 → 543
- player_weapon:CQC-5 Combat Hatchet:damage.type: 551 → 541
- player_weapon:CQC-73 Entrenchment Tool:damage.type: 554 → 544
- player_weapon:DBS-2 Double Freedom:attack.feed_primary.projectile: 317 → 311
- player_weapon:DBS-2 Double Freedom:projectile.type: 317 → 311
- player_weapon:DBS-2 Double Freedom:damage.type: 159 → 154
- player_weapon:GP-20 Ultimatum:terminal.primary.impact.explosion: 341 → 334
- player_weapon:GP-31 Grenade Pistol:rounds.spare_rounds: 5 → 3
- player_weapon:GP-31 Grenade Pistol:rounds.rounds_from_supply: 5 → 3
- player_weapon:GP-31 Grenade Pistol:rounds.starting_rounds: 3 → 2
- player_weapon:GP-31 Grenade Pistol:attack.primary.projectile: 263 → 260
- player_weapon:GP-31 Grenade Pistol:terminal.primary.impact.explosion: 327 → 320
- player_weapon:GP-31 Grenade Pistol:terminal.primary.expiry.explosion: 327 → 320
- player_weapon:GP-31 Grenade Pistol:projectile.type: 263 → 260
- player_weapon:GP-31 Grenade Pistol:damage.type: 225 → 219
- player_weapon:JAR-5 Dominator:damage.type: 153 → 148
- player_weapon:LAS-13 Trident:damage.type: 508 → 499
- player_weapon:LAS-16 Sickle:damage.type: 48 → 47
- player_weapon:LAS-17 Double-Edge Sickle:damage.type: 48 → 47
- player_weapon:LAS-5 Scythe:damage.type: 501 → 492
- player_weapon:LAS-58 Talon:damage.type: 54 → 52
- player_weapon:LAS-7 Dagger:damage.type: 500 → 491
- player_weapon:M6C/SOCOM Pistol:attack.primary.projectile: 308 → 302
- player_weapon:M6C/SOCOM Pistol:projectile.type: 308 → 302
- player_weapon:M6C/SOCOM Pistol:damage.type: 93 → 89
- player_weapon:M7S SMG:attack.primary.projectile: 340 → 333
- player_weapon:M7S SMG:projectile.type: 340 → 333
- player_weapon:M7S SMG:damage.type: 71 → 67
- player_weapon:M90A Shotgun:damage.type: 157 → 152
- player_weapon:MA5C Assault Rifle:damage.type: 136 → 131
- player_weapon:MP-98 Knight:attack.primary.projectile: 215 → 214
- player_weapon:MP-98 Knight:projectile.type: 215 → 214
- player_weapon:MP-98 Knight:damage.type: 74 → 70
- player_weapon:P-11 Stim Pistol:attack.primary.projectile: 318 → 312
- player_weapon:P-11 Stim Pistol:projectile.type: 318 → 312
- player_weapon:P-113 Verdict:damage.type: 91 → 87
- player_weapon:P-33 Missile Pistol:terminal.primary.impact.explosion: 154 → 151
- player_weapon:P-33 Missile Pistol:terminal.primary.expiry.explosion: 154 → 151
- player_weapon:P-33 Missile Pistol:damage.type: 95 → 91
- player_weapon:P-35 Re-Educator:attack.primary.projectile: 343 → 336
- player_weapon:P-35 Re-Educator:projectile.type: 343 → 336
- player_weapon:P-35 Re-Educator:damage.type: 67 → 65
- player_weapon:P-4 Senator:attack.feed_primary.projectile: 309 → 303
- player_weapon:P-4 Senator:projectile.type: 309 → 303
- player_weapon:P-4 Senator:damage.type: 99 → 95
- player_weapon:P-69 Veto:attack.primary.projectile: 237 → 235
- player_weapon:P-69 Veto:projectile.type: 237 → 235
- player_weapon:P-69 Veto:damage.type: 92 → 88
- player_weapon:P-92 Warrant:attack.primary.projectile: 326 → 319
- player_weapon:P-92 Warrant:projectile.type: 326 → 319
- player_weapon:P-92 Warrant:damage.type: 94 → 90
- player_weapon:P/40-K Bolt Pistol:attack.primary.projectile: 202 → 201
- player_weapon:P/40-K Bolt Pistol:terminal.primary.impact.explosion: 388 → 379
- player_weapon:P/40-K Bolt Pistol:projectile.type: 202 → 201
- player_weapon:P/40-K Bolt Pistol:damage.type: 156 → 151
- player_weapon:PLAS-1 Scorcher:terminal.primary.impact.explosion: 155 → 152
- player_weapon:PLAS-1 Scorcher:damage.type: 56 → 54
- player_weapon:PLAS-101 Purifier:attack.primary.projectile: 296 → 291
- player_weapon:PLAS-101 Purifier:terminal.primary.impact.explosion: 191 → 187
- player_weapon:PLAS-101 Purifier:projectile.type: 296 → 291
- player_weapon:PLAS-101 Purifier:damage.type: 63 → 61
- player_weapon:PLAS-15 Loyalist:terminal.primary.impact.explosion: 355 → 347
- player_weapon:PLAS-15 Loyalist:damage.type: 56 → 54
- player_weapon:PLAS-39 Accelerator Rifle:terminal.primary.impact.explosion: 413 → 404
- player_weapon:PLAS-39 Accelerator Rifle:damage.type: 308 → 302
- player_weapon:R-2 Amendment:attack.primary.projectile: 327 → 320
- player_weapon:R-2 Amendment:projectile.type: 327 → 320
- player_weapon:R-2 Amendment:damage.type: 138 → 133
- player_weapon:R-2124 Constitution:attack.feed_primary.projectile: 282 → 278
- player_weapon:R-2124 Constitution:projectile.type: 282 → 278
- player_weapon:R-2124 Constitution:damage.type: 137 → 132
- player_weapon:R-36 Eruptor:terminal.primary.impact.explosion: 158 → 155
- player_weapon:R-36 Eruptor:terminal.primary.expiry.explosion: 158 → 155
- player_weapon:R-36 Eruptor:damage.type: 149 → 144
- player_weapon:R-4 Hyena:attack.primary.projectile: 207 → 206
- player_weapon:R-4 Hyena:projectile.type: 207 → 206
- player_weapon:R-4 Hyena:damage.type: 142 → 137
- player_weapon:R-6 Deadeye:attack.primary.projectile: 299 → 293
- player_weapon:R-6 Deadeye:projectile.type: 299 → 293
- player_weapon:R-6 Deadeye:damage.type: 139 → 134
- player_weapon:R-63 Diligence:attack.primary.projectile: 305 → 299
- player_weapon:R-63 Diligence:projectile.type: 305 → 299
- player_weapon:R-63 Diligence:damage.type: 141 → 136
- player_weapon:R-63CS Diligence Counter Sniper:attack.primary.projectile: 241 → 239
- player_weapon:R-63CS Diligence Counter Sniper:projectile.type: 241 → 239
- player_weapon:R-63CS Diligence Counter Sniper:damage.type: 143 → 138
- player_weapon:R-72 Censor:attack.primary.projectile: 325 → 318
- player_weapon:R-72 Censor:projectile.type: 325 → 318
- player_weapon:R-72 Censor:damage.type: 130 → 126
- player_weapon:R/40-K Hot-Shot Marksman Rifle:damage.type: 510 → 501
- player_weapon:SG-20 Halt:damage.primary.type: 166 → 160
- player_weapon:SG-20 Halt:damage.alternate.type: 175 → 169
- player_weapon:SG-22 Bushwhacker:attack.feed_primary.projectile: 260 → 257
- player_weapon:SG-22 Bushwhacker:projectile.type: 260 → 257
- player_weapon:SG-22 Bushwhacker:damage.type: 163 → 157
- player_weapon:SG-225 Breaker:damage.type: 179 → 173
- player_weapon:SG-225IE Breaker Incendiary:attack.primary.projectile: 314 → 308
- player_weapon:SG-225IE Breaker Incendiary:projectile.type: 314 → 308
- player_weapon:SG-225IE Breaker Incendiary:damage.type: 182 → 176
- player_weapon:SG-225SP Breaker Spray&Pray:damage.type: 178 → 172
- player_weapon:SG-451 Cookout:attack.feed_primary.projectile: 347 → 340
- player_weapon:SG-451 Cookout:projectile.type: 347 → 340
- player_weapon:SG-451 Cookout:damage.type: 164 → 158
- player_weapon:SG-8 Punisher:attack.feed_primary.projectile: 260 → 257
- player_weapon:SG-8 Punisher:projectile.type: 260 → 257
- player_weapon:SG-8 Punisher:damage.type: 163 → 157
- player_weapon:SG-8P Punisher Plasma:terminal.primary.impact.explosion: 290 → 285
- player_weapon:SG-8P Punisher Plasma:damage.type: 57 → 55
- player_weapon:SG-8S Slugger:attack.feed_primary.projectile: 240 → 238
- player_weapon:SG-8S Slugger:projectile.type: 240 → 238
- player_weapon:SG-8S Slugger:damage.type: 176 → 170
- player_weapon:SG-97 Sweeper:attack.primary.projectile: 262 → 259
- player_weapon:SG-97 Sweeper:projectile.type: 262 → 259
- player_weapon:SG-97 Sweeper:damage.type: 158 → 153
- player_weapon:SMG-203 Gallant:damage.type: 77 → 73
- player_weapon:SMG-32 Reprimand:damage.type: 96 → 92
- player_weapon:SMG-37 Defender:damage.type: 83 → 79
- player_weapon:SMG-72 Pummeler:damage.type: 90 → 86
- player_weapon:SMG/FLAM-34 Stoker:damage.type: 97 → 93
- player_weapon:StA-11 SMG:attack.primary.projectile: 215 → 214
- player_weapon:StA-11 SMG:projectile.type: 215 → 214
- player_weapon:StA-11 SMG:damage.type: 74 → 70
- player_weapon:StA-52 Assault Rifle:attack.primary.projectile: 276 → 272
- player_weapon:StA-52 Assault Rifle:projectile.type: 276 → 272
- player_weapon:StA-52 Assault Rifle:damage.type: 108 → 104
- player_weapon:VG-70 Variable:damage.type: 76 → 72
- attachment:magazine/whisper-rifle-5-5x50mm-standard/16af29c8d0590809:attachment.magazines_from_supply: 16 → 12
- attachment:magazine/whisper-rifle-5-5x50mm-standard/16af29c8d0590809:attachment.spare_magazines: 16 → 12

## Ambiguous (0)

None.

## Lost (403)

- 99 × resource 0xB0C9FAF4AF8903F9 no longer exists
- 56 × weapon chain no longer resolves: anchor 0x8AFF7F0793A5BCED no longer owns ProjectileWeaponComponentData
- 29 × weapon chain no longer resolves: anchor 0x006E44327BB953FE no longer owns ProjectileWeaponComponentData; anchor 0x006E44327BB953FE no longer owns WeaponRoundsComponentData
- 29 × weapon chain no longer resolves: anchor 0xE91F569C2AD8AF01 no longer owns ProjectileWeaponComponentData
- 26 × resource 0x006E44327BB953FE no longer exists
- 26 × resource 0xC85F576D5E086147 no longer exists
- 25 × resource 0xA8A91EB54892B6B2 no longer exists
- 25 × resource 0xE91F569C2AD8AF01 no longer exists
- 17 × weapon chain no longer resolves: anchor 0xA8A91EB54892B6B2 no longer owns ProjectileWeaponComponentData
- 17 × weapon chain no longer resolves: anchor 0xC85F576D5E086147 no longer owns ProjectileWeaponComponentData
- 15 × weapon chain no longer resolves: anchor 0xD58AE6A04EDB10DE no longer owns ProjectileWeaponComponentData
- 14 × resource 0x8AFF7F0793A5BCED no longer exists
- 8 × resource 0xD58AE6A04EDB10DE no longer exists
- 8 × resource 0x3A061009AA31E9CB no longer exists
- 6 × weapon chain no longer resolves: anchor 0x3A061009AA31E9CB no longer owns ProjectileWeaponComponentData
- 3 × explosion type 417 no longer exists

## Blocked (592)

- 257 × shared scope widened: 0 -> 1 native consumers (1 new)
- 36 × damage type 261 changed and no weapon chain proves it is the same row (types can renumber)
- 27 × damage type 262 changed and no weapon chain proves it is the same row (types can renumber)
- 27 × damage type 265 changed and no weapon chain proves it is the same row (types can renumber)
- 18 × damage type 190 changed and no weapon chain proves it is the same row (types can renumber)
- 15 × projectile type 42 changed and no weapon chain proves it is the same row (types can renumber)
- 11 × damage type 391 changed and no weapon chain proves it is the same row (types can renumber)
- 11 × damage type 390 changed and no weapon chain proves it is the same row (types can renumber)
- 10 × projectile type 137 changed and no weapon chain proves it is the same row (types can renumber)
- 10 × projectile type 11 changed and no weapon chain proves it is the same row (types can renumber)
- 9 × damage type 251 changed and no weapon chain proves it is the same row (types can renumber)
- 9 × damage type 421 changed and no weapon chain proves it is the same row (types can renumber)
- 9 × damage type 513 changed and no weapon chain proves it is the same row (types can renumber)
- 9 × shared scope widened: 0 -> 2 native consumers (2 new)
- 9 × damage type 267 changed and no weapon chain proves it is the same row (types can renumber)
- 9 × damage type 443 changed and no weapon chain proves it is the same row (types can renumber)
- 6 × explosion type 75 changed and no weapon chain proves it is the same row (types can renumber)
- 6 × explosion type 106 changed and no weapon chain proves it is the same row (types can renumber)
- 6 × explosion type 74 changed and no weapon chain proves it is the same row (types can renumber)
- 5 × projectile type 170 changed and no weapon chain proves it is the same row (types can renumber)
- 5 × projectile type 286 changed and no weapon chain proves it is the same row (types can renumber)
- 5 × projectile type 131 changed and no weapon chain proves it is the same row (types can renumber)
- 5 × projectile type 188 changed and no weapon chain proves it is the same row (types can renumber)
- 5 × projectile type 141 changed and no weapon chain proves it is the same row (types can renumber)
- 5 × projectile type 130 changed and no weapon chain proves it is the same row (types can renumber)
- … 18 more distinct reasons in blocked.json

## Unchecked (inputs cannot prove either way) (271)

- 202 × stratagem rows are only readable from a snapshot of a runtime-profiled game.dll
- 40 × game.dll-resident booster table: a new game.dll must be re-proven by scripts/research_booster_native.py
- 29 × the target view has no status settings (snapshot-only table)

## Relationships

BROKEN 8, INTACT 125, UNCHECKED 286

- BROKEN vehicle_mount:mount:TD-110 Maelstrom:slot_0: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:mount:TD-110 Maelstrom:slot_2: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:mount:TD-110 Maelstrom:slot_3: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:mount:TD-110 Maelstrom:slot_4: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:vehicle-weapon-mount:TD-110 Maelstrom / attach_tank_gun: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:vehicle-weapon-mount:TD-110 Maelstrom / slot_2: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:vehicle-weapon-mount:TD-110 Maelstrom / slot_3: vehicle no longer owns a MountComponent
- BROKEN vehicle_mount:vehicle-weapon-mount:TD-110 Maelstrom / slot_4: vehicle no longer owns a MountComponent
- UNCHECKED: attachment_compatibility 37, booster_granted 1, stratagem_icon 93, stratagem_payload 93, stratagem_rack 62

## New candidates (unreviewed, not writable)

- Entities: 0 ()
- Settings rows: 0
- Stratagem ids: 0
- Entity deltas (attachments): 0
- Component types: none

Next steps: docs/game-update-migration.md.
