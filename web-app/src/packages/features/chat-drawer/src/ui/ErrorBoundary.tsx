import React, { Component, ReactNode } from "react";
import { createLogger } from "@ming/core-log";

const log = createLogger("drawer/error-boundary");

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    log.error("Drawer ErrorBoundary caught an error", error, {
      componentStack: errorInfo.componentStack ?? "",
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="flex h-full w-64 flex-col items-center justify-center border-r border-slate-200 bg-white px-4 text-center">
            <p className="text-sm text-slate-500">加载出错，请刷新页面</p>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
