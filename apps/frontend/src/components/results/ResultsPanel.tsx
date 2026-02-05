import { useState } from "react";
import { Table, BarChart3, Code, Info } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "./DataTable";
import { ResultChart } from "./ResultChart";
import { SQLPreview } from "./SQLPreview";
import { ExplanationPanel } from "./ExplanationPanel";
import type { NLQResponse } from "@/types";

interface ResultsPanelProps {
  response: NLQResponse;
}

export function ResultsPanel({ response }: ResultsPanelProps) {
  const [activeTab, setActiveTab] = useState("table");

  if (!response.success) {
    return (
      <Card className="mt-4 border-destructive/50 bg-destructive/5">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-destructive">
            Error
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">{response.error}</p>
        </CardContent>
      </Card>
    );
  }

  const hasResults = response.results && response.results.rows.length > 0;
  const canChart =
    hasResults &&
    response.results!.columns.length >= 2 &&
    response.results!.rows.length > 1;

  return (
    <div className="mt-4 space-y-4">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="table" className="gap-2">
            <Table className="h-4 w-4" />
            Table
          </TabsTrigger>
          {canChart && (
            <TabsTrigger value="chart" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              Chart
            </TabsTrigger>
          )}
          <TabsTrigger value="sql" className="gap-2">
            <Code className="h-4 w-4" />
            SQL
          </TabsTrigger>
          <TabsTrigger value="explain" className="gap-2">
            <Info className="h-4 w-4" />
            Explain
          </TabsTrigger>
        </TabsList>

        <TabsContent value="table" className="mt-4">
          {hasResults ? (
            <DataTable
              columns={response.results!.columns}
              rows={response.results!.rows}
            />
          ) : (
            <EmptyResults />
          )}
        </TabsContent>

        {canChart && (
          <TabsContent value="chart" className="mt-4">
            <ResultChart
              columns={response.results!.columns}
              rows={response.results!.rows}
            />
          </TabsContent>
        )}

        <TabsContent value="sql" className="mt-4">
          <SQLPreview sql={response.sql || "-- No SQL generated"} />
        </TabsContent>

        <TabsContent value="explain" className="mt-4">
          <ExplanationPanel
            ast={response.ast}
            explanation={response.explanation}
          />
        </TabsContent>
      </Tabs>

      {/* Row count */}
      {hasResults && (
        <p className="text-xs text-muted-foreground">
          Showing {response.results!.rows.length} of {response.results!.rowCount} rows
        </p>
      )}
    </div>
  );
}

function EmptyResults() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center py-8">
        <Table className="h-8 w-8 text-muted-foreground" />
        <p className="mt-2 text-sm text-muted-foreground">No results found</p>
      </CardContent>
    </Card>
  );
}
