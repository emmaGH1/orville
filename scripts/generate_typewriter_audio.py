"""Generate typewriter click SFX and clean 135s export audio track."""
import math
import wave
import struct
import subprocess
import os

SAMPLE_RATE = 44100
TOTAL_SECONDS = 135.0
TYPE_DURATION = 3.5

# Generate acoustic typewriter keystrokes
def make_typewriter_track():
    num_samples = int(SAMPLE_RATE * TOTAL_SECONDS)
    samples = [0.0] * num_samples
    
    # Generate ~28 rapid randomized keystroke clicks between 0.2s and 3.4s
    import random
    random.seed(42)
    
    click_times = []
    t = 0.2
    while t < TYPE_DURATION - 0.1:
        click_times.append(t)
        t += random.uniform(0.08, 0.15)
        
    for ct in click_times:
        start_idx = int(ct * SAMPLE_RATE)
        # Each click is a fast mechanical transient (noise burst + decaying resonant pitch)
        click_len = int(0.025 * SAMPLE_RATE) # 25ms
        freq1 = random.uniform(1800, 2400)
        freq2 = random.uniform(600, 900)
        for i in range(click_len):
            idx = start_idx + i
            if idx >= num_samples:
                break
            prog = i / click_len
            env = math.exp(-prog * 18.0) # Sharp transient decay
            noise = (random.random() * 2.0 - 1.0) * 0.4
            tone = (math.sin(2.0 * math.pi * freq1 * (i / SAMPLE_RATE)) * 0.4 +
                    math.sin(2.0 * math.pi * freq2 * (i / SAMPLE_RATE)) * 0.4)
            samples[idx] += (noise + tone) * env * 0.75

    # Add a satisfying carriage return / mechanical ding at the end of typing (3.45s)
    ding_idx = int(3.45 * SAMPLE_RATE)
    ding_len = int(0.35 * SAMPLE_RATE)
    for i in range(ding_len):
        idx = ding_idx + i
        if idx >= num_samples:
            break
        prog = i / ding_len
        env = math.exp(-prog * 8.0)
        bell = (math.sin(2.0 * math.pi * 3200 * (i / SAMPLE_RATE)) * 0.35 +
                math.sin(2.0 * math.pi * 1600 * (i / SAMPLE_RATE)) * 0.2)
        samples[idx] += bell * env * 0.5

    # Clamp and convert to 16-bit PCM
    wav_path = "demo-video/assets/audio/clean-audio.wav"
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(2) # stereo
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(SAMPLE_RATE)
        packed = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            val = int(clamped * 32767.0)
            packed.extend(struct.pack("<hh", val, val))
        wf.writeframes(packed)
    print(f"Generated {wav_path}")

    # Convert to MP3
    mp3_path = "demo-video/assets/audio/clean-audio.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-i", wav_path,
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-t", "135.0",
        mp3_path
    ], check=True)
    print(f"Generated {mp3_path}")

if __name__ == "__main__":
    make_typewriter_track()
