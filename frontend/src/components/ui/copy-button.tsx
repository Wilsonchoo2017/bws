'use client';

import { CheckIcon, ClipboardIcon } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

interface CopyButtonProps {
  value: string;
  label?: string;
}

export function CopyButton({ value, label }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      onClick={handleCopy}
      className='inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground'
      title={`Copy ${label ?? 'value'}`}
    >
      {copied ? (
        <>
          <CheckIcon className='size-3 text-green-600' />
          Copied
        </>
      ) : (
        <>
          <ClipboardIcon className='size-3' />
          Copy
        </>
      )}
    </button>
  );
}
