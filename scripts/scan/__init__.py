"""HD2Runtime research scanner toolkit (offline, read-only; never used in game).

Reusable building blocks for systematic field discovery, so research no longer depends on finding one offset at a
time:

* ``tables``    typed access to EVERY component table of the pinned entity file: flattened member paths, decoding,
                record ownership, entity membership and resource names;
* ``settings``  projectile/damage/explosion/arc/beam settings rows by native type, same flattened paths;
* ``golib``     Filediver Go struct leads aligned with the type library (name-length fit);
* ``compare``   side-by-side family matrices, member classification (float/int/enum/hash/bool/vector/sentinel),
                variation partitions, correlated-role clusters, archetype-specific values, shared vs unique records;
* ``strides``   array/struct stride discovery in raw bytes (records and snapshot memory);
* ``xref``      game.dll function map (.pdata), rip-relative global references, displacement-access scans and
                immediate searches: cross-references from candidate fields into native code;
* ``instances`` retained-snapshot analysis: per-instance copies of a type record, shared type data vs runtime state,
                and multi-snapshot diffs;
* ``report``    the candidate-report format (confidence vocabulary, JSON + Markdown writers). Reports never promote a
                field: promotion stays a reviewed step in the feature's own research script.

Confidence vocabulary (``report.CONFIDENCE``): CONFIRMED (independent proof: code read + exact published value or a
live test), STRONG (code read or exact published value plus a consistent name length and differential), PLAUSIBLE
(layout/name-length/differential agree but no active source), UNKNOWN (nothing but layout).
"""
