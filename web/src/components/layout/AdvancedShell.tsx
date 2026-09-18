import { useState } from 'react'
import { Search } from 'lucide-react'
import { FNG, pct } from '@/lib/mock'
import { fmtUSD } from '@/lib/format'
import { useStore } from '@/lib/store'
import { navigate, useRoute } from '@/lib/router'
import { setView } from '@/lib/view'
import { useT, type Key } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Omnibox } from '@/components/Omnibox'
import { TopControls } from '@/components/layout/TopControls'
import { CoinView } from '@/components/layout/CoinView'
import { Conversation, PromptInput, Suggestions } from '@/components/chat/Chat'
import { CoinIcon, Delta, Section } from '@/components/ui-bits'
import { Movers } from '@/pages/Dashboard'
import { FngTile } from '@/pages/Dashboard'
import AlertsPage from '@/pages/AlertsPage'
import MemoryPage from '@/pages/MemoryPage'
import SettingsPage from '@/pages/SettingsPage'
import PlanPage from '@/pages/PlanPage'
import { Input } from '@/components/ui/input'

const MANAGE: { id: string; k: Key }[] = [{ id: 'alerts', k: 'nav.alerts' }, { id: 'memory', k: 'nav.memory' }, { id: 'market', k: 'nav.market' }, { id: 'settings', k: 'nav.account' }, { id: 'plan', k: 'nav.plan' }]

function MarketView() {
  const { t } = useT()
  return <div className="flex max-w-[1080px] flex-col gap-4"><h1 className="text-[22px] font-bold">{t('nav.market')}</h1><div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr]"><FngTile compact /><Section title="Global"><div className="grid grid-cols-2 gap-3 text-sm">{[['Market cap', '$3.92T'], ['24h volume', '$148B'], ['BTC dominance', '57.3%'], ['F&G 30d ago', String(FNG.month)]].map(([k, v]) => <div key={k}><em className="block text-xs not-italic text-muted-foreground">{k}</em><b className="text-lg tnum">{v}</b></div>)}</div></Section></div><Movers range="7d" /></div>
}

/** Workbench: watchlist · workspace · agent, always on one screen. Wide screens only (PrefsProvider enforces). */
export function AdvancedShell({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useT()
  const { path, arg } = useRoute()
  const wl = useStore(s => s.watchlist); const alerts = useStore(s => s.alerts); const inbox = useStore(s => s.inbox); const q = useStore(s => s.quota)
  const [filter, setFilter] = useState('')
  const [sym, tab = 'overview'] = arg.split('/')
  const view = path === 'coin' && sym ? 'coin' : MANAGE.some(m => m.id === path) ? path : 'coin'
  const coin = view === 'coin' ? (sym || 'BTC').toUpperCase() : ''
  const unread = inbox.filter(x => !x.read).length
  const Work = () => {
    if (view === 'coin') return <CoinView sym={coin} tab={tab} />
    if (view === 'alerts') return <div className="max-w-[1080px]"><AlertsPage /></div>
    if (view === 'memory') return <div className="max-w-[1080px]"><MemoryPage /></div>
    if (view === 'market') return <MarketView />
    if (view === 'settings') return <div className="max-w-[1080px]"><SettingsPage /></div>
    return <div className="max-w-[1080px]"><PlanPage /></div>
  }
  return (
    <div className="grid h-full grid-cols-[288px_minmax(0,1fr)_372px] grid-rows-[56px_minmax(0,1fr)]">
      <header className="col-span-3 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3.5 border-b border-border bg-card px-4">
        <a href="#coin/BTC" className="flex items-center gap-2.5 whitespace-nowrap text-base font-bold"><span className="grid size-7 place-items-center rounded-lg bg-gold text-[15px]">🦉</span>CoinOwl</a>
        <div className="mx-auto w-full max-w-[640px]"><Omnibox mode="advanced" placeholder={t('omni.ph')} /></div>
        <div className="flex items-center justify-end gap-2"><span className="hidden items-center gap-1.5 whitespace-nowrap text-xs text-secondary-foreground 2xl:flex"><i className="size-2 rounded-full bg-up" />Bot online</span><TopControls onSignOut={onSignOut} /></div>
      </header>
      <aside className="flex flex-col overflow-auto border-r border-border bg-card">
        <div className="flex items-center justify-between px-3.5 pb-1.5 pt-3.5 text-xs font-bold uppercase tracking-wider text-muted-foreground">{t('nav.watchlist')}<a href="#settings" className="text-xs font-semibold normal-case tracking-normal text-gold-ink">{t('c.edit')}</a></div>
        <div className="relative mx-3 mb-1.5"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter coins" className="h-9 pl-8" /></div>
        <ul className="px-2" role="listbox" aria-label={t('nav.watchlist')}>
          {wl.filter(c => !filter || c.sym.toLowerCase().includes(filter.toLowerCase()) || c.name.toLowerCase().includes(filter.toLowerCase())).map(c => (
            <li key={c.sym} role="option" aria-selected={view === 'coin' && coin === c.sym} tabIndex={0} onClick={() => { setView({ coin: c.sym }); navigate('coin/' + c.sym + '/' + tab) }} onKeyDown={e => { if (e.key === 'Enter') navigate('coin/' + c.sym) }}
              className={cn('grid cursor-pointer grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border-l-[3px] border-transparent px-2 py-2 hover:bg-secondary', view === 'coin' && coin === c.sym && 'border-gold bg-accent')}>
              <CoinIcon sym={c.sym} size={36} />
              <div className="min-w-0"><b className="block text-sm leading-tight">{c.sym}</b><span className="block truncate text-xs text-muted-foreground">{c.name}</span></div>
              <div className="text-right"><b className="block text-sm tnum">{fmtUSD(c.price)}</b><Delta v={pct(c, '24h')} className="px-1.5 py-0 text-[11px]" /></div>
            </li>))}
        </ul>
        <div className="px-3.5 pb-1.5 pt-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">{t('nav.manage')}</div>
        <ul className="px-2">{MANAGE.map(m => <li key={m.id}><a href={'#' + m.id} className={cn('flex items-center justify-between rounded-lg border-l-[3px] border-transparent px-3 py-2 text-sm font-medium hover:bg-secondary', view === m.id && 'border-gold bg-accent font-semibold')}>{t(m.k)}<span className="text-xs text-muted-foreground">{m.id === 'alerts' ? `${alerts.filter(a => a.state === 'armed').length} armed${unread ? ` · ${unread} new` : ''}` : m.id === 'plan' ? `${q.used} / ${q.limit}` : ''}</span></a></li>)}</ul>
        <a href="#market" className="mt-auto block border-t border-border px-3.5 py-3 text-sm"><div className="flex items-baseline gap-2"><span className="text-muted-foreground">Fear &amp; Greed</span><b className="text-[22px]">{FNG.today}</b><span>{FNG.word}</span></div><div className="relative mt-1.5 h-1.5 rounded-full" style={{ background: 'linear-gradient(90deg,var(--down),var(--muted-foreground) 50%,var(--up))' }}><i className="absolute -top-1 size-3.5 -translate-x-1/2 rounded-full border-2 border-card bg-foreground" style={{ left: FNG.today + '%' }} /></div></a>
      </aside>
      <main className="min-w-0 overflow-auto px-6 py-5"><Work /></main>
      <aside className="flex min-h-0 flex-col border-l border-border bg-card">
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3"><b className="text-[15px]">{t('chat.agent')}</b><span className="text-xs text-muted-foreground">{t('chat.same')}</span><span className="ml-auto rounded-full bg-accent px-2 py-0.5 text-[11px] font-bold text-accent-foreground">gpt-5.4-mini</span></div>
        <Conversation className="flex-1 px-4 py-3.5" onOpenCoin={s => navigate('coin/' + s)} />
        <div className="px-4 pb-2.5"><Suggestions items={['Show BTC 30d', 'Compare BTC and ETH', 'Why did SOL drop?', 'Alert ETH below 3800']} /></div>
        <div className="flex flex-col gap-1.5 border-t border-border px-4 pb-3 pt-2.5"><PromptInput placeholder="Ask the agent…" /><span className="text-[11px] text-muted-foreground">{t('chat.hint')}</span></div>
      </aside>
    </div>
  )
}
