// account/src/ui/LoginPage.tsx
import React from "react";
import { useLoginPageHook } from "../hook/AccountHook";
import { useTranslation } from "@ming/i18n";

export function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const { t } = useTranslation("account");
  const {
    phone,
    password,
    setPhone,
    setPassword,
    phoneError,
    passwordError,
    submitError,
    status,
    handleSubmit,
  } = useLoginPageHook(onSuccess);

  const loading = status === "loading";

  return (
    <div className="flex h-full w-full items-center justify-center bg-gray-50 font-sans">
      <section
        className="w-full max-w-[360px] rounded-2xl border border-gray-100 bg-white p-8 shadow-xl"
        role="form"
        aria-label={t("login.title")}
      >
        <h1 className="m-0 mb-1 text-2xl font-bold text-gray-800">
          {t("login.title")}
        </h1>
        <p className="m-0 mb-6 text-sm text-gray-400">{t("login.subtitle")}</p>

        {/* 手机号 */}
        <label className="mb-4 block text-xs font-semibold text-gray-500">
          {t("login.phoneLabel")}
          <input
            type="tel"
            autoFocus
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder={t("login.phonePlaceholder")}
            className={`mt-1.5 block w-full rounded-xl border bg-gray-50 px-4 py-3 text-gray-700 outline-0 focus:bg-white ${
              phoneError
                ? "border-red-300 focus:border-red-400"
                : "border-gray-200 focus:border-blue-400"
            }`}
            disabled={loading}
          />
          {phoneError && (
            <span className="mt-1 block text-xs text-red-500">
              {phoneError}
            </span>
          )}
        </label>

        {/* 密码 */}
        <label className="mb-4 block text-xs font-semibold text-gray-500">
          {t("login.passwordLabel")}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("login.passwordPlaceholder")}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !loading) void handleSubmit();
            }}
            className={`mt-1.5 block w-full rounded-xl border bg-gray-50 px-4 py-3 text-gray-700 outline-0 focus:bg-white ${
              passwordError
                ? "border-red-300 focus:border-red-400"
                : "border-gray-200 focus:border-blue-400"
            }`}
            disabled={loading}
          />
          {passwordError && (
            <span className="mt-1 block text-xs text-red-500">
              {passwordError}
            </span>
          )}
        </label>

        {/* 提交错误 */}
        {submitError && (
          <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
            {submitError}
          </div>
        )}

        {/* 密码规则提示 */}
        <p className="m-0 mb-5 text-xs text-gray-400">
          {t("login.passwordHint")}
        </p>

        {/* 登录按钮 */}
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={loading}
          className="flex w-full items-center justify-center rounded-xl bg-blue-600 py-3 font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              {t("login.submitting")}
            </span>
          ) : (
            t("login.submit")
          )}
        </button>
      </section>
    </div>
  );
}
