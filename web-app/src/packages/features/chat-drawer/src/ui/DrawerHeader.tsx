import React from "react";
import { useDrawerHeaderHook } from "../hook/useDrawerHeaderHook";

export const DrawerHeader: React.FC = () => {
  const { toggle } = useDrawerHeaderHook();
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">✦</span>
        <strong className="text-sm font-semibold text-slate-800">
          Ming AI
        </strong>
      </div>
      <button
        type="button"
        className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        onClick={toggle}
        aria-label="折叠抽屉"
      >
        ‹
      </button>
    </div>
  );
};
