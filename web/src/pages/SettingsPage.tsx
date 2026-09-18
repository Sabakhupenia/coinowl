import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { coinBy, makeCoin } from '@/lib/mock'
import { profile as profileApi, useStore, watchlist as wlApi } from '@/lib/store'
import { usePrefs, type Theme } from '@/lib/prefs'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { undoToast } from '@/components/features/Alerts'
import { Section } from '@/components/ui-bits'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { LangSwitch } from '@/components/LangSwitch'

const LANGS: [string, string][] = [['ka', 'ქართული'], ['en', 'English'], ['ru', 'Русский']]

/** Bot-facing profile: name + the languages the *bot* may reply in. Not the site language. */
export function ProfileForm({ compact }: { compact?: boolean }) {
  const { t } = useT()
  const p = useStore(s => s.profile)
  const [name, setName] = useState(p.name); const [langs, setLangs] = useState(p.langs); const [tz, setTz] = useState(p.tz); const [cur, setCur] = useState(p.currency)
  const save = () => { profileApi.set({ name: name.trim() || p.name, langs, tz, currency: cur }); toast(t('set.saved')) }
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-1.5"><Label htmlFor="s-name">{t('set.name')}</Label><Input id="s-name" value={name} onChange={e => setName(e.target.value)} className="bg-sunken" /><span className="text-xs text-muted-foreground">{t('set.nameHelp')}</span></div>
      <div className="grid gap-1.5"><Label>{t('set.langs')}</Label>
        <div className="flex flex-wrap gap-2">{LANGS.map(([k, l]) => <label key={k} className={cn('inline-flex cursor-pointer items-center gap-2 rounded-full border border-input bg-card px-3 py-1.5 text-xs font-semibold', langs.includes(k) && 'border-gold/30 bg-gold-soft text-gold-ink')}><Checkbox checked={langs.includes(k)} onCheckedChange={c => setLangs(c === true ? [...langs, k] : langs.filter(x => x !== k))} />{l}</label>)}</div>
        <span className="text-xs leading-relaxed text-muted-foreground">{t('set.langsHelp')}</span></div>
      {!compact && <>
        <div className="grid gap-1.5"><Label>{t('set.tz')}</Label><Select value={tz} onValueChange={setTz}><SelectTrigger className="bg-sunken"><SelectValue /></SelectTrigger><SelectContent>{['Asia/Tbilisi', 'Europe/Berlin', 'Europe/London', 'America/New_York'].map(z => <SelectItem key={z} value={z}>{z}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid gap-1.5"><Label>{t('set.cur')}</Label><Select value={cur} onValueChange={setCur}><SelectTrigger className="bg-sunken"><SelectValue /></SelectTrigger><SelectContent>{['USD', 'EUR', 'GEL'].map(z => <SelectItem key={z} value={z}>{z}</SelectItem>)}</SelectContent></Select></div>
      </>}
      <Button className="btn-gold self-start border-0 font-bold" onClick={save}>{t('c.save')}</Button>
    </div>
  )
}

export function WatchlistEditor() {
  const { t } = useT()
  const wl = useStore(s => s.watchlist)
  const [v, setV] = useState('')
  const add = (e: FormEvent) => { e.preventDefault(); const s = v.trim().toUpperCase(); if (!s) return; if (wl.length >= 10) { toast('Free holds 10 coins — Pro raises it to 30'); return } if (wl.some(c => c.sym === s)) { toast(s + ' is already on the list'); return } wlApi.add(coinBy(s) ?? makeCoin(s, s, 1, 0.02, 70 + wl.length)); setV(''); toast(s + ' added') }
  return (
    <>
      <div className="flex flex-wrap gap-1.5">{wl.map(c => <span key={c.sym} className="inline-flex items-center gap-1.5 rounded-full border border-gold/30 bg-gold-soft px-2.5 py-1 text-xs font-semibold text-gold-ink">{c.sym}<button aria-label={'Remove ' + c.sym} className="text-base leading-none opacity-60 hover:opacity-100" onClick={() => { const undo = wlApi.remove(c.sym); undoToast(c.sym + ' removed', undo, t('c.undo')) }}>×</button></span>)}<span className="self-center text-xs text-muted-foreground">{wl.length} / 10 {t('set.onFree')}</span></div>
      <form onSubmit={add} className="mt-3 flex gap-2"><Input value={v} onChange={e => setV(e.target.value)} placeholder={t('set.addTicker')} className="max-w-[220px] bg-sunken" /><Button type="submit" variant="outline">{t('c.add')}</Button></form>
    </>
  )
}

export function Appearance() {
  const { t } = useT(); const { theme, setTheme } = usePrefs()
  return (
    <div className="flex flex-col gap-4">
      <div><Label className="mb-1.5 block">{t('top.theme')}</Label>
        <ToggleGroup type="single" value={theme} onValueChange={v => v && setTheme(v as Theme)} className="rounded-[11px] border border-border bg-sunken p-[3px]">
          {(['system', 'dark', 'light'] as const).map(k => <ToggleGroupItem key={k} value={k} className="h-8 rounded-lg px-3 text-xs font-bold data-[state=on]:bg-card data-[state=on]:text-gold-ink data-[state=on]:shadow">{t(`set.${k}`)}</ToggleGroupItem>)}
        </ToggleGroup></div>
      <div><Label className="mb-1.5 block">{t('top.language')}</Label><LangSwitch /><span className="mt-1.5 block text-xs text-muted-foreground">{t('top.langHelp')}</span></div>
    </div>
  )
}

export default function SettingsPage() {
  const { t } = useT()
  return (
    <div className="grid items-start grid-cols-1 gap-4 xl:grid-cols-2">
      <Section title={t('set.profile')}><ProfileForm /></Section>
      <div className="flex flex-col gap-4">
        <Section title={t('set.wl')} hint={t('set.wlHint')}><WatchlistEditor /></Section>
        <Section title={t('set.notif')}>
          <div className="flex items-center justify-between gap-3 border-b border-border py-3"><div><b className="block text-sm">{t('set.tg')}</b><span className="text-xs text-muted-foreground">{t('set.tgD')}</span></div><Badge className="bg-gold-soft text-gold-ink hover:bg-gold-soft">{t('set.connected')}</Badge></div>
          <div className="flex items-center justify-between gap-3 py-3"><div><b className="block text-sm">{t('set.device')}</b><span className="text-xs text-muted-foreground">{t('set.deviceD')}</span></div><Button size="sm" variant="outline" onClick={() => toast('Your browser will offer “Add to Home Screen” here')}>{t('set.install')}</Button></div>
        </Section>
        <Section title={t('set.appearance')}><Appearance /></Section>
      </div>
    </div>
  )
}
