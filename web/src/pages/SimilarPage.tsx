import { useState } from 'react'
import { UNIVERSE } from '@/lib/mock'
import { useT } from '@/lib/i18n'
import { navigate } from '@/lib/router'
import { compareWith } from '@/lib/view'
import { FeatureVector, SimilarList } from '@/components/features/SimilarList'
import { Pipeline } from '@/pages/NewsPage'
import { Section } from '@/components/ui-bits'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export const SIM_STEPS: [string, string][] = [
  ['Bootstrap the coins table', 'Top ~500 coins by market cap from CoinGecko coin-detail: id, categories, cap tier, 90 days of daily prices and volumes.'],
  ['Build a feature vector per coin', 'Shape of the normalized 30d return series, realized volatility, max drawdown, momentum, cap tier, category one-hots. Standardized, then stored as a pgvector column.'],
  ['Refresh on a cron', 'Hourly for prices, daily for categories. Batched so the free CoinGecko tier survives.'],
  ['Query', 'ORDER BY features <=> (SELECT features FROM coins WHERE id = $1) LIMIT 8. The chat tool find_similar(symbol) runs the same query, so "what moves like TON?" works in Telegram too.'],
]

export default function SimilarPage() {
  const { t } = useT()
  const [base, setBase] = useState('BTC')
  const onCompare = (a: string, b: string) => { compareWith(a, b); navigate('dashboard') }
  return (
    <div className="flex flex-col gap-4">
      <Section title={<span className="flex flex-wrap items-center gap-3">{t('sim.title')}<Select value={base} onValueChange={setBase}><SelectTrigger className="h-8 w-auto bg-sunken"><SelectValue /></SelectTrigger><SelectContent>{UNIVERSE.map(c => <SelectItem key={c.sym} value={c.sym}>{c.sym} · {c.name}</SelectItem>)}</SelectContent></Select></span>} hint={`${t('sim.hint')} · ${UNIVERSE.length}-coin sample universe`}>
        <SimilarList base={base} onCompare={onCompare} />
      </Section>
      <div className="grid items-start grid-cols-1 gap-4 xl:grid-cols-2">
        <Section title={t('sim.how')} hint="/similar · v0.9"><Pipeline steps={SIM_STEPS} /></Section>
        <Section title={`${t('sim.fv')} · ${base}`} hint={t('sim.fvHint')}><FeatureVector sym={base} /></Section>
      </div>
    </div>
  )
}
