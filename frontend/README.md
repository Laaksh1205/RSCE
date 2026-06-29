# RSCE Frontend

The web client for the **Research Synthesis & Contradiction Engine**. Built with Next.js 16 (App Router) and TypeScript, it lets users run a literature query, watch the analysis pipeline progress in real time, and explore the resulting contradictions as both a narrative report and an interactive claim-evidence graph.

## Structure

| Path | Purpose |
| :--- | :--- |
| `app/page.tsx` | Landing & search view — query input, seed-claim/date/journal filters, and pre-loaded demo topics. |
| `app/results/[runId]/page.tsx` | Results dashboard — live progress (WebSocket with polling fallback), narrative synthesis with clickable citations, filterable contradiction cards, and knowledge gaps. |
| `components/ClaimGraph.tsx` | Cytoscape.js (fcose layout) network of papers, claims, and entities with conflict/entity focus filters. |
| `utils/api.ts` | REST/WebSocket base URLs and the `startAnalysis` client. |

## Getting Started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The frontend talks to the FastAPI backend (see the root `README.md` for backend setup). Configure the endpoints with environment variables (defaults shown):

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000
```

## Build

```bash
npm run build
npm run start
```
