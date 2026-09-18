import { useState, type FormEvent } from 'react'
import { answerFor, type Answer } from '@/lib/mock'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'

export function GroundedAnswer({ initial }: { initial: string }) {
  const { t } = useT()
  const [q, setQ] = useState(initial)
  const [res, setRes] = useState(() => answerFor(initial))
  const [hot, setHot] = useState<number | null>(null)
  const ask = (e: FormEvent) => { e.preventDefault(); setRes(answerFor(q)) }
  return (
    <div>
      <form onSubmit={ask} className="mb-4 flex gap-2">
        <Input value={q} onChange={e => setQ(e.target.value)} aria-label="Question" className="h-10 bg-sunken" />
        <Button type="submit" className="btn-gold h-10 border-0 font-bold">{t('c.ask')}</Button>
      </form>
      {res.kind === 'refused' && <p className="text-[15px] leading-7">{t('news.refused')}</p>}
      {res.kind === 'none' && <p className="text-[15px] leading-7">{t('news.none')}</p>}
      {res.kind === 'ok' && res.a && <AnswerBody a={res.a} hot={hot} setHot={setHot} />}
    </div>
  )
}

function AnswerBody({ a, hot, setHot }: { a: Answer; hot: number | null; setHot: (n: number | null) => void }) {
  const { t } = useT()
  return (
    <>
      <p className="text-[15px] leading-7">
        {a.text.map(([s, cites], i) => (
          <span key={i}>{i ? ' ' : ''}{s}
            {cites.map(n => (
              <sup key={n} className="ml-0.5 inline-block">
                <button onMouseEnter={() => setHot(n)} onMouseLeave={() => setHot(null)} onClick={() => document.getElementById('src-' + n)?.scrollIntoView({ block: 'center', behavior: 'smooth' })}
                  className={cn('rounded-md border border-gold/30 bg-gold-soft px-1.5 py-0.5 font-mono text-[10.5px] font-bold text-gold-ink align-[2px]', hot === n && 'bg-gold text-[#1b1400]')}>{n}</button>
              </sup>
            ))}.
          </span>
        ))}
      </p>
      <div className="mt-2 border-t border-border pt-2.5 text-xs text-muted-foreground">{t('news.grounded', { n: a.src.length })} · gpt-5.4-mini</div>
      <div className="mt-3.5 flex flex-col gap-2.5">
        {a.src.map((x, i) => (
          <div key={i} id={'src-' + (i + 1)} className={cn('grid grid-cols-[28px_minmax(0,1fr)] gap-3 rounded-xl border border-border bg-sunken px-3.5 py-3 transition md:grid-cols-[28px_minmax(0,1fr)_92px]', hot === i + 1 && 'border-gold/50 ring-[3px] ring-gold-soft')}>
            <div className="grid size-[26px] place-items-center rounded-md border border-border bg-raised font-mono text-[11.5px] font-bold text-gold-ink">{i + 1}</div>
            <div>
              <b className="block text-[13.5px] leading-snug">{x.t}</b>
              <div className="mt-0.5 text-[11.5px] text-muted-foreground"><span className="text-secondary-foreground">CoinDesk</span> · {x.w} · chunk 2 of 5</div>
              <q className="mt-1.5 block text-[12.5px] leading-normal text-secondary-foreground [&_mark]:rounded-sm [&_mark]:bg-gold-soft [&_mark]:px-0.5 [&_mark]:text-gold-ink" dangerouslySetInnerHTML={{ __html: x.q }} />
            </div>
            <div className="hidden text-right text-[11px] text-muted-foreground md:block">
              <b className="mb-1.5 block font-mono text-sm font-semibold text-foreground">{x.sc.toFixed(2)}</b>
              <Progress value={x.sc * 100} className="h-1.5 bg-gold-soft [&>div]:bg-gold" />cosine
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
