import React from "react";
import { useDrawerUploadHook } from "../hook/useDrawerUploadHook";

export const DrawerUpload: React.FC = () => {
  const { message, handleUpload } = useDrawerUploadHook();
  return (
    <label className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition hover:bg-gray-200 hover:text-gray-700">
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
