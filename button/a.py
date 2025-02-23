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
import re
import requests
import json

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
    print("sent-message---------->",message_ids)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
     
    user = query.from_user  # Get user from the callback query
    username = user.username or "Unknown"  # Get username here
    user_db = collection.find_one({"username": username})
    
    if query.data == 'trade':  
        if user_db is None: return
        keyboard = [
            [InlineKeyboardButton("Add new target wallet", callback_data='add_new_target_wallet')],
            [InlineKeyboardButton("All target wallet list", callback_data='target_wallet_list')],
            [InlineKeyboardButton("Activate all", callback_data='activate_all')],
            [InlineKeyboardButton("Exclude tokens", callback_data='exclude_tokens')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh_second')],
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
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
        ]  
        reply_markup = InlineKeyboardMarkup(keyboard)  
        await query.edit_message_reply_markup(reply_markup=reply_markup)  
        await query.message.reply_text("To connect your wallet, please input your wallet private key.")  
        message_ids[username].append(query.message.message_id)  

    elif query.data == 'change':  
        expecting_private_key[username] = True  
        keyboard = [
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
        ]  
        reply_markup = InlineKeyboardMarkup(keyboard)  
        await query.edit_message_reply_markup(reply_markup=reply_markup)  
        message_ids[username].append(query.message.message_id)  
        sent_message = await query.message.reply_text("To change your wallet, please input your other wallet private key.")  
        message_ids[username].append(sent_message.message_id)  
    
    elif query.data == 'add_new_target_wallet':  
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
            [InlineKeyboardButton(f"Wallet label: {current_wallet.get('wallet_label', '...')}", callback_data='wallet_label')],
            [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}...{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
            [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
            [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
            [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
            [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
            [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
            [InlineKeyboardButton(f"Exclude tokens: {len(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
            [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
            [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
            [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
            [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
            [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
            [InlineKeyboardButton("➕ Create", callback_data='create')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_second'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username].append(query.message.message_id)  
    elif query.data.startswith('edit_'):  
        wallet_name = query.data.split('_')[1] 
        wallet = target_collection.find_one({"username": username, "target_wallet": wallet_name, "added": True})
        # url = f"https://feed-api.cielo.finance/api/v1/{wallet_name}/pnl/total-stats?chains=solana&timeframe=1d"

        # headers = {
        #     "accept": "application/json",
        #     "X-API-KEY": "22e3b1e2-df44-4cbf-8b36-207b80a68ac4"
        # }

        # response = requests.get(url, headers=headers).json()
        # print(response)
        # total_pnl = response['data']['combined_pnl_usd']
        # total_roi = response['data']['combined_roi_percentage']
        # traded = response['data']['tokens_traded']
        total_pnl = 0
        total_roi = 0
        traded = 0

        copy_pnl = 0
        copy_roi = 0
        copy_traded = 0
        message = f"""  
Target Wallet: 
<code>{wallet_name}</code>  
PNL:    {total_pnl:.2f}
ROI:     {total_roi:.2f}
Traded: {traded} 

Copy trade:
PNL:    {copy_pnl:.2f}
ROI:     {copy_roi:.2f}
Traded: {copy_traded}
""" 
        keyboard = [
            [InlineKeyboardButton("Change setting", callback_data=f'change_{wallet_name}')],
            [InlineKeyboardButton("OK", callback_data='back_to_main'), InlineKeyboardButton("Remove", callback_data='Remove')]
        ] 
        reply_markup = InlineKeyboardMarkup(keyboard)  
        await query.message.reply_text(message, reply_markup = reply_markup, parse_mode=ParseMode.HTML) 
        message_ids[username].append(query.message.message_id)  

    elif query.data.startswith('change_'):
        target_wallet = query.data.split('_')[1] 
        target_collection.delete_one({"username": username, "added": False})
        current_wallet = target_collection.find_one({"username": username, "target_wallet": target_wallet, "added": True})
        current_wallet['added'] = False
        target_collection.update_one({"username": username, "target_wallet": target_wallet, "added": True}, {"$set": current_wallet})
        user_db = collection.find_one({"username": username})
        sol_balance = await get_sol_balance(user_db['public_key'])
        message = f"""
*Welcome to copy trade bot `{username}`*

*Your current wallet address:*
    `{user_db['public_key']}`

*Your current balance:*
    `{sol_balance} SOL`"""
        keyboard = [
            [InlineKeyboardButton(f"Wallet label: {current_wallet.get('wallet_label', '-')}", callback_data='wallet_label')],
            [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}...{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
            [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
            [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
            [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
            [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
            [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
            [InlineKeyboardButton(f"Exclude tokens: {len(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
            [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
            [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
            [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
            [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
            [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
            [InlineKeyboardButton("✅ Ok", callback_data='create')],
            [InlineKeyboardButton("Remove", callback_data='target_wallet_list'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        

    elif query.data == 'target_wallet_list':
        target_wallets = target_collection.find({"username": username, "added": True})
        keyboard = []
        index = 1
        for wallet in target_wallets:
            keyboard.append([InlineKeyboardButton(f"{index} : {wallet['target_wallet']}", callback_data=f'edit_{wallet["target_wallet"]}')])
            index += 1
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_second')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username].append(query.message.message_id)

    elif query.data in ['wallet_label', 'target_wallet', 'buy_percentage', 'max_buy', 'min_buy', 'total_invest_sol', 'each_token_buy_times', 'tip', 'trader_tx_max_limit', 'exclude_tokens', 'max_marketcap', 'min_marketcap', 'auto_retry', 'buy_slippage', 'sell_slippage', 'buy_gas_fee', 'sell_gas_fee']:
        editing_field[username] = query.data
        await query.message.reply_text(f"Please enter the new value for {query.data.replace('_', ' ').title()}:")
        message_ids[username].append(query.message.message_id)
    elif query.data == 'create':  
        current_wallet = target_collection.find_one({"added": False, "username": username})
        if current_wallet['target_wallet'] == "" or current_wallet['wallet_label'] == "-":
            await query.message.reply_text("Please input required fields (target wallet & wallet label)")
            return
        editing_field['added'] = True
        target_collection.update_one({"username": username, "added": False}, {"$set": editing_field})
        back_trade(query)

    elif query.data == 'refresh_second':
        user_db = collection.find_one({"username": username})
        sol_balance = await get_sol_balance(user_db['public_key'])
        message = f"""
*Welcome to copy trade bot `{username}`*

*Your current wallet address:*
    `{user_db['public_key']}`

*Your current balance:*
    `{sol_balance} SOL`"""
        keyboard = [
            [InlineKeyboardButton("Add new target wallet", callback_data='add_new_target_wallet')],
            [InlineKeyboardButton("All target wallet list", callback_data='target_wallet_list')],
            [InlineKeyboardButton("Activate all", callback_data='activate_all')],
            [InlineKeyboardButton("Exclude tokens", callback_data='exclude_tokens')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh_second')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        message_ids[username].append(query.message.message_id)

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
            [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}...{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
            [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
            [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
            [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
            [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
            [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
            [InlineKeyboardButton(f"Exclude tokens: {len(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
            [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
            [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
            [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
            [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
            [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
            [InlineKeyboardButton("➕ Create", callback_data='create')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_second'), InlineKeyboardButton("Refresh", callback_data='refresh')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)

    elif query.data == 'back_to_second':  
        keyboard = [
            [InlineKeyboardButton("Add new target wallet", callback_data='add_new_target_wallet')],
            [InlineKeyboardButton("All target wallet list", callback_data='target_wallet_list')],
            [InlineKeyboardButton("Activate all", callback_data='activate_all')],
            [InlineKeyboardButton("Exclude tokens", callback_data='exclude_tokens')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main'), InlineKeyboardButton("Refresh", callback_data='refresh_second')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        message_ids[username].append(query.message.message_id)  

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
        [InlineKeyboardButton(f"Target wallet: {current_wallet.get('target_wallet', '-')[:5]}...{current_wallet.get('target_wallet', '-')[-5:]}",callback_data='target_wallet')],
        [InlineKeyboardButton(f"Buy percentage: {current_wallet.get('buy_percentage', 0)}%", callback_data='buy_percentage')],
        [InlineKeyboardButton(f"Max Buy: {current_wallet.get('max_buy', 0)}", callback_data='max_buy'), InlineKeyboardButton(f"Min Buy: {current_wallet.get('min_buy', 0)}", callback_data='min_buy')],
        [InlineKeyboardButton(f"Total invest: {current_wallet.get('total_invest_sol', 0)} sol", callback_data='total_invest_sol')],
        [InlineKeyboardButton(f"Each Token Buy times: {current_wallet.get('each_token_buy_times', 0)}", callback_data='each_token_buy_times')],
        [InlineKeyboardButton(f"Trader's Tx max limit: {current_wallet.get('trader_tx_max_limit', 0)}", callback_data='trader_tx_max_limit')],
        [InlineKeyboardButton(f"Exclude tokens: {len(current_wallet.get('exclude_tokens', []))}", callback_data='exclude_tokens')],
        [InlineKeyboardButton(f"Max MC: {current_wallet.get('max_marketcap', 0)}", callback_data='max_mc'), InlineKeyboardButton(f"Min MC: {current_wallet.get('min_marketcap', 0)}", callback_data='min_mc')],
        [InlineKeyboardButton(f"Auto Retry: {current_wallet.get('auto_retry_times', 0)}", callback_data='auto_retry')],
        [InlineKeyboardButton(f"Buy Slippage: {current_wallet.get('buy_slippage', 0)}%", callback_data='buy_slippage'), InlineKeyboardButton(f"Sell Slippage: {current_wallet.get('sell_slippage', 0)}%", callback_data='sell_slippage')],
        [InlineKeyboardButton(f"Jito Dynamic Tip: {current_wallet.get('tip', 0)}%", callback_data='tip')],
        [InlineKeyboardButton(f"Buy Gas Fee: {current_wallet.get('buy_gas_fee', 0)} sol", callback_data='buy_gas_fee'), InlineKeyboardButton(f"Sell Gas Fee: {current_wallet.get('sell_gas_fee', 0)} sol", callback_data='sell_gas_fee')],
        [InlineKeyboardButton("➕ Create", callback_data='create')],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_second'), InlineKeyboardButton("Refresh", callback_data='refresh')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    await delete_previous_messages(update, context, username) 
    message_ids[username].append(update.message.message_id)


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
        # Send the warning message  
        await context.bot.send_message(chat_id=update.effective_chat.id, text=warning_message)
        print(f"Error deriving Solana public key: {e}")  
        sent_message = await update.message.reply_text("Invalid Solana private key. Please try again.")  
        message_ids[username].append(sent_message.message_id)  

        return  
    try:  
        sol_balance = await get_sol_balance(sol_public_key_str)  
    except Exception as e:  
        print(f"Error fetching SOL balance: {e}")  
        sent_message = await update.message.reply_text("Error fetching SOL balance. Please try again.")  
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
    `{sol_balance} SOL`"""  
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
        if field == "wallet_label":
            exist_wallet_wallet = target_collection.find_one({"username": username, "wallet_label": value})
            if exist_wallet_wallet:
                await update.message.reply_text("This wallet label already exists.")
                return

        if field == "target_wallet" or field == "exclude_tokens":
            if field == "target_wallet":
                exist_wallet = target_collection.find_one({"username": username, "added": True, "target_wallet": value})
                if exist_wallet:
                    await update.message.reply_text("This wallet address already exists in target wallet list.")
                    return
            if len(value) != 43 and len(value) != 44:  
                await update.message.reply_text("Please enter valid target wallet address.")
                return  
            base58_pattern = r'^[A-HJ-NP-Za-km-z1-9]+$'  
            if re.match(base58_pattern, value) is None:  
                await update.message.reply_text("Please enter valid target wallet address.")
                return 

        target_collection.update_one(
            {"username": username, "added": False},
            {"$set": {field: value}}
        )
        await back_trade(update, context)

async def derive_public_key(private_key: str) -> str:
    print("private_key", private_key)  
    private_key_bytes = base58.b58decode(private_key) 
    if len(private_key_bytes) != 64:  
        raise ValueError("Invalid private key length for Solana.")  
    sol_keypair = Keypair.from_bytes(private_key_bytes)  
    # sol_public_key = sol_keypair.public_key
    sol_public_key = str(sol_keypair.pubkey()) # Convert PublicKey to base58
 # Convert PublicKey to string  
    print(f"Derived Solana public key: {sol_public_key}")  
    return sol_public_key

async def get_sol_balance(public_key: str) -> float:  
        
        sol_client = Client("https://mainnet.helius-rpc.com/?api-key=590d5e50-292e-414f-abea-5f751424692b")  
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
                print("")  
        message_ids[username] = []  

if __name__ == '__main__':  
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  

    application = ApplicationBuilder().token(TOKEN).build()  

    application.add_handler(CommandHandler("start", start))  
    application.add_handler(CallbackQueryHandler(button))  
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    asyncio.run(application.run_polling())