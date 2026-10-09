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
VOICE_OWNERS = {}  # {channel_id: owner_id} для приватных войсов


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успешно запущен и готов к работе!")


# ==========================================
# 1. АВТО-ПРИВЕТСТВИЕ И АВТО-РОЛЬ
# ==========================================
@bot.event
async def on_member_join(member: discord.Member):
  role = discord.utils.get(member.guild.roles, name="👤 ┃ Участник")
  if role:
    try:
      await member.add_roles(role)
    except Exception as e:
      print(f"Не удалось выдать авто-роль: {e}")

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
# 2. ПРИВАТНЫЕ ГОЛОСОВЫЕ КОМНАТЫ И НАСТРОЙКИ
# ==========================================


class RenameVoiceModal(discord.ui.Modal):

  def __init__(self, voice_channel: discord.VoiceChannel):
    super().__init__(title="Смена названия комнаты")
    self.voice_channel = voice_channel
    self.new_name = discord.ui.TextInput(
        label="Новое название канала",
        placeholder="Введите название...",
        max_length=100,
        required=True,
    )
    self.add_item(self.new_name)

  async def on_submit(self, interaction: discord.Interaction):
    await self.voice_channel.edit(name=self.new_name.value)
    await interaction.response.send_message(
        f"✅ Название комнаты изменено на: **{self.new_name.value}**",
        ephemeral=True,
    )


class LimitVoiceModal(discord.ui.Modal):

  def __init__(self, voice_channel: discord.VoiceChannel):
    super().__init__(title="Установка лимита участников")
    self.voice_channel = voice_channel
    self.limit = discord.ui.TextInput(
        label="Лимит человек (0 = без лимита)",
        placeholder="Например: 5",
        max_length=2,
        required=True,
    )
    self.add_item(self.limit)

  async def on_submit(self, interaction: discord.Interaction):
    try:
      val = int(self.limit.value)
      if 0 <= val <= 99:
        await self.voice_channel.edit(user_limit=val)
        await interaction.response.send_message(
            f"👥 Лимит участников установлен на: **{val}**", ephemeral=True
        )
      else:
        await interaction.response.send_message(
            "❌ Лимит должен быть от 0 до 99!", ephemeral=True
        )
    except ValueError:
      await interaction.response.send_message(
          "❌ Введите корректное число!", ephemeral=True
      )


class AccessVoiceModal(discord.ui.Modal):

  def __init__(
      self, voice_channel: discord.VoiceChannel, allow_access: bool = True
  ):
    action_str = "разрешить" if allow_access else "запретить"
    super().__init__(title=f"Кому {action_str} доступ")
    self.voice_channel = voice_channel
    self.allow_access = allow_access
    self.target_input = discord.ui.TextInput(
        label="ID пользователя или Упоминание",
        placeholder="Например: 123456789...",
        required=True,
    )
    self.add_item(self.target_input)

  async def on_submit(self, interaction: discord.Interaction):
    try:
      user_id = int(self.target_input.value.strip("<@!>"))
      member = interaction.guild.get_member(user_id)
      if not member:
        await interaction.response.send_message(
            "❌ Участник не найден!", ephemeral=True
        )
        return

      if self.allow_access:
        await self.voice_channel.set_permissions(member, connect=True)
        await interaction.response.send_message(
            f"✅ Доступ для {member.mention} **разрешен**!", ephemeral=True
        )
      else:
        await self.voice_channel.set_permissions(member, connect=False)
        if member in self.voice_channel.members:
          await member.move_to(None)
        await interaction.response.send_message(
            f"🚫 Доступ для {member.mention} **заблокирован**!", ephemeral=True
        )
    except ValueError:
      await interaction.response.send_message(
          "❌ Введите корректный ID!", ephemeral=True
      )


class VoiceControlView(discord.ui.View):

  def __init__(self, voice_channel: discord.VoiceChannel, owner_id: int):
    super().__init__(timeout=None)
    self.voice_channel = voice_channel
    self.owner_id = owner_id

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if (
        interaction.user.id != self.owner_id
        and not interaction.user.guild_permissions.administrator
    ):
      await interaction.response.send_message(
          "❌ Вы не являетесь владельцем этой комнаты!", ephemeral=True
      )
      return False
    return True

  @discord.ui.button(
      label="Название", style=discord.ButtonStyle.primary, emoji="✏️"
  )
  async def rename_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(
        RenameVoiceModal(self.voice_channel)
    )

  @discord.ui.button(
      label="Лимит", style=discord.ButtonStyle.primary, emoji="👥"
  )
  async def limit_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(LimitVoiceModal(self.voice_channel))

  @discord.ui.button(
      label="Закрыть / Открыть",
      style=discord.ButtonStyle.secondary,
      emoji="🔒",
  )
  async def lock_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    everyone = interaction.guild.default_role
    current_perm = self.voice_channel.overwrites_for(everyone).connect
    if current_perm is False:
      await self.voice_channel.set_permissions(everyone, connect=None)
      await interaction.response.send_message(
          "🔓 Комната открыта для всех!", ephemeral=True
      )
    else:
      await self.voice_channel.set_permissions(everyone, connect=False)
      await interaction.response.send_message(
          "🔒 Комната закрыта от посторонних!", ephemeral=True
      )

  @discord.ui.button(
      label="Скрыть / Показать",
      style=discord.ButtonStyle.secondary,
      emoji="👁️",
  )
  async def hide_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    everyone = interaction.guild.default_role
    current_perm = self.voice_channel.overwrites_for(everyone).read_messages
    if current_perm is False:
      await self.voice_channel.set_permissions(everyone, read_messages=None)
      await interaction.response.send_message(
          "👁️ Комната теперь видима всем!", ephemeral=True
      )
    else:
      await self.voice_channel.set_permissions(everyone, read_messages=False)
      await interaction.response.send_message(
          "🙈 Комната скрыта от остальных!", ephemeral=True
      )

  @discord.ui.button(
      label="Разрешить", style=discord.ButtonStyle.success, emoji="➕"
  )
  async def allow_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(
        AccessVoiceModal(self.voice_channel, allow_access=True)
    )

  @discord.ui.button(
      label="Запретить", style=discord.ButtonStyle.danger, emoji="➖"
  )
  async def deny_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(
        AccessVoiceModal(self.voice_channel, allow_access=False)
    )


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
  if after.channel and after.channel.name == "➕ ┃ Создать комнатку":
    category = after.channel.category
    new_channel = await member.guild.create_voice_channel(
        name=f"🔊 Комната {member.display_name}", category=category
    )
    VOICE_OWNERS[new_channel.id] = member.id
    await member.move_to(new_channel)

    embed = discord.Embed(
        title="🎛️ Управление вашей приватной комнатой",
        description="Используйте кнопки ниже для настройки:",
        color=discord.Color.blue(),
    )
    try:
      await member.send(
          embed=embed, view=VoiceControlView(new_channel, member.id)
      )
    except:
      pass

  if before.channel and before.channel.id in VOICE_OWNERS:
    if len(before.channel.members) == 0:
      del VOICE_OWNERS[before.channel.id]
      try:
        await before.channel.delete()
      except Exception:
        pass


@bot.command(name="setup_voice")
@commands.has_permissions(administrator=True)
async def setup_voice(ctx):
  guild = ctx.guild
  category = discord.utils.get(guild.categories, name="🔊 ┃ ПРИВАТНЫЕ КОМНАТЫ")
  if not category:
    category = await guild.create_category("🔊 ┃ ПРИВАТНЫЕ КОМНАТЫ")

  existing = discord.utils.get(
      category.voice_channels, name="➕ ┃ Создать комнатку"
  )
  if not existing:
    await guild.create_voice_channel(
        name="➕ ┃ Создать комнатку", category=category
    )
    await ctx.send("✅ Система приватных голосовых комнат успешно установлена!")
  else:
    await ctx.send("ℹ️ Триггерный канал уже существует!")


@bot.command(name="vpanel")
async def voice_panel(ctx):
  if not ctx.author.voice or not ctx.author.voice.channel:
    await ctx.send("❌ Вы должны находиться в своей голосовой комнате!")
    return
  channel = ctx.author.voice.channel
  owner_id = VOICE_OWNERS.get(channel.id)
  if not owner_id or (
      owner_id != ctx.author.id and not ctx.author.guild_permissions.administrator
  ):
    await ctx.send("❌ Вы не владелец этой комнаты!")
    return
  embed = discord.Embed(
      title=f"🎛️ Управление — {channel.name}", color=discord.Color.blue()
  )
  await ctx.send(embed=embed, view=VoiceControlView(channel, owner_id))


# ==========================================
# 3. СИСТЕМА ТИКЕТОВ И АВТО-РОЛИ ПО КНОПКАМ
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
    category = discord.utils.get(guild.categories, name="🎫 ┃ ТИКЕТЫ И ПОДДЕРЖКА")
    if not category:
      category = await guild.create_category("🎫 ┃ ТИКЕТЫ И ПОДДЕРЖКА")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        ),
    }

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
        description="Опишите вашу проблему. Администрация скоро ответит!",
        color=discord.Color.blue(),
    )
    await ticket_channel.send(
        content=f"{user.mention}", embed=embed, view=CloseTicketView()
    )
    await interaction.response.send_message(
        f"✅ Тикет создан: {ticket_channel.mention}", ephemeral=True
    )


@bot.command(name="ticket_panel")
@commands.has_permissions(administrator=True)
async def ticket_panel(ctx):
  await ctx.message.delete()
  embed = discord.Embed(
      title="📩 Поддержка и Обратная Связь",
      description="Нажмите на кнопку ниже, чтобы открыть тикет.",
      color=discord.Color.purple(),
  )
  await ctx.send(embed=embed, view=TicketCreateView())


class SelfRolesView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  async def toggle_role(
      self, interaction: discord.Interaction, role_name: str
  ):
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
      await interaction.response.send_message(
          f"❌ Роль `{role_name}` не найдена!", ephemeral=True
      )
      return
    if role in interaction.user.roles:
      await interaction.user.remove_roles(role)
      await interaction.response.send_message(
          f"➖ Роль **{role.name}** снята!", ephemeral=True
      )
    else:
      await interaction.user.add_roles(role)
      await interaction.response.send_message(
          f"➕ Роль **{role.name}** выдана!", ephemeral=True
      )

  @discord.ui.button(
      label="Ивентер", style=discord.ButtonStyle.primary, emoji="🎉"
  )
  async def r1(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.toggle_role(interaction, "🎉 ┃ Ивентер")

  @discord.ui.button(
      label="VIP", style=discord.ButtonStyle.secondary, emoji="⭐"
  )
  async def r2(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.toggle_role(interaction, "⭐ ┃ VIP Участник")


@bot.command(name="roles_panel")
@commands.has_permissions(administrator=True)
async def roles_panel(ctx):
  await ctx.message.delete()
  embed = discord.Embed(
      title="🎭 Выбор Ролей",
      description="Нажмите кнопку, чтобы получить роль.",
      color=discord.Color.gold(),
  )
  await ctx.send(embed=embed, view=SelfRolesView())


# ==========================================
# 4. АДМИН-ПАНЕЛЬ И МОДЕРАЦИЯ С ВЫБОРОМ МУТА
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
        label="ID пользователя", placeholder="Введите ID...", required=True
    )
    self.reason = discord.ui.TextInput(
        label="Причина", placeholder="Причина...", required=False
    )
    self.add_item(self.target_id)
    self.add_item(self.reason)

  async def on_submit(self, interaction: discord.Interaction):
    try:
      member = interaction.guild.get_member(
          int(self.target_id.value.strip("<@!>"))
      )
      if not member:
        return await interaction.response.send_message(
            "❌ Пользователь не найден!", ephemeral=True
        )
    except ValueError:
      return await interaction.response.send_message(
          "❌ Неверный ID!", ephemeral=True
      )

    reason = self.reason.value if self.reason.value else "Не указана"
    if self.action_type == "ban":
      await member.ban(reason=reason)
      await interaction.response.send_message(
          f"🔨 Заблокирован **{member}**. Причина: `{reason}`"
      )
    elif self.action_type == "kick":
      await member.kick(reason=reason)
      await interaction.response.send_message(
          f"👢 Изгнан **{member}**. Причина: `{reason}`"
      )
    elif self.action_type == "mute":
      await member.timeout(
          datetime.timedelta(minutes=self.mute_duration), reason=reason
      )
      await interaction.response.send_message(
          f"🔇 Мут **{member}** на {self.mute_duration} мин. Причина:"
          f" `{reason}`"
      )


class MuteSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(label="5 минут", value="5", emoji="⏱️"),
        discord.SelectOption(label="15 минут", value="15", emoji="⏳"),
        discord.SelectOption(label="1 час", value="60", emoji="⏰"),
        discord.SelectOption(label="1 день", value="1440", emoji="📅"),
        discord.SelectOption(label="1 неделя", value="10080", emoji="🛑"),
    ]
    super().__init__(
        placeholder="📌 Выберите время мута...", options=options
    )

  async def callback(self, interaction: discord.Interaction):
    duration = int(self.values[0])
    await interaction.response.send_modal(
        ModModal("mute", mute_duration=duration)
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
  async def b(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_modal(ModModal("ban"))

  @discord.ui.button(
      label="Кик", style=discord.ButtonStyle.secondary, emoji="👢"
  )
  async def k(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_modal(ModModal("kick"))

  @discord.ui.button(
      label="Мут...", style=discord.ButtonStyle.primary, emoji="🔇"
  )
  async def m(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_message(
        "Выберите время для мута:", view=MuteView(), ephemeral=True
    )


@bot.command(name="admin")
@commands.has_permissions(administrator=True)
async def admin_panel(ctx):
  embed = discord.Embed(
      title="🛡️ Панель Администратора",
      description="Используйте кнопки для быстрого наказания нарушителей.",
      color=discord.Color.gold(),
  )
  await ctx.send(embed=embed, view=AdminPanelView())


# ==========================================
# 5. СБРОС И ОЧИСТКА СЕРВЕРА (!clear / !setup)
# ==========================================


@bot.command(name="clear")
@is_server_owner()
async def clear_server(ctx):
  guild = ctx.guild
  await ctx.send("⚠️ Начинаю полное очищение и настройку сервера...")
  for channel in guild.channels:
    try:
      await channel.delete()
    except Exception:
      pass

  roles_data = [
      {
          "name": "👑 ┃ Создатель",
          "color": discord.Color.red(),
          "permissions": discord.Permissions(administrator=True),
          "hoist": True,
      },
      {
          "name": "🛡️ ┃ Главный Администратор",
          "color": discord.Color.orange(),
          "permissions": discord.Permissions(administrator=True),
          "hoist": True,
      },
      {
          "name": "🔨 ┃ Модератор",
          "color": discord.Color.blue(),
          "permissions": discord.Permissions(
              kick_members=True, ban_members=True, manage_messages=True
          ),
          "hoist": True,
      },
      {
          "name": "🎉 ┃ Ивентер",
          "color": discord.Color.magenta(),
          "permissions": discord.Permissions(manage_events=True),
          "hoist": True,
      },
      {
          "name": "⭐ ┃ VIP Участник",
          "color": discord.Color.purple(),
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
  for r in roles_data:
    if not discord.utils.get(guild.roles, name=r["name"]):
      await guild.create_role(
          name=r["name"],
          color=r["color"],
          permissions=r["permissions"],
          hoist=r["hoist"],
      )

  cat_info = await guild.create_category("📌 ┃ НАВИГАЦИЯ И ИНФО")
  await guild.create_text_channel(
      "📜・правила-чата",
      category=cat_info,
      overwrites={
          guild.default_role: discord.PermissionOverwrite(
              read_messages=True, send_messages=False
          )
      },
  )
  news = await guild.create_text_channel(
      "📰・новости-сервера",
      category=cat_info,
      overwrites={
          guild.default_role: discord.PermissionOverwrite(
              read_messages=True, send_messages=False
          )
      },
  )

  cat_chat = await guild.create_category("💬 ┃ КОМЬЮНИТИ")
  await guild.create_text_channel(
      "💬・общий-чат",
      category=cat_chat,
      overwrites={
          guild.default_role: discord.PermissionOverwrite(read_messages=True)
      },
  )

  cat_voice = await guild.create_category("🔊 ┃ ПРИВАТНЫЕ КОМНАТЫ")
  await guild.create_voice_channel("🔊 ┃ Главный Лобби", category=cat_voice)
  await guild.create_voice_channel("➕ ┃ Создать комнатку", category=cat_voice)

  await news.send("✅ **Сервер полностью очищен и настроен заново!**")


@bot.command(name="setup")
@is_server_owner()
async def setup_server(ctx):
  await ctx.invoke(bot.get_command("clear"))


# ==========================================
# 6. ЭКОНОМИКА С КУЛДАУНАМИ И РАЗВЛЕЧЕНИЯ
# ==========================================


@bot.command(name="balance", aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
  m = member or ctx.author
  bal = USER_ECONOMY.get(m.id, 0)
  await ctx.send(f"💰 Баланс **{m.display_name}**: **{bal}** 🪙")


@bot.command(name="daily")
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
  uid = ctx.author.id
  USER_ECONOMY[uid] = USER_ECONOMY.get(uid, 0) + 500
  await ctx.send(f"🎁 {ctx.author.mention}, вы получили ежедневный бонус **500** 🪙!")


@daily.error
async def daily_error(ctx, error):
  if isinstance(error, commands.CommandOnCooldown):
    hours = round(error.retry_after / 3600, 1)
    await ctx.send(
        f"⏳ {ctx.author.mention}, вы уже получали бонус сегодня! Попробуйте через"
        f" **{hours}** ч.",
        delete_after=10,
    )


@bot.command(name="work")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def work(ctx):
  uid = ctx.author.id
  earned = random.randint(50, 250)
  USER_ECONOMY[uid] = USER_ECONOMY.get(uid, 0) + earned
  await ctx.send(
      f"💼 {ctx.author.mention}, вы успешно поработали и заработали"
      f" **{earned}** 🪙!"
  )


@work.error
async def work_error(ctx, error):
  if isinstance(error, commands.CommandOnCooldown):
    minutes = round(error.retry_after / 60)
    await ctx.send(
        f"⏳ {ctx.author.mention}, вы устали! Следующая смена будет доступна"
        f" через **{minutes}** мин.",
        delete_after=10,
    )


@bot.command(name="slot")
async def slot(ctx, bet: int = 10):
  uid = ctx.author.id
  bal = USER_ECONOMY.get(uid, 0)
  if bet <= 0 or bal < bet:
    return await ctx.send("❌ Недостаточно монет или неверная ставка!")
  e = ["🍒", "🍋", "🔔", "⭐", "💎"]
  res = [random.choice(e), random.choice(e), random.choice(e)]
  if res[0] == res[1] == res[2]:
    win = bet * 5
    USER_ECONOMY[uid] = bal + win
    await ctx.send(f"🎰 | {' | '.join(res)} |\n🎉 ДЖЕКПОТ! Вы выиграли **{win}** 🪙!")
  elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
    win = bet * 2
    USER_ECONOMY[uid] = bal + win
    await ctx.send(
        f"🎰 | {' | '.join(res)} |\n✨ Совпадение! Выигрыш: **{win}** 🪙!"
    )
  else:
    USER_ECONOMY[uid] = bal - bet
    await ctx.send(f"🎰 | {' | '.join(res)} |\n😢 Вы проиграли **{bet}** 🪙.")


@bot.command(name="ping")
async def ping(ctx):
  await ctx.send(f"pong! 🏓 Задержка: **{round(bot.latency * 1000)}мс**")


# ==========================================
# 7. МЕНЮ ПОМОЩИ (!help)
# ==========================================


@bot.command(name="help")
async def custom_help(ctx):
  embed = discord.Embed(
      title="📜 Меню помощи",
      description="Список категорий команд:",
      color=discord.Color.blue(),
  )
  embed.add_field(
      name="👑 Создатель",
      value="`!setup` / `!clear` — Сброс и настройка сервера",
      inline=False,
  )
  embed.add_field(
      name="🔊 Голосовые комнаты",
      value=(
          "`!setup_voice` — Установить систему приватных войсов\n`!vpanel` —"
          " Панель управления комнатой"
      ),
      inline=False,
  )
  embed.add_field(
      name="🛡️ Администрирование",
      value=(
          "`!admin` — Админ-панель (с выбором времени мута)\n`!ticket_panel` —"
          " Панель тикетов\n`!roles_panel` — Авто-роли\n`!ban` / `!kick` / `!mute`"
          " — Наказания"
      ),
      inline=False,
  )
  embed.add_field(
      name="🎉 Экономика и Развлечения",
      value=(
          "`!balance` / `!daily` (1 раз в день) / `!work` (1 раз в час) /"
          " `!slot` — Экономика\n`!ping` — Пинг"
      ),
      inline=False,
  )
  await ctx.send(embed=embed)


bot.run(os.getenv("DISCORD_TOKEN"))
