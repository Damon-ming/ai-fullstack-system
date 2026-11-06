// chat/src/ui/ChatPage.tsx
import { ChatDrawer } from "@ming/feature-chat-drawer-api";
import { KnowledgeModal } from "@ming/feature-knowledge-api";
import { SearchModal } from "@ming/feature-search-api";
import { ChatChatroom } from "@ming/feature-chat-chatroom-api";
import { AccountDialog } from "@ming/feature-account-api";
import React, { useEffect } from "react";
import { useChatPageHook } from "../hook";
import { i18n, useTranslation } from "@ming/i18n";

export const ChatPage: React.FC = () => {
  const { t } = useTranslation("chat-page");
  const {
    chatSessionId,
    searchOpen,
    closeSearch,
    loadHistory,
    upload,
    uploadMessage,
    closeUpload,
    abortUpload,
    knowledgeOpen,
  } = useChatPageHook();

  // 页面关闭/刷新前取消进行中的上传，避免服务端继续空跑
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (upload.status === "uploading") {
        abortUpload();
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [abortUpload, upload.status]);

  const switchLang = () => {
    i18n.changeLanguage(i18n.language === "zh" ? "en" : "zh");
  };

  const handleSearchSelect = async (id: string) => {
    await loadHistory(id);
    closeSearch();
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

      {/* 账户弹窗 —— 由 account 模块自包含渲染 */}
      <AccountDialog />

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
            {upload.successFiles.length > 0 && (
              <div className="mt-4 max-h-[150px] overflow-auto rounded-xl border border-gray-100 bg-gray-50 p-2 text-left">
                {upload.successFiles.map((file) => (
                  <div
                    key={file.file_uid || file.filename}
                    className="flex items-center gap-2 px-2 py-2 text-xs text-gray-500"
                  >
                    <span className="text-base text-emerald-500">✓</span>
                    <strong className="min-w-0 flex-1 truncate font-semibold text-gray-700">
                      {file.filename}
                    </strong>
                    <em className="whitespace-nowrap not-italic text-blue-500">
                      {t("upload.fileIndexed")}
                    </em>
                  </div>
                ))}
              </div>
            )}
            {upload.status === "uploading" ? (
              <button
                type="button"
                onClick={abortUpload}
                className="mt-5 min-w-[112px] rounded-xl bg-red-500 px-6 py-2.5 font-bold text-white shadow-lg shadow-red-500/20 transition hover:bg-red-600"
              >
                取消上传
              </button>
            ) : (
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

      {/* 搜索弹窗 —— 由 search 模块自包含渲染 */}
      {searchOpen && <SearchModal onSelect={handleSearchSelect} />}

      {/* 知识库弹窗 —— 由 knowledge 模块自包含渲染 */}
      {knowledgeOpen && <KnowledgeModal />}
    </div>
  );
};
