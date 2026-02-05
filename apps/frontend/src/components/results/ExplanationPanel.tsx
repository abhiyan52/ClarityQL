import {
  Calculator,
  Grid3X3,
  Filter,
  ArrowUpDown,
  Database,
  Hash,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { QueryAST, QueryExplanation } from "@/types";

interface ExplanationPanelProps {
  ast?: QueryAST;
  explanation?: QueryExplanation;
}

export function ExplanationPanel({ ast, explanation }: ExplanationPanelProps) {
  if (!ast && !explanation) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No explanation available
        </CardContent>
      </Card>
    );
  }

  const sections = [
    {
      icon: Calculator,
      title: "Aggregations",
      items: explanation?.aggregates || ast?.metrics.map(
        (m) => `${m.function.toUpperCase()}(${m.field})${m.alias ? ` as ${m.alias}` : ""}`
      ) || [],
      color: "text-blue-500",
    },
    {
      icon: Grid3X3,
      title: "Grouped By",
      items: explanation?.group_by || ast?.dimensions.map((d) => d.field) || [],
      color: "text-green-500",
    },
    {
      icon: Filter,
      title: "Filters",
      items: explanation?.filters || ast?.filters.map(
        (f) => `${f.field} ${f.operator} ${JSON.stringify(f.value)}`
      ) || [],
      color: "text-orange-500",
    },
    {
      icon: ArrowUpDown,
      title: "Ordered By",
      items: explanation?.order_by || ast?.order_by.map(
        (o) => `${o.field} ${o.direction.toUpperCase()}`
      ) || [],
      color: "text-purple-500",
    },
    {
      icon: Database,
      title: "Source Tables",
      items: explanation?.source_tables || [],
      color: "text-cyan-500",
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Query Breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sections.map((section) => (
            section.items.length > 0 && (
              <div key={section.title} className="space-y-2">
                <div className="flex items-center gap-2">
                  <section.icon className={`h-4 w-4 ${section.color}`} />
                  <span className="text-sm font-medium">{section.title}</span>
                </div>
                <ul className="space-y-1 pl-6">
                  {section.items.map((item, i) => (
                    <li key={i} className="text-sm text-muted-foreground">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )
          ))}

          {/* Limit */}
          {(explanation?.limit || ast?.limit) && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Hash className="h-4 w-4 text-pink-500" />
                <span className="text-sm font-medium">Limit</span>
              </div>
              <p className="pl-6 text-sm text-muted-foreground">
                {explanation?.limit || ast?.limit} rows
              </p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
