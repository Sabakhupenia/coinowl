import { useEffect, useRef } from 'react'
import { AreaSeries, ColorType, CrosshairMode, LineSeries, createChart, type IChartApi, type UTCTimestamp } from 'lightweight-charts'
import { pts, type Coin, type RangeKey } from '@/lib/mock'
import { usePrefs } from '@/lib/prefs'

const SERIES = ['--s1', '--s2', '--s3', '--s4', '--s5']
const axisPrice = (v: number) => v >= 1000 ? Math.round(v).toLocaleString('en-US') : v >= 1 ? v.toFixed(2) : v >= 0.01 ? v.toFixed(4) : v.toPrecision(3)
const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** Single coin → gold area chart. Several coins → % change lines indexed to 0 at range start. */
export function PriceChart({ coins, range, height = 340, hidden }: { coins: Coin[]; range: RangeKey; height?: number; hidden?: Set<string> }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const { isDark, effectiveUi } = usePrefs()
  useEffect(() => {
    const el = ref.current; if (!el) return
    const compare = coins.length > 1
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: cssVar('--muted-foreground'), fontFamily: cssVar('--font-mono'), fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: cssVar('--chart-grid') }, horzLines: { color: cssVar('--chart-grid') } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.06 } },
      timeScale: { borderVisible: false, timeVisible: range === '24h' || range === '7d', secondsVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: CrosshairMode.Magnet, vertLine: { color: cssVar('--muted-foreground'), width: 1, style: 3, labelBackgroundColor: cssVar('--raised') }, horzLine: { color: cssVar('--muted-foreground'), labelBackgroundColor: cssVar('--raised') } },
      localization: { priceFormatter: compare ? (v: number) => (v > 0 ? '+' : '') + v.toFixed(1) + '%' : axisPrice },
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    })
    chartRef.current = chart
    const line = cssVar('--chart-line')
    coins.forEach((c, i) => {
      if (hidden?.has(c.sym)) return
      const p = pts(c, range); const base = p[0].p
      const data = p.map(q => ({ time: Math.floor(q.t / 1000) as UTCTimestamp, value: compare ? (q.p / base - 1) * 100 : q.p }))
      if (compare) {
        const s = chart.addSeries(LineSeries, { color: cssVar(SERIES[i % SERIES.length]), lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: c.sym, crosshairMarkerRadius: 4 })
        s.setData(data)
      } else {
        const s = chart.addSeries(AreaSeries, { lineColor: line, topColor: cssVar('--chart-fill-top'), bottomColor: 'rgba(0,0,0,0)', lineWidth: 2, priceLineVisible: true, priceLineColor: line, priceLineStyle: 3, crosshairMarkerRadius: 5, crosshairMarkerBorderColor: cssVar('--card') })
        s.setData(data)
      }
    })
    chart.timeScale().fitContent()
    return () => { chart.remove(); chartRef.current = null }
  }, [coins, range, hidden, isDark, effectiveUi])
  return <div ref={ref} style={{ height }} className="w-full" role="img" aria-label="Price chart" />
}
