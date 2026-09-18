import { useState } from 'react'
import { toast } from 'sonner'
import { coinBy, UNIVERSE } from '@/lib/mock'
import { fmtPct, fmtUSD } from '@/lib/format'
import { alerts, useStore, type Alert } from '@/lib/store'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'

export function undoToast(msg: string, undo: () => void, undoLabel: string) { toast(msg, { action: { label: undoLabel, onClick: undo }, duration: 6000 }) }

export function AlertRow({ a }: { a: Alert }) {
  const { t } = useT()
  const c = coinBy(a.sym)!
  const dist = (a.price / c.price - 1) * 100
  const prog = Math.max(0, Math.min(100, 100 - Math.abs(dist) * 4))
  return (
    <div className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-3.5 border-b border-border py-3 last:border-0 md:grid-cols-[44px_minmax(0,1.5fr)_minmax(0,1.6fr)_auto_auto]">
      <div className={cn('grid size-[42px] place-items-center rounded-xl border border-border bg-raised text-[17px]', a.state === 'armed' && 'border-gold/25 bg-gold-soft', a.state === 'triggered' && 'bg-[var(--copper-soft)]')}>{a.state === 'triggered' ? '✓' : a.state === 'paused' ? '⏸' : '🔔'}</div>
      <div>
        <b className="block text-sm">{a.sym} {a.dir} {fmtUSD(a.price)}</b>
        <span className="block text-xs text-muted-foreground">{a.state === 'triggered' ? `${t('al.fired')} ${a.fired} · ${t('al.off')}` : `${a.when} · ${a.rec ? t('al.rec') : t('al.oneShot')} · ${t('al.now')} ${fmtUSD(c.price)}`}</span>
        {a.state !== 'triggered' && <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground"><span>{fmtPct(dist)} {t('al.away')}</span><div className="h-1.5 w-40 overflow-hidden rounded-full bg-sunken"><i className="block h-full rounded-full bg-gold" style={{ width: prog + '%' }} /></div></div>}
      </div>
      <div className="col-span-3 col-start-2 border-l-2 border-gold pl-2.5 text-[13.5px] leading-snug text-secondary-foreground md:col-span-1 md:col-start-auto"><span className="display-italic">“{a.said}”</span><em className="mt-0.5 block text-[11px] not-italic text-muted-foreground">{t('al.words')}</em></div>
      <Badge variant="outline" className={cn('hidden md:inline-flex', a.state === 'armed' && 'border-gold/25 bg-gold-soft text-gold-ink', a.state === 'triggered' && 'bg-[var(--copper-soft)] text-[var(--copper-ink)]')}>{a.state === 'armed' ? t('c.armed') : a.state === 'paused' ? t('c.paused') : t('c.triggered')}</Badge>
      <div className="col-start-3 row-start-1 flex gap-1.5 md:col-start-auto md:row-start-auto">
        {a.state === 'armed' && <Button size="sm" variant="ghost" onClick={() => { const undo = alerts.patch(a.id, { state: 'paused' }); undoToast(t('toast.paused'), undo, t('c.undo')) }}>{t('c.pause')}</Button>}
        {a.state === 'paused' && <Button size="sm" variant="ghost" onClick={() => alerts.patch(a.id, { state: 'armed' })}>{t('c.resume')}</Button>}
        {a.state === 'triggered' && <Button size="sm" variant="ghost" onClick={() => alerts.patch(a.id, { state: 'armed', fired: undefined })}>{t('c.rearm')}</Button>}
        <Button size="sm" variant="ghost" className="text-[var(--copper-ink)]" onClick={() => { const undo = alerts.remove(a.id); undoToast(t('toast.deleted'), undo, t('c.undo')) }}>{t('c.delete')}</Button>
      </div>
    </div>
  )
}

export function AlertForm({ defaultSym }: { defaultSym?: string }) {
  const { t } = useT()
  const wl = useStore(s => s.watchlist)
  const [sym, setSym] = useState(defaultSym ?? 'BTC'); const [dir, setDir] = useState<'above' | 'below'>('above'); const [price, setPrice] = useState(''); const [rec, setRec] = useState(false)
  const arm = () => {
    const p = parseFloat(price.replace(/[,k]/gi, m => (m.toLowerCase() === 'k' ? '000' : '')))
    if (!p) { toast('Enter a price first'); return }
    const undo = alerts.add({ sym, dir, price: p, rec, state: 'armed', said: `${sym} ${dir} ${p} (set here)`, when: 'today' })
    setPrice(''); undoToast(t('toast.armed', { s: sym, d: dir, p: fmtUSD(p) }), undo, t('c.undo'))
  }
  const options = [...wl, ...UNIVERSE.filter(c => !wl.some(w => w.sym === c.sym))]
  return (
    <div className="grid grid-cols-2 items-end gap-2.5 rounded-xl border border-border bg-sunken p-4 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
      <div className="grid gap-1.5"><Label>{t('c.coin')}</Label><Select value={sym} onValueChange={setSym}><SelectTrigger className="bg-card"><SelectValue /></SelectTrigger><SelectContent>{options.map(c => <SelectItem key={c.sym} value={c.sym}>{c.sym} · {c.name}</SelectItem>)}</SelectContent></Select></div>
      <div className="grid gap-1.5"><Label>{t('al.when')}</Label><Select value={dir} onValueChange={v => setDir(v as 'above' | 'below')}><SelectTrigger className="bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="above">{t('al.above')}</SelectItem><SelectItem value="below">{t('al.below')}</SelectItem></SelectContent></Select></div>
      <div className="grid gap-1.5"><Label htmlFor="af-price">USD</Label><Input id="af-price" value={price} onChange={e => setPrice(e.target.value)} placeholder="120000" inputMode="decimal" className="bg-card font-mono" /></div>
      <label className="flex h-9 items-center gap-2 text-xs font-semibold"><Checkbox checked={rec} onCheckedChange={v => setRec(v === true)} />{t('al.repeat')}</label>
      <Button className="btn-gold border-0 font-bold" onClick={arm}>{t('al.arm')}</Button>
    </div>
  )
}
