import { useEffect, useMemo, useRef, useState } from 'react'
import { Command as CommandPrimitive } from 'cmdk'
import { Search } from 'lucide-react'
import { toast } from 'sonner'
import { coinBy, RANGE_KEYS, type RangeKey } from '@/lib/mock'
import { fmtUSD } from '@/lib/format'
import { alerts, getState } from '@/lib/store'
import { send } from '@/lib/chat'
import { navigate } from '@/lib/router'
import { compareWith, setView } from '@/lib/view'
import { useT, type Key } from '@/lib/i18n'
type TFn = (k: Key, v?: Record<string, string | number>) => string
import { cn } from '@/lib/utils'
import { undoToast } from '@/components/features/Alerts'

type Intent = { id: string; label: string; sub?: string; run: () => void }
const TICK = '(BTC|ETH|SOL|TON|XRP|ADA|DOGE|LINK|AVAX|DOT|SUI|HYPE|TAO|ARB|OP|APT|NEAR|INJ|LTC|BCH|ATOM|UNI|AAVE|WLD|PEPE|BITCOIN|ETHEREUM|SOLANA)'
const norm = (s: string) => ({ BITCOIN: 'BTC', ETHEREUM: 'ETH', SOLANA: 'SOL' } as Record<string, string>)[s.toUpperCase()] ?? s.toUpperCase()

/** Parses the box into a ranked list of intents. `mode` decides where "open a coin" lands. */
export function parseIntents(q: string, mode: 'standard' | 'advanced', t: TFn): Intent[] {
  const Q = q.trim(); if (!Q) return []
  const U = Q.toUpperCase(); const out: Intent[] = []; let m: RegExpMatchArray | null
  const openCoin = (sym: string, range?: RangeKey, tab?: string) => {
    if (range) setView({ range })
    setView({ coin: sym, mode: 'single' })
    navigate(mode === 'advanced' ? `coin/${sym}${tab ? '/' + tab : ''}` : tab === 'news' ? 'news' : tab === 'similar' ? 'similar' : 'dashboard')
  }
  if ((m = U.match(new RegExp('^(?:SHOW |OPEN |CHART )?' + TICK + '(?:\\s+(24H|7D|30D|90D|1Y))?$'))) && coinBy(norm(m[1]))) {
    const sym = norm(m[1]); const r = m[2]?.toLowerCase() as RangeKey | undefined
    out.push({ id: 'coin', label: `Open ${sym}${r ? ' · ' + r : ''}`, run: () => { openCoin(sym, r && RANGE_KEYS.includes(r) ? r : undefined); toast(t('toast.charting', { s: sym, r: r ?? '' })) } })
  }
  if ((m = U.match(new RegExp('^COMPARE\\s+' + TICK + '(?:\\s+(?:AND|VS|,)?\\s*' + TICK + ')+')))) {
    const syms = [...U.matchAll(new RegExp(TICK, 'g'))].map(x => norm(x[1])).filter(s => getState().watchlist.some(c => c.sym === s)).slice(0, 5)
    if (syms.length > 1) out.push({ id: 'cmp', label: 'Compare ' + syms.join(' vs '), run: () => { compareWith(syms[0], syms[1]); setView({ compare: syms }); navigate(mode === 'advanced' ? 'coin/' + syms[0] : 'dashboard') } })
  }
  if ((m = U.match(new RegExp('^(?:ALERT|NOTIFY|TELL ME WHEN)\\s+' + TICK + '\\s*(ABOVE|BELOW|OVER|UNDER|>|<|HITS|REACHES)\\s*\\$?([\\d.,]+)\\s*(K)?')))) {
    const price = parseFloat(m[3].replace(/,/g, '')) * (m[4] ? 1000 : 1); const dir = /BELOW|UNDER|</.test(m[2]) ? 'below' : 'above'; const sym = norm(m[1])
    out.push({ id: 'alert', label: `Arm alert: ${sym} ${dir} ${fmtUSD(price)}`, sub: 'pushes to Telegram when it crosses', run: () => { const undo = alerts.add({ sym, dir, price, rec: false, state: 'armed', said: Q, when: 'today' }); undoToast(`Armed: ${sym} ${dir} ${fmtUSD(price)}`, undo, 'Undo') } })
  }
  if ((m = U.match(new RegExp('^(?:WHY|NEWS|WHAT HAPPENED).*?' + TICK)))) { const sym = norm(m[1]); out.push({ id: 'news', label: `Why did ${sym} move? · grounded answer`, run: () => openCoin(sym, undefined, 'news') }) }
  if ((m = U.match(new RegExp('^(?:SIMILAR|LIKE)\\s+(?:TO\\s+)?' + TICK)))) { const sym = norm(m[1]); out.push({ id: 'sim', label: `Coins similar to ${sym}`, run: () => openCoin(sym, undefined, 'similar') }) }
  const pages: Record<string, string> = { ALERTS: 'alerts', SCHEDULES: 'alerts', INBOX: 'alerts', MEMORY: 'memory', SETTINGS: 'settings', ACCOUNT: 'settings', PLAN: 'plan', NEWS: 'news', SIMILAR: 'similar', DASHBOARD: 'dashboard', CHAT: 'chat' }
  if (pages[U]) out.push({ id: 'go', label: 'Go to ' + pages[U], run: () => navigate(pages[U]) })
  out.push({ id: 'ask', label: `Ask the agent: “${Q}”`, sub: 'natural language, same as Telegram', run: () => { send(Q); if (mode === 'standard') navigate('chat') } })
  return out
}

export function Omnibox({ mode, className, placeholder }: { mode: 'standard' | 'advanced'; className?: string; placeholder?: string }) {
  const { t } = useT()
  const [q, setQ] = useState(''); const [open, setOpen] = useState(false)
  const ref = useRef<HTMLInputElement>(null)
  const items = useMemo(() => parseIntents(q, mode, t), [q, mode, t])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { const tag = (document.activeElement?.tagName || '').toLowerCase(); if (e.key === '/' && !['input', 'textarea', 'select'].includes(tag) && !(document.activeElement as HTMLElement)?.isContentEditable) { e.preventDefault(); ref.current?.focus() } }
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey)
  }, [])
  const run = (it: Intent) => { it.run(); setQ(''); setOpen(false); ref.current?.blur() }
  return (
    <CommandPrimitive shouldFilter={false} loop className={cn('relative w-full', className)} onKeyDown={e => { if (e.key === 'Escape') { setOpen(false); ref.current?.blur() } }}>
      <div className="flex h-10 items-center gap-2.5 rounded-xl border border-border bg-sunken px-3 shadow-inner transition focus-within:border-gold/50 focus-within:ring-[3px] focus-within:ring-gold-soft">
        <Search className="size-4 shrink-0 text-muted-foreground" />
        <CommandPrimitive.Input ref={ref} value={q} onValueChange={v => { setQ(v); setOpen(true) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)} placeholder={placeholder ?? t('top.search')} className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-muted-foreground" />
        <kbd className="rounded-md border border-input bg-card px-1.5 py-0.5 font-mono text-[11px] font-semibold text-muted-foreground">/</kbd>
      </div>
      {open && items.length > 0 && (
        <CommandPrimitive.List className="absolute left-0 right-0 top-[calc(100%+6px)] z-40 max-h-80 overflow-auto rounded-xl border border-input bg-popover p-1.5 shadow-xl">
          {items.map((it, i) => (
            <CommandPrimitive.Item key={it.id} value={it.id} onSelect={() => run(it)} onMouseDown={e => { e.preventDefault(); run(it) }} className="grid cursor-pointer grid-cols-[26px_1fr] items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-gold-soft">
              <span className="text-center font-mono text-xs text-muted-foreground">{i === 0 ? '↵' : ''}</span>
              <span><b className="font-semibold">{it.label}</b>{it.sub && <span className="ml-2 text-xs text-muted-foreground">{it.sub}</span>}</span>
            </CommandPrimitive.Item>
          ))}
          <div className="mt-1 border-t border-border px-2.5 pb-1 pt-2 text-[11.5px] text-muted-foreground">{t('omni.hint')}</div>
        </CommandPrimitive.List>
      )}
    </CommandPrimitive>
  )
}
