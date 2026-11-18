# Research file uploads

The Sources page accepts PDF, DOCX, UTF-8 TXT and Markdown, WebVTT and SRT transcripts, MP4/MOV/WebM video, and MP3/M4A/WAV/OGG audio.

Install the runtime dependencies with python3 -m pip install -r requirements.txt. The desktop shortcut uses the existing adjacent .venv when available.

Files can be previewed or retained in the case-local library. Retained originals are checked by SHA-256 on reopening and download. Uploading creates no evidence or phase approval. Evidence still requires an explicit passage review and retains its synthetic classification.

PDF passages retain page references. PDF extraction uses embedded text and can change reading order. Scanned pages require OCR outside the tool. PDFs are limited to 500 pages and 2 MiB of extracted text.

Text and Markdown passages retain line references. Timestamped transcripts retain cue start and end times. Text files support up to 2 MiB and 2,000 passages.

Recordings can be saved and downloaded as originals. To search speech, open a saved recording and attach a UTF-8 WebVTT or SRT transcript. The transcript is retained immutably with its own SHA-256, alongside the recording. Reviewed evidence retains both fingerprints. Changed transcript versions can be saved as separate transcript sources. Automatic speech transcription, OCR, inline media playback, and visual video analysis are pending. Recording format checks inspect file signatures rather than decoding the full recording.

The per-file limit is 64 MiB, with the existing 8 MiB Word limit retained. Each case supports 20 original files. Saved originals, attached transcripts and saved source links are excluded from case checkpoint downloads.

Verification performed on 2026-11-11:
- Full suite: 1,281 passed in 159.80 seconds.
- Final focused suite after adding route and timestamp validation tests: 77 passed in 2.25 seconds.
- JavaScript syntax checked and the expanded Sources upload screen verified in the browser.
