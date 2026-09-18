// Chat pane modelled on AI Elements' API shape (Conversation / Message / PromptInput / Tool / Suggestion)
// but without its markdown/mermaid/katex payload. Swap for AI Elements later if richer rendering is wanted.
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { send, useChat, type Msg } from '@/lib/chat'
import { coinBy, pts, RANGES, type RangeKey } from '@/lib/mock'
import { useT } from '@/lib/i18n'
import { Sparkline } from '@/components/charts/Sparkline'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tag } from '@/components/ui-bits'

function ChartCard({ sym, range, onOpen }: { sym: string; range: RangeKey; onOpen?: (sym: string) => void }) {
  const c = coinBy(sym); if (!c) return null
  const s = pts(c, range).map(p => p.p); const step = Math.max(1, Math.floor(s.length / 60))
  return (
    <div className="mt-2 rounded-xl border border-border bg-sunken px-3 py-2">
      <div className="mb-1 flex justify-between text-xs font-bold"><span>{c.sym} · {RANGES[range].label}</span>{onOpen && <button className="font-semibold text-gold-ink hover:underline" onClick={() => onOpen(sym)}>Open →</button>}</div>
      <Sparkline series={s.filter((_, i) => i % step === 0)} w={420} h={90} neg={s[s.length - 1] < s[0]} />
    </div>
  )
}

export function Message({ m, onOpenCoin }: { m: Msg; onOpenCoin?: (sym: string) => void }) {
  const { t } = useT()
  const me = m.role === 'user'
  return (
    <div className={cn('flex max-w-[86%] gap-2.5', me && 'flex-row-reverse self-end')}>
      <div className={cn('grid size-8 shrink-0 place-items-center rounded-full border border-input bg-raised text-base', me && 'border-0 bg-linear-to-br from-[#7b5fe0] to-[#2aabee] text-xs font-extrabold text-white')}>{me ? 'S' : '🦉'}</div>
      <div className="min-w-0">
        <div className={cn('rounded-2xl border border-border bg-raised px-3.5 py-2.5 text-sm leading-relaxed', me && 'border-gold/20 bg-gold-soft')}>
          {m.status ? <span className="inline-flex items-center gap-2 text-secondary-foreground"><Loader2 className="size-3.5 animate-spin text-gold" />{m.status}</span> : m.text}
          {m.chart && <ChartCard sym={m.chart.sym} range={m.chart.range} onOpen={onOpenCoin} />}
          {m.attribution && <span className="mt-2 block text-[11px] text-muted-foreground">Data: CoinGecko</span>}
        </div>
        {m.used && <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">{t('chat.used')}:{m.used.map(u => <Tag key={u}>{u}</Tag>)}</div>}
      </div>
    </div>
  )
}

export function Conversation({ className, onOpenCoin }: { className?: string; onOpenCoin?: (sym: string) => void }) {
  const msgs = useChat(); const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { const el = ref.current; if (el) el.scrollTop = el.scrollHeight }, [msgs])
  return <div ref={ref} className={cn('flex min-h-0 flex-col gap-3.5 overflow-auto px-0.5 py-1', className)}>{msgs.map(m => <Message key={m.id} m={m} onOpenCoin={onOpenCoin} />)}</div>
}

export function PromptInput({ placeholder, prefill, className }: { placeholder?: string; prefill?: string; className?: string }) {
  const { t } = useT(); const [v, setV] = useState('')
  useEffect(() => { if (prefill != null) setV(prefill) }, [prefill])
  const onSubmit = (e: FormEvent) => { e.preventDefault(); if (!v.trim()) return; send(v); setV('') }
  return (
    <form onSubmit={onSubmit} className={cn('flex gap-2', className)}>
      <Input id="chat-input" value={v} onChange={e => setV(e.target.value)} placeholder={placeholder ?? t('chat.ph')} autoComplete="off" className="h-10 bg-sunken" />
      <Button type="submit" className="btn-gold h-10 border-0 font-bold">{t('c.send')}</Button>
    </form>
  )
}

export function Suggestions({ items, onPick }: { items: string[]; onPick?: (s: string) => void }) {
  return <div className="flex flex-wrap gap-1.5">{items.map(s => <button key={s} onClick={() => onPick ? onPick(s) : send(s)} className="rounded-full border border-input bg-card px-2.5 py-1 text-xs font-semibold hover:bg-accent">{s}</button>)}</div>
}
