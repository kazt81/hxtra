# HXtra features

Everything HXtra adds to the HX Stomp, where to find it, and every setting. The [setup page](https://wisemandenny.github.io/hxtra/web/) builds all of these into one firmware; with [`build.py`](building.md) you choose them with switches.

| Feature | Where it is on the HX Stomp | Switch |
|---|---|---|
| [Tuner settings](#tuner-settings) | The tuner's own settings, on a third page: open the tuner and page right past Trails, Offsets and String 6 | `HX_TUNER=1` |
| [BPM](#bpm) | Home screen: the tempo at the top left, the beat dot beside the preset number · Global Settings > BPM Display | `HX_BPM=1` |
| [Tap LED color](#tap-led-color) | The TAP footswitch: its ring, and its icon and label on the Home screen · Global Settings > Displays, under Tap Tempo LED | `HX_TAP_COLOR=1` |
| [Preset LED color](#preset-led-color) | Each preset's footswitch in Preset footswitch mode, in its own colour: its ring, and its icon on the Home screen · Global Settings > Displays, page 2 | `HX_PRESET_COLOR=1` |
| [DSP usage display](#dsp-usage-display) | Edit view and model browser: each block's or model's share, the total at the top right · no settings | `HX_DSP_METER=1` |
| [Breathing line](#breathing-line) | Home screen: the line between the signal flow and the knobs · Global Settings > Breathing Line | `HX_BREATHING_LINE=1` |
| [Real block names](#real-block-names) | Model browser and Edit view: each block's title · no settings | `HX_REAL_NAMES=1` |
| [FX Loop gate](#fx-loop-gate) | The FX Loop and Return blocks: three more knobs, Gate, Threshold and Decay | `HX_FX_GATE=1` |
| [Long press](#long-press) | FS1–FS5 in Stomp footswitch mode · Global Settings > Footswitches, pages 2 to 5 | `HX_LONG_PRESS=1` |
| [More snapshots](#more-snapshots) | The snapshot footswitches, with Footswitch Mode on Snapshot · Global Settings > Footswitches, Snapshot 4-6 Sel | `HX_MORE_SNAPSHOTS=1` |
| [Metronome](#metronome) | Model browser: Looper > Metronome > Metronome · the block's knobs | `HX_CLICK=1` |
| [USB monitoring](#usb-monitoring) | Path A's output to the computer instead of Main L/R · Global Settings > Ins/Outs, page 3 · a DSP feature on the setup page | `HX_USB_MONITOR=1` |
| [GR meter](#gr-meter) | Home screen and the compressor's Edit view, lit by a compressor · knobs on six compressors | `HX_GR=1` |
| [Boot screen](#boot-screen-hx-stomp-only) | The screen at power-on · set when you build | `--splash`, `--splash-text` |
| [NAM A2 Lite](#nam-a2-lite) | Model browser: Amp > NAM | `HX_NAM_SLOTS=3`, `2`, `1`, `0` (off); unset, the most that fit |

Every feature here has run on an HX Stomp from RAM before it was released. The setup page builds them all, but some only when you tick their boxes: the **DSP features** (how many NAM A2 Lite blocks, the GR meter, the Metronome and the FX Loop gate; at first 2 NAM blocks and all three ticked) and Real block names. The DSP features share the DSP's spare memory, so the page shows what is left as you tick, and won't let you tick one that doesn't fit: fewer NAM blocks leave room for more of the others ([NAM A2 Lite](#nam-a2-lite)). Each is off in a plain `build.py` build until its switch is set (an environment variable, or a `build.py` option), and switches combine:

```sh
HX_TUNER=1 HX_BPM=1 HX_DSP_METER=1 HX_MORE_SNAPSHOTS=1 HX_TAP_COLOR=1 python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf
```

## Custom settings

The features' settings are in Global Settings, each feature in a section of its own after Displays (turn the knob right past Displays): **BPM Display**, then **Breathing Line**, each with its own icon by the title (see [Icons](icons.md), which also makes an icon library of every stock icon from your firmware file). The section strip at the top has room for the six stock sections only, so none of its icons is lit while you are in a feature's. A build with none of these features has no sections after Displays. Long press's settings are in **Footswitches** instead, after FS5 Function, and More snapshots' after them (after FS5 Function without Long press), Tap LED color's in **Displays**, under Tap Tempo LED, Preset LED color's on a second Displays page, and USB monitoring's in **Ins/Outs**, on page 3.

| Feature | Setting | Values | What it does |
|---|---|---|---|
| BPM | **Font Size** | XL, **L** (default), M, S, Off | The tempo's size. XL is digits only: no ` X` with MIDI clock and nothing with no tempo. Off hides the tempo |
| BPM | **Color** | **White** (default), Gray, Red, Orange, Yellow, Green, Cyan, Blue, Purple, Tempo | The tempo's and the dot's colour. Tempo follows the TAP footswitch's colour (Tap LED Color; stock red in a build without it) |
| BPM | **Dot Position** | **Left** (default), Right, Both, Off | Where the beat dot sits, beside the preset number. Off hides the dot; with Font Size Off too the BPM display is off and the TAP ring blinks as stock |
| Tap LED color | **Tap LED Color** | **Red** (default), DkOrange, LtOrange, Yellow, Green, Teal, Blue, Violet, Pink, White, Rainbow, Random | The TAP footswitch's colour: its ring as it blinks the tempo, and its switch icon and TAP/TUNER label on the Home screen. Rainbow steps the ring round the colour wheel at each beat; Random picks a new colour at each beat. Both keep a white label. In Global Settings > Displays, under Tap Tempo LED. |
| Preset LED color | **Preset LED** | **Red** (default), DkOrange, LtOrange, Yellow, Green, Teal, Blue, Violet, Pink, White | In Preset footswitch mode, the colour of a preset without its own while it is selected: its ring, and its switch icon on the Home screen. In Global Settings > Displays, page 2. |
| Preset LED color | **This Preset** | **None** (default), Red, DkOrange, LtOrange, Yellow, Green, Teal, Blue, Violet, Pink, White | The current preset's own colour, saved with the preset. In Preset footswitch mode its ring and icon are lit in it while it is selected and dimmed while it is not. In Global Settings > Displays, page 2. |
| Long press | **FS1 Hold Function** … **FS5 Hold Function** | Off, Tuner, FS4, FS5, FS6 … FS10 (defaults FS6 … FS10) | What holding that footswitch for 1 s does. FS4 and FS5 are external switches. In Global Settings > Footswitches, pages 2 and 3, after FS5 Function. |
| Long press | **FS6 Function** … **FS10 Function** | Tuner, Stomp 6 … 10, Bank Up, Bank Dn, PresetUp, PresetDn, SnpshtUp, SnpshtDn, FS Mode>, <FS Mode, AllBypas, TogglEXP, GlobalEQ (default Stomp) | What that virtual footswitch does, as FS3 … FS5 Function do for the real ones, with Tuner in place of TAP/Tunr, and GlobalEQ added. In Global Settings > Footswitches, pages 4 and 5. |
| More snapshots | **Snapshot 4-6 Sel** | **Hold** (default), Tap | How the snapshot footswitches reach snapshots 4–6 in Snapshot footswitch mode. Hold: hold FS1 for 1–3 or FS2 for 4–6, then tap the one you want; it selects when you let go, and the footswitches stay on that bank until you hold one again, tap one or load a preset. Tap: press the lit footswitch again to flip between 1–3 and 4–6. See [More snapshots](#more-snapshots). In Global Settings > Footswitches, page 2, or page 5 with Long press. |
| Breathing line | **Color** | White, Red, Green, Blue, Fire, Ice, Sunset, Ocean, Aurora, Neon, **Rainbow** (default) | The line's colours. The gradients flow along the line: Fire is red, orange and yellow; Ice blue, cyan and white; Sunset purple, pink and orange; Ocean deep blue, blue and aqua; Aurora green, sky blue and violet; Neon magenta, indigo and cyan; Rainbow every hue. Where the motion dims the line, the colours dim with it. |
| Breathing line | **Type** | Off, Steady, **Breathe** (default), Cylon, Comet, Heart, Sparkle | How it moves. Breathe slowly fades the whole line in and out. Cylon sweeps a wide light from end to end and back, slowing at the ends, with a trail behind it. Comet shoots a light across with a long tail. Heart beats lub-dub from the middle. Sparkle twinkles at random. Steady holds the full colour. Off gives back the stock line. |
| Breathing line | **Speed** | 1 … 10, Tempo (default **4**) | One cycle takes 8 s at 1, 4 s at 4, 0.8 s at 10. Tempo follows the tempo (Global BPM or Preset BPM, as Tempo Select says): a beat a cycle for Heart, two for Breathe, Cylon and Comet, four for Steady, eight for Sparkle; with no tempo it runs at 4. |
| USB monitoring | **Path A Out** | **Main L/R** (default), Send/USB, USB Only, Main+Snd | Where path A's Output block goes. Send/USB sends it to the computer on USB 3/4 instead of Main L/R, so a DAW monitors it; Main and the phones play only what comes back on USB 1/2. The Send jacks carry the same sound. USB Only sends it to the computer alone, the Send jacks silent. Main+Snd keeps it on Main L/R and copies Main to the Send jacks and USB 3/4 too. In Global Settings > Ins/Outs, page 3, after the stock settings. |

Every feature's settings are virtual settings: HXtra serves their IDs itself and keeps their values in spare records of the Global Settings store, which the HX Stomp saves with the rest. `tools/setting_ids.py` assigns each its ID and place. A setting no build has stored yet, or whose stored value is out of range, shows its default. Builds before virtual settings kept these settings on real IDs, so the first virtual build starts them on their defaults.

## Tuner settings

<!-- demo: tuner -->
<img src="https://github.com/user-attachments/assets/7decba81-b026-4fb5-95f9-6c8899b2e47c" width="100%" alt="The tuner: Activate set to Press, so one press opens it, then Lock On and its knobs no longer change">

With `HX_TUNER=1`, the tuner's own settings get a page of their own, third: page right past Trails, Offsets and String 6. The string pages (Strings 5–3, then 2 and 1) follow it: few players use the per-string offsets, so the page comes before them. Its knobs set them as the stock pages' knobs do: turn to change, press to go back to the default.

| Knob | Values | What it does |
|---|---|---|
| **Activate** (Tuner Activation) | **Hold** (default), **Press** | A footswitch assigned TAP/Tunr normally taps the tempo, and holding it opens the tuner. On **Press**, pressing it opens the tuner at once and the tempo is no longer tapped. It follows the assignment, so it works on whichever footswitch has TAP/Tunr. |
| **Lock** (Lock Tuner Settings) | **Off** (default), **On** | On stops the tuner's other settings (Output, Refrnc, Type, Trails, Offsets) from changing: knob turns and the knob presses that reset an item to its default are ignored. Paging still works, and this page's knobs still turn, so Lock can be turned off where it was turned on. |

Both keep their values (setting IDs 29 and 104) from builds that had them in Global Settings > HXtra.

## BPM

<!-- demo: bpm -->
<img src="https://github.com/user-attachments/assets/62783af2-506f-4878-80ed-e2705acba51c" width="49%" alt="Tapping TAP: the tempo and its beat dot follow"> <img src="https://github.com/user-attachments/assets/4579e864-8a7d-46fd-a764-ec5cd102b6e9" width="49%" alt="Global Settings, BPM Display: Font Size, Color and Dot Position">

The Home screen shows the tempo at its top left, and a beat dot beside the preset number that lights with the TAP footswitch's ring, red on a tap.

- **The tempo** is the one the HX Stomp is using, the global or the preset's as Tempo Select says, as a whole number. It shows ` X` after it while the tempo comes from MIDI clock (the tempo screen's Extrnl), and `--` with no tempo.
- **The dot** keeps the beat in every footswitch mode, and with Tap Tempo LED off too: the ring then stays dark while the dot blinks.
- **Settings** (Global Settings > BPM Display): Font Size, Color (the tempo's and the dot's; Tempo takes the TAP footswitch's colour) and Dot Position (left of the preset number, right of it, or both). Off on Font Size hides the tempo and on Dot Position the dot; both Off turns the display off without a rebuild. See [Custom settings](#custom-settings).

## Tap LED color

<!-- demo: tap-color -->
<img src="https://github.com/user-attachments/assets/29f1b0a3-fa13-4d40-bfb0-cb426b15079d" width="100%" alt="Tap LED Color: red, green, blue, then Rainbow walking the colour wheel, and BPM Display Color Tempo following it">

The TAP footswitch's ring blinks red with the tempo, and its icon and label on the Home screen are red. Tap LED Color (Global Settings > Displays, under Tap Tempo LED) picks another colour for all three, from the colours the HX Stomp gives its other footswitches.

- **The colours** are the stock footswitch palette: each ring colour is the one the HX Stomp lights for a block of that colour, and each icon the stock switch icon of that colour.
- **Rainbow** moves the ring a small step round the colour wheel at each beat: 42 shades blended from the palette's Red, DkOrange, Yellow, Green, Blue and Violet, back to Red, about 21 s round at 120 BPM.
- **Random** lights the ring in a random colour of the palette at each beat, never the same twice running.
- With Rainbow and Random, the icon and label stay White, and a tap or a preset change re-lights the ring in its current colour without moving on.
- **External MIDI clock:** the ring keeps the stock colour it blinks with then. **Tap Tempo LED** still decides whether the ring blinks at all.
- **BPM Display's Color Tempo** gives the tempo and the beat dot the TAP footswitch's colour, the ring's current one with Rainbow and Random.

## Preset LED color

In Preset footswitch mode the HX Stomp lights the current preset's ring red, with a red switch icon on the Home screen, and leaves the other two presets' rings off. HXtra gives each preset a colour of its own, from the same palette as Tap LED color.

- **This Preset** (Global Settings > Displays, page 2) sets the current preset's colour. Save the preset to keep it: the colour is stored in the preset itself, so it goes with the preset when you move, export or restore it.
- **Selected**, a preset's ring and icon are lit in its colour. **Not selected**, a preset with a colour shows it dimmed (the shade the HX Stomp uses for a bypassed block of that colour), so you can see which footswitch holds which preset.
- **A preset without a colour** is lit in **Preset LED**'s colour (red by default, as stock) while it is selected, and off while it is not.
- **A change** shows when you go back to the Home screen.
- **Other modes** keep the stock colours: Stomp mode's rings are the blocks' colours, Snapshot mode's the snapshots'.

## DSP usage display

<!-- demo: dsp-usage -->
<img src="https://github.com/user-attachments/assets/fb8644f3-b5ab-4803-b3be-fefcfb23c7b3" width="100%" alt="Browsing bass amps: the DSP total previews each model, then the added block shows its share">

In the Edit view, each block in the signal-flow row shows its share of the DSP in per cent, in black on the block. The top right corner shows the blocks' total out of 75, e.g. `47/75`.

In the model browser, each model shows the share it would take, in white between its icon and its name, and the top right corner shows the total as in the Edit view.

Global Settings › DSP Usage Display has three settings:

- **Model Browser** (On, Off): the shares in the model browser, On by default. The browser's model names stay where the meter moved them, with room for the shares, even when it is Off.
- **Edit Blocks** (On, Off): the shares on the Edit view's blocks, On by default.
- **Total** (Small, Large, Off): the total in the top right corner. **Small**, the default, draws it in the meter's 3x5 digits at 2x, about half the title's height, in the same corner, so a long name can still run into it. **Large** draws it in the title's font, as before these settings. **Off** draws nothing there, so a long preset name or block title isn't covered.

75 is what blocks may use: the firmware's preset limit of 90%, less the 15% it always keeps. The numbers are the firmware's own fixed cost of each model, the same ones it uses to decide whether a block fits, not a measured load.

## Real block names

<!-- demo: real-names -->
<img src="https://github.com/user-attachments/assets/607728e6-773b-41ae-9619-5a30ca2f50ad" width="100%" alt="The model browser's Distortion list by real names: Xotic EP Booster, Klon Centaur, Ibanez TS808">

Line 6 names its models after the gear they're based on with a twist (Deez One Mod, US Double Nrm). With Real block names, the model browser and the Edit view title each block by that gear instead: Boss DS-1 Mod, Twin Reverb Nrm. The names come from [helixhelp.com/models](https://helixhelp.com/models)' "based on", at most 16 characters.

- **Off unless you ask:** a checkbox on the setup page, unticked, or `HX_REAL_NAMES=1` for `build.py`.
- **What keeps its name:** Line 6 originals, utility blocks and titles that are already real.
- **Presets** keep the same model IDs, so a preset is the same with or without real names, and opens on stock firmware as usual.

## Breathing line

<!-- demo: breathing-line -->
<img src="https://github.com/user-attachments/assets/d492b0aa-1151-42c6-b84a-27f6fd36e5d8" width="49%" alt="Breathing Line types, colours and speeds on the Home screen, on the unit"> <img src="https://github.com/user-attachments/assets/dd1085e1-c51d-4377-8dee-26b8ce5e1423" width="49%" alt="The same, the screen alone: Steady, Breathe, Cylon, Heart, Sparkle, then Aurora, Ice, Fire and Tempo">

Just for fun: the line across the middle of the Home screen, between the signal flow and the knobs, comes alive in the colours, motion and speed you pick. It starts on Rainbow, breathing once every 4 s.

- **Where it shows:** on the Home screen only. Other screens stay stock, and the line stops animating while you're on them.
- **The selected part of the line** is still thicker, as on the stock line, and **Off** gives the stock line back.
- **Settings** (Global Settings > Breathing Line): Color, Type and Speed. See [Custom settings](#custom-settings).

## FX Loop gate

A noise gate built into the FX Loop and Return blocks, as the Input block has one, so a noisy pedal in the loop doesn't take a Noise Gate block of its own ([#69](https://github.com/wisemandenny/hxtra/issues/69)). It gates what comes back from the loop, before the block's Return level and Mix; the dry signal and the Send are not gated.

| Knob | Values | What it does |
|---|---|---|
| **Gate** | **Off** (default), On | Turns the gate on. Off, the block sounds as on stock firmware. |
| **Threshold** | −96 … 0 dB (default **−48**) | Below this level the returned signal is muted. |
| **Decay** | 0.01 … 1 s (default **0.1**) | How fast the gate closes. |

- **On the setup page:** a box among the DSP features, ticked at first, or `HX_FX_GATE=1` for `build.py`. HX Stomp only.
- **DSP:** each FX Loop and Return block costs about 0.2% more (0.4% stereo), whether its gate is on or off. A preset already at the limit with one of these blocks may not load.
- **Stereo blocks** gate each side on its own, not linked.
- **Presets** saved with the gate keep its knobs. Opening such a preset on stock firmware, or in HX Edit, is not tested yet.

## Long press

<!-- demo: long-press -->
<img src="https://github.com/user-attachments/assets/50a6ecf0-6d87-4556-8ffd-035e4b40987b" width="49%" alt="Tapping and holding FS2, holding FS1 for the tuner, then the Hold and FS6 to FS10 Function settings"> <img src="https://github.com/user-attachments/assets/f0261c29-ef31-4527-8d96-21ef176b67aa" width="49%" alt="A block's Bypass Assign: MIDI In set to the virtual footswitch FS6, then holding FS2 toggles it">

In Stomp footswitch mode, each of FS1–FS5 can have a Hold action (Global Settings > Footswitches, pages 2 and 3: FS1 Hold Function … FS5 Hold Function), and each virtual footswitch FS6–FS10 a function (pages 4 and 5: FS6 Function … FS10 Function). Holding the switch for 1 s runs it; a tap still toggles the switch's own blocks, on release instead of on press, since the press can't tell yet whether it will become a hold.

- **Tuner** opens the tuner, as holding TAP does.
- **FS4, FS5** press that footswitch, as an external switch would.
- **FS6 … FS10** are virtual footswitches. Each toggles the blocks you assign to it: in a block's Bypass Assign, set MIDI In to FS6 … FS10 (the first five steps up from Off; the knob's label reads FootswIn while it's on one). The assignment is saved in the preset, and parameters assigned to the same footswitch through Controller Assign follow it too. They are MIDI CC 20–24 underneath, which is how HX Edit and other MIDI gear see them.
- **FS6 Function … FS10 Function** give a virtual footswitch the same choices FS3 … FS5 Function give a real one, with **Tuner** (opens the tuner) in place of TAP/Tunr, since a hold has no use for a tap. **Stomp**, the default, toggles its blocks as above. The others do what that function does on a press and release of a real footswitch: **Bank Up/Dn** opens the bank in Preset mode, **PresetUp/Dn** and **SnpshtUp/Dn** step the preset or snapshot, **FS Mode> / <FS Mode** step the footswitch mode, **AllBypas** bypasses everything, and **TogglEXP** switches EXP 1/2 and toggles the virtual footswitch's blocks. **GlobalEQ**, which no real footswitch offers, opens Global EQ for room or stage correction; it does nothing while the tuner is open. While Global EQ is open, however you got there, a press of any footswitch goes back to Home, as one leaves the tuner, and toggles nothing. Holds act only in Stomp mode, so after a function that leaves it (FS Mode, Bank), come back with a real footswitch or the menu. A MIDI CC 20–24 from outside still toggles the blocks, whatever the function.
- A switch with Hold **Off**, a momentary switch, and the Preset and Snapshot footswitch modes work as stock.

## More snapshots

<!-- demo: snapshots -->
<img src="https://github.com/user-attachments/assets/8ce9d86c-cffb-491e-9c47-0430a02a4af7" width="100%" alt="Snapshots 1 to 3, the lit footswitch again for 4 to 6, and again back to 1 to 3 (Snapshot 4-6 Sel on Tap)">

With Footswitch Mode on Snapshot, the three footswitches select snapshots 1–3 as usual, and the same footswitches can select a second bank of three, snapshots 4–6. **Snapshot 4-6 Sel** (Global Settings > Footswitches: page 2, or page 5 with [Long press](#long-press)) sets how you get to them:

- **Hold** (the default): hold FS1 for 1 s and the footswitches select snapshots 1–3; hold FS2 and they select 4–6. A hold changes no sound: the footswitch labels show that bank's snapshots, none lit, while the camera icon at the top right stays on the snapshot you hear. Holding the footswitch for the bank you hear shows that bank as usual, its snapshot lit. Then tap a footswitch to select its snapshot in that bank. A tap selects when you let go of the footswitch, not when you press it, since a press can still become a hold; a press you let go of before 1 s is a tap. Tapping the lit snapshot does what Reselect Snapshot says (below). Holding FS3 does nothing.
- **Tap:** press the lit footswitch again and the same footswitches select snapshots 4–6; press the lit one again to come back. Taps select as stock does, a moment after the press, and the lit footswitch never does what Reselect Snapshot says. This is how More snapshots worked before the setting.

In Hold:

- **The bank the footswitches are on** changes only when you hold FS1 or FS2, tap a snapshot footswitch (or send MIDI CC 49–51), or load a preset. After a tap they're on the bank of the snapshot it selected, and a preset load puts them on 1–3. Nothing else moves them: not MIDI CC 69, HX Edit, SnpshtUp or SnpshtDn, the Command Center, a save, leaving Snapshot mode, the tuner, or switching the setting. When one of those changes the snapshot, the labels stay on the footswitches' bank, none lit if you hear the other bank, and your next tap selects in that bank. A snapshot copy or swap (touch two snapshot footswitches and hold one) acts on the snapshots you hear, whichever bank the labels show.
- **Reselect Snapshot:** set to recall, tapping the lit snapshot recalls it, as stock. Set to go back to the previous snapshot, it goes back to the snapshot you were on before, in either bank: on 2, hold FS2 and tap FS3 for 6, tap FS3 again for 2, then FS2 again for 6. The previous snapshot is the one you were on before the last change, however it was made (a footswitch, MIDI, HX Edit, the Command Center). Going back from MIDI CC 69, HX Edit or the Command Center stays within the bank (below).
- **Switching to Tap and back** keeps the footswitches on the bank you hear, as long as you pressed a snapshot footswitch, picked a snapshot from the Command Center, or moved between 1–3 and 4–6 while on Tap. If you held FS1 or FS2 for the other bank, switched to Tap and did neither, they are still on the bank you held when you come back to Hold.
- **Two footswitches:** FS1+FS2 and FS2+FS3 pressed together still switch to Preset mode, and FS1+FS3 together still does nothing, as stock. Two footswitches pressed one after the other, rather than together, each select when let go, so the one you let go of last wins (stock selects in the order they were pressed).
- **MIDI CC 49–51**, which press FS1–FS3 from MIDI, act as taps: each selects its snapshot in the bank the footswitches are on, and on the lit snapshot does what Reselect Snapshot says. They select on the message that presses the footswitch, as stock does, and never hold, so to change the bank over MIDI use CC 69's values 3–5 (below).

In both:

- **Which bank you hear:** in 4–6 the camera icon at the top right shows 4, 5 or 6. On Tap the footswitch labels do too. In Hold they show the bank the footswitches are on, with its numbers and its snapshots' names (a renamed snapshot shows its name), and one is lit only when that is the bank you hear.
- **New snapshots:** the first time you go to a preset's 4–6, each one starts as a copy of the snapshot you came from. Edit them as any snapshot: snapshot-controlled parameters, block bypass, tempo and names are kept per snapshot.
- **Saving:** a save keeps all six with the preset. Saving while in 4–6, you hear the matching snapshot of 1–3 for a moment, as the save writes 1–3 first. In Hold, a tap in that moment selects nothing; tap again.
- **Stock firmware and HX Edit:** a preset saved with 4–6 still loads on a stock firmware, as snapshots 1–3, and the stock firmware drops 4–6 if it saves the preset again. HX Edit opens, exports and imports these presets, but its exports (`.hlx`) and backups (`.hxb`) hold snapshots 1–3 only. Snapshots 4–6 live on the HX Stomp.
- **Next and previous:** once a preset has snapshots 4–6 (saved with it, or made since it loaded), the SnpshtUp and SnpshtDn footswitch functions and MIDI CC 69's next and previous (values 8 and 9) step through all six: next on 3 goes to 4 and next on 6 to 1; previous on 1 goes to 6 and previous on 4 to 3. A preset with only 1–3 wraps within them, as stock.
- **MIDI CC 69:** values 0–2 select snapshots 1–3 and values 3–5 select snapshots 4–6, whichever bank you're in. Selecting 4–6 on a preset that has none yet makes them, as the footswitches do. Sending the lit snapshot's own value does what Reselect Snapshot says, as stock.
- **HX Edit's snapshot buttons** select within the bank you hear, as they always have with More snapshots: in 4–6, its snapshot 1 selects 4.
- **Reselect Snapshot outside the footswitches:** right after a move between 1–3 and 4–6, the snapshot you're on is also the "previous" one within its bank, so Reselect Snapshot set to go back stays put for MIDI CC 69's lit value, HX Edit and, in Hold, the Command Center's lit snapshot, rather than jump to a snapshot of the other bank. Otherwise they go back within the bank, as stock. In Hold, the lit footswitch goes back across the banks (above); on Tap it flips, and so does the Command Center's lit snapshot.

## Metronome

<!-- demo: metronome -->
https://github.com/user-attachments/assets/f25be41c-3ab0-45a1-87fa-99cd50194933

A click track in time with the tempo, as a block: add it from the model browser, Looper > Metronome > Metronome, anywhere in the signal flow. It is a mono effect block, listed under Looper so it's easy to find; it isn't a looper. In the signal flow it is teal, lit when on and dim when off, and its icon is a metronome.

| Knob | Values | What it does |
|---|---|---|
| **Time** | a note value, synced to the tempo (**1/4** by default), as a delay's Time | The beat: 100 ms to 8 s. |
| **Level** | −60 … +6 dB (default **−14**) | The click's volume. |
| **Accent** | **Off** (default), 2 … 12 | Every nth beat is a downbeat, a higher click (2 kHz instead of 1 kHz). |
| **Thru** | Off, **On** (default) | On passes your signal with the click under it; Off gives the click alone. |

- **The beat** starts when the block does, and a new tempo or Time counts from the last beat. Tapping the tempo doesn't yet move the beat onto your taps, and [BPM](#bpm)'s dot blinks with the TAP ring, not with the click.
- **Presets** store the block as model 181, as the earlier builds that listed it under Modulation did, so presets made with them keep it.

## USB monitoring

The HX Stomp always plays what you play straight to its outputs and phones, and sends the same sound to the computer on USB 1/2: hardware monitoring. To monitor through a DAW instead (software monitoring: hearing your tone with the DAW's plugins on it), set **Path A Out** (Global Settings > Ins/Outs, page 3) to **Send/USB**. Path A's Output block then goes to the computer on USB 3/4 instead of to Main L/R, and Main and the phones play only what the computer sends back on USB 1/2. Record and monitor USB 3/4 in the DAW.

- **Every preset** follows the setting: path A goes to Send/USB on each preset you load, and a turn of the setting switches at once. Path B's own output is not changed.
- **The Send jacks** carry the same sound as USB 3/4: on the HX Stomp they are one output. Leave them unplugged, or expect the sound there too.
- **Send and FX Loop blocks** add their send to that output, so the computer gets it with path A's sound. **Don't use Send/USB with an FX Loop block** (or the 4-cable method): path A's output would go out the Send jacks, through the loop and back in, and feed back.
- **USB Only** sends path A to the computer alone. The Send jacks stay silent, so nothing goes out of them at all: not path A, and not the send of any Send or FX Loop block either. That makes it safe with an FX Loop block in the preset (nothing can feed back), but the loop gets no signal. Choose it when you only monitor through the DAW.
- **Main+Snd** keeps path A on Main L/R and sends what Main plays to the Send jacks and USB 3/4 as well, at 0 dB, without a split or a block of its own: for a second amp, a front-of-house feed or recording the whole chain. Anything a Send or FX Loop block sends is added to it. With the Volume knob on the phones only (Global Settings > Ins/Outs), the knob doesn't change it. Global EQ applies to it on the Send jacks, as it does to Main, but not on USB 3/4. **Don't use Main+Snd with an FX Loop block** either: Main carries the loop's return, which would go back out the Send jacks and feed back.
- **USB Only and Main+Snd** work in the DSP (`src/sharc/usb_monitor.asm`, `src/sharc/main_send.asm`), so USB monitoring is a DSP feature on the setup page: 414 words of Block 3.
- **Saving a preset** with Send/USB or USB Only on stores Send for path A. A stock HX Stomp refuses that value when it loads the preset and keeps path A on Main L/R.
- The stock firmware can reach the same output only from path B: put a block on path B, move the merge to the end (its output is then Send L/R) and turn path A's Output Level down.

## GR meter

<!-- demo: gr-meter -->
https://github.com/user-attachments/assets/50b5cd91-f578-4252-a1df-4b73d8ca1995

A gain-reduction meter on the Home screen and in the compressor's Edit view, lit by the compressor you turn it on in, so you can see how hard it is working. HX Stomp only.

| Knob | Values | What it does |
|---|---|---|
| **Mtr Size** | Off, S, M, L, XL (default **Off**) | The meter's thickness: 5, 10, 15 or 20 pixels. A preset saved with an older build's Mtr Thk opens at S for 1 px, M for 2, L for 3 and XL for 4 or more. |
| **Mtr Pos** | **Middle** (default), Top, Left, Bottom, Right | Where on the Home screen and the Edit view the meter lights up. Middle takes the place of the line across the middle. |
| **Mtr Dir** | **Normal** (default), Reverse | Normal fills left to right or top to bottom; Reverse the other way. |

- **Which compressors:** Deluxe, LA Studio, Kinky, Ampeg Opto, Rochester and Red Squeeze.
- **Edit view:** while one of these compressors is selected, the meter shows in its Edit view too, in the same place and size, so you can set the compressor up while you play. Its lit lights cover what is under them (the preset name at Top, the knob names at Bottom); unlit ones leave it showing. With two metered compressors in a preset, both Edit views show the one whose Mtr Size was set last.
- **With NAM:** the meter's DSP code takes the room of NAM A2 Lite's third block, so a build with it has two NAM blocks at most.

## Boot screen (HX Stomp only)

```sh
python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf --splash my_picture.jpg --splash-text "HXS OS v0.1"
```

- Without `--splash`, the boot picture is the stock one with "HX STOMP" relabelled "HXtra STOMP" (`tools/splash_hxtra.py`). It's made from the firmware's own pixels at build time, so the repo holds no Line 6 artwork.
- `--splash` takes any picture macOS can open (PNG, JPEG, HEIC, ...) at any size. The screen is **320x240**; a 320x240 PNG is used exactly as it is, and anything else is converted to it with macOS's `sips`: scaled to cover the screen and cropped at the centre, or with `--splash-fit fit`, scaled to fit inside it on black. Off macOS, give a 320x240 PNG.
- The loading bar crosses the picture about halfway down, and the text sits on it in the bottom 40 rows, in grey (`0xb1b1b1`), so keep the bottom darkish.
- The boot text reads "v1.1.0", the HXtra version, in place of "Firmware 3.80.0". `--splash-text` replaces it with up to 23 characters: ASCII, and emoji, each of which counts as one, e.g. `--splash-text "HXS OS v0.1 🎸"`.
- Each emoji becomes a colour glyph of the line's font, 18 px tall, level with the capitals. On macOS it's rendered from Apple Color Emoji; `--splash-glyph 🎸=guitar.png` (repeatable) gives your own picture instead, and off macOS it's required. A line with emoji is drawn white, not grey, as the firmware shows a glyph's own colours only on a white line.
- The boot screen is an HXtra feature (`tools/features/splash.py`). The flags set its inputs `HX_SPLASH`, `HX_SPLASH_FIT`, `HX_SPLASH_TEXT` and `HX_SPLASH_GLYPHS`, which work as environment variables too, as the other features' flags do.
- `python3 tools/splash_topo.py out.png [--seed N]` draws a neon contour-map picture to start from; `python3 tools/patch_splash.py export firmware.hxf out.png` saves the picture an image has now.
- The bootloader shows its own copy of the stock picture for a moment at power-on, before the firmware starts; that copy is not changed.

This also changes the image store (part 8 of the 15), and with emoji, the font table (part 7).

## NAM A2 Lite

From upstream [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite), unchanged in this fork but for how the Model knob reads: [Neural Amp Modeler](https://www.neuralampmodeler.com) A2 Lite captures running on the HX Stomp's own DSP. The setup page converts your `.nam` files into User IRs the block reads.

- **Where:** Amp > NAM, a block with ten knobs and a tone stack. It sits on Xenomorph Fuzz Mono's preset ID 555 (that stock model is removed), so HX Edit keeps NAM blocks, and presets made with either build open with the other.
- **Older presets:** presets saved with an earlier NAM build (preset IDs 147 and 148) don't open NAM A2 Lite in this one: re-add the block in those presets.
- **How many blocks:** up to 3 play at once, each its own capture; a further one passes its input through. On the setup page you pick 3, 2, 1 or Off among the DSP features, and fewer leave room for more of the others: 3 blocks leave room for the Metronome and the FX Loop gate, 2 for those and the GR meter. With `build.py`, `HX_NAM_SLOTS` sets it; unset, it's the most that leave room for the DSP features you turned on.
- **Model** reads as the slot number, 4 rather than 4.0, on the HX Stomp. A value between slots (from a MIDI controller) reads as the slot that plays. The HX Stomp XL still reads 4.0.
- **Captures:** none are included. You bring your own `.nam` files, and their licences are up to their authors.

Upstream's [CHANGELOG.md](../CHANGELOG.md) has the NAM changes.
