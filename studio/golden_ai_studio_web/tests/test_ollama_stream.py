"""Test Ollama streaming directly."""
import asyncio
from ollama import chat

async def test():
    messages = [
        {"role": "system", "content": "Voce e o Jarvis. Responda em portugues."},
        {"role": "user", "content": "Ola"}
    ]

    print("Testing Ollama streaming...")
    try:
        response = chat(model="qwen2.5-coder:14b", messages=messages, stream=True)
        print(f"Response type: {type(response)}")
        count = 0
        for chunk in response:
            content = chunk.get("message", {}).get("content", "")
            if content:
                print(f"Token: {content[:30]}...")
                count += 1
                if count >= 5:
                    break
        print(f"Total tokens received: {count}")
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(test())
