// src/packages/data-layer/src/provider.tsx
// React 核心库和状态管理 Hook
import React, { useState } from "react";
// QueryClient: react-query 的客户端类，负责缓存、请求管理等
// QueryClientProvider: react-query 的 Context Provider，让子组件能使用查询功能
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// 作用：定义组件的 Props 类型，children 是 React 的子节点（可以是任何 React 可渲染的内容）。
export interface DataProviderProps {
  children: React.ReactNode;
}

/**
 * 数据层统一 Context Provider
 * 隐藏底层 @tanstack/react-query 的实现细节
 * 
 * 直接创建（每次渲染都会创建新实例）
 * 使用 useState（只在第一次渲染时创建）
  // function Welcome(props: { name: string })  // props 就是参数
*/
// 调用组件
/* <Button text="Click me" /> */
// 此时才执行！函数被调用，生成 React 元素
// 箭头函数: 方法通常指对象里的函数，如 obj.method()。,函数是独立的可调用值。

export const DataProvider: React.FC<DataProviderProps> = ({ children }) => {
  // 使用 useState 确保 QueryClient 实例在组件生命周期内唯一
  // 数据缓存共享
  // [] 是解构模式
  // 对象解构	数组解构
  // 语法	{ a, b }	[a, b]
  // 取值方式	按属性名	按位置
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 1000 * 60 * 5, // 5分钟数据过期机制
          },
        },
      }),
  );

  // <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  //  是 React 的 Context Provider 语法，它把 queryClient 实例注入到组件树中，让所有子组件都能访问到。
  // 这个 client 是 QueryClientProvider 的"参数名"
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};
