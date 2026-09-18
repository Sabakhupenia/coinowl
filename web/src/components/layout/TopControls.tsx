import { useState } from 'react'
import { toast } from 'sonner'
import { Moon, Sun } from 'lucide-react'
import { profile as profileApi, useStore } from '@/lib/store'
import { usePrefs } from '@/lib/prefs'
import { useT } from '@/lib/i18n'
import { navigate } from '@/lib/router'
import { LangSwitch } from '@/components/LangSwitch'
import { ModeSwitch } from '@/components/ModeSwitch'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

export function ThemeButton() {
  const { isDark, setTheme } = usePrefs(); const { t } = useT()
  return <Button variant="outline" size="icon" className="size-9 rounded-[11px] bg-card" onClick={() => setTheme(isDark ? 'light' : 'dark')} title={t('top.theme')} aria-label={t('top.theme')}>{isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}</Button>
}

/** Account menu with the quick profile edit (name + bot languages) — the thing that was hard to find in V2. */
export function AccountMenu({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useT()
  const p = useStore(s => s.profile)
  const [name, setName] = useState(p.name); const [langs, setLangs] = useState(p.langs)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2.5 rounded-full border border-border bg-card py-1 pl-1 pr-3 text-left shadow-[inset_0_1px_0_var(--edge)]">
          <span className="grid size-[30px] place-items-center rounded-full bg-linear-to-br from-[#7b5fe0] to-[#2aabee] text-xs font-extrabold text-white ring-2 ring-card">{p.name[0]?.toUpperCase()}</span>
          <span className="hidden whitespace-nowrap leading-tight sm:block [[data-ui=advanced]_&]:hidden"><b className="block text-[13px]">{p.name}</b><span className="text-[11px] text-muted-foreground">{t('top.plan')}</span></span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[300px] p-3.5">
        <DropdownMenuLabel className="px-0 pb-2 text-xs font-semibold text-muted-foreground">{t('set.profile')}</DropdownMenuLabel>
        <div className="flex flex-col gap-3" onKeyDown={e => e.stopPropagation()}>
          <div className="grid gap-1.5"><Label htmlFor="q-name">{t('set.name')}</Label><Input id="q-name" value={name} onChange={e => setName(e.target.value)} className="bg-sunken" /></div>
          <div className="grid gap-1.5"><Label>{t('set.langs')}</Label>
            {([['ka', 'ქართული'], ['en', 'English'], ['ru', 'Русский']] as const).map(([k, l]) => <label key={k} className="flex h-7 items-center gap-2 text-sm"><Checkbox checked={langs.includes(k)} onCheckedChange={c => setLangs(c === true ? [...langs, k] : langs.filter(x => x !== k))} />{l}</label>)}
            <span className="text-[11px] leading-snug text-muted-foreground">{t('set.langsHelp')}</span></div>
          <Button size="sm" className="btn-gold border-0 font-bold" onClick={() => { profileApi.set({ name: name.trim() || p.name, langs }); toast(t('set.saved')) }}>{t('c.save')}</Button>
        </div>
        <DropdownMenuSeparator className="my-3" />
        <DropdownMenuItem onSelect={() => navigate('settings')}>{t('nav.settings')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate('plan')}>{t('plan.title')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={onSignOut}>{t('top.signout')}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function TopControls({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <LangSwitch />
      <ModeSwitch />
      <ThemeButton />
      <AccountMenu onSignOut={onSignOut} />
    </div>
  )
}
