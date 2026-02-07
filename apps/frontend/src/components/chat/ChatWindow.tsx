import { useEffect, useRef } from "react";
import { MessageSquarePlus } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { useChatStore } from "@/store/chat";
import { submitQuery, streamTaskProgress, cancelTask } from "@/api/nlq";

export function ChatWindow() {
  const {
    conversations,
    currentConversationId,
    isLoading,
    createConversation,
    addMessage,
    updateMessage,
    setLoading,
    setAbortController,
    getMessages,
  } = useChatStore();

  const scrollRef = useRef<HTMLDivElement>(null);
  const messages = getMessages();

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Create initial conversation if none exists
  useEffect(() => {
    if (conversations.length === 0) {
      createConversation();
    }
  }, [conversations.length, createConversation]);

  const handleSend = async (content: string) => {
    if (!currentConversationId) {
      createConversation();
    }

    // Add user message
    addMessage({ role: "user", content });

    // Add loading assistant message
    const assistantId = addMessage({
      role: "assistant",
      content: "",
      isLoading: true,
      progressPercentage: 0,
      progressMessage: "Starting query processing...",
    });

    setLoading(true);

    try {
      // Get the last assistant message's backend conversation_id if it exists
      const lastAssistantMessage = messages
        .filter(m => m.role === 'assistant' && m.response)
        .pop();
      const backendConversationId = lastAssistantMessage?.response?.conversation_id;

      // Step 1: Submit query for background processing
      const { task_id } = await submitQuery({
        query: content,
        conversation_id: backendConversationId,
      });

      // Update message with task ID
      updateMessage(assistantId, {
        taskId: task_id,
      });

      // Step 2: Stream progress via SSE
      const controller = streamTaskProgress(task_id, {
        onProgress: (data) => {
          updateMessage(assistantId, {
            progressPercentage: data.percentage,
            progressMessage: data.message,
          });
        },
        onComplete: (response) => {
          updateMessage(assistantId, {
            content: "Here are your results:",
            response,
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

      // Store controller so cancel button can use it
      setAbortController(controller);
    } catch (error) {
      let errorMessage = "Please try again.";
      if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === "string") {
        errorMessage = error;
      } else if (error && typeof error === "object") {
        errorMessage = JSON.stringify(error);
      }
      updateMessage(assistantId, {
        content: `Sorry, I couldn't process your request. ${errorMessage}`,
        isLoading: false,
        progressPercentage: undefined,
        progressMessage: undefined,
      });
      setLoading(false);
      setAbortController(null);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="divide-y">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Input area */}
      <ChatInput onSend={handleSend} isLoading={isLoading} />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center p-8 text-center">
      <div className="rounded-full bg-primary/10 p-4">
        <MessageSquarePlus className="h-8 w-8 text-primary" />
      </div>
      <h2 className="mt-4 text-xl font-semibold">Welcome to ClarityQL</h2>
      <p className="mt-2 max-w-md text-muted-foreground">
        Ask questions about your data in natural language. I'll translate them
        into SQL queries and show you the results with visualizations.
      </p>
      <div className="mt-6 grid gap-2 text-sm">
        <p className="font-medium text-muted-foreground">Try asking:</p>
        <div className="flex flex-wrap justify-center gap-2">
          {[
            "Show me total revenue by region",
            "Top 10 products by sales",
            "Monthly order trends",
          ].map((example) => (
            <button
              key={example}
              className="rounded-full border bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
