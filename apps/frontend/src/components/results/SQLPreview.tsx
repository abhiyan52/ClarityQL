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
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Simple SQL syntax highlighting
  const highlightSQL = (sql: string) => {
    const keywords = [
      "SELECT",
      "FROM",
      "WHERE",
      "AND",
      "OR",
      "ORDER BY",
      "GROUP BY",
      "HAVING",
      "LIMIT",
      "OFFSET",
      "JOIN",
      "LEFT",
      "RIGHT",
      "INNER",
      "OUTER",
      "ON",
      "AS",
      "DESC",
      "ASC",
      "DISTINCT",
      "COUNT",
      "SUM",
      "AVG",
      "MIN",
      "MAX",
      "BETWEEN",
      "IN",
      "LIKE",
      "IS",
      "NULL",
      "NOT",
    ];

    let highlighted = sql;

    // Highlight keywords
    keywords.forEach((keyword) => {
      const regex = new RegExp(`\\b${keyword}\\b`, "gi");
      highlighted = highlighted.replace(
        regex,
        `<span class="text-blue-500 font-medium">${keyword}</span>`
      );
    });

    // Highlight strings
    highlighted = highlighted.replace(
      /'([^']*)'/g,
      `<span class="text-green-500">'$1'</span>`
    );

    // Highlight numbers
    highlighted = highlighted.replace(
      /\b(\d+\.?\d*)\b/g,
      `<span class="text-orange-500">$1</span>`
    );

    return highlighted;
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
        <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-sm">
          <code
            dangerouslySetInnerHTML={{ __html: highlightSQL(sql) }}
          />
        </pre>
      </CardContent>
    </Card>
  );
}
