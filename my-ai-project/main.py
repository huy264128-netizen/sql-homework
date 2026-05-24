from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

print("正在连接 DeepSeek AI...")

llm = ChatDeepSeek(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    model="deepseek-chat",
    temperature=0.7,
)

print("连接成功！请输入你的问题（输入 quit 退出）\n")

while True:
    user_input = input("你: ")
    if user_input.lower() == "quit":
        print("再见！")
        break
    
    messages = [
        SystemMessage(content="你是一个有用的AI助手。"),
        HumanMessage(content=user_input)
    ]
    
    print("AI 正在思考...")
    response = llm.invoke(messages)
    print(f"AI: {response.content}\n")