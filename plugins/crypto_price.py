"""
Plugin: Preço de Criptomoedas
Busca preços de criptomoedas via API pública.
"""
import json
import urllib.request

name = "crypto_price"
description = "Busca cotação atual de criptomoedas (BTC, ETH, SOL, etc.)"
parameters = {
    "type": "object",
    "properties": {
        "coins": {
            "type": "string",
            "description": "Moedas separadas por vírgula (ex: bitcoin,ethereum,solana)"
        }
    },
    "required": []
}

DEFAULT_COINS = "bitcoin,ethereum,solana"


def execute(args):
    coins = args.get("coins", DEFAULT_COINS)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coins}&vs_currencies=usd&include_24hr_change=true"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/2.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        result = {}
        for coin, info in data.items():
            result[coin] = {
                "price_usd": info.get("usd", 0),
                "change_24h": f"{info.get('usd_24h_change', 0):.2f}%",
            }
        return result

    except Exception as e:
        return {"error": f"Failed to fetch crypto prices: {e}"}
