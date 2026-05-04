
import discord
from discord.ext import commands
import random
import asyncio
from core import db, save_db, get_gif

# ========================================================================
# ADVANCED BLACKJACK ENGINE (REACTION & ANIMATION BASED)
# ========================================================================
def calculate_hand(hand):
    """Calculates the optimal blackjack hand value, accounting for soft/hard Aces."""
    value = sum([card['value'] for card in hand])
    aces = sum([1 for card in hand if card['rank'] == 'A'])
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def generate_deck():
    """Generates a fresh standard 52-card deck with casino formatting."""
    suits = ['♠️', '♥️', '♣️', '♦️']
    ranks = [('2', 2), ('3', 3), ('4', 4), ('5', 5), ('6', 6), ('7', 7), ('8', 8), ('9', 9), ('10', 10), ('J', 10), ('Q', 10), ('K', 10), ('A', 11)]
    return [{'rank': r[0], 'suit': s, 'value': r[1], 'display': f"[{r[0]}{s}]"} for s in suits for r in ranks]

def format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=True, result_msg=None):
    """Generates the OwO-style visual card board."""
    p_val = calculate_hand(player_hand)
    p_cards = " ".join([c['display'] for c in player_hand])
    
    if hide_dealer:
        d_val = dealer_hand[0]['value']
        d_cards = f"{dealer_hand[0]['display']}  [ ? ]"
    else:
        d_val = calculate_hand(dealer_hand)
        d_cards = " ".join([c['display'] for c in dealer_hand])

    embed = discord.Embed(title="🃏 High Stakes Blackjack", color=discord.Color.dark_theme())
    embed.add_field(name=f"👤 {ctx.author.name}'s Hand (Value: {p_val})", value=p_cards, inline=False)
    embed.add_field(name=f"🕴️ Dealer's Hand (Value: {d_val if hide_dealer else d_val})", value=d_cards, inline=False)
    
    if result_msg:
        embed.add_field(name="📋 Result", value=result_msg, inline=False)
        
    embed.set_footer(text=f"Current Bet: {bet:,} 🪙")
    return embed, p_val


# ========================================================================
# COG CLASS: Casino
# ========================================================================
class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 🔥 THE ANTI-DUPE LOCK: Prevents playing multiple games at once!
        self.active_gamblers = set()

    def check_bet(self, uid, bet):
        """Helper to safely check if a bet is valid."""
        bal = db.setdefault("economy", {}).get(uid, 0)
        if bet <= 0: return False, "❌ You must bet more than 0 coins."
        if bal < bet: return False, f"❌ You don't have enough coins! Balance: **{bal:,} 🪙**"
        return True, ""


    # ========================================================================
    # COMMAND: /blackjack (EXPLOIT PROOF)
    # ========================================================================
    @commands.hybrid_command(name="blackjack", aliases=["bj"], description="Play Blackjack using classic reaction emojis!")
    async def blackjack(self, ctx, bet: int):
        uid = str(ctx.author.id)
        
        # Security Lock Check
        if uid in self.active_gamblers:
            return await ctx.send(embed=discord.Embed(description="❌ You are already in an active casino game! Finish it first.", color=discord.Color.red()), ephemeral=True)
            
        valid, msg = self.check_bet(uid, bet)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))
            
        # Lock the user and deduct initial bet instantly
        self.active_gamblers.add(uid)
        db["economy"][uid] -= bet
        save_db(db)
        
        try:
            deck = generate_deck()
            random.shuffle(deck)
            
            player_hand = [deck.pop(), deck.pop()]
            dealer_hand = [deck.pop(), deck.pop()]
            
            embed, p_val = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=True)
            
            # Check for instant natural 21
            if p_val == 21:
                d_val = calculate_hand(dealer_hand)
                if d_val == 21:
                    db["economy"][uid] += bet # Refund
                    save_db(db)
                    embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg="🤝 **PUSH!** Both of you got a natural Blackjack!")
                    embed.color = discord.Color.light_grey()
                else:
                    winnings = int(bet * 1.5)
                    db["economy"][uid] += winnings
                    save_db(db)
                    embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg=f"🌟 **BLACKJACK!** You won **{winnings:,} 🪙**!")
                    embed.color = discord.Color.gold()
                    embed.set_image(url=get_gif("blackjack_win"))
                return await ctx.send(embed=embed)

            game_msg = await ctx.send(embed=embed)
            
            await game_msg.add_reaction("🃏") # Hit
            await game_msg.add_reaction("🛑") # Stand
            await game_msg.add_reaction("⏬") # Double Down

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["🃏", "🛑", "⏬"] and reaction.message.id == game_msg.id

            playing = True
            can_double = True

            while playing:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                    try: await game_msg.remove_reaction(reaction, user)
                    except: pass

                    emoji = str(reaction.emoji)
                    
                    # --- HIT LOGIC ---
                    if emoji == "🃏":
                        can_double = False
                        player_hand.append(deck.pop())
                        p_val = calculate_hand(player_hand)
                        
                        if len(player_hand) == 5 and p_val <= 21:
                            db["economy"][uid] += bet * 2
                            embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg=f"🎉 **5-CARD CHARLIE!** You won **{bet:,} 🪙**!")
                            embed.color = discord.Color.green()
                            embed.set_image(url=get_gif("blackjack_win"))
                            playing = False
                        elif p_val > 21:
                            embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg=f"💀 **BUST!** You lost **{bet:,} 🪙**.")
                            embed.color = discord.Color.red()
                            embed.set_image(url=get_gif("blackjack_lose"))
                            playing = False
                        elif p_val == 21:
                            emoji = "🛑"
                        else:
                            embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=True)
                            await game_msg.edit(embed=embed)

                    # --- DOUBLE DOWN LOGIC ---
                    if emoji == "⏬":
                        if not can_double:
                            await ctx.send("❌ You can only double down on your first turn!", delete_after=3)
                            continue
                        
                        bal = db.get("economy", {}).get(uid, 0)
                        if bal < bet:
                            await ctx.send("❌ Not enough coins to double down!", delete_after=3)
                            continue
                            
                        db["economy"][uid] -= bet
                        bet *= 2
                        
                        player_hand.append(deck.pop())
                        p_val = calculate_hand(player_hand)
                        
                        if p_val > 21:
                            embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg=f"💀 **DOUBLE DOWN BUST!** You lost **{bet:,} 🪙**.")
                            embed.color = discord.Color.red()
                            embed.set_image(url=get_gif("blackjack_lose"))
                            playing = False
                        else:
                            emoji = "🛑"

                    # --- STAND LOGIC ---
                    if emoji == "🛑" and playing:
                        while calculate_hand(dealer_hand) < 17:
                            dealer_hand.append(deck.pop())
                            
                        d_val = calculate_hand(dealer_hand)
                        p_val = calculate_hand(player_hand)
                        
                        if d_val > 21:
                            db["economy"][uid] += bet * 2
                            msg = f"🎉 **DEALER BUSTS!** You won **{bet:,} 🪙**!"
                            color = discord.Color.green()
                            img = get_gif("blackjack_win")
                        elif p_val > d_val:
                            db["economy"][uid] += bet * 2
                            msg = f"🎉 **YOU WIN!** You won **{bet:,} 🪙**!"
                            color = discord.Color.green()
                            img = get_gif("blackjack_win")
                        elif p_val < d_val:
                            msg = f"💀 **YOU LOSE!** Dealer takes **{bet:,} 🪙**."
                            color = discord.Color.red()
                            img = get_gif("blackjack_lose")
                        else:
                            db["economy"][uid] += bet
                            msg = f"🤝 **PUSH!** Your **{bet:,} 🪙** was returned."
                            color = discord.Color.light_grey()
                            img = None
                            
                        embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg=msg)
                        embed.color = color
                        if img: embed.set_image(url=img)
                        playing = False

                except asyncio.TimeoutError:
                    embed, _ = format_board(ctx, bet, player_hand, dealer_hand, hide_dealer=False, result_msg=f"💤 **AFK!** You took too long. The dealer kept your **{bet:,} 🪙**.")
                    embed.color = discord.Color.dark_grey()
                    playing = False

            save_db(db)
            await game_msg.edit(embed=embed)
            try: await game_msg.clear_reactions()
            except: pass
            
        finally:
            # UNLOCK THE USER NO MATTER WHAT HAPPENS
            self.active_gamblers.discard(uid)


    # ========================================================================
    # COMMAND: /slots (EXPLOIT PROOF)
    # ========================================================================
    @commands.hybrid_command(name="slots", description="Spin the high-speed animated slot machine!")
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        
        if uid in self.active_gamblers:
            return await ctx.send(embed=discord.Embed(description="❌ You are already in an active casino game!", color=discord.Color.red()), ephemeral=True)
            
        valid, msg = self.check_bet(uid, bet)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        self.active_gamblers.add(uid)
        db["economy"][uid] -= bet
        save_db(db)

        try:
            embed = discord.Embed(title="🎰 Habibi Slots", description="**Spinning...**\n\n🟦 | 🟦 | 🟦", color=discord.Color.gold())
            embed.set_image(url=get_gif("slots_spin"))
            msg = await ctx.send(embed=embed)
            
            await asyncio.sleep(0.8)
            
            symbols = ['🍎', '🍒', '🍇', '🔔', '💎', '7️⃣']
            weights = [35, 25, 20, 10, 8, 2]
            
            s1 = random.choices(symbols, weights=weights, k=1)[0]
            s2 = random.choices(symbols, weights=weights, k=1)[0]
            s3 = random.choices(symbols, weights=weights, k=1)[0]
            
            result_str = f"**[ {s1} | {s2} | {s3} ]**"
            
            if s1 == s2 == s3: 
                multiplier = 5 if s1 != '7️⃣' else 50
                winnings = bet * multiplier
                db["economy"][uid] += winnings
                save_db(db)
                
                e = discord.Embed(title="🎰 JACKPOT!", description=f"{result_str}\n\n🎉 **Massive Win!** You won **{winnings:,} 🪙**! ({multiplier}x)", color=discord.Color.green())
                e.set_image(url=get_gif("slots_jackpot" if multiplier == 50 else "slots_win"))
                
            elif s1 == s2 or s2 == s3 or s1 == s3: 
                winnings = int(bet * 1.5)
                db["economy"][uid] += winnings
                save_db(db)
                
                e = discord.Embed(title="🎰 Winner!", description=f"{result_str}\n\n💵 You matched 2 and won **{winnings:,} 🪙**! (1.5x)", color=discord.Color.gold())
                e.set_image(url=get_gif("slots_win"))
                
            else: 
                e = discord.Embed(title="🎰 Busted!", description=f"{result_str}\n\n💀 You lost your bet of **{bet:,} 🪙**.", color=discord.Color.red())
                e.set_image(url=get_gif("slots_lose"))
                
            await msg.edit(embed=e)
        finally:
            self.active_gamblers.discard(uid)


    # ========================================================================
    # COMMAND: /coinflip (EXPLOIT PROOF)
    # ========================================================================
    @commands.hybrid_command(name="coinflip", aliases=["cf"], description="Bet it all on a 50/50 coinflip.")
    async def coinflip(self, ctx, choice: str, bet: int):
        uid = str(ctx.author.id)
        
        if uid in self.active_gamblers:
            return await ctx.send(embed=discord.Embed(description="❌ You are already in an active casino game!", color=discord.Color.red()), ephemeral=True)
        
        choice = choice.lower()
        if choice not in ["heads", "tails", "h", "t"]:
            return await ctx.send(embed=discord.Embed(description="❌ You must choose either `heads` or `tails`.", color=discord.Color.red()))
            
        if choice == 'h': choice = 'heads'
        if choice == 't': choice = 'tails'
            
        valid, msg = self.check_bet(uid, bet)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))
        
        self.active_gamblers.add(uid)
        
        try:
            outcome = random.choice(["heads", "tails"])
            
            if choice == outcome:
                db["economy"][uid] += bet 
                save_db(db)
                embed = discord.Embed(description=f"🪙 **It landed on {outcome.title()}!**\n\n🎉 You won **{bet:,} 🪙**!", color=discord.Color.green())
                embed.set_image(url=get_gif("coinflip_win"))
            else:
                db["economy"][uid] -= bet 
                save_db(db)
                embed = discord.Embed(description=f"🪙 **It landed on {outcome.title()}!**\n\n💀 You lost **{bet:,} 🪙**.", color=discord.Color.red())
                embed.set_image(url=get_gif("coinflip_lose"))
                
            await ctx.send(embed=embed)
        finally:
            self.active_gamblers.discard(uid)

async def setup(bot):
    await bot.add_cog(Casino(bot))
