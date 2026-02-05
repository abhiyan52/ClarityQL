import type { NLQResponse } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface QueryRequest {
  query: string;
  conversation_id?: string;
}

function getAuthToken(): string | null {
  return localStorage.getItem("clarityql_auth_token");
}

function getAuthHeaders(): HeadersInit {
  const token = getAuthToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  
  return headers;
}

export async function sendQuery(request: QueryRequest): Promise<NLQResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nlq/query`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    // Handle various error formats
    let message = `HTTP ${response.status}`;
    if (error.detail) {
      if (typeof error.detail === "string") {
        message = error.detail;
      } else if (typeof error.detail === "object") {
        // Handle structured error details (e.g., Pydantic validation errors)
        message = JSON.stringify(error.detail);
      }
    }
    throw new Error(message);
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
  const response = await fetch(`${API_BASE_URL}/api/schema`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch schema: HTTP ${response.status}`);
  }

  return response.json();
}
