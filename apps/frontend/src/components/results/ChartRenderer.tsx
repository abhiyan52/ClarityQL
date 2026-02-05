/**
 * ChartRenderer Component
 *
 * This component receives the backend-driven visualization specification
 * and renders the appropriate chart. It DOES NOT decide the chart type -
 * that decision is made entirely by the backend based on the AST.
 *
 * Responsibilities:
 * 1. Map rows/columns to chart data format
 * 2. Select the correct chart component
 * 3. Render with proper props
 */

import { BarChart, LineChart, MultiLineChart, KPICard } from "./charts";
import type { VisualizationSpec } from "@/types";
import { Card, CardContent } from "@/components/ui/card";
import { AlertCircle } from "lucide-react";

interface ChartRendererProps {
  columns: string[];
  rows: Array<Array<string | number>>;
  visualization: VisualizationSpec;
}

export function ChartRenderer({
  columns,
  rows,
  visualization,
}: ChartRendererProps) {
  const { type, x, y, series } = visualization;

  // Table type means no chart should be rendered
  if (type === "table") {
    return null;
  }

  // KPI: Single value display
  if (type === "kpi") {
    if (!y || rows.length === 0) {
      return <ChartError message="Missing data for KPI display" />;
    }

    const yIndex = columns.indexOf(y);
    if (yIndex === -1) {
      return <ChartError message={`Column "${y}" not found in results`} />;
    }

    const value = rows[0][yIndex];
    return <KPICard value={value} label={y} />;
  }

  // Bar chart: categorical dimension + metric
  if (type === "bar") {
    if (!x || !y) {
      return <ChartError message="Bar chart requires x and y fields" />;
    }

    const xIndex = columns.indexOf(x);
    const yIndex = columns.indexOf(y);

    if (xIndex === -1 || yIndex === -1) {
      return (
        <ChartError
          message={`Columns not found: x="${x}" (${xIndex}), y="${y}" (${yIndex})`}
        />
      );
    }

    const data = rows.map((row) => ({
      label: String(row[xIndex]),
      value: Number(row[yIndex]),
    }));

    return <BarChart data={data} xLabel={x} yLabel={y} />;
  }

  // Line chart: date dimension + metric
  if (type === "line") {
    if (!x || !y) {
      return <ChartError message="Line chart requires x and y fields" />;
    }

    const xIndex = columns.indexOf(x);
    const yIndex = columns.indexOf(y);

    if (xIndex === -1 || yIndex === -1) {
      return (
        <ChartError
          message={`Columns not found: x="${x}" (${xIndex}), y="${y}" (${yIndex})`}
        />
      );
    }

    const data = rows.map((row) => ({
      label: String(row[xIndex]),
      value: Number(row[yIndex]),
    }));

    return <LineChart data={data} xLabel={x} yLabel={y} />;
  }

  // Multi-line chart: date dimension + category dimension + metric
  if (type === "multi-line") {
    if (!x || !y || !series) {
      return (
        <ChartError message="Multi-line chart requires x, y, and series fields" />
      );
    }

    const xIndex = columns.indexOf(x);
    const yIndex = columns.indexOf(y);
    const seriesIndex = columns.indexOf(series);

    if (xIndex === -1 || yIndex === -1 || seriesIndex === -1) {
      return (
        <ChartError
          message={`Columns not found: x="${x}", y="${y}", series="${series}"`}
        />
      );
    }

    // Pivot data: group by x-axis, with series as separate data keys
    const pivotedData = pivotMultiLineData(rows, xIndex, yIndex, seriesIndex);

    return (
      <MultiLineChart
        data={pivotedData.data}
        xLabel={x}
        yLabel={y}
        seriesLabel={series}
        seriesKeys={pivotedData.seriesKeys}
      />
    );
  }

  // Fallback for unknown types
  return <ChartError message={`Unknown visualization type: ${type}`} />;
}

interface PivotedDataEntry {
  label: string;
  [seriesKey: string]: string | number;
}

/**
 * Pivot data for multi-line chart.
 *
 * Input: Rows like [date, series, value]
 * Output: { label: date, series1: value1, series2: value2, ... }
 */
function pivotMultiLineData(
  rows: Array<Array<string | number>>,
  xIndex: number,
  yIndex: number,
  seriesIndex: number
): { data: PivotedDataEntry[]; seriesKeys: string[] } {
  const seriesSet = new Set<string>();
  const dataMap = new Map<string, PivotedDataEntry>();

  for (const row of rows) {
    const xValue = String(row[xIndex]);
    const seriesValue = String(row[seriesIndex]);
    const yValue = Number(row[yIndex]);

    seriesSet.add(seriesValue);

    if (!dataMap.has(xValue)) {
      dataMap.set(xValue, { label: xValue });
    }

    const entry = dataMap.get(xValue)!;
    entry[seriesValue] = yValue;
  }

  const seriesKeys = Array.from(seriesSet).sort();
  const data = Array.from(dataMap.values());

  return { data, seriesKeys };
}

function ChartError({ message }: { message: string }) {
  return (
    <Card className="border-destructive/50">
      <CardContent className="flex items-center gap-2 py-4">
        <AlertCircle className="h-5 w-5 text-destructive" />
        <span className="text-sm text-destructive">{message}</span>
      </CardContent>
    </Card>
  );
}
