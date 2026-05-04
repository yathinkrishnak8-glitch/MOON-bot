import discord
import random
from core import db, save_db, get_gif

# ========================================================================
# UI CLASSES: Pagination & Confirmation
# ========================================================================
class ConfirmView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30); self.ctx = ctx; self.value = None
    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your menu!", ephemeral=True)
        self.value = True; [setattr(c, 'disabled', True) for c in self.children]; await interaction.response.edit_message(view=self); self.stop()
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your menu!", ephemeral=True)
        self.value = False; [setattr(c, 'disabled', True) for c in self.children]; await interaction.response.edit_message(view=self); self.stop()

class PaginationView(discord.ui.View):
    def __init__(self, ctx, embeds):
        super().__init__(timeout=120); self.ctx = ctx; self.embeds = embeds; self.current_page = 0; self.update_buttons()
    def update_buttons(self):
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page == len(self.embeds) - 1)
    @discord.ui.button(label="◀️ Previous Page", style=discord.ButtonStyle.blurple)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your menu!", ephemeral=True)
        self.current_page -= 1; self.update_buttons(); await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    @discord.ui.button(label="Next Page ▶️", style=discord.ButtonStyle.blurple)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your menu!", ephemeral=True)
        self.current_page += 1; self.update_buttons(); await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)


# ========================================================================
# UI CLASSES: Economy Shop
# ========================================================================
class BuyButton(discord.ui.Button):
    def __init__(self, item): 
        super().__init__(label=f"🛒 Buy {item['name'][:15]} ({item['price']:,} 🪙)", style=discord.ButtonStyle.success)
        self.item = item
    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if db["economy"].get(uid, 0) < self.item["price"]: 
            return await interaction.response.send_message(embed=discord.Embed(description=f"❌ You need **{self.item['price']:,} coins**.", color=discord.Color.red()), ephemeral=True)
        db["economy"][uid] -= self.item["price"]
        db.setdefault("inventory", {}).setdefault(uid, []).append(self.item["name"])
        save_db(db)
        await interaction.response.send_message(embed=discord.Embed(description=f"✅ **Purchased!** Added **{self.item['name']}** to inventory.", color=discord.Color.green()), ephemeral=True)

class DynamicShopView(discord.ui.View):
    def __init__(self, shop_items):
        super().__init__(timeout=300)
        for item in shop_items: self.add_item(BuyButton(item))


# ========================================================================
# UI CLASSES: Epic AI Boss Fight
# ========================================================================
class ItemModal(discord.ui.Modal, title="Use an Item from Inventory"):
    item_name = discord.ui.TextInput(label="Exact Item Name", placeholder="e.g. Sukuna's Finger", required=True)
    action = discord.ui.TextInput(label="How do you use it?", style=discord.TextStyle.paragraph, placeholder="I swallow the finger to gain demonic power.", required=True)
    def __init__(self, view):
        super().__init__(); self.view = view 
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id); inv = db.setdefault("inventory", {}).get(uid, [])
        target_item = self.item_name.value.strip().lower()
        owned_item = next((i for i in inv if i.lower() == target_item), None)
        if not owned_item: return await interaction.followup.send(f"❌ You don't have `{self.item_name.value}`!", ephemeral=True)
        db["inventory"][uid].remove(owned_item); save_db(db)
        prompt = f"I use the item '{owned_item}' from my inventory! My action: {self.action.value}. Narrate the cinematic result, boss reaction, and battle status. End with '[CONTINUE]', '[WIN]', or '[LOSE]'."
        await self.view.process_turn(interaction, prompt, from_modal=True)

class AIBossFightView(discord.ui.View):
    def __init__(self, ctx, ai_client, chat_history):
        super().__init__(timeout=180); self.ctx = ctx; self.ai_client = ai_client; self.chat_history = chat_history
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author: 
            await interaction.response.send_message("❌ Not in your party!", ephemeral=True); return False
        return True
    async def process_turn(self, interaction: discord.Interaction, action_prompt: str, from_modal=False):
        if not from_modal: await interaction.response.defer()
        self.chat_history.append({"role": "user", "content": action_prompt})
        try:
            res = await self.ai_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=self.chat_history)
            reply = res.choices[0].message.content.strip()
        except Exception as e: return await interaction.followup.send(content=f"❌ DM disconnected: {e}", ephemeral=True)
        self.chat_history.append({"role": "assistant", "content": reply})

        if "[WIN]" in reply.upper():
            clean = reply.replace("[WIN]", "").replace("[win]", "").strip()
            reward = random.randint(5000000, 15000000); db["economy"][str(self.ctx.author.id)] = db["economy"].get(str(self.ctx.author.id), 0) + reward; save_db(db)
            embed = discord.Embed(title="🏆 RAID BOSS SLAIN!", description=f"{clean}\n\n💰 **Loot:** {reward:,} Coins!", color=discord.Color.gold())
            embed.set_image(url=get_gif("boss_win")); [setattr(c, 'disabled', True) for c in self.children]
            await interaction.edit_original_response(embed=embed, view=self)
        elif "[LOSE]" in reply.upper():
            clean = reply.replace("[LOSE]", "").replace("[lose]", "").strip()
            embed = discord.Embed(title="💀 RAID WIPE", description=clean, color=discord.Color.dark_red())
            embed.set_image(url=get_gif("boss_lose")); [setattr(c, 'disabled', True) for c in self.children]
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            clean = reply.replace("[CONTINUE]", "").replace("[continue]", "").strip()
            embed = discord.Embed(title="⚔️ RAID BOSS BATTLE", description=clean, color=discord.Color.dark_theme())
            embed.set_image(url=get_gif("boss_spawn")); await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Strike 🗡️", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction, button): await self.process_turn(interaction, "Launch a devastating close-quarters combo attack. Narrate outcome and end with '[CONTINUE]', '[WIN]', or '[LOSE]'.")
    @discord.ui.button(label="Cast Magic ✨", style=discord.ButtonStyle.primary)
    async def magic_button(self, interaction, button): await self.process_turn(interaction, "Channel mana and unleash magic spell. Narrate outcome and end with '[CONTINUE]', '[WIN]', or '[LOSE]'.")
    @discord.ui.button(label="Parry 🛡️", style=discord.ButtonStyle.success)
    async def defend_button(self, interaction, button): await self.process_turn(interaction, "Attempt a perfect parry/block. Narrate outcome and end with '[CONTINUE]', '[WIN]', or '[LOSE]'.")
    @discord.ui.button(label="Use Item 🎒", style=discord.ButtonStyle.secondary)
    async def item_button(self, interaction, button): 
        await interaction.response.send_modal(ItemModal(self))
