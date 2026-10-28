# UI/UX specification

> **Update 0.4.0 (2026-10-27): orb-only presence is the default** (`ui.style = "orb"`). There's no panel:
> just the HoloCore (`ui/holo.py`) floating on the desktop with fading subtitles under it
> (`ui/orb_window.py`). Drag to move · click = stop talking/answering · double-click = Command Center ·
> right-click = menu (type a message, ask about my screen, always listen, mute voice, emergency stop /
> resume, hide, quit) · start typing while it's focused = quick input.
> Motion per activity: idle breathes (~5 s); listening = ripples move inward and gold spikes stretch
> with your voice; thinking = inner rings counter-spin fast, bars flicker, sparks fly out; coding = rings
> step like gears, a radar sweep scans, segment bars fill; speaking = ripples move outward with her real
> voice plus a waveform ring. Colour = her emotion: neutral teal, calm sky blue, curious violet, happy
> gold, excited orange, playful pink, caring mint, sad blue, surprised yellow; approval amber, error red,
> offline grey. Gold accents (outer ring, data blocks, antenna dots) stay constant.

> **Update 2026-10-27: "Aurum" is now the default theme** (`ui.theme = "aurum"`; "nebula" below is still
> available). The core is a golden holographic sphere with a **live neural network**, an original
> design inspired by the owner's reference image:
> - Wireframe sphere (7 meridians, 5 latitude rings) rotating in 3D and depth-faded, plus two tilted
>   bands of light shards, orbiting circuit arcs and tick marks, and a glowing ring around a dark "eye".
> - **Neural network:** 110 neurons on the shell, axons to their 3 nearest neighbours, 16 axons to the
>   core. Signals travel along axons. When one arrives, the neuron flashes and (60–85% chance) fires
>   onward, so activity cascades.
> - **Reactions:** every generated word → signals out from the core (≤15/s) · tool call → strong
>   bursts · thinking → rapid internal firing · your voice (listening) → signals arrive from the shell,
>   scaled by mic loudness · N.E.K.O. speaking → outward signals scaled by the **real** Kokoro voice
>   loudness · idle → occasional spontaneous firing · approval → ice-blue steady pulse (distinct colour)
>   · error/offline → still.
> - Aurum colours: bg #0A0805, surface #14100A, border #4A3613, text #F6EEDD, accent gold #FFB224,
>   accent-2 #FF7A1A, hot #FFE6A8; approval ice #7FD4FF; error #FF5C6C.
> - Cost (measured, 150 px HUD core): idle ~10% of one CPU core (12 fps), busy ~29% (24 fps). Hidden = 0.
>   Reduced motion = static frame.

## (Original) "Nebula" design system

An original, restrained science-fiction look: a glowing *synapse core* floating over a dark glass
panel. No copied characters, logos or interface artwork. Colour always means something.

## 1. Surfaces
| Surface | File | Purpose |
|---|---|---|
| Compact HUD | `ui/hud.py` | Always-available floating panel: core, status, model/location/mic pills, latest reply, input, mic, capture, stop, expand, hide |
| Command Center | `ui/command_center.py` | Tabs: Chat · Activity · Memory · Models & Resources · Diagnostics · Settings; header with privacy pill and EMERGENCY STOP |
| Approval dialog | `ui/approval.py` | Risk-coloured, Deny default |
| Tray icon | `ui/app.py` | Show HUD · Command Center · Stop · EMERGENCY STOP · Quit |
| First-run screen | `ui/app.py` `FirstRunDialog` | What runs where, mic/camera policy, model status |

## 2. Core states (`ui/orb.py`, `core/types.AssistantState`)
| State | Colour (primary/secondary) | Motion | Label |
|---|---|---|---|
| idle | cyan #4DE3D8 / #2B6F8F | slow breathing, slow orbit | Ready |
| listening | green #5BE38C | waveform ring follows mic level | Listening... |
| transcribing | ice #7FE7FF | faster arcs | Transcribing... |
| thinking | violet #9C7BFF | fast arcs, lattice nodes pulse in sequence | Thinking... |
| tool | blue #6FA8FF | arcs lock into 4-segment gear | Using a tool... |
| awaiting_approval | amber #FFB547 | steady gentle pulse (never flashing) | Waiting for your approval |
| speaking | cyan + violet | waveform ring (synthetic envelope) | Speaking |
| recovering | gold #FFD27A | slow | Recovering... |
| error | rose #FF5C7A | motion stops | Something went wrong |
| offline | grey #5A6283 | static | Model server offline |

## 3. Tokens
- **Colours:** bg #0B0E1A · surface #121729 · surface-hi #1A2140 · border #2A3360 · text #E6EAF7 ·
  text-dim #8C95B8 · accent #4DE3D8 · accent-2 #9C7BFF · ok #5BE38C · warn #FFB547 · error #FF5C7A ·
  focus ring #FFFFFF. Amber/rose are used only for warnings and errors.
- **Type:** Segoe UI Variable (UI), Cascadia Mono (code/diagnostics); 10 pt base, 13 pt titles with
  2 px tracking.
- **Spacing:** 4 · 8 · 12 · 16 · 24 · 32 px. **Radii:** 8 (controls), 14 (panels), 18 (HUD), pills 9.
- **Elevation:** no drop shadows. Depth comes from the translucent HUD (92 % bg alpha), glow on the core
  and 1 px borders.
- **Iconography:** Unicode glyphs (🎙 mic, ⧉ capture, ■ stop, □ expand, – hide), so no icon assets
  need licensing. The app icon is drawn at runtime.
- **Motion:** 30 fps animation only while visible (timer stops when hidden); state fade 220 ms;
  expand 180 ms. **Reduced motion** stops all continuous animation; state is then shown by colour
  and label only.

## 4. HUD behaviour
- Frameless, translucent, drag anywhere; optional always-on-top (`ui.always_on_top`); opacity
  `ui.hud_opacity` (0.3–1.0).
- Enter sends. Esc hides (tray brings it back). Ctrl+E opens the Command Center. Ctrl+. stops.
  Ctrl+Shift+F12 is the emergency stop (in-app shortcut).
- Shift+click on ■ = emergency stop.
- Location pill: green "LOCAL", amber "LAN:…"/"CLOUD:…".
- It never covers security prompts. Approval dialogs aren't top-most and UAC uses the secure desktop.
  The HUD never imitates Windows dialogs or the login screen.

## 5. Command Center tabs
- **Chat:** streamed conversation; metadata line (model, where processed, tok/s, first-token time,
  memories used, notes such as "part of this model runs on CPU").
- **Activity:** tasks, tool invocations (redacted), audit log.
- **Memory:** search, status filter, table, provenance + "why retrieved" panel; Add/Approve/Edit/
  Delete/Export/Clear history; a deletion note about backups.
- **Models & Resources:** RAM/VRAM bars, GPU temp, CPU %, power, disk, "CPU temperature: not
  measured"; model table; model selection (Automatic or pinned); last routing decision with every
  candidate and its rejection reason.
- **Diagnostics:** run the read-only health check, open the log folder, back up now.
- **Settings:** name, personality, answer length, model profile, voice, speech engine, STT language,
  learning, history, readable/writable folders, computer control, reduced motion, HUD on top.
  Network/cloud/remote are intentionally **not** in the UI.

## 6. Accessibility
Keyboard-reachable controls with accessible names on all icon buttons; visible 2 px white focus ring;
text contrast ≥ 7:1 for body text on bg (#E6EAF7 on #0B0E1A); state is never conveyed by colour alone
(there's always a label); reduced-motion setting.

## 7. High-DPI and multiple monitors
`HighDpiScaleFactorRoundingPolicy.PassThrough` gives crisp fractional scaling. Capture uses the
screen under the cursor. Remembering the HUD position per monitor is a P1 item.

## 8. Error presentation
Errors appear in the status line and chat in plain language with a next step. Technical details go to
the log file, never as stack traces in the UI.

## 9. Not yet verified
None of the UI has been rendered: PySide6 isn't installed on this machine. Visual tuning (sizes,
opacity, glow strength) must happen on first run (TEST_PLAN U1–U12).
