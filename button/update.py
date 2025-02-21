from pymongo import MongoClient  
import time  
import aiohttp  
import asyncio  
import sys  

# Set the event loop policy for Windows  
if sys.platform == "win32":  
    import asyncio  
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  

mongo_client = MongoClient("mongodb+srv://vanguard951105:F0Y7B0MtjvH1OFbL@cluster0.haemz.mongodb.net/")  
db = mongo_client["IN_Parser"]  
collection = db["migratedtokens"]  

async def fetch_market_cap(session, token_address):  
    url = f"https://pro-api.solscan.io/v2.0/token/meta?address={token_address}"  
    headers = {  
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3Mzg3NDg3ODc2NDUsImVtYWlsIjoiYS5zbWlybm92MTUwODk3QGdtYWlsLmNvbSIsImFjdGlvbiI6InRva2VuLWFwaSIsImFwaVZlcnNpb24iOiJ2MiIsImlhdCI6MTczODc0ODc4N30.heFYyJ5obvzDbe1-ZruuVptCgRX4Hk8HXUcSDSUe7u8"  
    }  
    async with session.get(url, headers=headers) as response:  
        return await response.json()  

async def process_token(token):  
    graduated_time = token["graduated"]  
    current_time_milliseconds = int(time.time() * 1000)  
    seven_days_in_milliseconds = 7 * 24 * 60 * 60 * 1000  

    if (current_time_milliseconds - graduated_time) > seven_days_in_milliseconds:  
        collection.delete_one({"_id": token["_id"]})  
    else:  
        async with aiohttp.ClientSession() as session:  
            data = await fetch_market_cap(session, token['address'])  
            market_cap = data["data"]["market_cap"] if "market_cap" in data["data"] else 0  
            
            if market_cap > token["mATH"]:  
                collection.update_one({"_id": token["_id"]}, {"$set": {"marketcap": market_cap, "mATH": market_cap}})  
                print(f"Updated marketcap for {token['address']} {token['marketcap']} to {market_cap}")  
            else:  
                if token["marketcap"] != market_cap:
                  collection.update_one({"_id": token["_id"]}, {"$set": {"marketcap": market_cap}})  
                  print(f"Updated marketcap for {token['address']} {token['marketcap']} to {market_cap}")  

async def run():  
    tokens = list(collection.find())  
    tasks = []  

    for token in tokens:  
        tasks.append(process_token(token))  

    await asyncio.gather(*tasks)  

while True:
    try:
        asyncio.run(run())
        time.sleep(10)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)