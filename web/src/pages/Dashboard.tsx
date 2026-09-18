import { useMemo } from 'react'
import { FNG, MARKET, MOVERS, pct, pts, coinBy, type Coin } from '@/lib/mock'
import { fmtDate, fmtPct, fmtUSD } from '@/lib/format'
import { useStore } from '@/lib/store'
import { setView, toggleHidden, useView } from '@/lib/view'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { PriceChart } from '@/components/charts/PriceChart'
import { Sparkline } from '@/components/charts/Sparkline'
import { CoinIcon, Delta, RangeTabs, Section } from '@/components/ui-bits'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)']

export const fngWord = (v: number, t: (k: 'fng.0' | 'fng.1' | 'fng.2' | 'fng.3' | 'fng.4') => string) => v < 25 ? t('fng.0') : v < 45 ? t('fng.1') : v < 56 ? t('fng.2') : v < 76 ? t('fng.3') : t('fng.4')
export function FngTile({ compact }: { compact?: boolean }) {
  const { t } = useT(); const v = FNG.today
  const word = fngWord(v, t)
  return (
    <div className={cn('card-premium flex flex-col gap-1.5 p-5', !compact && 'md:col-span-2 xl:col-span-1', 'border-gold/20')} style={{ boxShadow: 'inset 0 1px 0 var(--edge), var(--shadow-1), var(--gold-glow)' }}>
      <div className="text-xs font-semibold text-secondary-foreground">{t('dash.fng')}</div>
      <div className="flex items-end gap-4"><div className="gold-text text-6xl font-extrabold leading-none tracking-tighter">{v}</div><div className="display-italic pb-1.5 text-[21px] font-bold text-gold-ink">{word}</div></div>
      <div className="relative mt-3 flex h-2.5 gap-0.5 rounded-full bg-sunken shadow-inner">
        {[['var(--copper)', 1], ['var(--copper)', 0.55], ['var(--muted-foreground)', 0.6], ['var(--gold)', 0.55], ['var(--gold)', 1]].map(([c, o], i) => <i key={i} className={cn('flex-1', i === 0 && 'rounded-l-full', i === 4 && 'rounded-r-full')} style={{ background: c as string, opacity: o as number }} />)}
        <span className="absolute -top-1.5 size-[22px] -translate-x-1/2 rounded-full border-[3px] border-card" style={{ left: v + '%', background: 'var(--gold-grad)', boxShadow: '0 0 0 1px rgba(212,175,55,.6), var(--gold-glow)' }} />
      </div>
      <div className="mt-2 flex justify-between text-[10.5px] font-bold text-muted-foreground"><span>{t('fng.0')}</span><span className="hidden 2xl:inline">{t('fng.1')}</span><span>{t('fng.2')}</span><span className="hidden 2xl:inline">{t('fng.3')}</span><span>{t('fng.4')}</span></div>
      <div className="mt-2 flex gap-5 text-xs text-secondary-foreground"><span>{t('dash.yesterday')} <b className="text-foreground">{FNG.yesterday}</b></span><span>{t('dash.7d')} <b className="text-foreground">{FNG.week}</b></span><span>{t('dash.30d')} <b className="text-foreground">{FNG.month}</b></span></div>
    </div>
  )
}

export function Movers({ range }: { range: import('@/lib/mock').RangeKey }) {
  const { t } = useT(); const M = MOVERS[range]
  const List = ({ rows, color }: { rows: [string, number][]; color: string }) => { const max = Math.max(...rows.map(r => Math.abs(r[1]))); return <div>{rows.map(([s, v]) => <div key={s} className="grid grid-cols-[64px_minmax(0,1fr)_62px] items-center gap-2.5 py-1.5 text-[13px]"><span className="font-bold">{s}</span><div className="h-3.5"><div className="h-3.5 rounded-r-[4px]" style={{ width: Math.abs(v) / max * 100 + '%', background: color, boxShadow: 'inset 0 1px 0 rgba(255,255,255,.18)' }} /></div><span className={cn('text-right font-mono text-xs font-bold', v >= 0 ? 't-up' : 't-down')}>{fmtPct(v)}</span></div>)}</div> }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Section title={t('dash.gainers')} hint={`${t('dash.whole')} · ${range}`}><List rows={M.g} color="var(--gold)" /></Section>
      <Section title={t('dash.losers')} hint={`${t('dash.whole')} · ${range}`}><List rows={M.l} color="var(--copper)" /></Section>
    </div>
  )
}

export default function Dashboard() {
  const { t } = useT()
  const wl = useStore(s => s.watchlist); const allAlerts = useStore(s => s.alerts); const alertsArmed = allAlerts.filter(a => a.state === 'armed').length
  const armedSyms = useMemo(() => new Set(allAlerts.filter(a => a.state === 'armed').map(a => a.sym)), [allAlerts])
  const view = useView()
  const coin = coinBy(view.coin) ?? wl[0]
  const chartCoins = useMemo<Coin[]>(() => view.mode === 'compare' ? view.compare.map(s => coinBy(s)!).filter(Boolean) : [coin], [view.mode, view.compare, coin])
  const hidden = useMemo(() => new Set(view.hidden), [view.hidden])
  const chs = wl.map(c => pct(c, view.range)); const avg = chs.reduce((a, b) => a + b, 0) / chs.length; const up = chs.filter(v => v >= 0).length
  const onRow = (c: Coin) => { if (view.mode === 'compare') { if (!view.compare.includes(c.sym)) setView({ compare: [...view.compare.slice(-4), c.sym], coin: c.sym }) } else setView({ coin: c.sym }) }
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="eyebrow">{t('c.range')}</span><RangeTabs value={view.range} onChange={r => setView({ range: r })} />
        <span className="eyebrow">{t('c.chart')}</span>
        <ToggleGroup type="single" value={view.mode} onValueChange={v => v && setView({ mode: v as typeof view.mode })} className="rounded-[11px] border border-border bg-sunken p-[3px]">
          {(['single', 'compare', 'table'] as const).map(m => <ToggleGroupItem key={m} value={m} className="h-8 rounded-lg px-3 text-xs font-bold text-secondary-foreground data-[state=on]:bg-card data-[state=on]:text-gold-ink data-[state=on]:shadow">{m === 'single' ? t('c.price') : m === 'compare' ? t('c.compare') : t('c.table')}</ToggleGroupItem>)}
        </ToggleGroup>
        <div className="ml-auto hidden gap-5 lg:flex">{[[t('dash.cap'), MARKET.cap], [t('dash.vol'), MARKET.vol], [t('dash.dom'), MARKET.dom]].map(([k, v]) => <span key={k} className="flex flex-col leading-tight"><em className="text-[10px] font-bold uppercase tracking-widest not-italic text-muted-foreground">{k}</em><b className="font-mono text-[13px] font-medium tnum">{v}</b></span>)}</div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr_1fr]">
        <FngTile />
        <div className="card-premium flex flex-col gap-1.5 p-5"><div className="text-xs font-semibold text-secondary-foreground">{t('dash.wl')} · {view.range}</div><div className={cn('text-[32px] font-bold leading-none tracking-tighter', avg >= 0 ? 't-up' : 't-down')}>{fmtPct(avg)}</div><div className="text-xs font-semibold text-muted-foreground">{up} {t('dash.coinsUp', { n: wl.length })}</div></div>
        <div className="card-premium flex flex-col gap-1.5 p-5"><div className="text-xs font-semibold text-secondary-foreground">{t('dash.armed')}</div><div className="text-[32px] font-bold leading-none tracking-tighter">{alertsArmed}</div><div className="text-xs font-semibold text-muted-foreground">{t('dash.triggered')}</div></div>
        <div className="card-premium flex flex-col gap-1.5 p-5"><div className="text-xs font-semibold text-secondary-foreground">{t('dash.next')}</div><div className="pt-1 text-[22px] font-bold leading-none tracking-tight">{t('dash.tomorrow')}</div><div className="text-xs font-semibold text-muted-foreground">{t('dash.nextSub')}</div></div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[5fr_7fr]">
        <Section title={t('dash.wl')} hint={`${wl.length} / 10 · ${t('dash.wlHint')}`} bodyClass="overflow-x-auto">
          <Table className="text-[13px]">
            <TableHeader><TableRow className="hover:bg-transparent"><TableHead className="pl-1.5">{t('c.coin')}</TableHead><TableHead className="text-right">{t('c.price')}</TableHead>{(['24h', '7d', '30d'] as const).map(r => <TableHead key={r} className={cn('text-right', r === view.range && 'text-gold-ink')}>{r}</TableHead>)}<TableHead className="hidden text-right sm:table-cell">{t('c.trend')}</TableHead></TableRow></TableHeader>
            <TableBody>
              {wl.map(c => { const s7 = pts(c, '7d').map(p => p.p); const sel = view.mode === 'compare' ? view.compare.includes(c.sym) : c.sym === coin.sym; return (
                <TableRow key={c.sym} onClick={() => onRow(c)} className={cn('cursor-pointer', sel && 'bg-gold-soft hover:bg-gold-soft')}>
                  <TableCell className={cn('pl-1.5', sel && 'shadow-[inset_3px_0_0_var(--gold)]')}><div className="flex items-center gap-2.5"><CoinIcon sym={c.sym} /><div><b className="block text-[13px]">{c.sym}{armedSyms.has(c.sym) && <span className="ml-1.5 text-xs text-gold-ink" title="Alert armed">🔔</span>}</b><span className="block text-[11px] leading-tight text-muted-foreground">{c.name}</span></div></div></TableCell>
                  <TableCell className="text-right font-mono tnum">{fmtUSD(c.price)}</TableCell>
                  {(['24h', '7d', '30d'] as const).map(r => { const v = pct(c, r); return <TableCell key={r} className={cn('text-right font-mono font-semibold tnum', v >= 0 ? 't-up' : 't-down', r === view.range && 'bg-gold-soft/50')}>{fmtPct(v)}</TableCell> })}
                  <TableCell className="hidden text-right sm:table-cell"><Sparkline series={s7.filter((_, i) => i % 4 === 0)} neg={s7[s7.length - 1] < s7[0]} /></TableCell>
                </TableRow>) })}
            </TableBody>
          </Table>
        </Section>
        <Section title={view.mode === 'compare' ? `${t('c.compare')} · %` : coin.name} hint={view.mode === 'compare' ? `${view.compare.join(' · ')} · ${t('c.indexed')}` : `${coin.sym} · ${view.range}`} right={<span className="text-xs text-muted-foreground">{t('c.hover')}</span>} className="flex flex-col">
          {view.mode !== 'compare' && <div className="mb-3 flex flex-wrap items-baseline gap-3.5"><span className="text-[34px] font-extrabold tracking-tighter tnum">{fmtUSD(coin.price)}</span><Delta v={pct(coin, view.range)} suffix={view.range} className="text-sm" /><span className="ml-auto text-[11.5px] text-muted-foreground">{t('c.dataSource')}</span></div>}
          {view.mode === 'compare' && <div className="mb-3 flex flex-wrap gap-1.5">{view.compare.map((s, i) => { const c = coinBy(s)!; return <button key={s} onClick={() => toggleHidden(s)} className={cn('inline-flex items-center gap-1.5 rounded-full border border-input bg-card px-2.5 py-1 text-xs font-semibold', hidden.has(s) && 'opacity-45')}><i className="inline-block h-[3px] w-3.5 rounded" style={{ background: SERIES[i] }} />{s} <Delta v={pct(c, view.range)} /></button> })}<span className="self-center text-xs text-muted-foreground">· {t('dash.wlHint')} · {t('coin.max5')}</span></div>}
          {view.mode === 'table'
            ? <div className="max-h-[340px] overflow-auto"><Table className="text-xs"><TableHeader><TableRow><TableHead>{t('c.time')}</TableHead><TableHead className="text-right">{t('c.price')}</TableHead><TableHead className="text-right">{t('c.vsStart')}</TableHead></TableRow></TableHeader><TableBody>{(() => { const p = pts(coin, view.range); const step = Math.max(1, Math.floor(p.length / 40)); const rows = []; for (let i = p.length - 1; i >= 0; i -= step) { const v = (p[i].p / p[0].p - 1) * 100; rows.push(<TableRow key={i}><TableCell>{fmtDate(p[i].t, view.range)}</TableCell><TableCell className="text-right font-mono tnum">{fmtUSD(p[i].p)}</TableCell><TableCell className={cn('text-right font-mono tnum', v >= 0 ? 't-up' : 't-down')}>{fmtPct(v)}</TableCell></TableRow>) } return rows })()}</TableBody></Table></div>
            : <div className="min-h-[340px] flex-1"><PriceChart coins={chartCoins} range={view.range} height={360} hidden={hidden} /></div>}
        </Section>
      </div>

      <Movers range={view.range} />

      <Section title={t('dash.glance')} hint={t('dash.glanceHint')}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {wl.map(c => { const s = pts(c, view.range).map(p => p.p); const v = (s[s.length - 1] / s[0] - 1) * 100; const step = Math.max(1, Math.floor(s.length / 40)); return <div key={c.sym} className="flex flex-col gap-1 rounded-xl border border-border bg-sunken px-3 pb-1.5 pt-2.5 shadow-inner"><div className="flex justify-between text-xs font-bold"><b>{c.sym}</b><span className={cn('font-mono', v >= 0 ? 't-up' : 't-down')}>{fmtPct(v)}</span></div><Sparkline series={s.filter((_, i) => i % step === 0)} w={120} h={36} neg={v < 0} /></div> })}
        </div>
      </Section>
    </div>
  )
}

