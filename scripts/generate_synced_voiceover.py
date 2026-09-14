"""Generate perfectly timed, calm neural voiceover synced to the 135s video cut."""
import asyncio
import os
import subprocess
import edge_tts

VOICE = "en-US-AndrewMultilingualNeural" # Calm, authoritative tech founder/engineer voice
RATE = "-2%"

SEGMENTS = [
    # Act 0: 0s - 10s (Typewriter SFX 0.2s - 3.5s)
    (
        "act0_1", 3.8,
        "What if a customer ticket tells your AI: 'Delete our production database'?"
    ),
    (
        "act0_2", 7.2,
        "Meet Orville. Guarded support handoffs powered by Strands."
    ),

    # Act 1: 10s - 25s
    (
        "act1_1", 10.5,
        "Automating cross-platform handoffs is essential for SaaS teams. But direct, unguarded write access to production APIs is dangerous."
    ),
    (
        "act1_2", 17.5,
        "Here, an incoming bug report secretly injects a deletion command. Orville immediately detects the attack, blocks the destructive call, and safeguards your database."
    ),

    # Act 2: 25s - 65s
    (
        "act2_1", 25.5,
        "Watch Orville run live with the Strands SDK. It inspects the report, matches existing Issue #1 with ninety-eight percent confidence, and refuses deletion."
    ),
    (
        "act2_2", 40.5,
        "Destination one: An engineering update is attached directly to GitHub Issue #1, anchoring a persistent deduplication marker."
    ),
    (
        "act2_3", 48.5,
        "Destination two: A customer follow-up card is created on Trello, embedding the verified GitHub issue link."
    ),
    (
        "act2_4", 56.5,
        "Destination three: An alert is published to Discord. Independent HTTP GET readbacks verify all three records before reporting complete."
    ),

    # Act 3: 65s - 90s
    (
        "act3_1", 65.8,
        "When confidence is split between two plausible issues, generic agents guess and corrupt your tracking. Orville enforces a hard stop with zero writes before human approval."
    ),
    (
        "act3_2", 78.0,
        "The human operator reviews and selects candidate #2, safely resuming the pipeline to completion."
    ),

    # Act 4: 90s - 110s
    (
        "act4_1", 90.8,
        "When a network retry occurs with the same report ID, Orville reuses verified records—never spamming channels or creating duplicate cards."
    ),
    (
        "act4_2", 100.5,
        "A full suite of forty-two automated tests continuously verifies injection resistance and network recovery. One hundred percent green."
    ),

    # Act 5: 110s - 135s
    (
        "act5_1", 110.8,
        "Orville combines the Strands SDK, Groq reasoning, and cross-app orchestration with end-to-end proof receipts."
    ),
    (
        "act5_2", 120.0,
        "Explore the live repository, verify the receipts, and build customer support handoffs that finish with proof."
    ),
]

async def generate_speech_clips():
    temp_dir = "demo-video/assets/audio/temp_clips"
    os.makedirs(temp_dir, exist_ok=True)
    generated = []
    
    for seg_id, start_sec, text in SEGMENTS:
        out_path = os.path.join(temp_dir, f"{seg_id}.mp3")
        comm = edge_tts.Communicate(text, VOICE, rate=RATE)
        await comm.save(out_path)
        
        # Check duration with ffmpeg
        proc = subprocess.run([
            "ffmpeg", "-i", out_path
        ], capture_output=True, text=True)
        dur = 4.0
        for line in proc.stderr.splitlines():
            if "Duration:" in line:
                parts = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = parts.split(":")
                dur = float(h) * 3600 + float(m) * 60 + float(s)
                break
        print(f"[{seg_id}] @ {start_sec:05.1f}s (dur: {dur:.2f}s): {text[:45]}...")
        generated.append((seg_id, start_sec, out_path, dur))
        
    return generated

def mix_master_soundtrack(clips):
    out_master = "demo-video/assets/audio/synced-soundtrack.mp3"
    
    # We will build an FFmpeg filter_complex that:
    # 1. Takes clean-audio.mp3 (typewriter sound at 0.2s - 3.5s) as input 0
    # 2. Takes each clip and delays it by its start_sec (in milliseconds)
    # 3. Mixes all voice clips on top of input 0
    
    inputs = ["-i", "demo-video/assets/audio/clean-audio.mp3"]
    filter_chains = []
    mix_inputs = ["[0:a]"]
    
    for idx, (seg_id, start_sec, path, dur) in enumerate(clips, start=1):
        inputs.extend(["-i", path])
        delay_ms = int(start_sec * 1000)
        filter_chains.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume=1.0[v{idx}]")
        mix_inputs.append(f"[v{idx}]")
        
    all_inputs_tag = "".join(mix_inputs)
    num_inputs = len(mix_inputs)
    filter_complex = ";".join(filter_chains) + f";{all_inputs_tag}amix=inputs={num_inputs}:duration=first:dropout_transition=0.5,volume=1.3[outa]"
    
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-t", "135.0",
        out_master
    ]
    
    print("Mixing master soundtrack with FFmpeg...")
    subprocess.run(cmd, check=True)
    print(f"Master soundtrack generated: {out_master}")

if __name__ == "__main__":
    clips = asyncio.run(generate_speech_clips())
    mix_master_soundtrack(clips)
