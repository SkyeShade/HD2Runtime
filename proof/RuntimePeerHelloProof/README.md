# RuntimePeerHelloProof 0.1.0: the first Runtime-to-Runtime message

Development proof of the Runtime's peer channel (docs/research/runtime-peer-messaging-F5FEE03DCFDB.md, sections 2 and
4). **Nothing of gameplay changes.** No custom stratagem uses the channel yet: this proof decides whether it works.

0.1.0 (`0.1.0 PEER HELLO BUILD`). It needs `HD2Runtime-0.30.0-dev-peer-channel.zip`, whose log says
`EXPERIMENTAL MULTIPLAYER PEER-CHANNEL BUILD`. With an older Runtime it logs that it has no peer channel and does nothing.

## What it does

Each machine publishes **one lobby member property**, `hd2rt`, and reads every other member's. It uses the game's own
PlayFab lobby member data, through the two engine functions game.dll itself calls for its own keys (`platform_lobby`,
`crossplay_mode`):

- T+0x120 `set_member_data`;
- T+0x118 `member_data`.

The value is an `hd2rt/1` state with no custom stratagem in it, for example
`hd2rt/1;0.30.0-dev;811C9DC5;1;-,-,-,-`. The proof publishes, in order:

| Value | When |
|---|---|
| `HELLO` (seq 1) | As soon as the channel allows: 10 s after this machine joined the lobby, and after the game's own one-shot `platform_lobby` post there (at most 20 s in Runtime builds after 2026-10-04; 60 s in the peer-channel build this proof was tested with) |
| `SIZE PROBE` (seq 2) | 20 s after another member's value was first read here. It holds four 48-character ids, the longest legal value (about 240 bytes) |
| `MISSION` | 20 s into a mission |
| `BACK ON SHIP` | Aboard the ship after that mission |

The channel posts at most once per 5 s and never repeats an unchanged value. After 3 failed posts in one lobby it posts
nothing more there.

Every member's value is read every 2 s aboard the ship and every 5 s in a mission. A change is logged with this
machine's UTC time, so comparing the two players' logs gives the latency.

## How to test

Two players. Both need Bingus Shared Loader, `HD2Runtime-0.30.0-dev-peer-channel.zip` and this ZIP. Disable the older
`HD2Runtime-0.30.0-dev-multiplayer-experimental` runtime. The custom stratagem examples may stay installed: nothing here
touches them.

1. Form a squad aboard the ship (either player hosts). Wait about a minute.
2. Play one mission and stay in it at least 30 s.
3. Return to the ship and wait about a minute.
4. Press Ctrl+F10 once (status), then quit. Send both `HD2Runtime.log` files, saying which player hosted.

## Checklist (both logs)

- [ ] `RuntimePeerHelloProof 0.1.0 PEER HELLO BUILD` and `EXPERIMENTAL MULTIPLAYER PEER-CHANNEL BUILD`
- [ ] `PEER CHANNEL LOBBY: ..., 2 members`
- [ ] `PEER IDS: ... every lobby member is a session player: yes` (lobby member ids = the game's session peer ids)
- [ ] `HELLO SET` then `PEER CHANNEL POSTED: hd2rt = "hd2rt/1;...;1;-,-,-,-"`
- [ ] `OWN VALUE VISIBLE: HELLO (seq 1) reads back from the lobby N s after it was set`
- [ ] `PEER HELLO RECEIVED from <the other player> ... seq 1 ... compatible with this machine: yes`, on the client
      (host -> client) and on the host (client -> host)
- [ ] `SIZE PROBE RECEIVED WHOLE from <the other player>: N bytes`
- [ ] `STATE: mission ... this machine is the host/client; lobby <the same id>`, then `MISSION SET`, its post and
      `PEER HELLO RECEIVED ... (..., mission): seq 3`
- [ ] `STATE: ship`, `BACK ON SHIP` received
- [ ] No `PEER CHANNEL POST FAILED`, no `PEER VALUE REFUSED`, no `PEER SEQ REGRESSION`
- [ ] The game behaves normally: the squad and its lobby, joining, the mission and its end

Also record: the UTC times of each `SET` on one machine and of the matching `RECEIVED` on the other (the latency), and
anything unusual in the game's lobby, invites or crossplay settings.

## Not part of this proof

No custom stratagem state is exchanged. The handshake, pick sync, carrier-map check and per-caller execution come only
after this passes live.
