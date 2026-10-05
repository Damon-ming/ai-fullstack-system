import React from "react";
import { useDrawerUploadHook } from "../hook/useDrawerUploadHook";

export const DrawerUpload: React.FC = () => {
  const { upload, message, handleUpload } = useDrawerUploadHook();
  return (
    <label className="mx-3 flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-slate-300 px-4 py-2.5 text-sm text-slate-600 transition hover:border-slate-400 hover:bg-slate-50 hover:text-slate-700">
      <span>{message}</span>
      <input
        hidden
        multiple
        accept=".pdf,.xls,.xlsx,.png,.jpg,.jpeg,.csv"
        type="file"
        onChange={(event) => handleUpload(event.target.files)}
      />
    </label>
  );
};
