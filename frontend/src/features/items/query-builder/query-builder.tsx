'use client';

import { useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Plus, Trash2 } from 'lucide-react';
import type { QueryGroup, QueryCondition, Conjunction } from './types';
import { QueryRuleRow } from './query-rule-row';
import { QUERY_FIELDS } from './fields';

interface QueryGroupProps {
  readonly group: QueryGroup;
  readonly onChange: (group: QueryGroup) => void;
  readonly onRemove?: () => void;
  readonly depth?: number;
}

let nextId = 1;
function genId(): string {
  return `qb_${Date.now()}_${nextId++}`;
}

function createEmptyCondition(): QueryCondition {
  return {
    id: genId(),
    field: QUERY_FIELDS[0].key,
    operator: 'contains',
    value: '',
  };
}

export function createEmptyGroup(): QueryGroup {
  return {
    id: genId(),
    conjunction: 'and',
    conditions: [],
    groups: [],
  };
}

function QueryGroupEditor({ group, onChange, onRemove, depth = 0 }: QueryGroupProps) {
  const handleConjunctionToggle = useCallback(() => {
    const next: Conjunction = group.conjunction === 'and' ? 'or' : 'and';
    onChange({ ...group, conjunction: next });
  }, [group, onChange]);

  const handleAddCondition = useCallback(() => {
    onChange({
      ...group,
      conditions: [...group.conditions, createEmptyCondition()],
    });
  }, [group, onChange]);

  const handleAddGroup = useCallback(() => {
    const newGroup: QueryGroup = {
      ...createEmptyGroup(),
      conditions: [createEmptyCondition()],
    };
    onChange({ ...group, groups: [...group.groups, newGroup] });
  }, [group, onChange]);

  const handleUpdateCondition = useCallback(
    (id: string, patch: Partial<Omit<QueryCondition, 'id'>>) => {
      onChange({
        ...group,
        conditions: group.conditions.map((c) =>
          c.id === id ? { ...c, ...patch } : c
        ),
      });
    },
    [group, onChange]
  );

  const handleRemoveCondition = useCallback(
    (id: string) => {
      onChange({
        ...group,
        conditions: group.conditions.filter((c) => c.id !== id),
      });
    },
    [group, onChange]
  );

  const handleUpdateSubGroup = useCallback(
    (index: number, updated: QueryGroup) => {
      onChange({
        ...group,
        groups: group.groups.map((g, i) => (i === index ? updated : g)),
      });
    },
    [group, onChange]
  );

  const handleRemoveSubGroup = useCallback(
    (index: number) => {
      onChange({
        ...group,
        groups: group.groups.filter((_, i) => i !== index),
      });
    },
    [group, onChange]
  );

  const totalRules = group.conditions.length + group.groups.length;

  return (
    <div
      className={
        depth > 0
          ? 'border-l-2 border-muted-foreground/20 pl-4 ml-2'
          : ''
      }
    >
      <div className="flex flex-col gap-2">
        {/* Conjunction toggle + group controls */}
        <div className="flex items-center gap-2">
          {totalRules > 1 && (
            <button
              type="button"
              onClick={handleConjunctionToggle}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wide transition-colors ${
                group.conjunction === 'and'
                  ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                  : 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
              }`}
            >
              {group.conjunction}
            </button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={handleAddCondition}
            className="h-7 gap-1 text-xs"
          >
            <Plus className="h-3 w-3" />
            Rule
          </Button>

          {depth < 2 && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddGroup}
              className="h-7 gap-1 text-xs"
            >
              <Plus className="h-3 w-3" />
              Group
            </Button>
          )}

          {onRemove && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRemove}
              className="h-7 gap-1 text-xs text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
        </div>

        {/* Conditions */}
        {group.conditions.map((condition) => (
          <QueryRuleRow
            key={condition.id}
            condition={condition}
            onUpdate={handleUpdateCondition}
            onRemove={handleRemoveCondition}
          />
        ))}

        {/* Sub-groups */}
        {group.groups.map((subGroup, index) => (
          <QueryGroupEditor
            key={subGroup.id}
            group={subGroup}
            onChange={(updated) => handleUpdateSubGroup(index, updated)}
            onRemove={() => handleRemoveSubGroup(index)}
            depth={depth + 1}
          />
        ))}
      </div>
    </div>
  );
}

interface QueryBuilderProps {
  readonly query: QueryGroup;
  readonly onChange: (query: QueryGroup) => void;
}

export function QueryBuilder({ query, onChange }: QueryBuilderProps) {
  const handleClear = useCallback(() => {
    onChange(createEmptyGroup());
  }, [onChange]);

  const hasRules = query.conditions.length > 0 || query.groups.length > 0;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-dashed border-muted-foreground/30 p-3">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          Advanced Query
        </span>
        {hasRules && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClear}
            className="h-6 text-xs text-muted-foreground"
          >
            Clear all
          </Button>
        )}
      </div>
      <QueryGroupEditor group={query} onChange={onChange} />
      {!hasRules && (
        <p className="text-muted-foreground text-xs">
          Add rules to build a custom query. Rules within a group are combined with AND/OR logic.
        </p>
      )}
    </div>
  );
}
