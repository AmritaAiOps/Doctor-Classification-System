import OccupancyCard from './OccupancyCard'
import VolumesCard from './VolumesCard'
import BillingCard from './BillingCard'
import CollectionCard from './CollectionCard'
import { formatDateDisplay } from '../../format'

// Read-only sanity-check view -- every number here comes straight from the
// same `values` dict used to write the Final output Excel. No editing here;
// corrections happen only in the Category Review panel.
function ResultsDashboard({ values, categoryReview, date }) {
  if (!values) return null

  const needsReviewCount =
    (categoryReview?.possible_matches?.length || 0) + (categoryReview?.unmatched?.length || 0)

  return (
    <div className="dashboard">
      {needsReviewCount > 0 && (
        <div className="banner banner--warning banner--compact">
          <div className="banner__body">
            {needsReviewCount} categor{needsReviewCount === 1 ? 'y' : 'ies'} need review — numbers below may change.{' '}
            <a href="#category-review">Jump to Category Review</a>
          </div>
        </div>
      )}

      <div className="dashboard__header">
        <span className="dashboard__date-label">Reporting date</span>
        <span className="dashboard__date-value">{formatDateDisplay(date)}</span>
      </div>

      <div className="dashboard__grid">
        <OccupancyCard values={values} />
        <VolumesCard values={values} />
        <BillingCard values={values} />
        <CollectionCard values={values} />
      </div>
    </div>
  )
}

export default ResultsDashboard
