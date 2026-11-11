import { useState } from 'react'
import { UNIVERSE } from '@/lib/mock'
import { useT } from '@/lib/i18n'
import { navigate } from '@/lib/router'
import { compareWith } from '@/lib/view'
import { FeatureVector, SimilarList } from '@/components/features/SimilarList'
import { Pipeline } from '@/pages/NewsPage'
import { SAMPLE } from '@/lib/sample'
import { Section } from '@/components/ui-bits'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export default function SimilarPage() {
  const { t, lang } = useT()
  const [base, setBase] = useState('BTC')
  const onCompare = (a: string, b: string) => { compareWith(a, b); navigate('dashboard') }
  return (
    <div className="flex flex-col gap-4">
      <Section title={<span className="flex flex-wrap items-center gap-3">{t('sim.title')}<Select value={base} onValueChange={setBase}><SelectTrigger className="h-8 w-auto bg-sunken"><SelectValue /></SelectTrigger><SelectContent>{UNIVERSE.map(c => <SelectItem key={c.sym} value={c.sym}>{c.sym} · {c.name}</SelectItem>)}</SelectContent></Select></span>} hint={`${t('sim.hint')} · ${t('sim.universe', { n: UNIVERSE.length })}`}>
        <SimilarList base={base} onCompare={onCompare} />
      </Section>
      <div className="grid items-start grid-cols-1 gap-4 xl:grid-cols-2">
        <Section title={t('sim.how')} hint={t('sim.v')}><Pipeline steps={SAMPLE[lang].simSteps} /></Section>
        <Section title={`${t('sim.fv')} · ${base}`} hint={t('sim.fvHint')}><FeatureVector sym={base} /></Section>
      </div>
    </div>
  )
}
