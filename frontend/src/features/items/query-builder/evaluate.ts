import type { UnifiedItem } from '../types';
import type { QueryCondition, QueryGroup, Operator } from './types';
import { getFieldByKey } from './fields';

function getFieldValue(item: UnifiedItem, fieldKey: string): unknown {
  return (item as unknown as Record<string, unknown>)[fieldKey];
}

function evaluateStringCondition(
  raw: unknown,
  operator: Operator,
  value: string
): boolean {
  if (operator === 'is_empty') return raw == null || String(raw).trim() === '';
  if (operator === 'is_not_empty') return raw != null && String(raw).trim() !== '';

  if (raw == null) return false;
  const s = String(raw).toLowerCase();
  const v = value.toLowerCase();

  switch (operator) {
    case 'equals':
      return s === v;
    case 'not_equals':
      return s !== v;
    case 'contains':
      return s.includes(v);
    case 'not_contains':
      return !s.includes(v);
    case 'starts_with':
      return s.startsWith(v);
    case 'ends_with':
      return s.endsWith(v);
    default:
      return false;
  }
}

function evaluateNumberCondition(
  raw: unknown,
  operator: Operator,
  value: string,
  value2?: string
): boolean {
  if (operator === 'is_empty') return raw == null;
  if (operator === 'is_not_empty') return raw != null;

  if (raw == null) return false;
  const n = Number(raw);
  const v = Number(value);
  if (Number.isNaN(n) || Number.isNaN(v)) return false;

  switch (operator) {
    case 'equals':
      return n === v;
    case 'not_equals':
      return n !== v;
    case 'greater_than':
      return n > v;
    case 'greater_than_or_equal':
      return n >= v;
    case 'less_than':
      return n < v;
    case 'less_than_or_equal':
      return n <= v;
    case 'between': {
      const v2 = Number(value2);
      if (Number.isNaN(v2)) return false;
      return n >= v && n <= v2;
    }
    default:
      return false;
  }
}

function evaluateBooleanCondition(raw: unknown, operator: Operator): boolean {
  switch (operator) {
    case 'is_true':
      return raw === true;
    case 'is_false':
      return raw !== true;
    default:
      return false;
  }
}

function evaluateDateCondition(
  raw: unknown,
  operator: Operator,
  value: string,
  value2?: string
): boolean {
  if (operator === 'is_empty') return raw == null || String(raw).trim() === '';
  if (operator === 'is_not_empty') return raw != null && String(raw).trim() !== '';

  if (raw == null) return false;
  const d = new Date(String(raw)).getTime();
  const v = new Date(value).getTime();
  if (Number.isNaN(d) || Number.isNaN(v)) return false;

  switch (operator) {
    case 'equals':
      return d === v;
    case 'before':
      return d < v;
    case 'after':
      return d > v;
    case 'between': {
      const v2 = new Date(value2 ?? '').getTime();
      if (Number.isNaN(v2)) return false;
      return d >= v && d <= v2;
    }
    default:
      return false;
  }
}

function evaluateCondition(item: UnifiedItem, condition: QueryCondition): boolean {
  const field = getFieldByKey(condition.field);
  if (!field) return true; // unknown field passes

  const raw = getFieldValue(item, condition.field);

  switch (field.type) {
    case 'string':
      return evaluateStringCondition(raw, condition.operator, condition.value);
    case 'number':
      return evaluateNumberCondition(raw, condition.operator, condition.value, condition.value2);
    case 'boolean':
      return evaluateBooleanCondition(raw, condition.operator);
    case 'date':
      return evaluateDateCondition(raw, condition.operator, condition.value, condition.value2);
  }
}

function evaluateGroup(item: UnifiedItem, group: QueryGroup): boolean {
  const conditionResults = group.conditions.map((c) => evaluateCondition(item, c));
  const groupResults = group.groups.map((g) => evaluateGroup(item, g));
  const allResults = [...conditionResults, ...groupResults];

  if (allResults.length === 0) return true;

  return group.conjunction === 'and'
    ? allResults.every(Boolean)
    : allResults.some(Boolean);
}

export function applyAdvancedQuery(
  items: readonly UnifiedItem[],
  query: QueryGroup | null
): UnifiedItem[] {
  if (!query || (query.conditions.length === 0 && query.groups.length === 0)) {
    return [...items];
  }
  return items.filter((item) => evaluateGroup(item, query));
}
