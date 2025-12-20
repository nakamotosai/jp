
import React, { useMemo, useState, useRef, useEffect } from 'react';
import { UI_CONFIG } from '../constants';
import { Theme, FontFamily } from '../types';

interface OverlayProps {
  inputText: string;
  translatedText: string;
  isProcessing: boolean;
  theme: Theme;
  fontFamily: FontFamily;
  onInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}

/**
 * 【UI/UX 专家】
 * 职责：实现极致半透明磨砂玻璃（Frosted Glass）质感。
 * - 穿透感：使用 backdrop-blur 和 saturate 提升视觉通透性。
 * - 分层设计：上下区域使用微弱的背景色差来区分功能区。
 */
export const Overlay: React.FC<OverlayProps> = ({ 
  inputText, 
  translatedText, 
  isProcessing,
  theme,
  fontFamily,
  onInputChange,
  onKeyDown
}) => {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartPos = useRef({ x: 0, y: 0 });

  const topMode: Theme = theme === 'dark' ? 'dark' : 'light';
  const bottomMode: Theme = theme === 'dark' ? 'light' : 'dark';

  const topStyles = UI_CONFIG[topMode];
  const bottomStyles = UI_CONFIG[bottomMode];
  const fontClass = UI_CONFIG.fonts[fontFamily];
  
  const getFontSize = (text: string) => {
    const len = text.length;
    if (len > 80) return 'text-sm';
    if (len > 40) return 'text-lg';
    return 'text-2xl';
  };

  const jpFontSize = useMemo(() => getFontSize(translatedText), [translatedText]);
  const cnFontSize = useMemo(() => getFontSize(inputText), [inputText]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).tagName === 'INPUT') return;
    setIsDragging(true);
    dragStartPos.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y
    };
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      setPosition({
        x: e.clientX - dragStartPos.current.x,
        y: e.clientY - dragStartPos.current.y
      });
    };
    const handleMouseUp = () => setIsDragging(false);

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  return (
    <div 
      className={`fixed inset-0 pointer-events-none flex items-center justify-center ${fontClass}`}
      style={{ zIndex: 40 }}
    >
      <div 
        onMouseDown={handleMouseDown}
        style={{ 
          transform: `translate(${position.x}px, ${position.y}px)`,
          cursor: isDragging ? 'grabbing' : 'grab'
        }}
        className={`
          glass-container pointer-events-auto
          ${UI_CONFIG.light.BACKDROP}
          rounded-[1.75rem]
          transition-all duration-300
          border ${UI_CONFIG.light.BORDER}
          min-w-[340px] max-w-[600px]
          min-h-[200px] max-h-[480px]
          w-fit h-fit overflow-hidden
          flex flex-col
          relative
          ${isDragging ? 'shadow-3xl scale-[1.02]' : 'shadow-2xl scale-100'}
          will-change-transform
        `}
      >
        <div className="glass-rim"></div>
        <div className="glass-glare"></div>

        {/* 上半部分：日文 */}
        <div className={`flex-1 flex items-center px-10 py-7 transition-colors duration-500 ${topStyles.CARD_BG} border-b border-white/10`}>
          <div className="flex items-center space-x-5 w-full">
            <div className={`
              font-['JetBrains_Mono'] text-[11px] font-bold ${topStyles.TEXT_PRIMARY}
              select-none tracking-tighter shrink-0 
              flex items-center justify-center
              px-2 py-1 rounded-lg border
              ${topMode === 'dark' ? 'bg-white/10 border-white/10' : 'bg-black/5 border-black/5'}
              backdrop-blur-md
            `}>
              日&gt;
            </div>
            <div className={`
              ${jpFontSize} font-bold tracking-tight ${topStyles.TEXT_PRIMARY} 
              transition-all duration-300 break-words leading-tight
              ${isProcessing ? 'opacity-40' : 'opacity-100'}
              flex-1
            `}>
              {translatedText || (isProcessing ? "..." : "")}
            </div>
          </div>
        </div>

        {/* 下半部分：中文 */}
        <div className={`flex-1 flex items-center px-10 py-7 transition-colors duration-500 ${bottomStyles.CARD_BG}`}>
          <div className="flex items-center space-x-5 w-full relative">
            <div className={`
              font-['JetBrains_Mono'] text-[11px] font-bold ${bottomStyles.TEXT_PRIMARY}
              select-none tracking-tighter shrink-0 
              flex items-center justify-center
              px-2 py-1 rounded-lg border
              ${bottomMode === 'dark' ? 'bg-white/10 border-white/10' : 'bg-black/5 border-black/5'}
              backdrop-blur-md
            `}>
              中&gt;
            </div>
            <div className="relative flex items-center flex-1 min-h-[1.5em]">
              <input
                autoFocus
                type="text"
                value={inputText}
                onChange={onInputChange}
                onKeyDown={onKeyDown}
                onMouseDown={(e) => e.stopPropagation()}
                className="absolute inset-0 opacity-0 cursor-text z-20 w-full h-full bg-transparent border-none outline-none"
              />
              <div className={`
                ${cnFontSize} font-medium tracking-tight ${bottomStyles.TEXT_SECONDARY} 
                flex items-center w-full break-words leading-tight
              `}>
                {inputText}
                <span className={`inline-block w-[3px] h-[0.9em] ml-1.5 ${bottomMode === 'dark' ? 'bg-white/70' : 'bg-black/70'} cursor-blink shrink-0 rounded-full`}></span>
                {!inputText && (
                  <span className={`${bottomStyles.LABEL} text-lg font-normal ml-0.5 select-none italic opacity-20`}>
                    输入中文测试...
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
