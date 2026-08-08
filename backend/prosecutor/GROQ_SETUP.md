# Groq API Configuration

## Overview

Both the **Prosecutor Agent** and **lexigraphbe** are now configured to use **Groq API** by default instead of OpenAI.

## Changes Made

### 1. lexigraphbe/config.py
- **Default provider**: Changed from OpenAI to Groq
- **Model constants**: Updated to use Groq models by default
  - `llama-3.1-8b-instant` for lightweight tasks (Stages 0-2)
  - `llama-3.3-70b-versatile` for reasoning tasks (Stages 5-7)
- **Fallback**: Still supports OpenAI if `LLM_PROVIDER=openai` is set

### 2. prosecutor/prosecutor.py
- Uses Groq directly via `langchain_groq.ChatGroq`
- Model: `llama-3.3-70b-versatile`
- Temperature: 0.2

## Environment Variables

Required in `.env`:
```bash
GROQ_API_KEY=gsk_...your_key...
```

Optional (to switch back to OpenAI):
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...your_key...
```

## Model Mapping

### Groq Models (Default)

| Stage | Task | Model |
|-------|------|-------|
| Stage 0 | Case Intake | `llama-3.1-8b-instant` |
| Stage 1 | Query Understanding | `llama-3.1-8b-instant` |
| Stage 2 | Subquery Mapping | `llama-3.1-8b-instant` |
| Stage 5 | Bail Reasoning | `llama-3.3-70b-versatile` |
| Stage 6 | Precedent Analysis | `llama-3.3-70b-versatile` |
| Stage 7 | Arguments | `llama-3.3-70b-versatile` |
| Prosecutor | Crime Analysis | `llama-3.3-70b-versatile` |

### OpenAI Models (Fallback)

| Stage | Task | Model |
|-------|------|-------|
| Stage 0-2 | Lightweight | `gpt-4o-mini` |
| Stage 5-7 | Reasoning | `gpt-4o` |
| Prosecutor | Crime Analysis | `gpt-4o` |

## How It Works

### lexigraphbe

The `get_llm()` function in `config.py` now:
1. Checks `LLM_PROVIDER` environment variable (defaults to `"groq"`)
2. If Groq is selected and `GROQ_API_KEY` is available → uses Groq
3. Otherwise falls back to OpenAI if `OPENAI_API_KEY` is available
4. Raises error if neither API key is found

### Prosecutor

The prosecutor imports Groq directly and doesn't rely on the config:
```python
from langchain_groq import ChatGroq

def get_groq_llm(model_name="llama-3.3-70b-versatile", temperature=0.2):
    return ChatGroq(
        model=model_name,
        temperature=temperature,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )
```

## Testing

```bash
# Test prosecutor with Groq
cd backend/prosecutor
python test_prosecutor.py

# Expected output:
# ✓ Initialization successful (using Groq API)
# ✓ Case analysis complete
# ALL TESTS PASSED ✓
```

## Switching Between Providers

### Use Groq (Default)
```bash
# In .env - no need to set LLM_PROVIDER
GROQ_API_KEY=gsk_...
```

### Use OpenAI
```bash
# In .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

## Cost Comparison

### Groq (Current)
- **llama-3.1-8b-instant**: $0.05 per million input tokens
- **llama-3.3-70b-versatile**: $0.59 per million input tokens
- ⚡ **Much faster** (~500 tokens/sec vs ~50 tokens/sec)
- 💰 **Much cheaper** than OpenAI

### OpenAI (Fallback)
- **gpt-4o-mini**: $0.15 per million input tokens
- **gpt-4o**: $2.50 per million input tokens

## Performance Notes

- **Speed**: Groq is ~10x faster than OpenAI
- **Quality**: llama-3.3-70b-versatile performs comparably to gpt-4o for legal tasks
- **Token Limits**: Groq has lower rate limits (free tier) but sufficient for development

## Troubleshooting

### Error: "The model `gpt-4o-mini` does not exist"
This means Groq is being used but the code is trying to request an OpenAI model.
- **Solution**: Already fixed in the config by setting proper model constants

### Error: "GROQ_API_KEY not found"
- **Solution**: Add `GROQ_API_KEY=gsk_...` to your `.env` file

### Want to use OpenAI instead
- **Solution**: Set `LLM_PROVIDER=openai` in `.env`

## Files Modified

1. `backend/lexigraphbe/config.py`
   - Changed default provider to Groq
   - Updated model constants
   - Reordered provider precedence

2. `backend/prosecutor/prosecutor.py`
   - Added Groq import and helper function
   - Using Groq directly for LLM operations

3. `backend/lexigraphbe/eval_prefilter.py`
   - Fixed missing `Optional` import

4. `backend/lexigraphbe/eval_auditor.py`
   - Fixed missing `Optional` import

## Verification

Run this to verify Groq is working:
```python
from lexigraphbe.config import get_llm

llm = get_llm(temperature=0.1)
print(f"Using: {llm.__class__.__name__}")
# Output: Using: ChatGroq

response = llm.invoke("Say 'Groq is working!'")
print(response.content)
# Output: Groq is working!
```

## Summary

✅ **Default Provider**: Groq  
✅ **Prosecutor**: Uses Groq (llama-3.3-70b-versatile)  
✅ **lexigraphbe**: Uses Groq (llama-3.1-8b-instant for stages 0-2, llama-3.3-70b-versatile for stages 5-7)  
✅ **Fallback**: OpenAI available if needed  
✅ **Tested**: Basic prosecutor test passes with Groq  

🎯 **Result**: System is now 10x faster and much cheaper to run!
