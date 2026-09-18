import { useState } from 'react'
import { Bell, Brain, CreditCard, LayoutGrid, MessageSquare, MoreHorizontal, Newspaper, Settings, Sparkles } from 'lucide-react'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { useStore } from '@/lib/store'
import { fmtToday } from '@/lib/format'
import { useRoute } from '@/lib/router'
import { useT, type Key } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Omnibox } from '@/components/Omnibox'
import { TopControls } from '@/components/layout/TopControls'
import Dashboard from '@/pages/Dashboard'
import ChatPage from '@/pages/ChatPage'
import NewsPage from '@/pages/NewsPage'
import SimilarPage from '@/pages/SimilarPage'
import AlertsPage from '@/pages/AlertsPage'
import MemoryPage from '@/pages/MemoryPage'
import SettingsPage from '@/pages/SettingsPage'
import PlanPage from '@/pages/PlanPage'

const NAV: { id: string; k: Key; Icon: typeof LayoutGrid }[] = [
  { id: 'dashboard', k: 'nav.dashboard', Icon: LayoutGrid }, { id: 'chat', k: 'nav.chat', Icon: MessageSquare }, { id: 'news', k: 'nav.news', Icon: Newspaper }, { id: 'similar', k: 'nav.similar', Icon: Sparkles },
  { id: 'alerts', k: 'nav.alerts', Icon: Bell }, { id: 'memory', k: 'nav.memory', Icon: Brain }, { id: 'settings', k: 'nav.settings', Icon: Settings }, { id: 'plan', k: 'nav.plan', Icon: CreditCard },
]
const PAGES: Record<string, () => React.JSX.Element> = { dashboard: Dashboard, chat: ChatPage, news: NewsPage, similar: SimilarPage, alerts: AlertsPage, memory: MemoryPage, settings: SettingsPage, plan: PlanPage }

export function StandardShell({ onSignOut }: { onSignOut: () => void }) {
  const { t, lang } = useT()
  const { path } = useRoute()
  const today = fmtToday(lang)
  const page = PAGES[path] ? path : 'dashboard'
  const Page = PAGES[page]
  const armed = useStore(s => s.alerts).filter(a => a.state === 'armed').length
  const [more, setMore] = useState(false)
  return (
    <div className="grid min-h-full grid-cols-1 md:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="fixed inset-x-0 bottom-0 z-20 flex flex-col border-t border-border px-1.5 pb-[calc(6px+env(safe-area-inset-bottom,0px))] pt-1.5 glass md:sticky md:top-0 md:h-dvh md:border-r md:border-t-0 md:bg-linear-to-b md:from-sunken md:to-transparent md:px-3.5 md:pb-4 md:pt-6 md:backdrop-blur-none">
        <a href="#dashboard" className="mb-6 hidden items-center gap-3 px-2 md:flex">
          <span className="grid size-[38px] place-items-center rounded-xl text-xl shadow-[inset_0_1px_0_rgba(255,255,255,.4),var(--gold-glow)]" style={{ background: 'var(--gold-grad)' }}>🦉</span>
          <span><span className="display block text-[23px] font-semibold leading-none">CoinOwl</span><span className="mt-1 block text-[10.5px] font-bold tracking-[0.09em] text-muted-foreground">CONSOLE · v0.8</span></span>
        </a>
        <nav className="flex justify-around md:flex-col md:gap-0.5">
          {NAV.map(({ id, k, Icon }, i) => (
            <a key={id} href={'#' + id} className={cn('relative flex flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[10px] font-bold text-secondary-foreground md:flex md:flex-row md:gap-3 md:rounded-[10px] md:px-3 md:py-2.5 md:text-[13.5px] md:font-semibold', i >= 4 && 'hidden', page === id ? 'bg-gold-soft text-gold-ink md:bg-linear-to-r md:from-gold-soft md:to-transparent' : 'hover:bg-raised hover:text-foreground')}>
              {page === id && <span className="absolute -left-3.5 top-2 bottom-2 hidden w-[3px] rounded-r md:block" style={{ background: 'var(--gold-grad)', boxShadow: 'var(--gold-glow)' }} />}
              <Icon className="size-[18px] opacity-85" />{t(k)}
              {id === 'alerts' && armed > 0 && <span className="hidden rounded-full border border-border bg-raised px-2 text-[11px] md:ml-auto md:inline">{armed}</span>}
            </a>
          ))}
          <button onClick={() => setMore(true)} className={cn('flex flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[10px] font-bold text-secondary-foreground md:hidden', NAV.slice(4).some(n => n.id === page) && 'bg-gold-soft text-gold-ink')}><MoreHorizontal className="size-[18px]" />{t('nav.more')}</button>
        </nav>
        <Sheet open={more} onOpenChange={setMore}>
          <SheetContent side="bottom" className="rounded-t-2xl pb-[calc(16px+env(safe-area-inset-bottom,0px))]">
            <SheetTitle className="mb-2 text-sm text-muted-foreground">{t('nav.more')}</SheetTitle>
            <div className="grid grid-cols-2 gap-2">{NAV.slice(4).map(({ id, k, Icon }) => <a key={id} href={'#' + id} onClick={() => setMore(false)} className={cn('flex items-center gap-3 rounded-xl border border-border px-3 py-3 text-sm font-semibold', page === id && 'border-gold/30 bg-gold-soft text-gold-ink')}><Icon className="size-[18px]" />{t(k)}</a>)}</div>
          </SheetContent>
        </Sheet>
        <div className="mt-auto hidden border-t border-border px-2.5 pt-4 text-xs leading-relaxed text-muted-foreground md:block"><div className="flex items-center gap-2 font-bold text-secondary-foreground"><span className="size-2 rounded-full bg-gold shadow-[0_0_10px_var(--gold)]" />{t('rail.bot')}</div>{t('rail.last')}<br />{t('c.dataSource')}</div>
      </aside>
      <main className="min-w-0 px-4 pb-24 md:px-8 md:pb-12">
        <header className="sticky top-0 z-10 -mx-4 mb-4 flex flex-wrap items-center gap-3 border-b border-border px-4 py-3.5 glass md:-mx-8 md:gap-4 md:px-8">
          <div className="min-w-0"><h1 className="display text-2xl font-medium leading-tight md:text-[30px]">{t(('nav.' + page) as Key)}</h1><p className="display-italic hidden text-[14.5px] text-secondary-foreground md:block">{t(('sub.' + page) as Key)}{page === 'dashboard' && <span className="ml-2 text-gold-ink">{today}</span>}</p></div>
          <div className="order-last w-full md:order-0 md:ml-auto md:w-auto md:max-w-[440px] md:flex-1"><Omnibox mode="standard" /></div>
          <span className="hidden rounded-full border border-border bg-raised px-2.5 py-0.5 text-[11.5px] font-bold text-secondary-foreground lg:inline" title="This preview uses generated numbers, not live CoinGecko data">{t('c.sample')}</span>
          <TopControls onSignOut={onSignOut} />
        </header>
        <Page />
      </main>
    </div>
  )
}
