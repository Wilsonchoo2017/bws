'use client';

import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';
import type { QueryCondition, Operator, FieldType } from './types';
import {
  QUERY_FIELDS,
  getFieldByKey,
  getOperatorsForType,
  operatorNeedsValue,
  operatorNeedsSecondValue,
} from './fields';

interface QueryRuleRowProps {
  readonly condition: QueryCondition;
  readonly onUpdate: (id: string, patch: Partial<Omit<QueryCondition, 'id'>>) => void;
  readonly onRemove: (id: string) => void;
}

// Group fields by their group property for the optgroup display
const GROUPED_FIELDS = QUERY_FIELDS.reduce<Record<string, typeof QUERY_FIELDS[number][]>>(
  (acc, field) => {
    const group = acc[field.group] ?? [];
    return { ...acc, [field.group]: [...group, field] };
  },
  {}
);

const GROUP_ORDER = [
  'Catalog', 'Shopee', 'ToysRUs', 'Mighty Utan', 'BrickLink',
  'ML', 'Cohort', 'Liquidity',
];

function getDefaultOperator(type: FieldType): Operator {
  switch (type) {
    case 'string':
      return 'contains';
    case 'number':
      return 'greater_than_or_equal';
    case 'boolean':
      return 'is_true';
    case 'date':
      return 'after';
  }
}

export function QueryRuleRow({ condition, onUpdate, onRemove }: QueryRuleRowProps) {
  const field = getFieldByKey(condition.field);
  const operators = field ? getOperatorsForType(field.type) : [];
  const showValue = operatorNeedsValue(condition.operator);
  const showValue2 = operatorNeedsSecondValue(condition.operator);

  const handleFieldChange = (newFieldKey: string) => {
    const newField = getFieldByKey(newFieldKey);
    if (!newField) return;
    const newOp = getDefaultOperator(newField.type);
    onUpdate(condition.id, { field: newFieldKey, operator: newOp, value: '', value2: undefined });
  };

  const inputType = field?.type === 'number' ? 'number' : field?.type === 'date' ? 'date' : 'text';

  return (
    <div className="flex items-center gap-2">
      {/* Field selector */}
      <select
        value={condition.field}
        onChange={(e) => handleFieldChange(e.target.value)}
        className="border-input bg-transparent rounded-md border px-2 py-1.5 text-sm shadow-xs h-8 min-w-[160px]"
      >
        {GROUP_ORDER.map((groupName) => {
          const fields = GROUPED_FIELDS[groupName];
          if (!fields) return null;
          return (
            <optgroup key={groupName} label={groupName}>
              {fields.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            </optgroup>
          );
        })}
      </select>

      {/* Operator selector */}
      <select
        value={condition.operator}
        onChange={(e) => onUpdate(condition.id, { operator: e.target.value as Operator })}
        className="border-input bg-transparent rounded-md border px-2 py-1.5 text-sm shadow-xs h-8 min-w-[120px]"
      >
        {operators.map((op) => (
          <option key={op.value} value={op.value}>
            {op.label}
          </option>
        ))}
      </select>

      {/* Value input */}
      {showValue && (
        <input
          type={inputType}
          value={condition.value}
          onChange={(e) => onUpdate(condition.id, { value: e.target.value })}
          placeholder="value"
          className="border-input bg-transparent rounded-md border px-2 py-1.5 text-sm shadow-xs h-8 w-32 font-mono placeholder:text-muted-foreground"
        />
      )}

      {/* Second value for "between" */}
      {showValue2 && (
        <>
          <span className="text-muted-foreground text-xs">and</span>
          <input
            type={inputType}
            value={condition.value2 ?? ''}
            onChange={(e) => onUpdate(condition.id, { value2: e.target.value })}
            placeholder="value"
            className="border-input bg-transparent rounded-md border px-2 py-1.5 text-sm shadow-xs h-8 w-32 font-mono placeholder:text-muted-foreground"
          />
        </>
      )}

      {/* Remove button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onRemove(condition.id)}
        className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
