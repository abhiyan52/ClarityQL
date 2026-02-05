import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, formatNumber, formatCurrency } from "@/lib/utils";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
}

export function DataTable({ columns, rows }: DataTableProps) {
  const formatValue = (value: unknown, column: string): string => {
    if (value === null || value === undefined) {
      return "—";
    }

    if (typeof value === "number") {
      // Check if it's a currency-like column
      const isCurrency =
        column.toLowerCase().includes("revenue") ||
        column.toLowerCase().includes("price") ||
        column.toLowerCase().includes("amount") ||
        column.toLowerCase().includes("cost");

      if (isCurrency) {
        return formatCurrency(value);
      }

      return formatNumber(value);
    }

    if (value instanceof Date) {
      return value.toLocaleDateString();
    }

    return String(value);
  };

  return (
    <Card className="overflow-hidden">
      <ScrollArea className="max-h-96">
        <table className="w-full">
          <thead className="sticky top-0 bg-muted">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground"
                >
                  {column.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((row, i) => (
              <tr
                key={i}
                className={cn(
                  "transition-colors hover:bg-muted/50",
                  i % 2 === 0 ? "bg-background" : "bg-muted/20"
                )}
              >
                {columns.map((column) => (
                  <td key={column} className="whitespace-nowrap px-4 py-3 text-sm">
                    {formatValue(row[column], column)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollArea>
    </Card>
  );
}
