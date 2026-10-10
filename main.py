import asyncio
import datetime
import json
import os
import random
import re

import discord
from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# Базы данных (хранятся в памяти, автосохранение в data.json — см. раздел 8)
USER_WARNINGS = {}  # {user_id: [причины]}
USER_ECONOMY = {}  # {user_id: баланс}
USER_XP = {}  # {user_id: [xp, level]}
VOICE_OWNERS = {}  # {channel_id: owner_id}

# Доступ к данным из Cog'а с новыми командами
bot.economy = USER_ECONOMY
bot.xp = USER_XP
bot.user_warnings = USER_WARNINGS

# Магазин ролей: {item_id: {"name": "Название роли", "price": цена}}
ROLE_SHOP = {
    1: {"name": "⭐ ┃ VIP Участник", "price": 1000},
    2: {"name": "🎉 ┃ Ивентер", "price": 2500},
}


@bot.event
async def setup_hook():
  await bot.add_cog(Extras(bot))


@bot.event
async def on_ready():
  print(f"Бот {bot.user} успешно запущен и готов к работе!")


# ==========================================
# 1. СИСТЕМА УРОВНЕЙ И ЛОГИРОВАНИЕ
# ==========================================
@bot.event
async def on_message(message: discord.Message):
  if message.author.bot or not message.guild:
    return

  uid = message.author.id
  if uid not in USER_XP:
    USER_XP[uid] = [0, 1]

  xp_gain = random.randint(15, 25)
  USER_XP[uid][0] += xp_gain

  needed_xp = USER_XP[uid][1] * 100
  if USER_XP[uid][0] >= needed_xp:
    USER_XP[uid][0] -= needed_xp
    USER_XP[uid][1] += 1
    new_lvl = USER_XP[uid][1]
    await message.channel.send(
        f"🎉 Поздравляем, {message.author.mention}! Вы повысили свой уровень до"
        f" **{new_lvl}**!"
    )

  await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member):
  role = discord.utils.get(member.guild.roles, name="👤 ┃ Участник")
  if role:
    try:
      await member.add_roles(role)
    except discord.HTTPException:
      pass

  channel = discord.utils.get(member.guild.text_channels, name="💬・общий-чат")
  if channel:
    embed = discord.Embed(
        title="👋 Добро пожаловать!",
        description=f"Приветствуем тебя на сервере, {member.mention}!",
        color=discord.Color.green(),
    )
    embed.set_thumbnail(
        url=member.avatar.url if member.avatar else member.default_avatar.url
    )
    await channel.send(embed=embed)


@bot.event
async def on_message_delete(message: discord.Message):
  if message.author.bot or not message.guild:
    return
  log_channel = discord.utils.get(
      message.guild.text_channels, name="🛠️・логи-сервера"
  )
  if log_channel:
    embed = discord.Embed(
        title="🗑️ Удаленное сообщение",
        description=(
            f"**Автор:** {message.author.mention}\n**Канал:**"
            f" {message.channel.mention}\n**Текст:**"
            f" `{message.content or 'Медиа-файл / Эмбед'}`"
        ),
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(),
    )
    await log_channel.send(embed=embed)


# ==========================================
# 2. ПРИВАТНЫЕ ГОЛОСОВЫЕ КОМНАТЫ И НАСТРОЙКИ
# ==========================================


class RenameVoiceModal(discord.ui.Modal):

  def __init__(self, voice_channel: discord.VoiceChannel):
    super().__init__(title="Смена названия комнаты")
    self.voice_channel = voice_channel
    self.new_name = discord.ui.TextInput(
        label="Новое название канала", max_length=100, required=True
    )
    self.add_item(self.new_name)

  async def on_submit(self, interaction: discord.Interaction):
    await self.voice_channel.edit(name=self.new_name.value)
    await interaction.response.send_message(
        f"✅ Название изменено на: **{self.new_name.value}**", ephemeral=True
    )


class LimitVoiceModal(discord.ui.Modal):

  def __init__(self, voice_channel: discord.VoiceChannel):
    super().__init__(title="Лимит участников")
    self.voice_channel = voice_channel
    self.limit = discord.ui.TextInput(
        label="Лимит (0 - 99)", max_length=2, required=True
    )
    self.add_item(self.limit)

  async def on_submit(self, interaction: discord.Interaction):
    try:
      val = int(self.limit.value)
    except ValueError:
      return await interaction.response.send_message(
          "❌ Ошибка ввода числа!", ephemeral=True
      )
    if not 0 <= val <= 99:
      return await interaction.response.send_message(
          "❌ Лимит должен быть от 0 до 99!", ephemeral=True
      )
    await self.voice_channel.edit(user_limit=val)
    await interaction.response.send_message(
        f"👥 Лимит установлен на: **{val}**", ephemeral=True
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
          "❌ Вы не владелец комнаты!", ephemeral=True
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
    current = self.voice_channel.overwrites_for(everyone).connect
    if current is False:
      await self.voice_channel.set_permissions(everyone, connect=None)
      await interaction.response.send_message("🔓 Комната открыта!", ephemeral=True)
    else:
      await self.voice_channel.set_permissions(everyone, connect=False)
      await interaction.response.send_message(
          "🔒 Комната закрыта!", ephemeral=True
      )


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
  if after.channel and after.channel.name == "➕ ┃ Создать комнатку":
    new_channel = await member.guild.create_voice_channel(
        name=f"🔊 Комната {member.display_name}", category=after.channel.category
    )
    VOICE_OWNERS[new_channel.id] = member.id
    await member.move_to(new_channel)
    try:
      await member.send(
          "🎛️ Панель управления вашей комнатой:",
          view=VoiceControlView(new_channel, member.id),
      )
    except discord.HTTPException:
      pass

  if before.channel and before.channel.id in VOICE_OWNERS:
    if len(before.channel.members) == 0:
      del VOICE_OWNERS[before.channel.id]
      try:
        await before.channel.delete()
      except discord.HTTPException:
        pass


@bot.command(name="setup_voice")
@commands.has_permissions(administrator=True)
async def setup_voice(ctx):
  category = discord.utils.get(ctx.guild.categories, name="🔊 ┃ ПРИВАТНЫЕ КОМНАТЫ")
  if not category:
    category = await ctx.guild.create_category("🔊 ┃ ПРИВАТНЫЕ КОМНАТЫ")
  if not discord.utils.get(
      category.voice_channels, name="➕ ┃ Создать комнатку"
  ):
    await ctx.guild.create_voice_channel(
        name="➕ ┃ Создать комнатку", category=category
    )
    await ctx.send("✅ Система приватных войсов установлена!")
  else:
    await ctx.send("ℹ️ Триггер уже существует.")


@bot.command(name="vpanel")
async def voice_panel(ctx):
  if not ctx.author.voice or not ctx.author.voice.channel:
    return await ctx.send("❌ Вы не в голосовом канале!")
  channel = ctx.author.voice.channel
  owner_id = VOICE_OWNERS.get(channel.id)
  if not owner_id or (
      owner_id != ctx.author.id and not ctx.author.guild_permissions.administrator
  ):
    return await ctx.send("❌ Вы не владелец этой комнаты!")
  await ctx.send(
      "🎛️ Управление комнатой:", view=VoiceControlView(channel, owner_id)
  )


# ==========================================
# 3. ТИКЕТЫ И АВТО-РОЛИ
# ==========================================


class CloseTicketView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Закрыть тикет", style=discord.ButtonStyle.danger, emoji="🔒"
  )
  async def close(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message("⏳ Удаление через 3 сек...")
    await asyncio.sleep(3)
    await interaction.channel.delete()


class TicketCreateView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Открыть тикет", style=discord.ButtonStyle.success, emoji="📩"
  )
  async def create(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    guild = interaction.guild
    user = interaction.user
    category = discord.utils.get(guild.categories, name="🎫 ┃ ТИКЕТЫ И ПОДДЕРЖКА")
    if not category:
      category = await guild.create_category("🎫 ┃ ТИКЕТЫ И ПОДДЕРЖКА")

    name = f"ticket-{user.name}".lower()
    if discord.utils.get(guild.channels, name=name):
      return await interaction.response.send_message(
          "❌ У вас уже открыт тикет!", ephemeral=True
      )

    ch = await guild.create_text_channel(
        name=name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
        },
    )
    await ch.send(
        f"{user.mention}",
        embed=discord.Embed(
            title="🎫 Поддержка",
            description="Опишите вашу проблему.",
            color=discord.Color.blue(),
        ),
        view=CloseTicketView(),
    )
    await interaction.response.send_message(
        f"✅ Тикет создан: {ch.mention}", ephemeral=True
    )


@bot.command(name="ticket_panel")
@commands.has_permissions(administrator=True)
async def ticket_panel(ctx):
  await ctx.message.delete()
  await ctx.send(
      embed=discord.Embed(
          title="📩 Поддержка",
          description="Нажмите кнопку ниже, чтобы открыть тикет.",
          color=discord.Color.purple(),
      ),
      view=TicketCreateView(),
  )


class SelfRolesView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="VIP Участник", style=discord.ButtonStyle.secondary, emoji="⭐"
  )
  async def r1(self, interaction: discord.Interaction, button: discord.ui.Button):
    role = discord.utils.get(interaction.guild.roles, name="⭐ ┃ VIP Участник")
    if role in interaction.user.roles:
      await interaction.user.remove_roles(role)
      await interaction.response.send_message(
          "➖ Роль VIP снята!", ephemeral=True
      )
    else:
      await interaction.user.add_roles(role)
      await interaction.response.send_message("➕ Роль VIP выдана!", ephemeral=True)


@bot.command(name="roles_panel")
@commands.has_permissions(administrator=True)
async def roles_panel(ctx):
  await ctx.message.delete()
  await ctx.send(
      embed=discord.Embed(
          title="🎭 Авто-роли",
          description="Нажмите кнопку для получения роли.",
          color=discord.Color.gold(),
      ),
      view=SelfRolesView(),
  )


# ==========================================
# 4. АДМИН-ПАНЕЛЬ И МОДЕРАЦИЯ
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
    super().__init__(title=f"Модерация: {action_type.upper()}")
    self.action_type = action_type
    self.mute_duration = mute_duration
    self.target_id = discord.ui.TextInput(
        label="ID пользователя", placeholder="ID...", required=True
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
    except ValueError:
      return await interaction.response.send_message(
          "❌ Ошибка ID!", ephemeral=True
      )
    if not member:
      return await interaction.response.send_message(
          "❌ Не найден!", ephemeral=True
      )

    reason = self.reason.value or "Не указана"
    try:
      if self.action_type == "ban":
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Заблокирован **{member}**.")
      elif self.action_type == "kick":
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Изгнан **{member}**.")
      elif self.action_type == "mute":
        await member.timeout(
            datetime.timedelta(minutes=self.mute_duration), reason=reason
        )
        await interaction.response.send_message(
            f"🔇 Мут **{member}** на {self.mute_duration} мин."
        )
    except discord.Forbidden:
      await interaction.response.send_message(
          "❌ У бота недостаточно прав для этого участника!", ephemeral=True
      )


class MuteSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(label="5 минут", value="5"),
        discord.SelectOption(label="15 минут", value="15"),
        discord.SelectOption(label="1 час", value="60"),
        discord.SelectOption(label="1 день", value="1440"),
    ]
    super().__init__(placeholder="📌 Выберите время мута...", options=options)

  async def callback(self, interaction: discord.Interaction):
    await interaction.response.send_modal(
        ModModal("mute", mute_duration=int(self.values[0]))
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
        "Выберите время:", view=MuteView(), ephemeral=True
    )


@bot.command(name="admin")
@commands.has_permissions(administrator=True)
async def admin_panel(ctx):
  await ctx.send(
      embed=discord.Embed(
          title="🛡️ Панель Администратора", color=discord.Color.gold()
      ),
      view=AdminPanelView(),
  )


# ==========================================
# 5. ОЧИСТКА И НАСТРОЙКА СЕРВЕРА
# ==========================================
@bot.command(name="clear")
@is_server_owner()
async def clear_server(ctx):
  guild = ctx.guild
  await ctx.send("⚠️ Сброс и настройка сервера...")
  for channel in guild.channels:
    try:
      await channel.delete()
    except discord.HTTPException:
      pass

  roles = [
      ("👑 ┃ Создатель", discord.Color.red(), discord.Permissions(administrator=True)),
      (
          "🛡️ ┃ Главный Администратор",
          discord.Color.orange(),
          discord.Permissions(administrator=True),
      ),
      (
          "🔨 ┃ Модератор",
          discord.Color.blue(),
          discord.Permissions(kick_members=True, ban_members=True),
      ),
      (
          "⭐ ┃ VIP Участник",
          discord.Color.purple(),
          discord.Permissions.none(),
      ),
      ("👤 ┃ Участник", discord.Color.default(), discord.Permissions.none()),
  ]
  for name, col, perms in roles:
    if not discord.utils.get(guild.roles, name=name):
      await guild.create_role(name=name, color=col, permissions=perms, hoist=True)

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

  cat_admin = await guild.create_category("🛡️ ┃ УПРАВЛЕНИЕ")
  await guild.create_text_channel(
      "🛠️・логи-сервера",
      category=cat_admin,
      overwrites={
          guild.default_role: discord.PermissionOverwrite(read_messages=False)
      },
  )

  cat_voice = await guild.create_category("🔊 ┃ ПРИВАТНЫЕ КОМНАТЫ")
  await guild.create_voice_channel("🔊 ┃ Главный Лобби", category=cat_voice)
  await guild.create_voice_channel("➕ ┃ Создать комнатку", category=cat_voice)

  await news.send("✅ **Сервер полностью настроен!**")


@bot.command(name="setup")
@is_server_owner()
async def setup_server(ctx):
  await ctx.invoke(bot.get_command("clear"))


# ==========================================
# 6. ЭКОНОМИКА, МАГАЗИН И МИНИ-ИГРЫ
# ==========================================


@bot.command(name="balance", aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
  m = member or ctx.author
  bal = USER_ECONOMY.get(m.id, 0)
  await ctx.send(f"💰 Баланс **{m.display_name}**: **{bal}** 🪙")


@bot.command(name="daily")
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
  USER_ECONOMY[ctx.author.id] = USER_ECONOMY.get(ctx.author.id, 0) + 500
  await ctx.send(f"🎁 {ctx.author.mention}, ежедневный бонус **500** 🪙 забран!")


@daily.error
async def daily_error(ctx, error):
  if isinstance(error, commands.CommandOnCooldown):
    await ctx.send(
        f"⏳ Подождите еще **{round(error.retry_after / 3600, 1)}** ч.",
        delete_after=5,
    )


@bot.command(name="work")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def work(ctx):
  earned = random.randint(50, 250)
  USER_ECONOMY[ctx.author.id] = USER_ECONOMY.get(ctx.author.id, 0) + earned
  await ctx.send(
      f"💼 {ctx.author.mention}, вы заработали **{earned}** 🪙 на работе!"
  )


@work.error
async def work_error(ctx, error):
  if isinstance(error, commands.CommandOnCooldown):
    await ctx.send(
        f"⏳ На работу можно через **{round(error.retry_after / 60)}** мин.",
        delete_after=5,
    )


@bot.command(name="shop")
async def shop(ctx):
  embed = discord.Embed(
      title="🛍️ Магазин ролей",
      description="Купите роль с помощью `!buy [ID]`",
      color=discord.Color.blue(),
  )
  for item_id, info in ROLE_SHOP.items():
    embed.add_field(
        name=f"[{item_id}] {info['name']}",
        value=f"Цена: **{info['price']}** 🪙",
        inline=False,
    )
  await ctx.send(embed=embed)


@bot.command(name="buy")
async def buy(ctx, item_id: int):
  if item_id not in ROLE_SHOP:
    return await ctx.send("❌ Товара с таким ID не существует!")
  item = ROLE_SHOP[item_id]
  bal = USER_ECONOMY.get(ctx.author.id, 0)
  if bal < item["price"]:
    return await ctx.send("❌ У вас недостаточно монет!")

  role = discord.utils.get(ctx.guild.roles, name=item["name"])
  if not role:
    return await ctx.send("❌ Ошибка: Роль не найдена на сервере.")

  USER_ECONOMY[ctx.author.id] -= item["price"]
  await ctx.author.add_roles(role)
  await ctx.send(
      f"✅ Вы успешно приобрели роль **{role.name}** за **{item['price']}** 🪙!"
  )


@bot.command(name="rank")
async def rank(ctx, member: discord.Member = None):
  m = member or ctx.author
  xp, lvl = USER_XP.get(m.id, [0, 1])
  await ctx.send(
      f"📊 Уровень **{m.display_name}**: **{lvl}** (Опыт: **{xp}/{lvl*100}** XP)"
  )


class DuelView(discord.ui.View):
  """Дуэль с подтверждением от соперника."""

  def __init__(self, challenger: discord.Member, opponent: discord.Member, bet: int):
    super().__init__(timeout=60)
    self.challenger = challenger
    self.opponent = opponent
    self.bet = bet
    self.message = None

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user != self.opponent:
      await interaction.response.send_message(
          "❌ Это вызов не для вас!", ephemeral=True
      )
      return False
    return True

  def _disable(self):
    for child in self.children:
      child.disabled = True

  async def on_timeout(self):
    self._disable()
    if self.message:
      await self.message.edit(content="⌛ Вызов на дуэль истёк.", view=self)

  @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="⚔️")
  async def accept(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self._disable()
    self.stop()
    bal1 = USER_ECONOMY.get(self.challenger.id, 0)
    bal2 = USER_ECONOMY.get(self.opponent.id, 0)
    if bal1 < self.bet or bal2 < self.bet:
      return await interaction.response.edit_message(
          content="❌ У кого-то из игроков уже не хватает монет!", view=self
      )
    winner = random.choice([self.challenger, self.opponent])
    loser = self.opponent if winner == self.challenger else self.challenger
    USER_ECONOMY[winner.id] = USER_ECONOMY.get(winner.id, 0) + self.bet
    USER_ECONOMY[loser.id] = USER_ECONOMY.get(loser.id, 0) - self.bet
    await interaction.response.edit_message(
        content=(
            f"⚔️ Дуэль {self.challenger.mention} vs {self.opponent.mention} на"
            f" **{self.bet}** 🪙!\n🏆 Победитель: **{winner.display_name}**!"
        ),
        view=self,
    )

  @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="✖️")
  async def decline(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self._disable()
    self.stop()
    await interaction.response.edit_message(
        content=f"🏳️ {self.opponent.mention} отклонил(а) дуэль.", view=self
    )


@bot.command(name="duel")
async def duel(ctx, member: discord.Member, bet: int):
  if member == ctx.author or member.bot:
    return await ctx.send("❌ Нельзя вызвать этого участника на дуэль!")
  bal1 = USER_ECONOMY.get(ctx.author.id, 0)
  bal2 = USER_ECONOMY.get(member.id, 0)
  if bet <= 0 or bal1 < bet or bal2 < bet:
    return await ctx.send(
        "❌ У кого-то из игроков недостаточно монет или ставка неверная!"
    )
  view = DuelView(ctx.author, member, bet)
  view.message = await ctx.send(
      f"⚔️ {member.mention}, {ctx.author.mention} вызывает вас на дуэль на"
      f" **{bet}** 🪙! У вас 60 секунд.",
      view=view,
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


@bot.command(name="roll")
async def roll_dice(ctx):
  await ctx.send(
      f"🎲 **{ctx.author.name}** бросил кубик: **{random.randint(1, 100)}** (из"
      " 100)"
  )


@bot.command(name="coinflip")
async def coinflip(ctx):
  await ctx.send(
      f"🪙 **{ctx.author.name}** подбросил монетку: **{random.choice(['Орёл', 'Решка'])}**"
  )


@bot.command(name="ping")
async def ping(ctx):
  await ctx.send(f"pong! 🏓 `{round(bot.latency * 1000)}мс`")


# ==========================================
# 7. МЕНЮ ПОМОЩИ (!help)
# ==========================================
@bot.command(name="help")
async def custom_help(ctx):
  embed = discord.Embed(
      title="📜 Меню помощи",
      description="Все доступные команды бота:",
      color=discord.Color.blue(),
  )
  embed.add_field(
      name="👑 Владелец",
      value="`!setup` / `!clear` — Сброс сервера\n`!setup_voice` — Войсы",
      inline=False,
  )
  embed.add_field(
      name="🛡️ Модерация",
      value=(
          "`!admin` — Админ-панель\n`!ticket_panel` — Тикеты\n`!roles_panel` —"
          " Авто-роли\n`!warn` | `!warns` | `!clearwarns` | `!purge N`\n"
          "`!giveaway 10m приз` — Розыгрыш"
      ),
      inline=False,
  )
  embed.add_field(
      name="💰 Экономика и Магазин",
      value=(
          "`!balance` | `!daily` | `!work` | `!shop` | `!buy` | `!duel`\n"
          "`!pay @user сумма` | `!top [money|xp]` | `!roulette ставка цвет`"
      ),
      inline=False,
  )
  embed.add_field(
      name="🎮 Игры и Уровни",
      value=(
          "`!rank` | `!slot` | `!roll` | `!coinflip` | `!ping`\n"
          "`!rps` | `!8ball вопрос` | `!rate что-то` | `!choose а | б`"
      ),
      inline=False,
  )
  embed.add_field(
      name="🎉 Социальное и инфо",
      value=(
          "`!hug/!slap/!pat/!kiss @user` | `!poll вопрос | а | б`\n"
          "`!remind 10m текст` | `!avatar` | `!userinfo` | `!serverinfo`"
      ),
      inline=False,
  )
  await ctx.send(embed=embed)


# ==========================================
# 8. НОВЫЕ ФУНКЦИИ (Cog "Extras")
# ==========================================

DATA_FILE = "data.json"


def parse_duration(text: str):
  """'30s', '10m', '2h', '1d' -> секунды (или None)."""
  m = re.fullmatch(r"(\d+)([smhd])", text.lower())
  if not m:
    return None
  return int(m[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m[2]]


# ---------- Камень-ножницы-бумага ----------
RPS_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


class RPSView(discord.ui.View):

  def __init__(self, author: discord.Member):
    super().__init__(timeout=30)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user != self.author:
      await interaction.response.send_message(
          "❌ Это не ваша игра!", ephemeral=True
      )
      return False
    return True

  async def play(self, interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(list(RPS_EMOJI))
    if choice == bot_choice:
      result = "🤝 Ничья!"
    elif RPS_BEATS[choice] == bot_choice:
      result = "🎉 Вы победили!"
    else:
      result = "😢 Вы проиграли!"
    for child in self.children:
      child.disabled = True
    await interaction.response.edit_message(
        content=(
            f"Вы: {RPS_EMOJI[choice]} | Бот: {RPS_EMOJI[bot_choice]}\n{result}"
        ),
        view=self,
    )
    self.stop()

  @discord.ui.button(label="Камень", emoji="🪨")
  async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.play(interaction, "rock")

  @discord.ui.button(label="Бумага", emoji="📄")
  async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.play(interaction, "paper")

  @discord.ui.button(label="Ножницы", emoji="✂️")
  async def scissors(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.play(interaction, "scissors")


# ---------- Розыгрыш ----------
class GiveawayView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.users = set()

  @discord.ui.button(
      label="Участвовать", style=discord.ButtonStyle.success, emoji="🎉"
  )
  async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.user.id in self.users:
      self.users.remove(interaction.user.id)
      await interaction.response.send_message(
          "➖ Вы вышли из розыгрыша.", ephemeral=True
      )
    else:
      self.users.add(interaction.user.id)
      await interaction.response.send_message(
          "➕ Вы участвуете в розыгрыше!", ephemeral=True
      )


RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
COLOR_ALIASES = {
    "red": "red", "красное": "red", "красный": "red", "к": "red",
    "black": "black", "черное": "black", "чёрное": "black", "чёрный": "black", "ч": "black",
    "green": "green", "зеленое": "green", "зелёное": "green", "з": "green",
}  # fmt: skip

EIGHT_BALL = [
    "✅ Бесспорно", "✅ Да, определённо", "✅ Скорее всего да",
    "🤔 Пока не ясно, спроси позже", "🤔 Сконцентрируйся и спроси ещё раз",
    "❌ Даже не думай", "❌ Мой ответ — нет", "❌ Перспективы не очень",
]  # fmt: skip

ACTIONS = {
    "hug": ("🤗", "обнял(а)"),
    "slap": ("👋", "дал(а) леща"),
    "pat": ("🫳", "погладил(а) по голове"),
    "kiss": ("😘", "поцеловал(а)"),
}


class Extras(commands.Cog):
  """Дополнительные функции бота."""

  def __init__(self, bot: commands.Bot):
    self.bot = bot
    self.load_data()
    self.autosave.start()

  # ---------- Сохранение данных ----------
  def load_data(self):
    if not os.path.exists(DATA_FILE):
      return
    try:
      with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    except (OSError, json.JSONDecodeError):
      return
    self.bot.economy.update({int(k): v for k, v in data.get("economy", {}).items()})
    self.bot.xp.update({int(k): v for k, v in data.get("xp", {}).items()})
    self.bot.user_warnings.update(
        {int(k): v for k, v in data.get("warnings", {}).items()}
    )

  def save_data(self):
    data = {
        "economy": self.bot.economy,
        "xp": self.bot.xp,
        "warnings": self.bot.user_warnings,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False)

  @tasks.loop(seconds=60)
  async def autosave(self):
    self.save_data()

  def cog_unload(self):
    self.autosave.cancel()
    self.save_data()

  # ---------- Общий обработчик ошибок ----------
  @commands.Cog.listener()
  async def on_command_error(self, ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
      return
    if ctx.command and ctx.command.has_error_handler():
      return
    if isinstance(error, commands.MissingPermissions):
      await ctx.send("❌ У вас недостаточно прав.")
    elif isinstance(error, commands.MissingRequiredArgument):
      await ctx.send(f"❌ Не хватает аргумента: `{error.param.name}`")
    elif isinstance(error, (commands.BadArgument, commands.MemberNotFound)):
      await ctx.send("❌ Неверный аргумент (участник не найден или не число).")
    elif isinstance(error, commands.CommandOnCooldown):
      await ctx.send(f"⏳ Подождите {error.retry_after:.0f} сек.")
    elif isinstance(error, commands.CheckFailure):
      await ctx.send(f"❌ {error}")
    else:
      print(f"Ошибка в команде {ctx.command}: {error!r}")

  # ---------- Экономика ----------
  @commands.command(name="pay")
  async def pay(self, ctx, member: discord.Member, amount: int):
    """Перевести монеты другому участнику."""
    eco = self.bot.economy
    if member.bot or member == ctx.author or amount <= 0:
      return await ctx.send("❌ Неверный получатель или сумма.")
    if eco.get(ctx.author.id, 0) < amount:
      return await ctx.send("❌ Недостаточно монет!")
    eco[ctx.author.id] -= amount
    eco[member.id] = eco.get(member.id, 0) + amount
    await ctx.send(f"💸 {ctx.author.mention} перевёл {member.mention} **{amount}** 🪙")

  @commands.command(name="top", aliases=["leaderboard", "lb"])
  async def top(self, ctx, kind: str = "money"):
    """Топ-10: !top money / !top xp"""
    if kind.lower() in ("xp", "lvl", "level", "уровень"):
      items = sorted(
          self.bot.xp.items(), key=lambda kv: (kv[1][1], kv[1][0]), reverse=True
      )[:10]
      title = "📊 Топ по уровню"
      fmt = lambda v: f"ур. **{v[1]}** ({v[0]} XP)"
    else:
      items = sorted(self.bot.economy.items(), key=lambda kv: kv[1], reverse=True)[:10]
      title = "💰 Топ по балансу"
      fmt = lambda v: f"**{v}** 🪙"
    if not items:
      return await ctx.send("Пока никого в топе.")
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, val) in enumerate(items):
      m = ctx.guild.get_member(uid)
      name = m.display_name if m else f"ID {uid}"
      lines.append(f"{medals[i] if i < 3 else f'`{i + 1}.`'} {name} — {fmt(val)}")
    await ctx.send(
        embed=discord.Embed(
            title=title, description="\n".join(lines), color=discord.Color.gold()
        )
    )

  @commands.command(name="roulette", aliases=["rl"])
  async def roulette(self, ctx, bet: int, color: str):
    """Рулетка: !roulette 100 красное|чёрное|зелёное"""
    color = COLOR_ALIASES.get(color.lower())
    eco = self.bot.economy
    bal = eco.get(ctx.author.id, 0)
    if not color:
      return await ctx.send("❌ Выберите: красное, чёрное или зелёное.")
    if bet <= 0 or bal < bet:
      return await ctx.send("❌ Недостаточно монет или неверная ставка!")
    n = random.randint(0, 36)
    result = "green" if n == 0 else "red" if n in RED_NUMBERS else "black"
    emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[result]
    if result == color:
      mult = 14 if result == "green" else 2
      eco[ctx.author.id] = bal + bet * (mult - 1)
      await ctx.send(f"🎡 Выпало {emoji} **{n}**\n🎉 Вы выиграли **{bet * mult}** 🪙!")
    else:
      eco[ctx.author.id] = bal - bet
      await ctx.send(f"🎡 Выпало {emoji} **{n}**\n😢 Вы проиграли **{bet}** 🪙.")

  # ---------- Развлечения ----------
  @commands.command(name="8ball")
  async def eight_ball(self, ctx, *, question: str):
    """Магический шар."""
    await ctx.send(f"🎱 **{question}**\n{random.choice(EIGHT_BALL)}")

  @commands.command(name="rps")
  async def rps(self, ctx):
    """Камень-ножницы-бумага с ботом."""
    await ctx.send("Выбирайте:", view=RPSView(ctx.author))

  @commands.command(name="hug", aliases=["slap", "pat", "kiss"])
  async def action(self, ctx, member: discord.Member):
    """!hug / !slap / !pat / !kiss @участник"""
    emoji, text = ACTIONS[ctx.invoked_with.lower()]
    await ctx.send(f"{emoji} **{ctx.author.display_name}** {text} **{member.display_name}**")

  @commands.command(name="rate")
  async def rate(self, ctx, *, thing: str):
    """Оценить что-нибудь по 10-балльной шкале."""
    rng = random.Random(thing.lower())  # одна и та же вещь = одна и та же оценка
    await ctx.send(f"⭐ Я оцениваю **{thing}** на **{rng.randint(0, 10)}/10**")

  @commands.command(name="choose")
  async def choose(self, ctx, *, options: str):
    """!choose пицца | суши | бургер"""
    parts = [p.strip() for p in options.split("|") if p.strip()]
    if len(parts) < 2:
      return await ctx.send("❌ Укажите минимум 2 варианта через `|`.")
    await ctx.send(f"🤔 Я выбираю: **{random.choice(parts)}**")

  @commands.command(name="poll")
  async def poll(self, ctx, *, text: str):
    """!poll Вопрос | вариант 1 | вариант 2 ..."""
    parts = [p.strip() for p in text.split("|") if p.strip()]
    if len(parts) < 3 or len(parts) > 11:
      return await ctx.send("❌ Формат: `!poll Вопрос | вариант 1 | вариант 2` (до 10 вариантов)")
    numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    question, options = parts[0], parts[1:]
    desc = "\n".join(f"{numbers[i]} {opt}" for i, opt in enumerate(options))
    msg = await ctx.send(
        embed=discord.Embed(
            title=f"📊 {question}", description=desc, color=discord.Color.blurple()
        )
    )
    for i in range(len(options)):
      await msg.add_reaction(numbers[i])

  @commands.command(name="remind")
  async def remind(self, ctx, duration: str, *, text: str):
    """!remind 10m Выключить плиту (s/m/h/d, до 7 дней)"""
    secs = parse_duration(duration)
    if not secs or secs > 7 * 86400:
      return await ctx.send("❌ Формат времени: `30s`, `10m`, `2h`, `1d` (макс. 7д)")
    await ctx.send(f"⏰ Напомню через **{duration}**: {text}")
    await asyncio.sleep(secs)
    await ctx.send(f"⏰ {ctx.author.mention}, напоминание: **{text}**")

  @commands.command(name="giveaway")
  @commands.has_permissions(administrator=True)
  async def giveaway(self, ctx, duration: str, *, prize: str):
    """!giveaway 10m Нитро"""
    secs = parse_duration(duration)
    if not secs:
      return await ctx.send("❌ Формат: `!giveaway 10m Приз`")
    view = GiveawayView()
    end = discord.utils.utcnow() + datetime.timedelta(seconds=secs)
    embed = discord.Embed(
        title="🎁 РОЗЫГРЫШ",
        description=f"Приз: **{prize}**\nЗавершится {discord.utils.format_dt(end, 'R')}",
        color=discord.Color.magenta(),
    )
    msg = await ctx.send(embed=embed, view=view)
    await asyncio.sleep(secs)
    for child in view.children:
      child.disabled = True
    await msg.edit(view=view)
    if view.users:
      winner = random.choice(list(view.users))
      await ctx.send(f"🎉 Победитель розыгрыша **{prize}**: <@{winner}>!")
    else:
      await ctx.send("😢 В розыгрыше никто не участвовал.")

  # ---------- Информация ----------
  @commands.command(name="avatar")
  async def avatar(self, ctx, member: discord.Member = None):
    m = member or ctx.author
    embed = discord.Embed(title=f"Аватар {m.display_name}", color=m.color)
    embed.set_image(url=m.display_avatar.url)
    await ctx.send(embed=embed)

  @commands.command(name="userinfo", aliases=["whois"])
  async def userinfo(self, ctx, member: discord.Member = None):
    m = member or ctx.author
    roles = [r.mention for r in m.roles[1:]][::-1]
    embed = discord.Embed(title=f"👤 {m}", color=m.color)
    embed.set_thumbnail(url=m.display_avatar.url)
    embed.add_field(name="ID", value=m.id)
    embed.add_field(name="Аккаунт создан", value=discord.utils.format_dt(m.created_at, "D"))
    embed.add_field(
        name="Зашёл на сервер",
        value=discord.utils.format_dt(m.joined_at, "D") if m.joined_at else "—",
    )
    xp, lvl = self.bot.xp.get(m.id, [0, 1])
    embed.add_field(name="Уровень", value=f"{lvl} ({xp} XP)")
    embed.add_field(name="Баланс", value=f"{self.bot.economy.get(m.id, 0)} 🪙")
    embed.add_field(name="Предупреждения", value=len(self.bot.user_warnings.get(m.id, [])))
    embed.add_field(
        name=f"Роли ({len(roles)})",
        value=" ".join(roles[:15]) or "нет",
        inline=False,
    )
    await ctx.send(embed=embed)

  @commands.command(name="serverinfo", aliases=["server"])
  async def serverinfo(self, ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blue())
    if g.icon:
      embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Владелец", value=g.owner.mention if g.owner else "—")
    embed.add_field(name="Участников", value=g.member_count)
    embed.add_field(name="Создан", value=discord.utils.format_dt(g.created_at, "D"))
    embed.add_field(name="Текстовых каналов", value=len(g.text_channels))
    embed.add_field(name="Голосовых каналов", value=len(g.voice_channels))
    embed.add_field(name="Ролей", value=len(g.roles))
    await ctx.send(embed=embed)

  # ---------- Модерация ----------
  @commands.command(name="warn")
  @commands.has_permissions(kick_members=True)
  async def warn(self, ctx, member: discord.Member, *, reason: str = "Не указана"):
    """Выдать предупреждение. 3 предупреждения = мут на 1 час."""
    warns = self.bot.user_warnings.setdefault(member.id, [])
    warns.append(reason)
    await ctx.send(f"⚠️ {member.mention} получил предупреждение ({len(warns)}/3): {reason}")
    if len(warns) >= 3:
      try:
        await member.timeout(datetime.timedelta(hours=1), reason="3 предупреждения")
        warns.clear()
        await ctx.send(f"🔇 {member.mention} получил мут на 1 час за 3 предупреждения.")
      except discord.Forbidden:
        await ctx.send("❌ Не хватает прав, чтобы замутить этого участника.")

  @commands.command(name="warns")
  @commands.has_permissions(kick_members=True)
  async def warns(self, ctx, member: discord.Member):
    warns = self.bot.user_warnings.get(member.id, [])
    if not warns:
      return await ctx.send("✅ У участника нет предупреждений.")
    text = "\n".join(f"`{i + 1}.` {r}" for i, r in enumerate(warns))
    await ctx.send(embed=discord.Embed(title=f"⚠️ Предупреждения {member}", description=text))

  @commands.command(name="clearwarns")
  @commands.has_permissions(kick_members=True)
  async def clearwarns(self, ctx, member: discord.Member):
    self.bot.user_warnings.pop(member.id, None)
    await ctx.send(f"✅ Предупреждения {member.mention} сброшены.")

  @commands.command(name="purge")
  @commands.has_permissions(manage_messages=True)
  async def purge(self, ctx, amount: int):
    """Удалить N последних сообщений (до 100)."""
    if not 1 <= amount <= 100:
      return await ctx.send("❌ Укажите число от 1 до 100.")
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Удалено сообщений: **{len(deleted) - 1}**", delete_after=4)


bot.run(os.getenv("DISCORD_TOKEN"))
