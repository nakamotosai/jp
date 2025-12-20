import os
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

model_path = r"C:\Users\sai\jp\models\nllb-200-distilled-600M"

def test_config(name, text, src_lang, tgt_lang, num_beams=1):
    print(f"\n--- Testing Config: {name} ---")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    try:
        # Re-load for each config to be sure
        tokenizer = AutoTokenizer.from_pretrained(model_path, src_lang=src_lang)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(device)
        
        inputs = tokenizer(text, return_tensors="pt").to(device)
        tgt_lang_id = tokenizer.convert_tokens_to_ids(tgt_lang)
        
        translated_tokens = model.generate(
            **inputs, 
            forced_bos_token_id=tgt_lang_id, 
            max_length=128,
            num_beams=num_beams
        )
        result = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
        print(f"Input: {text}")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error in {name}: {e}")

if __name__ == "__main__":
    test_phrase = "请多关照"
    
    # Config 1: src_lang in init, num_beams=1 (Current)
    test_config("Init-src-lang-B1", test_phrase, "zho_Hans", "jpn_Jpan", num_beams=1)
    
    # Config 2: src_lang in init, num_beams=5 (Better quality)
    test_config("Init-src-lang-B5", test_phrase, "zho_Hans", "jpn_Jpan", num_beams=5)
    
    # Config 3: Try different zh code (zho_Hans vs chi_Hans?)
    # NLLB usually uses zho_Hans for Simplified Chinese
    test_config("Alt-Lang-Code-B5", test_phrase, "zho_Hans", "jpn_Jpan", num_beams=5)
