# Evidence policy

Evidence is recorded per field as independent facts, not a single confidence
ladder. A field can be gameplay-proven while its stripped schema name is unknown.

| Flag | Meaning |
| --- | --- |
| `structural_candidate` | Reviewed bytes, field width and an owned record location exist |
| `schema_labelled` | The semantic label is supported by the sibling's named schema/reference analysis; current type metadata may be stripped |
| `current_live_ownership_proven` | This observation used the live adapter, checked the build, resolved the resource/component or settings linkage and passed stable rereads |
| `gameplay_proven` | A cited prior sibling gameplay report supports this field's meaning; it does not prove every replacement value or preset |
| `native_consumer_proven` | A traced native consumer establishes the exact field semantics; no milestone-1 field claims this |

All observations using regression fixtures set current-live ownership to false.
Historical logs are source evidence only. Values copied from those logs never
acquire current-live status. Sources are linked by sibling-relative path and
their audit-time SHA-256 in `provenance.json`. `domains/catalog.lua` maps each
field to its source; `schemas/current.lua` records reviewed structural identities.

Jump-pack `vertical_launch_velocity`, shield scalar aliases and health-zone
aliases deliberately do not claim schema labels. They retain their gameplay
evidence separately. The JAR-5 `armor_penetration` convenience read exposes the
first of three AP lanes. A future patch must explicitly address all intended
lanes and leave the fourth entry unchanged; a scalar read must not silently
become a twelve-byte write.

The live-validation client also reads AP lanes 1–3 and the reviewed Jump Pack
`movement_scalar_04` / `movement_scalar_24`. Those two scalar aliases remain
structural candidates with gameplay/native-consumer flags false. Their observed
values are compared to 20 and 60 without assigning new movement semantics.

Expected FP32 comparison in read reports allows one half-ULP-scale relative
tolerance for display baselines such as 0.1. This is only a diagnostic indicator.
Future writes and ensure conflict classification require exact encoded-byte
comparison, never this tolerance.
