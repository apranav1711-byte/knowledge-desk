"""Voice-over agent: narration.json -> narrated video + subtitles + transcript.

    python make_voiceover.py                 # build ../less-voiceover.mp4 from narration.json
    python make_voiceover.py --voice en-IN-PrabhatNeural
    python make_voiceover.py --engine windows   # offline Windows voice instead of the online neural voice
    python make_voiceover.py --list-voices      # English neural voices
    python make_voiceover.py --subs soft        # subtitle track only (no captions drawn on the picture)

How it works: each narration segment is spoken with text-to-speech, timed to start at its `start` second, sped up
slightly (max 1.25x) if it would run into the next segment, then mixed onto the video. Small captions are drawn
at the bottom of the picture and also embedded as a subtitle track. Clips are cached, so re-running after editing one line only re-synthesises that line.
Outputs: the narrated MP4, an .srt subtitle file next to it, and TRANSCRIPT.md here.
"""
import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "audio"
MAX_SPEEDUP = 1.25
GAP = 0.15  # seconds of breathing room before the next segment
# small white captions on a soft dark band at the bottom (libass style; FontSize is relative to a 288-line canvas)
# BorderStyle=3 = plain box behind the text; its colour is OutlineColour (alpha 0x50 = ~70% opaque), Outline = padding
SUB_STYLE = ("FontName=Segoe UI,FontSize=10,PrimaryColour=&H00FFFFFF,OutlineColour=&H50000000,"
             "BorderStyle=3,Outline=2,Shadow=0,MarginV=12,Alignment=2")


def caption_chunks(text: str, maxlen: int = 46) -> list[str]:
    """Split narration into short caption lines, preferring sentence and clause boundaries."""
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > maxlen:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
        if cur.endswith((".", "?", "!", ":")) and len(cur) >= 18:
            out.append(cur)
            cur = ""
    if cur:
        if out and len(cur) < 12 and len(out[-1]) + len(cur) < maxlen + 12:
            out[-1] += " " + cur  # avoid a lonely one-word caption
        else:
            out.append(cur)
    return out


def sh(cmd: list[str], cwd=None) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        sys.exit(f"Command failed: {' '.join(cmd[:4])} ...\n{r.stderr[-1500:]}")
    return r.stdout


def duration(path: Path) -> float:
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).strip())


async def tts_edge(text: str, voice: str, rate: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def tts_windows(text: str, out: Path) -> None:
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SetOutputToWaveFile('{out}');"
        "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], input=text, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Windows speech failed: {r.stderr[-800:]}")


def synth(seg: dict, voice: str, rate: str, engine: str) -> Path:
    spoken = seg.get("say") or seg["text"]
    key = hashlib.sha1(f"{engine}|{voice}|{rate}|{spoken}".encode()).hexdigest()[:16]
    out = CACHE / f"{key}.{'mp3' if engine == 'edge' else 'wav'}"
    if not out.exists():
        CACHE.mkdir(exist_ok=True)
        if engine == "edge":
            asyncio.run(tts_edge(spoken, voice, rate, out))
        else:
            tts_windows(spoken, out)
    return out


def ts(sec: float, sep: str = ",") -> str:
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "narration.json"))
    ap.add_argument("--voice")
    ap.add_argument("--rate", help='speaking rate, e.g. "+5%%" or "-5%%"')
    ap.add_argument("--engine", choices=["edge", "windows"], default="edge")
    ap.add_argument("--subs", choices=["both", "burn", "soft", "none"],
                    help="burn = drawn into the picture, soft = subtitle track players can toggle (default: both)")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()

    if args.list_voices:
        import edge_tts

        for v in asyncio.run(edge_tts.list_voices()):
            if v["Locale"].startswith("en-"):
                print(f"{v['ShortName']:34} {v['Gender']:7} {v['Locale']}")
        return

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    video = (HERE / cfg["video"]).resolve()
    output = (HERE / cfg["output"]).resolve()
    voice, rate = args.voice or cfg.get("voice", "en-US-AndrewNeural"), args.rate or cfg.get("rate", "+0%")
    segs = sorted(cfg["segments"], key=lambda s: s["start"])
    vdur = duration(video)

    print(f"Video {video.name}: {vdur:.1f}s | voice {voice if args.engine == 'edge' else 'Windows default'} | {len(segs)} segments")
    plan, problems = [], []
    for i, seg in enumerate(segs):
        clip = synth(seg, voice, rate, args.engine)
        d = duration(clip)
        end_limit = (segs[i + 1]["start"] if i + 1 < len(segs) else vdur) - GAP
        slot = end_limit - seg["start"]
        tempo = max(1.0, d / slot) if slot > 0 else MAX_SPEEDUP
        if tempo > MAX_SPEEDUP:
            problems.append(f"  {ts(seg['start'], '.')}: needs {tempo:.2f}x to fit in {slot:.1f}s; shorten: \"{seg['text'][:60]}...\"")
            tempo = MAX_SPEEDUP
        plan.append(dict(seg=seg, clip=clip, tempo=tempo, end=seg["start"] + d / tempo))
        print(f"  {ts(seg['start'], '.')}  {d:4.1f}s{'  x%.2f' % tempo if tempo > 1 else '':7}  {seg['text'][:70]}")

    # subtitles: short caption chunks timed to the speech (one or two short lines on screen at a time)
    caps = []
    for p in plan:
        parts_ = caption_chunks(p["seg"]["text"])
        total, t0 = p["end"] - p["seg"]["start"], p["seg"]["start"]
        weights = [len(c) for c in parts_]
        for c, w in zip(parts_, weights):
            t1 = t0 + total * w / sum(weights)
            caps.append((t0, t1, c))
            t0 = t1
    srt = output.with_suffix(".srt")
    srt.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{c}\n" for i, (a, b, c) in enumerate(caps, start=1)),
                   encoding="utf-8")

    # mix every clip onto the timeline; burn small captions into the picture and/or embed a subtitle track
    subs = args.subs or cfg.get("subtitles", "both")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video)]
    parts = []
    for n, p in enumerate(plan, start=1):
        cmd += ["-i", str(p["clip"])]
        delay = int(p["seg"]["start"] * 1000)
        tempo = f"atempo={p['tempo']:.4f}," if p["tempo"] > 1 else ""
        parts.append(f"[{n}:a]aresample=48000,{tempo}adelay={delay}|{delay}[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(1, len(plan) + 1))
    graph = ";".join(parts) + f";{mix}amix=inputs={len(plan)}:normalize=0:dropout_transition=0,alimiter=limit=0.95[aout]"
    if subs in ("burn", "both"):
        style = cfg.get("subtitle_style", SUB_STYLE)
        graph += f";[0:v]subtitles={srt.name}:force_style='{style}'[vout]"  # relative name: no drive-letter escaping
        vmap, vcodec = "[vout]", ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
    else:
        vmap, vcodec = "0:v", ["-c:v", "copy"]
    if subs in ("soft", "both"):
        cmd += ["-i", srt.name]
    cmd += ["-filter_complex", graph, "-map", vmap, "-map", "[aout]"]
    if subs in ("soft", "both"):
        cmd += ["-map", f"{len(plan) + 1}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    cmd += vcodec + ["-c:a", "aac", "-b:a", "192k", "-t", f"{vdur:.3f}", "-movflags", "+faststart", str(output)]
    sh(cmd, cwd=output.parent)

    md = ["# Voice-over transcript", "", f"Video: `{video.name}` ({vdur:.0f} s). Voice: {voice}.", "",
          "| Time | On screen | Narration |", "| --- | --- | --- |"]
    md += [f"| {ts(p['seg']['start'], '.')[3:8]}–{ts(p['end'], '.')[3:8]} | {p['seg'].get('scene', '')} | {p['seg']['text']} |"
           for p in plan]
    (HERE / "TRANSCRIPT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nDone: {output}\nSubtitles: {srt}\nTranscript: {HERE / 'TRANSCRIPT.md'}")
    if problems:
        print("\nSome lines are too long for their slot (they were sped up to the maximum and may overlap):")
        print("\n".join(problems))


if __name__ == "__main__":
    main()
