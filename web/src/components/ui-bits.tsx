import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { fmtPct } from '@/lib/format'
import { RANGE_KEYS, type RangeKey } from '@/lib/mock'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

export const Delta = ({ v, suffix, className }: { v: number; suffix?: string; className?: string }) => (
  <span className={cn('delta', v >= 0 ? 'delta-up' : 'delta-down', className)}>{fmtPct(v)}{suffix ? ' ' + suffix : ''}</span>
)
export const CoinIcon = ({ sym, size = 30 }: { sym: string; size?: number }) => (
  <span className="grid shrink-0 place-items-center rounded-full border border-input bg-raised font-mono text-[10px] font-extrabold text-secondary-foreground" style={{ width: size, height: size, boxShadow: '0 0 0 1px var(--gold-soft)' }}>{sym.slice(0, 4)}</span>
)
export function Section({ title, hint, right, children, className, bodyClass }: { title?: ReactNode; hint?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={cn('card-premium min-w-0 p-5 md:p-6', className)}>
      {(title || right) && (
        <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          {title && <h2 className="text-[15.5px] font-bold">{title}</h2>}
          {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
          {right && <div className="ml-auto flex items-center gap-2">{right}</div>}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}
export function RangeTabs({ value, onChange, className }: { value: RangeKey; onChange: (r: RangeKey) => void; className?: string }) {
  return (
    <ToggleGroup type="single" value={value} onValueChange={v => v && onChange(v as RangeKey)} className={cn('rounded-[11px] border border-border bg-sunken p-[3px]', className)} aria-label="Range">
      {RANGE_KEYS.map(k => <ToggleGroupItem key={k} value={k} className="h-8 rounded-lg px-3 text-xs font-bold text-secondary-foreground data-[state=on]:bg-card data-[state=on]:text-gold-ink data-[state=on]:shadow">{k}</ToggleGroupItem>)}
    </ToggleGroup>
  )
}
export const Eyebrow = ({ children, className }: { children: ReactNode; className?: string }) => <div className={cn('eyebrow', className)}>{children}</div>
export const Tag = ({ children, className }: { children: ReactNode; className?: string }) => <span className={cn('inline-block rounded-md border border-border bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-secondary-foreground', className)}>{children}</span>
