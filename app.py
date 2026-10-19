import random
import threading
import time
import base64
import os
import gradio as gr

from AIGN import AIGN
# from LLM import chatLLM
from zhipuAI import zhipuChatLLM

chatLLM = zhipuChatLLM(model_name="glm-4-plus",api_key = '57ecdcf0e2b7407a9800b2e58fc8b214.kXuA501N2Hcc2Q8N')
STREAM_INTERVAL = 0.

def convert_history(history):
    """将旧版历史记录转换为新版messages格式"""
    converted = []
    for msg in history:
        if isinstance(msg, (list, tuple)):  # 处理旧格式
            role = "user" if msg[0] is None else "assistant"
            content = msg[1] if msg[0] is None else msg[0]
            converted.append({"role": role, "content": content})
        elif isinstance(msg, dict):
            converted.append(msg)
    return converted
def make_middle_chat():
    carrier = threading.Event()
    carrier.history = []
    def middle_chat(messages, temperature=None, top_p=None):
        nonlocal carrier
        carrier.history.append({"role": "assistant", "content": ""})
        if len(carrier.history) > 20:
            carrier.history = carrier.history[-16:]
        try:
            output_text = ''
            
            for resp in chatLLM(
                messages, temperature=temperature, top_p=top_p, stream=True
            ):
                output_text += resp["content"]
                
                # 更新最后一条消息
                carrier.history[-1] = {
                    "role": "assistant",
                    "content": f"t{output_text}"
                }
            
            return {
                "content": output_text,
                
            }
        except Exception as e:
            carrier.history[-1] = {
                "role": "assistant",
                "content": f"Error: {e}"
            }
            raise e

    return carrier, middle_chat


def gen_ouline_button_clicked(aign, user_idea, history):
    history = convert_history(history)
    aign.user_idea = user_idea

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_outline_writer.chatLLM = middle_chat

    gen_ouline_thread = threading.Thread(target=aign.genNovelOutline)
    gen_ouline_thread.start()

    while gen_ouline_thread.is_alive():
        yield [
            aign,
            carrier.history,
            aign.novel_outline,
            gr.Button(visible=False),
        ]
        time.sleep(STREAM_INTERVAL)
    yield [
        aign,
        carrier.history,
        aign.novel_outline,
        gr.Button(visible=False),
    ]


def gen_beginning_button_clicked(
    aign, history, novel_outline, user_requriments, embellishment_idea
):
    history = convert_history(history)
    aign.novel_outline = novel_outline
    aign.user_requriments = user_requriments
    aign.embellishment_idea = embellishment_idea

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_beginning_writer.chatLLM = middle_chat
    aign.novel_embellisher.chatLLM = middle_chat

    gen_beginning_thread = threading.Thread(target=aign.genBeginning)
    gen_beginning_thread.start()

    while gen_beginning_thread.is_alive():
        yield [
            aign,
            carrier.history,
            aign.writing_plan,
            aign.temp_setting,
            aign.novel_content,
            gr.Button(visible=False),
        ]
        time.sleep(STREAM_INTERVAL)
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temp_setting,
        aign.novel_content,
        gr.Button(visible=False),
    ]


def gen_next_paragraph_button_clicked(
    aign,
    history,
    user_idea,
    novel_outline,
    writing_memory,
    temp_setting,
    writing_plan,
    user_requriments,
    embellishment_idea,
    auto_gen_next

):
    
    # current_state = {
    #     "novel_content": aign.novel_content,
    #     "writing_memory": aign.writing_memory,
    #     "writing_plan": aign.writing_plan,
    #     "temp_setting": aign.temp_setting
    # }
    history = convert_history(history)
    current_state = {
        "paragraph_list": aign.paragraph_list.copy(),  # 使用copy()防止引用问题
        "writing_plan": aign.writing_plan,
        "temp_setting": aign.temp_setting,
        "writing_memory": aign.writing_memory,
        "novel_content": aign.novel_content
    }
    aign.history_stack.append(current_state)
    if len(aign.history_stack) > aign.max_history:
        aign.history_stack.pop(0)
    # 维护历史记录栈
    aign.history_stack.append(current_state)
    if len(aign.history_stack) > aign.max_history:
        aign.history_stack.pop(0)
    aign.user_idea = user_idea
    aign.novel_outline = novel_outline
    aign.writing_memory = writing_memory
    aign.temp_setting = temp_setting
    aign.writing_plan = writing_plan
    aign.user_requriments = user_requriments
    aign.embellishment_idea = embellishment_idea

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_writer.chatLLM = middle_chat
    aign.novel_embellisher.chatLLM = middle_chat
    aign.memory_maker.chatLLM = middle_chat

    gen_next_paragraph_thread = threading.Thread(target=aign.genNextParagraph)
    gen_next_paragraph_thread.start()

    while gen_next_paragraph_thread.is_alive():
        yield [
            aign,
            carrier.history,
            aign.writing_plan,
            aign.temp_setting,
            aign.writing_memory,
            aign.novel_content,
            gr.Button(visible=False),
        ]
        time.sleep(STREAM_INTERVAL)
    # yield [
    #     aign,
    #     carrier.history,
    #     aign.writing_plan,
    #     aign.temp_setting,
    #     aign.writing_memory,
    #     aign.novel_content,
    #     gr.Button(visible=False),
    # ]
    result = [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temp_setting,
        aign.writing_memory,
        aign.novel_content,
        gr.Button(visible=False),
    ]
        
    yield result
def download_novel():
    if os.path.exists("novel_record.md"):
        with open("novel_record.md", "r+", encoding="utf-8") as f:
            content = f.read()
            if "[END]" not in content:
                f.write("\n\n# [END]\n")
        return "novel_record.md"
    raise gr.Error("尚未生成任何小说内容")
def gen_ending_button_clicked(
    aign, 
    history,
    user_requriments,
    novel_content
):
    history = convert_history(history)
    aign.user_requriments = user_requriments
    
    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_ending_writer.chatLLM = middle_chat
    aign.novel_embellisher.chatLLM = middle_chat

    # 保存当前生成进度
    current_state = {
        "paragraph_list": aign.paragraph_list.copy(),
        "writing_plan": aign.writing_plan,
        "temp_setting": aign.temp_setting,
        "writing_memory": aign.writing_memory,
        "novel_content": aign.novel_content
    }
    aign.history_stack.append(current_state)
    
    try:
        gen_ending_thread = threading.Thread(target=aign.genEnding)
        gen_ending_thread.start()

        while gen_ending_thread.is_alive():
            yield [
                aign,
                carrier.history,
                aign.writing_plan,
                aign.temp_setting,
                aign.writing_memory,
                aign.novel_content,
                gr.Button(visible=False),
            ]
            time.sleep(STREAM_INTERVAL)
            
        # 添加结局标记
        aign.paragraph_list.append("\n\n## 故事终章\n")
        final_content = f"{aign.novel_content}\n\n{aign.paragraph_list[-1]}"
        
        yield [
            aign,
            carrier.history,
            aign.writing_plan,
            aign.temp_setting,
            aign.writing_memory,
            final_content,
            gr.Button(visible=False),
        ]
        
    except Exception as e:
        aign.restore_previous_state()
        raise gr.Error(f"结局生成失败，已回滚: {str(e)}")
css = f"""
/* 主容器透明化 */
gradio-app {{
    background-color: rgba(0,0,0,0) !important;
    background-image: none !important;
}}

/* 全局文字颜色 */
* {{
    color: black !important;           /* 字体设置为白色 */
    background: none transparent !important;
}}



/* 浅蓝色背景设置 */
body {{
    background: #e6f7ff !important;    /* 使用柔和的浅蓝色 */
    /* 也可以使用rgba格式：background: rgba(230, 247, 255, 1) !important; */
}}

/* 容器样式 */
#row1, #row2, #row3 {{
    background: rgba(255,255,255,0.2) !important;  /* 半透明白色背景 */
    backdrop-filter: blur(3px);
    border: 1px solid rgba(255,255,255,0.4) !important;  /* 浅色边框 */
    border-radius: 8px;                /* 添加圆角 */
    margin: 10px 0;                    /* 增加间距 */
    padding: 15px;                     /* 内边距 */
}}

/* 输入框等组件样式 */
.gr-input, .gr-textbox, .gr-slider, .gr-checkbox {{
    background: rgba(255,255,255,0.3) !important;
    border: 1px solid rgba(255,255,255,0.5) !important;
}}
.gr-slider {{
    background: rgba(255,255,255,0.6) !important;
    height: 6px !important;
}}
.gr-button {{
    background: rgba(255,255,255,0.9) !important;
    border: 1px solid #ffffff !important;
    color: #2a6496 !important;               /* 品牌蓝色 */
    font-weight: bold !important;
}}

"""
with gr.Blocks(css =css) as demo:
    aign = gr.State(AIGN(chatLLM))
    gr.Markdown("## 语启智创--文本创作助手")
    with gr.Row():
        with gr.Column(scale=0, elem_id="row1"):
            with gr.Tab("开始"):
                gr.Markdown("生成大纲->生成开头->生成下一段")
                user_idea_text = gr.Textbox(
                    "请在这里输入您的想法",
                    label="想法",
                    lines=7,
                    interactive=True,
                )
                user_requriments_text = gr.Textbox(
                    "",
                    label="写作要求",
                    lines=7,
                    interactive=True,
                )
                embellishment_idea_text = gr.Textbox(
                    "",
                    label="润色要求",
                    lines=7,
                    interactive=True,
                )
                gen_ouline_button = gr.Button("生成大纲")
            with gr.Tab("大纲"):
                novel_outline_text = gr.Textbox(
                    label="大纲", lines=30, interactive=True
                )
                gen_beginning_button = gr.Button("生成开头")
            with gr.Tab("状态"):
                writing_memory_text = gr.Textbox(
                    label="记忆",
                    lines=6,
                    interactive=True,
                    max_lines=8,
                )
                writing_plan_text = gr.Textbox(label="计划", lines=6, interactive=True)
                temp_setting_text = gr.Textbox(
                    label="临时设定", lines=5, interactive=True
                )
           
                with gr.Row():
                    gen_next_paragraph_button = gr.Button("生成下一段")
                    gen_ending_button = gr.Button("生成结局", variant="stop")
                with gr.Row():
                    # auto_gen_next_checkbox = gr.Checkbox(label="自动生成下一段", value=False)
                    download_button = gr.Button("下载小说")
        
                

        with gr.Column(scale=3, elem_id="row2"):
            chatBox = gr.Chatbot(height="80vh", label="", type="messages")
        with gr.Column(scale=0, elem_id="row3"):
            novel_content_text = gr.Textbox(
                label="小说正文", lines=32, interactive=True, show_copy_button=True
            )
            
    download_button.click(
        lambda: "novel_record.md" if os.path.exists("novel_record.md") else \
            gr.Error("尚未生成内容"),
        outputs=gr.File(label="下载小说")
    )
    gen_ouline_button.click(
        gen_ouline_button_clicked,
        [aign, user_idea_text, chatBox],
        [aign, chatBox, novel_outline_text, gen_ouline_button],
    )
    gen_beginning_button.click(
        gen_beginning_button_clicked,
        [
            aign,
            chatBox,
            novel_outline_text,
            user_requriments_text,
            embellishment_idea_text,
        ],
        [
            aign,
            chatBox,
            writing_plan_text,
            temp_setting_text,
            novel_content_text,
            gen_beginning_button,
        ],
    )
    gen_next_paragraph_button.click(
        gen_next_paragraph_button_clicked,
        [
            aign,
            chatBox,
            user_idea_text,
            novel_outline_text,
            writing_memory_text,
            temp_setting_text,
            writing_plan_text,
            user_requriments_text,
            embellishment_idea_text,

        ],
        [
             aign,
            chatBox,
            writing_plan_text,
            temp_setting_text,
            writing_memory_text,
            novel_content_text,
            gr.Button(visible=False),
        ],
    )
    gen_ending_button.click(
        gen_ending_button_clicked,
        [
            aign,
            chatBox,
            user_requriments_text,
            novel_content_text
        ],
        [
            aign,
            chatBox,
            writing_plan_text,
            temp_setting_text,
            writing_memory_text,
            novel_content_text,
            gen_ending_button
        ]
    )

demo.queue()
share_url = demo.launch(share=True)
print(f"分享此链接以允许他人访问您的应用: {share_url}")