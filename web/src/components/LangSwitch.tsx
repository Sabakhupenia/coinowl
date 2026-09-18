import { useT, type Lang } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/** Site-UI language. Deliberately separate from the bot's reply languages in Settings → Profile. */
export function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang, t } = useT()
  const opts: [Lang, string][] = [['ka', 'ქარ'], ['en', 'EN']]
  return (
    <div role="radiogroup" aria-label={t('top.language')} title={t('top.langHelp')} className={cn('inline-flex rounded-[11px] border border-border bg-sunken p-[3px] shadow-inner', className)}>
      {opts.map(([k, l]) => <button key={k} role="radio" aria-checked={lang === k} onClick={() => setLang(k)} className={cn('h-8 rounded-lg px-3 text-xs font-bold text-secondary-foreground transition', lang === k && 'bg-card text-gold-ink shadow')}>{l}</button>)}
    </div>
  )
}
