// Mirrors backend/app/schemas/ai_explanation.py

export interface AISummaryResponse {
  available: boolean;
  reason: string | null;
  summary: string | null;
  facts_used: Record<string, unknown>;
  ai_disclaimer: string;
  disclaimer: string;
}
