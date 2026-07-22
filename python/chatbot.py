import os
import discord
import requests
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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").strip()
GROQ_URL = os.getenv("GROQ_URL", "https://api.groq.com/openai/v1/chat/completions")
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Ты злой Discord-бот, отвечаешь с матюками жестко без пощады, как тролль на ксививайде.").strip()

INTENTS = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=INTENTS)


def ask_model(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "Не настроен GROQ_API_KEY."

    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.8,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.HTTPError as exc:
        if response is not None and response.status_code == 429:
            return "Сейчас лимит запросов к модели исчерпан. Попробуй позже."
        return f"Ошибка при обращении к модели: {exc}"
    except Exception as exc:
        return f"Ошибка при обращении к модели: {exc}"


@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")


@bot.command(name="chat")
async def chat(ctx, *, prompt: str):
    if not prompt.strip():
        await ctx.send("Напиши текст после команды. Например: !chat Привет")
        return

    await ctx.send("Думаю...")
    answer = ask_model(prompt)
    await ctx.reply(answer)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    mention_bot = bot.user in message.mentions
    reply_to_bot = (
        isinstance(message.reference, discord.MessageReference)
        and message.reference.resolved is not None
        and message.reference.resolved.author == bot.user
    )

    if not (mention_bot or reply_to_bot):
        return

    await message.channel.send("Думаю...")
    answer = ask_model(message.content)
    await message.channel.send(answer)


if not TOKEN:
    raise RuntimeError("Не задан DISCORD_TOKEN. Экспортируй его перед запуском.")

bot.run(TOKEN)
