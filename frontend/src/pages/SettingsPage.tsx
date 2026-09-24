import { appConfig } from '../lib/config'

export function SettingsPage() {
  return (
    <div className="settings-page">
      <div className="settings-heading">
        <p className="eyebrow">Configuration</p>
        <h1>Settings</h1>
        <p>Runtime values are read from the active Vite environment.</p>
      </div>

      <section className="settings-card" aria-labelledby="api-settings">
        <div>
          <span className="settings-number">01</span>
          <div>
            <h2 id="api-settings">API connection</h2>
            <p>Backend endpoint and network timeout used by the shared client.</p>
          </div>
        </div>
        <dl className="settings-values">
          <div>
            <dt>Base URL</dt>
            <dd>{appConfig.apiBaseUrl}</dd>
          </div>
          <div>
            <dt>Request timeout</dt>
            <dd>{appConfig.apiTimeoutMs.toLocaleString()} ms</dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{appConfig.environment}</dd>
          </div>
        </dl>
      </section>

      <div className="settings-help">
        Override local values in <code>.env.local</code> and restart the dev server.
      </div>
    </div>
  )
}
