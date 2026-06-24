# Replay Visualizer Replacement Design

**Goal:** Replace the current local replay renderer with the notebook-based replay visualizer, and move the local battle record format closer to the Kaggle/notebook `steps` structure.

**Scope**

- Extract the reusable replay viewer logic from `sample_code/battle-replay-visualizer-visualizer.ipynb` into a Python module.
- Change local battle record generation so the primary structured output is `steps[]`, not `history[]`.
- Route `scripts/local_battle.py --replay-file` through the extracted replay visualizer.
- Keep the current human-readable logs and summary output.

**Current State**

- `battle_viewer.py` is a local custom renderer with its own intermediate frame schema.
- `scripts/local_battle.py` currently stores local match data in a `history[]` structure with per-step metadata plus `visualizer_frame`.
- The notebook replay viewer expects a `steps` list in the same shape produced by `visualize_data()`, with optional step extras layered on top.

**Target Architecture**

- New module: `replay_visualizer.py`
  - Owns the extracted notebook viewer HTML/CSS/JS template.
  - Exposes a pure function to write replay HTML from `steps`.
  - Exposes a record-aware wrapper that reads local record JSON and emits replay HTML.
- `scripts/local_battle.py`
  - Builds a Kaggle-like/local-compatible `steps[]` list during match execution.
  - Stores that `steps[]` list as the primary detailed replay structure in `record-file`.
  - Uses `replay_visualizer.py` for `--replay-file`.
- Record JSON
  - Keeps top-level local metadata such as `status`, `winner`, `agent_a`, `agent_b`, `summary`.
  - Replaces `history[]` as the primary replay payload with `steps[]`.
  - Each `steps[i]` should contain the viewer-compatible `visualize` step data and any local extras we want to preserve.

**Data Model Direction**

- Prefer a local record schema shaped like:
  - `steps`: ordered list of replay steps
  - `steps[i]["visualize"]`: one replay step compatible with notebook viewer rendering
  - `steps[i]["player_index"]`, `selected`, `selected_options`, `context_name`, `select_type_name`, and similar local debug fields as optional local extras
- This keeps replay rendering close to Kaggle/notebook expectations while preserving local debugging value.

**Migration Strategy**

1. Extract replay visualizer code into a clean Python module without notebook-only cells.
2. Add a conversion path from current sample local records to the new `steps[]` shape for tests.
3. Update match execution to populate `steps[]` directly.
4. Switch replay HTML generation in `local_battle.py` to the new module.
5. Update tests and README to describe the new replay path and record shape.

**Tradeoffs**

- Keeping only `history[]` would preserve local compatibility but force a custom adapter forever.
- Fully imitating Kaggle episode JSON would be more uniform, but would add extra structure that local tools do not currently need.
- The chosen direction keeps top-level local metadata while making replay payloads structurally compatible with the notebook visualizer.

**Verification Strategy**

- Unit tests for replay HTML generation from local records.
- Unit tests for record JSON shape and step content.
- End-to-end local battle test proving:
  - `record-file` contains `steps[]`
  - `replay-file` is generated
  - replay HTML contains notebook viewer markers
