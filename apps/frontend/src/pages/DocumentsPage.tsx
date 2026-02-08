import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, Loader2, CheckCircle2, XCircle, Clock, Eye, PanelLeft, Moon, Sun, MessageSquare, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { uploadDocument, listDocuments, type Document } from "@/api/rag";
import { RAGChatWindow } from "@/components/rag/RAGChatWindow";
import { RAGSidebar } from "@/components/rag/RAGSidebar";
import { DocumentViewer } from "@/components/rag/DocumentViewer";
import { useRAGChatStore } from "@/store/ragChat";

export function DocumentsPage() {
  const {
    selectedDocumentIds,
    setSelectedDocumentIds,
    toggleDocumentSelection
  } = useRAGChatStore();

  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerDocumentId, setViewerDocumentId] = useState<string | undefined>();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [docLibraryOpen, setDocLibraryOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle("dark");
  };

  // Fetch documents
  const { data: documentsData, isLoading: isLoadingDocuments } = useQuery({
    queryKey: ["documents"],
    queryFn: () => listDocuments(),
    refetchInterval: 5000,
  });

  const documents = documentsData?.documents || [];

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: (_data, _variables) => {
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
    event.target.value = "";
  };

  const handleToggleSelect = (documentId: string) => {
    toggleDocumentSelection(documentId);
  };

  const selectAllDocuments = () => {
    const readyDocuments = documents
      .filter(doc => doc.processing_status === "ready")
      .map(doc => doc.id);
    setSelectedDocumentIds(readyDocuments);
  };

  const clearSelection = () => {
    setSelectedDocumentIds([]);
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
    <div className={cn("flex h-screen flex-col bg-background", darkMode && "dark")}>
      {/* Top Header */}
      <header className="flex h-14 items-center justify-between border-b px-4 bg-background">
        <div className="flex items-center gap-2">
          {!sidebarOpen && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(true)}
              title="Show chat history"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          )}
          <h1 className="text-lg font-semibold">ClarityQL</h1>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            Beta
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => navigate("/")}
            className="gap-2"
          >
            <MessageSquare className="h-4 w-4" />
            NLQ Chat
          </Button>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setDocLibraryOpen(!docLibraryOpen)}
            className="gap-2"
          >
            <FileText className="h-4 w-4" />
            Documents
          </Button>
          <Button variant="ghost" size="icon" onClick={toggleDarkMode}>
            {darkMode ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Column 1 - Chat History (Collapsible) */}
        <div
          className={cn(
            "border-r bg-muted/20 flex flex-col transition-all duration-300",
            sidebarOpen ? "w-64" : "w-0 overflow-hidden"
          )}
        >
          <RAGSidebar onClose={() => setSidebarOpen(false)} />
        </div>

        {/* Column 2 - Chat Window */}
        <div className="flex-1 flex flex-col">
          <RAGChatWindow
            totalDocuments={readyCount}
          />
        </div>

        {/* Column 3 - Document Library (Collapsible, right side) */}
        <div
          className={cn(
            "border-l bg-muted/20 flex flex-col transition-all duration-300",
            docLibraryOpen ? "w-[400px]" : "w-0 overflow-hidden"
          )}
        >
          {/* Header */}
          <div className="border-b bg-background p-4">
            <div className="flex items-center justify-between mb-3">
              <h1 className="text-xl font-semibold">Document Library</h1>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setDocLibraryOpen(false)}
                className="h-8 w-8"
                title="Close document library"
              >
                <X className="h-4 w-4" />
              </Button>
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
                {selectedDocumentIds.length > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={clearSelection}
                    className="flex-1"
                  >
                    Clear ({selectedDocumentIds.length})
                  </Button>
                )}
              </div>
              {(selectedDocumentIds.length > 0 || readyCount > 0) && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => openViewer(selectedDocumentIds[0])}
                  className="w-full gap-2"
                >
                  <Eye className="h-4 w-4" />
                  View {selectedDocumentIds.length > 0 ? `Selected (${selectedDocumentIds.length})` : `All (${readyCount})`}
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
                    isSelected={selectedDocumentIds.includes(doc.id)}
                    onToggleSelect={() => handleToggleSelect(doc.id)}
                    onView={() => openViewer(doc.id)}
                  />
                ))
              )}
            </div>
          </ScrollArea>
        </div>

      {/* Document Viewer Modal */}
      {viewerOpen && (
        <DocumentViewer
          documents={selectedDocumentIds.length > 0
            ? documents.filter(doc => selectedDocumentIds.includes(doc.id))
            : documents.filter(doc => doc.processing_status === "ready")
          }
          selectedDocumentId={viewerDocumentId}
          onClose={closeViewer}
        />
      )}
    </div>
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
        <div className="flex-1 min-w-0 overflow-hidden" onClick={() => isReady && onToggleSelect()}>
          <div className="relative group/title">
            <h3 className="font-medium text-sm truncate" title={document.file_name || document.title}>
              {document.file_name || document.title}
            </h3>
            {/* Tooltip for truncated filename */}
            <div className="absolute left-0 top-full mt-1 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 invisible group-hover/title:opacity-100 group-hover/title:visible transition-opacity duration-200 z-50 whitespace-nowrap max-w-[300px] overflow-hidden text-ellipsis">
              {document.file_name || document.title}
            </div>
          </div>
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
