import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Send, Loader2, FileText, MessageSquarePlus, X, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import { streamTaskProgress, cancelTask, type ChunkResult, type RAGQueryResponse, submitQuery } from "@/api/rag";
import { useRAGChatStore, type RAGMessage as Message } from "@/store/ragChat";

interface RAGChatWindowProps {
  totalDocuments: number;
}

export function RAGChatWindow({ totalDocuments }: RAGChatWindowProps) {
  const queryClient = useQueryClient();
  const {
    messages,
    currentConversationId,
    isLoading,
    addMessage,
    updateMessage,
    setLoading,
    setAbortController,
    cancelCurrentQuery,
    createConversation,
    selectedDocumentIds,
  } = useRAGChatStore();

  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    // Refetch documents when messages change (e.g., new conversation created)
    queryClient.invalidateQueries({ queryKey: ["documents"] });
  }, [messages, queryClient]);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleCancel = async () => {
    if (isLoading) {
      const loadingMessage = messages.find(m => m.isLoading && m.taskId);
      if (loadingMessage?.taskId) {
        try {
          await cancelTask(loadingMessage.taskId);
        } catch (error) {
          console.error("Failed to cancel task:", error);
        }
      }
      cancelCurrentQuery();
    }
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    if (!currentConversationId) {
      createConversation();
    }

    addMessage({
      role: "user",
      content: trimmed,
    });

    setInput("");
    setLoading(true);

    const assistantId = addMessage({
      role: "assistant",
      content: "",
      isLoading: true,
      progressPercentage: 0,
      progressMessage: "Starting query...",
    });

    const controller = new AbortController();
    setAbortController(controller);

    try {
      const { task_id, conversation_id: newConvId } = await submitQuery({
        query: trimmed,
        document_ids: selectedDocumentIds.length > 0 ? selectedDocumentIds : undefined,
        conversation_id: (currentConversationId?.startsWith("temp-") ? undefined : currentConversationId) as string | undefined,
        top_k: 5,
        min_similarity: 0.0,
      }, { signal: controller.signal });

      if (currentConversationId?.startsWith("temp-")) {
        useRAGChatStore.setState({ currentConversationId: newConvId });
      }

      updateMessage(assistantId, {
        taskId: task_id,
      });

      streamTaskProgress(task_id, {
        onProgress: (data) => {
          updateMessage(assistantId, {
            progressPercentage: data.percentage,
            progressMessage: data.message,
          });
        },
        onComplete: (response: RAGQueryResponse) => {
          updateMessage(assistantId, {
            content: response.answer || "I couldn't find any relevant information in the selected documents for your query.",
            chunks: response.chunks,
            isLoading: false,
            progressPercentage: undefined,
            progressMessage: undefined,
          });
          setLoading(false);
          setAbortController(null);
        },
        onError: (error) => {
          updateMessage(assistantId, {
            content: `Sorry, I couldn't process your request. ${error}`,
            isLoading: false,
            progressPercentage: undefined,
            progressMessage: undefined,
            error: error,
          });
          setLoading(false);
          setAbortController(null);
        },
        onCancelled: () => {
          updateMessage(assistantId, {
            content: "Query was cancelled.",
            isLoading: false,
            progressPercentage: undefined,
            progressMessage: undefined,
          });
          setLoading(false);
          setAbortController(null);
        },
      });

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        updateMessage(assistantId, {
          content: "Query was cancelled.",
          isLoading: false,
          progressPercentage: undefined,
          progressMessage: undefined,
        });
        return;
      }

      let errorMessage = "Please try again.";
      if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === "string") {
        errorMessage = error;
      }

      updateMessage(assistantId, {
        content: `Sorry, I couldn't submit your query. ${errorMessage}`,
        isLoading: false,
        progressPercentage: undefined,
        progressMessage: undefined,
        error: errorMessage,
      });
      setLoading(false);
      setAbortController(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const documentCountText =
    selectedDocumentIds.length === 0
      ? `All documents (${totalDocuments})`
      : `${selectedDocumentIds.length} of ${totalDocuments} selected`;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b bg-background p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">RAG Query Chat</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Ask questions about your documents
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Searching:</span>
            <span className="font-medium">{documentCountText}</span>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1" ref={scrollRef}>
        {messages.length === 0 ? (
          <EmptyState totalDocuments={totalDocuments} selectedCount={selectedDocumentIds.length} />
        ) : (
          <div className="flex flex-col gap-4 py-4">
            {messages.map((message) => {
              const isUser = message.role === "user";
              return (
                <div
                  key={message.id}
                  className={cn(
                    "flex gap-3 px-4",
                    isUser ? "flex-row-reverse" : "flex-row"
                  )}
                >
                  <Avatar className="h-8 w-8 shrink-0">
                    <AvatarFallback
                      className={cn(
                        isUser ? "bg-primary text-primary-foreground" : "bg-chart-1 text-white"
                      )}
                    >
                      {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                    </AvatarFallback>
                  </Avatar>

                  <div className={cn(
                    "flex-1 space-y-2 overflow-hidden",
                    isUser ? "text-right" : "text-left"
                  )}>
                    <div className={cn(
                      "flex items-center gap-2",
                      isUser ? "justify-end" : "justify-start"
                    )}>
                      <span className="text-sm font-medium">
                        {isUser ? "You" : "ClarityQL"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {message.timestamp.toLocaleTimeString()}
                      </span>
                    </div>

                    {message.isLoading ? (
                      <LoadingIndicator
                        message={message}
                        onCancel={handleCancel}
                      />
                    ) : (
                      <>
                        <div className={cn(
                          "text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none",
                          message.error && "text-destructive",
                          isUser ? "ml-auto" : "mr-auto"
                        )}>
                          {isUser ? (
                            <p className="whitespace-pre-wrap">{message.content}</p>
                          ) : (
                            <ReactMarkdown>{message.content}</ReactMarkdown>
                          )}
                        </div>
                        {message.chunks && message.chunks.length > 0 && (
                          <ChunkResults chunks={message.chunks} />
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>

      <div className="border-t bg-background p-4">
        <div className="mx-auto max-w-4xl">
          <div className="relative flex items-end gap-2 rounded-lg border bg-background p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your documents..."
              disabled={isLoading || totalDocuments === 0}
              rows={1}
              className={cn(
                "flex-1 resize-none bg-transparent px-2 py-1.5 text-sm",
                "placeholder:text-muted-foreground focus:outline-none",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
            />
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!input.trim() || isLoading || totalDocuments === 0}
              className="shrink-0"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            {totalDocuments === 0
              ? "Upload documents to start querying"
              : selectedDocumentIds.length === 0
                ? "Searching all documents • Select specific documents to narrow your search"
                : `Searching ${selectedDocumentIds.length} selected document${selectedDocumentIds.length > 1 ? "s" : ""}`}
          </p>
        </div>
      </div>
    </div>
  );
}

function ChunkResults({ chunks }: { chunks: ChunkResult[] }) {
  return (
    <div className="mt-4 space-y-3 text-left">
      {chunks.map((chunk) => (
        <div key={chunk.chunk_id} className="p-3 bg-muted/50 rounded-lg space-y-2">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 text-xs">
              <FileText className="h-3 w-3 text-muted-foreground" />
              <span className="font-medium truncate">{chunk.document_title}</span>
              {chunk.page_number && (
                <span className="text-muted-foreground">• Page {chunk.page_number}</span>
              )}
            </div>
            <span className="text-xs font-medium text-primary shrink-0">
              {(chunk.similarity_score * 100).toFixed(0)}% match
            </span>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed line-clamp-3">
            {chunk.content}
          </p>
          {chunk.section && (
            <p className="text-xs text-muted-foreground mt-2">
              Section: {chunk.section}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function LoadingIndicator({
  message,
  onCancel
}: {
  message: Message;
  onCancel: () => void;
}) {
  const hasProgress = typeof message.progressPercentage === 'number';

  return (
    <div className="space-y-2">
      {hasProgress ? (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {message.progressMessage || "Processing..."}
            </p>
            <span className="text-xs text-muted-foreground">
              {Math.round(message.progressPercentage || 0)}%
            </span>
          </div>
          <Progress value={message.progressPercentage} className="h-1" />
        </>
      ) : (
        <div className="flex items-center gap-1">
          <div className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
          <div className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
          <div className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
        </div>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={onCancel}
        className="mt-2"
      >
        <X className="mr-1 h-3 w-3" />
        Cancel
      </Button>
    </div>
  );
}

function EmptyState({ totalDocuments, selectedCount }: { totalDocuments: number; selectedCount: number }) {
  return (
    <div className="flex h-full flex-col items-center justify-center p-8 text-center">
      <div className="rounded-full bg-primary/10 p-4">
        <MessageSquarePlus className="h-8 w-8 text-primary" />
      </div>
      <h2 className="mt-4 text-xl font-semibold">Start Chatting with Your Documents</h2>
      <p className="mt-2 max-w-md text-muted-foreground">
        {totalDocuments === 0
          ? "Upload documents to start asking questions and getting AI-powered answers."
          : `Ask questions about ${selectedCount === 0 ? "all your documents" : `the ${selectedCount} selected document${selectedCount > 1 ? "s" : ""}`}. The AI will search through them and provide relevant answers.`}
      </p>
    </div>
  );
}
