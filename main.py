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

# Базы данных в памяти
USER_WARNINGS = {}  # {user_id: [причины]}
USER_ECONOMY = {}  # {user_id: баланс}
USER_XP = {}  # {user_id: [xp, level]}
VOICE_OWNERS = {}  # {channel_id: owner_id}

# Магазин ролей: {item_id: {"name": "Название роли", "price": цена}}
ROLE_SHOP = {
    1: {"name": "⭐ ┃ VIP Участник", "price": 1000},
    2: {"name": "🎉 ┃ Ивентер", "price": 2500},
}


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
    except:
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
      if 0 <= val <= 99:
        await self.voice_channel.edit(user_limit=val)
        await interaction.response.send_message(
            f"👥 Лимит установлен на: **{val}**", ephemeral=True
        )
    except:
      await interaction.response.send_message(
          "❌ Ошибка ввода числа!", ephemeral=True
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
    except:
      pass

  if before.channel and before.channel.id in VOICE_OWNERS:
    if len(before.channel.members) == 0:
      del VOICE_OWNERS[before.channel.id]
      try:
        await before.channel.delete()
      except:
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
      if not member:
        return await interaction.response.send_message(
            "❌ Не найден!", ephemeral=True
        )
    except:
      return await interaction.response.send_message(
          "❌ Ошибка ID!", ephemeral=True
      )

    reason = self.reason.value or "Не указана"
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
    except:
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

  winner = random.choice([ctx.author, member])
  loser = member if winner == ctx.author else ctx.author

  USER_ECONOMY[winner.id] += bet
  USER_ECONOMY[loser.id] -= bet
  await ctx.send(
      f"⚔️ Дуэль между {ctx.author.mention} и {member.mention} на **{bet}** 🪙!\n🏆"
      f" Победитель: **{winner.name}**!"
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
          " Авто-роли"
      ),
      inline=False,
  )
  embed.add_field(
      name="💰 Экономика и Магазин",
      value="`!balance` | `!daily` | `!work` | `!shop` | `!buy` | `!duel`",
      inline=False,
  )
  embed.add_field(
      name="🎮 Игры и Уровни",
      value="`!rank` | `!slot` | `!roll` | `!coinflip` | `!ping`",
      inline=False,
  )
  await ctx.send(embed=embed)


bot.run(os.getenv("DISCORD_TOKEN"))
