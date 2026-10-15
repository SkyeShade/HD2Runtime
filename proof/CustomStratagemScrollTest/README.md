# CustomStratagemScrollTest 0.1.0: the 0.40.1 custom stratagem panel scroll test

This mod registers 24 custom stratagems, `SCROLL TEST 01` to `SCROLL TEST 24`. Each one is the Orbital Gas Barrage
example under its own id, name and call-in code (LEFT LEFT RIGHT RIGHT, then three more directions). Not live-tested.

It needs the HD2Runtime 0.40.1 development build. Runtime 0.40.0 refuses the 17th custom stratagem at load.

The log names this build: `CustomStratagemScrollTest 0.1.0 SCROLL BUILD`.

## What to look for in a live test

1. Open a stratagem slot's selector. The CUSTOM STRATAGEMS panel shows five rows of four (cards 01 to 20), with a
   scrollbar right of the grid. The log says `5 of 6 rows in view, scrolled to row 0`.
2. Scroll with the mouse wheel over the panel. The log says `scrolled (the mouse wheel)`, and cards 21 to 24 come into
   view. If the wheel does nothing, click the scrollbar track below the thumb instead (`scrolled (the scrollbar)`).
3. Press F6 repeatedly. The focus walks the cards, and the panel scrolls to card 21 when the focus reaches it.
4. Pick a card from the scrolled row (21 to 24). It goes into the slot like any other card.
