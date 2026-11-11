import { toast } from 'sonner'
import { useStore } from '@/lib/store'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Eyebrow, Section } from '@/components/ui-bits'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'


export default function PlanPage() {
  const { t } = useT()
  const q = useStore(s => s.quota)
  const ROWS = t('plan.rows').split(';').map(r => r.split('|'))
  return (
    <div className="flex flex-col gap-4">
      <Section title={t('plan.window')} hint={t('plan.resets')}>
        <div className="mb-2 flex items-baseline gap-2.5"><b className="text-2xl font-extrabold tracking-tight tnum">{q.used} / {q.limit}</b><span className="text-xs text-muted-foreground">{t('plan.msgs')}</span></div>
        <Progress value={q.used / q.limit * 100} className="h-2 bg-gold-soft [&>div]:bg-gold" />
      </Section>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card-premium flex flex-col gap-3 p-6"><Eyebrow>{t('plan.current')}</Eyebrow><h2 className="text-lg font-bold">{t('plan.free')}</h2><div className="text-[38px] font-extrabold tracking-tighter">$0<small className="text-[13px] font-semibold tracking-normal text-muted-foreground"> {t('plan.forever')}</small></div>
          <ul className="flex flex-col gap-1.5 text-[13px] text-secondary-foreground">{t('plan.freeList').split('|').map(x => <li key={x}><span className="mr-2 text-gold">–</span>{x}</li>)}</ul><Button variant="outline" disabled>{t('plan.onFree')}</Button></div>
        <div className={cn('flex flex-col gap-3 rounded-[18px] p-6')} style={{ border: '1px solid transparent', background: 'linear-gradient(160deg,var(--raised),var(--card)) padding-box,linear-gradient(135deg,rgba(212,175,55,.75),rgba(212,175,55,.08) 55%,rgba(212,175,55,.4)) border-box', boxShadow: 'var(--gold-glow), var(--shadow-1)' }}>
          <Eyebrow className="text-gold-ink">{t('plan.pro')}</Eyebrow><h2 className="text-lg font-bold">Pro</h2><div className="text-[38px] font-extrabold tracking-tighter">$6.99<small className="text-[13px] font-semibold tracking-normal text-muted-foreground"> {t('plan.month')}</small></div>
          <ul className="flex flex-col gap-1.5 text-[13px] text-secondary-foreground">{t('plan.proList').split('|').map(x => <li key={x}><span className="mr-2 text-gold">–</span>{x}</li>)}</ul><Button className="btn-gold border-0 font-bold" onClick={() => document.getElementById('pay')?.scrollIntoView({ behavior: 'smooth' })}>{t('plan.upgrade')}</Button></div>
      </div>
      <div id="pay"><Section title={t('plan.pay')} hint={t('plan.payHint')}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {[[t('plan.stars'), t('plan.starsD'), t('plan.openTg'), () => toast(t('toast.stars')), true], [t('plan.ton'), t('plan.tonD'), t('plan.wallet'), () => toast(t('toast.ton')), true], [t('plan.card'), t('plan.cardD'), t('plan.soon'), () => {}, false]].map(([b, p, l, fn, on]) => (
            <div key={b as string} className="flex flex-col gap-2 rounded-xl border border-border bg-sunken p-4 shadow-inner"><b className="text-sm">{b as string}</b><p className="flex-1 text-xs leading-relaxed text-secondary-foreground">{p as string}</p><Button variant="outline" disabled={!on} onClick={fn as () => void}>{l as string}</Button></div>))}
        </div>
      </Section></div>
      <Section title={t('plan.compare')}>
        <Table className="text-[13px]"><TableHeader><TableRow><TableHead>{t('plan.limit')}</TableHead><TableHead className="text-right">{t('plan.free')}</TableHead><TableHead className="text-right">Pro</TableHead></TableRow></TableHeader>
          <TableBody>{ROWS.map(r => <TableRow key={r[0]}><TableCell className="text-secondary-foreground">{r[0]}</TableCell><TableCell className="text-right font-mono tnum">{r[1]}</TableCell><TableCell className="text-right font-mono font-semibold tnum">{r[2]}</TableCell></TableRow>)}</TableBody></Table>
      </Section>
    </div>
  )
}
