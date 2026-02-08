import { create } from "zustand";
import type { ChatMessage, Conversation } from "@/types";
import { generateId } from "@/lib/utils";
import { fetchConversations, fetchConversation, deleteConversation as apiDeleteConversation } from "@/api/nlq";

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  abortController: AbortController | null;
  deleteError: string | null;

  // Actions
  loadConversations: () => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  createConversation: () => void;
  setCurrentConversation: (id: string | null) => void;
  addMessage: (message: Omit<ChatMessage, "id" | "timestamp">) => string;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  deleteConversation: (id: string) => Promise<void>;
  clearDeleteError: () => void;
  setLoading: (loading: boolean) => void;
  setAbortController: (controller: AbortController | null) => void;
  cancelCurrentQuery: () => void;
  replaceConversationId: (tempId: string, realId: string) => void;

  // Helpers
  getCurrentConversation: () => Conversation | undefined;
  getMessages: () => ChatMessage[];
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  isLoading: false,
  abortController: null,
  deleteError: null,

  loadConversations: async () => {
    try {
      const data = await fetchConversations();
      // Map API response to Conversation type
      const conversations: Conversation[] = data.map((c: any) => ({
        id: c.id,
        title: c.title,
        messages: [], // Fetched on selection
        createdAt: new Date(c.created_at),
        updatedAt: new Date(c.updated_at),
        status: c.status,
      }));
      set({ conversations });
    } catch (error) {
      console.error("Failed to load conversations:", error);
    }
  },

  selectConversation: async (id: string) => {
    set({ currentConversationId: id, isLoading: true });
    try {
      const data = await fetchConversation(id);

      const messages: ChatMessage[] = data.messages.map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: new Date(m.created_at),
        // Restore meta fields if needed
        response: m.meta?.response,
        taskId: m.meta?.task_id,
      }));

      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === id ? { ...c, messages: messages } : c
        ),
        isLoading: false,
      }));
    } catch (error) {
      console.error("Failed to load conversation details:", error);
      set({ isLoading: false });
    }
  },

  createConversation: () => {
    // Just clear current ID to show empty state
    // Actual creation happens on first message
    set({ currentConversationId: null });
  },

  setCurrentConversation: (id) => {
    set({ currentConversationId: id });
  },

  addMessage: (message) => {
    // If no conversation ID, we're in "New Chat" mode
    // We don't add message to store yet? 
    // Wait, UI needs to show it.
    // If currentConversationId is null, we should create a temporary local one?
    // OR, we assume submitQuery checks for null ID.

    // BUT the ChatWindow needs to display the message immediately.
    // So we need a temporary conversation if ID is null?
    // Or we handle it by creating a conversation ID locally?
    // Backend expects UUID.
    // Better approach:
    // If ID is null, we create a placeholder conversation in the store with a temp ID,
    // THEN when backend returns real ID, we swap it? That's complex.

    // Simpler: If ID is null, ChatWindow calls addMessage.
    // We need a place to store messages for "New Chat" before it's persisted.
    // Let's use a special "new" ID or just allow null currentID but store messages?
    // No, store structure relies on conversations array.

    // Let's create a temporary optimistic conversation.
    let conversationId = get().currentConversationId;

    if (!conversationId) {
      // We don't have an ID yet. We can't easily generate a UUID that matches backend.
      // So we'll use a temp one, and the ChatWindow must update it when submitQuery returns.
      // Actually, ChatWindow calls createConversation() first if null.
      // Let's make createConversation return a temp ID.
      // isNew = true;
      // We'll treat this as a UI-only concern until first message sent?
      // Let's revert to using generateId() for temp ID, 
      // and we will update it later.
    }

    const id = generateId();
    const newMessage: ChatMessage = {
      ...message,
      id,
      timestamp: new Date(),
    };

    set((state) => {
      // If no current conversation, create one temporarily
      if (!state.currentConversationId) {
        const tempId = "temp-" + generateId();
        const newConv: Conversation = {
          id: tempId,
          title: "New Conversation",
          messages: [newMessage],
          createdAt: new Date(),
          updatedAt: new Date(),
        };
        return {
          conversations: [newConv, ...state.conversations],
          currentConversationId: tempId
        };
      }

      const conversations = state.conversations.map((conv) => {
        if (conv.id === state.currentConversationId) {
          return {
            ...conv,
            messages: [...conv.messages, newMessage],
            updatedAt: new Date(),
          };
        }
        return conv;
      });

      return { conversations, currentConversationId: state.currentConversationId };
    });

    return id;
  },

  updateMessage: (id, updates) => {
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id === state.currentConversationId) {
          return {
            ...conv,
            messages: conv.messages.map((msg) =>
              msg.id === id ? { ...msg, ...updates } : msg
            ),
            updatedAt: new Date(),
          };
        }
        return conv;
      }),
    }));
  },

  // New action to replace temp ID with real ID
  replaceConversationId: (tempId: string, realId: string) => {
    set((state) => ({
      currentConversationId: realId,
      conversations: state.conversations.map(c =>
        c.id === tempId ? { ...c, id: realId } : c
      )
    }));
  },

  deleteConversation: async (id: string) => {
    try {
      await apiDeleteConversation(id);
      set((state) => {
        const conversations = state.conversations.filter((c) => c.id !== id);
        const currentConversationId =
          state.currentConversationId === id
            ? conversations[0]?.id || null
            : state.currentConversationId;

        return { conversations, currentConversationId, deleteError: null };
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to delete conversation";
      console.error("Failed to delete conversation", error);
      set({ deleteError: errorMessage });
      throw error;
    }
  },

  clearDeleteError: () => {
    set({ deleteError: null });
  },

  setLoading: (loading) => {
    set({ isLoading: loading });
  },

  setAbortController: (controller) => {
    set({ abortController: controller });
  },

  cancelCurrentQuery: () => {
    const state = get();
    if (state.abortController) {
      state.abortController.abort();
      set({ abortController: null, isLoading: false });
    }
  },

  getCurrentConversation: () => {
    const state = get();
    return state.conversations.find(
      (c) => c.id === state.currentConversationId
    );
  },

  getMessages: () => {
    const conversation = get().getCurrentConversation();
    return conversation?.messages || [];
  },
}));
