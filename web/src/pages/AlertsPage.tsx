import { useState } from 'react'
import { toast } from 'sonner'
import { inbox as inboxApi, schedules as schedApi, useStore } from '@/lib/store'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { AlertForm, AlertRow, undoToast } from '@/components/features/Alerts'
import { Section, Tag } from '@/components/ui-bits'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

export function SchedulesList() {
  const { t } = useT()
  const sched = useStore(s => s.schedules)
  return (
    <div className="flex flex-col">
      {sched.map(s => (
        <div key={s.id} className="grid grid-cols-1 gap-3.5 border-b border-border py-3.5 last:border-0 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1.5fr)_auto] md:items-center">
          <div><b className="block text-sm">{s.title}</b><span className="block text-xs text-muted-foreground">{s.when} ({s.tz}) · {t('sc.next')} {s.next}</span><Tag className="mt-1">{s.tool}</Tag><div className="display-italic mt-1.5 border-l-2 border-gold pl-2.5 text-[13px] text-secondary-foreground">“{s.said}”</div></div>
          <RadioGroup value={s.mode} onValueChange={v => { schedApi.patch(s.id, { mode: v as 'notify' | 'save' }); toast(v === 'notify' ? 'Will ping you in Telegram' : 'Will wait for your next visit') }} className="gap-1.5">
            {([['notify', t('sc.notify'), t('sc.notifyD')], ['save', t('sc.save'), t('sc.saveD')]] as const).map(([m, l, d]) => (
              <label key={m} className={cn('grid cursor-pointer grid-cols-[20px_1fr] items-start gap-x-2.5 rounded-lg border border-border px-3 py-2', s.mode === m && 'border-gold/40 bg-gold-soft')}><RadioGroupItem value={m} className="mt-0.5" /><span><b className="block text-[13px]">{l}</b><span className="block text-xs text-muted-foreground">{d}</span></span></label>
            ))}
          </RadioGroup>
          <Button size="sm" variant="ghost" className="justify-self-start text-[var(--copper-ink)] md:justify-self-auto" onClick={() => { const undo = schedApi.remove(s.id); undoToast('Schedule removed', undo, t('c.undo')) }}>{t('c.delete')}</Button>
        </div>
      ))}
    </div>
  )
}

export function Inbox() {
  const { t } = useT()
  const items = useStore(s => s.inbox)
  return (
    <div className="flex flex-col">
      {items.map(x => (
        <div key={x.id} className="border-b border-border py-3 last:border-0">
          <div className="flex flex-wrap items-center gap-2.5 text-[13px] font-bold">{!x.read && <Badge className="bg-gold-soft text-gold-ink hover:bg-gold-soft">{t('ib.new')}</Badge>}<b>{x.t}</b><span className="text-xs font-semibold text-muted-foreground">{x.d}</span></div>
          <p className="mb-2 mt-1.5 text-[13px] leading-relaxed text-secondary-foreground">{x.p}</p>
          {!x.read && <Button size="sm" variant="outline" onClick={() => inboxApi.markRead(x.id)}>{t('ib.read')}</Button>}
        </div>
      ))}
    </div>
  )
}

export default function AlertsPage() {
  const { t } = useT()
  const alerts = useStore(s => s.alerts)
  const [showForm, setShowForm] = useState(false)
  return (
    <div className="flex flex-col gap-4">
      <Section title={t('al.title')} hint={t('al.sub')} right={<Button size="sm" variant="outline" onClick={() => setShowForm(v => !v)}>+ {t('al.new')}</Button>}>
        {showForm && <div className="mb-3"><AlertForm /></div>}
        <div className="flex flex-col">{alerts.map(a => <AlertRow key={a.id} a={a} />)}</div>
      </Section>
      <Section title={t('sc.title')} hint={t('sc.sub')}><SchedulesList /></Section>
      <Section title={t('ib.title')} hint={t('ib.sub')}><Inbox /></Section>
    </div>
  )
}
