// src/app/main/src/main.tsx
import './compat'
import './index.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { createLogger } from '@ming/core-log'
import { bootstrap } from './bootstrap'
import { App } from './App'

const log = createLogger("app/main")

async function startApp() {
  try {
    // 1. 确保在应用渲染前完成最高优先级的初始化
    await bootstrap()

    // 2. 网络等基础层就绪后，挂载 React App
    const rootElement = document.getElementById('root')
    if (!rootElement) throw new Error('Root element #root not found')

    ReactDOM.createRoot(rootElement).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    )
  } catch (error) {
    log.error('Failed to start application', error)
    const rootElement = document.getElementById('root')
    if (rootElement) {
      rootElement.innerHTML = '<main style="min-height:100vh;display:grid;place-items:center;padding:24px;font-family:system-ui;color:#334155;background:#f8fafc"><section><h1 style="margin:0 0 8px;font-size:20px">应用启动失败</h1><p style="margin:0;color:#64748b">请刷新页面重试；详细错误信息请查看浏览器控制台。</p></section></main>'
    }
  }
}

// 启动应用（入口点，错误在 startApp 内部已处理）
void startApp()
