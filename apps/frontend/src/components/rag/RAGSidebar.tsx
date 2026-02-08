import { useEffect, useState } from "react";
import { Trash2, Plus, Clock, AlertTriangle, PanelLeftClose, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useRAGChatStore } from "@/store/ragChat";
import { useNavigate } from "react-router-dom";

interface RAGSidebarProps {
  onClose?: () => void;
}

export function RAGSidebar({ onClose }: RAGSidebarProps) {
    const navigate = useNavigate();
    const {
        conversations,
        currentConversationId,
        fetchConversations,
        selectConversation,
        deleteConversation,
        createConversation,
    } = useRAGChatStore();

    // State for delete confirmation dialog
    const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);
    const [conversationTitleToDelete, setConversationTitleToDelete] = useState<string>("");
    const [isDeleting, setIsDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    useEffect(() => {
        fetchConversations();
    }, [fetchConversations]);

    const handleDeleteClick = (e: React.MouseEvent, id: string, title: string) => {
        e.stopPropagation();
        setConversationToDelete(id);
        setConversationTitleToDelete(title || "New Document Chat");
        setDeleteError(null);
    };

    const handleConfirmDelete = async () => {
        if (!conversationToDelete) return;
        
        setIsDeleting(true);
        setDeleteError(null);
        try {
            await deleteConversation(conversationToDelete);
            setConversationToDelete(null);
            setConversationTitleToDelete("");
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : "Failed to delete conversation";
            setDeleteError(errorMessage);
        } finally {
            setIsDeleting(false);
        }
    };

    const handleCancelDelete = () => {
        setConversationToDelete(null);
        setConversationTitleToDelete("");
        setDeleteError(null);
    };

    return (
        <div className="flex h-full flex-col bg-muted/10">
            {/* Header */}
            <div className="flex items-center justify-between p-4">
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => navigate("/")}
                        className="h-8 w-8 shrink-0"
                        title="Back to main chat"
                    >
                        <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <h2 className="text-sm font-semibold flex items-center gap-2">
                        <Clock className="h-4 w-4" />
                        Chat History
                    </h2>
                </div>
                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => createConversation()}
                        title="New Chat"
                    >
                        <Plus className="h-4 w-4" />
                    </Button>
                    {onClose && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={onClose}
                            title="Hide chat history"
                        >
                            <PanelLeftClose className="h-4 w-4" />
                        </Button>
                    )}
                </div>
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
                                    "group flex items-center gap-2 w-full rounded-lg px-2 py-2 text-sm transition-colors overflow-hidden",
                                    "hover:bg-accent cursor-pointer",
                                    conversation.id === currentConversationId && "bg-accent"
                                )}
                                onClick={() => selectConversation(conversation.id)}
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
                        ))}
                    </div>
                )}
            </ScrollArea>

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
        </div>
    );
}
