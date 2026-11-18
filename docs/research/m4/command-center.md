# Command Center

The Command Center's object, its command types and their tables, the Command knob, and how a footswitch press and a snapshot recall fire a command. Status tags as in [conventions.md](../conventions.md). Everything here is from disassembling Entry 0 (2026-11-17, for issue #108) unless it says otherwise.

## The object and its slots [verified offline]

- `0x28d96094()` returns the Command Center object, `0x281252b8`. It holds 13 slots: 0..5 Instant 1..6, 6..10 FS1..FS5 (slot = footswitch index k + 6), 11..12 EXP 1..2.
- Slot s's command type is the byte at `cc + 0x74 + s` (getter `0x28de6634(cc, s)`). Its parameters are 7 bytes at `cc + 0x81 + 7s` (getter `0x28de671c(cc, s, p)`, setter `0x28de672c(cc, s, p, v)`); p = 0 is the Command knob itself, the command's own parameters start at p = 1.
- `0x28de67e4(cc, s, type, ...)` sets a slot's type from the UI; `0x28de4fc0` copies a slot.
- **The footswitch node** [verified on unit, 2026-11-17]: an FS slot's command acts only through a node of kind 3 in its footswitch's assignment list (the stomp toggle walks that list, `0x28dd113e`; `0x28dd7218(fs, k)` finds the kind-3 node). Setting an FS slot's type adds it through `0x28de4e74` and the node insert `0x28dd87bc(fs, k, type, 1)`, which names the node with `0x28dd568c(node, type)` (the label, at node + 0x24, that Home shows for a footswitch without a block: CC Toggle, Hotkey, Snapshot …). `0x28dd568c` returns 0 for types 7..11 and 13, and the insert then makes no node, so such a type in an FS slot is stored but never fires.

## Command types [verified offline]

Types 0..21; the tables below are indexed by type and all have 22 rows.

| type | short name | parameters (labels) | offered on |
|---|---|---|---|
| 0 | None | | every slot |
| 1 | MIDI CC | Channel, CC #, Value | FS |
| 2 | CC Togl | Channel, CC #, Dim Value, Lit Value, Type | FS |
| 3 | MIDI CC | Channel, CC #, Min Value, Max Value | EXP |
| 4 | BankPC | Channel, Bank CC00, Bank CC32, Program | FS |
| 5 | NoteOn | Channel, Note, Velocity, Off Note | FS |
| 6 | MMC | Message | FS |
| 7, 8 | Ext Amp | Select, Type / Select, Wait Time | none (Helix only) |
| 9 | CV Out | CV Value | none (Helix only) |
| 10 | CV Out | CV Min, CV Max | none (Helix only) |
| 11 | CV Togl | Dim Value, Lit Value, Type | none (Helix only) |
| 12 | Hotkey | Modifier 1..3, Key-stroke, Type | FS |
| 13 | Hotkey | Modifier 1..3, Key-stroke, Wait Time | Instant |
| 14 | Preset | Preset | FS |
| 15 | Snpsht | Behavior, Press, Release | FS |
| 16 | Looper | Behavior, Press, Release | FS |
| 17 | Looper | Function, Wait Time | Instant |
| 18..21 | MIDI CC, BankPC, MMC, CV Out | | Instant (18..20) |

- Short names: 8-byte slots at `0x28e3c628` (`0x28de663c(cc, type)` returns type's; the Command value text, called at `0x28dbd338`).
- Parameter count per type (the Command knob included): bytes at `0x28e3c6d8` (`0x28de66e4`; callers `0x28dbd1fa`, `0x28dbd860`, `0x28dbdabc`, `0x28de3210`, `0x28e1d086`).
- Knob labels: 7 x 16-byte strings per type at `0x28e3c76c`. Parameter kinds: 7 bytes per type at `0x28e3d10c`; kind k's range is the 4 bytes at `0x28e3c6f0 + 4k` (byte 1 the maximum; kind 22 is "no parameter"). Setting a parameter of kind `0xd` or `0x15` on an FS slot also sets that footswitch's momentary flag (`0x28dd83e4`).
- **Types 7..11 are complete in every table but the HX Stomp never offers them**, and its fire function does nothing for them. A preset holding one is harmless to stock 3.80: the Command knob sits on None (the type-to-choice map returns 0), the name and labels come from the type's own rows, and the footswitch gets no node (below), so a press reaches nothing.

## The Command knob [verified offline]

- Choices per slot: words at `0x28e3c5f4`, one per slot (Instant 6, FS 10, EXP 2), read only by `0x28de57bc(cc, s)` (called once, `0x28dbd354`).
- The FS choices after None are the 9 bytes at `0x28e3d1a9`: types 1, 2, 4, 5, 6, 12, 14, 15, 16. Instant: the 5 bytes at `0x28e3d2c5`: 18, 19, 20, 13, 17. EXP: type 3 alone.
- `0x28de57d0(cc, s, type)` gives the choice index of a type (the knob's position; 0 for a type not on the slot's list). It is unrolled for exactly 9 FS entries. Callers: `0x28dbd366`, `0x28dbd4d0`, `0x28dbd9fa`.
- `0x28de64a0(cc, s, type, delta)` steps to the next type on the slot's list, also unrolled; its only caller is the Command knob's turn, `0x28dbd6bc`, which then stores the type with `0x28de6a18(cc, s, type)`.
- So a new FS choice needs the count word, both mapping functions and the name; the lists cannot grow in place (the FS list is followed by a string).

## Firing a command [verified offline]

- `0x28de5cd4(cc, s, state, momentary)`: with state non-zero it switches (tbh at `0x28de5cec`) on type - 1 for types 1..16, else through a word table at `0x28de5d68` (the "release" side). Types 3, 7..11, 13 and 14 do nothing on either side.
- Three callers:
  - `0x28dd1298` and `0x28dd1342`, in the stomp toggle `0x28dd10c0` (footswitch function 2, Stomp N): the press flips the footswitch's command state (`[fs + 0x20]`, fs = `0x28dd7218(0x28d96084(), k)`), fires the slot with it, then sets the LED colour from `0x28db7e1c(0, state)` and refreshes the LED. `0x28dd1298` is the Looper (type 16) branch; type 15 (Snapshot) with Behavior 1 goes elsewhere (`0x28dd144a`); every other type goes through `0x28dd1342`.
  - `0x28de36b6`, in snapshot recall (`0x28de2f90` and on, per snapshot `0x260` bytes): an FS command whose stored state differs in the new snapshot is fired again with that state.
- So a command is fired by a footswitch only when that footswitch's function is Stomp N: FS3 with its default TAP/Tunr function never reaches its Command Center slot.
- The Home screen's footswitch label (`0x28dc7288(home, k)`) handles only types 14 (Preset), 15 (Snapshot) and 16 (Looper); every other type leaves the label as it was.

## Use in HXtra

- [Tap command](../features/tap-command.md) (#108): a Tap FS command stored as type 9.
