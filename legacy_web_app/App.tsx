
import React, { useState, useCallback, useRef } from 'react';
import { Overlay } from './components/Overlay';
import { GeminiTranslationEngine } from './services/geminiService';
import { DesktopSystemService } from './services/systemService';
import { AppState, FontFamily } from './types';

const App: React.FC = () => {
  const engine = useRef(new GeminiTranslationEngine());
  const system = useRef(new DesktopSystemService());

  const [state, setState] = useState<AppState>({
    input: "",
    translation: "",
    isOverlayVisible: true,
    isProcessing: false,
    theme: 'dark',
    fontFamily: 'sans',
  });

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const translationTimeout = useRef<any>(null);

  const toggleTheme = () => {
    setState(prev => ({
      ...prev,
      theme: prev.theme === 'light' ? 'dark' : 'light'
    }));
  };

  const toggleFont = () => {
    setState(prev => ({
      ...prev,
      fontFamily: prev.fontFamily === 'sans' ? 'serif' : 'sans'
    }));
  };

  const handleTranslate = useCallback(async (text: string) => {
    if (!text.trim()) {
      setState(prev => ({ ...prev, translation: "", isProcessing: false }));
      return;
    }

    setState(prev => ({ ...prev, isProcessing: true }));
    try {
      const result = await engine.current.translate(text);
      setState(prev => ({ ...prev, translation: result, isProcessing: false }));
    } catch (err) {
      console.error("Integration Error:", err);
      setState(prev => ({ ...prev, isProcessing: false }));
      system.current.notify("任务失败");
    }
  }, []);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newVal = e.target.value;
    setState(prev => ({ ...prev, input: newVal }));

    if (translationTimeout.current) clearTimeout(translationTimeout.current);
    translationTimeout.current = setTimeout(() => {
      handleTranslate(newVal);
    }, 350);
  };

  const onKeyDown = async (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (!state.translation) return;
      const success = await system.current.copyToClipboard(state.translation);
      if (success) {
        await system.current.simulateSend();
        setState(prev => ({ ...prev, input: "", translation: "" }));
      }
    }
    if (e.key === 'Escape') {
      system.current.notify("Hidden");
    }
  };

  // 根据当前主题决定设置面板的背景和文字颜色
  // 遵循：深色背景配浅色文字，浅色背景配深色文字
  const settingsPanelBg = state.theme === 'dark' ? 'bg-black/40' : 'bg-white/60';
  const settingsPanelText = state.theme === 'dark' ? 'text-white' : 'text-[#1a1a1a]';
  const settingsPanelLabel = state.theme === 'dark' ? 'text-white/40' : 'text-black/40';
  const settingsIconBg = state.theme === 'dark' ? 'bg-black/20 text-white/70' : 'bg-white/40 text-black/70';

  return (
    <main className="w-full h-full flex items-center justify-center relative overflow-hidden">
      <Overlay 
        inputText={state.input}
        translatedText={state.translation}
        isProcessing={state.isProcessing}
        theme={state.theme}
        fontFamily={state.fontFamily}
        onInputChange={onInputChange}
        onKeyDown={onKeyDown}
      />

      {/* 设置按钮容器 */}
      <div className="fixed top-10 right-10 flex flex-col items-end space-y-4 z-50">
        <button 
          onClick={() => setIsSettingsOpen(!isSettingsOpen)}
          className={`
            p-4 rounded-2xl transition-all duration-300 transform 
            hover:scale-105 active:scale-95
            ${settingsIconBg}
            backdrop-blur-2xl border border-white/20 shadow-lg
            glass-container
          `}
        >
          <div className="glass-rim"></div>
          <svg xmlns="http://www.w3.org/2000/svg" className={`h-5 w-5 transition-transform duration-500 ${isSettingsOpen ? 'rotate-90' : 'rotate-0'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>

        {/* 下拉菜单 */}
        <div className={`
          flex flex-col space-y-2 p-2 rounded-2xl
          transition-all duration-300 transform origin-top-right
          ${isSettingsOpen ? 'scale-100 opacity-100' : 'scale-95 opacity-0 pointer-events-none'}
          ${settingsPanelBg}
          backdrop-blur-3xl border border-white/10 shadow-xl
          glass-container min-w-[160px]
        `}>
          <div className="glass-rim"></div>
          
          {/* 切换主题 */}
          <button 
            onClick={toggleTheme}
            className={`flex items-center space-x-3 px-4 py-3 rounded-xl transition-colors w-full text-left ${state.theme === 'dark' ? 'hover:bg-white/10' : 'hover:bg-black/5'}`}
          >
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${state.theme === 'dark' ? 'bg-amber-400/20 text-amber-300' : 'bg-indigo-400/20 text-indigo-600'}`}>
              {state.theme === 'dark' ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M16.071 16.071l.707.707M7.929 7.929l.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" /></svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>
              )}
            </div>
            <span className={`text-xs font-semibold ${settingsPanelText}`}>切换主题</span>
          </button>

          {/* 切换字体 */}
          <button 
            onClick={toggleFont}
            className={`flex items-center space-x-3 px-4 py-3 rounded-xl transition-colors w-full text-left ${state.theme === 'dark' ? 'hover:bg-white/10' : 'hover:bg-black/5'}`}
          >
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center bg-emerald-400/20 text-emerald-500`}>
              <span className="text-sm font-bold">{state.fontFamily === 'sans' ? 'あ' : 'ア'}</span>
            </div>
            <div className="flex flex-col">
              <span className={`text-xs font-semibold ${settingsPanelText}`}>切换字体</span>
              <span className={`text-[9px] font-mono uppercase tracking-wider ${settingsPanelLabel}`}>{state.fontFamily === 'sans' ? 'Sans' : 'Serif'}</span>
            </div>
          </button>
        </div>
      </div>

      {/* 底部提示 */}
      <div className="fixed bottom-10 left-1/2 transform -translate-x-1/2 flex space-x-10 text-[9px] font-mono tracking-[0.4em] select-none uppercase opacity-20 text-black">
        <span>[Enter] Auto Send</span>
        <span>[Esc] Minimize</span>
      </div>
    </main>
  );
};

export default App;
