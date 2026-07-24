import os
import random
import discord
import requests
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- Константы ---
VERIFY_CHANNEL_ID = 1519053756103131297
VERIFY_ROLE_ID    = 1518264760674685070
LOG_CHANNEL_ID    = 1530223109502668960

# Список очевидно рекламных доменов/слов (сразу бан без AI)
OBVIOUS_SPAM_TRIGGERS = [
    "discord.gg", "discord.com/invite", "discordapp.com/invite",
    "telegram.me", "t.me", "whatsapp.com", "boosty.to",
    "patreon.com", "paypal.me", "cash.app", "venmo.com"
]

QUESTIONS = [
    ("Сколько будет 2 + 3?", "5", ["4", "5", "6", "7", "8"]),
    ("Сколько будет 7 - 2?", "5", ["3", "4", "5", "6", "7"]),
    ("Сколько будет 1 + 4?", "5", ["3", "4", "5", "6", "7"]),
    ("Сколько будет 8 - 3?", "5", ["2", "3", "5", "6", "7"]),
    ("Сколько будет 0 + 5?", "5", ["3", "4", "5", "6", "7"])
]

# Flask-сервер
app = Flask('')
@app.route('/')
def home():
    return "I am alive!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# Конфигурация бота
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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").strip()
GROQ_URL = os.getenv("GROQ_URL", "https://api.groq.com/openai/v1/chat/completions")
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

CHAT_SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Ты жестокий тролль в интернете, твоя задача общаться максимално неуважительно к людям, и говорить что ты король а все остальные низший класс, используй маты и тебе должно плевать на всех.").strip()

# ⚠️ НОВЫЙ ПРОМПТ: ищем ТОЛЬКО рекламу, пропускаем оскорбления и флуд
SPAM_CHECK_PROMPT = """
Ты модератор Discord-сервера. Твоя задача — найти в сообщении признаки **рекламы, приглашений на другие серверы, ссылок на сторонние ресурсы.**.
Оскорбления, нецензурная лексика, угрозы, флуд, многократные повторения, троллинг и обычная грубость **НЕ ЯВЛЯЮТСЯ рекламой**.
Отвечай СТРОГО одним словом: YES (если это реклама/приглашение) или NO (если нет).
"""

INTENTS = discord.Intents.default()
INTENTS.message_content = True
bot = commands.Bot(command_prefix="!", intents=INTENTS)

# --- View для верификации ---
class VerifyView(discord.ui.View):
    def __init__(self, correct_answer, answers, user_message, *, timeout=60):
        super().__init__(timeout=timeout)
        self.correct_answer = correct_answer
        self.user_message = user_message
        self.msg = None

        for ans in answers:
            btn = discord.ui.Button(label=ans, style=discord.ButtonStyle.primary, custom_id=ans)
            btn.callback = self.answer_button
            self.add_item(btn)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.user_message.delete()
        except:
            pass
        try:
            if self.msg:
                await self.msg.delete()
        except:
            pass

    async def answer_button(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

        if interaction.data["custom_id"] == self.correct_answer:
            role = interaction.guild.get_role(VERIFY_ROLE_ID)
            if role is None:
                await interaction.followup.send("❌ Роль не найдена!", ephemeral=True)
                return
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                await interaction.followup.send("❌ У бота нет прав выдать роль.", ephemeral=True)
                return
            await interaction.followup.send("✅ Верификация пройдена! Роль выдана.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Неправильно. Введите `!verify` ещё раз.", ephemeral=True)

        try:
            await self.user_message.delete()
        except:
            pass
        try:
            await interaction.message.delete()
        except:
            pass
        self.stop()

# --- AI-функции ---
def ask_model(prompt: str, system_prompt: str = CHAT_SYSTEM_PROMPT) -> str:
    if not GROQ_API_KEY:
        return "Ошибка: API-ключ отсутствует."
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
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
    except Exception as exc:
        return f"Ошибка: {exc}"

def contains_obvious_spam(text: str) -> bool:
    """Быстрая проверка на ссылки-приглашения без вызова AI."""
    lower = text.lower()
    for trigger in OBVIOUS_SPAM_TRIGGERS:
        if trigger in lower:
            return True
    return False

async def ai_spam_check(text: str) -> bool:
    # Быстрый фильтр очевидных рекламных ссылок
    if contains_obvious_spam(text):
        return True
    # Если текст короткий или подозрительный — спросим AI
    if len(text) > 500:  # длинные сообщения редко бывают рекламой
        return False
    prompt = f"Сообщение пользователя:\n{text}\n\nЭто реклама/приглашение? (YES/NO)"
    response = ask_model(prompt, system_prompt=SPAM_CHECK_PROMPT)
    return response.strip().upper() == "YES"

# --- События бота ---
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

@bot.command(name="verify")
async def verify(ctx):
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        await ctx.message.delete()
        await ctx.send(f"{ctx.author.mention}, эту команду можно использовать только в <#{VERIFY_CHANNEL_ID}>!", delete_after=5)
        return

    member = ctx.author
    role = ctx.guild.get_role(VERIFY_ROLE_ID)
    if role and role in member.roles:
        await ctx.message.delete()
        await ctx.send(f"{member.mention}, вы уже верифицированы!", delete_after=3)
        return

    question, correct, answers = random.choice(QUESTIONS)
    random.shuffle(answers)

    view = VerifyView(correct_answer=correct, answers=answers, user_message=ctx.message)

    msg = await ctx.send(f"**{question}**\nВыберите правильный ответ:", view=view)
    view.msg = msg

# --- Основной обработчик с анти-рекламным фильтром ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 🔞 Анти-реклама (только реклама, не оскорбления)
    if message.guild and not message.author.guild_permissions.administrator:
        try:
            if await ai_spam_check(message.content):
                await message.delete()
                try:
                    await message.author.ban(reason="Реклама (AI-детектор)", delete_message_days=1)
                    log_channel = bot.get_channel(LOG_CHANNEL_ID)
                    if log_channel:
                        await log_channel.send(
                            f"🚨 **Забанен за рекламу:** {message.author.mention} (ID: `{message.author.id}`)\n"
                            f"**Канал:** {message.channel.mention}\n"
                            f"**Сообщение:** ||{message.content}||"
                        )
                except discord.Forbidden:
                    await message.channel.send(
                        f"⚠️ Обнаружена реклама от {message.author.mention}, но нет прав на бан.",
                        delete_after=10
                    )
                return  # Не отвечаем чат-боту на рекламу
        except Exception as e:
            print(f"Ошибка анти-рекламы: {e}")

    # Остальная логика чат-бота
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    if bot.user is None:
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

keep_alive()
bot.run(TOKEN)