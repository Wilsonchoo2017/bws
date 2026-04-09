export type FieldType = 'string' | 'number' | 'boolean' | 'date';

export type StringOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'is_empty'
  | 'is_not_empty';

export type NumberOperator =
  | 'equals'
  | 'not_equals'
  | 'greater_than'
  | 'greater_than_or_equal'
  | 'less_than'
  | 'less_than_or_equal'
  | 'between'
  | 'is_empty'
  | 'is_not_empty';

export type BooleanOperator = 'is_true' | 'is_false';

export type DateOperator =
  | 'equals'
  | 'before'
  | 'after'
  | 'between'
  | 'is_empty'
  | 'is_not_empty';

export type Operator = StringOperator | NumberOperator | BooleanOperator | DateOperator;

export type Conjunction = 'and' | 'or';

export interface QueryCondition {
  readonly id: string;
  readonly field: string;
  readonly operator: Operator;
  readonly value: string;
  readonly value2?: string; // for "between" operator
}

export interface QueryGroup {
  readonly id: string;
  readonly conjunction: Conjunction;
  readonly conditions: readonly QueryCondition[];
  readonly groups: readonly QueryGroup[];
}

export interface FieldDefinition {
  readonly key: string;
  readonly label: string;
  readonly type: FieldType;
  readonly group: string;
}
