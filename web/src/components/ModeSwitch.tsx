import { useState } from 'react'
import { toast } from 'sonner'
import { LayoutPanelLeft, Monitor } from 'lucide-react'
import { usePrefs } from '@/lib/prefs'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

/** Standard ⇄ Advanced layout. Advanced is wide-screen only; the disclaimer dialog gates the first switch. */
export function ModeSwitch({ className }: { className?: string }) {
  const { ui, setUi, wide } = usePrefs()
  const { t } = useT()
  const [open, setOpen] = useState(false)
  const on = ui === 'advanced'
  const change = (v: boolean) => { if (!v) { setUi('standard'); toast(t('toast.uiStandard')); return } setOpen(true) }
  const confirm = () => { setUi('advanced'); setOpen(false); toast(wide ? t('toast.uiAdvanced') : t('mode.narrow')) }
  return (
    <>
      <label className={cn('inline-flex h-9 cursor-pointer items-center gap-2 rounded-[11px] border border-border bg-sunken px-2.5 text-xs font-bold text-secondary-foreground', on && 'text-gold-ink', className)} title={t('top.ui')}>
        <LayoutPanelLeft className="size-4" />
        <span className="hidden sm:inline">{on ? t('top.advanced') : t('top.standard')}</span>
        <Switch checked={on} onCheckedChange={change} aria-label={t('top.ui')} className="data-[state=checked]:bg-gold" />
      </label>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Monitor className="size-5 text-gold" />{t('mode.title')}</DialogTitle><DialogDescription className="pt-2 text-left leading-relaxed">{t('mode.body')}</DialogDescription></DialogHeader>
          {!wide && <p className="rounded-lg border border-gold/30 bg-gold-soft px-3 py-2 text-xs font-semibold text-gold-ink">{t('mode.narrow')}</p>}
          <DialogFooter className="gap-2 sm:gap-0"><Button variant="outline" onClick={() => setOpen(false)}>{t('c.cancel')}</Button><Button className="btn-gold border-0 font-bold" onClick={confirm}>{t('mode.confirm')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
