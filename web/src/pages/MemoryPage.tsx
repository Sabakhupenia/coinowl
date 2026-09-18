import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { facts as factsApi, setInstructions, useStore } from '@/lib/store'
import { useT } from '@/lib/i18n'
import { undoToast } from '@/components/features/Alerts'
import { Eyebrow, Section } from '@/components/ui-bits'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'

export function FactsList() {
  const { t } = useT()
  const facts = useStore(s => s.facts)
  const [v, setV] = useState('')
  const add = (e: FormEvent) => { e.preventDefault(); if (!v.trim()) return; factsApi.add(v.trim()); setV(''); toast(t('toast.factSaved')) }
  return (
    <>
      <div className="flex flex-col">
        {facts.map(f => (
          <div key={f.id} className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-border py-2 last:border-0">
            <Checkbox checked={f.on} onCheckedChange={c => factsApi.patch(f.id, { on: c === true })} title="Use in replies" />
            <div contentEditable suppressContentEditableWarning spellCheck={false} className="rounded-md border border-transparent px-1.5 py-1 text-[13.5px] hover:border-input focus:border-ring focus:outline-none" onBlur={e => { const nv = e.currentTarget.textContent?.trim(); if (nv && nv !== f.f) { factsApi.patch(f.id, { f: nv }); toast(t('toast.factSaved')) } }} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLElement).blur() } }}>{f.f}</div>
            <div className="flex items-center gap-2"><Badge variant="outline" className={f.src === 'you' ? 'border-gold/25 bg-gold-soft text-gold-ink' : ''}>{f.src === 'you' ? t('mem.told') : t('mem.noticed')} · {f.d}</Badge><Button size="sm" variant="ghost" className="text-[var(--copper-ink)]" onClick={() => { const undo = factsApi.remove(f.id); undoToast(t('toast.forgotten'), undo, t('c.undo')) }}>{t('mem.forget')}</Button></div>
          </div>
        ))}
      </div>
      <form onSubmit={add} className="mt-3 flex gap-2"><Input value={v} onChange={e => setV(e.target.value)} placeholder={t('mem.addPh')} className="bg-sunken" /><Button type="submit" variant="outline">{t('c.add')}</Button></form>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('mem.factsHint')}</p>
    </>
  )
}

export function Instructions() {
  const { t } = useT()
  const instr = useStore(s => s.instructions)
  const [v, setV] = useState(instr)
  return (
    <>
      <Textarea value={v} onChange={e => setV(e.target.value)} className="min-h-[110px] bg-sunken" />
      <div className="mt-2 flex items-center gap-3"><span className="text-xs text-muted-foreground">{v.length} / 500</span><Button size="sm" className="btn-gold ml-auto border-0 font-bold" onClick={() => { setInstructions(v); toast(t('toast.instr')) }}>{t('c.save')}</Button></div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('mem.instrNote')}</p>
    </>
  )
}

export function History() {
  const { t } = useT()
  const history = useStore(s => s.history)
  const [q, setQ] = useState(''); const [gone, setGone] = useState<Set<string>>(new Set())
  const n = q.toLowerCase()
  return (
    <>
      <div className="mb-2 flex"><Input value={q} onChange={e => setQ(e.target.value)} placeholder={t('mem.search')} className="ml-auto max-w-[260px] bg-sunken" /></div>
      {history.map(([day, rows]) => { const vis = rows.filter(r => !gone.has(day + r[0]) && (!n || r[1].toLowerCase().includes(n) || r[2].toLowerCase().includes(n))); if (!vis.length) return null; return (
        <div key={day}><Eyebrow className="mb-1 mt-3">{day}</Eyebrow>{vis.map(r => <div key={r[0]} className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-border py-1.5 text-[13px]"><span className="font-mono text-xs text-muted-foreground">{r[0]}</span><div className="truncate">{r[1]}  <em className="not-italic text-muted-foreground">→ {r[2]}</em></div><Button size="sm" variant="ghost" className="text-[var(--copper-ink)]" onClick={() => { const key = day + r[0]; setGone(g => new Set(g).add(key)); undoToast(t('toast.turn'), () => setGone(g => { const c = new Set(g); c.delete(key); return c }), t('c.undo')) }}>{t('c.delete')}</Button></div>)}</div>) })}
    </>
  )
}

export default function MemoryPage() {
  const { t } = useT()
  return (
    <div className="flex flex-col gap-4">
      <div className="card-premium flex flex-wrap items-center gap-6 p-5 md:p-6">
        <div><Eyebrow>{t('mem.since')}</Eyebrow><div className="text-4xl font-extrabold tracking-tighter">1,284<small className="ml-1.5 text-sm font-semibold tracking-normal text-secondary-foreground">{t('mem.msgs')}</small></div></div>
        <div><Eyebrow>{t('mem.charts')}</Eyebrow><div className="text-4xl font-extrabold tracking-tighter">37</div></div>
        <div><Eyebrow>{t('mem.most')}</Eyebrow><div className="pt-1.5 text-[22px] font-extrabold tracking-tight">BTC · TON · ETH</div></div>
        <div className="ml-auto flex gap-2"><Button variant="outline">{t('mem.export')}</Button><Button variant="outline" className="text-[var(--copper-ink)]" onClick={() => { const undo = factsApi.clear(); undoToast(t('mem.cleared'), undo, t('c.undo')) }}>{t('mem.forgetAll')}</Button></div>
      </div>
      <div className="grid items-start grid-cols-1 gap-4 xl:grid-cols-2">
        <Section title={t('mem.facts')} hint={t('mem.injected')}><FactsList /></Section>
        <Section title={t('mem.instr')} hint={t('mem.instrHint')}><Instructions /></Section>
      </div>
      <Section title={t('mem.history')} hint={t('mem.historyHint')}><History /></Section>
    </div>
  )
}
