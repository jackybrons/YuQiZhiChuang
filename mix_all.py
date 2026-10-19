import random
import threading
import time
import base64
import os
import gradio as gr
from AIGC import GovernmentDocumentSystem
from AIGN import AIGN
from SCRIPT import ScriptAIGN
from zhipuAI import zhipuChatLLM
import re
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inchesp
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import markdown
from bs4 import BeautifulSoup
from voice_input import record_audio, realtime_asr,signal_handler
import voice_input
import threading
import signal

# 用于跟踪语音输入状态的变量
is_recording = threading.Event()
stop_recording = threading.Event()

chatLLM = zhipuChatLLM(model_name="glm-4-plus", api_key='57ecdcf0e2b7407a9800b2e58fc8b214.kXuA501N2Hcc2Q8N')
STREAM_INTERVAL = 0.

# 公文生成常量
STANDARD_FONT = "SimSun"
FONT_MAPPING = {
    "SimSun": ["宋体", "SimSun"],
    "SimHei": ["黑体", "SimHei"],
    "FangSong": ["仿宋", "FangSong_GB2312", "FangSong"]
}

DOC_TYPES = {
    "通知": {
        "structure": ["标题", "发文字号", "主送机关", "正文", "发文机关", "成文日期"],
        "format_rules": {
            "title": {"font": "SimHei", "size": 22, "align": "center"},
            "body": {"font": STANDARD_FONT, "size": 16}
        }
    },
    "请示": {
        "structure": ["标题", "主送机关", "请示缘由", "请示事项", "结语"],
        "format_rules": {
            "title": {"font": "SimHei", "size": 22},
            "emphasis": {"bold": True, "underline": True}
        }
    },
    "函": {
        "structure": ["标题", "主送机关", "发函缘由", "商洽事项", "结语"],
        "format_rules": {
            "title": {"font": "SimHei", "size": 20}
        }
    },
    "报告": {
        "structure": ["标题", "主送机关", "基本情况", "分析情况", "意见建议"],
        "format_rules": {
            "title": {"font": "SimHei", "size": 20}
        }
    }
}

import time
from voice_input import record_audio, realtime_asr, combined_emotion_analysis, visualize_emotion_segments, generate_summary, Config

is_recording = False
stop_recording = False

# 定义线程锁
recording_lock = threading.Lock()

def handle_voice_input(input_textbox):
    global is_recording, stop_recording
    print(f"点击按钮时，is_recording状态: {is_recording.is_set()}")
    if not is_recording.is_set():
        print("准备开始录音...")
        # 开始录音
        is_recording.set()
        stop_recording.clear()  # 确保停止标志被清除
        print("开始录音...")
        audio_file = record_audio()
        if audio_file:
            text = realtime_asr(audio_file)
            if text:
                # 情感分析
                emotion_result = combined_emotion_analysis(text, audio_file)
                if emotion_result:
                    print("\n🎭 情感分析结果:")
                    if emotion_result['text_analysis']:
                        print(f"文本情感: {emotion_result['text_analysis']['emotion']} "
                              f"(置信度: {emotion_result['text_analysis']['score']:.2f})")
                    if emotion_result['audio_analysis']:
                        print(f"语调特征: {emotion_result['audio_analysis']}")
                    print(f"综合判定: {emotion_result['combined_result']['emotion']} "
                          f"(置信度: {emotion_result['combined_result']['confidence']:.2f})")

                    # 可视化分析
                    visualize_emotion_segments(text)

                # 内容摘要
                print("\n生成摘要...", end='', flush=True)
                if len(text.strip()) < 15:
                    print("内容过短，无法生成摘要")
                else:
                    summary = generate_summary(text)
                    if summary:
                        print("\n📝 内容摘要:")
                        print(summary)
                    else:
                        print("\n摘要生成失败")

                # 保存结果
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                with open(f"result_{timestamp}.txt", 'w', encoding='utf-8') as f:
                    f.write(f"识别文本:\n{text}\n\n")
                    if emotion_result:
                        f.write(f"情感分析:\n{str(emotion_result)}\n\n")
                    if summary:
                        f.write(f"内容摘要:\n{summary}\n")
                    print(f"\n✅ 分析结果已保存到 result_{timestamp}.txt")

                is_recording.clear()  # 录音结束后清除标志
                print("录音结束，is_recording状态已清除")
                return text
    else:
        print("准备停止录音...")
        # 停止录音
        is_recording.clear()
        stop_recording.set()
        print("停止录音...")
        # 等待录音线程结束
        while is_recording.is_set():
            time.sleep(0.1)
        # 确保录音文件关闭
        try:
            with open(Config.WAVE_OUTPUT_FILENAME, 'a') as f:
                pass  # 尝试打开文件以确保文件句柄关闭
        except Exception as e:
            print(f"关闭录音文件时出错: {e}")
    return input_textbox

# 处理 Ctrl+C 信号
def signal_handler(sig, frame):
    if is_recording.is_set():
        is_recording.clear()
        stop_recording.set()
        print("停止录音...")
        # 等待录音线程结束
        while voice_input.is_recording_active():
            time.sleep(0.1)
    else:
        print("程序正常退出...")
        exit(0)

# 注册信号处理函数
signal.signal(signal.SIGINT, signal_handler)

def convert_history(history):
    converted = []
    for msg in history:
        if isinstance(msg, (list, tuple)) and len(msg) == 2:
            converted.append(msg)
        elif isinstance(msg, dict):
            content = msg.get("content", "")
            if msg.get("role") == "user":
                converted.append([None, content])
            elif msg.get("role") == "assistant":
                converted.append([content, None])
    return converted

def make_middle_chat():
    carrier = threading.Event()
    carrier.history = []
    def middle_chat(messages, temperature=None, top_p=None):
        nonlocal carrier
        carrier.history.append([None, ""])
        if len(carrier.history) > 20:
            carrier.history = carrier.history[-16:]
        try:
            output_text = ''
            for resp in chatLLM(messages, temperature=temperature, top_p=top_p, stream=True):
                output_text += resp["content"]
                carrier.history[-1] = [output_text, None]
            return {"content": output_text}
        except Exception as e:
            carrier.history[-1] = [f"Error: {e}", None]
            raise e
    return carrier, middle_chat

def get_available_font(font_name: str) -> str:
    for font in FONT_MAPPING.get(font_name, [font_name]):
        return font
    return "Arial Unicode MS"

def sanitize_text(text: str) -> str:
    text = re.sub(r'[\u3000\xa0\u200b]', ' ', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text.strip()

def format_chinese_date():
    return datetime.now().strftime("%Y年%m月%d日")

def _generate_doc_number(doc_type: str) -> str:
    prefix_map = {"通知": "X政", "请示": "X政请", "函": "X政函", "报告": "X政报"}
    year = datetime.now().year
    seq = f"{int(time.time()) % 1000:03d}"
    return f"{prefix_map.get(doc_type, 'X政')}〔{year}〕{seq}号"

def _set_font(element, font_name: str):
    rPr = element._element.rPr
    if rPr is None:
        rPr = OxmlElement('w:rPr')
        element._element.insert(0, rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:eastAsia'), font_name)

def generate_document(doc_type, sender, recipient, content, doc_number, doc_date):
    try:
        full_input = {
            "type": doc_type,
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "doc_number": doc_number or _generate_doc_number(doc_type),
            "date": doc_date or format_chinese_date()
        }
        
        messages = [
            {"role": "system", "content": f"请按标准格式生成{doc_type}，直接返回最终公文内容"},
            {"role": "user", "content": content}
        ]
        
        response = chatLLM(messages)
        result = response["content"]
        
        lines = result.split('\n')
        formatted = []
        for i, line in enumerate(lines):
            if i in [0, 1, 3] or i >= len(lines)-2:
                formatted.append(line)
            else:
                if line.strip():
                    formatted.append(f"　　{line}" if not line.startswith(' ') else line)
        
        return "\n".join(formatted)
    except Exception as e:
        return f"生成失败: {str(e)}"

def export_to_word(content_text, doc_type):
    try:
        lines = content_text.split('\n')
        doc_info = {
            "type": doc_type,
            "title": lines[0] if lines else "",
            "doc_number": lines[1] if len(lines)>1 else "",
            "recipient": lines[3] if len(lines)>3 else "",
            "content": '\n'.join(lines[4:-2]) if len(lines)>5 else "",
            "sender": lines[-2] if len(lines)>=2 else "",
            "date": lines[-1] if lines else ""
        }
        
        output_path = os.path.join("output", f"{doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        document = Document()
        section = document.sections[0]
        section.left_margin = Inches(1.5)
        section.right_margin = Inches(1.5)
        
        # 标题
        title_para = document.add_paragraph()
        title_run = title_para.add_run(sanitize_text(doc_info["title"]))
        _set_font(title_run, get_available_font("SimHei"))
        title_run.font.size = Pt(22)
        title_run.font.bold = True
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        document.add_paragraph()
        
        # 文号
        if doc_info.get("doc_number"):
            num_para = document.add_paragraph()
            num_run = num_para.add_run(sanitize_text(doc_info["doc_number"]))
            _set_font(num_run, get_available_font(STANDARD_FONT))
            num_run.font.size = Pt(16)
            num_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            document.add_paragraph()
        
        # 正文内容
        body_font = get_available_font(STANDARD_FONT)
        body_size = Pt(16)
        
        content = sanitize_text(doc_info["content"])
        for paragraph in content.split('\n'):
            if not paragraph.strip():
                document.add_paragraph()
                continue
                
            p = document.add_paragraph()
            p.paragraph_format.first_line_indent = Pt(32)
            p.paragraph_format.line_spacing = 1.5
            
            run = p.add_run(paragraph)
            _set_font(run, body_font)
            run.font.size = body_size

        # 发文信息
        if all(key in doc_info for key in ["sender", "date"]):
            document.add_paragraph()
            
            sender_para = document.add_paragraph()
            sender_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            sender_run = sender_para.add_run(sanitize_text(doc_info["sender"]))
            _set_font(sender_run, body_font)
            sender_run.font.size = body_size
            
            date_para = document.add_paragraph()
            date_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            date_run = date_para.add_run(sanitize_text(doc_info["date"]))
            _set_font(date_run, body_font)
            date_run.font.size = body_size

        document.save(output_path)
        return output_path
    except Exception as e:
        raise gr.Error(f"Word导出失败: {str(e)}")

def gen_ouline_button_clicked(aign, user_idea, history, chapter_count, word_count_per_chapter):
    history = convert_history(history)
    aign.user_idea = user_idea
    aign.chapter_count = chapter_count
    aign.word_count_per_chapter = word_count_per_chapter

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
            gr.Button(visible=True),
            gr.Button(visible=False),
            gr.Button(visible=False),
            gr.Button(visible=False)
        ]
        time.sleep(STREAM_INTERVAL)
        
    yield [
        aign,
        carrier.history,
        aign.novel_outline,
        gr.Button(visible=True),
        gr.Button(visible=True),
        gr.Button(visible=False),
        gr.Button(visible=False)
    ]

def gen_beginning_button_clicked(aign, history, novel_outline, user_requriments, embellishment_idea):
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
            gr.Button(visible=True),
            gr.Button(visible=True),
            gr.Button(visible=False)
        ]
        time.sleep(STREAM_INTERVAL)
        
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temp_setting,
        aign.novel_content,
        gr.Button(visible=True),
        gr.Button(visible=True),
        gr.Button(visible=True)
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
    history = convert_history(history)
    current_state = {
        "paragraph_list": aign.paragraph_list.copy(),
        "writing_plan": aign.writing_plan,
        "temp_setting": aign.temp_setting,
        "writing_memory": aign.writing_memory,
        "novel_content": aign.novel_content
    }
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

    # 获取当前章节信息
    current_chapter = len(aign.paragraph_list) + 1
    total_chapters = aign.chapter_count
    
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
            gr.Button(visible=True),
            gr.Button(visible=True),
            gr.Button(visible=True)
        ]
        time.sleep(STREAM_INTERVAL)
        
    # 添加章节标记
    if aign.novel_content and f"第{current_chapter}章" not in aign.novel_content:
        chapter_header = f"\n\n# 第{current_chapter}章/{total_chapters}章\n\n"
        aign.novel_content = aign.novel_content + chapter_header + aign.paragraph_list[-1]
    
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temp_setting,
        aign.writing_memory,
        aign.novel_content,
        gr.Button(visible=True),
        gr.Button(visible=True),
        gr.Button(visible=True)
    ]

def gen_ending_button_clicked(aign, history, user_requriments, novel_content):
    history = convert_history(history)
    aign.user_requriments = user_requriments
    
    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_ending_writer.chatLLM = middle_chat
    aign.novel_embellisher.chatLLM = middle_chat

    current_state = {
        "paragraph_list": aign.paragraph_list.copy(),
        "writing_plan": aign.writing_plan,
        "temp_setting": aign.temp_setting,
        "writing_memory": aign.writing_memory,
        "novel_content": aign.novel_content
    }
    aign.history_stack.append(current_state)
    if len(aign.history_stack) > aign.max_history:
        aign.history_stack.pop(0)

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
            gr.Button(visible=True),
            gr.Button(visible=True),
            gr.Button(visible=True)
        ]
        time.sleep(STREAM_INTERVAL)
        
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temp_setting,
        aign.writing_memory,
        aign.novel_content,
        gr.Button(visible=True),
        gr.Button(visible=True),
        gr.Button(visible=True)
    ]

def download_novel():
    if os.path.exists("novel_record.md"):
        with open("novel_record.md", "r+", encoding="utf-8") as f:
            content = f.read()
            if "[END]" not in content:
                f.write("\n\n# [END]\n")
        return "novel_record.md"
    raise gr.Error("尚未生成任何小说内容")

def download_document(doc_type, content):
    try:
        if not content.strip():
            raise gr.Error("没有可下载的内容")
        
        output_path = export_to_word(content, doc_type)
        if os.path.exists(output_path):
            return output_path
        raise gr.Error("文件生成失败")
    except Exception as e:
        raise gr.Error(f"下载失败: {str(e)}")

def toggle_interface(mode):
    is_fiction = mode == "fiction"
    is_script = mode == "script"
    return {
        fiction_interface: gr.Row(visible=is_fiction),
        document_interface: gr.Row(visible=not (is_fiction or is_script)),
        script_interface: gr.Row(visible=is_script),
        switch_btn: gr.Button(
            value="切换到公文模式" if is_fiction else ("切换到剧本模式" if mode == "document" else "切换到小说模式"),
            variant="primary" if not is_fiction else "secondary"
        )
    }

def process_document_request(doc_type, doc_requirements, history):
    history = convert_history(history)
    
    try:
        sender = "XX市城市绿化管理局"
        recipient = "各区县城市绿化管理部门、各相关单位"
        doc_number = _generate_doc_number(doc_type)
        doc_date = format_chinese_date()
        
        generated_content = generate_document(
            doc_type=doc_type,
            sender=sender,
            recipient=recipient,
            content=doc_requirements,
            doc_number=doc_number,
            doc_date=doc_date
        )
        
        formatted_output = f"📝 根据您的要求生成的{doc_type}：\n\n{generated_content}"
        
        new_history = history + [
            {"role": "user", "content": doc_requirements},
            {"role": "assistant", "content": formatted_output}
        ]
        
        return [new_history, generated_content, gr.Button(visible=True)]
    
    except Exception as e:
        error_msg = f"❌ {doc_type}生成失败：{str(e)}"
        return [
            history + [{"role": "assistant", "content": error_msg}],
            "",
            gr.Button(visible=False)
        ]

# 剧本生成相关函数
def gen_script_outline_button_clicked(aign, user_idea, history, scene_count, word_count_per_scene):
    history = convert_history(history)
    aign.user_idea = user_idea
    aign.scene_count = scene_count
    aign.word_count_per_scene = word_count_per_scene

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.creative_architect.chatLLM = middle_chat

    thread = threading.Thread(target=lambda: aign.genScriptOutline())
    thread.start()
    while thread.is_alive():
        yield [aign, carrier.history, aign.script_outline, gr.update(visible=True)]
        time.sleep(STREAM_INTERVAL)
    yield [aign, carrier.history, aign.script_outline, gr.update(visible=True)]

def gen_script_beginning_button_clicked(aign, history, script_outline, user_requirements):
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
        yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_content, gr.update(visible=True)]
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
    if len(aign.history_stack) >= aign.max_history:
        aign.history_stack.pop(0)
    aign.history_stack.append({
        "scene_list": aign.scene_list.copy(),
        "script_memory": aign.script_memory,
        "script_content": aign.script_content
    })

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

    # 获取当前场景信息
    current_scene = len(aign.scene_list) + 1
    total_scenes = aign.scene_count
    
    thread = threading.Thread(target=lambda: aign.genNextScene())
    thread.start()
    while thread.is_alive():
        yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content]
        time.sleep(STREAM_INTERVAL)
    
    # 添加场景标记
    if aign.script_content and f"第{current_scene}场" not in aign.script_content:
        scene_header = f"\n\n## 第{current_scene}场/{total_scenes}场\n\n"
        aign.script_content = aign.script_content + scene_header + aign.scene_list[-1]
    
    yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content]

def gen_script_ending_button_clicked(aign, history, user_requirements, script_content):
    history = convert_history(history)
    aign.user_requirements = user_requirements

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.master_director.chatLLM = middle_chat
    aign.dialogue_alchemist.chatLLM = middle_chat

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
            yield [aign, carrier.history, aign.working_plan, aign.temp_setting, aign.script_memory, aign.script_content, gr.update(visible=True)]
            time.sleep(STREAM_INTERVAL)
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

css = """
/* 主容器透明化 */
gradio-app {
    background-color: rgba(0,0,0,0) !important;
    background-image: none !important;
}

/* 全局文字颜色 */
* {
    color: black !important;
}

/* 更精确的全局背景设置 */
body {
    background: #e6f7ff !important;
}

/* 新增大尺寸输入输出框样式 */
.large-input .gr-input,
.large-output .gr-textbox {
    min-height: 600px !important;
    font-size: 14px !important;
    line-height: 1.6 !important;
}

/* 标题行样式 */
.title-row {
    margin-bottom: 20px !important;
}

.mode-button {
    margin-left: 20px !important;
    background: #2196F3 !important;
    color: white !important;
    padding: 6px 12px !important;
    font-size: 14px !important;
    border-radius: 4px !important;
    border: none !important;
    cursor: pointer !important;
}

.document-chat .message-bot {
    font-family: 'SimSun', serif !important;
    white-space: pre-wrap;
    background: #f0faff !important;
    border-left: 4px solid #1890ff !important;
}

.document-preview {
    font-family: 'FangSong', serif !important;
    font-size: 16px !important;
    line-height: 2 !important;
    padding: 20px !important;
    background: #f9f9f9 !important;
    border: 1px solid #ddd !important;
}

/* 完全重写下拉菜单样式 */
.document-interface .gr-dropdown {
    --tw-bg-opacity: 1 !important;
    background-color: rgb(255 255 255 / var(--tw-bg-opacity)) !important;
}

.document-interface .gr-dropdown .wrap {
    background-color: white !important;
    background-image: none !important;
    border-radius: 4px !important;
    border: 1px solid #ddd !important;
}

.document-interface .gr-dropdown .wrap:hover {
    background-color: #f5f5f5 !important;
}

.document-interface .gr-dropdown .options {
    background-color: white !important;
    background-image: none !important;
    border: 1px solid #ddd !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
}

.document-interface .gr-dropdown .option {
    background-color: white !important;
    background-image: none !important;
}

.document-interface .gr-dropdown .option:hover {
    background-color: #f0f7ff !important;
}

/* 添加对Gradio 3.x+的特殊处理 */
.document-interface .gr-box {
    background-color: white !important;
    background-image: none !important;
}

/* 保持原有其他样式不变 */
.document-preview {
    font-family: 'FangSong', serif !important;
    font-size: 16px !important;
    line-height: 2 !important;
    padding: 20px !important;
    background: #f9f9f9 !important;
    border: 1px solid #ddd !important;
}
.hidden {
    display: none !important;
}

/* 剧本界面特定样式 */
.script-panel {
    background: rgba(255,253,245,0.8) !important;
    border: 1px solid #f5e8c4 !important;
}

.script-content {
    font-family: 'KaiTi', serif !important;
    font-size: 15px !important;
    line-height: 1.8 !important;
}

/* 章节设置样式 */
.chapter-settings {
    background: #f5f5f5 !important;
    padding: 15px !important;
    border-radius: 8px !important;
    margin-bottom: 15px !important;
}

.chapter-settings label {
    font-weight: bold !important;
    margin-bottom: 5px !important;
    display: block !important;
}

.chapter-settings input {
    width: 100% !important;
    padding: 8px !important;
    border: 1px solid #ddd !important;
    border-radius: 4px !important;
}

/* 章节标题样式 */
.chapter-title {
    font-weight: bold;
    color: #1890ff;
    margin: 15px 0 10px 0;
}

.scene-title {
    font-weight: bold;
    color: #722ed1;
    margin: 12px 0 8px 0;
}

/* 新增横向滑轮样式 */
.scrollable-chat {
    overflow-x: auto;
    white-space: nowrap;
    padding-bottom: 15px;
}

.scrollable-chat .message {
    display: inline-block;
    vertical-align: top;
    margin-right: 15px;
    white-space: normal;
    width: 300px;
    min-height: 100px;
    background: #f5f5f5;
    border-radius: 8px;
    padding: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.scrollable-chat .message-user {
    border-left: 4px solid #4CAF50;
}

.scrollable-chat .message-bot {
    border-left: 4px solid #2196F3;
}

.scrollable-chat .message-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    max-height: 200px;
    overflow-y: auto;
}
"""

with gr.Blocks(css=css) as demo:
    aign = gr.State(AIGN(chatLLM))
    script_aign = gr.State(ScriptAIGN(chatLLM))
    current_mode = gr.State("fiction")
    
    with gr.Row(equal_height=True, elem_classes="title-row"):
        gr.Markdown("## 语启智创--文本创作助手")
        switch_btn = gr.Button("切换到公文模式", elem_classes="mode-button")
    
    # 小说创作界面
    with gr.Row(visible=True) as fiction_interface:
        with gr.Column(scale=1, elem_id="row1"):
            with gr.Tab("开始"):
                gr.Markdown("生成大纲->生成开头->生成下一段")
                user_idea_text = gr.Textbox(
                    "请在这里输入您的想法",
                    label="想法",
                    lines=7,
                    interactive=True,
                )
                voice_input_button = gr.Button(value="语音输入")
                voice_input_button.click(
                        handle_voice_input,
                        [user_idea_text],
                        [user_idea_text]
                    )

                with gr.Accordion("章节设置", open=False, elem_classes="chapter-settings"):
                    gr.Markdown("**章节设置说明**：\n- 每章字数建议不少于500字\n- 章节数量建议5-30章")
                    chapter_count = gr.Number(
                        label="章节数量",
                        value=10,
                        minimum=1,
                        maximum=100,
                        step=1,
                        interactive=True
                    )
                    word_count_per_chapter = gr.Number(
                        label="每章节字数",
                        value=2000,
                        minimum=500,
                        maximum=10000,
                        step=100,
                        interactive=True
                    )
                user_requriments_text = gr.Textbox(
                    "",
                    label="写作要求",
                    lines=7,
                    interactive=True,
                )
                voice_input_button = gr.Button(value="语音输入")
                voice_input_button.click(
                    handle_voice_input,
                    [user_idea_text],
                    [user_idea_text]
                )

                embellishment_idea_text = gr.Textbox(
                    "",
                    label="润色要求",
                    lines=7,
                    interactive=True,
                )
                voice_input_button = gr.Button(value="语音输入")
                voice_input_button.click(
                    handle_voice_input,
                    [user_idea_text],
                    [user_idea_text]
                )

                gen_ouline_button = gr.Button("生成大纲", variant="primary")
                
            with gr.Tab("大纲"):
                novel_outline_text = gr.Textbox(
                    "",
                    label="小说大纲",
                    lines=15,
                    interactive=True,
                    elem_classes=["large-output"]
                )
                gen_beginning_button = gr.Button("生成开头", visible=False)
                
            with gr.Tab("正文"):
                writing_plan_text = gr.Textbox(
                    "",
                    label="写作计划",
                    lines=5,
                    interactive=True
                )
                temp_setting_text = gr.Textbox(
                    "",
                    label="临时设定",
                    lines=5,
                    interactive=True
                )
                writing_memory_text = gr.Textbox(
                    "",
                    label="写作记忆",
                    lines=5,
                    interactive=True
                )
                novel_content_text = gr.Textbox(
                    "",
                    label="小说正文",
                    lines=15,
                    interactive=True,
                    elem_classes=["large-output"]
                )
                with gr.Row():
                    gen_next_paragraph_button = gr.Button("生成下一段", visible=False)
                    gen_ending_button = gr.Button("生成结局", visible=False)
                    download_novel_button = gr.Button("下载小说", visible=False)
        
        with gr.Column(scale=1, elem_id="row2"):
            gr.Markdown("### 创作对话记录")
            chat_history = gr.Chatbot(
                [],
                label="对话历史",
                elem_id="chatbot",
                height=600,
                show_label=False,
                elem_classes=["scrollable-chat"]
            )
    
    # 公文创作界面
    with gr.Row(visible=False) as document_interface:
        with gr.Column(scale=1):
            with gr.Tab("公文生成"):
                doc_type = gr.Dropdown(
                    ["通知", "请示", "函", "报告"],
                    label="公文类型",
                    value="通知"
                )
                doc_requirements = gr.Textbox(
                    "请描述您需要生成的公文内容要求",
                    label="内容要求",
                    lines=10,
                    interactive=True
                )
                voice_input_button = gr.Button(value="语音输入")
                voice_input_button.click(
                    handle_voice_input,
                    [user_idea_text],
                    [user_idea_text]
                )

                process_doc_button = gr.Button("生成公文", variant="primary")
                
            with gr.Tab("公文预览"):
                doc_preview = gr.Textbox(
                    "",
                    label="公文预览",
                    lines=20,
                    interactive=True,
                    elem_classes=["document-preview"]
                )
                download_doc_button = gr.Button("下载公文", visible=False)
        
        with gr.Column(scale=1):
            gr.Markdown("### 公文对话记录")
            doc_chat_history = gr.Chatbot(
                [],
                label="公文对话",
                height=600,
                show_label=False
            )
    
    # 剧本创作界面
    with gr.Row(visible=False) as script_interface:
        with gr.Column(scale=1):
            with gr.Tab("创意构思"):
                script_user_idea = gr.Textbox(
                    "请描述您的剧本创意",
                    label="创意构思",
                    lines=7,
                    interactive=True
                )
                voice_input_button = gr.Button(value="语音输入")
                voice_input_button.click(
                        handle_voice_input,
                        [user_idea_text],
                        [user_idea_text]
                    )

                with gr.Accordion("场景设置", open=False):
                    scene_count = gr.Number(
                        label="场景数量",
                        value=8,
                        minimum=3,
                        maximum=50,
                        step=1,
                        interactive=True
                    )
                    word_count_per_scene = gr.Number(
                        label="每场景字数",
                        value=800,
                        minimum=300,
                        maximum=5000,
                        step=100,
                        interactive=True
                    )
                script_user_requirements = gr.Textbox(
                    "",
                    label="剧本要求",
                    lines=7,
                    interactive=True
                )
                voice_input_button = gr.Button(value="语音输入")
                voice_input_button.click(
                        handle_voice_input,
                        [user_idea_text],
                        [user_idea_text]
                    )

                gen_script_outline_button = gr.Button("生成剧本大纲", variant="primary")
                
            with gr.Tab("剧本大纲"):
                script_outline_text = gr.Textbox(
                    "",
                    label="剧本大纲",
                    lines=15,
                    interactive=True
                )
                gen_script_beginning_button = gr.Button("生成开头", visible=False)
                
            with gr.Tab("剧本正文"):
                script_working_plan = gr.Textbox(
                    "",
                    label="工作计划",
                    lines=5,
                    interactive=True
                )
                script_temp_setting = gr.Textbox(
                    "",
                    label="临时设定",
                    lines=5,
                    interactive=True
                )
                script_memory = gr.Textbox(
                    "",
                    label="创作记忆",
                    lines=5,
                    interactive=True
                )
                script_content = gr.Textbox(
                    "",
                    label="剧本内容",
                    lines=15,
                    interactive=True,
                    elem_classes=["script-content"]
                )
                with gr.Row():
                    gen_next_scene_button = gr.Button("生成下一场", visible=False)
                    gen_script_ending_button = gr.Button("生成结局", visible=False)
                    download_script_button = gr.Button("下载剧本", visible=False)
        
        with gr.Column(scale=1):
            gr.Markdown("### 剧本创作对话")
            script_chat_history = gr.Chatbot(
                [],
                label="剧本对话",
                height=600,
                show_label=False,
                elem_classes=["script-panel"]
            )

    # 小说创作事件绑定
    gen_ouline_button.click(
        gen_ouline_button_clicked,
        [aign, user_idea_text, chat_history, chapter_count, word_count_per_chapter],
        [aign, chat_history, novel_outline_text, gen_beginning_button, gen_next_paragraph_button, gen_ending_button, download_novel_button]
    )
    
    gen_beginning_button.click(
        gen_beginning_button_clicked,
        [aign, chat_history, novel_outline_text, user_requriments_text, embellishment_idea_text],
        [aign, chat_history, writing_plan_text, temp_setting_text, novel_content_text, gen_next_paragraph_button, gen_ending_button, download_novel_button]
    )
    
    gen_next_paragraph_button.click(
        gen_next_paragraph_button_clicked,
        [aign, chat_history, user_idea_text, novel_outline_text, writing_memory_text, temp_setting_text, writing_plan_text, user_requriments_text, embellishment_idea_text],
        [aign, chat_history, writing_plan_text, temp_setting_text, writing_memory_text, novel_content_text, gen_next_paragraph_button, gen_ending_button, download_novel_button]
    )
    
    gen_ending_button.click(
        gen_ending_button_clicked,
        [aign, chat_history, user_requriments_text, novel_content_text],
        [aign, chat_history, writing_plan_text, temp_setting_text, writing_memory_text, novel_content_text, gen_next_paragraph_button, gen_ending_button, download_novel_button]
    )
    
    download_novel_button.click(
        download_novel,
        [],
        [download_novel_button]
    )
    
    # 公文创作事件绑定
    process_doc_button.click(
        process_document_request,
        [doc_type, doc_requirements, doc_chat_history],
        [doc_chat_history, doc_preview, download_doc_button]
    )
    
    download_doc_button.click(
        download_document,
        [doc_type, doc_preview],
        [download_doc_button]
    )
    
    # 剧本创作事件绑定
    gen_script_outline_button.click(
        gen_script_outline_button_clicked,
        [script_aign, script_user_idea, script_chat_history, scene_count, word_count_per_scene],
        [script_aign, script_chat_history, script_outline_text, gen_script_beginning_button]
    )
    
    gen_script_beginning_button.click(
        gen_script_beginning_button_clicked,
        [script_aign, script_chat_history, script_outline_text, script_user_requirements],
        [script_aign, script_chat_history, script_working_plan, script_temp_setting, script_content, gen_next_scene_button]
    )
    
    gen_next_scene_button.click(
        gen_next_scene_button_clicked,
        [script_aign, script_chat_history, script_user_idea, script_outline_text, script_memory, script_temp_setting, script_working_plan, script_user_requirements],
        [script_aign, script_chat_history, script_working_plan, script_temp_setting, script_memory, script_content]
    )
    
    gen_script_ending_button.click(
        gen_script_ending_button_clicked,
        [script_aign, script_chat_history, script_user_requirements, script_content],
        [script_aign, script_chat_history, script_working_plan, script_temp_setting, script_memory, script_content, download_script_button]
    )
    
    download_script_button.click(
        download_script,
        [],
        [download_script_button]
    )
    
    # 界面切换事件
    switch_btn.click(
        lambda x: "document" if x == "fiction" else ("script" if x == "document" else "fiction"),
        [current_mode],
        [current_mode],
    ).then(
        toggle_interface,
        [current_mode],
        [fiction_interface, document_interface, script_interface, switch_btn]
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
