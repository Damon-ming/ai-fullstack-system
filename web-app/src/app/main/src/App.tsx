// src/app/main/src/App.tsx
import React from 'react'
import { DataProvider } from '@ming/data-layer'
import { ChatPage } from '@ming/feature-chat'

export const App: React.FC = () => {
  return (
    <DataProvider>
      <ChatPage />
    </DataProvider>
  )
}