import asyncio
import datetime
import random
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успешно запущен и готов к работе!")


# ==========================================
# ПРОВЕРКА НА СОЗДАТЕЛЯ СЕРВЕРА
# ==========================================
def is_server_owner():

  async def predicate(ctx):
    if ctx.author != ctx.guild.owner:
      raise commands.CheckFailure(
          "Эту команду может использовать только создатель сервера!"
      )
    return True

  return commands.check(predicate)


# ==========================================
# ИНТЕРАКТИВНАЯ АДМИН-ПАНЕЛЬ (МОДАЛКИ И КНОПКИ)
# ==========================================


class ModModal(discord.ui.Modal):

  def __init__(self, action_type: str):
    super().__init__(title=f"Управление: {action_type.upper()}")
    self.action_type = action_type

    self.target_id = discord.ui.TextInput(
        label="ID или Упоминание (например: 12345678)",
        placeholder="Введите ID пользователя...",
        required=True,
    )
    self.reason = discord.ui.TextInput(
        label="Причина",
        placeholder="Укажите причину наказания...",
        required=False,
        style=discord.TextStyle.long,
    )

    self.add_item(self.target_id)
    self.add_item(self.reason)

  async def on_submit(self, interaction: discord.Interaction):
    try:
      member_id = int(
          self.target_id.value.strip("<@!>")
      )  # Очищаем от лишних символов упоминания
      member = interaction.guild.get_member(member_id)
      if not member:
        await interaction.response.send_message(
            "❌ Пользователь не найден на этом сервере!", ephemeral=True
        )
        return
    except ValueError:
      await interaction.response.send_message(
          "❌ Неверный формат ID пользователя!", ephemeral=True
      )
      return

    reason_text = (
        self.reason.value
        if self.reason.value
        else "Причина не указана"
    )

    if self.action_type == "ban":
      await member.ban(reason=reason_text)
      await interaction.response.send_message(
          f"🔨 Администратор {interaction.user.mention} заблокировал"
          f" **{member}**. Причина: `{reason_text}`",
          ephemeral=False,
      )
    elif self.action_type == "kick":
      await member.kick(reason=reason_text)
      await interaction.response.send_message(
          f"👢 Администратор {interaction.user.mention} выгнал **{member}**."
          f" Причина: `{reason_text}`",
          ephemeral=False,
      )
    elif self.action_type == "mute":
      duration = datetime.timedelta(minutes=10)  # По умолчанию мут на 10 минут
      await member.timeout(duration, reason=reason_text)
      await interaction.response.send_message(
          f"🔇 Администратор {interaction.user.mention} выдал мут **{member}** на"
          f" 10 мин. Причина: `{reason_text}`",
          ephemeral=False,
      )


class AdminPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Бан", style=discord.ButtonStyle.danger, emoji="🔨"
  )
  async def ban_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.ban_members:
      await interaction.response.send_message(
          "❌ У вас нет прав на бан участников!", ephemeral=True
      )
      return
    await interaction.response.send_modal(ModModal("ban"))

  @discord.ui.button(
      label="Кик", style=discord.ButtonStyle.secondary, emoji="👢"
  )
  async def kick_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.kick_members:
      await interaction.response.send_message(
          "❌ У вас нет прав на кик участников!", ephemeral=True
      )
      return
    await interaction.response.send_modal(ModModal("kick"))

  @discord.ui.button(
      label="Мут (10 мин)", style=discord.ButtonStyle.primary, emoji="🔇"
  )
  async def mute_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.moderate_members:
      await interaction.response.send_message(
          "❌ У вас нет прав на выдачу мутов!", ephemeral=True
      )
      return
    await interaction.response.send_modal(ModModal("mute"))


@bot.command(name="admin")
@commands.has_permissions(administrator=True)
async def admin_panel(ctx):
  embed = discord.Embed(
      title="🛡️ Панель Администратора",
      description=(
          "Используйте кнопки ниже для быстрого применения наказаний к"
          " нарушителям.\n\n*При нажатии откроется форма для ввода ID и"
          " причины.*"
      ),
      color=discord.Color.gold(),
  )
  embed.set_footer(text=f"Вызвана пользователем: {ctx.author.name}")
  await ctx.send(embed=embed, view=AdminPanelView())

# ==========================================
# КРАСИВОЕ МЕНЮ ПОМОЩИ (!help)
# ==========================================

bot.remove_command("help")


@bot.command(name="help")
async def custom_help(ctx):
  embed = discord.Embed(
      title="📜 Меню помощи и навигация по боту",
      description="Ниже представлен список всех доступных команд:",
      color=discord.Color.blue(),
  )

  embed.add_field(
      name="👑 Команды создателя (Только Владелец)",
      value=(
          "`!setup` — Автоматическая настройка сервера\n`!clear` — Полная"
          " очистка каналов и создание структуры"
      ),
      inline=False,
  )

  embed.add_field(
      name="🛡️ Команды модерации (Админы / Модеры)",
      value=(
          "`!admin` — Открыть интерактивную админ-панель\n`!ban @участник"
          " [причина]` — Заблокировать\n`!kick @участник [причина]` —"
          " Изгнать\n`!mute @участник [минуты] [причина]` — Выдать тайм-аут\n`!unmute"
          " @участник` — Снять мут\n`!clear_chat [кол-во]` — Очистить чат"
      ),
      inline=False,
  )

  embed.add_field(
      name="👤 Общие команды (Для всех)",
      value=(
          "`!ping` — Проверить задержку бота\n`!roll` — Бросить игральный кубик"
          " (1-100)\n`!avatar [@участник]` — Посмотреть аватар"
      ),
      inline=False,
  )

  embed.set_footer(text="Бот автоматизации сервера • Сделано с любовью")
  await ctx.send(embed=embed)


# ==========================================
# КОМАНДЫ СОЗДАТЕЛЯ (SETUP / CLEAR)
# ==========================================


@bot.command(name="clear")
@is_server_owner()
async def clear_server(ctx):
  guild = ctx.guild
  await ctx.send(
      "⚠️ **Внимание!** Начинаю полное очищение сервера: удаляю все каналы и"
      " категории..."
  )

  for channel in guild.channels:
    try:
      await channel.delete()
    except Exception as e:
      print(f"Не удалось удалить канал {channel.name}: {e}")

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

  everyone_role = guild.default_role
  overwrites_info = {
      everyone_role: discord.PermissionOverwrite(
          read_messages=True, send_messages=False
      )
  }
  overwrites_general = {
      everyone_role: discord.PermissionOverwrite(read_messages=True)
  }

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

  cat_voice = await guild.create_category("🔊 ┃ ГОЛОСОВЫЕ КОМНАТЫ")
  await guild.create_voice_channel("🔊 ┃ Главный Лобби", category=cat_voice)
  await guild.create_voice_channel("🎮 ┃ Дуо / Трио (1)", category=cat_voice)
  await guild.create_voice_channel("🎮 ┃ Дуо / Трио (2)", category=cat_voice)
  await guild.create_voice_channel("👥 ┃ Сквад / Команда", category=cat_voice)
  await guild.create_voice_channel("🎧 ┃ Чилаут и Музыка", category=cat_voice)
  await guild.create_voice_channel("🌙 ┃ Уединение", category=cat_voice)
  await guild.create_voice_channel("💤 ┃ AFK Зона", category=cat_voice)

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
# КЛАССИЧЕСКИЕ КОМАНДЫ МОДЕРАЦИИ
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
  await asyncio.sleep(3)
  await msg.delete()


# ==========================================
# ОБЩИЕ КОМАНДЫ
# ==========================================


@bot.command(name="ping")
async def ping(ctx):
  latency = round(bot.latency * 1000)
  await ctx.send(f"pong! 🏓 Задержка: **{latency}мс**")


@bot.command(name="roll")
async def roll_dice(ctx):
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
  embed.set_image(
      url=member.avatar.url if member.avatar else member.default_avatar.url
  )
  await ctx.send(embed=embed)


# Обработка ошибок
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
        "❌ Вы забыли указать обязательный аргумент!", delete_after=5
    )


import os

bot.run(os.getenv("DISCORD_TOKEN"))
