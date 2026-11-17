#!/usr/bin/env python3
"""Transcribe one audio file with faster-whisper and write segments as JSON.

Usage: whisper.py <audio> <out.json> [video id]
Model: WHISPER_MODEL (default large-v3), int8 on CPU.
"""
import json, os, sys, time
from faster_whisper import WhisperModel

audio, out = sys.argv[1], sys.argv[2]
vid = sys.argv[3] if len(sys.argv) > 3 else ""
name = os.environ.get("WHISPER_MODEL", "large-v3")
t0 = time.time()
model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
segments, info = model.transcribe(
    audio, language="ar", beam_size=5, vad_filter=True,
    vad_parameters={"min_silence_duration_ms": 500},
    condition_on_previous_text=True,
    initial_prompt="بسم الله الرحمن الرحيم. الحمد لله رب العالمين، والصلاة والسلام على رسول الله. أما بعد، "
                   "فيا أيها الإخوة المؤمنون: قال الله تعالى في كتابه الكريم.")
segs = [{"s": round(s.start, 2), "e": round(s.end, 2), "t": s.text.strip()} for s in segments]
json.dump({"id": vid, "model": name, "duration": round(info.duration, 1),
           "seconds": round(time.time() - t0), "segments": segs},
          open(out, "w"), ensure_ascii=False, indent=0)
print(f"{vid}: {info.duration/60:.1f} min audio in {(time.time()-t0)/60:.1f} min, {len(segs)} segments")
