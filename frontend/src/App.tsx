import { StatusCard } from './components/StatusCard'
import { getApiBaseUrl } from './api/client'

export default function App() {
  const appName = import.meta.env.VITE_APP_NAME || 'Johnny'

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="eyebrow">Fullstack Preset</p>
        <h1>{appName}</h1>
        <p className="lead">
          This frontend was generated from the scaffold CLI prototype and is wired to talk to the backend API.
        </p>
      </section>

      <section className="grid">
        <StatusCard title="Frontend" value="React + Vite" detail="A minimal shell ready for routes, state, and API hooks." />
        <StatusCard title="Backend API" value={getApiBaseUrl()} detail="Default API base URL used by the frontend client." />
      </section>
    </main>
  )
}
