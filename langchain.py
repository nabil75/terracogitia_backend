from gpt4all import GPT4All


for m in GPT4All.list_models(): 
    print("===============================================================================================================================")
    print(m['filename'])
    print("===============================================================================================================================")
    model = GPT4All(m['filename'],device="cpu")

    with model.chat_session():
        response = model.generate(
            "Explain artificial intelligence simply.",
            max_tokens=200,
            temp=0.7
        )
        print(response)

    print("===============================================================================================================================")