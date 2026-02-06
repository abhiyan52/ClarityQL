import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, Loader2, CheckCircle2, XCircle, Clock, ArrowLeft, Eye } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { uploadDocument, listDocuments, getTaskStatus, type Document } from "@/api/rag";
import { RAGChatWindow } from "@/components/rag/RAGChatWindow";
import { DocumentViewer } from "@/components/rag/DocumentViewer";

export function DocumentsPage() {
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState<Map<string, { taskId: string; fileName: string }>>(new Map());
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerDocumentId, setViewerDocumentId] = useState<string | undefined>();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // Fetch documents
  const { data: documentsData, isLoading: isLoadingDocuments } = useQuery({
    queryKey: ["documents"],
    queryFn: () => listDocuments(),
    refetchInterval: 5000, // Poll every 5 seconds to update processing status
  });

  const documents = documentsData?.documents || [];

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: (data, variables) => {
      // Track the upload task
      const file = variables as File;
      setUploadingFiles(prev => new Map(prev).set(data.task_id, { taskId: data.task_id, fileName: file.name }));
      // Refetch documents
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    for (const file of Array.from(files)) {
      try {
        await uploadMutation.mutateAsync(file);
      } catch (error) {
        console.error("Upload failed:", error);
      }
    }

    // Reset input
    event.target.value = "";
  };

  const toggleDocumentSelection = (documentId: string) => {
    setSelectedDocuments(prev => {
      if (prev.includes(documentId)) {
        return prev.filter(id => id !== documentId);
      } else {
        return [...prev, documentId];
      }
    });
  };

  const selectAllDocuments = () => {
    const readyDocuments = documents
      .filter(doc => doc.processing_status === "ready")
      .map(doc => doc.id);
    setSelectedDocuments(readyDocuments);
  };

  const clearSelection = () => {
    setSelectedDocuments([]);
  };

  const openViewer = (documentId?: string) => {
    setViewerDocumentId(documentId);
    setViewerOpen(true);
  };

  const closeViewer = () => {
    setViewerOpen(false);
    setViewerDocumentId(undefined);
  };

  // Count documents by status
  const readyCount = documents.filter(doc => doc.processing_status === "ready").length;
  const processingCount = documents.filter(doc => 
    !["ready", "failed"].includes(doc.processing_status)
  ).length;

  return (
    <div className="flex h-screen bg-background">
      {/* Left Panel - Document Management */}
      <div className="w-96 border-r bg-muted/20 flex flex-col">
        {/* Header */}
        <div className="border-b bg-background p-4">
          <div className="flex items-center gap-2 mb-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate("/")}
              className="shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="text-xl font-semibold">Document Library</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Upload and manage documents for RAG queries
          </p>
        </div>

        {/* Upload Section */}
        <div className="p-4 border-b">
          <label htmlFor="file-upload">
            <div className="cursor-pointer rounded-lg border-2 border-dashed border-muted-foreground/25 bg-background p-6 text-center hover:border-primary hover:bg-accent transition-colors">
              <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
              <p className="text-sm font-medium">Click to upload documents</p>
              <p className="text-xs text-muted-foreground mt-1">
                PDF, DOCX, TXT, MD supported
              </p>
            </div>
            <input
              id="file-upload"
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md"
              onChange={handleFileUpload}
              className="hidden"
              disabled={uploadMutation.isPending}
            />
          </label>
        </div>

        {/* Stats */}
        <div className="p-4 border-b bg-background">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <span className="text-muted-foreground">Ready:</span>
              <span className="font-semibold">{readyCount}</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-blue-600" />
              <span className="text-muted-foreground">Processing:</span>
              <span className="font-semibold">{processingCount}</span>
            </div>
          </div>
        </div>

        {/* Selection Controls */}
        {readyCount > 0 && (
          <div className="p-4 border-b bg-background">
            <div className="flex gap-2 mb-2">
              <Button
                size="sm"
                variant="outline"
                onClick={selectAllDocuments}
                className="flex-1"
              >
                Select All ({readyCount})
              </Button>
              {selectedDocuments.length > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={clearSelection}
                  className="flex-1"
                >
                  Clear ({selectedDocuments.length})
                </Button>
              )}
            </div>
            {(selectedDocuments.length > 0 || readyCount > 0) && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => openViewer(selectedDocuments[0])}
                className="w-full gap-2"
              >
                <Eye className="h-4 w-4" />
                View {selectedDocuments.length > 0 ? `Selected (${selectedDocuments.length})` : `All (${readyCount})`}
              </Button>
            )}
          </div>
        )}

        {/* Documents List */}
        <ScrollArea className="flex-1">
          <div className="p-4 space-y-2">
            {isLoadingDocuments ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : documents.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No documents yet</p>
                <p className="text-xs mt-1">Upload your first document to get started</p>
              </div>
            ) : (
              documents.map(doc => (
                <DocumentCard
                  key={doc.id}
                  document={doc}
                  isSelected={selectedDocuments.includes(doc.id)}
                  onToggleSelect={() => toggleDocumentSelection(doc.id)}
                  onView={() => openViewer(doc.id)}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Right Panel - RAG Chat */}
      <div className="flex-1 flex flex-col">
        <RAGChatWindow 
          selectedDocuments={selectedDocuments}
          totalDocuments={readyCount}
        />
      </div>

      {/* Document Viewer Modal */}
      {viewerOpen && (
        <DocumentViewer
          documents={selectedDocuments.length > 0 
            ? documents.filter(doc => selectedDocuments.includes(doc.id))
            : documents.filter(doc => doc.processing_status === "ready")
          }
          selectedDocumentId={viewerDocumentId}
          onClose={closeViewer}
        />
      )}
    </div>
  );
}

interface DocumentCardProps {
  document: Document;
  isSelected: boolean;
  onToggleSelect: () => void;
  onView: () => void;
}

function DocumentCard({ document, isSelected, onToggleSelect, onView }: DocumentCardProps) {
  const statusConfig = getStatusConfig(document.processing_status);
  const isReady = document.processing_status === "ready";

  return (
    <Card
      className={cn(
        "p-3 transition-all hover:shadow-md",
        isSelected && "ring-2 ring-primary bg-accent",
        !isReady && "opacity-60"
      )}
    >
      <div className="flex items-start gap-3">
        {/* Checkbox/Status Icon */}
        <div 
          className="shrink-0 mt-0.5 cursor-pointer"
          onClick={() => isReady && onToggleSelect()}
        >
          {isReady ? (
            <div
              className={cn(
                "h-5 w-5 rounded border-2 flex items-center justify-center transition-colors",
                isSelected
                  ? "bg-primary border-primary"
                  : "border-muted-foreground/25"
              )}
            >
              {isSelected && <CheckCircle2 className="h-3 w-3 text-primary-foreground" />}
            </div>
          ) : (
            statusConfig.icon
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0" onClick={() => isReady && onToggleSelect()}>
          <h3 className="font-medium text-sm truncate">{document.title}</h3>
          {document.description && (
            <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
              {document.description}
            </p>
          )}
          
          {/* Status */}
          <div className="flex items-center gap-2 mt-2">
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded-full font-medium",
                statusConfig.className
              )}
            >
              {statusConfig.label}
            </span>
            {isReady && (
              <span className="text-xs text-muted-foreground">
                {document.chunk_count} chunks
              </span>
            )}
          </div>

          {/* Error message */}
          {document.processing_error && (
            <p className="text-xs text-destructive mt-2">
              {document.processing_error}
            </p>
          )}
        </div>

        {/* Actions */}
        {isReady && (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 h-8 w-8"
            onClick={(e) => {
              e.stopPropagation();
              onView();
            }}
          >
            <Eye className="h-4 w-4" />
          </Button>
        )}
      </div>
    </Card>
  );
}

function getStatusConfig(status: string) {
  switch (status) {
    case "ready":
      return {
        label: "Ready",
        className: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
        icon: <CheckCircle2 className="h-5 w-5 text-green-600" />,
      };
    case "failed":
      return {
        label: "Failed",
        className: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
        icon: <XCircle className="h-5 w-5 text-red-600" />,
      };
    case "parsing":
      return {
        label: "Parsing",
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
        icon: <Loader2 className="h-5 w-5 animate-spin text-blue-600" />,
      };
    case "chunking":
      return {
        label: "Chunking",
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
        icon: <Loader2 className="h-5 w-5 animate-spin text-blue-600" />,
      };
    case "embedding":
      return {
        label: "Embedding",
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
        icon: <Loader2 className="h-5 w-5 animate-spin text-blue-600" />,
      };
    default:
      return {
        label: status.charAt(0).toUpperCase() + status.slice(1),
        className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
        icon: <Clock className="h-5 w-5 text-gray-600" />,
      };
  }
}
