import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useSearchParams } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import ChatPage from './pages/ChatPage'
import SettingsPage from './pages/SettingsPage'
import WorkspacePickerPage from './pages/WorkspacePickerPage'

function LoginWithParams() {
  const [params] = useSearchParams()
  const error = params.get('error')
  return <LoginPage error={error} />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginWithParams />} />
        <Route path="/choose-workspace" element={<WorkspacePickerPage />} />
        <Route path="/" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
