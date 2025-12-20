
/**
 * 核心契约：定义各模块间的通信协议
 */

export type Theme = 'light' | 'dark';
export type FontFamily = 'sans' | 'serif';

export interface TranslationResult {
  sourceText: string;
  translatedText: string;
  status: 'idle' | 'translating' | 'success' | 'error';
  error?: string;
}

export interface ICoreEngine {
  translate: (text: string) => Promise<string>;
}

export interface ISystemService {
  copyToClipboard: (text: string) => Promise<boolean>;
  simulateSend: () => Promise<void>;
  notify: (msg: string) => void;
}

export interface AppState {
  input: string;
  translation: string;
  isOverlayVisible: boolean;
  isProcessing: boolean;
  theme: Theme;
  fontFamily: FontFamily;
}
