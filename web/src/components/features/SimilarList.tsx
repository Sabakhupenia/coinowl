import { toast } from 'sonner'
import { coinBy, feats, corr, similarTo } from '@/lib/mock'
import { fmtPct } from '@/lib/format'
import { useStore } from '@/lib/store'
import { useT } from '@/lib/i18n'
import { Overlay } from '@/components/charts/Sparkline'
import { CoinIcon } from '@/components/ui-bits'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'

export function SimilarList({ base, onCompare }: { base: string; onCompare: (a: string, b: string) => void }) {
  const { t } = useT()
  const wl = useStore(s => s.watchlist)
  const rows = similarTo(base)
  return (
    <div className="flex flex-col">
      {rows.map((r, i) => (
        <div key={r.c.sym} className="grid grid-cols-[30px_minmax(120px,1fr)_100px_auto] items-center gap-3 border-b border-border py-3 last:border-0 md:grid-cols-[30px_minmax(150px,1.2fr)_120px_160px_minmax(0,1.6fr)_auto] md:gap-4">
          <span className="font-mono text-xs font-bold text-muted-foreground">{String(i + 1).padStart(2, '0')}</span>
          <div className="flex items-center gap-2.5"><CoinIcon sym={r.c.sym} /><div><b className="block text-[13px]">{r.c.sym}</b><span className="block text-[11px] leading-tight text-muted-foreground">{r.c.name}</span></div></div>
          <div className="text-[11px] text-muted-foreground"><b className="mb-1 block text-[17px] font-extrabold tracking-tight text-foreground">{r.score.toFixed(2)}</b><Progress value={r.score * 100} className="h-1.5 bg-gold-soft [&>div]:bg-gold" />{t('sim.similarity')}</div>
          <div className="hidden md:block"><Overlay a={r.fb.d} b={r.f.d} /></div>
          <div className="hidden flex-wrap gap-1 md:flex">{[['ρ', r.rho.toFixed(2)], ['vol', (r.f.vol * 100).toFixed(1) + '%'], ['dd', (r.f.dd * 100).toFixed(1) + '%'], ['30d', fmtPct(r.f.ret * 100)], ['', r.f.tier]].map(([k, v]) => <span key={k + v} className="whitespace-nowrap rounded-md border border-border bg-sunken px-1.5 py-0.5 font-mono text-[11px] font-semibold text-secondary-foreground">{k && <em className="mr-1 not-italic text-muted-foreground">{k}</em>}{v}</span>)}</div>
          <Button size="sm" variant="outline" onClick={() => wl.some(c => c.sym === r.c.sym) ? onCompare(base, r.c.sym) : toast(t('sim.notOnList', { s: r.c.sym }))}>{t('c.compare')}</Button>
        </div>
      ))}
    </div>
  )
}

export function FeatureVector({ sym }: { sym: string }) {
  const { t } = useT()
  const c = coinBy(sym)!; const f = feats(c); const btc = coinBy('BTC')!
  const rhoB = sym === 'BTC' ? 1 : corr(feats(btc).r, f.r)
  const rows: [string, number | string, string, number | null][] = [['30-day return', f.ret * 100, '%', 60], ['Daily volatility', f.vol * 100, '%', 6], ['Max drawdown', f.dd * 100, '%', -40], ['Momentum (2nd half vs 1st)', f.mom * 100, '%', 30], ['Correlation to BTC', rhoB, '', 1], ['Cap tier', f.tier, '', null]]
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map(([k, v, u, max]) => (
        <div key={k} className="grid grid-cols-[150px_minmax(0,1fr)_64px] items-center gap-3 text-xs">
          <span className="font-semibold text-secondary-foreground">{k}</span>
          <div className="h-2 overflow-hidden rounded-full bg-sunken"><i className="block h-full rounded-full" style={{ background: 'var(--gold-grad)', width: (max === null ? ({ Mega: 100, Large: 66, Mid: 33 } as Record<string, number>)[v as string] : Math.min(100, Math.abs(v as number) / Math.abs(max) * 100)) + '%' }} /></div>
          <span className="text-right font-mono text-secondary-foreground tnum">{typeof v === 'number' ? (u === '%' ? fmtPct(v) : v.toFixed(2)) : v}</span>
        </div>
      ))}
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('sim.note')}</p>
    </div>
  )
}
