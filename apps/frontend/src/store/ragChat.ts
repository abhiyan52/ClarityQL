import { create } from 'zustand';
import {
    fetchConversations,
    fetchConversation,
    deleteConversation as deleteConversationApi,
    type ChunkResult
} from '@/api/rag';

export interface RAGMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    isLoading?: boolean;
    progressPercentage?: number;
    progressMessage?: string;
    taskId?: string;
    chunks?: ChunkResult[];
    error?: string;
}

export interface RAGConversation {
    id: string;
    title: string;
    created_at: string;
    updated_at: string;
    status: string;
}

interface RAGChatState {
    conversations: RAGConversation[];
    currentConversationId: string | null;
    messages: RAGMessage[];
    isLoading: boolean;
    isListLoading: boolean;
    abortController: AbortController | null;
    selectedDocumentIds: string[];

    // Actions
    fetchConversations: () => Promise<void>;
    selectConversation: (id: string | null) => Promise<void>;
    createConversation: () => void;
    deleteConversation: (id: string) => Promise<void>;
    setSelectedDocumentIds: (ids: string[]) => void;
    toggleDocumentSelection: (id: string) => void;
    addMessage: (message: Omit<RAGMessage, 'id' | 'timestamp'>) => string;
    updateMessage: (id: string, updates: Partial<RAGMessage>) => void;
    setLoading: (loading: boolean) => void;
    setAbortController: (controller: AbortController | null) => void;
    cancelCurrentQuery: () => void;
    clearMessages: () => void;
    getMessages: () => RAGMessage[];
}

export const useRAGChatStore = create<RAGChatState>((set, get) => ({
    conversations: [],
    currentConversationId: null,
    messages: [],
    isLoading: false,
    isListLoading: false,
    abortController: null,
    selectedDocumentIds: [],

    fetchConversations: async () => {
        set({ isListLoading: true });
        try {
            const conversations = await fetchConversations();
            set({ conversations, isListLoading: false });
        } catch (error) {
            console.error('Failed to fetch RAG conversations:', error);
            set({ isListLoading: false });
        }
    },

    selectConversation: async (id) => {
        if (!id) {
            set({ currentConversationId: null, messages: [], selectedDocumentIds: [] });
            return;
        }

        set({ currentConversationId: id, isLoading: true });
        try {
            const data = await fetchConversation(id);
            const formattedMessages: RAGMessage[] = data.messages.map((m: any) => ({
                id: m.id,
                role: m.role,
                content: m.content,
                timestamp: new Date(m.created_at),
                chunks: m.meta?.chunks || [],
                taskId: m.meta?.task_id,
            }));

            // Restore selected documents from metadata
            let selectedIds: string[] = [];
            // Look for the most recent message with selected_document_ids
            for (let i = data.messages.length - 1; i >= 0; i--) {
                const msg = data.messages[i];
                if (msg.meta?.selected_document_ids) {
                    selectedIds = msg.meta.selected_document_ids;
                    break;
                }
            }

            // Fallback: If no meta, try to collect from chunks/docs of assistant messages
            if (selectedIds.length === 0) {
                const allDocIds = new Set<string>();
                data.messages.forEach((m: any) => {
                    if (m.role === 'assistant' && m.meta?.documents) {
                        m.meta.documents.forEach((d: any) => allDocIds.add(String(d.id)));
                    }
                });
                selectedIds = Array.from(allDocIds);
            }

            set({
                messages: formattedMessages,
                isLoading: false,
                selectedDocumentIds: selectedIds
            });
        } catch (error) {
            console.error('Failed to fetch RAG conversation:', error);
            set({ isLoading: false });
        }
    },

    createConversation: () => {
        const tempId = `temp-${Date.now()}`;
        set({
            currentConversationId: tempId,
            messages: [],
            selectedDocumentIds: [],
        });
    },

    deleteConversation: async (id) => {
        const isTemp = id.startsWith('temp-');
        try {
            if (!isTemp) {
                await deleteConversationApi(id);
            }

            const { conversations, currentConversationId } = get();

            // If we deleted the current conversation, clear it
            if (currentConversationId === id) {
                set({
                    currentConversationId: null,
                    messages: [],
                    selectedDocumentIds: [],
                });
            }

            // Update list
            set({
                conversations: conversations.filter((c) => c.id !== id),
            });

            // If it wasn't temp, refetch to be absolutely sure
            if (!isTemp) {
                await get().fetchConversations();
            }
        } catch (error) {
            console.error('Failed to delete RAG conversation:', error);
            throw error;
        }
    },

    setSelectedDocumentIds: (ids) => set({ selectedDocumentIds: ids }),

    toggleDocumentSelection: (id) => {
        set((state) => {
            const isSelected = state.selectedDocumentIds.includes(id);
            if (isSelected) {
                return {
                    selectedDocumentIds: state.selectedDocumentIds.filter((docId) => docId !== id),
                };
            } else {
                return {
                    selectedDocumentIds: [...state.selectedDocumentIds, id],
                };
            }
        });
    },

    addMessage: (message) => {
        const id = Date.now().toString();
        const newMessage: RAGMessage = {
            ...message,
            id,
            timestamp: new Date(),
        };
        set((state) => ({
            messages: [...state.messages, newMessage],
        }));
        return id;
    },

    updateMessage: (id, updates) => {
        set((state) => ({
            messages: state.messages.map((msg) =>
                msg.id === id ? { ...msg, ...updates } : msg
            ),
        }));
    },

    setLoading: (loading) => set({ isLoading: loading }),

    setAbortController: (controller) => set({ abortController: controller }),

    cancelCurrentQuery: () => {
        const { abortController } = get();
        if (abortController) {
            abortController.abort();
            set({ abortController: null, isLoading: false });
        }
    },

    clearMessages: () => set({ messages: [] }),

    getMessages: () => get().messages,
}));
