import { useState } from 'react'
import { FEED } from '@/lib/mock'
import { send } from '@/lib/chat'
import { useT } from '@/lib/i18n'
import { navigate } from '@/lib/router'
import { cn } from '@/lib/utils'
import { GroundedAnswer } from '@/components/features/GroundedAnswer'
import { Section } from '@/components/ui-bits'
import { Button } from '@/components/ui/button'

export function Pipeline({ steps }: { steps: [string, string][] }) {
  return (
    <ol className="ml-3 flex flex-col">
      {steps.map(([b, s], i) => (
        <li key={i} className={cn('relative border-l border-border py-2.5 pb-3 pl-9', i === steps.length - 1 && 'border-l-transparent')}>
          <span className="absolute -left-[13px] top-2.5 grid size-[26px] place-items-center rounded-full text-[11.5px] font-extrabold text-[#1b1400] ring-[3px] ring-card" style={{ background: 'var(--gold-grad)' }}>{i + 1}</span>
          <b className="block text-[13.5px]">{b}</b><span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{s}</span>
        </li>
      ))}
    </ol>
  )
}
export const NEWS_STEPS: [string, string][] = [
  ['Ingest', 'CoinDesk RSS every 15 min → article → ~400-token chunks → knowledge_chunks with gemini-embedding-001 (768d). Tagged by coin when a ticker or name appears.'],
  ['Embed the question', 'One embedding call. Same model and dimension as your chat memory, so it shares the pgvector index type.'],
  ['Retrieve', 'Cosine search, top 4 chunks, recency-boosted (last 72h ×1.3). ~40 ms on 1,932 chunks.'],
  ['Write with citations only', 'gpt-5.4-mini gets the 4 chunks and may cite [1]–[4] and nothing else. A sentence without a source is dropped before you see it.'],
  ['Guardrail', 'Same regex + judge as chat: reporting only. "Why did it drop" is answerable; "will it recover" is refused.'],
]

export function Feed({ only }: { only?: string }) {
  const { t } = useT()
  const [tag, setTag] = useState(only ?? 'All')
  const rows = FEED.filter(a => tag === 'All' || a.tags.includes(tag))
  return (
    <>
      {!only && <div className="mb-3 flex flex-wrap gap-1.5">{['All', 'BTC', 'ETH', 'SOL', 'TON', 'XRP', 'LINK'].map(x => <button key={x} onClick={() => setTag(x)} className={cn('rounded-full border border-input px-2.5 py-1 text-xs font-semibold', tag === x && 'border-gold/30 bg-gold-soft text-gold-ink')}>{x}</button>)}</div>}
      <div className="mb-2 flex flex-wrap gap-5">{[['Last ingest', '12 min ago'], ['Articles today', '48'], ['Chunks indexed', '1,932'], ['Coins tagged', '63']].map(([k, v]) => <span key={k} className="flex flex-col leading-tight"><em className="text-[10px] font-bold uppercase tracking-widest not-italic text-muted-foreground">{k}</em><b className="text-[15px]">{v}</b></span>)}</div>
      <div className="flex flex-col">
        {rows.map(a => (
          <div key={a.t} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3.5 border-b border-border py-3 last:border-0">
            <div><b className="block text-sm leading-snug">{a.t}</b><div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">{a.tags.map(x => <span key={x} className="rounded-md bg-gold-soft px-1.5 py-0.5 font-mono text-[10.5px] font-bold text-gold-ink">{x}</span>)}<span>CoinDesk · {a.w}</span></div><p className="mt-1 text-[13px] leading-relaxed text-secondary-foreground">{a.p}</p></div>
            <Button size="sm" variant="outline" onClick={() => { send('What was reported here: ' + a.t); navigate('chat') }}>{t('news.askAbout')}</Button>
          </div>
        ))}
        {!rows.length && <p className="text-sm text-muted-foreground">No articles tagged {tag} in the last 7 days.</p>}
      </div>
    </>
  )
}

export default function NewsPage() {
  const { t } = useT()
  return (
    <div className="flex flex-col gap-4">
      <div className="grid items-start grid-cols-1 gap-4 xl:grid-cols-[7fr_5fr]">
        <Section title={t('news.ask')} hint={t('news.askHint')}><GroundedAnswer initial="Why did SOL drop yesterday?" /></Section>
        <Section title={t('news.how')} hint="news RAG · v0.9"><Pipeline steps={NEWS_STEPS} /></Section>
      </div>
      <Section title={t('news.latest')} hint="sample articles · CoinDesk RSS"><Feed /></Section>
    </div>
  )
}
