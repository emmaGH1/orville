#!/usr/bin/env python3
"""
Generate an upbeat, polished 165-second (2m45s) electronic tech / synthwave
background music track for the Orville hackathon demo video.
Pure Python standard library: wave, struct, math.
Outputs: demo-video/assets/audio/background-tech.wav
"""

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 44100
DURATION_SEC = 165.0  # 2m 45s
TOTAL_SAMPLES = int(SAMPLE_RATE * DURATION_SEC)
BPM = 124.0
BEAT_DUR = 60.0 / BPM
BAR_DUR = BEAT_DUR * 4.0

OUT_DIR = Path("demo-video/assets/audio")
OUT_DIR.mkdir(parents=True, exist_ok=True)
WAV_PATH = OUT_DIR / "background-tech.wav"

NOTES = {
    "C2": 65.41, "D2": 73.42, "E2": 82.41, "F2": 87.31, "G2": 98.00, "A2": 110.00, "B2": 123.47,
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00, "A3": 220.00, "B3": 246.94,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99, "A5": 880.00, "B5": 987.77,
}

PROGRESSION = [
    {"root": "F2", "bass": "F2", "pad": ["F3", "A3", "C4", "E4"], "arp": ["C4", "E4", "A4", "C5"]},
    {"root": "G2", "bass": "G2", "pad": ["G3", "B3", "D4", "F4"], "arp": ["D4", "G4", "B4", "D5"]},
    {"root": "A2", "bass": "A2", "pad": ["A3", "C4", "E4", "G4"], "arp": ["E4", "A4", "C5", "E5"]},
    {"root": "E2", "bass": "E2", "pad": ["E3", "G3", "B3", "D4"], "arp": ["B3", "E4", "G4", "B4"]},
]

def synthesize():
    print(f"Synthesizing {DURATION_SEC}s audio at {SAMPLE_RATE}Hz...")
    
    noise_len = 44100
    noise = []
    seed = 42
    for _ in range(noise_len):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        noise.append((seed / 0x7FFFFFFF) * 2.0 - 1.0)
    
    with wave.open(str(WAV_PATH), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        
        chunk_size = 4410
        total_chunks = TOTAL_SAMPLES // chunk_size
        
        for chunk_idx in range(total_chunks + 1):
            start_samp = chunk_idx * chunk_size
            end_samp = min(start_samp + chunk_size, TOTAL_SAMPLES)
            if start_samp >= end_samp:
                break
                
            frames = bytearray()
            for i in range(start_samp, end_samp):
                t = i / SAMPLE_RATE
                
                if t < 8.0:
                    drum_vol = min(1.0, max(0.0, (t - 4.0) / 4.0)) * 0.5
                    bass_vol = 0.4
                    pad_vol = 0.6
                    arp_vol = 0.5
                elif t < 75.0:
                    drum_vol = 0.85
                    bass_vol = 0.8
                    pad_vol = 0.55
                    arp_vol = 0.65
                elif t < 105.0:
                    drum_vol = 0.35
                    bass_vol = 0.5
                    pad_vol = 0.7
                    arp_vol = 0.45
                elif t < 145.0:
                    drum_vol = 0.95
                    bass_vol = 0.85
                    pad_vol = 0.6
                    arp_vol = 0.75
                else:
                    fade = max(0.0, 1.0 - (t - 158.0) / 7.0) if t > 158.0 else 1.0
                    drum_vol = 0.6 * fade
                    bass_vol = 0.6 * fade
                    pad_vol = 0.6 * fade
                    arp_vol = 0.5 * fade
                
                bar_idx = int(t / BAR_DUR) % len(PROGRESSION)
                chord = PROGRESSION[bar_idx]
                time_in_bar = t % BAR_DUR
                time_in_beat = t % BEAT_DUR
                beat_num = int(time_in_bar / BEAT_DUR)
                
                kick = 0.0
                if drum_vol > 0.0:
                    if beat_num in (0, 2):
                        kt = time_in_beat
                        if kt < 0.22:
                            k_freq = 140.0 * math.exp(-kt * 28.0) + 45.0
                            k_env = math.exp(-kt * 18.0)
                            kick = math.sin(2.0 * math.pi * k_freq * kt) * k_env * 1.1
                    
                    snare = 0.0
                    if beat_num in (1, 3):
                        st = time_in_beat
                        if st < 0.2:
                            n_samp = int(i * 1.3) % noise_len
                            s_noise = noise[n_samp] * math.exp(-st * 24.0)
                            s_tone = math.sin(2.0 * math.pi * 180.0 * st) * math.exp(-st * 30.0)
                            snare = (s_noise * 0.7 + s_tone * 0.3) * 0.85
                    
                    hat = 0.0
                    sub_16 = time_in_beat % (BEAT_DUR / 4.0)
                    if sub_16 < 0.06:
                        n_samp = int(i * 3.7) % noise_len
                        hat = noise[n_samp] * math.exp(-sub_16 * 75.0) * 0.4
                else:
                    kick, snare, hat = 0.0, 0.0, 0.0
                
                bass = 0.0
                sub_8 = time_in_beat % (BEAT_DUR / 2.0)
                if sub_8 < (BEAT_DUR / 2.0) * 0.85:
                    bfreq = NOTES[chord["bass"]]
                    benv = math.exp(-sub_8 * 9.0)
                    bass = (math.sin(2.0 * math.pi * bfreq * t) + 
                            0.4 * math.sin(4.0 * math.pi * bfreq * t) +
                            0.15 * math.sin(6.0 * math.pi * bfreq * t)) * benv
                
                pad_l, pad_r = 0.0, 0.0
                for n_str in chord["pad"]:
                    pfreq = NOTES[n_str]
                    p1 = math.sin(2.0 * math.pi * pfreq * t)
                    p2 = math.sin(2.0 * math.pi * (pfreq * 1.003) * t)
                    p3 = math.sin(2.0 * math.pi * (pfreq * 0.997) * t)
                    pad_l += (p1 + p2) * 0.15
                    pad_r += (p1 + p3) * 0.15
                
                arp_idx = int((time_in_bar / (BEAT_DUR / 4.0))) % len(chord["arp"])
                arp_note = chord["arp"][arp_idx]
                afreq = NOTES[arp_note]
                sub_arp = time_in_bar % (BEAT_DUR / 4.0)
                aenv = math.exp(-sub_arp * 16.0)
                arp = (math.sin(2.0 * math.pi * afreq * t) + 0.3 * math.sin(4.0 * math.pi * afreq * t)) * aenv
                
                left = (kick * 0.9 + snare * 0.6 + hat * 0.35 + bass * bass_vol * 0.8 + 
                        pad_l * pad_vol + arp * arp_vol * 0.4)
                right = (kick * 0.9 + snare * 0.6 + hat * 0.35 + bass * bass_vol * 0.8 + 
                         pad_r * pad_vol + arp * arp_vol * 0.4)
                
                left = math.tanh(left * 0.7) * 0.85
                right = math.tanh(right * 0.7) * 0.85
                
                i_l = int(max(-32767, min(32767, left * 32767.0)))
                i_r = int(max(-32767, min(32767, right * 32767.0)))
                frames.extend(struct.pack("<hh", i_l, i_r))
                
            wf.writeframes(frames)
            
    print(f"Generated {WAV_PATH} ({WAV_PATH.stat().st_size} bytes)")

if __name__ == "__main__":
    synthesize()
