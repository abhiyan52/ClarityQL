# ClarityQL Follow-up Query Examples

## Tested Follow-up Patterns

This document shows the types of follow-up queries that ClarityQL can handle, validated by the comprehensive test suite.

### 1. Adding Dimensions (Grouping)

**User's Initial Query:** "What is the total quantity sold?"
```
AST: QueryAST(metrics=[SUM(quantity)])
```

**Follow-up:** "Add group by product_line"
```
Delta: QueryAST(metrics=[SUM(quantity)], dimensions=[Dimension(field="product_line")])
Result: QueryAST(metrics=[SUM(quantity)], dimensions=[Dimension(field="product_line")])
```

**Follow-up 2:** "Break it down by region too"
```
Delta: QueryAST(metrics=[SUM(quantity)], dimensions=[Dimension(field="region")])
Result: QueryAST(
    metrics=[SUM(quantity)], 
    dimensions=[Dimension(field="product_line"), Dimension(field="region")]
)
```

### 2. Adding Filters (WHERE Clause)

**Initial:** "Show revenue by region"
```
AST: QueryAST(
    metrics=[SUM(revenue)],
    dimensions=[Dimension(field="region")]
)
```

**Follow-up:** "Only for Europe"
```
Delta: QueryAST(
    filters=[Filter(field="region", operator=EQ, value="EMEA")]
)
Result: QueryAST(
    metrics=[SUM(revenue)],
    dimensions=[Dimension(field="region")],
    filters=[Filter(field="region", operator=EQ, value="EMEA")]
)
```

**Follow-up 2:** "Actually, show me APAC instead"
```
Delta: QueryAST(
    filters=[Filter(field="region", operator=EQ, value="APAC")]
)
Result: QueryAST(
    metrics=[SUM(revenue)],
    dimensions=[Dimension(field="region")],
    filters=[Filter(field="region", operator=EQ, value="APAC")]  # Replaced
)
```

### 3. Adding Independent Filters

**Initial:** "Average price by category"
```
AST: QueryAST(
    metrics=[AVG(unit_price)],
    dimensions=[Dimension(field="category")]
)
```

**Follow-up:** "Where region is North America"
```
Delta: QueryAST(
    filters=[Filter(field="region", operator=EQ, value="NA")]
)
Result: QueryAST(
    metrics=[AVG(unit_price)],
    dimensions=[Dimension(field="category")],
    filters=[Filter(field="region", operator=EQ, value="NA")]
)
```

### 4. Combining Multiple Refinements

**Initial:** "Total quantity sold"
```
AST: QueryAST(metrics=[SUM(quantity)])
```

**Follow-up:** "Break down by region, for Europe only"
```
Delta: QueryAST(
    dimensions=[Dimension(field="region")],
    filters=[Filter(field="region", operator=EQ, value="EMEA")]
)
Result: QueryAST(
    metrics=[SUM(quantity)],
    dimensions=[Dimension(field="region")],
    filters=[Filter(field="region", operator=EQ, value="EMEA")]
)
```

**Follow-up 2:** "Also group by product line"
```
Delta: QueryAST(
    dimensions=[Dimension(field="product_line")]
)
Result: QueryAST(
    metrics=[SUM(quantity)],
    dimensions=[Dimension(field="region"), Dimension(field="product_line")],
    filters=[Filter(field="region", operator=EQ, value="EMEA")]
)
```

### 5. Modifying Ordering

**Initial:** "Revenue by region"
```
AST: QueryAST(
    metrics=[SUM(revenue)],
    dimensions=[Dimension(field="region")],
    order_by=[OrderBy(field="revenue", direction=DESC)]
)
```

**Follow-up:** "Sort by region A-Z instead"
```
Delta: QueryAST(
    order_by=[OrderBy(field="region", direction=ASC)]
)
Result: QueryAST(
    metrics=[SUM(revenue)],
    dimensions=[Dimension(field="region")],
    order_by=[OrderBy(field="region", direction=ASC)]  # Replaced
)
```

### 6. Adjusting Result Limits

**Initial:** "Top 10 products by quantity"
```
AST: QueryAST(
    metrics=[SUM(quantity)],
    dimensions=[Dimension(field="product_line")],
    limit=10
)
```

**Follow-up:** "Show me 20 instead"
```
Delta: QueryAST(
    limit=20
)
Result: QueryAST(
    metrics=[SUM(quantity)],
    dimensions=[Dimension(field="product_line")],
    limit=20  # Updated
)
```

### 7. Complex Real-World Scenario

**Initial:** "Revenue by region in Q1"
```
AST: QueryAST(
    metrics=[SUM(revenue)],
    dimensions=[Dimension(field="region")],
    filters=[
        Filter(
            field="order_date",
            operator=BETWEEN,
            value=["2024-01-01", "2024-03-31"]
        )
    ],
    order_by=[OrderBy(field="revenue", direction=DESC)],
    limit=10
)
```

**Follow-up 1:** "Break down by product line too"
```
Merged: Dimensions now include [region, product_line], preserves everything else
```

**Follow-up 2:** "But only show electronics"
```
Merged: Adds filter on category=Electronics, preserves everything else
```

**Follow-up 3:** "Sort by product line ascending"
```
Merged: Replaces order_by with [OrderBy(field="product_line", direction=ASC)]
```

---

## Safety Features Validated

All tested follow-up patterns include safety validation:

### ✅ What Works
- Adding valid fields from the database schema
- Refining filters on existing fields
- Combining multiple dimensions
- Changing sort order and limits
- Natural language variations

### ❌ What's Blocked
```python
# Unknown field → ERROR
"Group by fake_column"  # Not in database

# Wrong operator → ERROR
"Where region > APAC"   # Can't use > on strings

# Non-aggregatable metric → ERROR
"Sum of region"         # region is a string, not numeric

# Malformed filter → ERROR
"Between 2024-01-01"    # BETWEEN needs 2 dates
```

## Test Coverage by Pattern

| Pattern | Tests | Examples |
|---------|-------|----------|
| Add dimension | 3 | "group by X", "break down by X" |
| Override filter | 3 | "Actually for Y", "change to Z" |
| Add independent filter | 3 | "And where X = Y" |
| Adjust ordering | 2 | "Sort by X" |
| Adjust limit | 2 | "Show 50 instead of 10" |
| Complex pipeline | 4 | Multiple refinements combined |
| Validation | 5 | Invalid follow-ups rejected |
| Safety | 10 | Hallucinations prevented |

## Running the Tests

To verify all follow-up patterns work correctly:

```bash
# Run follow-up tests
uv run pytest tests/core/test_nlq_followups.py -v

# Run specific category
uv run pytest tests/core/test_nlq_followups.py::TestASTMergeDimensions -v

# Run with output
uv run pytest tests/core/test_nlq_followups.py::TestFollowUpQueryCompilation -v -s
```

## Implementation Details

Follow-ups are handled by the `merge_ast()` function in `packages/core/conversation/ast_merge.py`:

```python
# Example from service layer
previous_ast = load_from_database(conversation_id)
delta_ast = parser.parse(follow_up_query)

# Merge preserves previous context
merged_ast = merge_ast(previous_ast, delta_ast)

# Merged AST is then validated and compiled to SQL
validator.validate(merged_ast)
join_plan = resolver.resolve(merged_ast)
sql = compiler.compile(merged_ast, join_plan)
```

The merge logic ensures:
1. **Metrics**: Preserved unless delta explicitly changes
2. **Dimensions**: Extended and deduplicated
3. **Filters**: Merged by field (new overrides old on same field)
4. **Order**: Replaced if delta specified, else preserved
5. **Limit**: Replaced if delta differs from default (50), else preserved

---

For more details, see `TEST_SUMMARY.md` and `tests/core/test_nlq_followups.py`.
