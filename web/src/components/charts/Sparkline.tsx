export function Sparkline({ series, w = 64, h = 22, neg, fill = true }: { series: number[]; w?: number; h?: number; neg?: boolean; fill?: boolean }) {
  const lo = Math.min(...series), hi = Math.max(...series), pad = 3
  const x = (i: number) => pad + (i / (series.length - 1)) * (w - pad * 2)
  const y = (v: number) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - pad * 2)
  const d = series.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ')
  const color = neg ? 'var(--down)' : 'var(--up)'
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden="true" className="block max-w-full">
      {fill && <path d={`${d} L${x(series.length - 1).toFixed(1)} ${h} L${x(0).toFixed(1)} ${h} Z`} fill={color} opacity={0.12} />}
      <path d={d} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(series.length - 1).toFixed(1)} cy={y(series[series.length - 1]).toFixed(1)} r={2.6} fill={color} stroke="var(--card)" strokeWidth={1.5} />
    </svg>
  )
}
export function Overlay({ a, b, w = 160, h = 40 }: { a: number[]; b: number[]; w?: number; h?: number }) {
  const na = a.map(v => v / a[0] - 1), nb = b.map(v => v / b[0] - 1); const all = na.concat(nb)
  const lo = Math.min(...all), hi = Math.max(...all)
  const x = (i: number) => 3 + (i / (na.length - 1)) * (w - 6), y = (v: number) => h - 3 - ((v - lo) / (hi - lo || 1)) * (h - 6)
  const path = (s: number[]) => s.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden="true" className="block max-w-full">
      <path d={path(na)} fill="none" stroke="var(--chart-line)" strokeWidth={1.8} strokeLinejoin="round" />
      <path d={path(nb)} fill="none" stroke="var(--s2)" strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  )
}
