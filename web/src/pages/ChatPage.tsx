import { useStore } from '@/lib/store'
import { useT } from '@/lib/i18n'
import { navigate } from '@/lib/router'
import { setView } from '@/lib/view'
import { Conversation, PromptInput, Suggestions } from '@/components/chat/Chat'
import { Section, Tag } from '@/components/ui-bits'

export default function ChatPage() {
  const { t } = useT()
  const allFacts = useStore(s => s.facts); const facts = allFacts.filter(f => f.on).slice(0, 3)
  const open = (sym: string) => { setView({ coin: sym, mode: 'single' }); navigate('dashboard') }
  return (
    <div className="grid items-start grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
      <Section title={t('chat.title')} hint={t('chat.same')}>
        <Conversation className="max-h-[62vh]" onOpenCoin={open} />
        <div className="mt-3 flex flex-col gap-2.5 border-t border-border pt-3">
          <Suggestions items={['Show BTC 30d', 'Compare BTC and ETH', 'Why did SOL drop?', 'Alert ETH below 3800']} />
          <PromptInput />
          <span className="text-[11px] text-muted-foreground">{t('chat.hint')}</span>
        </div>
      </Section>
      <Section className="text-[12.5px]">
        <h3 className="mb-2 text-[13px] font-bold">{t('chat.ctx')}</h3>
        {[[t('chat.turns'), '6'], [t('chat.facts'), `${facts.length} of ${allFacts.length}`], [t('chat.recall'), 'not needed'], [t('chat.model'), 'gpt-5.4-mini']].map(([k, v]) => <div key={k} className="flex justify-between gap-2.5 border-b border-border py-1.5 last:border-0"><span className="text-muted-foreground">{k}</span><b>{v}</b></div>)}
        <h3 className="mb-2 mt-4 text-[13px] font-bold">{t('chat.leaned')}</h3>
        {facts.map(f => <div key={f.id} className="border-b border-border py-1.5 text-secondary-foreground last:border-0">{f.f}</div>)}
        <h3 className="mb-2 mt-4 text-[13px] font-bold">{t('chat.tools')}</h3>
        <div className="flex flex-wrap gap-1"><Tag>get_price(BTC)</Tag><Tag>get_chart(BTC, 1d)</Tag></div>
        <p className="mt-3 text-xs text-muted-foreground">{t('chat.editable')} <a href="#memory" className="text-gold-ink underline">{t('nav.memory')}</a></p>
      </Section>
    </div>
  )
}
