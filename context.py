import logging
import openai
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import asyncio
from duckduckgo_search import DDGS
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()  # загружаем переменные из .env

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_TOKEN = os.getenv('OPENAI_TOKEN')


key_index = 0
def switch_key():
    global key_index
    key_index = (key_index + 1) % len(OPENAI_API_KEYS)
    return OPENAI_API_KEYS[key_index]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

openai.api_key = OPENAI_API_KEYS[0]

user_data = {}
user_daily_requests = {}
group_contexts = {}
MAX_TEXT_LENGTH = 200
DAILY_REQUEST_LIMIT = 50

# Поиск
async def google_search(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, region='wt-wt', safesearch='Moderate')
            results_list = list(results)
            if not results_list:
                return "Ничего не нашёл, попробуй переформулировать."
            top_result = results_list[0]
            return f"{top_result['title']}\n{top_result['href']}\n{top_result['body']}"
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        return "Ошибка при поиске. Попробуй позже."

# Контекст групп
async def get_group_context(chat_id: int) -> str:
    return "\n".join(group_contexts.get(chat_id, []))

async def update_group_context(chat_id: int, message: str):
    if chat_id not in group_contexts:
        group_contexts[chat_id] = []
    group_contexts[chat_id].append(message)
    if len(group_contexts[chat_id]) > 10:
        group_contexts[chat_id] = group_contexts[chat_id][-10:]

async def reset_group_context(chat_id: int):
    if chat_id in group_contexts:
        del group_contexts[chat_id]
    return "Бля, а о чём мы говорили? Всё стерто к хуям."

# Запрос к GPT
async def ask_gpt(prompt: str, user_id: int, system_message: str) -> str:
    try:
        openai.api_key = switch_key()

        if user_id not in user_data:
            user_data[user_id] = {"questions": []}
        memory = user_data[user_id]["questions"][-3:]

        await asyncio.sleep(1)

        messages = [{"role": "system", "content": system_message}]
        for q in memory:
            messages.append({"role": "user", "content": q})
        messages.append({"role": "user", "content": prompt})

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.8,
            max_tokens=500,
        )

        answer = response.choices[0].message['content'].strip()

        user_data[user_id]["questions"].append(prompt)
        if len(user_data[user_id]["questions"]) > 3:
            user_data[user_id]["questions"] = user_data[user_id]["questions"][-3:]

        return answer

    except openai.error.RateLimitError:
        await asyncio.sleep(60)
        return await ask_gpt(prompt, user_id, system_message)
    except Exception as e:
        print(f"GPT ошибка: {e}")
        return "Хрррр-бибибибиб."

# Сброс лимитов
def reset_user_limits():
    now = datetime.now()
    for user_id, data in list(user_daily_requests.items()):
        if data['last_reset'] + timedelta(days=1) <= now:
            user_daily_requests[user_id] = {'count': 0, 'last_reset': now}

# Обработка сообщений
@dp.message(F.text)
async def handle_message(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    if text.lower() == "/сброс":
        reset_msg = await reset_group_context(chat_id)
        await message.answer(reset_msg)
        return

    if len(text) > MAX_TEXT_LENGTH:
        await message.answer(f"Слишком много текста. Урежь до {MAX_TEXT_LENGTH} символов.")
        return

    now = datetime.now()
    reset_user_limits()
    if user_id not in user_daily_requests:
        user_daily_requests[user_id] = {'count': 0, 'last_reset': now}
    if user_daily_requests[user_id]['count'] >= DAILY_REQUEST_LIMIT:
        await message.answer("Ты исчерпал лимит запросов на сегодня.")
        return
    user_daily_requests[user_id]['count'] += 1

    text_lower = text.lower()

    # Гугл
    if text_lower.startswith("гугл ") or text_lower.startswith("поиск ") or ("гугл" in text_lower and chat_type != "private"):
        query = text.split(maxsplit=1)[1] if " " in text else ""
        reply = await google_search(query) if query else "Что гуглить-то, брат?"
        await message.answer(reply)
        return

    # Художник
    if text_lower.startswith("нарисуй ") or text_lower.startswith("сгенерируй ") or ("нарисуй" in text_lower or "сгенерируй" in text_lower and chat_type != "private"):
        reply = await ask_gpt(text, user_id, system_message="Ты талантливый художник, который описывает визуальные сцены для генерации изображений. Пиши чётко, красиво, с описанием деталей на русском.")
        await message.answer(reply)
        return

    # Личный чат
    if chat_type == "private":
        reply = await ask_gpt(text, user_id, system_message="Ты — разговорчивый и дерзкий помощник с чувством юмора. Пиши по-русски. Не повторяйся, не говори шаблонно.")
        await message.answer(reply)
        return

    # Групповой чат
    if "чат" in text_lower:
        await update_group_context(chat_id, f"{message.from_user.first_name}: {text}")
        context = await get_group_context(chat_id)
        reply = await ask_gpt(text, user_id, system_message=f"Ты бот в Telegram-группе. Общайся легко, по-русски. Контекст:\n{context}")
        await message.answer(reply)
        return

# Запуск
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
