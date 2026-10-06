import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles.css'
import { applyDensity, applyZoom, loadDensity, loadZoom } from './display'
import { applyTheme, loadTheme } from './theme'

applyTheme(loadTheme())
applyZoom(loadZoom())
applyDensity(loadDensity())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
