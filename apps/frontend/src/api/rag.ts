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

/**
 * Query documents using semantic search
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
