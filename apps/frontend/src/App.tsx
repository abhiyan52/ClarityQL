import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PanelLeft, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/chat/Sidebar";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { cn } from "@/lib/utils";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [darkMode, setDarkMode] = useState(false);

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle("dark");
  };

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <div className={cn("flex h-screen bg-background", darkMode && "dark")}>
          {/* Sidebar */}
          <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

          {/* Main content */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Header */}
            <header className="flex h-14 items-center justify-between border-b px-4">
              <div className="flex items-center gap-2">
                {!sidebarOpen && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSidebarOpen(true)}
                  >
                    <PanelLeft className="h-4 w-4" />
                  </Button>
                )}
                <h1 className="text-lg font-semibold">ClarityQL</h1>
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                  Beta
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" onClick={toggleDarkMode}>
                  {darkMode ? (
                    <Sun className="h-4 w-4" />
                  ) : (
                    <Moon className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </header>

            {/* Chat window */}
            <main className="flex-1 overflow-hidden">
              <ChatWindow />
            </main>
          </div>
        </div>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
