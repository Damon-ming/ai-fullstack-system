// src/vite-env.d.ts
// 告诉 TS 编译器：**把 `vite/client` 的类型定义引入进来**。
/// <reference types="vite/client" />

// 手动告诉 TS：导入`import './xxx.css'`，这个模块导出是字符串。
declare module '*.css' {
  const content: string
  export default content
}

declare module '*.scss' {
  const content: string
  export default content
}

declare module '*.sass' {
  const content: string
  export default content
}

declare module '*.less' {
  const content: string
  export default content
}