import discord
from discord.ext import commands

# Настройка интентов
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True  # Обязательно для работы команд

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успешно запущен и готов к работе!")


# ==========================================
# КОМАНДЫ ДЛЯ СОЗДАТЕЛЯ СЕРВЕРА
# ==========================================


def is_server_owner():
  """Проверка, является ли пользователь создателем сервера"""

  async def predicate(ctx):
    if ctx.author != ctx.guild.owner:
      raise commands.CheckFailure(
          "Эту команду может использовать только создатель сервера!"
      )
    return True

  return commands.check(predicate)


@bot.command(name="clear")
@is_server_owner()
async def clear_server(ctx):
  guild = ctx.guild
  await ctx.send(
      "⚠️ **Внимание!** Начинаю полное очищение сервера: удаляю все каналы и"
      " категории..."
  )

  # 1. Удаляем все каналы и категории на сервере
  for channel in guild.channels:
    try:
      await channel.delete()
    except Exception as e:
      print(f"Не удалось удалить канал {channel.name}: {e}")

  # 2. Создаем роли (проверяем, чтобы не дублировать)
  roles_data = [
      {
          "name": "👑 ┃ Создатель",
          "color": discord.Color.from_rgb(255, 0, 0),
          "permissions": discord.Permissions(administrator=True),
          "hoist": True,
      },
      {
          "name": "🛡️ ┃ Главный Администратор",
          "color": discord.Color.from_rgb(255, 128, 0),
          "permissions": discord.Permissions(administrator=True),
          "hoist": True,
      },
      {
          "name": "⚡ ┃ Куратор",
          "color": discord.Color.from_rgb(255, 255, 0),
          "permissions": discord.Permissions(
              manage_roles=True, kick_members=True, manage_channels=True
          ),
          "hoist": True,
      },
      {
          "name": "🔨 ┃ Модератор",
          "color": discord.Color.from_rgb(0, 200, 255),
          "permissions": discord.Permissions(
              kick_members=True, ban_members=True, manage_messages=True
          ),
          "hoist": True,
      },
      {
          "name": "👮 ┃ Хелпер",
          "color": discord.Color.from_rgb(0, 100, 255),
          "permissions": discord.Permissions(
              manage_messages=True, mute_members=True
          ),
          "hoist": True,
      },
      {
          "name": "🎉 ┃ Ивентер",
          "color": discord.Color.from_rgb(255, 0, 255),
          "permissions": discord.Permissions(manage_events=True),
          "hoist": True,
      },
      {
          "name": "💎 ┃ Бустер Сервера",
          "color": discord.Color.from_rgb(244, 127, 255),
          "permissions": discord.Permissions(
              priority_speaker=True, attach_files=True, external_emojis=True
          ),
          "hoist": True,
      },
      {
          "name": "⭐ ┃ VIP Участник",
          "color": discord.Color.from_rgb(170, 0, 255),
          "permissions": discord.Permissions(
              change_nickname=True, attach_files=True
          ),
          "hoist": True,
      },
      {
          "name": "💬 ┃ Активный участник",
          "color": discord.Color.from_rgb(0, 255, 128),
          "permissions": discord.Permissions.none(),
          "hoist": True,
      },
      {
          "name": "👤 ┃ Участник",
          "color": discord.Color.default(),
          "permissions": discord.Permissions.none(),
          "hoist": True,
      },
  ]

  created_roles = {}
  for r_info in roles_data:
    existing_role = discord.utils.get(guild.roles, name=r_info["name"])
    if not existing_role:
      role = await guild.create_role(
          name=r_info["name"],
          color=r_info["color"],
          permissions=r_info["permissions"],
          hoist=r_info["hoist"],
      )
      created_roles[r_info["name"]] = role
    else:
      created_roles[r_info["name"]] = existing_role

  # Права доступа
  everyone_role = guild.default_role
  overwrites_info = {
      everyone_role: discord.PermissionOverwrite(
          read_messages=True, send_messages=False
      )
  }
  overwrites_general = {
      everyone_role: discord.PermissionOverwrite(read_messages=True)
  }

  # --- КАТЕГОРИЯ: ИНФОРМАЦИЯ ---
  cat_info = await guild.create_category("📌 ┃ НАВИГАЦИЯ И ИНФО")
  await guild.create_text_channel(
      "📜・правила-чата", category=cat_info, overwrites=overwrites_info
  )
  news_channel = await guild.create_text_channel(
      "📰・новости-сервера", category=cat_info, overwrites=overwrites_info
  )
  await guild.create_text_channel(
      "🎉・конкурсы-ивенты", category=cat_info, overwrites=overwrites_info
  )
  await guild.create_text_channel(
      "💎・бусты-и-привилегии", category=cat_info, overwrites=overwrites_info
  )
  await guild.create_text_channel(
      "🔗・полезные-ссылки", category=cat_info, overwrites=overwrites_info
  )

  # --- КАТЕГОРИЯ: ОБЩЕНИЕ ---
  cat_chat = await guild.create_category("💬 ┃ КОМЬЮНИТИ")
  await guild.create_text_channel(
      "💬・общий-чат", category=cat_chat, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "🤖・команды-ботов", category=cat_chat, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "📷・медиа-контент", category=cat_chat, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "💡・предложения", category=cat_chat, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "🔮・мемы-и-арты", category=cat_chat, overwrites=overwrites_general
  )

  # --- КАТЕГОРИЯ: ИГРЫ И МУЗЫКА ---
  cat_games = await guild.create_category("🎮 ┃ ИГРЫ И РАЗВЛЕЧЕНИЯ")
  await guild.create_text_channel(
      "🎮・игровой-чат", category=cat_games, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "🎧・музыкальный-чат", category=cat_games, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "🎲・аркады-и-игры", category=cat_games, overwrites=overwrites_general
  )

  # --- КАТЕГОРИЯ: ГОЛОСОВЫЕ КАНАЛЫ ---
  cat_voice = await guild.create_category("🔊 ┃ ГОЛОСОВЫЕ КОМНАТЫ")
  await guild.create_voice_channel("🔊 ┃ Главный Лобби", category=cat_voice)
  await guild.create_voice_channel("🎮 ┃ Дуо / Трио (1)", category=cat_voice)
  await guild.create_voice_channel("🎮 ┃ Дуо / Трио (2)", category=cat_voice)
  await guild.create_voice_channel("👥 ┃ Сквад / Команда", category=cat_voice)
  await guild.create_voice_channel("🎧 ┃ Чилаут и Музыка", category=cat_voice)
  await guild.create_voice_channel("🌙 ┃ Уединение", category=cat_voice)
  await guild.create_voice_channel("💤 ┃ AFK Зона", category=cat_voice)

  # --- КАТЕГОРИЯ: АДМИНИСТРАЦИЯ (СКРЫТАЯ) ---
  overwrites_admin = {
      everyone_role: discord.PermissionOverwrite(read_messages=False),
      created_roles["👑 ┃ Создатель"]: discord.PermissionOverwrite(
          read_messages=True
      ),
      created_roles["🛡️ ┃ Главный Администратор"]: discord.PermissionOverwrite(
          read_messages=True
      ),
      created_roles["⚡ ┃ Куратор"]: discord.PermissionOverwrite(
          read_messages=True
      ),
      created_roles["🔨 ┃ Модератор"]: discord.PermissionOverwrite(
          read_messages=True
      ),
      created_roles["👮 ┃ Хелпер"]: discord.PermissionOverwrite(
          read_messages=True
      ),
  }

  cat_admin = await guild.create_category("🛡️ ┃ УПРАВЛЕНИЕ")
  await guild.create_text_channel(
      "🔒・админ-чат", category=cat_admin, overwrites=overwrites_admin
  )
  await guild.create_text_channel(
      "🛠️・логи-сервера", category=cat_admin, overwrites=overwrites_admin
  )
  await guild.create_text_channel(
      "📋・жалобы-и-отчеты", category=cat_admin, overwrites=overwrites_admin
  )
  await guild.create_voice_channel(
      "🔒 ┃ Совещание", category=cat_admin, overwrites=overwrites_admin
  )

  await news_channel.send(
      "✅ **Очистка и настройка сервера успешно завершены!**\nВсе старые каналы"
      " удалены, создана новая структура."
  )


@bot.command(name="setup")
@is_server_owner()
async def setup_server(ctx):
  await ctx.invoke(bot.get_command("clear"))


# ==========================================
# КОМАНДЫ МОДЕРАЦИИ (Только для модераторов/админов)
# ==========================================


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_member(
    ctx, member: discord.Member, *, reason: str = "Причина не указана"
):
  await member.ban(reason=reason)
  await ctx.send(
      f"🔨 Пользователь **{member.mention}** заблокирован. Причина: `{reason}`"
  )


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_member(
    ctx, member: discord.Member, *, reason: str = "Причина не указана"
):
  await member.kick(reason=reason)
  await ctx.send(
      f"👢 Пользователь **{member.mention}** изгнан с сервера. Причина:"
      f" `{reason}`"
  )


@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_member(
    ctx, member: discord.Member, minutes: int, *, reason: str = "Без причины"
):
  import datetime

  duration = datetime.timedelta(minutes=minutes)
  await member.timeout(duration, reason=reason)
  await ctx.send(
      f"🔇 Пользователь **{member.mention}** получил мут на {minutes} мин."
      f" Причина: `{reason}`"
  )


@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_member(ctx, member: discord.Member):
  await member.timeout(None)
  await ctx.send(f"🔊 С пользователя **{member.mention}** снят мут.")


@bot.command(name="clear_chat")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int = 10):
  await ctx.channel.purge(limit=amount + 1)
  msg = await ctx.send(f"🧹 Удалено сообщений: {amount}")
  import asyncio

  await asyncio.sleep(3)
  await msg.delete()


# ==========================================
# КОМАНДЫ ДЛЯ ОБЫЧНЫХ УЧАСТНИКОВ
# ==========================================


@bot.command(name="ping")
async def ping(ctx):
  latency = round(bot.latency * 1000)
  await ctx.send(f"pong! 🏓 Задержка: **{latency}мс**")


@bot.command(name="roll")
async def roll_dice(ctx):
  import random

  result = random.randint(1, 100)
  await ctx.send(
      f"🎲 **{ctx.author.name}** бросил кубик и выпало число: **{result}** (из"
      " 100)"
  )


@bot.command(name="avatar")
async def get_avatar(ctx, member: discord.Member = None):
  if member is None:
    member = ctx.author
  embed = discord.Embed(title=f"Аватар пользователя {member.name}")
  embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
  await ctx.send(embed=embed)


# Обработка ошибок прав доступа
@bot.event
async def on_command_error(ctx, error):
  if isinstance(
      error, (commands.MissingPermissions, commands.CheckFailure)
  ):
    await ctx.send(
        "❌ У вас **нет прав** на использование этой команды!", delete_after=5
    )
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send(
        "❌ Вы забыли указать обязательный аргумент (например, пользователя)!",
        delete_after=5,
    )


import os

bot.run(os.getenv("DISCORD_TOKEN"))
