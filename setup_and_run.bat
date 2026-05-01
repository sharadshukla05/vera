@echo off
REM ============================================================
REM  Vera Bot — Quick Setup Script for Windows
REM  Run this file to configure your API key and start the bot
REM ============================================================

echo.
echo  ============================================================
echo   magicpin AI Challenge - Vera Bot Setup
echo  ============================================================
echo.

REM ── STEP 1: Set your API key ────────────────────────────────
echo  STEP 1: Configure your LLM provider
echo  ─────────────────────────────────────────────────────────
echo  Choose your provider (free options marked with *):
echo.
echo    1. Gemini 1.5 Flash  * FREE - get key at: https://ai.google.dev
echo    2. OpenAI GPT-4o-mini
echo    3. Anthropic Claude Haiku
echo    4. Groq Llama 70B    * FREE - get key at: https://console.groq.com
echo    5. DeepSeek Chat
echo.
set /p CHOICE="Enter choice (1-5, default=1): "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" (
    set LLM_PROVIDER=gemini
    echo  Provider: Gemini 1.5 Flash
) else if "%CHOICE%"=="2" (
    set LLM_PROVIDER=openai
    echo  Provider: OpenAI GPT-4o-mini
) else if "%CHOICE%"=="3" (
    set LLM_PROVIDER=anthropic
    echo  Provider: Anthropic Claude Haiku
) else if "%CHOICE%"=="4" (
    set LLM_PROVIDER=groq
    echo  Provider: Groq Llama 3.1 70B
) else if "%CHOICE%"=="5" (
    set LLM_PROVIDER=deepseek
    echo  Provider: DeepSeek Chat
) else (
    set LLM_PROVIDER=gemini
    echo  Provider: Gemini 1.5 Flash (default)
)

echo.
set /p LLM_API_KEY="Paste your API key: "

if "%LLM_API_KEY%"=="" (
    echo  ERROR: No API key provided. Exiting.
    pause
    exit /b 1
)

echo.
echo  API key set. ✓
echo.

REM ── STEP 2: Expand dataset ──────────────────────────────────
echo  STEP 2: Expanding dataset (50 merchants, 200 customers, 100 triggers)...
python dataset\generate_dataset.py --seed-dir dataset --out dataset\expanded
if errorlevel 1 (
    echo  ERROR: Dataset generation failed.
    pause
    exit /b 1
)
echo  Dataset expanded. ✓
echo.

REM ── STEP 3: Quick smoke test ─────────────────────────────────
echo  STEP 3: Quick smoke test (Dr. Meera + research_digest)...
python bot.py
if errorlevel 1 (
    echo  ERROR: bot.py test failed. Check your API key.
    pause
    exit /b 1
)
echo.

REM ── STEP 4: Generate submission ──────────────────────────────
echo  STEP 4: Generating submission.jsonl (30 messages)...
echo  This will take 2-5 minutes...
echo.
python generate_submission.py
if errorlevel 1 (
    echo  ERROR: Submission generation failed.
    pause
    exit /b 1
)
echo.
echo  ============================================================
echo   DONE! Your submission.jsonl is ready.
echo  ============================================================
echo.
echo  Next steps:
echo    1. Review submission.jsonl
echo    2. Start server:  python bot_server.py
echo    3. Run judge:     python judge_simulator.py (in another terminal)
echo.
pause
