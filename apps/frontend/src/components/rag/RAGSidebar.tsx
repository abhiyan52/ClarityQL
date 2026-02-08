import { useEffect } from "react";
import { MessageSquare, Trash2, Plus, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useRAGChatStore } from "@/store/ragChat";

export function RAGSidebar() {
    const {
        conversations,
        currentConversationId,
        fetchConversations,
        selectConversation,
        deleteConversation,
        createConversation,
    } = useRAGChatStore();

    useEffect(() => {
        fetchConversations();
    }, [fetchConversations]);

    return (
        <div className="flex h-full flex-col bg-muted/10">
            {/* Header */}
            <div className="flex items-center justify-between p-4">
                <h2 className="text-sm font-semibold flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Chat History
                </h2>
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => createConversation()}
                    title="New Chat"
                >
                    <Plus className="h-4 w-4" />
                </Button>
            </div>

            <Separator />

            {/* Conversation List */}
            <ScrollArea className="flex-1 p-2">
                {conversations.length === 0 ? (
                    <div className="text-center py-8 text-xs text-muted-foreground">
                        No history yet
                    </div>
                ) : (
                    <div className="space-y-1">
                        {conversations.map((conversation) => (
                            <div
                                key={conversation.id}
                                className={cn(
                                    "group flex items-center gap-2 rounded-lg px-3 py-2 text-xs transition-colors",
                                    "hover:bg-accent cursor-pointer",
                                    conversation.id === currentConversationId && "bg-accent"
                                )}
                                onClick={() => selectConversation(conversation.id)}
                            >
                                <MessageSquare className="h-3 w-3 shrink-0 text-muted-foreground" />
                                <span className="flex-1 truncate">{conversation.title}</span>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 opacity-0 group-hover:opacity-100 hover:text-destructive transition-all"
                                    onClick={async (e) => {
                                        e.stopPropagation();
                                        if (window.confirm("Are you sure you want to delete this conversation?")) {
                                            try {
                                                await deleteConversation(conversation.id);
                                            } catch (error) {
                                                alert("Failed to delete conversation. Please try again.");
                                            }
                                        }
                                    }}
                                >
                                    <Trash2 className="h-3 w-3" />
                                </Button>
                            </div>
                        ))}
                    </div>
                )}
            </ScrollArea>
        </div>
    );
}
