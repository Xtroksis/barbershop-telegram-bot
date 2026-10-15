import json
import os
from datetime import date, timedelta

import telebot
from telebot import types

from config import TOKEN, ADMIN_ID

bot = telebot.TeleBot(TOKEN)
FILE = "bookings.json"

SERVICES = [
    ("Стрижка", 1500),
    ("Стрижка + борода", 2300),
    ("Моделирование бороды", 1000),
    ("Детская стрижка", 1000),
]
HOURS = [f"{h}:00" for h in range(10, 20)]
draft = {}  # временные данные записи по user_id


def load():
    if os.path.exists(FILE):
        with open(FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save(data):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def busy_times(day):
    return {b["time"] for b in load() if b["day"] == day}


def nice_day(day):
    return date.fromisoformat(day).strftime("%d.%m")


def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✂️ Записаться", callback_data="book"),
        types.InlineKeyboardButton("💰 Прайс", callback_data="price"),
        types.InlineKeyboardButton("📋 Мои записи", callback_data="my"),
        types.InlineKeyboardButton("📍 Контакты", callback_data="contacts"),
    )
    return kb


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "💈 Барбершоп «Борода и ножницы» (демо-бот)\n\n"
        "Это пример бота для записи клиентов. Нажмите «Записаться», "
        "чтобы пройти весь путь клиента.",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda c: True)
def on_click(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    uid = call.from_user.id
    data = call.data

    if data == "menu":
        bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())

    elif data == "price":
        lines = [f"• {n} — {p} ₽" for n, p in SERVICES]
        bot.send_message(chat_id, "💰 Прайс:\n" + "\n".join(lines), reply_markup=main_menu())

    elif data == "contacts":
        bot.send_message(
            chat_id,
            "📍 г. Москва, ул. Примерная, 1\n🕙 Ежедневно 10:00–20:00\n📞 +7 000 000-00-00",
            reply_markup=main_menu(),
        )

    elif data == "book":
        kb = types.InlineKeyboardMarkup(row_width=1)
        for i, (name, price) in enumerate(SERVICES):
            kb.add(types.InlineKeyboardButton(f"{name} — {price} ₽", callback_data=f"svc:{i}"))
        bot.send_message(chat_id, "Выберите услугу:", reply_markup=kb)

    elif data.startswith("svc:"):
        idx = int(data.split(":", 1)[1])
        draft[uid] = {"service": SERVICES[idx][0]}
        kb = types.InlineKeyboardMarkup(row_width=3)
        today = date.today()
        for i in range(1, 6):
            d = today + timedelta(days=i)
            kb.add(types.InlineKeyboardButton(d.strftime("%d.%m"), callback_data=f"day:{d.isoformat()}"))
        bot.send_message(chat_id, "Выберите день:", reply_markup=kb)

    elif data.startswith("day:"):
        if uid not in draft:
            bot.send_message(chat_id, "Начнём заново:", reply_markup=main_menu())
            return
        day = data.split(":", 1)[1]
        draft[uid]["day"] = day
        free = [t for t in HOURS if t not in busy_times(day)]
        if not free:
            bot.send_message(chat_id, "На этот день всё занято. Выберите другой:", reply_markup=main_menu())
            return
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(*[types.InlineKeyboardButton(t, callback_data=f"time:{t}") for t in free])
        bot.send_message(chat_id, f"Свободное время на {nice_day(day)}:", reply_markup=kb)

    elif data.startswith("time:"):
        if uid not in draft or "day" not in draft[uid]:
            bot.send_message(chat_id, "Начнём заново:", reply_markup=main_menu())
            return
        draft[uid]["time"] = data.split(":", 1)[1]
        msg = bot.send_message(chat_id, "Как вас зовут?")
        bot.register_next_step_handler(msg, finish_booking)

    elif data == "my":
        mine = [b for b in load() if b["user_id"] == uid]
        if not mine:
            bot.send_message(chat_id, "У вас пока нет записей.", reply_markup=main_menu())
            return
        for b in mine:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel:{b['id']}"))
            bot.send_message(
                chat_id,
                f"✂️ {b['service']}\n📅 {nice_day(b['day'])} в {b['time']}",
                reply_markup=kb,
            )

    elif data.startswith("cancel:"):
        bid = int(data.split(":", 1)[1])
        bookings = load()
        target = next((b for b in bookings if b["id"] == bid and b["user_id"] == uid), None)
        if target:
            bookings.remove(target)
            save(bookings)
            bot.send_message(chat_id, "Запись отменена.", reply_markup=main_menu())
            if ADMIN_ID:
                bot.send_message(
                    ADMIN_ID,
                    f"❌ Отмена: {target['name']}, {target['service']}, "
                    f"{nice_day(target['day'])} {target['time']}",
                )
        else:
            bot.send_message(chat_id, "Запись не найдена.", reply_markup=main_menu())


def finish_booking(message):
    uid = message.from_user.id
    if not message.text or message.text.startswith("/") or uid not in draft:
        bot.send_message(message.chat.id, "Запись отменена.", reply_markup=main_menu())
        draft.pop(uid, None)
        return

    d = draft.pop(uid)
    if d.get("time") in busy_times(d["day"]):
        bot.send_message(message.chat.id, "Это время уже заняли, выберите другое.", reply_markup=main_menu())
        return

    bookings = load()
    new_id = max([b["id"] for b in bookings], default=0) + 1
    bookings.append(
        {
            "id": new_id,
            "user_id": uid,
            "name": message.text,
            "service": d["service"],
            "day": d["day"],
            "time": d["time"],
        }
    )
    save(bookings)

    bot.send_message(
        message.chat.id,
        f"✅ Вы записаны!\n\n✂️ {d['service']}\n📅 {nice_day(d['day'])} в {d['time']}\n\n"
        "Ждём вас!",
        reply_markup=main_menu(),
    )
    if ADMIN_ID:
        bot.send_message(
            ADMIN_ID,
            f"📩 Новая запись: {message.text} (@{message.from_user.username})\n"
            f"{d['service']}, {nice_day(d['day'])} в {d['time']}",
        )


@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(message.chat.id, "Выберите действие в меню:", reply_markup=main_menu())


bot.infinity_polling()