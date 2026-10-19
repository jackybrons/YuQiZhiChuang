import os
import threading
import time
import base64
import gradio as gr

from SCRIPT import ScriptAIGN  # 请确保 ScriptAIGN 类已在 SCRIPT.py 文件中实现
from zhipuAI import zhipuChatLLM

# 初始化 LLM 接口
chatLLM = zhipuChatLLM(model_name="glm-4-plus", api_key='57ecdcf0e2b7407a9800b2e58fc8b214.kXuA501N2Hcc2Q8N')
STREAM_INTERVAL = 0.5  # 调整更新频率

def convert_history(history):
    """将旧版历史记录转换为新版 messages 格式"""
    converted = []
    for msg in history:
        if isinstance(msg, (list, tuple)):
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
        output_text = ''
        try:
            for resp in chatLLM(messages, temperature=temperature, top_p=top_p, stream=True):
                output_text += resp.get("content", "")
                carrier.history[-1] = {"role": "assistant", "content": output_text}
            return {"content": output_text}
        except Exception as e:
            carrier.history[-1] = {"role": "assistant", "content": f"Error: {e}"}
            raise e
    return carrier, middle_chat


def gen_outline_button_clicked(aign, user_idea, history):
    history = convert_history(history)
    aign.user_idea = user_idea

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.creative_architect.chatLLM = middle_chat

    thread = threading.Thread(target=lambda: aign.genScriptOutline())
    thread.start()
    while thread.is_alive():
        yield [aign, carrier.history, aign.script_outline, gr.update(visible=False)]
        time.sleep(STREAM_INTERVAL)
    yield [aign, carrier.history, aign.script_outline, gr.update(visible=True)]


def gen_beginning_button_clicked(aign, history, script_outline, user_requirements):
    history = convert_history(history)
    aign.script_outline = script_outline
    aign.user_requirements = user_requirements

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.master_director.chatLLM = middle_chat
    aign.scene_engineer.chatLLM = middle_chat

    thread = threading.Thread(target=lambda: aign.genBeginning())
    thread.start()
    while thread.is_alive():
        yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_content, gr.update(visible=False)]
        time.sleep(STREAM_INTERVAL)
    yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_content, gr.update(visible=True)]


def gen_next_scene_button_clicked(
    aign,
    history,
    user_idea,
    script_outline,
    script_memory,
    temp_setting,
    working_plan,
    user_requirements,
    auto_gen_next
):
    history = convert_history(history)
    # 保存状态
    if len(aign.history_stack) >= aign.max_history:
        aign.history_stack.pop(0)
    aign.history_stack.append({
        "scene_list": aign.scene_list.copy(),
        "script_memory": aign.script_memory,
        "script_content": aign.script_content
    })

    # 更新输入参数
    aign.user_idea = user_idea
    aign.script_outline = script_outline
    aign.script_memory = script_memory
    aign.temp_setting = temp_setting
    aign.working_plan = working_plan
    aign.user_requirements = user_requirements

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.master_director.chatLLM = middle_chat
    aign.dialogue_alchemist.chatLLM = middle_chat
    aign.cultural_guardian.chatLLM = middle_chat

    thread = threading.Thread(target=lambda: aign.genNextScene())
    thread.start()
    while thread.is_alive():
        yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content]
        time.sleep(STREAM_INTERVAL)
    yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content]


def gen_ending_button_clicked(aign, history, user_requirements, script_content):
    history = convert_history(history)
    aign.user_requirements = user_requirements

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.master_director.chatLLM = middle_chat
    aign.dialogue_alchemist.chatLLM = middle_chat

    # 保存状态
    if len(aign.history_stack) >= aign.max_history:
        aign.history_stack.pop(0)
    aign.history_stack.append({
        "scene_list": aign.scene_list.copy(),
        "script_memory": aign.script_memory,
        "script_content": aign.script_content
    })

    try:
        thread = threading.Thread(target=lambda: aign.genEnding())
        thread.start()
        while thread.is_alive():
            yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content, gr.update(visible=False)]
            time.sleep(STREAM_INTERVAL)
        # 结束后直接使用 aign.script_content
        yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content, gr.update(visible=True)]
    except Exception as e:
        aign.restore_previous_state()
        raise gr.Error(f"结局生成失败，已回滚: {e}")


def download_script():
    if os.path.exists("script_record.md"):
        with open("script_record.md", "r+", encoding="utf-8") as f:
            content = f.read()
            if "[END]" not in content:
                f.write("\n\n# [END]\n")
        return "script_record.md"
    raise gr.Error("尚未生成任何剧本内容")

css = f"""
/* 主容器透明化 */
gradio-app {{ background-color: rgba(0,0,0,0) !important; background-image: none !important; }}
/* 全局文字颜色 */
* {{ color: black !important; background: none transparent !important; }}
/* 浅蓝色背景 */
body {{ background: #e6f7ff !important; }}
/* 容器样式 */
#row1, #row2, #row3 {{ background: rgba(255,255,255,0.2) !important; backdrop-filter: blur(3px); border: 1px solid rgba(255,255,255,0.4) !important; border-radius: 8px; margin: 10px 0; padding: 15px; }}
/* 组件样式 */
.gr-input, .gr-textbox, .gr-slider, .gr-checkbox {{ background: rgba(255,255,255,0.3) !important; border: 1px solid rgba(255,255,255,0.5) !important; }}
.gr-slider {{ height: 6px !important; }}
.gr-button {{ background: rgba(255,255,255,0.9) !important; border: 1px solid #ffffff !important; color: #2a6496 !important; font-weight: bold !important; }}
"""

with gr.Blocks(css=css) as demo:
    aign = gr.State(ScriptAIGN(chatLLM))
    gr.Markdown("## 短剧剧本创作--协同工作平台")
    with gr.Row():
        with gr.Column(scale=0, elem_id="row1"):
            with gr.Tab("开始"):
                gr.Markdown("生成大纲 -> 生成开篇 -> 生成下一场景 -> 生成结局")
                user_idea_text = gr.Textbox("请在这里输入您的创意", label="创意", lines=7)
                user_requirements_text = gr.Textbox("", label="写作要求", lines=7)
                gen_outline_button = gr.Button("生成大纲")
            with gr.Tab("大纲"):
                script_outline_text = gr.Textbox(label="剧本大纲", lines=30)
                gen_beginning_button = gr.Button("生成开篇")
                gen_next_scene_button = gr.Button("生成下一场景")
                gen_ending_button = gr.Button("生成结局", variant="stop")
            with gr.Tab("状态"):
                script_memory_text = gr.Textbox(label="记忆", lines=6, max_lines=8)
                working_plan_text = gr.Textbox(label="计划", lines=6)
                temp_setting_text = gr.Textbox(label="临时设定", lines=5)
                download_button = gr.Button("下载剧本")
        with gr.Column(scale=3, elem_id="row2"):
            chatBox = gr.Chatbot(height="80vh", type="messages")
        with gr.Column(scale=0, elem_id="row3"):
            script_content_text = gr.Textbox(label="剧本正文", lines=32, show_copy_button=True)

    download_button.click(download_script, outputs=gr.File(label="下载剧本"))
    gen_outline_button.click(
        gen_outline_button_clicked,
        [aign, user_idea_text, chatBox],
        [aign, chatBox, script_outline_text, gen_outline_button]
    )
    gen_beginning_button.click(
        gen_beginning_button_clicked,
        [aign, chatBox, script_outline_text, user_requirements_text],
        [aign, chatBox, working_plan_text, temp_setting_text, script_content_text, gen_beginning_button]
    )
    gen_next_scene_button.click(
        gen_next_scene_button_clicked,
        [aign, chatBox, user_idea_text, script_outline_text, script_memory_text, temp_setting_text, working_plan_text, user_requirements_text, gr.Checkbox(value=False)],
        [aign, chatBox, working_plan_text, temp_setting_text, script_memory_text, script_content_text]
    )
    gen_ending_button.click(
        gen_ending_button_clicked,
        [aign, chatBox, user_requirements_text, script_content_text],
        [aign, chatBox, working_plan_text, temp_setting_text, script_memory_text, script_content_text, gen_ending_button]
    )

    demo.queue()
    share_url = demo.launch(share=True)
    print(f"分享链接: {share_url}")

