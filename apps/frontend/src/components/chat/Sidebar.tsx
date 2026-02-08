import { useEffect } from "react";
import { Plus, MessageSquare, Trash2, PanelLeftClose, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";
import { useAuth } from "@/contexts/AuthContext";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const {
    conversations,
    currentConversationId,
    createConversation,
    selectConversation,
    deleteConversation,
    loadConversations,
  } = useChatStore();

  const { user, logout } = useAuth();

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleNewChat = () => {
    createConversation();
  };

  const handleSelectConversation = (id: string) => {
    selectConversation(id);
  };

  return (
    <div
      className={cn(
        "flex h-full w-64 flex-col border-r bg-muted/30 transition-all duration-300",
        !isOpen && "-ml-64"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4">
        <h2 className="text-lg font-semibold">Chats</h2>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>

      {/* New Chat Button */}
      <div className="px-4 pb-4">
        <Button onClick={handleNewChat} className="w-full gap-2">
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>

      <Separator />

      {/* Conversation List */}
      <ScrollArea className="flex-1 p-2">
        <div className="space-y-1">
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={cn(
                "group flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                "hover:bg-accent cursor-pointer",
                conversation.id === currentConversationId && "bg-accent"
              )}
              onClick={() => handleSelectConversation(conversation.id)}
            >
              <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{conversation.title}</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 opacity-0 group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(conversation.id);
                }}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Footer */}
      <Separator />
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground truncate">{user?.email}</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={logout}
            title="Logout"
          >
            <LogOut className="h-3 w-3" />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          ClarityQL v0.1.0
        </p>
      </div>
    </div>
  );
}
