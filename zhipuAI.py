# import os

# from zhipuai import ZhipuAI


# def zhipuChatLLM(model_name, api_key=None):
#     api_key = os.environ.get("57ecdcf0e2b7407a9800b2e58fc8b214.kXuA501N2Hcc2Q8N", api_key)
#     client = ZhipuAI(api_key=api_key)

#     def chatLLM(
#         messages: list,
#         max_tokens=None,  
#         temperature=0.85,
#         top_p=0.8,
#         stream=False,
#     ) -> dict:
#         if not stream:
#             response = client.chat.completions.create(
#                 model=model_name,
#                 messages=messages,
#                 temperature=temperature,
#                 top_p=top_p,
#                 max_tokens=max_tokens,
#             )
#             return {
#                 "content": response.choices[0].message.content,
#                 "total_tokens": response.usage.total_tokens,
#             }
#         else:
#             responses = client.chat.completions.create(
#                 model=model_name,
#                 messages=messages,
#                 temperature=temperature,
#                 top_p=top_p,
#                 max_tokens=max_tokens,
#                 stream=True,
#             )

#             def respGenerator():
#                 content = ""
#                 for response in responses:
#                     delta = response.choices[0].delta.content
#                     if delta:  # 过滤空内容
#                         content += delta
#                         yield {
#                             "content": delta,  # 仅返回增量内容
#                             "accumulated": content,  # 可选：单独返回累积内容
#                             "total_tokens": None
#             }

#             return respGenerator()

#     return chatLLM
import os
from typing import Generator, Union, Any
from dotenv import load_dotenv
from openai import OpenAI

def qwenChatLLM(model_name="qwen-turbo-latest", api_key=None):
    load_dotenv()
    client = OpenAI(
        api_key=api_key or os.environ.get("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    def chatLLM(
        messages: list,
        max_tokens=1500,
        temperature=0.85,
        top_p=0.8,
        stream=False,
    ) -> Union[dict, Generator[dict, None, None]]:  # 关键类型声明修改
        try:
            if not stream:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                )
                return {
                    "content": response.choices[0].message.content,
                    "total_tokens": response.usage.total_tokens,
                }
            else:
                responses = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    stream=True,
                )

                def respGenerator() -> Generator[dict, None, None]:  # 明确的生成器类型标注
                    full_content = ""
                    for chunk in responses:
                        if chunk.choices:
                            delta = chunk.choices[0].delta.content or ""
                            full_content += delta
                            yield {
                                "content": delta,
                                "accumulated": full_content,
                                "total_tokens": None
                            }

                return respGenerator()  # 直接返回生成器对象

        except Exception as e:
            error_msg = f"API调用失败: {str(e)}"
            if stream:
                def error_gen() -> Generator[dict, None, None]:
                    yield {"content": error_msg}
                return error_gen()
            else:
                return {"content": error_msg, "total_tokens": 0}

    return chatLLM
