# NLQ Follow-up Tests - Comprehensive Summary

## Overview

We've created a comprehensive test suite for ClarityQL's follow-up query behavior, covering merge logic, integration scenarios, LLM output validation, and SQL safety guarantees.

**File:** `tests/core/test_nlq_followups.py`
**Test Count:** 38 tests
**Status:** ✅ All passing

## Test Categories

### 1. AST Merge Tests (14 tests)

These tests verify the core logic that enables conversational queries. When a user refines their query (e.g., "add group by product_line"), the system merges the follow-up with the previous AST.

#### Dimension Merge Tests (3 tests)
- `test_merge_adds_dimension_to_previous_query`: Validates adding a new dimension extends previous ones
- `test_merge_deduplicates_dimensions`: Ensures duplicate dimensions aren't added twice
- `test_merge_multiple_dimensions_from_followup`: Multiple dimensions can be added in one follow-up

#### Filter Merge Tests (3 tests)
- `test_merge_adds_filter_to_previous_query`: New filters extend or override existing ones
- `test_merge_independent_filters`: Filters on different fields are preserved
- `test_merge_overrides_filter_on_same_field`: New filter on same field replaces old one

#### Metrics Merge Tests (2 tests)
- `test_merge_keeps_previous_metrics_when_delta_empty`: Metrics are preserved if not explicitly changed
- `test_merge_keeps_previous_metrics_with_new_dimensions`: Adding dimensions doesn't affect metrics

#### Order & Limit Merge Tests (4 tests)
- `test_merge_keeps_previous_order_when_delta_empty`: Previous order preserved if not specified
- `test_merge_replaces_order_when_delta_provided`: Explicit order in follow-up replaces previous
- `test_merge_keeps_previous_limit_when_delta_default`: Default limit (50) preserves previous custom limit
- `test_merge_replaces_limit_when_delta_custom`: Custom limit in follow-up replaces previous

#### AST Diff & Delta Tests (2 tests)
- `test_diff_detects_added_dimension`: Changes between ASTs are properly detected
- `test_diff_detects_filter_changes`: Filter modifications are captured

#### Delta Emptiness Tests (3 tests)
- `test_empty_delta`: Queries with only default values are marked as empty
- `test_non_empty_delta_with_dimensions`: Non-empty detection works for dimensions
- `test_non_empty_delta_with_custom_limit`: Non-empty detection works for custom limits

### 2. Integration Tests (4 tests)

End-to-end tests that compile follow-up queries through the full pipeline: merge → validation → join resolution → SQL compilation.

- `test_initial_query_filter_group_aggregate`: Basic query compiles with all components
- `test_followup_adds_dimension_to_filter_group_aggregate`: Follow-up integration: adding dimensions preserves filters and grouping
- `test_followup_adds_aggregate_with_existing_filters_and_grouping`: Follow-up can add metrics while preserving previous filters and dimensions
- `test_full_pipeline_filter_group_aggregate_order_limit`: Complex 3-table query with multiple aggregates, dimensions, filters, and ordering

### 3. LLM Output Validation Tests (5 tests)

Tests validating that typical LLM outputs for follow-up queries are correctly validated.

- `test_validate_followup_add_group_by_product_line`: Validates "add group by product_line"
- `test_validate_followup_break_down_by_product_line`: Validates "break it down by product line"
- `test_validate_followup_filter_refine`: Validates "only for Europe"
- `test_validate_followup_with_unknown_field_fails`: LLM hallucination (unknown field) is caught
- `test_validate_followup_with_multiple_valid_dimensions`: Multiple valid dimensions from LLM pass

### 4. SQL Safety Guarantee Tests (10 tests)

These tests document and verify the system's defenses against LLM hallucinations and malformed queries.

#### Field Validation (3 tests)
- `test_llm_hallucination_unknown_metric_field_blocked`: Unknown metric field rejected
- `test_llm_hallucination_unknown_dimension_field_blocked`: Unknown dimension field rejected
- `test_llm_hallucination_unknown_filter_field_blocked`: Unknown filter field rejected

#### Type & Aggregation Safety (4 tests)
- `test_llm_hallucination_non_aggregatable_metric_blocked`: Non-aggregatable fields (e.g., region) can't be used in SUM()
- `test_llm_wrong_operator_for_field_type_blocked`: Wrong operator for field type (e.g., > on string) rejected
- `test_invalid_between_operator_without_two_values_blocked`: BETWEEN requires exactly 2 values
- `test_invalid_in_operator_without_list_blocked`: IN operator requires list format

#### Structural Safety (2 tests)
- `test_order_by_invalid_field_blocked`: ORDER BY field must be in metrics or dimensions
- `test_limit_exceeds_maximum_blocked`: LIMIT capped at 1000

#### Cumulative Safety (1 test)
- `test_cumulative_safety_filters_dimensions_aggregates`: All validation layers work together to prevent bad SQL

### 5. Merge Error Handling Tests (2 tests)

- `test_merge_queries_with_metrics_produces_valid_ast`: Merge produces valid QueryAST
- `test_merge_with_single_metric_previous`: Single metric queries can be merged with additional dimensions

## Key Testing Patterns

### 1. Follow-up Simulation
Tests simulate the conversational flow:
```python
# Initial query
previous = QueryAST(metrics=[...], dimensions=[Dimension(field="region")])

# User: "add group by product_line"
delta = QueryAST(metrics=[...], dimensions=[Dimension(field="product_line")])

# Merge and verify
merged = merge_ast(previous, delta)
assert {d.field for d in merged.dimensions} == {"region", "product_line"}
```

### 2. Real-World LLM Outputs
Tests use actual follow-up queries users might say:
- "add group by product_line"
- "break it down by product line"
- "only for Europe"
- "also show average price"

### 3. Safety-First Validation
Each test documents a specific safety guarantee:
```python
# LLM might hallucinate a field, but system catches it
query = QueryAST(metrics=[Metric(..., field="fantasy_metric")])
with pytest.raises(ASTValidationError):
    validator.validate(query)
```

### 4. Full Pipeline Testing
Integration tests verify the entire flow:
```
Merge → Validation → Join Resolution → SQL Compilation
```

## Coverage Summary

| Category | Tests | Coverage |
|----------|-------|----------|
| Dimension Merging | 3 | Adding, deduplicating, extending dimensions |
| Filter Merging | 3 | Adding, overriding, preserving filters |
| Metrics Merging | 2 | Preserving previous metrics |
| Order & Limit Merging | 4 | Conditional preservation/replacement |
| Diff & Delta | 5 | Change detection and emptiness |
| Integration | 4 | End-to-end query compilation |
| LLM Validation | 5 | Typical follow-up outputs |
| Safety Guarantees | 10 | LLM hallucination prevention |
| Error Handling | 2 | Merge error scenarios |
| **Total** | **38** | **Comprehensive** |

## Running the Tests

### Run all follow-up tests:
```bash
uv run pytest tests/core/test_nlq_followups.py -v
```

### Run specific test class:
```bash
uv run pytest tests/core/test_nlq_followups.py::TestASTMergeDimensions -v
```

### Run with coverage:
```bash
uv run pytest tests/core/test_nlq_followups.py --cov=packages/core/conversation --cov=packages/core/safety
```

### Run all core tests:
```bash
uv run pytest tests/core/ -v
```

## Safety Guarantees Documented

The test suite documents these critical safety properties:

1. **Unknown Field Prevention**: LLM cannot reference non-existent database fields
2. **Type Safety**: Operators are type-checked (no > on strings, no LIKE on dates)
3. **Aggregation Safety**: Non-aggregatable fields cannot be used in aggregates
4. **Structural Safety**: ORDER BY fields must exist in SELECT
5. **Range Safety**: LIMIT is bounded (1-1000 rows)
6. **Format Safety**: BETWEEN requires 2 values, IN requires list
7. **Cumulative Validation**: Multiple layers catch errors
8. **Conversational Coherence**: Merge logic preserves user intent across turns

## Key Insights

### Merge Rules Tested
- **Dimensions**: Extend (additive)
- **Filters**: Merge by field (new overrides old on same field)
- **Metrics**: Preserve unless delta explicitly changes
- **Order**: Replace if delta provided, else keep previous
- **Limit**: Keep previous if delta is default (50), else use delta

### LLM Output Validation
The tests validate these natural language patterns:
- "add X" → Add dimension/filter to previous
- "break down by X" → Add grouping dimension
- "filter by X" → Add where clause
- "show me X" → Change metrics (validated as valid fields)
- Unknown fields → Caught before SQL generation

### Integration Test Scenarios
1. Simple queries with multiple components
2. Adding dimensions to existing queries
3. Adding metrics to multi-dimensional queries
4. Complex 3-table joins with multiple aggregates and filters

## Testing Best Practices Demonstrated

1. **Comprehensive Edge Cases**: Dimension deduplication, filter override, default value handling
2. **Real-World Scenarios**: Follow-ups matching actual user speech patterns
3. **Safety-First Approach**: Hallucination prevention at multiple layers
4. **Clear Test Names**: Descriptive names that explain the behavior being tested
5. **Isolated Fixtures**: Each test has clean setup via pytest fixtures
6. **Integration Testing**: Full pipeline tests verify components work together

## Future Test Enhancements

Potential areas for additional testing:
1. Multi-turn conversations (3+ queries)
2. Complex metric refinements
3. Edge cases in join resolution for follow-ups
4. Performance testing with large filter lists
5. Concurrent follow-up handling
6. Natural language variations (same intent, different wording)
7. Error recovery and retry logic

## Commit Information

**Branch:** main  
**Files Added:** tests/core/test_nlq_followups.py  
**Tests Added:** 38  
**Total Core Tests:** 127 (all passing)

---

**Created:** 2026-02-08  
**Test Framework:** pytest 9.0.2  
**Python Version:** 3.12.11
