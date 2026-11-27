import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { getAnalytics } from '../services/crmApi'
import type { Analytics } from '../services/crmApi'
import type { DashboardContext } from './DashboardOverviewPage'
import '../crm.css'

function dateInput(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function metricValue(metric: { value: number; available: boolean } | undefined): string {
  return metric?.available ? metric.value.toLocaleString() : '—'
}

function toUtcStart(day: string): string {
  return new Date(`${day}T00:00:00`).toISOString()
}

function toUtcEnd(day: string): string {
  const end = new Date(`${day}T00:00:00`)
  end.setDate(end.getDate() + 1)
  return end.toISOString()
}

const initialToDay = dateInput(new Date())
const initialMonthStart = (() => {
  const monthAgo = new Date(`${initialToDay}T00:00:00`)
  monthAgo.setDate(monthAgo.getDate() - 29)
  return dateInput(monthAgo)
})()

export function AnalyticsPage() {
  const { search } = useOutletContext<DashboardContext>()
  const [fromDay, setFromDay] = useState(initialMonthStart)
  const [toDay, setToDay] = useState(initialToDay)
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loadedRange, setLoadedRange] = useState('')
  const [error, setError] = useState('')
  const rangeKey = `${fromDay}:${toDay}`
  const loading = loadedRange !== rangeKey

  useEffect(() => {
    let active = true
    const key = `${fromDay}:${toDay}`
    getAnalytics({ date_from: toUtcStart(fromDay), date_to: toUtcEnd(toDay) })
      .then((result) => { if (active) setAnalytics(result) })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Analytics could not be loaded.') })
      .finally(() => { if (active) setLoadedRange(key) })
    return () => { active = false }
  }, [fromDay, toDay])

  const metrics = analytics ? [
    ['Connected accounts', analytics.connected_accounts, 'Current connected Meta accounts'],
    ['Active automations', analytics.active_automations, 'Current active workflows'],
    ['Automation executions', analytics.automation_executions, 'In selected period'],
    ['Successful executions', analytics.successful_executions, 'Meta-confirmed sends'],
    ['Failed executions', analytics.failed_executions, 'In selected period'],
    ['Messages sent', analytics.messages_sent, 'Accepted by Meta'],
    ['Messages received', analytics.messages_received, 'Captured from webhooks'],
    ['Total contacts', analytics.total_contacts, 'Current CRM records'],
    ['New leads', analytics.new_leads, 'Added in selected period'],
    ['Converted leads', analytics.converted_leads, 'Currently converted, updated in period'],
  ] : []
  const maxBars = Math.max(1, ...(analytics?.daily_messages.flatMap((day) => [day.sent, day.received]) ?? [1]))
  const maxWeeklyBars = Math.max(1, ...(analytics?.weekly_messages.flatMap((week) => [week.sent, week.received]) ?? [1]))

  return <div className="dashboard-page-content crm-page">
    <div className="dashboard-welcome-row">
      <div><span className="dashboard-page-eyebrow">WORKSPACE · REPORTING</span><h1>Analytics</h1><p>Metrics calculated from records stored for your organization.</p></div>
      <span className="dashboard-date-chip"><i /> {analytics?.coverage_start ? `DATA FROM ${new Date(analytics.coverage_start).toLocaleDateString()}` : 'NO MESSAGE HISTORY'}</span>
    </div>
    <div className="crm-toolbar">
      <label>From<input type="date" value={fromDay} max={toDay} onChange={(event) => { setError(''); setFromDay(event.target.value) }} /></label>
      <label>To<input type="date" value={toDay} min={fromDay} max={initialToDay} onChange={(event) => { setError(''); setToDay(event.target.value) }} /></label>
      <span className="crm-muted">Select up to 366 days. Historical Meta messages are not imported automatically.</span>
    </div>
    {error && <p className="crm-feedback error" role="alert">{error}</p>}
    {loading && <p className="crm-muted" role="status">Loading organization analytics…</p>}
    {analytics && <>
      <section className="crm-metric-grid" aria-label="Analytics summary">
        {metrics.map(([label, metric, caption]) => <article className="crm-card crm-metric" key={label as string}>
          <span>{label as string}</span><strong>{metricValue(metric as { value: number; available: boolean })}</strong><small>{caption as string}</small>
        </article>)}
      </section>
      <section className="crm-card">
        <div className="crm-card-head"><div><h2>Messages by day</h2><p>{new Date(`${fromDay}T00:00:00`).toLocaleDateString()} – {new Date(`${toDay}T00:00:00`).toLocaleDateString()}</p></div><span className="crm-muted">Recorded messages only</span></div>
        {analytics.daily_messages.some((day) => day.sent || day.received) ? <>
          <div className="crm-chart" role="img" aria-label="Daily sent and received messages">
            {analytics.daily_messages.map((day) => <div className="crm-chart-day" key={day.date} title={`${day.date}: ${day.sent} sent, ${day.received} received`}>
              <div className="crm-chart-bars">
                <i style={{ height: `${Math.max(2, (day.sent / maxBars) * 145)}px` }} />
                <i style={{ height: `${Math.max(2, (day.received / maxBars) * 145)}px` }} />
              </div><small>{new Date(`${day.date}T00:00:00`).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' })}</small>
            </div>)}
          </div>
          <div className="crm-legend"><span><i /> Sent</span><span><i /> Received</span></div>
        </> : <p className="crm-empty">No messages were recorded in this period. Zero means no matching stored records.</p>}
      </section>
      <section className="crm-card">
        <div className="crm-card-head"><div><h2>Messages by week</h2><p>Weekly totals across the selected period</p></div><span className="crm-muted">Recorded messages only</span></div>
        {analytics.weekly_messages.some((week) => week.sent || week.received) ? <>
          <div className="crm-chart" role="img" aria-label="Weekly sent and received messages">
            {analytics.weekly_messages.map((week) => <div className="crm-chart-day" key={week.week_start} title={`Week of ${week.week_start}: ${week.sent} sent, ${week.received} received`}>
              <div className="crm-chart-bars">
                <i style={{ height: `${Math.max(2, (week.sent / maxWeeklyBars) * 145)}px` }} />
                <i style={{ height: `${Math.max(2, (week.received / maxWeeklyBars) * 145)}px` }} />
              </div><small>{new Date(`${week.week_start}T00:00:00`).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' })}</small>
            </div>)}
          </div>
          <div className="crm-legend"><span><i /> Sent</span><span><i /> Received</span></div>
        </> : <p className="crm-empty">No weekly message data is available in this period.</p>}
      </section>
      <div className="crm-inbox-grid">
        <section className="crm-card">
          <div className="crm-card-head"><div><h2>Platform breakdown</h2><p>Messages recorded by connected account platform</p></div></div>
          {analytics.platform_breakdown.length ? <div className="crm-table-wrap"><table className="crm-table"><thead><tr><th>Platform</th><th>Sent</th><th>Received</th></tr></thead><tbody>{analytics.platform_breakdown.map((row) => <tr key={row.platform}><td className="crm-platform">{row.platform}</td><td>{row.sent}</td><td>{row.received}</td></tr>)}</tbody></table></div> : <p className="crm-empty">No platform message data in this period.</p>}
        </section>
        <section className="crm-card">
          <div className="crm-card-head"><div><h2>Automation performance</h2><p>Executions started during the selected period</p></div></div>
          {analytics.automation_performance.length ? <div className="crm-table-wrap"><table className="crm-table"><thead><tr><th>Automation</th><th>Executions</th><th>Sent</th><th>Failed</th></tr></thead><tbody>{analytics.automation_performance.filter((row) => row.name.toLowerCase().includes(search.toLowerCase())).map((row) => <tr key={row.automation_id}><td>{row.name}</td><td>{row.executions}</td><td>{row.successful}</td><td>{row.failed}</td></tr>)}</tbody></table></div> : <p className="crm-empty">No automation executions in this period.</p>}
        </section>
      </div>
      {!analytics.coverage_start && <p className="crm-muted">No message history is stored yet. Connected account metrics and current automation/contact counts remain based on current records.</p>}
    </>}
  </div>
}
