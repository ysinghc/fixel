import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { RunLayout } from './layout/RunLayout'
import { Shell } from './layout/Shell'
import { BenchmarkPage } from './pages/BenchmarkPage'
import { FindingPage } from './pages/FindingPage'
import { FixPage } from './pages/FixPage'
import { Home } from './pages/Home'
import { LabelPage } from './pages/LabelPage'
import { NotFound } from './pages/NotFound'
import { RunPage } from './pages/RunPage'
import { Runs } from './pages/Runs'
import { ScanSetup } from './pages/ScanSetup'
import { ScreenPage } from './pages/ScreenPage'
import { ScreensPage } from './pages/ScreensPage'

/** One task per page, each with its own URL (see docs/UI_DESIGN.md). */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="scan" element={<ScanSetup />} />
          <Route path="runs" element={<Runs />} />
          <Route path="runs/:run" element={<RunLayout />}>
            <Route index element={<RunPage />} />
            <Route path="screens" element={<ScreensPage />} />
            <Route path="screens/:state" element={<ScreenPage />} />
            <Route path="findings/:key" element={<FindingPage />} />
            <Route path="fixes/:fix" element={<FixPage />} />
          </Route>
          <Route path="label" element={<LabelPage />} />
          <Route path="benchmark" element={<BenchmarkPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
