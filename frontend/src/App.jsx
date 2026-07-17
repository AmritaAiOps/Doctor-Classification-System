import { useEffect, useRef, useState } from 'react'
import './App.css'
import Dropzone from './components/Dropzone'
import UploadedFilesList from './components/UploadedFilesList'
import ReportChecklist from './components/ReportChecklist'
import ResultsDashboard from './components/dashboard/ResultsDashboard'
import CategoryReviewPanel from './components/CategoryReviewPanel'
import { REPORT_TYPES, PROCESSING_STEPS } from './reports'

function App() {
  const [droppedFiles, setDroppedFiles] = useState([])
  const [rejectedNames, setRejectedNames] = useState([])
  const [detecting, setDetecting] = useState(false)
  const [detectError, setDetectError] = useState(null)
  const [candidates, setCandidates] = useState([])
  const [autoMatches, setAutoMatches] = useState({})
  const [assignments, setAssignments] = useState({})
  const manualOverrides = useRef(new Set())

  const [date, setDate] = useState('')
  const [dateAutoDetected, setDateAutoDetected] = useState(false)
  const [dateConflict, setDateConflict] = useState(false)
  const dateManuallySet = useRef(false)
  const [phase, setPhase] = useState('idle') // idle | processing | success | warning | error
  const [stepIndex, setStepIndex] = useState(0)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [errorInfo, setErrorInfo] = useState(null)
  const stepTimer = useRef(null)
  const progressTimer = useRef(null)

  const [showSettings, setShowSettings] = useState(false)
  const [outputDir, setOutputDir] = useState('')
  const [settingsError, setSettingsError] = useState(null)
  const [browsing, setBrowsing] = useState(false)

  useEffect(() => () => {
    clearInterval(stepTimer.current)
    clearInterval(progressTimer.current)
  }, [])

  useEffect(() => {
    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => setOutputDir(data.output_dir))
      .catch(() => {})
  }, [])

  async function saveOutputDir(path) {
    setSettingsError(null)
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: path }),
      })
      const data = await res.json()
      if (!res.ok) {
        setSettingsError(data.detail || 'Could not save that folder.')
        return
      }
      setOutputDir(data.output_dir)
    } catch {
      setSettingsError('Could not reach the server to save that setting.')
    }
  }

  async function handleBrowse() {
    if (!window.pywebview?.api?.choose_folder) {
      setSettingsError('Folder picker is only available in the desktop app.')
      return
    }
    setBrowsing(true)
    setSettingsError(null)
    try {
      const path = await window.pywebview.api.choose_folder()
      if (path) await saveOutputDir(path)
    } finally {
      setBrowsing(false)
    }
  }

  useEffect(() => {
    if (droppedFiles.length === 0) {
      setCandidates([])
      setAutoMatches({})
      setAssignments({})
      manualOverrides.current = new Set()
      return
    }
    runDetect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [droppedFiles])

  async function runDetect() {
    setDetecting(true)
    setDetectError(null)
    const form = new FormData()
    droppedFiles.forEach((f) => form.append('files', f))

    try {
      const res = await fetch('/detect', { method: 'POST', body: form })
      const data = await res.json()
      setDetecting(false)

      if (data.file_error) {
        setDetectError(`${data.file_error.source_file}: ${data.file_error.reason}`)
        return
      }

      const matchMap = Object.fromEntries(data.matches.map((m) => [m.report_type, m]))
      setCandidates(data.candidates)
      setAutoMatches(matchMap)

      setDateConflict(!!data.date_conflict)
      if (data.detected_date && !dateManuallySet.current) {
        setDate(data.detected_date)
        setDateAutoDetected(true)
      } else if (!dateManuallySet.current) {
        setDate('')
        setDateAutoDetected(false)
      }

      const validIds = new Set(data.candidates.map((c) => c.id))
      setAssignments((prev) => {
        const next = { ...prev }
        for (const rt of REPORT_TYPES) {
          if (next[rt] && !validIds.has(next[rt])) {
            delete next[rt]
            manualOverrides.current.delete(rt)
          }
          if (!manualOverrides.current.has(rt)) {
            next[rt] = matchMap[rt] ? matchMap[rt].candidate_id : next[rt] || ''
          }
        }
        return next
      })
    } catch (err) {
      setDetecting(false)
      setDetectError('Could not reach the server to detect reports. Check your connection and try again.')
    }
  }

  function handleFilesAdded(newFiles) {
    setRejectedNames([])
    setDroppedFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name))
      const merged = [...prev]
      for (const f of newFiles) {
        if (!existingNames.has(f.name)) merged.push(f)
      }
      return merged
    })
  }

  function handleFilesRejected(names) {
    setRejectedNames(names)
  }

  function handleRemoveFile(name) {
    setDroppedFiles((prev) => prev.filter((f) => f.name !== name))
  }

  function handleClearAllFiles() {
    setDroppedFiles([])
    setRejectedNames([])
    setDetectError(null)
  }

  function handleAssign(reportType, candidateId) {
    manualOverrides.current.add(reportType)
    setAssignments((prev) => ({ ...prev, [reportType]: candidateId }))
  }

  const allAssigned = REPORT_TYPES.every((rt) => !!assignments[rt])
  const canProcess = allAssigned && !!date && phase !== 'processing' && !detecting

  async function handleProcess() {
    setPhase('processing')
    setStepIndex(0)
    setProgress(0)
    setResult(null)
    setErrorInfo(null)

    stepTimer.current = setInterval(() => {
      setStepIndex((i) => (i + 1) % PROCESSING_STEPS.length)
    }, 1100)
    // Estimated progress: eases toward 95% while the server works, jumps to
    // 100% when the response lands (the API gives no real progress events).
    progressTimer.current = setInterval(() => {
      setProgress((p) => Math.min(95, p + (95 - p) * 0.06 + 0.3))
    }, 250)

    const form = new FormData()
    droppedFiles.forEach((f) => form.append('files', f))
    const mapping = Object.fromEntries(REPORT_TYPES.map((rt) => [rt, assignments[rt]]))
    form.append('mapping', JSON.stringify(mapping))
    form.append('date', date)

    try {
      const res = await fetch('/process', { method: 'POST', body: form })
      const data = await res.json()
      clearInterval(stepTimer.current)
      clearInterval(progressTimer.current)
      setProgress(100)

      if (data.status === 'error') {
        setErrorInfo({
          failed_file: data.failed_file,
          reason: data.reason,
          code: data.error?.code,
          category: data.error?.category,
        })
        setPhase('error')
        return
      }

      setResult(data)
      setPhase(data.status === 'warning' ? 'warning' : 'success')
    } catch (err) {
      clearInterval(stepTimer.current)
      clearInterval(progressTimer.current)
      setErrorInfo({ failed_file: null, reason: 'Could not reach the server. Check your connection and try again.' })
      setPhase('error')
    }
  }

  async function handleAcceptCategories(resolutions) {
    try {
      const res = await fetch('/category-review/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: result.file_id, resolutions }),
      })
      const data = await res.json()
      if (data.status === 'error') {
        setErrorInfo({ failed_file: data.failed_file, reason: data.reason })
        setPhase('error')
        return
      }
      setResult(data)
      setPhase(data.status === 'warning' ? 'warning' : 'success')
    } catch (err) {
      setErrorInfo({ failed_file: null, reason: 'Could not reach the server to apply that override.' })
      setPhase('error')
    }
  }

  async function handleResetBaseline() {
    try {
      const res = await fetch('/api/schema-baseline/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: errorInfo.category }),
      })
      const data = await res.json()
      if (data.success) {
        setErrorInfo(null)
        setPhase('idle')
      }
    } catch {
      /* banner already visible; user can retry */
    }
  }

  function handleDateChange(value) {
    dateManuallySet.current = true
    setDateAutoDetected(false)
    setDateConflict(false)
    setDate(value)
  }

  function handleReset() {
    setDroppedFiles([])
    setRejectedNames([])
    setCandidates([])
    setAutoMatches({})
    setAssignments({})
    manualOverrides.current = new Set()
    setDetectError(null)
    setDate('')
    setDateAutoDetected(false)
    setDateConflict(false)
    dateManuallySet.current = false
    setPhase('idle')
    setResult(null)
    setErrorInfo(null)
  }

  const showForm = phase === 'idle' || phase === 'processing' || phase === 'error'
  const detectedCount = REPORT_TYPES.filter((rt) => !!assignments[rt]).length

  return (
    <div className={`app ${(phase === 'success' || phase === 'warning') ? 'app--wide' : ''}`}>
      <header className="app__header">
        <h1>Daily HIS Report Automation</h1>
        <p className="app__subtitle">
          Drop today's reports below — one combined workbook, separate files, or a mix.
        </p>
        <button
          type="button"
          className="settings-toggle"
          onClick={() => setShowSettings((v) => !v)}
        >
          <span className="settings-toggle__icon" aria-hidden="true">📁</span>
          Output folder
        </button>
      </header>

      {showSettings && (
        <section className="panel settings-panel">
          <div className="panel__row">
            <span className="panel__label">Save reports to</span>
            <span className="settings-panel__path" title={outputDir}>{outputDir || 'Loading…'}</span>
            <button
              type="button"
              className="button button--tiny button--primary"
              disabled={browsing}
              onClick={handleBrowse}
            >
              {browsing ? 'Choosing…' : 'Browse…'}
            </button>
          </div>
          {settingsError && (
            <div className="banner banner--error banner--compact">
              <div className="banner__body">{settingsError}</div>
            </div>
          )}
        </section>
      )}

      {phase === 'error' && errorInfo && (
        <div className="banner banner--error">
          <div className="banner__title">Processing failed{errorInfo.failed_file ? `: ${errorInfo.failed_file}` : ''}</div>
          <div className="banner__body">{errorInfo.reason}</div>
          {errorInfo.code === 'SCHEMA_MISMATCH' && (
            <button
              type="button"
              className="button button--tiny button--secondary"
              onClick={handleResetBaseline}
            >
              Reset baseline for {errorInfo.category}
            </button>
          )}
        </div>
      )}

      {(phase === 'success' || phase === 'warning') && result && (
        <>
          {phase === 'warning' && (
            <div className="banner banner--warning">
              <div className="banner__title">Needs manual review</div>
              <ul className="banner__list">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="result-actions">
            <a className="button button--primary" href={result.download_url} download>
              Download Final output.xlsx
            </a>
            <button className="button button--secondary" onClick={handleReset}>
              Start over
            </button>
          </div>
          <div className="results-split">
            <div className="results-split__col">
              <CategoryReviewPanel categoryReview={result.category_review} onAccept={handleAcceptCategories} />
            </div>
            <div className="results-split__col">
              <ResultsDashboard values={result.values} categoryReview={result.category_review} date={date} />
            </div>
          </div>
        </>
      )}

      {showForm && (
        <>
          <section className="panel">
            <div className="panel__row">
              <label htmlFor="report-date" className="panel__label">
                Report date
              </label>
              <input
                id="report-date"
                type="date"
                value={date}
                disabled={phase === 'processing'}
                onChange={(e) => handleDateChange(e.target.value)}
              />
              {dateAutoDetected && <span className="checklist__tag checklist__tag--auto">detected from files</span>}
            </div>
            {dateConflict && (
              <div className="banner banner--error banner--compact">
                <div className="banner__body">
                  Uploaded files have conflicting dates in their filenames. Please confirm the correct report date manually.
                </div>
              </div>
            )}
            <div className="panel__counter">
              {detectedCount} of {REPORT_TYPES.length} reports ready
            </div>
          </section>

          {droppedFiles.length > 0 && (
            <div className="clear-files-row">
              <button
                type="button"
                className="button button--tiny button--secondary"
                disabled={phase === 'processing'}
                onClick={handleClearAllFiles}
              >
                Clear all files
              </button>
            </div>
          )}

          <Dropzone disabled={phase === 'processing'} onFilesAdded={handleFilesAdded} onRejected={handleFilesRejected} />

          {rejectedNames.length > 0 && (
            <div className="banner banner--error banner--compact">
              <div className="banner__body">
                Not an Excel file, skipped: {rejectedNames.join(', ')}
              </div>
            </div>
          )}

          <UploadedFilesList files={droppedFiles} disabled={phase === 'processing'} onRemove={handleRemoveFile} />

          {detectError && (
            <div className="banner banner--error banner--compact">
              <div className="banner__body">{detectError}</div>
            </div>
          )}

          {detecting && <p className="detecting-status">Scanning uploaded files for reports...</p>}

          {droppedFiles.length > 0 && !detecting && (
            <section className="checklist-section">
              <h2 className="checklist-section__title">Detected Reports</h2>
              <ReportChecklist
                candidates={candidates}
                assignments={assignments}
                autoMatches={autoMatches}
                disabled={phase === 'processing'}
                onAssign={handleAssign}
              />
            </section>
          )}

          <section className="process-section">
            {phase === 'processing' ? (
              <div className="processing-status">
                <span className="spinner" aria-hidden="true" />
                <span>{PROCESSING_STEPS[stepIndex]}</span>
                <span className="processing-status__pct">{Math.round(progress)}%</span>
                <div className="progress-bar">
                  <div className="progress-bar__fill" style={{ width: `${progress}%` }} />
                </div>
              </div>
            ) : (
              <button className="button button--primary button--large" disabled={!canProcess} onClick={handleProcess}>
                Process
              </button>
            )}
            {phase === 'error' && (
              <button className="button button--secondary" onClick={handleReset}>
                Start over
              </button>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default App
