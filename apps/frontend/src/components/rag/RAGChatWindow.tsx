import { useState, useRef, useEffect } from "react";
import { Send, Loader2, FileText, MessageSquarePlus, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import { queryDocuments, type ChunkResult } from "@/api/rag";

interface RAGChatWindowProps {
  selectedDocuments: string[];
  totalDocuments: number;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  isLoading?: boolean;
  chunks?: ChunkResult[];
  conversationId?: string;
}

export function RAGChatWindow({ selectedDocuments, totalDocuments }: RAGChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    // Add loading assistant message
    const loadingId = (Date.now() + 1).toString();
    setMessages(prev => [
      ...prev,
      {
        id: loadingId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isLoading: true,
      },
    ]);

    try {
      // Call real RAG API
      const response = await queryDocuments({
        query: trimmed,
        document_ids: selectedDocuments.length > 0 ? selectedDocuments : undefined,
        conversation_id: conversationId,
        top_k: 5,
        min_similarity: 0.0,
      });

      // Update conversation ID for context continuity
      setConversationId(response.conversation_id);

      // Format response message
      const chunksText = response.chunks.length > 0
        ? `I found ${response.total_chunks_found} relevant ${response.total_chunks_found === 1 ? 'passage' : 'passages'} across ${response.documents.length} ${response.documents.length === 1 ? 'document' : 'documents'}:`
        : "I couldn't find any relevant information in the selected documents for your query.";

      setMessages(prev =>
        prev.map(msg =>
          msg.id === loadingId
            ? {
                ...msg,
                content: chunksText,
                isLoading: false,
                chunks: response.chunks,
                conversationId: response.conversation_id,
              }
            : msg
        )
      );
    } catch (error) {
      console.error("RAG query failed:", error);
      const errorMessage = error instanceof Error ? error.message : "An error occurred";
      
      setMessages(prev =>
        prev.map(msg =>
          msg.id === loadingId
            ? {
                ...msg,
                content: `Sorry, I encountered an error: ${errorMessage}`,
                isLoading: false,
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const documentCountText = 
    selectedDocuments.length === 0
      ? `All documents (${totalDocuments})`
      : `${selectedDocuments.length} of ${totalDocuments} selected`;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
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

      {/* Messages area */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        {messages.length === 0 ? (
          <EmptyState totalDocuments={totalDocuments} selectedCount={selectedDocuments.length} />
        ) : (
          <div className="divide-y">
            {messages.map(message => (
              <ChatMessage key={message.id} message={message} />
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Input area */}
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
              : selectedDocuments.length === 0
              ? "Searching all documents • Select specific documents to narrow your search"
              : `Searching ${selectedDocuments.length} selected document${selectedDocuments.length > 1 ? "s" : ""}`}
          </p>
        </div>
      </div>
    </div>
  );
}

interface ChatMessageProps {
  message: Message;
}

function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isLoading = message.isLoading;

  return (
    <div
      className={cn(
        "flex gap-4 p-4",
        isUser ? "bg-background" : "bg-muted/50"
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

      <div className="flex-1 space-y-2 overflow-hidden">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            {isUser ? "You" : "ClarityQL"}
          </span>
          <span className="text-xs text-muted-foreground">
            {message.timestamp.toLocaleTimeString()}
          </span>
        </div>

        {isLoading ? (
          <LoadingIndicator />
        ) : (
          <>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
            {message.chunks && message.chunks.length > 0 && (
              <ChunkResults chunks={message.chunks} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface ChunkResultsProps {
  chunks: ChunkResult[];
}

function ChunkResults({ chunks }: ChunkResultsProps) {
  return (
    <div className="mt-4 space-y-3">
      {chunks.map((chunk, idx) => (
        <Card key={chunk.chunk_id} className="p-3 bg-muted/50">
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
        </Card>
      ))}
    </div>
  );
}

function LoadingIndicator() {
  return (
    <div className="flex items-center gap-1">
      <div className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
      <div className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
      <div className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
    </div>
  );
}

interface EmptyStateProps {
  totalDocuments: number;
  selectedCount: number;
}

function EmptyState({ totalDocuments, selectedCount }: EmptyStateProps) {
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
      {totalDocuments > 0 && (
        <div className="mt-6 grid gap-2 text-sm">
          <p className="font-medium text-muted-foreground">Try asking:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {[
              "What are the key findings?",
              "Summarize the main points",
              "What does it say about...?",
            ].map(example => (
              <button
                key={example}
                className="rounded-full border bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
