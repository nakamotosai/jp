
import { GoogleGenAI } from "@google/genai";
import { ICoreEngine } from "../types";

/**
 * 【内核引擎专家】
 * 职责：负责加载翻译模型，文本预处理，并发推理任务管理。
 */
export class GeminiTranslationEngine implements ICoreEngine {
  private ai: GoogleGenAI;

  constructor() {
    // Initialization must use process.env.API_KEY directly as a named parameter.
    this.ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
  }

  /**
   * 将中文翻译为自然、地道的日文。
   * @param text 用户输入的中文
   */
  async translate(text: string): Promise<string> {
    if (!text.trim()) return "";

    try {
      // Use ai.models.generateContent with the appropriate model for basic text tasks.
      const response = await this.ai.models.generateContent({
        model: 'gemini-3-flash-preview',
        contents: text,
        config: {
          systemInstruction: "你是一个精通中日翻译的专家。用户输入中文，你只需直接返回翻译后的日文结果。不要有任何解释、引文或标点外的多余字符。保持极简、自然、地道。",
          temperature: 0.3,
        },
      });

      // Extract generated text using the .text property from GenerateContentResponse.
      return response.text?.trim() || "";
    } catch (error) {
      console.error("Translation Engine Error:", error);
      throw new Error("翻译引擎任务调度失败");
    }
  }
}
