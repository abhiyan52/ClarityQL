import type { NLQResponse } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface QueryRequest {
  query: string;
  conversation_id?: string;
}

export interface ProgressData {
  percentage: number;
  message: string;
  current: number;
  total: number;
}

export interface StreamCallbacks {
  onProgress: (data: ProgressData) => void;
  onComplete: (data: NLQResponse) => void;
  onError: (error: string) => void;
  onCancelled?: () => void;
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

/**
 * Submit a query for background processing.
 * Returns a task_id that can be used to stream progress.
 */
export async function submitQuery(request: QueryRequest): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/nlq/query`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    let message = `HTTP ${response.status}`;
    if (error.detail) {
      if (typeof error.detail === "string") {
        message = error.detail;
      } else if (typeof error.detail === "object") {
        message = JSON.stringify(error.detail);
      }
    }
    throw new Error(message);
  }

  return response.json();
}

/**
 * Stream task progress via SSE using fetch + ReadableStream.
 * EventSource doesn't support custom headers, so we use fetch instead.
 * 
 * Returns an AbortController that can be used to cancel the stream.
 */
export function streamTaskProgress(
  taskId: string,
  callbacks: StreamCallbacks
): AbortController {
  const controller = new AbortController();
  
  const connect = async () => {
    try {
      const token = getAuthToken();
      const headers: HeadersInit = {};
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(
        `${API_BASE_URL}/api/nlq/tasks/${taskId}/stream`,
        {
          headers,
          signal: controller.signal,
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error("Response body is null");
      }

      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // Process complete SSE messages (terminated by \n\n)
        const messages = buffer.split("\n\n");
        buffer = messages.pop() || "";

        for (const message of messages) {
          if (!message.trim()) continue;

          const lines = message.split("\n");
          let eventType = "message";
          let data = "";

          for (const line of lines) {
            if (line.startsWith("event:")) {
              eventType = line.substring(6).trim();
            } else if (line.startsWith("data:")) {
              data = line.substring(5).trim();
            }
          }

          if (!data) continue;

          try {
            const parsed = JSON.parse(data);

            switch (eventType) {
              case "progress":
                callbacks.onProgress(parsed);
                break;
              case "complete":
                callbacks.onComplete(parsed);
                break;
              case "error":
                callbacks.onError(parsed.error || "Unknown error");
                break;
              case "cancelled":
                callbacks.onCancelled?.();
                break;
            }
          } catch (e) {
            console.error("Failed to parse SSE data:", e);
          }
        }
      }
    } catch (error: any) {
      if (error.name === "AbortError") {
        // User cancelled
        return;
      }
      callbacks.onError(error.message || "Stream connection failed");
    }
  };

  connect();

  return controller;
}

/**
 * Cancel a running task.
 */
export async function cancelTask(taskId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/nlq/tasks/${taskId}/cancel`, {
    method: "POST",
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to cancel task: HTTP ${response.status}`);
  }
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
