import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { ChatMessage, Conversation } from "@/types";
import { generateId } from "@/lib/utils";

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;

  // Actions
  createConversation: () => string;
  setCurrentConversation: (id: string) => void;
  addMessage: (message: Omit<ChatMessage, "id" | "timestamp">) => string;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  deleteConversation: (id: string) => void;
  clearConversations: () => void;
  setLoading: (loading: boolean) => void;

  // Selectors
  getCurrentConversation: () => Conversation | undefined;
  getMessages: () => ChatMessage[];
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      currentConversationId: null,
      isLoading: false,

      createConversation: () => {
        const id = generateId();
        const conversation: Conversation = {
          id,
          title: "New Conversation",
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
        };

        set((state) => ({
          conversations: [conversation, ...state.conversations],
          currentConversationId: id,
        }));

        return id;
      },

      setCurrentConversation: (id) => {
        set({ currentConversationId: id });
      },

      addMessage: (message) => {
        const id = generateId();
        const newMessage: ChatMessage = {
          ...message,
          id,
          timestamp: new Date(),
        };

        set((state) => {
          const conversations = state.conversations.map((conv) => {
            if (conv.id === state.currentConversationId) {
              // Update title from first user message
              const title =
                conv.messages.length === 0 && message.role === "user"
                  ? message.content.slice(0, 50) + (message.content.length > 50 ? "..." : "")
                  : conv.title;

              return {
                ...conv,
                title,
                messages: [...conv.messages, newMessage],
                updatedAt: new Date(),
              };
            }
            return conv;
          });

          return { conversations };
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

      deleteConversation: (id) => {
        set((state) => {
          const conversations = state.conversations.filter((c) => c.id !== id);
          const currentConversationId =
            state.currentConversationId === id
              ? conversations[0]?.id || null
              : state.currentConversationId;

          return { conversations, currentConversationId };
        });
      },

      clearConversations: () => {
        set({ conversations: [], currentConversationId: null });
      },

      setLoading: (loading) => {
        set({ isLoading: loading });
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
    }),
    {
      name: "clarityql-chat",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        conversations: state.conversations,
        currentConversationId: state.currentConversationId,
      }),
    }
  )
);
