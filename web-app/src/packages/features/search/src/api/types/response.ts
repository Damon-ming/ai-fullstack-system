export interface SearchResultItem {
  title: string;
  turns?: Array<{ query: string; content: string }>;
}
