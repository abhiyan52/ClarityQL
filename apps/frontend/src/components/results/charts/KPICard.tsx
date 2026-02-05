import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp } from "lucide-react";

interface KPICardProps {
  value: number | string;
  label: string;
}

export function KPICard({ value, label }: KPICardProps) {
  const formattedValue =
    typeof value === "number" ? formatValue(value) : value;

  return (
    <Card className="w-full max-w-sm mx-auto">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {formatLabel(label)}
        </CardTitle>
        <TrendingUp className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-4xl font-bold tracking-tight">{formattedValue}</div>
      </CardContent>
    </Card>
  );
}

function formatValue(value: number): string {
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function formatLabel(label: string): string {
  return label.replace(/_/g, " ");
}
