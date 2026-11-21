'use client'

import { useState } from 'react'
import { captureDemo, compareDemo, demoReport, type DemoSnapshot, type DemoValue } from './demo.js'

function display(value: DemoValue): string {
  if (value === null) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export function DemoWorkbench({scenario,snapshot}: {scenario: string; snapshot: DemoSnapshot | null}) {
  const [baseline, setBaseline] = useState<DemoSnapshot | null>(null)
  const [notice, setNotice] = useState('')
  const comparison = baseline && snapshot ? compareDemo(baseline, snapshot) : null

  function saveBaseline() {
    if (!snapshot) return
    try {
      setBaseline(captureDemo(snapshot))
      setNotice('Baseline saved for this session.')
    } catch {
      setNotice('This scenario exceeds the report limits.')
    }
  }

  function download() {
    if (!snapshot) return
    try {
      const report = demoReport(scenario, snapshot, baseline)
      const url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'], {type:'application/json'}))
      const link = document.createElement('a')
      link.href = url
      link.download = `${scenario}-demo-report.json`
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice('Demo report download started.')
    } catch {
      setNotice('The demo report could not be downloaded.')
    }
  }

  return <div className="demo-workbench">
    <h3>Compare scenarios</h3>
    <p>Save a baseline, change the inputs, and compare the results. Your run stays in this browser unless you download it.</p>
    <div className="row">
      <button type="button" className="btn" disabled={!snapshot} onClick={saveBaseline}>{baseline ? 'Replace baseline' : 'Save baseline'}</button>
      <button type="button" className="btn" disabled={!snapshot} onClick={download}>Download demo JSON</button>
      {baseline && <button type="button" className="btn" onClick={() => { setBaseline(null); setNotice('Baseline cleared.') }}>Clear baseline</button>}
    </div>
    {notice && <p className="widget-note" role="status">{notice}</p>}
    {comparison && <div className="demo-comparison" role="region" aria-label="Scenario comparison" tabIndex={0}>
      <table>
        <caption>Baseline and current values</caption>
        <thead><tr><th scope="col">Field</th><th scope="col">Baseline</th><th scope="col">Current</th></tr></thead>
        {([['Inputs',comparison.inputs],['Results',comparison.results]] as const).map(([label,rows]) => <tbody key={label}>
          <tr><th scope="rowgroup" colSpan={3}>{label}</th></tr>
          {rows.map(row => <tr key={row.field}>
            <th scope="row">{row.field}{row.changed && <span className="demo-change">Changed</span>}</th>
            <td>{display(row.baseline)}</td><td>{display(row.current)}</td>
          </tr>)}
        </tbody>)}
      </table>
    </div>}
  </div>
}
