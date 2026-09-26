# Extraction and tooling provenance

Generic functions and platform declarations were selectively adapted from the
user's sibling mod projects. Exact inspected file hashes and retained-input
provenance are in `docs/provenance.json`; `docs/audit.md` identifies their roles.
No complete gameplay mod, native executable or third-party tool is bundled.

The archive writer inherited the siblings' Bingus tooling adaptation. Loader
integration follows the existing local Bingus Shared Loader v15/API 1 authoring
guide. The loader itself remains a separate dependency.

The offline runner loads the user's installed `lua51.dll` without redistributing
it or loading the game. Fixture bytes come from already-retained local decoded
data and one saved diagnostic row. They are regression evidence, not source for
an assertion that a new live capture or gameplay test took place.
