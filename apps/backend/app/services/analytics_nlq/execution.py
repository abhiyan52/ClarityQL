"""Query execution layer."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


@dataclass
class ExecutionResult:
    """Result of query execution."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int


class QueryExecutionError(Exception):
    """Raised when query execution fails."""

    pass


async def execute_query(
    session: AsyncSession,
    statement: Select,
) -> ExecutionResult:
    """
    Execute a SQLAlchemy Select statement and return results.

    This is a thin execution layer with no business logic.
    It accepts a compiled statement and returns structured results.

    Args:
        session: Async database session.
        statement: SQLAlchemy Select statement.

    Returns:
        ExecutionResult with columns and rows.

    Raises:
        QueryExecutionError: If execution fails.
    """
    try:
        # Compile to SQL string for execution
        # We use text() because async session needs raw SQL
        compiled = statement.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)

        result = await session.execute(text(sql_str))

        # Extract column names
        columns = list(result.keys())

        # Fetch all rows
        rows_raw = result.fetchall()

        # Convert to list of lists for JSON serialization
        rows = [list(row) for row in rows_raw]

        return ExecutionResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )

    except Exception as e:
        # Don't expose raw SQL errors to users
        raise QueryExecutionError(
            f"Query execution failed: {type(e).__name__}"
        ) from e


def get_sql_string(statement: Select) -> str:
    """
    Get the SQL string from a SQLAlchemy statement.

    Args:
        statement: SQLAlchemy Select statement.

    Returns:
        SQL string with bound parameters.
    """
    compiled = statement.compile(compile_kwargs={"literal_binds": True})
    return str(compiled)
