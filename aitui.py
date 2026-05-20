"""
这个只是用于娱乐的ai agent
也可能某种程度上简化了调用吧
"""
from dataclasses import dataclass
from langchain.agents import create_agent
from langchain.tools import tool, ToolRuntime
import langchain_deepseek
from accessDB import exampleDB
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek
import init_database
class FixedChatDeepSeek(ChatDeepSeek):
    """终极修复版：拦截 payload 字典生成，强行补齐 reasoning_content"""
    
    def _get_request_payload(self, messages, stop=None, **kwargs):
        # 1. 调用父类方法，获取原本要发给 API 的字典 (这个时候 reasoning_content 已经被剔除了)
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        
        # 2. 强行补回来
        if "messages" in payload:
            for raw_msg, dict_msg in zip(messages, payload["messages"]):
                # 只有 assistant 的消息会被 DeepSeek 校验
                if dict_msg.get("role") == "assistant":
                    
                    # 尝试找回原本的思考内容
                    rc = getattr(raw_msg, "additional_kwargs", {}).get("reasoning_content") or \
                         getattr(raw_msg, "response_metadata", {}).get("reasoning_content")
                    
                    # 核心保底机制：如果 LangGraph 丢弃了历史数据，但这条消息又带有 tool_calls
                    # DeepSeek 接口会强行要求推理内容。我们给一个占位符糊弄过去，避免 400 报错
                    if not rc and dict_msg.get("tool_calls"):
                        rc = "思考过程已省略" 
                        
                    # 只要有内容，就硬塞进发给 API 的字典里
                    if rc:
                        dict_msg["reasoning_content"] = rc
                        
        return payload

# 初始化你的模型
model = FixedChatDeepSeek(
    model="deepseek-v4-flash",
    temperature=0.1,
    max_tokens=None,
    timeout=None,
    max_retries=2
)

@dataclass
class Context:
    """自定义运行时上下文模式。"""
    user_id: str
systemPrompt ="""
你是一个图书管理系统的交互机器人,你可以用SQL语句查询并操纵这个图书管理系统的信息,每次操纵后你要返回你使用的SQL命令,同时返回你得到的原始信息,请使用简洁并且不包含markdown的语言回复用户的问题接下来的内容是有关这个图书管理系统的详细信息:
"""
with open("./readme.md",'r',encoding='utf-8') as readme:
    systemPrompt+= readme.read()
@tool
def sqlcmd(cmd:str) -> str:
    """输入一个sql命令,返回查询结果"""
    result:str
    try:
        result= str(exampleDB.execSQL(cmd))
    except Exception as e:
        result=str(e)
    return result
checkpointer = InMemorySaver()
agent = create_agent(
    model=model,
    system_prompt=systemPrompt,
    tools=[sqlcmd],
    checkpointer=checkpointer,
    context_schema=Context,
)


config = {"configurable": {"thread_id": "1"}}
def main():
    userInput=input()
    while(userInput!='exit'):
        response=agent.invoke(
            {"messages":[{"role":"user","content":userInput}]},
            config=config,
            context=Context(user_id="1")
        )
        print(response["messages"][-1].content)
        userInput=input()
if __name__=='__main__':
    init_database.initial()
    main()