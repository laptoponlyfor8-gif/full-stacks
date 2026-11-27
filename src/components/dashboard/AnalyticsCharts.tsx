import { ArrowDownRight, ArrowUpRight, MoreHorizontal } from 'lucide-react'

function Chart({ title, subtitle, data, color, value, change, label }: { title: string; subtitle: string; data: number[]; color: string; value: string; change: string; label: string }) {
  const width = 520
  const height = 150
  const points = data.map((point, index) => `${(index / (data.length - 1)) * width},${height - (point / 100) * (height - 12)}`).join(' ')
  const areaPoints = `0,${height} ${points} ${width},${height}`
  const marker = data[data.length - 1]
  const markerY = height - (marker / 100) * (height - 12)

  return <article className="dashboard-chart-card">
    <div className="dashboard-chart-header"><div><h3>{title}</h3><span>{subtitle}</span></div><button type="button" aria-label={`${title} options`}><MoreHorizontal size={18} /></button></div>
    <div className="dashboard-chart-metric"><strong>{value}</strong><span className="dashboard-chart-change"><ArrowUpRight size={14} />{change}</span><span className="dashboard-chart-demo">DEMO</span></div>
    <div className="dashboard-chart" role="img" aria-label={`${title} demo chart: ${label}`}>
      <div className="dashboard-chart-y"><span>100</span><span>75</span><span>50</span><span>25</span><span>0</span></div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id={`fill-${color}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".17" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient></defs>
        {[0, 25, 50, 75, 100].map((line) => <line key={line} x1="0" x2={width} y1={height - (line / 100) * (height - 12)} y2={height - (line / 100) * (height - 12)} stroke="#edf0f6" strokeDasharray="3 5" />)}
        <polygon points={areaPoints} fill={`url(#fill-${color})`} />
        <polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        <circle cx={width} cy={markerY} r="4" fill="#fff" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="dashboard-chart-x"><span>MON</span><span>TUE</span><span>WED</span><span>THU</span><span>FRI</span><span>SAT</span><span>SUN</span></div>
    </div>
  </article>
}

export function AnalyticsCharts({ activityData, dmData }: { activityData: number[]; dmData: number[] }) {
  return <div className="dashboard-charts-grid">
    <Chart title="Comments activity" subtitle="Comments received over the last 7 days" data={activityData} color="#315fe8" value="2,481" change="18.6%" label="Daily comments" />
    <Chart title="DM performance" subtitle="Automated messages delivered over the last 7 days" data={dmData} color="#7665dc" value="1,936" change="12.4%" label="Daily DMs sent" />
  </div>
}

export function SuccessRateCard() {
  return <article className="dashboard-success-card"><div className="dashboard-chart-header"><div><h3>Automation success rate</h3><span>Replies delivered successfully</span></div><button type="button" aria-label="Success rate options"><MoreHorizontal size={18} /></button></div><div className="success-rate-content"><div className="success-ring"><div><strong>94.8%</strong><span>SUCCESS</span></div></div><div className="success-rate-copy"><span><i className="success-dot" />Successful replies <b>1,836</b></span><span><i className="success-dot muted" />Needs attention <b>100</b></span><small><ArrowDownRight size={13} />Sample performance, demo only</small></div></div></article>
}
