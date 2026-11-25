// search/src/ui/SearchModal.tsx
// Search requests are scoped to the authenticated user's server-side history.
import { useSearchModalHook } from "../hook/useSearchModalHook";
import { useTranslation } from "@ming/i18n";

type SearchModalProps = Readonly<{
  onSelect: (id: string) => void;
}>;

export function SearchModal({ onSelect }: SearchModalProps) {
  const { t } = useTranslation("search");
  const { open, keyword, setKeyword, closeSearch, results } =
    useSearchModalHook();

  if (!open) return null;

  return (
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
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder={t("search.placeholder")}
          className="block w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-gray-700 outline-0 focus:border-blue-400 focus:bg-white"
        />
        <div className="mt-4 max-h-[300px] overflow-auto">
          {keyword.trim() && results.length === 0 && (
            <p className="py-3 text-center text-sm text-gray-400">
              {t("search.noResults")}
            </p>
          )}
          {results.map((item) => (
            <button
              key={item.conversationId}
              type="button"
              onClick={() => onSelect(item.conversationId)}
              className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-gray-700 transition hover:bg-blue-50"
            >
              <strong className="min-w-0 flex-1 truncate">{item.title}</strong>
              <small className="text-gray-400">{item.updatedAt}</small>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
