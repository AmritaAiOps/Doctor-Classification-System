import { formatInr, formatPercent, formatCount } from '../format'

function SummaryCard({ summary }) {
  const items = [
    { label: 'Bed Occupancy', value: formatPercent(summary['Bed Occupancy %']) },
    { label: 'OP Encounters', value: formatCount(summary['OP Encounters']) },
    { label: 'Total Billing', value: formatInr(summary['Total Billing']) },
    { label: 'AEPL Billing', value: formatInr(summary['AEPL Billing']) },
  ]

  return (
    <div className="summary-card">
      <h2 className="summary-card__title">Today's numbers — check before downloading</h2>
      <div className="summary-card__grid">
        {items.map((item) => (
          <div className="summary-card__item" key={item.label}>
            <div className="summary-card__value">{item.value}</div>
            <div className="summary-card__label">{item.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default SummaryCard
