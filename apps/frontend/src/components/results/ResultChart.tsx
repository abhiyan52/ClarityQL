import { useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BarChart3, LineChartIcon, PieChartIcon, AreaChartIcon } from "lucide-react";
import type { ChartType } from "@/types";

interface ResultChartProps {
  columns: string[];
  rows: Record<string, unknown>[];
}

const CHART_COLORS = [
  "hsl(220, 70%, 50%)",
  "hsl(160, 60%, 45%)",
  "hsl(30, 80%, 55%)",
  "hsl(280, 65%, 60%)",
  "hsl(340, 75%, 55%)",
  "hsl(200, 70%, 50%)",
  "hsl(100, 60%, 45%)",
  "hsl(50, 80%, 50%)",
];

export function ResultChart({ columns, rows }: ResultChartProps) {
  const [chartType, setChartType] = useState<ChartType>("bar");

  // Infer chart configuration from data
  const numericColumns = columns.filter((col) =>
    rows.some((row) => typeof row[col] === "number")
  );
  const categoryColumns = columns.filter((col) =>
    rows.some((row) => typeof row[col] === "string")
  );

  const xAxis = categoryColumns[0] || columns[0];
  const yAxis = numericColumns[0] || columns[1];

  // Prepare data for charts
  const chartData = rows.map((row) => ({
    name: String(row[xAxis] || ""),
    value: Number(row[yAxis] || 0),
    ...row,
  }));

  const chartTypes: { type: ChartType; icon: React.ReactNode; label: string }[] = [
    { type: "bar", icon: <BarChart3 className="h-4 w-4" />, label: "Bar" },
    { type: "line", icon: <LineChartIcon className="h-4 w-4" />, label: "Line" },
    { type: "area", icon: <AreaChartIcon className="h-4 w-4" />, label: "Area" },
    { type: "pie", icon: <PieChartIcon className="h-4 w-4" />, label: "Pie" },
  ];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">
          {yAxis.replace(/_/g, " ")} by {xAxis.replace(/_/g, " ")}
        </CardTitle>
        <div className="flex gap-1">
          {chartTypes.map(({ type, icon, label }) => (
            <Button
              key={type}
              variant={chartType === type ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setChartType(type)}
              title={label}
            >
              {icon}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            {chartType === "bar" ? (
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => formatValue(value)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                  }}
                  formatter={(value: number) => [formatValue(value), yAxis]}
                />
                <Legend />
                <Bar dataKey="value" name={yAxis} fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
              </BarChart>
            ) : chartType === "line" ? (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => formatValue(value)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                  }}
                  formatter={(value: number) => [formatValue(value), yAxis]}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="value"
                  name={yAxis}
                  stroke={CHART_COLORS[0]}
                  strokeWidth={2}
                  dot={{ fill: CHART_COLORS[0] }}
                />
              </LineChart>
            ) : chartType === "area" ? (
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => formatValue(value)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                  }}
                  formatter={(value: number) => [formatValue(value), yAxis]}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="value"
                  name={yAxis}
                  stroke={CHART_COLORS[0]}
                  fill={CHART_COLORS[0]}
                  fillOpacity={0.3}
                />
              </AreaChart>
            ) : (
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }) =>
                    `${name} (${(percent * 100).toFixed(0)}%)`
                  }
                  labelLine={false}
                >
                  {chartData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={CHART_COLORS[index % CHART_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                  }}
                  formatter={(value: number) => [formatValue(value), yAxis]}
                />
                <Legend />
              </PieChart>
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function formatValue(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString();
}
