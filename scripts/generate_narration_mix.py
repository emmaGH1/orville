"""Generate edge-tts voiceover and ducked background audio mix for Orville demo video (135s)."""
import asyncio
import os
import subprocess
import edge_tts

VOICE = "en-US-AndrewNeural"
RATE = "-4%"
TOTAL_DURATION = 135.0

SEGMENTS = [
    {
        "id": "act0",
        "start": 1.0,
        "text": "What happens when an untrusted bug report tells your AI agent to delete your production database? Meet Orville: the guarded support handoff agent, built with the Strands SDK."
    },
    {
        "id": "act1",
        "start": 11.0,
        "text": "For SaaS engineering and support teams, automating ticket handoffs across GitHub, Trello, and Discord is essential. But giving autonomous agents direct write access to production APIs is a security nightmare."
    },
    {
        "id": "act2",
        "start": 26.0,
        "text": "Orville solves this using Strands. The Strands Agent loop executes strictly guarded tools. Notice what happens: it matches existing Issue number one with ninety-eight percent confidence, but completely refuses the prompt injection deletion request. It comments on GitHub, links a Trello follow-up card, updates Discord, and verifies every single record with independent HTTP GET readbacks before reporting completion."
    },
    {
        "id": "act3",
        "start": 66.0,
        "text": "What if a customer ticket is ambiguous? Most agents guess and corrupt project state. Orville enforces a hard safety boundary. Execution halts with a needs human stop reason, performing exactly zero writes across all three apps. Once an operator selects the correct issue, execution resumes safely."
    },
    {
        "id": "act4",
        "start": 91.0,
        "text": "Retrying the identical report ID reuses verified records with zero duplicate tickets or spam. And forty-two automated tests prove resilience against network faults and prompt injection attacks."
    },
    {
        "id": "act5",
        "start": 111.0,
        "text": "Built with Strands, Groq, and verifiable proof receipts. Explore the live repository on GitHub, and try the interactive landing page. Customer handoffs that finish with proof."
    }
]


async def generate_speech_clips():
    os.makedirs("demo-video/assets/audio/voice", exist_ok=True)
    for seg in SEGMENTS:
        out_path = f"demo-video/assets/audio/voice/{seg['id']}.mp3"
        print(f"Generating voice for {seg['id']}...")
        comm = edge_tts.Communicate(seg["text"], VOICE, rate=RATE)
        await comm.save(out_path)
        print(f"Saved {out_path}")


def assemble_master_audio():
    voice_dir = "demo-video/assets/audio/voice"
    filter_inputs = []
    amix_inputs = []

    # Build ffmpeg input arguments
    cmd = ["ffmpeg", "-y"]
    # Input 0: Background music
    bg_music = "demo-video/assets/audio/background-tech.mp3"
    cmd.extend(["-i", bg_music])

    # Inputs 1..N: Voice segments
    for i, seg in enumerate(SEGMENTS):
        seg_file = f"{voice_dir}/{seg['id']}.mp3"
        cmd.extend(["-i", seg_file])
        delay_ms = int(seg["start"] * 1000)
        filter_inputs.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[v{i}];")
        amix_inputs.append(f"[v{i}]")

    all_voice_cat = "".join(amix_inputs)
    num_voices = len(SEGMENTS)
    filter_complex = "".join(filter_inputs)
    filter_complex += f"{all_voice_cat}amix=inputs={num_voices}:dropout_transition=2[voice_mix];"
    filter_complex += "[0:a]volume=0.20[bg_low];"
    filter_complex += "[voice_mix]volume=1.20[voice_loud];"
    filter_complex += "[bg_low][voice_loud]amix=inputs=2:duration=first:dropout_transition=2,atrim=0:135[aout]"

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-t", "135.0",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "demo-video/assets/audio/master-soundtrack.mp3"
    ])

    print("Running FFmpeg audio mix...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("FFmpeg stderr:", res.stderr)
        raise RuntimeError("FFmpeg audio mix failed")
    print("Master soundtrack generated successfully: demo-video/assets/audio/master-soundtrack.mp3")


async def main():
    await generate_speech_clips()
    assemble_master_audio()


if __name__ == "__main__":
    asyncio.run(main())
