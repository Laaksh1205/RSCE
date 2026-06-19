export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8000";

export interface AnalyzeResponse {
  run_id: string;
  query: string;
  status: string;
}

export async function startAnalysis(
  query: string,
  maxPapers: number = 25,
  seedClaim?: string,
  dateFrom?: number,
  dateTo?: number,
  journals?: string[]
): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      max_papers: maxPapers,
      seed_claim: seedClaim || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      journals: journals && journals.length > 0 ? journals : undefined,
    }),
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(errData.detail || "Failed to start analysis run.");
  }

  return response.json();
}
