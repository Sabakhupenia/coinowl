import { useMemo } from 'react'
import { toast } from 'sonner'
import { coinBy, pct, pts, type Coin } from '@/lib/mock'
import { fmtPct, fmtUSD } from '@/lib/format'
import { useStore } from '@/lib/store'
import { compareWith, setView, toggleHidden, useView } from '@/lib/view'
import { navigate } from '@/lib/router'
import { send } from '@/lib/chat'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { PriceChart } from '@/components/charts/PriceChart'
import { Sparkline } from '@/components/charts/Sparkline'
import { CoinIcon, Delta, RangeTabs, Tag } from '@/components/ui-bits'
import { GroundedAnswer } from '@/components/features/GroundedAnswer'
import { SimilarList } from '@/components/features/SimilarList'
import { AlertForm, AlertRow } from '@/components/features/Alerts'
import { Feed } from '@/pages/NewsPage'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)']

/** Advanced-mode workspace: everything about one coin on one screen (chart · stats · overview/news/similar/alerts). */
export function CoinView({ sym, tab }: { sym: string; tab: string }) {
  const { t, lang } = useT()
  const wl = useStore(s => s.watchlist); const alerts = useStore(s => s.alerts)
  const view = useView()
  const c = coinBy(sym) ?? wl[0]
  const compare = view.mode === 'compare'
  const chartCoins = useMemo<Coin[]>(() => compare ? view.compare.map(s => coinBy(s)!).filter(Boolean) : [c], [compare, view.compare, c])
  const hidden = useMemo(() => new Set(view.hidden), [view.hidden])
  const p = pts(c, view.range).map(q => q.p); const lo = Math.min(...p), hi = Math.max(...p), avg = p.reduce((a, b) => a + b, 0) / p.length
  const vr = pct(c, view.range)
  const mine = alerts.filter(a => a.sym === c.sym)
  const go = (tb: string) => navigate(`coin/${c.sym}/${tb}`)
  return (
    <div className="flex max-w-[1080px] flex-col gap-4">
      <div className="flex flex-wrap items-start gap-3">
        <div><h1 className="text-[22px] font-bold leading-tight">{c.name} <Tag className="align-middle">{c.sym}</Tag></h1><div className="text-sm text-muted-foreground">{wl.includes(c) ? t('coin.onList', { n: wl.indexOf(c) + 1 }) : t('coin.notOnList')}</div></div>
        <div className="ml-auto flex gap-2"><Button size="sm" variant="outline" onClick={() => go('alerts')}>{t('coin.setAlert')}</Button><Button size="sm" variant="outline" onClick={() => { send(t('coin.askQ', { s: c.sym })) }}>{t('coin.askAgent')}</Button></div>
      </div>
      <div className="flex flex-wrap items-baseline gap-3"><span className="text-[30px] font-bold tracking-tight tnum">{fmtUSD(c.price)}</span><Delta v={pct(c, '24h')} suffix="24h" /><Delta v={vr} suffix={view.range} /><span className="ml-auto text-xs text-muted-foreground">{t('c.updated')} · CoinGecko · {t('c.sample')}</span></div>
      <div className="flex flex-wrap items-center gap-4">
        <RangeTabs value={view.range} onChange={r => setView({ range: r })} />
        <span className="flex-1" />
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={compare} onCheckedChange={v => { const on = v === true; setView({ mode: on ? 'compare' : 'single', compare: on && !view.compare.includes(c.sym) ? [c.sym, ...view.compare].slice(0, 5) : view.compare }) }} />{t('c.compare')}</label>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={view.mode === 'table'} onCheckedChange={v => setView({ mode: v === true ? 'table' : 'single' })} />{t('c.table')}</label>
      </div>
      {compare && <div className="flex flex-wrap gap-x-4 gap-y-1.5">{wl.map(x => <label key={x.sym} className="flex items-center gap-1.5 text-sm"><Checkbox checked={view.compare.includes(x.sym)} onCheckedChange={v => { if (v === true) { if (view.compare.length >= 5) { toast(t('coin.max5')); return } setView({ compare: [...view.compare, x.sym], hidden: [] }) } else setView({ compare: view.compare.filter(s => s !== x.sym), hidden: [] }) }} />{x.sym}</label>)}</div>}
      {compare && <div className="flex flex-wrap gap-1.5">{view.compare.map((s, i) => <button key={s} onClick={() => toggleHidden(s)} className={cn('inline-flex items-center gap-1.5 rounded-full border border-input bg-card px-2.5 py-1 text-xs font-semibold', hidden.has(s) && 'opacity-45')}><i className="inline-block h-[3px] w-3.5 rounded" style={{ background: SERIES[i] }} />{s} <Delta v={pct(coinBy(s)!, view.range)} /></button>)}</div>}
      <div className="card-premium p-3">
        {view.mode === 'table'
          ? <div className="max-h-[320px] overflow-auto"><Table className="text-xs"><TableHeader><TableRow><TableHead>{t('c.time')}</TableHead><TableHead className="text-right">{t('c.price')}</TableHead><TableHead className="text-right">{t('c.vsStart')}</TableHead></TableRow></TableHeader><TableBody>{(() => { const P = pts(c, view.range); const step = Math.max(1, Math.floor(P.length / 40)); const rows = []; for (let i = P.length - 1; i >= 0; i -= step) { const v = (P[i].p / P[0].p - 1) * 100; rows.push(<TableRow key={i}><TableCell>{new Date(P[i].t).toLocaleString()}</TableCell><TableCell className="text-right font-mono tnum">{fmtUSD(P[i].p)}</TableCell><TableCell className={cn('text-right font-mono tnum', v >= 0 ? 't-up' : 't-down')}>{fmtPct(v)}</TableCell></TableRow>) } return rows })()}</TableBody></Table></div>
          : <PriceChart coins={chartCoins} range={view.range} height={320} hidden={hidden} />}
      </div>
      <div className="grid grid-cols-2 overflow-hidden rounded-[10px] border border-border bg-card md:grid-cols-5">
        {[[t('coin.low') + ' · ' + view.range, fmtUSD(lo), ''], [t('coin.high') + ' · ' + view.range, fmtUSD(hi), ''], [t('coin.change'), fmtPct(vr), vr >= 0 ? 't-up' : 't-down'], [t('coin.fromHigh'), fmtPct((c.price / hi - 1) * 100), 't-down'], [t('coin.avg'), fmtUSD(avg), '']].map(([k, v, cls]) => <div key={k} className="border-b border-r border-border px-4 py-3 last:border-r-0 md:border-b-0"><em className="block text-xs not-italic text-muted-foreground">{k}</em><b className={cn('mt-0.5 block text-[17px] tnum', cls)}>{v}</b></div>)}
      </div>
      <Tabs value={tab || 'overview'} onValueChange={go}>
        <TabsList className="h-auto w-full justify-start gap-0.5 rounded-none border-b border-border bg-transparent p-0">
          {[['overview', t('coin.overview')], ['news', t('coin.why')], ['similar', t('coin.similar')], ['alerts', `${t('nav.alerts')} ${mine.filter(a => a.state === 'armed').length || ''}`]].map(([k, l]) => <TabsTrigger key={k} value={k} className="-mb-px rounded-none border-b-2 border-transparent px-3.5 py-2 text-sm font-semibold text-muted-foreground shadow-none data-[state=active]:border-gold data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none">{l}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="overview" className="card-premium mt-3 p-5">
          <h2 className="mb-2.5 text-[15px] font-bold">{t('coin.ranked', { r: view.range })}</h2>
          <Table className="text-sm"><TableHeader><TableRow><TableHead>#</TableHead><TableHead>{t('c.coin')}</TableHead><TableHead className="text-right">{t('c.price')}</TableHead><TableHead className="text-right">{view.range}</TableHead><TableHead className="text-right">7d</TableHead></TableRow></TableHeader>
            <TableBody>{[...wl].sort((a, b) => pct(b, view.range) - pct(a, view.range)).map((x, i) => { const s7 = pts(x, '7d').map(q => q.p); return <TableRow key={x.sym} onClick={() => navigate('coin/' + x.sym)} className={cn('cursor-pointer', x.sym === c.sym && 'bg-gold-soft hover:bg-gold-soft')}><TableCell>{i + 1}</TableCell><TableCell><span className="flex items-center gap-2"><CoinIcon sym={x.sym} size={24} />{x.sym} · {x.name}</span></TableCell><TableCell className="text-right font-mono tnum">{fmtUSD(x.price)}</TableCell><TableCell className="text-right"><Delta v={pct(x, view.range)} /></TableCell><TableCell className="text-right"><Sparkline series={s7.filter((_, k) => k % 4 === 0)} w={70} h={20} neg={s7[s7.length - 1] < s7[0]} /></TableCell></TableRow> })}</TableBody></Table>
        </TabsContent>
        <TabsContent value="news" className="card-premium mt-3 p-5">
          <h2 className="mb-2.5 text-[15px] font-bold">{t('coin.grounded')} <span className="ml-2 text-xs font-medium text-muted-foreground">{t('coin.groundedHint')}</span></h2>
          <GroundedAnswer key={lang + c.sym} initial={t('news.qCoin', { s: c.sym })} />
          <h2 className="mb-2 mt-5 text-[15px] font-bold">{t('coin.articles', { s: c.sym })}</h2><Feed only={c.sym} />
        </TabsContent>
        <TabsContent value="similar" className="card-premium mt-3 p-5">
          <h2 className="mb-1 text-[15px] font-bold">{t('sim.title')} {c.sym} <span className="ml-2 text-xs font-medium text-muted-foreground">{t('sim.hint')} · {t('coin.simHint', { s: c.sym })}</span></h2>
          <SimilarList base={c.sym} onCompare={(a, b) => { compareWith(a, b); navigate('coin/' + a) }} />
          <p className="mt-3 text-xs text-muted-foreground">{t('sim.note')}</p>
        </TabsContent>
        <TabsContent value="alerts" className="card-premium mt-3 p-5">
          <h2 className="mb-2.5 text-[15px] font-bold">{t('al.new')} · {c.sym}</h2><AlertForm defaultSym={c.sym} />
          <h2 className="mb-1 mt-5 text-[15px] font-bold">{t('nav.alerts')} · {c.sym}</h2>
          {mine.length ? mine.map(a => <AlertRow key={a.id} a={a} />) : <p className="text-sm text-muted-foreground">{t('coin.noAlerts', { s: c.sym })}</p>}
        </TabsContent>
      </Tabs>
    </div>
  )
}
