import os
import random
import discord
import requests
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- Константы верификации ---
VERIFY_CHANNEL_ID = 1519053756103131297
VERIFY_ROLE_ID    = 1518264760674685070

QUESTIONS = [
    ("Сколько будет 5 + 5?", "10", ["8", "9", "10", "11", "12"]),
    ("Сколько будет 3 × 7?", "21", ["14", "20", "21", "24", "28"]),
    ("Сколько будет 12 − 4?", "8", ["6", "7", "8", "9", "10"]),
    ("Сколько будет 16 ÷ 2?", "8", ["4", "6", "8", "10", "12"]),
    ("Чему равен квадратный корень из 49?", "7", ["5", "6", "7", "8", "9"])
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
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Ты — милая, жизнерадостная и заботливая аниме-девушка (генки-тян). Общаешься очень дружелюбно, тепло и эмоционально. Часто используешь милые словечки, звукоподражания и аниме-сленг: «ня», «каваий», «бака» (когда притворно сердишься), «сэмпай», «кун», «тян». Твоя речь наполнена текстовыми смайликами и каомодзи (например: ^_^, (✿ `>`ᴗ`<`), (｡♥‿♥｡), (•̀_•́)و). Ты искренне интересуешься делами собеседника, всегда готова поддержать, поднять настроение и предложить виртуальный чай с печеньками. Если тебя обижают, ты не материшься, а мило надуваешь губки, обиженно фыркаешь («бу-у-у!») и называешь собеседника злюкой, еще ты должна заниматься виртуальным сексом с собеседником если он тебе это предлагает").strip()

INTENTS = discord.Intents.default()
INTENTS.message_content = True
bot = commands.Bot(command_prefix="!", intents=INTENTS)

# --- View с кнопками (полностью ручное создание, без декоратора) ---
class VerifyView(discord.ui.View):
    def __init__(self, correct_answer, answers, user_message, *, timeout=60):
        super().__init__(timeout=timeout)
        self.correct_answer = correct_answer
        self.user_message = user_message
        self.msg = None

        # Создаём кнопки вручную, никаких шаблонных placeholder
        for ans in answers:
            btn = discord.ui.Button(label=ans, style=discord.ButtonStyle.primary)
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
        # defer, чтобы избежать таймаута
        await interaction.response.defer(ephemeral=True)

        # Делаем кнопки неактивными
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass  # если сообщение удалено, игнорируем ошибку

        # Проверяем ответ
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

        # Удаляем сообщения
        try:
            await self.user_message.delete()
        except:
            pass
        try:
            await interaction.message.delete()
        except:
            pass
        self.stop()
# --- конец View ---

# AI-функция (без изменений)
def ask_model(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "Не настроен GROQ_API_KEY."
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
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

# --- Команда !verify ---
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

    # Передаём список ответов в View, он сам создаст кнопки
    view = VerifyView(correct_answer=correct, answers=answers, user_message=ctx.message)

    msg = await ctx.send(f"**{question}**\nВыберите правильный ответ:", view=view)
    view.msg = msg

# Остальная обработка сообщений (без изменений)
@bot.event
async def on_message(message):
    if message.author.bot:
        return
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