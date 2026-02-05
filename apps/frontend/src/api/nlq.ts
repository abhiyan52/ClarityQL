import type { NLQResponse } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface QueryRequest {
  query: string;
  conversation_id: string;
}

export async function sendQuery(request: QueryRequest): Promise<NLQResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nlq/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function getSchema(): Promise<{
  tables: Array<{
    name: string;
    fields: Array<{ name: string; type: string; description?: string }>;
  }>;
  derivedMetrics: Array<{ name: string; description?: string }>;
}> {
  const response = await fetch(`${API_BASE_URL}/api/schema`);

  if (!response.ok) {
    throw new Error(`Failed to fetch schema: HTTP ${response.status}`);
  }

  return response.json();
}
