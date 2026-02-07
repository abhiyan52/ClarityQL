import { useState, useEffect } from "react";
import { X, ChevronLeft, ChevronRight, Download, Loader2, AlertCircle } from "lucide-react";
import DocViewer, { DocViewerRenderers } from "react-doc-viewer";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { Document } from "@/api/rag";
import * as pdfjsLib from 'pdfjs-dist';

// Configure PDF.js worker from CDN
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function getAuthToken(): string | null {
  return localStorage.getItem("clarityql_auth_token");
}

interface DocumentViewerProps {
  documents: Document[];
  selectedDocumentId?: string;
  onClose: () => void;
}

export function DocumentViewer({ documents, selectedDocumentId, onClose }: DocumentViewerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [documentBlobUrl, setDocumentBlobUrl] = useState<string | null>(null);

  // Filter to only ready documents
  const viewableDocuments = documents.filter(doc => doc.processing_status === "ready");
  
  // Get current document
  const currentDocument = viewableDocuments[currentIndex];

  // Set initial document
  useEffect(() => {
    if (selectedDocumentId) {
      const index = viewableDocuments.findIndex(doc => doc.id === selectedDocumentId);
      if (index !== -1) {
        setCurrentIndex(index);
      }
    }
  }, [selectedDocumentId, viewableDocuments]);

  // Fetch document with authentication and create blob URL
  useEffect(() => {
    const fetchDocument = async () => {
      if (!currentDocument) return;

      setLoading(true);
      setError(null);

      // Clean up previous blob URL
      if (documentBlobUrl) {
        window.URL.revokeObjectURL(documentBlobUrl);
        setDocumentBlobUrl(null);
      }

      const token = getAuthToken();
      const url = `${API_BASE_URL}/api/rag/documents/${currentDocument.id}/download`;

      try {
        const response = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch document: ${response.statusText}`);
        }

        const blob = await response.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        setDocumentBlobUrl(blobUrl);
        setLoading(false);
      } catch (err) {
        console.error("Failed to fetch document:", err);
        setError(err instanceof Error ? err.message : "Failed to load document");
        setLoading(false);
      }
    };

    fetchDocument();

    // Cleanup blob URL on unmount or document change
    return () => {
      if (documentBlobUrl) {
        window.URL.revokeObjectURL(documentBlobUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDocument?.id]);

  if (viewableDocuments.length === 0) {
    return (
      <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
        <div className="flex h-full items-center justify-center">
          <div className="bg-background border rounded-lg p-8 text-center">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <h2 className="text-xl font-semibold mb-2">No Documents to View</h2>
            <p className="text-muted-foreground mb-4">
              Selected documents are not ready for viewing yet.
            </p>
            <Button onClick={onClose}>Close</Button>
          </div>
        </div>
      </div>
    );
  }

  const token = getAuthToken();

  // Prepare document for viewer - use blob URL if available
  const docs = documentBlobUrl ? [{
    uri: documentBlobUrl,
    fileName: currentDocument.title,
    fileType: getFileExtension(currentDocument.title, currentDocument.mime_type),
  }] : [];

  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      setLoading(true);
      setError(null);
    }
  };

  const handleNext = () => {
    if (currentIndex < viewableDocuments.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setLoading(true);
      setError(null);
    }
  };

  const handleDownload = () => {
    const url = `${API_BASE_URL}/api/rag/documents/${currentDocument.id}/download`;
    const link = document.createElement("a");
    link.href = url;
    link.download = currentDocument.title;
    link.target = "_blank";
    // Add authorization header via fetch and blob
    fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then(response => response.blob())
      .then(blob => {
        const blobUrl = window.URL.createObjectURL(blob);
        link.href = blobUrl;
        link.click();
        window.URL.revokeObjectURL(blobUrl);
      })
      .catch(err => {
        console.error("Download failed:", err);
        // Fallback to direct link
        window.open(url, "_blank");
      });
  };

  return (
    <div className="fixed inset-0 z-50 bg-background">
      {/* Header */}
      <div className="border-b bg-background p-4 flex items-center justify-between">
        <div className="flex items-center gap-4 flex-1 min-w-0">
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
          
          <div className="flex-1 min-w-0">
            <h2 className="font-semibold truncate">{currentDocument.title}</h2>
            <p className="text-sm text-muted-foreground">
              {currentIndex + 1} of {viewableDocuments.length}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Navigation */}
          {viewableDocuments.length > 1 && (
            <div className="flex items-center gap-1 border rounded-lg p-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={handlePrevious}
                disabled={currentIndex === 0}
                className="h-8 w-8"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleNext}
                disabled={currentIndex === viewableDocuments.length - 1}
                className="h-8 w-8"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}

          {/* Download */}
          <Button variant="outline" size="sm" onClick={handleDownload} className="gap-2">
            <Download className="h-4 w-4" />
            Download
          </Button>
        </div>
      </div>

      {/* Document List Sidebar (if multiple documents) */}
      {viewableDocuments.length > 1 && (
        <div className="absolute left-0 top-[73px] bottom-0 w-64 border-r bg-muted/20 z-10">
          <ScrollArea className="h-full">
            <div className="p-2 space-y-1">
              {viewableDocuments.map((doc, idx) => (
                <button
                  key={doc.id}
                  onClick={() => {
                    setCurrentIndex(idx);
                    setLoading(true);
                    setError(null);
                  }}
                  className={cn(
                    "w-full text-left p-3 rounded-lg text-sm transition-colors",
                    "hover:bg-accent",
                    idx === currentIndex && "bg-accent ring-2 ring-primary"
                  )}
                >
                  <p className="font-medium truncate">{doc.title}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {doc.chunk_count} chunks • {formatFileSize(doc.file_size_bytes)}
                  </p>
                </button>
              ))}
            </div>
          </ScrollArea>
        </div>
      )}

      {/* Viewer Area */}
      <div
        className={cn(
          "h-[calc(100vh-73px)] bg-muted/10",
          viewableDocuments.length > 1 && "ml-64"
        )}
      >
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center z-20">
            <div className="bg-background border rounded-lg p-6 text-center max-w-md">
              <AlertCircle className="h-10 w-10 mx-auto mb-3 text-destructive" />
              <h3 className="font-semibold mb-2">Failed to Load Document</h3>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button onClick={() => setError(null)}>Try Again</Button>
            </div>
          </div>
        )}

        {!error && docs.length > 0 && (
          <DocViewer
            key={currentDocument.id}
            documents={docs}
            pluginRenderers={DocViewerRenderers}
            config={{
              header: {
                disableHeader: true,
                disableFileName: true,
              },
            }}
            style={{ height: "100%" }}
            className="document-viewer"
          />
        )}
      </div>
    </div>
  );
}

// Helper functions
function getFileExtension(fileName: string, mimeType?: string): string {
  // Try to extract from filename first
  const match = fileName.match(/\.([^.]+)$/);
  if (match) {
    return match[1].toLowerCase();
  }

  // Fall back to mime type
  if (mimeType) {
    const mimeMap: Record<string, string> = {
      "application/pdf": "pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
      "application/msword": "doc",
      "text/plain": "txt",
      "text/markdown": "md",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
      "application/vnd.ms-excel": "xls",
    };
    return mimeMap[mimeType] || "pdf";
  }

  return "pdf"; // Default
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return "Unknown size";
  
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}
