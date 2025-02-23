import requests
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solana.rpc.core import RPCException




solana_client = Client("https://mainnet.helius-rpc.com/?api-key=590d5e50-292e-414f-abea-5f751424692b")
wallet = Keypair.from_secret_key(bytes(eval(private_key)))


def get_token_mint_address(token_name):
    url= "https://api.jupiter.exchange/v1/tokens"
    response = requests.get(url)
    tokens = response.json()

    for token in tokens['data']:
       if token['symbol'] == token_name:
          return token['mint']      
    return None


def swap_routes(message):
    url= "http://quote-api.jup.ag/v1/quote"
    params= {
        "input": {
           "inputToken": get_token_mint_address(message['token0']['symbol']),
           "outputToken":get_token_mint_address(message['token1']['symbol']),
           "amount" : message.amount   
        }
    }
    response = requests.get(url,params=params)
    if response.status_code == 200:
        return response.json()
    else: 
        print("Error: ", "your wallet isn't connected solana")
        return None

def excute_swap(routes):
    transaction = Transaction()
    if routes and 'data'in routes and 'swap' in routes['data']:
        for instruction in route['data']['swap']['instructions']:
            transaction.add(instruction)

        try:
            response= solana_client.send_transaction(transaction, wallet, opts=TxOpts(skip_preflight=True))
            print(f"Swap successful! Transaction ID: {response}")
        except RPCException as e:
            print(f"Error sending transactions: {e}")
    else:
        print("Error: Invalid swap.")