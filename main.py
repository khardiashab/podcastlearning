#!/usr/bin/env python3
"""YouTube Hinglish Summarizer — Learn from any video in simple Hinglish."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DOCS_FILE = Path("personal_notes.md")
MAX_TRANSCRIPT_CHARS = 30_000  # ~7,500 words; enough for a 30-40 min video

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------

def extract_video_id(url: str) -> str:
    """Extract 11-char video ID from any YouTube URL format."""
    for pattern in [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]:
        if m := re.search(pattern, url):
            return m.group(1)
    raise ValueError(f"Invalid YouTube URL: {url}")


def get_transcript(video_id: str) -> str:
    """Fetch video transcript text via youtube-transcript-api."""
    try:
        from youtube_transcript_api import (
            NoTranscriptFound,
            VideoUnavailable,
            YouTubeTranscriptApi,
        )
    except ImportError:
        raise SystemExit(
            "❌  youtube-transcript-api install nahi hai.\n"
            "    Run:  pip install youtube-transcript-api"
        )

    try:
        tl = YouTubeTranscriptApi.list_transcripts(video_id)
        # Prefer English; fall back to whatever is available
        try:
            transcript = tl.find_transcript(["en", "en-US", "en-GB", "en-IN"])
        except Exception:
            transcript = next(iter(tl))
        entries = transcript.fetch()
        return " ".join(e["text"] for e in entries)
    except VideoUnavailable:
        raise ValueError("Video unavailable ya private hai")
    except NoTranscriptFound:
        raise ValueError("Is video ka koi transcript nahi mila")
    except Exception as exc:
        raise ValueError(f"Transcript error: {exc}") from exc


# ---------------------------------------------------------------------------
# Claude — summary generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "Tu ek expert educator hai jo complex ideas ko simple Hinglish mein explain karta hai. "
    "Hindi aur English naturally mix kar — jaise koi young Delhi/Mumbai wala dost baat karta hai. "
    "Technical terms English mein rakh. Concise, clear aur conversational reh. "
    "Emojis use mat kar."
)


def generate_summary(transcript: str) -> str:
    """Stream Hinglish summary + numbered learnings from Claude Opus 4.7."""
    truncated = transcript[:MAX_TRANSCRIPT_CHARS]
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        print(
            f"   ℹ️   Video bahut lamba hai — pehle "
            f"{MAX_TRANSCRIPT_CHARS:,} characters use honge\n"
        )

    prompt = f"""Yeh YouTube video ka transcript hai.
Is video ki key learnings Hinglish mein extract karo.

TRANSCRIPT:
{truncated}

Exactly yeh format follow karo — koi extra text mat likho:

## VIDEO SUMMARY
[2-3 lines mein video ka core idea, Hinglish mein]

## KEY LEARNINGS
[Har point ek specific, actionable learning honi chahiye]

1. [Learning]
2. [Learning]
3. [Learning]
[Minimum 5, maximum 15 points — jitne relevant ho utne]

## QUICK TAKEAWAY
[Sirf ek line — agar ek hi cheez yaad rakhni ho toh kya?]"""

    print("\n🤖  Claude video analyze kar raha hai...\n")
    print("─" * 60)

    result = ""
    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            print(chunk, end="", flush=True)
            result += chunk

    print("\n" + "─" * 60)
    return result


# ---------------------------------------------------------------------------
# Claude — point enhancement
# ---------------------------------------------------------------------------

def enhance_with_claude(point: str) -> str:
    """Ask Claude Sonnet to enrich a learning point with context + tips."""
    print("\n💭  Claude suggestions de raha hai...\n")
    result = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=600,
        thinking={"type": "adaptive"},
        messages=[{
            "role": "user",
            "content": (
                f'Learning point: "{point}"\n\n'
                "Isko mere personal notes ke liye enhance karo:\n"
                "- Ek real-life example ya relatable analogy\n"
                "- 1-2 practical tips — isko life mein kaise apply karein\n\n"
                "Hinglish mein, max 5 lines, concise raho."
            ),
        }],
    ) as stream:
        for chunk in stream.text_stream:
            print(chunk, end="", flush=True)
            result += chunk
    print()
    return result


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_learnings(text: str) -> list[str]:
    """Extract numbered items from the KEY LEARNINGS section."""
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        if re.search(r"KEY LEARNING", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section and re.match(r"^##\s", line):
            break
        if in_section:
            if m := re.match(r"^\s*\d+[.)]\s+(.+)", line):
                items.append(m.group(1).strip())
    return items


# ---------------------------------------------------------------------------
# Docs writer
# ---------------------------------------------------------------------------

class DocsWriter:
    """Appends selected learnings to personal_notes.md."""

    def __init__(self, video_url: str) -> None:
        self.video_url = video_url
        self._header_written = False

    # ------------------------------------------------------------------
    def _ensure_file(self) -> None:
        if not DOCS_FILE.exists():
            DOCS_FILE.write_text(
                "# My Personal Learning Notes\n\n"
                "_YouTube videos se seekhe gaye important ideas_\n\n",
                encoding="utf-8",
            )

    def _write_section_header(self) -> None:
        self._ensure_file()
        date = datetime.now().strftime("%d %b %Y, %I:%M %p")
        with DOCS_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n---\n\n## 🎬  {date}\n**Source:** {self.video_url}\n\n")
        self._header_written = True

    # ------------------------------------------------------------------
    def add(self, point: str, mode: str) -> None:
        """
        mode:
          "as_is"    — bullet point, exactly as-is
          "thought"  — bullet with 💭 prefix
          "enhanced" — section heading + Claude suggestions
        """
        if not self._header_written:
            self._write_section_header()

        with DOCS_FILE.open("a", encoding="utf-8") as f:
            if mode == "as_is":
                f.write(f"- {point}\n")
            elif mode == "thought":
                f.write(f"- 💭 **Thought:** {point}\n")
            elif mode == "enhanced":
                enhanced = enhance_with_claude(point)
                f.write(f"\n### {point}\n\n{enhanced}\n\n")

        print(f"\n✅  '{DOCS_FILE}' mein add ho gaya!")


# ---------------------------------------------------------------------------
# Interactive CLI helpers
# ---------------------------------------------------------------------------

def _pick_add_mode() -> str | None:
    """Ask user how to save the selected point. Returns mode key or None."""
    print("\n  Kaise add karein?")
    print("    1 — As-is           (exactly jaise hai)")
    print("    2 — As a thought    (💭 thought ki tarah)")
    print("    3 — With suggestions  (Claude se enhance karwao)")
    print("    c — Cancel")
    while True:
        c = input("  👉  (1/2/3/c): ").strip().lower()
        if c == "1":
            return "as_is"
        if c == "2":
            return "thought"
        if c == "3":
            return "enhanced"
        if c == "c":
            return None
        print("    1, 2, 3 ya c type karo")


def run_interactive_loop(learnings: list[str], writer: DocsWriter) -> None:
    """Let user pick which points to save and how."""
    if not learnings:
        print("\n⚠️   Koi numbered learnings parse nahi hue. Ek baar phir try karo.")
        return

    def show_list() -> None:
        print()
        for i, p in enumerate(learnings, 1):
            marker = "✓" if i in added else " "
            print(f"  [{marker}] {i:2}.  {p}")

    print(f"\n\n{'═' * 60}")
    print("  APNE DOCS MEIN ADD KARO")
    print(f"{'═' * 60}")
    print("\n  Commands:")
    print("    <number>  — ek specific point add karo")
    print("    all       — saare points ek saath add karo")
    print("    list      — points dobara dekho")
    print("    q         — quit\n")

    added: set[int] = set()
    show_list()

    while True:
        print()
        raw = input("  👉  Enter command: ").strip().lower()

        if raw == "q":
            total = len(added)
            if total:
                print(f"\n  📚  {total} point(s) '{DOCS_FILE}' mein save ho gaye.")
            print("  ✌️   Happy learning!\n")
            break

        elif raw == "list":
            show_list()

        elif raw == "all":
            remaining = [i for i in range(1, len(learnings) + 1) if i not in added]
            if not remaining:
                print("  ⚠️   Saare points pehle se add ho chuke hain!")
                continue
            mode = _pick_add_mode()
            if mode:
                for i in remaining:
                    writer.add(learnings[i - 1], mode)
                    added.add(i)
                print(f"\n  ✅  Saare {len(remaining)} points add ho gaye!")

        else:
            try:
                n = int(raw)
                if not (1 <= n <= len(learnings)):
                    print(f"  ⚠️   1 se {len(learnings)} ke beech number do")
                    continue
                if n in added:
                    print(f"  ⚠️   Point {n} pehle se add hai!")
                    continue
                print(f"\n  Selected →  {learnings[n - 1]}")
                mode = _pick_add_mode()
                if mode:
                    writer.add(learnings[n - 1], mode)
                    added.add(n)
            except ValueError:
                print("  ⚠️   Number, 'all', 'list', ya 'q' type karo")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:   python main.py <youtube_url>")
        print("Example: python main.py https://www.youtube.com/watch?v=VIDEO_ID")
        sys.exit(1)

    url = sys.argv[1].strip()

    print("\n🎬  YouTube Hinglish Summarizer")
    print("═" * 60)
    print(f"  URL: {url}\n")

    # 1. Validate URL
    try:
        video_id = extract_video_id(url)
        print(f"  ✅  Video ID: {video_id}")
    except ValueError as exc:
        print(f"  ❌  {exc}")
        sys.exit(1)

    # 2. Fetch transcript
    print("  📝  Transcript fetch kar raha hai...")
    try:
        transcript = get_transcript(video_id)
        words = len(transcript.split())
        print(f"  ✅  {words:,} words ka transcript mila")
    except ValueError as exc:
        print(f"  ❌  {exc}")
        sys.exit(1)

    # 3. Generate Hinglish summary (streamed)
    try:
        summary = generate_summary(transcript)
    except anthropic.AuthenticationError:
        print("\n  ❌  ANTHROPIC_API_KEY invalid ya set nahi hai")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n  ⚠️   Generation interrupt ho gayi.")
        sys.exit(0)

    # 4. Parse points + interactive save menu
    learnings = parse_learnings(summary)
    writer = DocsWriter(url)

    try:
        run_interactive_loop(learnings, writer)
    except KeyboardInterrupt:
        print("\n\n  ✌️   Bye!")


if __name__ == "__main__":
    main()
