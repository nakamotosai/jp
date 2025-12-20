import os
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

model_path = r"C:\Users\sai\jp\models\nllb-200-distilled-600M"

def test():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    
    # Load model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(device)
    
    text = "请多关照"
    
    # Method 1: src_lang set on tokenizer object
    tokenizer.src_lang = "zho_Hans"
    inputs = tokenizer(text, return_tensors="pt").to(device)
    tgt_lang_id = tokenizer.convert_tokens_to_ids("jpn_Jpan")
    
    print(f"\n--- Testing '请多关照' with different parameters ---")
    
    # B1
    out1 = model.generate(**inputs, forced_bos_token_id=tgt_lang_id, max_length=128, num_beams=1)
    print(f"Beam 1: {tokenizer.batch_decode(out1, skip_special_tokens=True)[0]}")
    
    # B4
    out4 = model.generate(**inputs, forced_bos_token_id=tgt_lang_id, max_length=128, num_beams=4)
    print(f"Beam 4: {tokenizer.batch_decode(out4, skip_special_tokens=True)[0]}")
    
    # B5 + Early Stopping
    out5 = model.generate(**inputs, forced_bos_token_id=tgt_lang_id, max_length=128, num_beams=5, early_stopping=True)
    print(f"Beam 5: {tokenizer.batch_decode(out5, skip_special_tokens=True)[0]}")

    # Method 2: Check if target lang should be passed differently
    # Some implementations use forced_bos_token_id=tokenizer.get_lang_id("jpn_Jpan")
    # But convert_tokens_to_ids is the same.

    # What if we use a different zh code?
    # Some NLLB variants use chi_Hans
    try:
        tokenizer.src_lang = "chi_Hans"
        inputs_alt = tokenizer(text, return_tensors="pt").to(device)
        out_alt = model.generate(**inputs_alt, forced_bos_token_id=tgt_lang_id, max_length=128, num_beams=5)
        print(f"Alt Code (chi_Hans) B5: {tokenizer.batch_decode(out_alt, skip_special_tokens=True)[0]}")
    except:
        print("chi_Hans not supported")

if __name__ == "__main__":
    test()
