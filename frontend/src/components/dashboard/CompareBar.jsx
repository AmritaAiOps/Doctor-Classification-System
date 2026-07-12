// Two-segment horizontal bar for simple A-vs-B comparisons (OP vs IP,
// Domestic vs International, Cash vs Credit). Not for anything that can
// exceed 100% of a fixed capacity -- see OccupancyBar for that case.
function CompareBar({ segments, formatFn }) {
  const total = segments.reduce((sum, s) => sum + (s.value || 0), 0)

  return (
    <div className="compare-bar">
      <div className="compare-bar__track">
        {segments.map((s, i) => (
          <div
            key={i}
            className={`compare-bar__segment compare-bar__segment--${s.color || 'blue'}`}
            style={{ width: total > 0 ? `${(s.value / total) * 100}%` : `${100 / segments.length}%` }}
          />
        ))}
      </div>
      <div className="compare-bar__legend">
        {segments.map((s, i) => (
          <div className="compare-bar__legend-item" key={i}>
            <span className={`compare-bar__dot compare-bar__dot--${s.color || 'blue'}`} aria-hidden="true" />
            {s.label}: <strong>{formatFn ? formatFn(s.value) : s.value}</strong>
          </div>
        ))}
      </div>
    </div>
  )
}

export default CompareBar
