# MinefieldSalvos

Live test: MD-6 Anti-Personnel Minefield salvos 6 -> 2 (48 mines -> 16).

What to verify: call in the MD-6 on open, flat ground and count the launcher's salvos. Vanilla, it fires six
salvos of eight mines, 48 in total. With this mod it should fire two salvos (16 mines) and then stop. The other three
minefields stay vanilla, so they are the control.

ThrowerComponent slot 0 +40 matches three independent proofs:
- the wiki's "six salvos of eight mines" sentence and its structured Salvos field;
- a typed u32 member;
- the launcher's 48 distinct launch sockets (salvos x mines per salvo).

Counts can only be reduced. Built only.
