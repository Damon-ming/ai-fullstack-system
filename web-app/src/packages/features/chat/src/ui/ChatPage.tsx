import { ChatDrawer } from "@ming/features-chat-drawer";
import { ChatChatroom } from "@ming/features-chat-chatroom";
import React, { useMemo } from "react";
import { useChatPageHook } from "../hook";
import { useTranslation } from "@ming/i18n";
import { i18n } from "@ming/i18n";

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

  const switchLang = () => {
    i18n.changeLanguage(i18n.language === "zh" ? "en" : "zh");
  };

  return (
    <div className="relative flex h-full w-full overflow-hidden font-sans text-gray-800 bg-gray-50">
      {/* 右上角语言切换小图标 */}
      <button
        type="button"
        onClick={switchLang}
        className="fixed right-4 top-3 z-50 flex h-8 w-8 items-center justify-center rounded-full bg-white text-sm font-medium text-gray-500 shadow-md transition hover:bg-gray-100 hover:text-gray-700 border border-gray-200"
        aria-label="Switch language"
      >
        {i18n.language === "zh" ? "EN" : "中"}
      </button>

      {/* 主内容区 */}
      <div className="flex w-full min-h-0 flex-1">
        <ChatDrawer />
        <ChatChatroom key={chatSessionId} />
      </div>

      {/* 搜索弹窗 */}
      {searchOpen && (
        <div
          className="fixed inset-0 z-30 grid place-items-center bg-black/40 backdrop-blur-sm"
          onClick={closeSearch}
        >
          <section
            className="w-full max-w-[480px] rounded-2xl bg-white p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="m-0 mb-3 text-lg font-semibold text-gray-800">
              {t("search.placeholder")}
            </h2>
            <input
              autoFocus
              value={searchKeyword}
              onChange={(event) => setSearchKeyword(event.target.value)}
              placeholder={t("search.placeholder")}
              className="block w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-gray-700 outline-0 focus:border-blue-400 focus:bg-white"
            />
            <div className="mt-4 max-h-[300px] overflow-auto">
              {searchKeyword.trim() && searchResults.length === 0 && (
                <p className="py-3 text-center text-sm text-gray-400">
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
                  className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-gray-700 transition hover:bg-blue-50"
                >
                  <strong className="min-w-0 flex-1 truncate">
                    {item.title}
                  </strong>
                  <small className="text-gray-400">{item.meta}</small>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* 账户弹窗 */}
      {accountOpen && (
        <div
          className="fixed inset-0 z-30 grid place-items-center bg-black/40 backdrop-blur-sm"
          onClick={closeAccount}
        >
          <section
            className="w-full max-w-[420px] rounded-2xl bg-white p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="m-0 text-xl font-semibold text-gray-800">
              {t("account.title")}
            </h2>
            <p className="mt-1.5 mb-5 text-xs text-gray-400">
              {t("account.hint")}
            </p>
            <label className="block text-xs font-semibold text-gray-500">
              {t("account.displayName")}
              <input
                value={draftName}
                maxLength={30}
                autoFocus
                onChange={(event) => setDraftName(event.target.value)}
                className="mt-2 block w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-gray-700 outline-0 focus:border-blue-400 focus:bg-white"
              />
            </label>
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={closeAccount}
                className="rounded-xl bg-gray-100 px-5 py-2 text-gray-500 transition hover:bg-gray-200"
              >
                {t("account.cancel")}
              </button>
              <button
                type="button"
                onClick={saveAccount}
                className="rounded-xl bg-blue-600 px-5 py-2 font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
              >
                {t("account.save")}
              </button>
            </div>
          </section>
        </div>
      )}

      {/* 上传弹窗 */}
      {upload.status !== "idle" && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/40 backdrop-blur-sm">
          <section
            className="w-full max-w-[420px] rounded-3xl border border-gray-100 bg-white px-8 py-8 text-center shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-title"
          >
            <div
              className={`mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl text-3xl font-extrabold ${
                upload.status === "uploading"
                  ? "bg-blue-50 text-blue-500 animate-pulse"
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
              className="text-xl font-semibold text-gray-800"
            >
              {upload.status === "uploading"
                ? t("upload.uploading")
                : upload.status === "success"
                  ? t("upload.success")
                  : t("upload.error")}
            </h2>
            {uploadMessage && (
              <p className="mt-2 text-sm leading-relaxed text-gray-500">
                {uploadMessage}
              </p>
            )}
            {upload.fileNames.length > 0 && (
              <small className="mt-2 block truncate text-xs text-gray-400">
                {upload.fileNames.join("、")}
              </small>
            )}
            {upload.files.length > 0 && (
              <div className="mt-4 max-h-[150px] overflow-auto rounded-xl border border-gray-100 bg-gray-50 p-2 text-left">
                {upload.files.map((file) => (
                  <div
                    key={file.file_md5}
                    className="flex items-center gap-2 px-2 py-2 text-xs text-gray-500"
                  >
                    <span className="text-base text-emerald-500">
                      {file.indexed || file.duplicate ? "✓" : "◌"}
                    </span>
                    <strong className="min-w-0 flex-1 truncate font-semibold text-gray-700">
                      {file.filename}
                    </strong>
                    <em className="whitespace-nowrap not-italic text-blue-500">
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
                className="mt-5 min-w-[112px] rounded-xl bg-blue-600 px-6 py-2.5 font-bold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
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
