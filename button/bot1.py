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

# MongoDB connection
mongo_client = MongoClient("mongodb+srv://vanguard951105:F0Y7B0MtjvH1OFbL@cluster0.haemz.mongodb.net/")
db = mongo_client["CopyTrading"]
collection = db["Userinfo"]
target_collection = db["Target"]

# Telegram bot token
TOKEN = '7371994922:AAE-bsc4XZxQpH9_OU0lMeeoa-OluGNNjZU'

# State variable to track if the bot is expecting a private key
expecting_private_key = {}

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
        message_ids[username] = [query.message.message_id]

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
        # Fetch user's target wallets from the database
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
                "slippage": 50,
                "buy_gas_fee": 0.005,
                "sell_gas_fee": 0.005,
                "created_at": datetime.now(),
            })
            current_wallet = target_collection.find_one({"username": username})
        
        # Create dynamic buttons based on the fetched data
        keyboard = [
            [InlineKeyboardButton(f"Wallet label: {current_wallet.get('wallet_label', '-')}", callback_data='wallet_label')],
            [InlineKeyboardButton(f"Target wallet: ", callback_data='target_wallet')],
            [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
            [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
            [InlineKeyboardButton(f"Total invest Sol: {current_wallet.get('total_invest_sol', 0)}", callback_data='total_invest_sol')],
            [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
            [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
            [InlineKeyboardButton(f"Exclude tokens: {', '.join(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
            [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
            [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
            [InlineKeyboardButton(f"Slippage: {current_wallet.get('slippage', 0)}", callback_data='slippage')],
            [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)}", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('buy_gas_fee', 0)}", callback_data='sell_gas_fee')],
            [InlineKeyboardButton("+ Create:", callback_data='create')],
            [InlineKeyboardButton("Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username] = [query.message.message_id]

    elif query.data == 'back':  
        await delete_previous_messages(update, context, username)  
        await start(update, context)  

    elif query.data == 'back_to_main':  
        keyboard = [
            [InlineKeyboardButton("Copy Trade", callback_data='trade'), InlineKeyboardButton("Wallet Setting", callback_data='setting')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)  

    elif query.data == 'refresh':  
        # Handle refresh logic here
        await query.answer(text="Refreshed!", show_alert=True)

async def handle_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  
    user = update.effective_user  
    username = user.username or "Unknown"  
    private_key = update.message.text  
    print(f"Received private key for user @{username}: {private_key}")  
    
    # Delete the private key message for security reasons  
    await update.message.delete()  
    
    # Convert private key to Solana public key  
    try:  
        sol_public_key_str = await derive_public_key(private_key)  
        # Store only the public key in the database  
        collection.update_one(  
            {"username": username},  
            {"$set": {"public_key": sol_public_key_str, "private_key": private_key}},  
            upsert=True  
        )  
    except Exception as e:  
        print(f"Error deriving Solana public key: {e}")  
        sent_message = await update.message.reply_text("Invalid Solana private key. Please try again.")  
        message_ids[username] = [sent_message.message_id]  
        return  
    
    # Get SOL balance  
    try:  
        sol_balance = await get_sol_balance(sol_public_key_str)  
    except Exception as e:  
        print(f"Error fetching SOL balance: {e}")  
        # Send error message  
        sent_message = await update.message.reply_text("Error fetching SOL balance. Please try again.")  
        message_ids[username] = [sent_message.message_id]  
        return  
    
    # Update the message to show the "wallet updated" message  
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
    `{sol_balance} SOL`"""  
    
    sent_message = await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)  
    message_ids[username] = [sent_message.message_id]  

    expecting_private_key[username] = False  

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
    sol_balance = sol_client.get_balance(PublicKey(public_key)).value / 10**9  # Convert lamports to SOL  
    print(f"SOL balance for {public_key}: {sol_balance} SOL")  
    return sol_balance  

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_private_key))  

    asyncio.run(application.run_polling())