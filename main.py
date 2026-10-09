import asyncio
import datetime
import os
import random
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

USER_WARNINGS = {}
USER_ECONOMY = {}


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успешно запущен и готов к работе!")


# ==========================================
# 1. АВТО-ПРИВЕТСТВИЕ И АВТО-РОЛЬ
# ==========================================
@bot.event
async def on_member_join(member: discord.Member):
  # Выдача роли
  role = discord.utils.get(member.guild.roles, name="👤 ┃ Участник")
  if role:
    try:
      await member.add_roles(role)
    except Exception as e:
      print(f"Не удалось выдать авто-роль: {e}")

  # Отправка приветствия в общий чат
  channel = discord.utils.get(member.guild.text_channels, name="💬・общий-чат")
  if channel:
    embed = discord.Embed(
        title="👋 Добро пожаловать!",
        description=(
            f"Приветствуем тебя на сервере, {member.mention}!\n"
            "Не забудь ознакомиться с правилами в канале <#📜・правила-чата>."
        ),
        color=discord.Color.green(),
    )
    embed.set_thumbnail(
        url=member.avatar.url if member.avatar else member.default_avatar.url
    )
    await channel.send(embed=embed)


# ==========================================
# 2. ДИНАМИЧЕСКИЕ ГОЛОСОВЫЕ КАНАЛЫ
# ==========================================
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
  # Вход в канал-триггер "➕ ┃ Создать комнатку"
  if (
      after.channel
      and after.channel.name == "➕ ┃ Создать комнатку"
  ):
    category = after.channel.category
    new_channel = await member.guild.create_voice_channel(
        name=f"🔊 Комната {member.display_name}", category=category
    )
    await member.move_to(new_channel)

  # Удаление пустой авто-созданной комнаты
  if before.channel and before.channel.name.startswith("🔊 Комната "):
    if len(before.channel.members) == 0:
      await before.channel.delete()


# ==========================================
# 3. СИСТЕМА ТИКЕТОВ (ПОДДЕРЖКА)
# ==========================================
class CloseTicketView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Закрыть тикет", style=discord.ButtonStyle.danger, emoji="🔒"
  )
  async def close_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        "⏳ Тикет будет удален через 5 секунд..."
    )
    await asyncio.sleep(5)
    await interaction.channel.delete()


class TicketCreateView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Открыть тикет", style=discord.ButtonStyle.success, emoji="📩"
  )
  async def create_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    guild = interaction.guild
    user = interaction.user

    # Ищем или создаем категорию для тикетов
    category = discord.utils.get(guild.categories, name="🎫 ┃ ТИКЕТЫ И ПОДДЕРЖКА")
    if not category:
      category = await guild.create_category("🎫 ┃ ТИКЕТЫ И ПОДДЕРЖКА")

    # Настройка прав для канала тикета
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        ),
    }

    # Даем доступ админам/модераторам
    for role_name in ["👑 ┃ Создатель", "🛡️ ┃ Главный Администратор", "🔨 ┃ Модератор"]:
      mod_role = discord.utils.get(guild.roles, name=role_name)
      if mod_role:
        overwrites[mod_role] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        )

    channel_name = f"ticket-{user.name}".lower().replace(" ", "-")
    existing_channel = discord.utils.get(guild.channels, name=channel_name)
    if existing_channel:
      await interaction.response.send_message(
          f"❌ У вас уже открыт тикет: {existing_channel.mention}",
          ephemeral=True,
      )
      return

    ticket_channel = await guild.create_text_channel(
        name=channel_name, category=category, overwrites=overwrites
    )

    embed = discord.Embed(
        title=f"🎫 Тикет пользователя {user.name}",
        description=(
            "Опишите вашу проблему или вопрос. Администрация ответит вам в"
            " ближайшее время!"
        ),
        color=discord.Color.blue(),
    )
    await ticket_channel.send(
        content=f"{user.mention}", embed=embed, view=CloseTicketView()
    )
    await interaction.response.send_message(
        f"✅ Ваш тикет создан: {ticket_channel.mention}", ephemeral=True
    )


@bot.command(name="ticket_panel")
@commands.has_permissions(administrator=True)
async def ticket_panel(ctx):
  await ctx.message.delete()
  embed = discord.Embed(
      title="📩 Поддержка и Обратная Связь",
      description=(
          "Нажмите на кнопку ниже, чтобы создать приватный тикет для связи с"
          " администрацией."
      ),
      color=discord.Color.purple(),
  )
  await ctx.send(embed=embed, view=TicketCreateView())


# ==========================================
# 4. АВТО-РОЛИ ПО КНОПКАМ (BUTTON ROLES)
# ==========================================
class SelfRolesView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  async def toggle_role(
      self, interaction: discord.Interaction, role_name: str
  ):
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
      await interaction.response.send_message(
          f"❌ Роль `{role_name}` не найдена на сервере!", ephemeral=True
      )
      return

    if role in interaction.user.roles:
      await interaction.user.remove_roles(role)
      await interaction.response.send_message(
          f"➖ Роль **{role.name}** успешно снята!", ephemeral=True
      )
    else:
      await interaction.user.add_roles(role)
      await interaction.response.send_message(
          f"➕ Роль **{role.name}** успешно выдана!", ephemeral=True
      )

  @discord.ui.button(
      label="Геймер", style=discord.ButtonStyle.primary, emoji="🎮"
  )
  async def gamer_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.toggle_role(interaction, "🎉 ┃ Ивентер")

  @discord.ui.button(
      label="VIP Участник", style=discord.ButtonStyle.secondary, emoji="🔮"
  )
  async def vip_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.toggle_role(interaction, "⭐ ┃ VIP Участник")

  @discord.ui.button(
      label="Уведомления", style=discord.ButtonStyle.success, emoji="📢"
  )
  async def notify_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.toggle_role(interaction, "💬 ┃ Активный участник")


@bot.command(name="roles_panel")
@commands.has_permissions(administrator=True)
async def roles_panel(ctx):
  await ctx.message.delete()
  embed = discord.Embed(
      title="🎭 Выбор Ролей",
      description=(
          "Нажимайте на кнопки ниже, чтобы получить или снять интересующие вас"
          " роли!"
      ),
      color=discord.Color.gold(),
  )
  await ctx.send(embed=embed, view=SelfRolesView())


# ==========================================
# ПРОВЕРКА НА СОЗДАТЕЛЯ И АДМИН-ПАНЕЛЬ
# ==========================================
def is_server_owner():

  async def predicate(ctx):
    if ctx.author != ctx.guild.owner:
      raise commands.CheckFailure(
          "Эту команду может использовать только создатель сервера!"
      )
    return True

  return commands.check(predicate)


class ModModal(discord.ui.Modal):

  def __init__(self, action_type: str, mute_duration: int = 10):
    title_map = {
        "ban": "Бан участника",
        "kick": "Кик участника",
        "mute": f"Мут на {mute_duration} мин.",
    }
    super().__init__(title=title_map.get(action_type, "Модерация"))
    self.action_type = action_type
    self.mute_duration = mute_duration

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
      member_id = int(self.target_id.value.strip("<@!>"))
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
        self.reason.value if self.reason.value else "Причина не указана"
    )

    if self.action_type == "ban":
      await member.ban(reason=reason_text)
      await interaction.response.send_message(
          f"🔨 Администратор {interaction.user.mention} заблокировал"
          f" **{member}**. Причина: `{reason_text}`"
      )
    elif self.action_type == "kick":
      await member.kick(reason=reason_text)
      await interaction.response.send_message(
          f"👢 Администратор {interaction.user.mention} выгнал **{member}**."
          f" Причина: `{reason_text}`"
      )
    elif self.action_type == "mute":
      duration = datetime.timedelta(minutes=self.mute_duration)
      await member.timeout(duration, reason=reason_text)
      await interaction.response.send_message(
          f"🔇 Администратор {interaction.user.mention} выдал мут **{member}** на"
          f" {self.mute_duration} мин. Причина: `{reason_text}`"
      )


class MuteSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label="5 минут", description="Быстрый мут на 5 минут", emoji="⏱️"
        ),
        discord.SelectOption(
            label="15 минут", description="Мут на 15 минут", emoji="⏳"
        ),
        discord.SelectOption(
            label="1 час", description="Мут на 1 час", emoji="⏰"
        ),
        discord.SelectOption(
            label="1 день", description="Серьёзный мут на 24 часа", emoji="📅"
        ),
        discord.SelectOption(
            label="1 неделя", description="Максимальный мут на 7 дней", emoji="🛑"
        ),
    ]
    super().__init__(
        placeholder="📌 Выберите время для мута...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    mapping = {
        "5 минут": 5,
        "15 минут": 15,
        "1 час": 60,
        "1 день": 1440,
        "1 неделя": 10080,
    }
    selected_time = mapping.get(self.values[0], 10)
    await interaction.response.send_modal(
        ModModal("mute", mute_duration=selected_time)
    )


class MuteView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=60)
    self.add_item(MuteSelect())


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
      label="Мут...", style=discord.ButtonStyle.primary, emoji="🔇"
  )
  async def mute_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.moderate_members:
      await interaction.response.send_message(
          "❌ У вас нет прав на выдачу мутов!", ephemeral=True
      )
      return
    await interaction.response.send_message(
        "Выберите время для тайм-аута участника:",
        view=MuteView(),
        ephemeral=True,
    )


@bot.command(name="admin")
@commands.has_permissions(administrator=True)
async def admin_panel(ctx):
  embed = discord.Embed(
      title="🛡️ Панель Администратора",
      description=(
          "Используйте кнопки ниже для быстрого применения наказаний к"
          " нарушителям."
      ),
      color=discord.Color.gold(),
  )
  embed.set_footer(text=f"Вызвана пользователем: {ctx.author.name}")
  await ctx.send(embed=embed, view=AdminPanelView())


# ==========================================
# МЕНЮ ПОМОЩИ (!help)
# ==========================================
@bot.command(name="help")
async def custom_help(ctx):
  embed = discord.Embed(
      title="📜 Меню помощи и навигация по боту",
      description="Список всех доступных категорий и команд бота:",
      color=discord.Color.blue(),
  )

  embed.add_field(
      name="👑 Команды создателя",
      value="`!setup` / `!clear` — Авто-настройка и очистка сервера",
      inline=False,
  )

  embed.add_field(
      name="🛡️ Модерация и администрирование",
      value=(
          "`!admin` — Панель модерации\n`!ticket_panel` — Панель"
          " тикетов\n`!roles_panel` — Панель выдачи ролей\n`!ban / !unban /"
          " !kick / !mute` — Наказания\n`!warn / !warnings / !clear_warnings` —"
          " Варны\n`!clear_chat / !lock / !unlock / !slowmode` — Чат"
      ),
      inline=False,
  )

  embed.add_field(
      name="🎉 Экономика и Развлечения",
      value=(
          "`!balance` / `!daily` / `!work` / `!slot` — Экономика\n`!poll` —"
          " Голосование\n`!ping / !roll / !coinflip / !avatar / !userinfo /"
          " !serverinfo` — Разное"
      ),
      inline=False,
  )

  embed.set_footer(text="Discord Bot • Все права защищены")
  await ctx.send(embed=embed)


# ==========================================
# ОЧИСТКА И НАСТРОЙКА СЕРВЕРА (!clear)
# ==========================================
@bot.command(name="clear")
@is_server_owner()
async def clear_server(ctx):
  guild = ctx.guild
  await ctx.send("⚠️ Начинаю очистку сервера и пересоздание структуры...")

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
          "name": "🔨 ┃ Модератор",
          "color": discord.Color.from_rgb(0, 200, 255),
          "permissions": discord.Permissions(
              kick_members=True, ban_members=True, manage_messages=True
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
          "name": "⭐ ┃ VIP Участник",
          "color": discord.Color.from_rgb(170, 0, 255),
          "permissions": discord.Permissions.none(),
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

  cat_chat = await guild.create_category("💬 ┃ КОМЬЮНИТИ")
  await guild.create_text_channel(
      "💬・общий-чат", category=cat_chat, overwrites=overwrites_general
  )
  await guild.create_text_channel(
      "🤖・команды-ботов", category=cat_chat, overwrites=overwrites_general
  )

  cat_voice = await guild.create_category("🔊 ┃ ГОЛОСОВЫЕ КОМНАТЫ")
  await guild.create_voice_channel("🔊 ┃ Главный Лобби", category=cat_voice)
  await guild.create_voice_channel(
      "➕ ┃ Создасть комнатку", category=cat_voice
  )  # Динамический канал

  await news_channel.send(
      "✅ **Сервер успешно настроен!** Сообщение об успешной очистке."
  )


@bot.command(name="setup")
@is_server_owner()
async def setup_server(ctx):
  await ctx.invoke(bot.get_command("clear"))


# ==========================================
# МОДЕРАЦИЯ И ЭКОНОМИКА
# ==========================================
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_member(
    ctx, member: discord.Member, *, reason: str = "Причина не указана"
):
  await member.ban(reason=reason)
  await ctx.send(f"🔨 Пользователь **{member.mention}** заблокирован.")


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_member(
    ctx, member: discord.Member, *, reason: str = "Причина не указана"
):
  await member.kick(reason=reason)
  await ctx.send(f"👢 Пользователь **{member.mention}** изгнан.")


@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_member(
    ctx, member: discord.Member, minutes: int, *, reason: str = "Без причины"
):
  duration = datetime.timedelta(minutes=minutes)
  await member.timeout(duration, reason=reason)
  await ctx.send(
      f"🔇 Пользователь **{member.mention}** получил мут на {minutes} мин."
  )


@bot.command(name="clear_chat")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int = 10):
  await ctx.channel.purge(limit=amount + 1)
  msg = await ctx.send(f"🧹 Удалено сообщений: {amount}")
  await asyncio.sleep(3)
  await msg.delete()


@bot.command(name="balance")
async def balance(ctx, member: discord.Member = None):
  if member is None:
    member = ctx.author
  bal = USER_ECONOMY.get(member.id, 0)
  await ctx.send(
      f"💰 Баланс пользователя **{member.display_name}**: **{bal}** 🪙"
  )


@bot.command(name="daily")
async def daily_bonus(ctx):
  user_id = ctx.author.id
  current_bal = USER_ECONOMY.get(user_id, 0)
  USER_ECONOMY[user_id] = current_bal + 500
  await ctx.send(f"🎁 {ctx.author.mention}, вы получили бонус **500** 🪙!")


@bot.command(name="work")
async def work(ctx):
  user_id = ctx.author.id
  earned = random.randint(50, 250)
  USER_ECONOMY[user_id] = USER_ECONOMY.get(user_id, 0) + earned
  await ctx.send(
      f"💼 {ctx.author.mention}, вы отлично поработали и заработали **{earned}**"
      " 🪙!"
  )


@bot.command(name="ping")
async def ping(ctx):
  await ctx.send(f"pong! 🏓 Задержка: **{round(bot.latency * 1000)}мс**")


bot.run(os.getenv("DISCORD_TOKEN"))
