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
  rows: Array<Array<string | number>>;
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

/**
 * Strictly checks if a value is a real number (not a date, UUID, etc.).
 * Uses Number() which requires the ENTIRE string to be numeric,
 * unlike parseFloat() which stops at the first non-numeric char
 * (e.g. parseFloat("2025-02-04") = 2025 — WRONG).
 */
function isStrictlyNumeric(value: unknown): boolean {
  if (typeof value === "number") return !isNaN(value) && isFinite(value);
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed === "") return false;
    const num = Number(trimmed);
    return !isNaN(num) && isFinite(num);
  }
  return false;
}

/**
 * Determine if a column is predominantly numeric by sampling rows.
 * A column is numeric if the majority of its non-empty values are numbers.
 */
function isNumericColumn(rows: Array<Array<string | number>>, colIdx: number): boolean {
  let numericCount = 0;
  let totalNonEmpty = 0;
  for (const row of rows) {
    const val = row[colIdx];
    if (val === null || val === undefined || val === "") continue;
    totalNonEmpty++;
    if (isStrictlyNumeric(val)) numericCount++;
  }
  // At least 80% of non-empty values must be numeric
  return totalNonEmpty > 0 && numericCount / totalNonEmpty >= 0.8;
}

export function ResultChart({ columns, rows }: ResultChartProps) {
  const [chartType, setChartType] = useState<ChartType>("bar");

  // Early return if no valid data
  if (!columns.length || !rows.length) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <p className="text-muted-foreground">No data available for charting</p>
        </CardContent>
      </Card>
    );
  }

  // Classify columns as numeric or category using strict detection
  const numericColIndices: number[] = [];
  const categoryColIndices: number[] = [];

  columns.forEach((_, idx) => {
    if (isNumericColumn(rows, idx)) {
      numericColIndices.push(idx);
    } else {
      categoryColIndices.push(idx);
    }
  });

  const numericColumns = numericColIndices.map((i) => columns[i]);
  const categoryColumns = categoryColIndices.map((i) => columns[i]);

  // Early return if no numeric columns for Y-axis
  if (numericColumns.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <p className="text-muted-foreground">
            No numeric data available for charting. Try a query with aggregations
            like &quot;total revenue by region&quot; or &quot;count of orders by month&quot;.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Pick axes: category for X, numeric for Y
  const xAxis = categoryColumns[0] || columns[0];
  const yAxisColumns = numericColumns.length > 0 ? numericColumns : [columns[1] || columns[0]];
  const yAxis = yAxisColumns[0];

  // Convert rows to objects for recharts
  const chartData = rows.map((row) => {
    const obj: Record<string, unknown> = {};
    columns.forEach((col, idx) => {
      const value = row[idx];
      obj[col] = isStrictlyNumeric(value) ? Number(value) : value;
    });
    return obj;
  });

  // Build formatted data with name/value keys
  const formattedData = chartData.map((row) => {
    let name: string;
    if (categoryColumns.length > 1) {
      name = categoryColumns.map((col) => String(row[col] ?? "")).join(" - ");
    } else {
      name = String(row[xAxis] ?? "");
    }

    const entry: Record<string, unknown> = {
      name,
      ...row,
    };

    // Add each numeric column as a separate series for multi-series charts
    yAxisColumns.forEach((col, i) => {
      const key = i === 0 ? "value" : col;
      entry[key] = Number(row[col] ?? 0) || 0;
    });

    return entry;
  });

  // For pie chart, we need to aggregate if there are multiple numeric columns
  // Use the first numeric column only
  const pieData = formattedData.map((row) => ({
    name: row.name as string,
    value: Number(row.value ?? 0),
  }));

  // Determine chart options
  const showPieOption = formattedData.length <= 8;
  const isLargeDataset = formattedData.length > 15;
  const isTimeSeries = categoryColumns.some(
    (c) => c.toLowerCase().includes("date") || c.toLowerCase().includes("month") || c.toLowerCase().includes("year")
  );

  // Auto-select best chart type for first render
  let effectiveChartType = chartType;
  if (chartType === "pie" && !showPieOption) {
    effectiveChartType = isTimeSeries ? "line" : "bar";
  }

  // Default to line for time series on initial render
  const [hasUserSwitched, setHasUserSwitched] = useState(false);
  if (!hasUserSwitched && isTimeSeries && isLargeDataset && chartType === "bar") {
    effectiveChartType = "line";
  }

  const chartTypes: { type: ChartType; icon: React.ReactNode; label: string }[] = [
    { type: "bar", icon: <BarChart3 className="h-4 w-4" />, label: "Bar" },
    { type: "line", icon: <LineChartIcon className="h-4 w-4" />, label: "Line" },
    { type: "area", icon: <AreaChartIcon className="h-4 w-4" />, label: "Area" },
    ...(showPieOption
      ? [{ type: "pie" as ChartType, icon: <PieChartIcon className="h-4 w-4" />, label: "Pie" }]
      : []),
  ];

  // X-axis label management
  const xAxisInterval =
    formattedData.length > 20
      ? Math.floor(formattedData.length / 8)
      : formattedData.length > 10
        ? Math.floor(formattedData.length / 10)
        : 0;

  const needsAngle = formattedData.length > 6;

  // Dynamic title
  const xLabel =
    categoryColumns.length > 1
      ? categoryColumns.map((c) => c.replace(/_/g, " ")).join(" & ")
      : xAxis.replace(/_/g, " ");
  const yLabel = yAxis.replace(/_/g, " ");

  // Shared axis props
  const xAxisProps = {
    dataKey: "name" as const,
    tick: { fontSize: 11 },
    tickLine: false as const,
    axisLine: false as const,
    angle: needsAngle ? -45 : 0,
    textAnchor: (needsAngle ? "end" : "middle") as string,
    height: needsAngle ? 80 : 30,
    interval: xAxisInterval,
  };

  const yAxisProps = {
    tick: { fontSize: 12 },
    tickLine: false as const,
    axisLine: false as const,
    tickFormatter: (value: number) => formatValue(value),
  };

  const tooltipStyle = {
    backgroundColor: "hsl(var(--popover))",
    border: "1px solid hsl(var(--border))",
    borderRadius: "var(--radius)",
  };

  const handleChartSwitch = (type: ChartType) => {
    setHasUserSwitched(true);
    setChartType(type);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">
          {yLabel} by {xLabel}
        </CardTitle>
        <div className="flex gap-1">
          {chartTypes.map(({ type, icon, label }) => (
            <Button
              key={type}
              variant={
                (hasUserSwitched ? chartType : effectiveChartType) === type
                  ? "secondary"
                  : "ghost"
              }
              size="sm"
              onClick={() => handleChartSwitch(type)}
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
            {effectiveChartType === "bar" ? (
              <BarChart data={formattedData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis {...xAxisProps} />
                <YAxis {...yAxisProps} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number) => [formatValue(value), yAxis]}
                />
                <Legend />
                <Bar
                  dataKey="value"
                  name={yAxis}
                  fill={CHART_COLORS[0]}
                  radius={[4, 4, 0, 0]}
                />
                {/* Additional numeric columns as extra series with different colors */}
                {yAxisColumns.slice(1).map((col, idx) => (
                  <Bar
                    key={col}
                    dataKey={col}
                    name={col.replace(/_/g, " ")}
                    fill={CHART_COLORS[(idx + 1) % CHART_COLORS.length]}
                    radius={[4, 4, 0, 0]}
                  />
                ))}
              </BarChart>
            ) : effectiveChartType === "line" ? (
              <LineChart data={formattedData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis {...xAxisProps} />
                <YAxis {...yAxisProps} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number) => [formatValue(value), yAxis]}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="value"
                  name={yAxis}
                  stroke={CHART_COLORS[0]}
                  strokeWidth={2}
                  dot={formattedData.length <= 20}
                />
                {/* Additional numeric columns as extra lines with different colors */}
                {yAxisColumns.slice(1).map((col, idx) => (
                  <Line
                    key={col}
                    type="monotone"
                    dataKey={col}
                    name={col.replace(/_/g, " ")}
                    stroke={CHART_COLORS[(idx + 1) % CHART_COLORS.length]}
                    strokeWidth={2}
                    dot={formattedData.length <= 20}
                  />
                ))}
              </LineChart>
            ) : effectiveChartType === "area" ? (
              <AreaChart data={formattedData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis {...xAxisProps} />
                <YAxis {...yAxisProps} />
                <Tooltip
                  contentStyle={tooltipStyle}
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
                {/* Additional numeric columns as extra areas with different colors */}
                {yAxisColumns.slice(1).map((col, idx) => (
                  <Area
                    key={col}
                    type="monotone"
                    dataKey={col}
                    name={col.replace(/_/g, " ")}
                    stroke={CHART_COLORS[(idx + 1) % CHART_COLORS.length]}
                    fill={CHART_COLORS[(idx + 1) % CHART_COLORS.length]}
                    fillOpacity={0.3}
                  />
                ))}
              </AreaChart>
            ) : (
              <PieChart>
                <Pie
                  data={pieData}
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
                  {pieData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={CHART_COLORS[index % CHART_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={tooltipStyle}
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
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString();
}
