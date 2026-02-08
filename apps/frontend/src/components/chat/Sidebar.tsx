import { useEffect, useState } from "react";
import { Plus, Trash2, PanelLeftClose, LogOut, AlertTriangle } from "lucide-react";
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
    deleteError,
    clearDeleteError,
  } = useChatStore();

  const { user, logout } = useAuth();
  
  // State for delete confirmation dialog
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);
  const [conversationTitleToDelete, setConversationTitleToDelete] = useState<string>("");
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleNewChat = () => {
    createConversation();
  };

  const handleSelectConversation = (id: string) => {
    selectConversation(id);
  };

  const handleDeleteClick = (e: React.MouseEvent, id: string, title: string) => {
    e.stopPropagation();
    setConversationToDelete(id);
    setConversationTitleToDelete(title || "New Conversation");
  };

  const handleConfirmDelete = async () => {
    if (!conversationToDelete) return;
    
    setIsDeleting(true);
    try {
      await deleteConversation(conversationToDelete);
    } catch (error) {
      console.error("Failed to delete conversation:", error);
    } finally {
      setIsDeleting(false);
      setConversationToDelete(null);
      setConversationTitleToDelete("");
    }
  };

  const handleCancelDelete = () => {
    setConversationToDelete(null);
    setConversationTitleToDelete("");
    clearDeleteError();
  };

  // Clear delete error when dialog closes
  useEffect(() => {
    if (!conversationToDelete && deleteError) {
      clearDeleteError();
    }
  }, [conversationToDelete, deleteError, clearDeleteError]);

  return (
    <>
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
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {conversations.length === 0 ? (
              <div className="px-3 py-8 text-center text-sm text-muted-foreground">
                No conversations yet.
                <br />
                Start a new chat!
              </div>
            ) : (
              conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={cn(
                    "group flex items-center gap-2 w-full rounded-lg px-2 py-2 text-sm transition-colors overflow-hidden",
                    "hover:bg-accent cursor-pointer",
                    conversation.id === currentConversationId && "bg-accent"
                  )}
                  onClick={() => handleSelectConversation(conversation.id)}
                >
                  {/* Delete button with animation */}
                  <button
                    className="shrink-0 opacity-0 scale-75 group-hover:opacity-100 group-hover:scale-100 flex items-center justify-center w-5 h-5 rounded border border-gray-300 bg-white text-gray-500 hover:border-red-500 hover:text-red-600 hover:bg-red-50 transition-all duration-200 ease-out"
                    onClick={(e) => handleDeleteClick(e, conversation.id, conversation.title)}
                    title="Delete conversation"
                    type="button"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                  {/* Title with tooltip */}
                  <div className="flex-1 min-w-0 relative">
                    <span className="block truncate">
                      {conversation.title}
                    </span>
                    {/* Custom tooltip */}
                    <div className="absolute left-0 top-full mt-1 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-opacity duration-200 z-50 whitespace-nowrap max-w-[200px] overflow-hidden text-ellipsis">
                      {conversation.title}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>

        {/* Footer */}
        <Separator />
        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground truncate" title={user?.email}>
              {user?.email}
            </span>
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

      {/* Delete Confirmation Dialog */}
      {conversationToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-background p-6 shadow-lg border">
            <div className="flex items-start gap-4">
              <div className="rounded-full bg-destructive/10 p-3">
                <AlertTriangle className="h-6 w-6 text-destructive" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold">Delete Conversation</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Are you sure you want to delete "
                  <span className="font-medium text-foreground">
                    {conversationTitleToDelete}
                  </span>
                  "? This action cannot be undone.
                </p>
              </div>
            </div>
            {deleteError && (
              <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {deleteError}
              </div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={handleCancelDelete}
                disabled={isDeleting}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="gap-2"
              >
                {isDeleting ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    Delete
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
