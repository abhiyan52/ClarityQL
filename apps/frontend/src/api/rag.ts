/**
 * API client for RAG document management
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function getAuthToken(): string | null {
  return localStorage.getItem("clarityql_auth_token");
}

export interface Document {
  id: string;
  title: string;
  file_name?: string;
  description?: string;
  language: string;
  chunk_count: number;
  source_type: string;
  visibility: string;
  processing_status: string;
  processing_error?: string;
  file_size_bytes?: number;
  mime_type?: string;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  task_id: string;
  celery_task_id: string;
  status: string;
  message: string;
  status_url: string;
  is_reprocessing?: boolean;
  existing_document_id?: string;
}

export interface TaskStatus {
  task_id: string;
  celery_task_id: string;
  task_type: string;
  task_name: string;
  status: string;
  progress: number;
  progress_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  result?: any;
  error_message?: string;
}

export interface DocumentsResponse {
  total: number;
  page: number;
  page_size: number;
  documents: Document[];
}

/**
 * Upload a document for ingestion
 */
export async function uploadDocument(
  file: File,
  options?: {
    document_title?: string;
    description?: string;
    language?: string;
    max_chunk_tokens?: number;
    chunk_overlap_tokens?: number;
  }
): Promise<UploadResponse> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const formData = new FormData();
  formData.append("file", file);

  if (options?.document_title) {
    formData.append("document_title", options.document_title);
  }
  if (options?.description) {
    formData.append("description", options.description);
  }
  if (options?.language) {
    formData.append("language", options.language);
  }
  if (options?.max_chunk_tokens) {
    formData.append("max_chunk_tokens", options.max_chunk_tokens.toString());
  }
  if (options?.chunk_overlap_tokens) {
    formData.append("chunk_overlap_tokens", options.chunk_overlap_tokens.toString());
  }

  const response = await fetch(`${API_BASE_URL}/api/rag/ingest`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to upload document");
  }

  return response.json();
}

/**
 * Get task status for document processing
 */
export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/api/rag/tasks/${taskId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to get task status");
  }

  return response.json();
}

/**
 * List documents for the current user's tenant
 */
export async function listDocuments(
  page: number = 1,
  pageSize: number = 20
): Promise<DocumentsResponse> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(
    `${API_BASE_URL}/api/rag/documents?page=${page}&page_size=${pageSize}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to fetch documents");
  }

  return response.json();
}

/**
 * Get a specific document with full details
 */
export async function getDocument(documentId: string): Promise<Document> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/api/rag/documents/${documentId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to fetch document");
  }

  return response.json();
}

/**
 * RAG Query types and function
 */
export interface ChunkResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  page_number?: number;
  section?: string;
  chunk_index: number;
  similarity_score: number;
  token_count?: number;
}

export interface RAGQueryResponse {
  conversation_id: string;
  query: string;
  answer: string;
  chunks: ChunkResult[];
  documents: Array<{
    document_id: string;
    title: string;
    description?: string;
    language: string;
    chunk_count: number;
  }>;
  total_chunks_found: number;
}

export interface RAGQueryRequest {
  query: string;
  document_ids?: string[];
  conversation_id?: string;
  top_k?: number;
  min_similarity?: number;
}

export interface ProgressData {
  percentage: number;
  message: string;
  current: number;
  total: number;
}

export interface RAGStreamCallbacks {
  onProgress: (data: ProgressData) => void;
  onComplete: (response: RAGQueryResponse) => void;
  onError: (error: string) => void;
  onCancelled?: () => void;
}

/**
 * Submit a RAG query for background processing.
 * Returns a task_id and conversation_id that can be used to stream progress.
 */
export async function submitQuery(
  request: RAGQueryRequest,
  options?: { signal?: AbortSignal }
): Promise<{ task_id: string; conversation_id: string }> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/api/rag/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    signal: options?.signal,
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
 * Fetch all RAG conversations for the user
 */
export async function fetchConversations(): Promise<Array<{
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: string;
}>> {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const response = await fetch(`${API_BASE_URL}/api/rag/conversations`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) throw new Error("Failed to fetch conversations");
  return response.json();
}

/**
 * Fetch a single RAG conversation with messages
 */
export async function fetchConversation(id: string): Promise<{
  id: string;
  title: string;
  status: string;
  messages: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
    meta?: any;
  }>;
}> {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const response = await fetch(`${API_BASE_URL}/api/rag/conversations/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) throw new Error("Failed to fetch conversation");
  return response.json();
}

/**
 * Delete a RAG conversation
 */
export async function deleteConversation(id: string): Promise<void> {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const response = await fetch(`${API_BASE_URL}/api/rag/conversations/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) throw new Error("Failed to delete conversation");
}

/**
 * Stream task progress via SSE using fetch + ReadableStream.
 * EventSource doesn't support custom headers, so we use fetch instead.
 * 
 * Returns an AbortController that can be used to cancel the stream.
 */
export function streamTaskProgress(
  taskId: string,
  callbacks: RAGStreamCallbacks
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
        `${API_BASE_URL}/api/rag/tasks/${taskId}/stream`,
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
 * Cancel a running RAG task.
 */
export async function cancelTask(taskId: string): Promise<void> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/api/rag/tasks/${taskId}/cancel`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to cancel task");
  }
}

/**
 * @deprecated Use submitQuery and streamTaskProgress instead
 * Query documents using semantic search (synchronous - kept for backward compatibility)
 */
export async function queryDocuments(
  request: RAGQueryRequest
): Promise<RAGQueryResponse> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/api/rag/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to query documents");
  }

  return response.json();
}
