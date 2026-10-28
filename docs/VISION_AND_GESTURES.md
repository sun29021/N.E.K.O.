# Vision, screen analysis and gestures

## 1. Screenshot questions (v0.1)
**How:** press the capture button (⧉) on the HUD. The HUD hides for 250 ms, the screen under your
mouse is captured, the HUD returns and says "Screenshot attached". Then type your question
("explain this error", "what's wrong with this dialog?", "explain this chart").

**Where the image goes:** it is downscaled so the longest side is ≤1344 px (`vision.max_image_side`),
kept in RAM, and sent **only** to the local vision model the router picks (e.g. `gemma3:4b` via
Ollama on 127.0.0.1). It is not written to disk (`vision.retain_screenshots = false`) and not stored in
the database. Only your question text and the reply are kept in history.

**Without a vision model** N.E.K.O. says so and points to MODEL_GUIDE. The text models can't see.

**Safety:** text inside screenshots is untrusted. Vision turns have tools disabled, and the
conversation stays "tainted" for 3 turns, so any action afterwards needs your approval.

**Not implemented:** continuous screen watching (deliberately never), selected-window capture (P1),
region selection (P1), OCR-first pipeline (P2, `tile_boxes()` helper exists).

## 2. Model choice for a 4 GB GPU
| Model | Size | Fit | Notes |
|---|---|---|---|
| `gemma3:4b` | 3.4 GB | partial GPU | default vision candidate; Gemma Terms of Use |
| `qwen2.5vl:3b` | 3.2 GB | partial GPU | strong on documents/UI; 3B licence is research-only (verify) |
| OCR engines (Tesseract / Windows.Media.Ocr) | small | CPU | P2: extract text first, then reason with a text model (cheaper, more reliable for error dialogs) |

Expect several seconds per image. Vision encoders add hundreds to thousands of tokens per image
(estimate; **benchmark needed**, PERFORMANCE_PLAN P4).

## 3. Honesty rules for the Vision role
The vision prompt says: describe only what is visible, quote on-screen text exactly, state
uncertainty, and never assume hidden application state.

## 4. Hand gestures (Research, not built)
- Candidate: Google **MediaPipe** Hands / Gesture Recognizer (Apache-2.0 per general knowledge;
  **not re-verified this session**). Runs on CPU from a webcam at ~15–30 fps (estimate).
- Proposed default mappings, all configurable: open palm → pause/stop speech; hand raised → show
  HUD; pinch → select highlighted item; thumbs-up → *non-destructive* confirmations only.
- **Gestures can never approve** Level 2/3 actions, purchases, credentials or deletions. The approval
  dialog ignores gesture input by design.
- The camera is off by default. When it's on, the HUD would show a persistent camera indicator, and
  frames would be processed in memory only.
- Prerequisites: a webcam, the `mediapipe` package (Python version support must be checked), and a
  feasibility test for CPU load alongside the LLM.
