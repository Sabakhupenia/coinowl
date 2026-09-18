import { useEffect, useState } from 'react'
import { Toaster, toast } from 'sonner'
import { PrefsProvider, usePrefs } from '@/lib/prefs'
import { useT } from '@/lib/i18n'
import { navigate, useRoute } from '@/lib/router'
import { TooltipProvider } from '@/components/ui/tooltip'
import { StandardShell } from '@/components/layout/StandardShell'
import { AdvancedShell } from '@/components/layout/AdvancedShell'
import { Button } from '@/components/ui/button'

function Login({ onIn }: { onIn: () => void }) {
  const { t } = useT()
  return (
    <div className="grid min-h-full place-items-center p-4">
      <div className="w-full max-w-[440px] rounded-[22px] p-9 text-center" style={{ border: '1px solid transparent', background: 'linear-gradient(var(--card),var(--card)) padding-box,linear-gradient(135deg,rgba(212,175,55,.65),rgba(212,175,55,.06) 55%,rgba(212,175,55,.35)) border-box', boxShadow: 'var(--shadow-1), var(--gold-glow)' }}>
        <div className="mx-auto mb-4 grid size-[72px] place-items-center rounded-[20px] text-4xl shadow-[inset_0_1px_0_rgba(255,255,255,.4),var(--gold-glow)]" style={{ background: 'var(--gold-grad)' }}>🦉</div>
        <h1 className="display text-[32px] font-medium">{t('login.title')}</h1>
        <p className="display-italic mb-6 mt-2.5 text-[15px] text-secondary-foreground">{t('login.sub')}</p>
        <Button onClick={onIn} className="h-11 rounded-full bg-[#2AABEE] px-6 text-[15px] font-bold text-white hover:bg-[#2AABEE]/90"><svg viewBox="0 0 24 24" className="size-5 fill-white"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.6 6.9-1.6 7.6c-.1.5-.4.7-.9.4l-2.4-1.8-1.2 1.1c-.1.1-.2.2-.5.2l.2-2.5 4.5-4.1c.2-.2 0-.3-.3-.1l-5.6 3.5-2.4-.8c-.5-.2-.5-.5.1-.8l9.4-3.6c.4-.2.8.1.7.9z" /></svg>{t('login.btn')}</Button>
        <p className="mt-5 text-xs leading-relaxed text-muted-foreground">{t('login.fine')}</p>
      </div>
    </div>
  )
}

function Shell() {
  const { effectiveUi, ui, wide } = usePrefs()
  const { t } = useT()
  const { path } = useRoute()
  const [signedIn, setSignedIn] = useState(true)
  // Keep the URL sensible when the layout changes: advanced uses #coin/X, standard uses page names.
  useEffect(() => {
    if (effectiveUi === 'advanced' && (path === 'dashboard' || path === '' || path === 'chat' || path === 'news' || path === 'similar')) navigate('coin/BTC')
    if (effectiveUi === 'standard' && path === 'coin') navigate('dashboard')
  }, [effectiveUi, path])
  useEffect(() => { if (ui === 'advanced' && !wide) toast(t('mode.narrow'), { id: 'narrow' }) }, [ui, wide, t])
  if (!signedIn) return <Login onIn={() => { setSignedIn(true); toast('Signed in as Saba via Telegram') }} />
  return effectiveUi === 'advanced' ? <AdvancedShell onSignOut={() => setSignedIn(false)} /> : <StandardShell onSignOut={() => setSignedIn(false)} />
}

export default function App() {
  return (
    <PrefsProvider>
      <TooltipProvider>
        <Shell />
        <Toaster position="bottom-center" richColors={false} toastOptions={{ className: 'font-sans' }} />
      </TooltipProvider>
    </PrefsProvider>
  )
}
