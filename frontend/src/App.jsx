import { useEffect, useRef, useState } from 'react'
import './App.css'
import Dropzone from './components/Dropzone'
import UploadedFilesList from './components/UploadedFilesList'
import ReportChecklist from './components/ReportChecklist'
import SummaryCard from './components/SummaryCard'
import { REPORT_TYPES, PROCESSING_STEPS } from './reports'

function todayIso() {
  const d = new Date()
  const offset = d.getTimezoneOffset()
  return new Date(d.getTime() - offset * 60000).toISOString().slice(0, 10)
}

function App() {
  const [droppedFiles, setDroppedFiles] = useState([])
  const [rejectedNames, setRejectedNames] = useState([])
  const [detecting, setDetecting] = useState(false)
  const [detectError, setDetectError] = useState(null)
  const [candidates, setCandidates] = useState([])
  const [autoMatches, setAutoMatches] = useState({})
  const [assignments, setAssignments] = useState({})
  const manualOverrides = useRef(new Set())

  const [date, setDate] = useState(todayIso)
  const [dateAutoDetected, setDateAutoDetected] = useState(false)
  const dateManuallySet = useRef(false)
  const [phase, setPhase] = useState('idle') // idle | processing | success | warning | error
  const [stepIndex, setStepIndex] = useState(0)
  const [result, setResult] = useState(null)
  const [errorInfo, setErrorInfo] = useState(null)
  const stepTimer = useRef(null)

  useEffect(() => () => clearInterval(stepTimer.current), [])

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

      if (data.detected_date && !dateManuallySet.current) {
        setDate(data.detected_date)
        setDateAutoDetected(true)
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

  function handleAssign(reportType, candidateId) {
    manualOverrides.current.add(reportType)
    setAssignments((prev) => ({ ...prev, [reportType]: candidateId }))
  }

  const allAssigned = REPORT_TYPES.every((rt) => !!assignments[rt])
  const canProcess = allAssigned && !!date && phase !== 'processing' && !detecting

  async function handleProcess() {
    setPhase('processing')
    setStepIndex(0)
    setResult(null)
    setErrorInfo(null)

    stepTimer.current = setInterval(() => {
      setStepIndex((i) => (i + 1) % PROCESSING_STEPS.length)
    }, 1100)

    const form = new FormData()
    droppedFiles.forEach((f) => form.append('files', f))
    const mapping = Object.fromEntries(REPORT_TYPES.map((rt) => [rt, assignments[rt]]))
    form.append('mapping', JSON.stringify(mapping))
    form.append('date', date)

    try {
      const res = await fetch('/process', { method: 'POST', body: form })
      const data = await res.json()
      clearInterval(stepTimer.current)

      if (data.status === 'error') {
        setErrorInfo({ failed_file: data.failed_file, reason: data.reason })
        setPhase('error')
        return
      }

      setResult(data)
      setPhase(data.status === 'warning' ? 'warning' : 'success')
    } catch (err) {
      clearInterval(stepTimer.current)
      setErrorInfo({ failed_file: null, reason: 'Could not reach the server. Check your connection and try again.' })
      setPhase('error')
    }
  }

  function handleDateChange(value) {
    dateManuallySet.current = true
    setDateAutoDetected(false)
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
    setDate(todayIso())
    setDateAutoDetected(false)
    dateManuallySet.current = false
    setPhase('idle')
    setResult(null)
    setErrorInfo(null)
  }

  const showForm = phase === 'idle' || phase === 'processing' || phase === 'error'
  const detectedCount = REPORT_TYPES.filter((rt) => !!assignments[rt]).length

  return (
    <div className="app">
      <header className="app__header">
        <h1>Daily HIS Report Automation</h1>
        <p className="app__subtitle">
          Drop today's reports below — one combined workbook, separate files, or a mix.
        </p>
      </header>

      {phase === 'error' && errorInfo && (
        <div className="banner banner--error">
          <div className="banner__title">Processing failed{errorInfo.failed_file ? `: ${errorInfo.failed_file}` : ''}</div>
          <div className="banner__body">{errorInfo.reason}</div>
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
          <SummaryCard summary={result.summary} />
          <div className="result-actions">
            <a className="button button--primary" href={result.download_url} download>
              Download Final output.xlsx
            </a>
            <button className="button button--secondary" onClick={handleReset}>
              Start over
            </button>
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
            <div className="panel__counter">
              {detectedCount} of {REPORT_TYPES.length} reports ready
            </div>
          </section>

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
