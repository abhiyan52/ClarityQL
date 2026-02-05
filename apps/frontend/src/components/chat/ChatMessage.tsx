import { Bot, User } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import type { ChatMessage as ChatMessageType } from "@/types";
import { ResultsPanel } from "@/components/results/ResultsPanel";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
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
          {message.response?.intent && (
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                message.response.intent === "refine"
                  ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                  : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
              )}
            >
              {message.response.intent === "refine" ? "Refined" : "New Query"}
            </span>
          )}
        </div>

        {isLoading ? (
          <LoadingIndicator />
        ) : (
          <>
            <p className="text-sm leading-relaxed">{message.content}</p>
            {message.response && <ResultsPanel response={message.response} />}
          </>
        )}
      </div>
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
