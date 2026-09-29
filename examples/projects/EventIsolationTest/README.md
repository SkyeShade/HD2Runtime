# EventIsolationTest

Deliberate-failure test for the event bus (`docs/events.md#callback-isolation`).

- **F9** (`event_isolation_test.trigger`): two subscribers on `key_down`. The first (higher priority) raises
  `EventIsolationTest: intentional failure` on every press and is never disabled (`max_failures=0`). The second must
  still run every time.
- **Timers**: two repeating 2-second timers. The first always fails; after 25 consecutive failures Runtime disables
  it (one log line). The second keeps running.

## How to test

Load into the ship or a mission, focus the game window and press F9 a few times. `HD2Runtime.log` must show, per
press:

```
[HD2Runtime] event key_down callback failed (mod mods/hd2runtime_examples/event_isolation_test, subscription N): EventIsolationTest: intentional failure [...]
[HD2Runtime] [mods/hd2runtime_examples/event_isolation_test] second subscriber ran after the failing one (press 1)
```

The failure is logged in full for the first three presses, then every 100th, while the "second subscriber ran" line
appears for every press. About 50 seconds after loading, the log shows the failing timer disabled
(`repeating timer callback disabled ... disabled after 25 consecutive failures`) while `healthy timer ran` continues.

Report whether each press produced the second-subscriber line, and whether anything else stopped working.
