# Orville static landing page

The page explains a recorded Strands-driven support handoff using fictional customer input and real app records. It does not run the Python agent.

Serve only `dist/` as the public root. No build step or application dependencies are required. Fonts are loaded from Google Fonts; font sources and licenses are documented in ASSETS.md.

## Vercel deployment

Deploy `dist/` as a static site — no framework preset needed. Two equivalent options:

- Dashboard: add the repository, set **Root Directory** to `landing-page`, leave the output as-is (`landing-page/dist` is committed), and deploy.
- CLI: from `landing-page/`, run `npx vercel --prod` (Vercel serves `dist/` because of `vercel.json`).

`vercel.json` sets the output directory to `dist` and enables clean URLs. `og.png` is served from the same origin as the page, so the Open Graph image reference no longer depends on the retired chatgpt.site host.

## Review path

Open the page, follow "Explore the recorded handoff", and inspect the HARBOR-STRANDS-05 receipt. The expected IDs are GitHub comment 5667869897 on issue #1, Trello card 6aa82c5d3a1ff6da7c9129b6, and Discord message 1549107085609013442. The displayed status is historical, not a live verification; the run and its same-ID retry were captured as terminal output on September 14, 2026.

Both primary links target the receipt. FAQ disclosure controls work with a keyboard. The page includes reduced-motion handling and noindex metadata. Update both primary actions only after a real accessible demo link is verified.

## Publication boundary

`.openai/hosting.json` records the earlier reserved, unpublished Site and is retained as history; Vercel is the deployment target now. Publish only `dist/`. The parent repository, local state, private production notes, recordings, frame pack and credentials must never be included in the public artifact. Public visitor access requires the owner's publication approval.
