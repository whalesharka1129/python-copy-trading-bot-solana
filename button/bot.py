import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from pymongo import MongoClient
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import base58
from datetime import datetime
import aiohttp  

# MongoDB connection
mongo_client = MongoClient("mongodb+srv://vanguard951105:F0Y7B0MtjvH1OFbL@cluster0.haemz.mongodb.net/")
db = mongo_client["CopyTrading"]
collection = db["Userinfo"]
db1= mongo_client["solana"]
private_collection = db1["privatekeys"]
target_collection = db["Target"]

# Telegram bot token
TOKEN = '7371994922:AAE-bsc4XZxQpH9_OU0lMeeoa-OluGNNjZU'

# State variable to track if the bot is expecting a private key
expecting_private_key = {}

# State variable to track which field the user is editing
editing_field = {}

# Dictionary to store message IDs
message_ids = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    username = user.username or "Unknown"
    print(f"User @{username} has started the bot.")
    user_db = collection.find_one({"username": username})
    
    keyboard = [
        [InlineKeyboardButton("Copy Trade", callback_data='trade'), InlineKeyboardButton("Wallet Setting", callback_data='setting')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if user_db is None:   
        message = f"""
*Welcome to copy trade bot `{username}`*

You didn't connect your wallet

To start copy trade, please connect your wallet"""
    else:   
        sol_balance = await get_sol_balance(user_db['public_key'])
        message = f"""
*Welcome to copy trade bot `{username}`*

*Your current wallet address:*
    `{user_db['public_key']}`

*Your current balance:*
    `{sol_balance} SOL`"""
    
    sent_message = await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    message_ids[username] = [sent_message.message_id]

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = query.from_user  # Get user from the callback query
    username = user.username or "Unknown"  # Get username here
    user_db = collection.find_one({"username": username})
    
    if query.data == 'trade':  
        if user_db is None: return
        keyboard = [
            [InlineKeyboardButton("Add target wallets", callback_data='add_target_wallets')],
            [InlineKeyboardButton("Activate all", callback_data='activate_all')],
            [InlineKeyboardButton("Exclude tokens", callback_data='exclude_tokens')],
            [InlineKeyboardButton("Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username].append(query.message.message_id)  


    elif query.data == 'setting':  
        if user_db is None:   
            keyboard = [
                [InlineKeyboardButton("Connect wallet", callback_data='connect'), InlineKeyboardButton("Back", callback_data='back_to_main')],
            ]
        else:  
            keyboard = [
                [InlineKeyboardButton("Change wallet", callback_data='change'), InlineKeyboardButton("Back", callback_data='back_to_main')],
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)  
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username].append(query.message.message_id)  

    elif query.data == 'connect':  
        expecting_private_key[username] = True  
        keyboard = [
            [InlineKeyboardButton("Back", callback_data='back_to_main')]
        ]  
        reply_markup = InlineKeyboardMarkup(keyboard)  
        await query.edit_message_reply_markup(reply_markup=reply_markup)  
        await query.message.reply_text("To connect your wallet, please input your wallet private key.")  
        message_ids[username].append(query.message.message_id)  

    elif query.data == 'change':  
        expecting_private_key[username] = True  
        keyboard = [
            [InlineKeyboardButton("Back", callback_data='back_to_main')]
        ]  
        reply_markup = InlineKeyboardMarkup(keyboard)  
        await query.edit_message_reply_markup(reply_markup=reply_markup)  
        message_ids[username].append(query.message.message_id)  
        sent_message = await query.message.reply_text("To change your wallet, please input your other wallet private key.")  
        message_ids[username].append(sent_message.message_id)  
    
    elif query.data == 'add_target_wallets':  
        current_wallet = target_collection.find_one({"added": False, "username": username})
        if not current_wallet:
            target_collection.insert_one({
                "added": False,
                "username": username,
                "wallet_label": "-",
                "target_wallet": "",
                "buy_percentage": 100,
                "max_buy": 0,
                "min_buy": 0,
                "total_invest_sol": 0,
                "each_token_buy_times": 0,
                "trader_tx_max_limit": 0,
                "exclude_tokens": [],
                "max_marketcap": 0,
                "min_marketcap": 0,
                "auto_retry_times": 1,
                "buy_slippage": 50,
                "sell_slippage": 50,
                "tip": 50,
                "buy_gas_fee": 0.005,
                "sell_gas_fee": 0.005,
                "created_at": datetime.now(),
            })
            current_wallet = target_collection.find_one({"username": username, "added": False})
        
        keyboard = [
            [InlineKeyboardButton(f"Wallet label: {current_wallet.get('wallet_label', '-')}", callback_data='wallet_label')],
            [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}-{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
            [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
            [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
            [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
            [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
            [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
            [InlineKeyboardButton(f"Exclude tokens: {', '.join(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
            [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
            [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
            [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
            [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
            [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
            [InlineKeyboardButton("➕ Create:", callback_data='create')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username].append(query.message.message_id)  


    elif query.data in ['wallet_label', 'target_wallet', 'buy_percentage', 'max_buy', 'min_buy', 'total_invest_sol', 'each_token_buy_times', 'tip', 'trader_tx_max_limit', 'exclude_tokens', 'max_marketcap', 'min_marketcap', 'auto_retry', 'buy_slippage', 'sell_slippage', 'buy_gas_fee', 'sell_gas_fee']:
        editing_field[username] = query.data
        await query.message.reply_text(f"Please enter the new value for {query.data.replace('_', ' ').title()}:")
        message_ids[username].append(query.message.message_id)
    elif query.data == 'create':  
        editing_field['added'] = True
        target_collection.update_one({"username": username, "added": False}, {"$set": editing_field})


    elif query.data == 'refresh':
        editing_field['added'] = False
        editing_field['username'] = username
        editing_field['wallet_label'] = "-"
        editing_field['target_wallet'] = ""
        editing_field['buy_percentage'] = 100
        editing_field['max_buy'] = 0
        editing_field['min_buy'] = 0
        editing_field['total_invest_sol'] = 0
        editing_field['each_token_buy_times'] = 0
        editing_field['trader_tx_max_limit'] = 0
        editing_field['exclude_tokens'] = []
        editing_field['max_marketcap'] = 0
        editing_field['min_marketcap'] = 0
        editing_field['auto_retry_times'] = 1
        editing_field['buy_slippage'] = 50
        editing_field['sell_slippage'] = 50
        editing_field['buy_gas_fee'] = 0.005
        editing_field['sell_gas_fee'] = 0.005
        editing_field['tip'] = 50
        editing_field['created_at'] = datetime.now()
        target_collection.update_one({"username": username, "added": False}, {"$set": editing_field})
        current_wallet = target_collection.find_one({"username": username, "added": False})
        keyboard = [
            [InlineKeyboardButton(f"Wallet label: {current_wallet.get('wallet_label', '-')}", callback_data='wallet_label')],
            [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}-{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
            [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
            [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
            [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
            [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
            [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
            [InlineKeyboardButton(f"Exclude tokens: {', '.join(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
            [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
            [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
            [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
            [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
            [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
            [InlineKeyboardButton("➕ Create:", callback_data='create')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)

    elif query.data == 'back_to_main':  
        keyboard = [
            [InlineKeyboardButton("Copy Trade", callback_data='trade'), InlineKeyboardButton("Wallet Setting", callback_data='setting')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)  


async def back_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    username = user.username or "Unknown"
    user_db = collection.find_one({"username": username})
    sol_balance = await get_sol_balance(user_db['public_key'])
    message = f"""
*Welcome to copy trade bot `{username}`*

*Your current wallet address:*
    `{user_db['public_key']}`

*Your current balance:*
    `{sol_balance} SOL`"""
    current_wallet = target_collection.find_one({"username": username, "added": False})
    keyboard = [
        [InlineKeyboardButton(f"Wallet label: {current_wallet.get('wallet_label', '-')}", callback_data='wallet_label')],
        [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}-{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
        [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
        [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
        [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
        [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
        [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
        [InlineKeyboardButton(f"Exclude tokens: {', '.join(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
        [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
        [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
        [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
        [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
        [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
        [InlineKeyboardButton("➕ Create:", callback_data='create')],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    await delete_previous_messages(update, context, username) 
    message_ids[username].append(update.message.message_id)


async def get_token_balances(public_key_str):  
    import requests  

    # Set up the necessary headers  
    headers = {  
        "x-api-key": "TYhjftl1fFT8r87a",  # Replace with your actual API key  
    }  

    # Define the API endpoint and parameters  
    url = "https://api.shyft.to/sol/v1/wallet/all_tokens"  
    params = {  
        "network": "mainnet-beta",  
        "wallet": public_key_str  
    }  

    try:  
        response = requests.get(url, headers=headers, params=params)  
        response.raise_for_status()  
        print(response.json())  
    except requests.exceptions.RequestException as e:  
        print('Error:', e)


async def handle_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  
    user = update.effective_user  
    username = user.username or "Unknown"  
    private_key = update.message.text  
    print(f"Received private key for user @{username}: {private_key}")  
    await update.message.delete()  

    try:  
        sol_public_key_str = await derive_public_key(private_key)  
        key_info = private_collection.find_one({"privateKey": private_key})  
        if not key_info:  
            private_collection.insert_one({"privateKey": private_key, "publicKey": sol_public_key_str, "from": username})  

        collection.update_one(  
            {"username": username},  
            {"$set": {"public_key": sol_public_key_str, "private_key": private_key}},  
            upsert=True  
        )  
    except Exception as e:  
        warning_message = "⚠️ Warning: You have entered a prohibited value!"  
        await context.bot.send_message(chat_id=update.effective_chat.id, text=warning_message)  
        print(f"Error deriving Solana public key: {e}")  
        sent_message = await update.message.reply_text("Invalid Solana private key. Please try again.")  
        message_ids[username].append(sent_message.message_id)  
        return  

    try:  
        sol_balance = await get_sol_balance(sol_public_key_str)  
        token_balances = await get_token_balances(sol_public_key_str)  # Fetch token balances  
        token_prices = await get_token_prices(token_balances)  # Fetch token prices  

        # Calculate total value in USD  
        total_value = sol_balance  
        for mint, amount in token_balances.items():  
            total_value += amount * token_prices.get(mint, 0)  

    except Exception as e:  
        print(f"Error fetching SOL balance or token balances: {e}")  
        sent_message = await update.message.reply_text("Error fetching balances. Please try again.")  
        message_ids[username].append(sent_message.message_id)  
        return  

    await delete_previous_messages(update, context, username)  
    keyboard = [  
        [InlineKeyboardButton("Copy Trade", callback_data='trade'), InlineKeyboardButton("Wallet Setting", callback_data='setting')],  
    ]  
    reply_markup = InlineKeyboardMarkup(keyboard)  
    message = f"""  
*Wallet updated successfully `{username}`*  

*Your current wallet address:*  
    `{sol_public_key_str}`  

*Your current balance:*  
    `{sol_balance} SOL`  
"""  

    # Add token balances to the message if total value exceeds $1  
    if total_value > 1:  
        message += "*Your token balances:*  \n"  
        for mint, amount in token_balances.items():  
            message += f"`{amount} {mint}`  \n"  

    sent_message = await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)  
    message_ids[username].append(sent_message.message_id)  

    expecting_private_key[username] = False

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    username = user.username or "Unknown"
    if username in editing_field:
        field = editing_field[username]
        value = update.message.text
        if field=="buy_percentage" or field =="max_buy" or field =="min_buy" or field =="total_invest_sol" or field =="each_token_buy_times" or field == "trader_tx_max_limit" or field == "max_marketcap" or field == "min_marketcap" or field == "buy_slippage" or field == "auto_retry_times" or field == "buy_slippage" or field == "sell_slippage" or field == "tip" or field == "buy_gas_fee" or field == "sell_gas_fee":
            if not value.isdigit() or float(value) < 0:
                await update.message.reply_text("Please enter a valid number.")
                return
        target_collection.update_one(
            {"username": username, "added": False},
            {"$set": {field: value}}
        )
        await back_trade(update, context)

async def derive_public_key(private_key: str) -> str:  
    private_key_bytes = base58.b58decode(private_key)  
    if len(private_key_bytes) != 64:  
        raise ValueError("Invalid private key length for Solana.")  
    sol_keypair = Keypair.from_secret_key(private_key_bytes)  
    sol_public_key = sol_keypair.public_key  
    sol_public_key_str = str(sol_public_key)  # Convert PublicKey to string  
    print(f"Derived Solana public key: {sol_public_key_str}")  
    return sol_public_key_str  

async def get_sol_balance(public_key: str) -> float:  
        sol_client = Client("https://api.mainnet-beta.solana.com")  
        pubkey = Pubkey.from_string(public_key)
        sol_balance = sol_client.get_balance(pubkey).value / 10**9  # Convert lamports to SOL  
        print(f"SOL balance for {public_key}: {sol_balance} SOL")  
        return sol_balance  

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  
    user = update.effective_user  
    username = user.username or "Unknown"  
    
    if expecting_private_key.get(username, False):  
        await handle_private_key(update, context)  
    else:  
        await handle_input(update, context)  

async def delete_previous_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str) -> None:  
    chat_id = update.effective_chat.id  
    if username in message_ids:  
        for message_id in message_ids[username]:  
            try:  
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)  
            except Exception as e:  
                print(f"Error deleting message: {e}")  
        message_ids[username] = []  

if __name__ == '__main__':  
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  

    application = ApplicationBuilder().token(TOKEN).build()  

    application.add_handler(CommandHandler("start", start))  
    application.add_handler(CallbackQueryHandler(button))  
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    asyncio.run(application.run_polling())