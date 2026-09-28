import { ChatDrawer } from "@ming/features-chat-drawer";
import { ChatChatroom } from "@ming/features-chat-chatroom";
import React from "react";
import { useChatPageHook } from "../hook";

export const ChatPage: React.FC = () => {
  const {
    drawerOpen,
    chatSessionId,
    toggleDrawer,
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
  return (
    <div className="feature-chat-page">
      <ChatDrawer />
      <ChatChatroom key={chatSessionId} />
      {searchOpen && (
        <div className="feature-search-backdrop" onClick={closeSearch}>
          <section
            className="feature-search-modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <input
              autoFocus
              value={searchKeyword}
              onChange={(event) => setSearchKeyword(event.target.value)}
              placeholder="搜索历史对话内容..."
            />
            <div className="feature-search-results">
              {searchKeyword.trim() && searchResults.length === 0 && (
                <p>没有找到匹配的对话</p>
              )}
              {searchResults.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    loadHistory(item.id);
                    closeSearch();
                  }}
                >
                  <strong>{item.title}</strong>
                  <small>{item.meta}</small>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}
      {accountOpen && (
        <div className="feature-account-backdrop" onClick={closeAccount}>
          <section
            className="feature-account-modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <h2>账户信息</h2>
            <p>信息仅保存在当前浏览器。</p>
            <label>
              显示名称
              <input
                value={draftName}
                maxLength={30}
                autoFocus
                onChange={(event) => setDraftName(event.target.value)}
              />
            </label>
            <div>
              <button type="button" onClick={closeAccount}>
                取消
              </button>
              <button type="button" onClick={saveAccount}>
                保存
              </button>
            </div>
          </section>
        </div>
      )}
      {upload.status !== "idle" && (
        <div className="feature-upload-modal-backdrop" role="presentation">
          <section
            className={`feature-upload-modal ${upload.status}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-title"
          >
            <div className="feature-upload-icon">
              {upload.status === "uploading"
                ? "↥"
                : upload.status === "success"
                  ? "✓"
                  : "!"}
            </div>
            <h2 id="upload-title">
              {upload.status === "uploading"
                ? "正在上传文件"
                : upload.status === "success"
                  ? "上传完成"
                  : "上传失败"}
            </h2>
            <p>{upload.message}</p>
            {upload.fileNames.length > 0 && (
              <small>{upload.fileNames.join("、")}</small>
            )}
            {upload.files.length > 0 && (
              <div className="feature-upload-results">
                {upload.files.map((file) => (
                  <div className="feature-upload-result" key={file.file_md5}>
                    <span>{file.indexed || file.duplicate ? "✓" : "◌"}</span>
                    <strong>{file.filename}</strong>
                    <em>
                      {file.duplicate
                        ? "已存在"
                        : file.indexed
                          ? "已入语料库"
                          : "更新中"}
                    </em>
                  </div>
                ))}
              </div>
            )}
            {upload.status !== "uploading" && (
              <button type="button" onClick={closeUpload}>
                知道了
              </button>
            )}
          </section>
        </div>
      )}
      <style>{styles}</style>
      <style>{motionStyles}</style>
      <style>{uploadResultStyles}</style>
      <style>{activeHistoryStyles}</style>
      <style>{layoutFixStyles}</style>
    </div>
  );
};

const styles = `
*{box-sizing:border-box}html,body,#root{width:100%;height:100%;margin:0;overflow:hidden}.feature-chat-page{width:100%;height:100%;display:flex;overflow:hidden;color:#172033;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 72% 5%,#eef2ff 0,#f8faff 34%,#f5f7fb 100%)}.feature-chat-drawer{height:100%;width:286px;flex:none;display:flex;flex-direction:column;padding:22px 16px 14px;background:rgba(255,255,255,.82);border-right:1px solid rgba(211,219,235,.7);backdrop-filter:blur(18px)}.feature-drawer-top{display:flex;align-items:center;gap:11px;padding:0 8px 24px;color:#202b43}.feature-brand,.feature-welcome>div{display:grid;place-items:center;color:#fff;background:linear-gradient(135deg,#5865f2 0%,#8b5cf6 100%);box-shadow:0 10px 24px rgba(88,101,242,.25)}.feature-brand{width:36px;height:36px;border-radius:12px;font-size:18px}.feature-drawer-top button{margin-left:auto;width:30px;height:30px;border:0;border-radius:9px;background:#f2f4fa;color:#7d879b;font-size:21px;line-height:1;cursor:pointer}.feature-new-chat{height:44px;width:100%;border:0;border-radius:13px;background:linear-gradient(135deg,#5967f5,#7b5bea);color:#fff;font-weight:650;letter-spacing:.1px;box-shadow:0 10px 20px rgba(94,92,235,.2);cursor:pointer}.feature-new-chat:hover{filter:brightness(1.04);transform:translateY(-1px)}.feature-search{display:flex;align-items:center;gap:9px;margin:20px 2px 25px;padding:10px 12px;border:1px solid #e7eaf2;border-radius:12px;background:#f8f9fc;color:#929bad}.feature-search input{width:100%;border:0;outline:0;background:transparent;color:#374151;font:inherit}.feature-history-title{display:flex;justify-content:space-between;padding:0 9px 10px;color:#9aa3b4;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.feature-history-title span{padding:2px 7px;border-radius:99px;background:#eef0ff;color:#6971d9;letter-spacing:0}.feature-chat-drawer nav{min-height:0;flex:1;overflow-y:auto}.feature-history-item{display:flex;align-items:center;width:100%;gap:9px;margin:2px 0;padding:11px 10px;border:0;border-radius:11px;background:transparent;color:#667085;text-align:left;cursor:pointer;transition:.18s}.feature-history-item:hover{background:#f0f2ff;color:#4f46c7}.feature-history-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.feature-history-item small{margin-left:auto;color:#a5adbb;font-size:10px}.feature-user{display:flex;flex:none;gap:10px;align-items:center;margin-top:10px;padding:14px 8px 3px;border-top:1px solid #edf0f5;color:#344054;font-size:13px}.feature-user>span{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:#e9eaff;color:#5965dc;font-weight:700}.feature-collapsed-tools{position:fixed;top:18px;left:18px;display:flex;gap:8px;z-index:5}.feature-collapsed-tools button{width:40px;height:40px;border:1px solid #e1e6f0;border-radius:12px;background:rgba(255,255,255,.9);color:#5965dc;box-shadow:0 8px 20px #25344b12;cursor:pointer}.feature-chat-drawer.is-collapsed{width:0;padding:0;border:0}.feature-chatroom{min-width:0;min-height:0;height:100%;flex:1;overflow:hidden;display:flex;flex-direction:column;align-items:center;padding:34px 28px 22px}.feature-composer-area{width:min(900px,100%);display:flex;flex-direction:column;min-height:0}.feature-chatroom.is-empty{justify-content:center}.feature-chatroom.is-empty .feature-composer-area{align-items:center}.feature-chatroom.has-messages .feature-composer-area{flex:none}.feature-welcome{margin:auto;text-align:center}.feature-welcome>div{width:66px;height:66px;margin:auto;border-radius:21px;font-size:32px}.feature-welcome h1{margin:22px 0 8px;font-size:31px;letter-spacing:-.04em;color:#1f2940}.feature-welcome p,.feature-hint{color:#98a2b3;font-size:14px}.feature-messages{width:min(900px,100%);min-height:0;flex:1;overflow-y:auto;padding:22px 8px}.feature-message{width:max-content;max-width:72%;margin:14px 0;padding:12px 16px;border:1px solid #e7eaf2;border-radius:17px 17px 17px 5px;background:rgba(255,255,255,.82);box-shadow:0 5px 16px rgba(28,39,71,.05);line-height:1.55;color:#344054}.feature-message.user{margin-left:auto;border:0;border-radius:17px 17px 5px 17px;color:#fff;background:linear-gradient(135deg,#5865f2,#7660ed);box-shadow:0 8px 18px rgba(88,101,242,.2)}.feature-composer{width:min(900px,100%);display:flex;align-items:flex-end;gap:9px;padding:11px 12px 11px 14px;border:1px solid #dfe4ee;border-radius:19px;background:rgba(255,255,255,.92);box-shadow:0 14px 35px rgba(36,48,82,.1);transition:.2s}.feature-composer:focus-within{border-color:#9da7f6;box-shadow:0 14px 38px rgba(88,101,242,.15)}.feature-composer label{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;color:#8993a7;font-size:21px;cursor:pointer}.feature-composer label:hover{background:#f0f2ff;color:#5965dc}.feature-composer button{width:36px;height:36px;border:0;border-radius:11px;background:linear-gradient(135deg,#5865f2,#7660ed);color:#fff;font-size:21px;line-height:1;cursor:pointer}.feature-composer button:disabled{opacity:.5;cursor:not-allowed}.feature-composer textarea{min-height:36px;max-height:140px;flex:1;resize:none;border:0;outline:0;line-height:24px;color:#344054;font:inherit;background:transparent}.feature-composer textarea::placeholder{color:#a3abba}.feature-hint{margin:9px 0 0;font-size:11px;text-align:center}@media(max-width:720px){.feature-chat-drawer{position:fixed;z-index:4;inset:0 auto 0 0;box-shadow:14px 0 35px rgba(30,41,70,.15)}.feature-chatroom{padding:20px 16px}.feature-welcome h1{font-size:25px}.feature-message{max-width:84%}}
`;

const motionStyles = `
.feature-messages{scrollbar-width:thin;scrollbar-color:#c7cdea transparent;overscroll-behavior:contain;scroll-behavior:smooth}.feature-messages::-webkit-scrollbar{width:8px}.feature-messages::-webkit-scrollbar-track{background:transparent;margin:12px 0}.feature-messages::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:99px;background-clip:padding-box;background-color:#c7cdea}.feature-messages::-webkit-scrollbar-thumb:hover{background-color:#9da7df}
.feature-chat-page{position:relative;isolation:isolate;background-image:radial-gradient(circle at 75% 0%,rgba(224,228,255,.9),transparent 34%),radial-gradient(circle at 30% 100%,rgba(237,225,255,.6),transparent 28%);}
.feature-upload-modal-backdrop{position:fixed;inset:0;z-index:20;display:grid;place-items:center;background:rgba(19,27,52,.3);backdrop-filter:blur(7px);cursor:wait}.feature-upload-modal{width:min(420px,calc(100vw - 36px));padding:34px 30px 28px;border:1px solid rgba(255,255,255,.75);border-radius:26px;background:rgba(255,255,255,.96);box-shadow:0 30px 90px rgba(27,38,82,.28);text-align:center;cursor:default;animation:feature-modal-in .3s cubic-bezier(.22,1,.36,1)}.feature-upload-icon{display:grid;place-items:center;width:58px;height:58px;margin:0 auto 18px;border-radius:19px;background:#eef0ff;color:#5965dc;font-size:29px;font-weight:800}.feature-upload-modal.uploading .feature-upload-icon{animation:feature-upload-pulse 1.2s ease-in-out infinite}.feature-upload-modal.success .feature-upload-icon{background:#e9fbf1;color:#169456}.feature-upload-modal.error .feature-upload-icon{background:#fff0f0;color:#d14343}.feature-upload-modal h2{margin:0;color:#1f2940;font-size:21px}.feature-upload-modal p{margin:10px 0 5px;color:#667085;font-size:14px;line-height:1.6}.feature-upload-modal small{display:block;margin-top:8px;color:#98a2b3;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.feature-upload-modal button{min-width:112px;margin-top:22px;padding:10px 18px;border:0;border-radius:11px;background:linear-gradient(135deg,#5865f2,#7660ed);color:#fff;font-weight:700;cursor:pointer;box-shadow:0 8px 18px rgba(88,101,242,.22)}
@keyframes feature-modal-in{from{opacity:0;transform:translateY(12px) scale(.97)}to{opacity:1;transform:none}}@keyframes feature-upload-pulse{0%,100%{box-shadow:0 0 0 0 rgba(88,101,242,.12);transform:translateY(0)}50%{box-shadow:0 0 0 12px rgba(88,101,242,0);transform:translateY(-3px)}}
.feature-upload-file{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:38px;margin-top:9px;border:1px dashed #cfd5ea;border-radius:11px;color:#6874c9;background:#f8f9ff;font-size:12px;font-weight:600;cursor:pointer;transition:.2s}.feature-upload-file:hover{border-color:#8993ef;background:#f0f2ff;transform:translateY(-1px)}.feature-collapsed-upload{display:grid;place-items:center;width:40px;height:40px;border:1px solid #e1e6f0;border-radius:12px;background:rgba(255,255,255,.9);color:#5965dc;box-shadow:0 8px 20px #25344b12;cursor:pointer;transition:.2s}.feature-collapsed-upload:hover{background:#f0f2ff;transform:translateY(-2px)}
.feature-chat-page:before,.feature-chat-page:after{content:"";position:absolute;z-index:-1;border-radius:999px;pointer-events:none;filter:blur(2px);animation:feature-float 10s ease-in-out infinite}
.feature-chat-page:before{width:280px;height:280px;right:-90px;top:-120px;background:#dfe3ff;opacity:.55}.feature-chat-page:after{width:200px;height:200px;left:28%;bottom:-130px;background:#eadfff;opacity:.5;animation-delay:-4s}
.feature-chat-drawer{position:relative;z-index:1;animation:feature-drawer-in .55s cubic-bezier(.22,1,.36,1);transition:width .35s cubic-bezier(.22,1,.36,1),padding .35s cubic-bezier(.22,1,.36,1),border-color .35s ease}
.feature-chat-drawer.is-collapsed{overflow:visible;transition:width .35s cubic-bezier(.22,1,.36,1)}
.feature-chat-drawer:not(.is-collapsed)>*{animation:feature-drawer-content-in .4s cubic-bezier(.22,1,.36,1) both}
.feature-chat-drawer:not(.is-collapsed)>*:nth-child(2){animation-delay:.04s}.feature-chat-drawer:not(.is-collapsed)>*:nth-child(3){animation-delay:.08s}.feature-chat-drawer:not(.is-collapsed)>*:nth-child(4){animation-delay:.12s}
.feature-chatroom{position:relative;z-index:0;animation:feature-page-in .65s cubic-bezier(.22,1,.36,1)}
.feature-brand,.feature-welcome>div{animation:feature-glow 3.2s ease-in-out infinite}
.feature-welcome h1,.feature-welcome p{animation:feature-text-in .6s both}.feature-welcome p{animation-delay:.1s}
.feature-message-row{margin:8px 0}.feature-message-shell{position:relative;display:flex;align-items:flex-end;max-width:100%;padding:10px 38px 10px 10px}.feature-message-shell.user{justify-content:flex-end}.feature-message{animation:feature-message-in .4s cubic-bezier(.22,1,.36,1) both;transition:transform .2s,box-shadow .2s}.feature-message-shell:hover .feature-message{transform:translateY(-2px);box-shadow:0 10px 24px rgba(28,39,71,.1)}.feature-copy-button{position:absolute;right:5px;bottom:5px;width:27px;height:27px;border:1px solid #e1e5f0;border-radius:9px;background:rgba(255,255,255,.95);color:#6974c9;font-size:14px;line-height:1;cursor:pointer;opacity:0;transform:translateY(4px);transition:opacity .18s,transform .18s,background .18s}.feature-message-shell:hover .feature-copy-button,.feature-copy-button:focus-visible{opacity:1;transform:none}.feature-copy-button:hover{background:#eef0ff}.feature-scroll-bottom{position:absolute;right:18px;bottom:90px;z-index:3;width:34px;height:34px;border:1px solid #dfe4f2;border-radius:50%;background:rgba(255,255,255,.96);color:#5965dc;font-size:18px;line-height:1;box-shadow:0 8px 20px rgba(38,48,86,.16);cursor:pointer;transition:transform .2s,box-shadow .2s}.feature-scroll-bottom:hover{transform:translateY(-2px);box-shadow:0 11px 24px rgba(38,48,86,.22)}
.feature-composer{transition:border-color .2s,box-shadow .2s,transform .2s}.feature-composer:focus-within{transform:translateY(-2px)}
.feature-new-chat,.feature-composer button,.feature-collapsed-tools button{transition:transform .2s,filter .2s,box-shadow .2s}.feature-new-chat:hover,.feature-composer button:hover{transform:translateY(-2px);filter:brightness(1.06);box-shadow:0 10px 22px rgba(88,101,242,.28)}.feature-new-chat:active,.feature-composer button:active{transform:scale(.97)}
@keyframes feature-page-in{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@keyframes feature-drawer-in{from{opacity:0;transform:translateX(-18px)}to{opacity:1;transform:none}}@keyframes feature-drawer-content-in{from{opacity:0;transform:translateX(-12px)}to{opacity:1;transform:none}}@keyframes feature-text-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}@keyframes feature-message-in{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}@keyframes feature-glow{0%,100%{box-shadow:0 10px 24px rgba(88,101,242,.25)}50%{box-shadow:0 14px 34px rgba(139,92,246,.42)}}@keyframes feature-float{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(0,16px,0)}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
`;

const uploadResultStyles = `.feature-upload-results{max-height:150px;margin-top:16px;padding:8px;border:1px solid #edf0f7;border-radius:13px;background:#fafbff;text-align:left;overflow:auto}.feature-upload-result{display:flex;align-items:center;gap:8px;padding:8px 6px;font-size:12px;color:#667085}.feature-upload-result span{color:#16a05d;font-size:15px}.feature-upload-result strong{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#344054;font-weight:600}.feature-upload-result em{font-style:normal;color:#7c86d9;white-space:nowrap}.feature-history-item i{display:none;margin-left:4px;color:#a6aec0;font-style:normal;font-size:16px}.feature-history-item:hover i{display:block}.feature-history-item i:hover{color:#d14343}.feature-user{width:100%;border:0;background:transparent;text-align:left;cursor:pointer}.feature-user small{margin-left:auto;color:#98a2b3;font-size:11px}.feature-account-backdrop,.feature-search-backdrop{position:fixed;inset:0;z-index:30;display:grid;place-items:center;background:rgba(19,27,52,.3);backdrop-filter:blur(6px)}.feature-account-modal,.feature-search-modal{width:min(420px,calc(100vw - 32px));padding:26px;border-radius:20px;background:rgba(255,255,255,.94);box-shadow:0 25px 70px rgba(27,38,82,.24)}.feature-account-modal h2{margin:0;color:#1f2940;font-size:20px}.feature-account-modal p{margin:7px 0 20px;color:#98a2b3;font-size:12px}.feature-account-modal label{display:block;color:#667085;font-size:12px;font-weight:600}.feature-account-modal input,.feature-search-modal>input{display:block;width:100%;margin-top:8px;padding:12px;border:1px solid #dfe4ee;border-radius:10px;outline:0;font:inherit;color:#344054;background:rgba(255,255,255,.8)}.feature-account-modal input:focus,.feature-search-modal>input:focus{border-color:#8993ef}.feature-account-modal>div{display:flex;justify-content:flex-end;gap:9px;margin-top:22px}.feature-account-modal button{padding:9px 16px;border:0;border-radius:10px;background:#f0f2f8;color:#667085;cursor:pointer}.feature-account-modal button:last-child{background:linear-gradient(135deg,#5865f2,#7660ed);color:#fff}.feature-search-results{max-height:280px;margin-top:12px;overflow:auto}.feature-search-results button{display:flex;align-items:center;gap:12px;width:100%;padding:12px;border:0;border-radius:11px;background:transparent;text-align:left;color:#344054;cursor:pointer}.feature-search-results button:hover{background:#eef0ff}.feature-search-results strong{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.feature-search-results small{color:#98a2b3}.feature-search-results p{padding:10px;color:#98a2b3;text-align:center;font-size:13px}`;
const activeHistoryStyles = `.feature-history-item.is-active{background:#eef0ff;color:#4f46c7;box-shadow:inset 3px 0 0 #5965dc}`;
const layoutFixStyles = `.feature-history-item span{min-width:0;flex:1}.feature-history-item i{flex:none;margin-left:auto}.feature-message-shell{width:100%;padding:10px}.feature-message-shell.user{padding-right:44px}.feature-message-bubble{position:relative;width:fit-content;max-width:100%}.feature-message-bubble.user{max-width:50%}.feature-message-bubble .feature-message{max-width:100%!important}.feature-copy-button{right:-34px}.feature-message-bubble:hover .feature-copy-button,.feature-copy-button:focus-visible{opacity:1;transform:none}.feature-messages{overflow-x:hidden;overflow-y:scroll;scrollbar-width:thin;scrollbar-color:transparent transparent;scrollbar-gutter:stable}.feature-messages::-webkit-scrollbar{width:8px;height:0}.feature-messages::-webkit-scrollbar-thumb{background-color:transparent}.feature-messages.is-scrolling{scrollbar-color:#c7cdea transparent}.feature-messages.is-scrolling::-webkit-scrollbar-thumb{background-color:#c7cdea}.feature-messages.is-scrolling::-webkit-scrollbar-thumb:hover{background-color:#9da7df}.feature-message{max-width:100%;overflow-wrap:anywhere}`;
