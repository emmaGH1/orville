# Orville static landing page

Live at **https://orville-tau.vercel.app/** (Vercel, deployed September 14, 2026).

The page explains a recorded Strands-driven support handoff using fictional customer input and real app records. It does not run the Python agent.

Serve only `dist/` as the public root. No build step or application dependencies are required. Fonts are loaded from Google Fonts; font sources and licenses are documented in ASSETS.md.

## Vercel deployment

The project (`orville`, scope `emmagh1s-projects`) is configured with **Root Directory = `landing-page`**, so Git-connected deployments build this directory directly. CLI uploads are already scoped to the linked directory and conflict with that setting: to redeploy by CLI, temporarily clear Root Directory in project settings, run `npx vercel --prod` from `landing-page/`, then restore it. The public production alias is `orville-tau.vercel.app` (the default `*-emmagh1s-projects.vercel.app` alias sits behind Vercel Authentication and is not publicly reachable).

## Review path

Open the page, follow "Explore the recorded handoff", and inspect the HARBOR-STRANDS-05 receipt. The expected IDs are GitHub comment 5667869897 on issue #1, Trello card 6aa82c5d3a1ff6da7c9129b6, and Discord message 1549107085609013442. The displayed status is historical, not a live verification; the run and its same-ID retry were captured as terminal output on September 14, 2026.

Both primary links target the receipt. FAQ disclosure controls work with a keyboard. The page includes reduced-motion handling and noindex metadata. Update both primary actions only after a real accessible demo link is verified.

## Publication boundary

`.openai/hosting.json` records the earlier reserved, unpublished Site and is retained as history; Vercel is the deployment target now. Publish only `dist/`. The parent repository, local state, private production notes, recordings, frame pack and credentials must never be included in the public artifact. Public visitor access requires the owner's publication approval.
