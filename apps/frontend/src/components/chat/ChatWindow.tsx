import { useEffect, useRef } from "react";
import { MessageSquarePlus } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { useChatStore } from "@/store/chat";
import { sendQuery } from "@/api/nlq";

export function ChatWindow() {
  const {
    conversations,
    currentConversationId,
    isLoading,
    createConversation,
    addMessage,
    updateMessage,
    setLoading,
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
    });

    setLoading(true);

    try {
      const response = await sendQuery({
        query: content,
        conversation_id: currentConversationId!,
      });

      updateMessage(assistantId, {
        content: response.success
          ? "Here are your results:"
          : `I encountered an error: ${response.error}`,
        response,
        isLoading: false,
      });
    } catch (error) {
      updateMessage(assistantId, {
        content: `Sorry, I couldn't process your request. ${error instanceof Error ? error.message : "Please try again."}`,
        isLoading: false,
      });
    } finally {
      setLoading(false);
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
