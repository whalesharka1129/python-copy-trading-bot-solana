from mnemonic import Mnemonic
from eth_account import Account
from web3 import Web3

# Your 12-word mnemonic phrase
mnemonic_phrase = "ocean hidden kidney famous rich season gloom husband spring convince attitude boy"

# Initialize Mnemonic
mnemo = Mnemonic("english")

# Check if the mnemonic is valid
if not mnemo.check(mnemonic_phrase):
    print("Invalid mnemonic phrase.")
else:
    # Enable unaudited HD wallet features
    Account.enable_unaudited_hdwallet_features()

    # Generate seed from mnemonic
    seed = mnemo.to_seed(mnemonic_phrase)

    # Generate private key (using BIP32)
    # Here we derive the first account (m/44'/60'/0'/0/0)
    account = Account.from_mnemonic(mnemonic_phrase)
    print(f"Private Key: {account.key.hex()}")
    # Get the public address
    address = account.address
    print(f"Public Address: {address}")

    # Connect to an Ethereum node (replace with your own node provider)
    web3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID'))

    # Check if connected
    if web3.isConnected():
        # Get the balance of the address
        balance_wei = web3.eth.get_balance(address)
        balance_eth = web3.fromWei(balance_wei, 'ether')
        print(f"Balance of {address}: {balance_eth} ETH")
    else:
        print("Failed to connect to Ethereum node.")
