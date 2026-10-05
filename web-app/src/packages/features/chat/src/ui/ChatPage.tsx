import { ChatDrawer } from "@ming/features-chat-drawer";
import { ChatChatroom } from "@ming/features-chat-chatroom";
import React, { useMemo } from "react";
import { useChatPageHook } from "../hook";
import { useTranslation } from "@ming/i18n";

export const ChatPage: React.FC = () => {
  const { t } = useTranslation("chat-page");
  const {
    chatSessionId,
    searchOpen,
    searchKeyword,
    closeSearch,
    setSearchKeyword,
    searchResults,
    accountOpen,
    draftName,
    closeAccount,
    setDraftName,
    saveAccount,
    loadHistory,
    upload,
    closeUpload,
  } = useChatPageHook();

  // store 不再持有 message —— UI 层根据 status + 结果数据生成文案
  const uploadMessage = useMemo(() => {
    switch (upload.status) {
      case "uploading":
        return t("upload.uploading");
      case "error":
        return t("upload.error");
      case "success": {
        const allIndexed =
          upload.files.length === 0 ||
          upload.files.every((f) => f.indexed || f.duplicate);
        return allIndexed
          ? t("upload.successAllIndexed")
          : t("upload.successPartial");
      }
      default:
        return "";
    }
  }, [upload.status, upload.files, t]);

  return (
    <div className="relative flex h-full w-full overflow-hidden font-sans text-slate-800">
      <ChatDrawer />
      <ChatChatroom key={chatSessionId} />

      {/* 搜索弹窗 */}
      {searchOpen && (
        <div
          className="fixed inset-0 z-30 grid place-items-center bg-slate-900/30 backdrop-blur-sm"
          onClick={closeSearch}
        >
          <section
            className="w-full max-w-[420px] rounded-2xl bg-white/94 p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <input
              autoFocus
              value={searchKeyword}
              onChange={(event) => setSearchKeyword(event.target.value)}
              placeholder={t("search.placeholder")}
              className="mt-2 block w-full rounded-lg border border-slate-200 bg-white/80 px-3 py-3 text-slate-700 outline-0 focus:border-indigo-300"
            />
            <div className="mt-3 max-h-[280px] overflow-auto">
              {searchKeyword.trim() && searchResults.length === 0 && (
                <p className="py-2.5 text-center text-sm text-slate-400">
                  {t("search.noResults")}
                </p>
              )}
              {searchResults.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    loadHistory(item.id);
                    closeSearch();
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-slate-700 hover:bg-indigo-50"
                >
                  <strong className="min-w-0 flex-1 truncate">
                    {item.title}
                  </strong>
                  <small className="text-slate-400">{item.meta}</small>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* 账户弹窗 */}
      {accountOpen && (
        <div
          className="fixed inset-0 z-30 grid place-items-center bg-slate-900/30 backdrop-blur-sm"
          onClick={closeAccount}
        >
          <section
            className="w-full max-w-[420px] rounded-2xl bg-white/94 p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="m-0 text-xl font-semibold text-slate-800">
              {t("account.title")}
            </h2>
            <p className="mt-1.5 mb-5 text-xs text-slate-400">
              {t("account.hint")}
            </p>
            <label className="block text-xs font-semibold text-slate-500">
              {t("account.displayName")}
              <input
                value={draftName}
                maxLength={30}
                autoFocus
                onChange={(event) => setDraftName(event.target.value)}
                className="mt-2 block w-full rounded-lg border border-slate-200 bg-white/80 px-3 py-3 text-slate-700 outline-0 focus:border-indigo-300"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={closeAccount}
                className="rounded-lg bg-slate-100 px-4 py-2 text-slate-500 hover:bg-slate-200"
              >
                {t("account.cancel")}
              </button>
              <button
                type="button"
                onClick={saveAccount}
                className="rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 px-4 py-2 font-semibold text-white shadow-lg shadow-indigo-500/20"
              >
                {t("account.save")}
              </button>
            </div>
          </section>
        </div>
      )}

      {/* 上传弹窗 */}
      {upload.status !== "idle" && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-slate-900/30 backdrop-blur-sm">
          <section
            className="w-full max-w-[420px] rounded-3xl border border-white/75 bg-white/96 px-8 py-8 text-center shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-title"
          >
            <div
              className={`mx-auto mb-4 flex h-[58px] w-[58px] items-center justify-center rounded-2xl text-[29px] font-extrabold ${
                upload.status === "uploading"
                  ? "bg-indigo-50 text-indigo-500 animate-pulse"
                  : upload.status === "success"
                    ? "bg-emerald-50 text-emerald-600"
                    : "bg-red-50 text-red-500"
              }`}
            >
              {upload.status === "uploading"
                ? "↥"
                : upload.status === "success"
                  ? "✓"
                  : "!"}
            </div>
            <h2
              id="upload-title"
              className="text-xl font-semibold text-slate-800"
            >
              {upload.status === "uploading"
                ? t("upload.uploading")
                : upload.status === "success"
                  ? t("upload.success")
                  : t("upload.error")}
            </h2>
            {uploadMessage && (
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                {uploadMessage}
              </p>
            )}
            {upload.fileNames.length > 0 && (
              <small className="mt-2 block truncate text-xs text-slate-400">
                {upload.fileNames.join("、")}
              </small>
            )}
            {upload.files.length > 0 && (
              <div className="mt-4 max-h-[150px] overflow-auto rounded-xl border border-slate-100 bg-slate-50 p-2 text-left">
                {upload.files.map((file) => (
                  <div
                    key={file.file_md5}
                    className="flex items-center gap-2 px-1.5 py-2 text-xs text-slate-500"
                  >
                    <span className="text-base text-emerald-500">
                      {file.indexed || file.duplicate ? "✓" : "◌"}
                    </span>
                    <strong className="min-w-0 flex-1 truncate font-semibold text-slate-700">
                      {file.filename}
                    </strong>
                    <em className="whitespace-nowrap not-italic text-indigo-500">
                      {file.duplicate
                        ? t("upload.fileExists")
                        : file.indexed
                          ? t("upload.fileIndexed")
                          : t("upload.fileIndexing")}
                    </em>
                  </div>
                ))}
              </div>
            )}
            {upload.status !== "uploading" && (
              <button
                type="button"
                onClick={closeUpload}
                className="mt-5 min-w-[112px] rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 px-5 py-2.5 font-bold text-white shadow-lg shadow-indigo-500/20"
              >
                {t("upload.close")}
              </button>
            )}
          </section>
        </div>
      )}
    </div>
  );
};
