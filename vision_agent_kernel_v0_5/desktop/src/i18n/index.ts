import { createContext, useContext } from "react";
import type { Dict } from "./zh";
import zh from "./zh";
import en from "./en";

export type Lang = "zh" | "en";
export const dicts: Record<Lang, Dict> = { zh, en };

export const I18nContext = createContext<Dict>(zh);
export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: "zh",
  setLang: () => {},
});

export function useI18n() {
  return useContext(I18nContext);
}

export function useLang() {
  return useContext(LangContext);
}
