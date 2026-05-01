# Vera — magicpin AI Challenge Submission

**Team:** ShortlistMe  
**Track:** Build a Merchant AI Assistant ("Vera")

---

## Approach

### Architecture

```
bot_server.py (HTTP, port 8080)
    └── bot.py              compose()
            └── compose_engine/
                    ├── trigger_router.py   trigger kind → prompt strategy
                    ├── prompt_builder.py   4-context → LLM prompt
                    ├── llm_client.py       multi-provider LLM wrapper
                    └── validator.py        post-LLM checks + fixes
conversation_handlers.py    multi-turn reply handler
generate_submission.py      batch generates submission.jsonl
```

### Key Design Decisions

**1. Trigger Router**  
Every trigger kind gets a dedicated strategy config: framing style, which compulsion levers to use, CTA shape, and voice note. This ensures `research_digest` messages sound like peer knowledge-sharing while `renewal_due` messages use loss aversion + social proof — never interchangeable.

**2. Prompt Engineering for All 5 Judge Dimensions**  
The prompt builder injects:
- Category voice, taboos, peer stats, digest items → *Category Fit + Specificity*
- Merchant name, city, CTR vs peer median, actual offers, signals, history → *Merchant Fit*
- Trigger payload in full + resolved digest items → *Trigger Relevance*
- Explicit compulsion lever instructions per trigger kind → *Engagement Compulsion*
- Concrete numbers from context (not hallucinated) → *Specificity*

**3. Post-LLM Validator**  
Catches: preambles, multiple CTAs, category taboo words, wrong `send_as` scope, empty bodies. Fixes what it safely can, flags the rest.

**4. Multi-turn Handler**  
- **Auto-reply detection**: 15 canned phrase patterns + generic short-ack detection → exits after 2nd auto-reply
- **Intent routing**: "yes/let's do it/kar do" → action mode (no re-qualifying); "stop/not interested" → graceful exit; "?" → answer from context
- **Graceful exit**: After 6 unanswered turns, politely sign off

### What Tradeoffs Were Made

| Decision | Tradeoff |
|---|---|
| Temperature = 0.0 | Deterministic outputs, slightly less creative than temp=0.3 |
| Single-pass LLM call | Faster (<5s/message), but no self-critique loop |
| Seed dataset used for submission | Full expanded dataset (50 merchants, 100 triggers) needs `generate_dataset.py` first |
| No RAG/retrieval | Digest items injected directly in prompt — simple and effective for 5 categories |

### Additional Context That Would Have Helped Most

1. **Real conversation transcripts** (thousands, not dozens) — to fine-tune intent detection and tone calibration per category
2. **Actual merchant reply rates** by message type — to validate which compulsion levers work best in practice
3. **WhatsApp template approval patterns** — to know which message shapes Meta actually approves for first-outbound
4. **Merchant language detection signals** — which merchants actually prefer Hindi vs English (language field in context is declared but rarely matches actual usage)

---

## Running Locally

### 1. Set your LLM API key

```powershell
# Windows PowerShell
$env:LLM_PROVIDER = "gemini"    # or openai, anthropic, groq, deepseek
$env:LLM_API_KEY  = "your_key_here"
```

Supported providers: `gemini` (free tier at ai.google.dev), `openai`, `anthropic`, `groq`, `deepseek`, `ollama`

### 2. Expand the dataset (optional but recommended)

```powershell
cd dataset
python generate_dataset.py --out ./expanded
cd ..
```

### 3. Start the bot server

```powershell
python bot_server.py
```

### 4. Run the judge simulator (in a second terminal)

Edit `judge_simulator.py` — set `LLM_API_KEY` and `LLM_PROVIDER` at the top, then:

```powershell
python judge_simulator.py
```

### 5. Generate submission.jsonl

```powershell
python generate_submission.py
```

### Quick compose test

```powershell
python bot.py
```

---

## File Structure

```
magicpin-ai-challenge/
├── bot.py                       # standalone compose() — primary submission artifact
├── bot_server.py                # HTTP server (judge talks to this)
├── conversation_handlers.py     # multi-turn reply handler (tiebreaker)
├── generate_submission.py       # batch generates submission.jsonl
├── submission.jsonl             # 30 pre-generated test outputs
├── compose_engine/
│   ├── trigger_router.py        # trigger kind → prompt strategy (30 trigger types)
│   ├── prompt_builder.py        # builds LLM prompt from 4 contexts
│   ├── llm_client.py            # multi-provider LLM wrapper
│   └── validator.py             # post-LLM validation + fixes
├── dataset/                     # provided dataset (unchanged)
└── judge_simulator.py           # provided judge (unchanged)
```
