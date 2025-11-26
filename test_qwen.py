from openai import OpenAI

def main():
    client = OpenAI(
        base_url="http://localhost:8000/v1",
        api_key="EMPTY"   # vLLM doesn't require a key, but the client does
    )

    prompt = "Explain how stars are formed."

    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Instruct-2507",  # match your folder name exactly
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200
    )

    # Correct way to access message text
    print("\nAssistant Response:\n")
    print(response.choices[0].message.content)

if __name__ == "__main__":
    main()
