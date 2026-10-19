import React from "react";
import { useDrawerUploadHook } from "../hook/useDrawerUploadHook";

export const DrawerUpload: React.FC = () => {
  const { message, handleUpload, abortUpload, upload, failedFiles } =
    useDrawerUploadHook();

  if (upload.status === "uploading") {
    return (
      <button
        type="button"
        onClick={() => abortUpload()}
        className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-500 transition hover:bg-red-50 hover:text-red-600"
      >
        <span>{message}</span>
        <span className="ml-auto text-xs font-medium">✕ 取消</span>
      </button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-1">
      <label className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition hover:bg-gray-200 hover:text-gray-700">
        <span>{message}</span>
        <input
          hidden
          multiple
          accept=".pdf,.md,.txt,.csv,.xlsx,.docx,.doc,.pptx,.html,.htm"
          type="file"
          onChange={(event) => handleUpload(event.target.files)}
        />
      </label>
      {failedFiles.length > 0 && (
        <div className="ml-3 mt-1 space-y-1 border-l-2 border-red-300 pl-3">
          {failedFiles.map((f) => (
            <p key={f.filename} className="text-xs text-red-500">
              <span className="font-medium">{f.filename}</span>
              <span className="ml-1 text-red-400">— {f.error}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
};
