#!/usr/bin/env python3
"""
ClarityQL Interactive NLQ Chat

A beautiful command-line interface to test natural language queries
against your analytics database.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich import box
from sqlalchemy import MetaData, Table as SATable, Column, Integer, String, Date, Numeric, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID

from packages.core.schema_registry.registry import get_default_registry
from packages.core.safety.validator import ASTValidator, ASTValidationError
from packages.core.sql_ast.join_resolver import JoinResolver, JoinResolutionError
from packages.core.sql_ast.compiler import SQLCompiler
from packages.llm.parser import NLQParser, NLQParseError
from packages.db.base import get_engine


console = Console()


# -----------------------------
# SQLAlchemy Table Setup
# -----------------------------


def create_sqlalchemy_tables():
    """Create SQLAlchemy Table objects for the compiler."""
    metadata = MetaData()

    orders = SATable(
        "orders",
        metadata,
        Column("order_id", UUID(as_uuid=True), primary_key=True),
        Column("customer_id", UUID(as_uuid=True), ForeignKey("customers.customer_id")),
        Column("product_id", UUID(as_uuid=True), ForeignKey("products.product_id")),
        Column("order_date", Date),
        Column("quantity", Integer),
        Column("unit_price", Numeric(10, 2)),
        Column("region", String),
    )

    products = SATable(
        "products",
        metadata,
        Column("product_id", UUID(as_uuid=True), primary_key=True),
        Column("product_line", String),
        Column("category", String),
    )

    customers = SATable(
        "customers",
        metadata,
        Column("customer_id", UUID(as_uuid=True), primary_key=True),
        Column("name", String),
        Column("segment", String),
        Column("country", String),
    )

    return {
        "orders": orders,
        "products": products,
        "customers": customers,
    }


# -----------------------------
# Display Functions
# -----------------------------


def show_header():
    """Display the application header."""
    header = Text()
    header.append("🔮 ", style="bright_magenta")
    header.append("ClarityQL", style="bold bright_cyan")
    header.append(" - Natural Language Analytics", style="dim")

    console.print()
    console.print(Panel(
        header,
        box=box.DOUBLE,
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()


def show_help():
    """Display help information."""
    help_text = Text()
    help_text.append("Available Commands:\n", style="bold cyan")
    help_text.append("  help     ", style="green")
    help_text.append("- Show this help message\n")
    help_text.append("  schema   ", style="green")
    help_text.append("- Show available fields and metrics\n")
    help_text.append("  exit     ", style="green")
    help_text.append("- Exit the application\n")
    help_text.append("  quit     ", style="green")
    help_text.append("- Exit the application\n\n")

    help_text.append("Example Queries:\n", style="bold cyan")
    help_text.append("  • \"Show me total revenue by region\"\n", style="white")
    help_text.append("  • \"What are the top 10 products by sales quantity?\"\n", style="white")
    help_text.append("  • \"Revenue by customer segment for 2024\"\n", style="white")
    help_text.append("  • \"Count orders by region where quantity > 5\"\n", style="white")

    console.print(Panel(
        help_text,
        title="[bold]Help[/bold]",
        border_style="dim",
    ))


def show_schema():
    """Display the available schema."""
    registry = get_default_registry()

    # Tables section
    table = Table(
        title="[bold cyan]Available Fields[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Table", style="cyan")
    table.add_column("Field", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Aggregatable", style="dim")

    for table_name in registry.list_tables():
        table_meta = registry.get_table(table_name)
        if table_meta:
            for field_name, field_meta in table_meta.fields.items():
                agg = "✓" if field_meta.aggregatable else ""
                table.add_row(
                    table_name,
                    field_name,
                    field_meta.field_type.value,
                    agg,
                )

    console.print(table)
    console.print()

    # Derived metrics
    metrics_table = Table(
        title="[bold cyan]Derived Metrics[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    metrics_table.add_column("Metric", style="green")
    metrics_table.add_column("Expression", style="yellow")
    metrics_table.add_column("Description", style="dim")

    for metric_name in registry.list_derived_metrics():
        metric = registry.get_derived_metric(metric_name)
        if metric:
            metrics_table.add_row(
                metric_name,
                metric.expression,
                metric.description or "",
            )

    console.print(metrics_table)
    console.print()


def show_ast(ast):
    """Display the parsed AST."""
    ast_dict = ast.model_dump()

    # Build a nice representation
    lines = []

    # Metrics
    lines.append("[bold cyan]Metrics:[/bold cyan]")
    for m in ast_dict["metrics"]:
        alias = f" AS {m['alias']}" if m.get("alias") else ""
        lines.append(f"  • {m['function']}({m['field']}){alias}")

    # Dimensions
    if ast_dict["dimensions"]:
        lines.append("[bold cyan]Dimensions:[/bold cyan]")
        for d in ast_dict["dimensions"]:
            alias = f" AS {d['alias']}" if d.get("alias") else ""
            lines.append(f"  • {d['field']}{alias}")

    # Filters
    if ast_dict["filters"]:
        lines.append("[bold cyan]Filters:[/bold cyan]")
        for f in ast_dict["filters"]:
            lines.append(f"  • {f['field']} {f['operator']} {f['value']}")

    # Order By
    if ast_dict["order_by"]:
        lines.append("[bold cyan]Order By:[/bold cyan]")
        for o in ast_dict["order_by"]:
            lines.append(f"  • {o['field']} {o['direction']}")

    lines.append(f"[bold cyan]Limit:[/bold cyan] {ast_dict['limit']}")

    console.print(Panel(
        "\n".join(lines),
        title="[bold green]Parsed Query AST[/bold green]",
        border_style="green",
    ))


def show_sql(sql_text: str):
    """Display the generated SQL."""
    # Format SQL nicely
    formatted_sql = sql_text.replace(" FROM ", "\nFROM ")
    formatted_sql = formatted_sql.replace(" LEFT OUTER JOIN ", "\nLEFT JOIN ")
    formatted_sql = formatted_sql.replace(" WHERE ", "\nWHERE ")
    formatted_sql = formatted_sql.replace(" GROUP BY ", "\nGROUP BY ")
    formatted_sql = formatted_sql.replace(" ORDER BY ", "\nORDER BY ")
    formatted_sql = formatted_sql.replace(" LIMIT ", "\nLIMIT ")
    formatted_sql = formatted_sql.replace(" AND ", "\n  AND ")

    syntax = Syntax(formatted_sql, "sql", theme="monokai", line_numbers=False)
    console.print(Panel(
        syntax,
        title="[bold yellow]Generated SQL[/bold yellow]",
        border_style="yellow",
    ))


def show_results(rows, columns):
    """Display query results in a table."""
    if not rows:
        console.print("[dim]No results found.[/dim]")
        return

    table = Table(
        title=f"[bold cyan]Results ({len(rows)} rows)[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )

    for col in columns:
        table.add_column(str(col), style="cyan")

    for row in rows[:50]:  # Limit display to 50 rows
        table.add_row(*[str(v) if v is not None else "NULL" for v in row])

    if len(rows) > 50:
        console.print(f"[dim](Showing first 50 of {len(rows)} rows)[/dim]")

    console.print(table)


def show_error(title: str, message: str):
    """Display an error message."""
    console.print(Panel(
        f"[red]{message}[/red]",
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
    ))


# -----------------------------
# Main Processing
# -----------------------------


def process_query(query: str, parser: NLQParser, validator: ASTValidator,
                  resolver: JoinResolver, compiler: SQLCompiler, engine):
    """Process a natural language query end-to-end."""

    # Step 1: Parse NLQ to AST
    console.print()
    with console.status("[bold cyan]Parsing your query with AI...[/bold cyan]", spinner="dots"):
        try:
            ast = parser.parse(query)
        except NLQParseError as e:
            show_error("Parse Error", str(e))
            return

    show_ast(ast)
    console.print()

    # Step 2: Validate AST
    with console.status("[bold cyan]Validating query...[/bold cyan]", spinner="dots"):
        try:
            validator.validate(ast)
        except ASTValidationError as e:
            show_error("Validation Error", str(e))
            return

    console.print("[green]✓[/green] Query validated successfully")
    console.print()

    # Step 3: Resolve joins
    with console.status("[bold cyan]Resolving joins...[/bold cyan]", spinner="dots"):
        try:
            join_plan = resolver.resolve(ast)
        except JoinResolutionError as e:
            show_error("Join Resolution Error", str(e))
            return

    if join_plan.joins:
        joins_str = " → ".join([f"{j.left_table} ⟷ {j.right_table}" for j in join_plan.joins])
        console.print(f"[green]✓[/green] Joins resolved: {joins_str}")
    else:
        console.print(f"[green]✓[/green] Single table query: {join_plan.base_table}")
    console.print()

    # Step 4: Compile to SQL
    try:
        sql_stmt = compiler.compile(ast, join_plan)
        sql_text = str(sql_stmt.compile(compile_kwargs={"literal_binds": True}))
    except Exception as e:
        show_error("Compilation Error", str(e))
        return

    show_sql(sql_text)
    console.print()

    # Step 5: Execute query
    with console.status("[bold cyan]Executing query...[/bold cyan]", spinner="dots"):
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql_text))
                columns = result.keys()
                rows = result.fetchall()
        except Exception as e:
            show_error("Database Error", str(e))
            return

    show_results(rows, columns)
    console.print()


def main():
    """Main entry point."""
    show_header()

    # Initialize components
    console.print("[dim]Initializing...[/dim]")

    try:
        registry = get_default_registry()
        parser = NLQParser(registry=registry)
        validator = ASTValidator(registry=registry)
        resolver = JoinResolver(registry=registry)

        tables = create_sqlalchemy_tables()
        compiler = SQLCompiler(sqlalchemy_tables=tables, registry=registry)

        engine = get_engine()

        # Test database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        console.print(f"[green]✓[/green] Connected to database")
        console.print(f"[green]✓[/green] Using LLM: [cyan]{parser.model_info}[/cyan]")
        console.print(f"[green]✓[/green] Prompt version: [cyan]{parser.prompt_version}[/cyan]")

    except Exception as e:
        show_error("Initialization Error", str(e))
        console.print("\n[dim]Make sure your .env file is configured correctly.[/dim]")
        sys.exit(1)

    console.print()
    console.print("[dim]Type 'help' for available commands, or enter a natural language query.[/dim]")
    console.print()

    # Main loop
    while True:
        try:
            query = Prompt.ask("[bold magenta]🔮 Query[/bold magenta]")
            query = query.strip()

            if not query:
                continue

            if query.lower() in ("exit", "quit", "q"):
                console.print("\n[dim]Goodbye! 👋[/dim]\n")
                break

            if query.lower() == "help":
                show_help()
                continue

            if query.lower() == "schema":
                show_schema()
                continue

            # Process the query
            process_query(query, parser, validator, resolver, compiler, engine)

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye! 👋[/dim]\n")
            break
        except Exception as e:
            show_error("Unexpected Error", str(e))


if __name__ == "__main__":
    main()
