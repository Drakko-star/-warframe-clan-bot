"""
Bot Discord - Économie de Clan Warframe (v2 - avec images et pagination)
"""

import json
import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.environ.get("DISCORD_TOKEN")
ADMIN_ROLE_NAME = os.environ.get("ADMIN_ROLE_NAME", "Officier")

RESSOURCES_FILE = "ressources.json"
BOUTIQUE_FILE = "boutique.json"
SOLDES_FILE = "soldes.json"
HISTORIQUE_FILE = "historique.json"
EN_ATTENTE_FILE = "en_attente.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def charger_json(fichier, defaut):
    if not os.path.exists(fichier):
        sauver_json(fichier, defaut)
        return defaut
    with open(fichier, "r", encoding="utf-8") as f:
        return json.load(f)


def sauver_json(fichier, data):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_soldes():
    return charger_json(SOLDES_FILE, {})


def get_historique():
    return charger_json(HISTORIQUE_FILE, [])


def get_en_attente():
    return charger_json(EN_ATTENTE_FILE, {"dons": [], "achats": []})


def get_ressources():
    return charger_json(RESSOURCES_FILE, {"tiers": []})


def get_boutique():
    return charger_json(BOUTIQUE_FILE, {"categories": [], "conversion_points_vers_plat": {}})


def ajouter_historique(type_action, user_id, user_name, detail, points):
    hist = get_historique()
    hist.append({
        "date": datetime.utcnow().isoformat(),
        "type": type_action,
        "user_id": user_id,
        "user_name": user_name,
        "detail": detail,
        "points": points,
    })
    sauver_json(HISTORIQUE_FILE, hist)


def est_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    return any(role.name == ADMIN_ROLE_NAME for role in interaction.user.roles)


def trouver_lot(nom_ressource: str):
    data = get_ressources()
    nom_ressource = nom_ressource.strip().lower()
    for tier in data["tiers"]:
        for lot in tier["lots"]:
            if lot["ressource"].lower() == nom_ressource:
                return lot
    return None


def trouver_item_boutique(nom_item: str):
    data = get_boutique()
    nom_item = nom_item.strip().lower()
    for cat in data["categories"]:
        for item in cat["items"]:
            if item["nom"].lower() == nom_item:
                return cat, item
    return None, None


def embed_pour_tier_ressource(tier: dict, index: int, total: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"📦 {tier['nom']}",
        description="Quantité requise par lot → points crédités",
        color=discord.Color.blue(),
    )
    for lot in tier["lots"]:
        embed.add_field(
            name=lot["ressource"],
            value=f"{lot['quantite']} unités → **{lot['points']} pts**",
            inline=True,
        )
    if tier["lots"] and tier["lots"][0].get("image"):
        embed.set_thumbnail(url=tier["lots"][0]["image"])
    embed.set_footer(text=f"Tier {index + 1}/{total} • Utilise les boutons pour naviguer")
    return embed


def embed_pour_categorie_boutique(cat: dict, index: int, total: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🛒 {cat['nom']}",
        description="Échange tes points contre ces récompenses",
        color=discord.Color.gold(),
    )
    for item in cat["items"]:
        stock_txt = "∞" if item["stock"] == -1 else str(item["stock"])
        embed.add_field(
            name=item["nom"],
            value=f"**{item['points']} pts** (stock: {stock_txt})",
            inline=True,
        )
    if cat["items"] and cat["items"][0].get("image"):
        embed.set_thumbnail(url=cat["items"][0]["image"])
    embed.set_footer(text=f"Catégorie {index + 1}/{total} • Utilise les boutons pour naviguer")
    return embed


class PaginationView(discord.ui.View):
    def __init__(self, pages_data: list, builder_fn, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.pages_data = pages_data
        self.builder_fn = builder_fn
        self.index = 0
        self._update_buttons()

    def _update_buttons(self):
        self.precedent.disabled = self.index == 0
        self.suivant.disabled = self.index >= len(self.pages_data) - 1

    def embed_actuel(self) -> discord.Embed:
        return self.builder_fn(self.pages_data[self.index], self.index, len(self.pages_data))

    @discord.ui.button(label="◀ Précédent", style=discord.ButtonStyle.secondary)
    async def precedent(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed_actuel(), view=self)

    @discord.ui.button(label="Suivant ▶", style=discord.ButtonStyle.secondary)
    async def suivant(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.pages_data) - 1, self.index + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed_actuel(), view=self)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Connecté en tant que {bot.user} - {len(bot.guilds)} serveur(s)")


@bot.tree.command(name="lots", description="Affiche les lots de ressources et leur prix en points (avec images)")
async def lots(interaction: discord.Interaction):
    data = get_ressources()
    tiers = data["tiers"]
    if not tiers:
        await interaction.response.send_message("Aucun barème configuré.", ephemeral=True)
        return

    view = PaginationView(tiers, embed_pour_tier_ressource)
    await interaction.response.send_message(embed=view.embed_actuel(), view=view)


@bot.tree.command(name="don", description="Déclare un don de ressources (en attente de validation)")
@app_commands.describe(
    ressource="Nom de la ressource (ex: Neurodes)",
    quantite="Quantité totale donnée",
)
async def don(interaction: discord.Interaction, ressource: str, quantite: int):
    lot = trouver_lot(ressource)
    if lot is None:
        await interaction.response.send_message(
            f"❌ Ressource `{ressource}` introuvable dans le barème. Utilise `/lots` pour voir la liste.",
            ephemeral=True,
        )
        return

    if quantite <= 0:
        await interaction.response.send_message("❌ La quantité doit être positive.", ephemeral=True)
        return

    nb_lots = quantite // lot["quantite"]
    if nb_lots <= 0:
        await interaction.response.send_message(
            f"❌ Il faut au moins {lot['quantite']} unités de {lot['ressource']} pour 1 lot. "
            f"Tu en as déclaré {quantite}.",
            ephemeral=True,
        )
        return

    points_calcules = nb_lots * lot["points"]
    reste = quantite - (nb_lots * lot["quantite"])

    en_attente = get_en_attente()
    don_id = len(en_attente["dons"]) + 1
    en_attente["dons"].append({
        "id": don_id,
        "user_id": interaction.user.id,
        "user_name": str(interaction.user),
        "ressource": lot["ressource"],
        "quantite": quantite,
        "nb_lots": nb_lots,
        "points": points_calcules,
        "statut": "en_attente",
    })
    sauver_json(EN_ATTENTE_FILE, en_attente)

    embed = discord.Embed(
        title="📥 Don déclaré",
        description=f"{interaction.user.mention} a déclaré un don",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Ressource", value=f"{quantite}x {lot['ressource']}", inline=True)
    embed.add_field(name="Lots complets", value=str(nb_lots), inline=True)
    embed.add_field(name="Points en attente", value=f"**{points_calcules} pts**", inline=True)
    if lot.get("image"):
        embed.set_thumbnail(url=lot["image"])
    if reste > 0:
        embed.add_field(name="⚠️ Reste non compté", value=f"{reste} unités", inline=False)
    embed.set_footer(text=f"ID demande: {don_id} • En attente de validation par un officier (/valider_don id:{don_id})")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="valider_don", description="[Officier] Valide un don en attente et crédite les points")
@app_commands.describe(id="ID de la demande de don")
async def valider_don(interaction: discord.Interaction, id: int):
    if not est_admin(interaction):
        await interaction.response.send_message("❌ Réservé aux officiers du clan.", ephemeral=True)
        return

    en_attente = get_en_attente()
    demande = next((d for d in en_attente["dons"] if d["id"] == id and d["statut"] == "en_attente"), None)
    if demande is None:
        await interaction.response.send_message(f"❌ Aucune demande de don en attente avec l'ID `{id}`.", ephemeral=True)
        return

    soldes = get_soldes()
    uid = str(demande["user_id"])
    soldes[uid] = soldes.get(uid, 0) + demande["points"]
    sauver_json(SOLDES_FILE, soldes)

    demande["statut"] = "valide"
    sauver_json(EN_ATTENTE_FILE, en_attente)

    ajouter_historique("don", demande["user_id"], demande["user_name"],
                        f"{demande['quantite']}x {demande['ressource']}", demande["points"])

    await interaction.response.send_message(
        f"✅ Don `{id}` validé : **{demande['points']} points** crédités à {demande['user_name']} "
        f"(nouveau solde : {soldes[uid]} pts)."
    )


@bot.tree.command(name="refuser_don", description="[Officier] Refuse un don en attente")
@app_commands.describe(id="ID de la demande de don", raison="Raison du refus (optionnel)")
async def refuser_don(interaction: discord.Interaction, id: int, raison: str = ""):
    if not est_admin(interaction):
        await interaction.response.send_message("❌ Réservé aux officiers du clan.", ephemeral=True)
        return

    en_attente = get_en_attente()
    demande = next((d for d in en_attente["dons"] if d["id"] == id and d["statut"] == "en_attente"), None)
    if demande is None:
        await interaction.response.send_message(f"❌ Aucune demande de don en attente avec l'ID `{id}`.", ephemeral=True)
        return

    demande["statut"] = "refuse"
    sauver_json(EN_ATTENTE_FILE, en_attente)

    msg = f"🚫 Don `{id}` refusé ({demande['user_name']} — {demande['quantite']}x {demande['ressource']})."
    if raison:
        msg += f"\nRaison : {raison}"
    await interaction.response.send_message(msg)


@bot.tree.command(name="boutique", description="Affiche les récompenses disponibles (avec images)")
async def boutique(interaction: discord.Interaction):
    data = get_boutique()
    categories = data["categories"]
    if not categories:
        await interaction.response.send_message("Aucune récompense configurée.", ephemeral=True)
        return

    view = PaginationView(categories, embed_pour_categorie_boutique)
    embed = view.embed_actuel()

    conv = data.get("conversion_points_vers_plat")
    if conv:
        embed.add_field(
            name="💱 Conversion plat",
            value=f"{conv['points']} points → {conv['plat']} plat",
            inline=False,
        )

    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="acheter", description="Demande l'achat d'un item de la boutique avec tes points")
@app_commands.describe(item="Nom exact de l'item (voir /boutique)")
async def acheter(interaction: discord.Interaction, item: str):
    cat, article = trouver_item_boutique(item)
    if article is None:
        await interaction.response.send_message(
            f"❌ Item `{item}` introuvable. Utilise `/boutique` pour voir la liste exacte.",
            ephemeral=True,
        )
        return

    if article["stock"] == 0:
        await interaction.response.send_message(f"❌ `{article['nom']}` est en rupture de stock.", ephemeral=True)
        return

    soldes = get_soldes()
    uid = str(interaction.user.id)
    solde_actuel = soldes.get(uid, 0)

    if solde_actuel < article["points"]:
        await interaction.response.send_message(
            f"❌ Solde insuffisant. Il te faut {article['points']} pts, tu en as {solde_actuel}.",
            ephemeral=True,
        )
        return

    en_attente = get_en_attente()
    achat_id = len(en_attente["achats"]) + 1
    en_attente["achats"].append({
        "id": achat_id,
        "user_id": interaction.user.id,
        "user_name": str(interaction.user),
        "item": article["nom"],
        "points": article["points"],
        "statut": "en_attente",
    })
    sauver_json(EN_ATTENTE_FILE, en_attente)

    embed = discord.Embed(
        title="🛍️ Demande d'achat",
        description=f"{interaction.user.mention} souhaite acheter **{article['nom']}**",
        color=discord.Color.purple(),
    )
    embed.add_field(name="Coût", value=f"{article['points']} pts", inline=True)
    if article.get("image"):
        embed.set_thumbnail(url=article["image"])
    embed.set_footer(text=f"ID demande: {achat_id} • En attente de validation (/valider_achat id:{achat_id})")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="valider_achat", description="[Officier] Valide un achat, débite les points et le stock")
@app_commands.describe(id="ID de la demande d'achat")
async def valider_achat(interaction: discord.Interaction, id: int):
    if not est_admin(interaction):
        await interaction.response.send_message("❌ Réservé aux officiers du clan.", ephemeral=True)
        return

    en_attente = get_en_attente()
    demande = next((a for a in en_attente["achats"] if a["id"] == id and a["statut"] == "en_attente"), None)
    if demande is None:
        await interaction.response.send_message(f"❌ Aucune demande d'achat en attente avec l'ID `{id}`.", ephemeral=True)
        return

    soldes = get_soldes()
    uid = str(demande["user_id"])
    solde_actuel = soldes.get(uid, 0)

    if solde_actuel < demande["points"]:
        await interaction.response.send_message(
            f"❌ {demande['user_name']} n'a plus assez de points (solde actuel : {solde_actuel}).",
            ephemeral=True,
        )
        return

    soldes[uid] = solde_actuel - demande["points"]
    sauver_json(SOLDES_FILE, soldes)

    boutique_data = get_boutique()
    for cat in boutique_data["categories"]:
        for article in cat["items"]:
            if article["nom"] == demande["item"] and article["stock"] != -1:
                article["stock"] = max(0, article["stock"] - 1)
    sauver_json(BOUTIQUE_FILE, boutique_data)

    demande["statut"] = "valide"
    sauver_json(EN_ATTENTE_FILE, en_attente)

    ajouter_historique("achat", demande["user_id"], demande["user_name"], demande["item"], -demande["points"])

    await interaction.response.send_message(
        f"✅ Achat `{id}` validé : **{demande['item']}** débité ({demande['points']} pts) pour {demande['user_name']}.\n"
        f"📦 N'oublie pas de livrer l'item en jeu (trade manuel) !"
    )


@bot.tree.command(name="refuser_achat", description="[Officier] Refuse une demande d'achat")
@app_commands.describe(id="ID de la demande d'achat", raison="Raison du refus (optionnel)")
async def refuser_achat(interaction: discord.Interaction, id: int, raison: str = ""):
    if not est_admin(interaction):
        await interaction.response.send_message("❌ Réservé aux officiers du clan.", ephemeral=True)
        return

    en_attente = get_en_attente()
    demande = next((a for a in en_attente["achats"] if a["id"] == id and a["statut"] == "en_attente"), None)
    if demande is None:
        await interaction.response.send_message(f"❌ Aucune demande d'achat en attente avec l'ID `{id}`.", ephemeral=True)
        return

    demande["statut"] = "refuse"
    sauver_json(EN_ATTENTE_FILE, en_attente)

    msg = f"🚫 Achat `{id}` refusé ({demande['user_name']} — {demande['item']})."
    if raison:
        msg += f"\nRaison : {raison}"
    await interaction.response.send_message(msg)


@bot.tree.command(name="solde", description="Affiche ton solde de points (ou celui d'un autre membre)")
@app_commands.describe(membre="Membre à consulter (optionnel, toi par défaut)")
async def solde(interaction: discord.Interaction, membre: discord.Member = None):
    cible = membre or interaction.user
    soldes = get_soldes()
    pts = soldes.get(str(cible.id), 0)
    await interaction.response.send_message(f"💰 **{cible.display_name}** : {pts} points")


@bot.tree.command(name="classement", description="Top contributeurs du clan")
async def classement(interaction: discord.Interaction):
    soldes = get_soldes()
    if not soldes:
        await interaction.response.send_message("Aucune donnée pour le moment.")
        return

    classement_trie = sorted(soldes.items(), key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Classement du clan", color=discord.Color.purple())
    lignes = []
    for i, (uid, pts) in enumerate(classement_trie, start=1):
        membre = interaction.guild.get_member(int(uid))
        nom = membre.display_name if membre else f"Inconnu ({uid})"
        lignes.append(f"{i}. **{nom}** — {pts} pts")
    embed.description = "\n".join(lignes)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajouter_points", description="[Officier] Ajuste manuellement le solde de points d'un membre")
@app_commands.describe(membre="Membre concerné", points="Nombre de points à ajouter (négatif pour retirer)", raison="Raison de l'ajustement")
async def ajouter_points(interaction: discord.Interaction, membre: discord.Member, points: int, raison: str = "Ajustement manuel"):
    if not est_admin(interaction):
        await interaction.response.send_message("❌ Réservé aux officiers du clan.", ephemeral=True)
        return

    soldes = get_soldes()
    uid = str(membre.id)
    soldes[uid] = soldes.get(uid, 0) + points
    sauver_json(SOLDES_FILE, soldes)

    ajouter_historique("ajustement", membre.id, str(membre), raison, points)

    await interaction.response.send_message(
        f"✅ {points:+d} points pour {membre.display_name} ({raison}). Nouveau solde : {soldes[uid]} pts."
    )


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("La variable d'environnement DISCORD_TOKEN n'est pas définie.")
    bot.run(TOKEN)
