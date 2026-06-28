# CHANGES — new-version branch

## Files Changed

### 1. `app/main.py`
- **CORS fix**: Changed `allow_credentials=True` → `allow_credentials=False`. The app has no cookie/session-based auth, so credentials were never needed. `allow_origins=["*"]` is kept so LAN devices (phones, etc.) can reach the server.
- **Rate limiter activated**: Added `limiter.init_app(app)` after `app` creation. Without this call, the configured SlowAPI `default_limits=["10/minute"]` was never enforced — the `Limiter` object existed but its before-request hooks were not registered with FastAPI.

### 2. `Dockerfile`
- **Workers fix**: Changed `--workers 2` → `--workers 1`. Task state (`active_tasks`, `active_websockets`, `cancel_events`) is stored in plain in-memory dicts scoped to a single process. With 2+ workers (separate OS processes), a download started on one worker could not have its WebSocket progress found on another. The app is fully async, so one worker handles concurrent requests fine for personal use.

### 3. `app/utils/srt_converter.py`
- **Translation batch size**: Reduced `batch_size` from 50 to 18. Server logs showed frequent JSON truncation where the LLM returned fewer translations than input texts (e.g. 46/50, 21/50). Smaller batches reduce the risk of hitting `max_tokens` truncation.
- **Automatic retry**: Added exactly one automatic retry of the same batch when translation count mismatches input count, before falling back to partial-fill. Previously, mismatches were silently partial-filled.
- **Untranslated segment logging**: Every segment that remains untranslated after retry is now explicitly logged with its index and original text (first 80 chars), making gaps traceable in server logs.
- **Prompt improvement**: Added the exact expected count (`عدد النصوص المطلوب ترجمتها بالضبط: N`) to the prompt to reduce count mismatches.
- **merge_short_segments gap guard**: Added `max_gap=2.0` parameter. Previously, a short segment at time T+50s would be merged into a previous segment at time T, extending its end to T+50s and causing the text from T+50s to display at time T (30-60 seconds early). Now, segments with a gap > 2s from the previous are kept as independent entries.

### 4. `app/services/groq_service.py`
- **FFmpeg seek accuracy**: In `_extract_chunk()`, moved `-ss` before `-i` in both the `-c copy` and re-encode ffmpeg commands. With `-ss` after `-i` and `-c copy`, ffmpeg performs frame-level copying that can start from an inaccurate position in the MP3 stream, causing all timestamps in that chunk to shift. Putting `-ss` before `-i` does input-level seeking which is more accurate.
- **Chunk start verification**: After a successful `-c copy` extraction, the code now uses `ffprobe` to check the actual `start_time` of the output file. If it's > 0.5s (indicating the copy included padding from before the seek point), the file is deleted and re-encoded instead. This ensures the `offset` parameter passed to the transcription functions matches the chunk's real start time.

### 5. `app/routers/download.py`
- **Path traversal fix**: The `filename` query param in `GET /api/v1/download/file/{task_id}` was joined directly via `os.path.join(output_dir, filename)`, allowing `../../etc/passwd` to escape the task directory. Fixed by:
  - Using `os.path.basename()` to strip any directory components
  - Using `os.path.normpath()` to resolve any remaining `..` sequences
  - Checking that the resolved path starts with `output_dir + os.sep`
  - Also validating that `task_id` contains only alphanumeric characters, hyphens, and underscores

### 6. `frontend/index.html`
- **Third background orb**: Added `<div class="bg-orb bg-orb-3"></div>` for the animated background enhancement.
- **Accessibility**: Added `aria-label` attributes to icon-only buttons (paste button, clear button, cancel button).

### 7. `frontend/css/style.css`
- **Animated background**: Replaced the two inline-styled `.bg-orb` elements with three class-based orbs (`.bg-orb-1`, `.bg-orb-2`, `.bg-orb-3`) with independent animations including opacity breathing. Added a third radial gradient on `body::before` and a slow `bgShift` opacity animation. All using the existing `--primary`/`--primary-alt`/`--accent` palette.
- **Button disabled states**: Added `:disabled` rules for `.btn-secondary`, `.btn-success`, `.btn-danger`, `.btn-outline`, `.btn-link` (opacity 0.35, `cursor: not-allowed`, no transform).
- **Keyboard focus states**: Added `:focus-visible` outlines (2px solid `--primary-alt`, offset 2px) for `.btn`, `.input-row input`, `.btn-paste`, `.subtitle-toggle-track`, and `.embed-option-content`.
- **Responsive**: Added mobile sizing rules for `.bg-orb-1/2/3` in the `@media (max-width: 500px)` block.

## No Silent Behavior Changes

All changes are documented above. No file was modified without a corresponding entry in this log.
