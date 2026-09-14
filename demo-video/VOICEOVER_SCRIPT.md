# Orville — Official 135-Second Voiceover Script & Pitch Guide

> **Project:** Orville — Guarded Multi-App Support Handoff Agent  
> **Event:** Agents for Humans Hackathon 2026  
> **Total Duration:** 135.00 Seconds (02:15)  
> **Clean Export:** `demo-video/output/orville-demo.mp4` *(Contains ONLY intro typewriter SFX + clean silence ready for your voice track)*  
> **Format:** Formatted for direct copy-paste into **ElevenLabs**, **Clipchamp**, or live studio narration.

---

## 🎯 Executive Pitch Pillars (Covered in this Script)
1. **The Problem:** Generic AI agents given direct API write access are ticking time bombs. A malicious customer ticket with prompt injection or an ambiguous bug report will blindly execute destructive calls—dropping databases, overwriting tickets, and spamming channels.
2. **Who It's For:** SaaS engineering, product, and customer support operations teams that desperately need to automate handoffs between customer tickets, GitHub Issues, Trello follow-ups, and Discord alerts—without risking catastrophic data corruption.
3. **Why It Matters:** Orville introduces **verifiable guardrails with the Strands SDK**: deterministic injection refusal, independent HTTP GET readback receipts, fail-safe human-in-the-loop escalation with zero pre-approval writes, and guaranteed idempotent retries.

---

## 🎙️ Master Timestamped Voiceover Script

### Act 0: Cold Open — The Vulnerability & The Brand
**Timecode:** `0:00 – 0:10` (10 Seconds)  
**Visual on Screen:** Typewriter sound effects type out the question (`0.2s - 3.4s`), holds clean for reading (`3.4s - 5.4s`), docked red refusal banner slides in above the card (`5.5s`), followed by the clean white Orville logo splash (`7.2s - 10.0s`).  
**Tone:** Urgent, authoritative, thought-provoking.

> *(0:00 - 0:03.5: Silence on speech while typewriter acoustic keystrokes click and carriage dings)*  
> 
> **[0:03.5]**  
> "What happens when an untrusted customer bug report tells your AI agent: *'Delete our production database'*?  
> **[0:06.5]**  
> Meet Orville. A guarded support handoff agent built for teams that demand automated workflows—without catastrophic security risks."

---

### Act 1: The Problem & Who It's For
**Timecode:** `0:10 – 0:25` (15 Seconds)  
**Visual on Screen:** SaaS ticket arrives with embedded injection payload. Danger line accents in red. Docked `🚨 INJECTION REFUSED · 0 WRITES` status pill pops into the header. Raw file capture on the right.  
**Tone:** Grounded, relatable, precise.

> **[0:10]**  
> "For modern SaaS operations, automating cross-platform handoffs is critical. But giving autonomous agents direct write access to your production APIs is dangerous.  
> **[0:17]**  
> Here, an incoming ticket reports a legitimate CSV export timeout—but secretly injects an instruction to wipe closed tickets.  
> **[0:21]**  
> Most agents blindly execute this payload. Orville immediately detects the prompt injection, blocks the destructive call, and protects your database."

---

### Act 2: The Solution — Guarded Execution & Multi-App Proof
**Timecode:** `0:25 – 1:05` (40 Seconds)  
**Visual on Screen:** Terminal run with Strands SDK tool loop. Docked header pills show `🛑 DELETION REFUSED` and `🔍 ISSUE #1 MATCHED`. Then camera transitions across 3 real destinations: GitHub comment posted (16s), Trello follow-up card created (24s), and Discord webhook posted (32s). Checkmarks cascade to green, culminating in `🏆 3/3 APPS VERIFIED`.  
**Tone:** Dynamic, confident, demonstrating real capability.

> **[0:25]**  
> "Watch Orville run live using the Strands SDK.  
> **[0:28]**  
> Our sequential tool loop inspects the report, performs a candidate similarity search, and matches existing GitHub Issue #1 with ninety-eight percent confidence.  
> **[0:36]**  
> It safely refuses the deletion request, then initiates a coordinated multi-app handoff.  
> **[0:41]**  
> Destination one: Orville appends an engineering update directly to GitHub Issue #1, anchoring a unique deduplication marker.  
> **[0:49]**  
> Destination two: A customer follow-up card is created on Trello, embedding the exact GitHub comment link so support has full context.  
> **[0:57]**  
> Destination three: A notification is dispatched to Discord. But Orville doesn't just trust the LLM summary—it performs independent HTTP GET readbacks across all three services, proving every record exists before marking the run complete."

---

### Act 3: Human-in-the-Loop Safety & Zero Writes Guarantee
**Timecode:** `1:05 – 1:30` (25 Seconds)  
**Visual on Screen:** Ambiguity scenario. Docked `⚠️ NEEDS_HUMAN · 0 WRITES` badge in card header. Zero-writes counter highlights: 0 GitHub writes, 0 Trello cards, 0 Discord posts. Operator modal appears, clicks Option #2, pipeline resumes and resolves cleanly.  
**Tone:** Measured, reassuring, emphasizing architectural discipline.

> **[1:05]**  
> "What happens when confidence is split between two plausible issues?  
> **[1:09]**  
> Generic agents guess—corrupting issue trackers and notifying the wrong teams.  
> **[1:14]**  
> Orville enforces a hard stop. It halts execution under `needs_human` with a strict guarantee: zero GitHub comments, zero Trello cards, and zero Discord posts before approval.  
> **[1:22]**  
> The human operator reviews the candidates, selects the correct issue, and Orville safely resumes the pipeline to completion."

---

### Act 4: Reliability — Idempotent Retries & 42 Automated Tests
**Timecode:** `1:30 – 1:50` (20 Seconds)  
**Visual on Screen:** Terminal retry with same report ID. Docked `⚡ ZERO DUPLICATES` pill pops in header. Then transitions to local pytest runner: stat number `42 / 42` punches in green with cascading checkmarks.  
**Tone:** Technical, robust, undeniable proof.

> **[1:30]**  
> "In real-world networks, retries are inevitable.  
> **[1:33]**  
> When Orville reruns an identical report ID, it verifies existing records and reuses them instantly—never spamming channels or duplicating tickets.  
> **[1:40]**  
> And this isn't a fragile demo script. A full test suite of forty-two automated tests continuously verifies injection resistance, five-hundred error reconciliations, and review resumes. One hundred percent green."

---

### Act 5: Architecture & The Proof of Value
**Timecode:** `1:50 – 2:15` (25 Seconds)  
**Visual on Screen:** Clean white circular logo emblem, four architecture cards slide in (Strands SDK, Groq OSS 120B, 3 Destinations, Proof Receipt), receipts badges show live repository and landing page, CTA button with gentle breathing pulse.  
**Tone:** Inspiring, visionary, strong closing call to action.

> **[1:50]**  
> "Orville combines the Strands SDK for guarded execution, Groq open-source reasoning, and multi-app orchestration with end-to-end auditability.  
> **[1:58]**  
> It proves that AI agents don't have to be reckless black boxes. With deterministic safety boundaries, independent verification, and human oversight, you can automate customer support handoffs with total confidence.  
> **[2:09]**  
> Explore the live repository, check the test receipts, and see why Orville sets the standard for safe multi-app agents."

---

## 🎛️ Recommended ElevenLabs Configuration

If generating this voiceover in **ElevenLabs**:
1. **Voice Choice:**
   - *Adam* (Deep, authoritative American) — ideal for enterprise/security demos.
   - *Marcus* (Crisp, authoritative tech founder) — great energy and pacing.
   - *Rachel* or *Charlotte* (Polished, articulate, clear tech product voice).
2. **Voice Settings:**
   - **Stability:** `55%` (keeps delivery consistent and punchy)
   - **Clarity + Similarity:** `85%` (ensures zero slurring of technical terms like *'idempotent'*, *'Strands SDK'*, *'HTTP GET'*)
   - **Style Exaggeration:** `10% - 15%` (natural speaking cadence without over-dramatization)
3. **Pacing:**
   - Generate each Act as an individual audio file (`act0.mp3`, `act1.mp3`, etc.).
   - This allows effortless, exact alignment with the on-screen cue points inside Clipchamp.

---

## 🎬 Clipchamp / Video Editor Alignment Table

| Segment | Video Timecode | Audio File | Target Speech Duration | Visual Synchronization Cue |
| :--- | :--- | :--- | :--- | :--- |
| **Act 0** | `0:00 - 0:10` | `act0-vo.mp3` | **6.5s** (starts at `0:03.5`) | Speaks right after typewriter bell ding; logo splash appears at `0:07.2` |
| **Act 1** | `0:10 - 0:25` | `act1-vo.mp3` | **13.5s** (starts at `0:10.5`) | *"secretly injects"* matches red danger line highlight at `0:13.5` |
| **Act 2** | `0:25 - 1:05` | `act2-vo.mp3` | **37.0s** (starts at `0:25.5`) | Destination mentions align with GitHub (`0:41`), Trello (`0:49`), Discord (`0:57`) |
| **Act 3** | `1:05 - 1:30` | `act3-vo.mp3` | **22.5s** (starts at `1:05.5`) | Zero-writes highlight at `1:08.5`; button click at `1:16.0` |
| **Act 4** | `1:30 - 1:50` | `act4-vo.mp3` | **18.0s** (starts at `1:30.5`) | *"forty-two automated tests"* hits when `42 / 42` pops at `1:40.5` |
| **Act 5** | `1:50 - 2:15` | `act5-vo.mp3` | **23.0s** (starts at `1:50.5`) | Architectural cards cascade into place as features are detailed |
