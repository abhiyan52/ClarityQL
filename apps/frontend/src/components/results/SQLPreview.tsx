import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface SQLPreviewProps {
  sql: string;
}

export function SQLPreview({ sql }: SQLPreviewProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    // Copy the original SQL without HTML formatting
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = sql;
    const plainText = tempDiv.textContent || tempDiv.innerText || sql;
    await navigator.clipboard.writeText(plainText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Generated SQL</CardTitle>
        <Button variant="ghost" size="sm" onClick={handleCopy}>
          {copied ? (
            <Check className="h-4 w-4 text-green-500" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
        </Button>
      </CardHeader>
      <CardContent>
        <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-sm font-mono">
          <code className="text-foreground whitespace-pre-wrap break-words">
            {sql}
          </code>
        </pre>
      </CardContent>
    </Card>
  );
}
