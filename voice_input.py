# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

import base64
import requests
import json
import sounddevice as sd
import soundfile as sf
import numpy as np
import time
import threading
import matplotlib.pyplot as plt
from queue import Queue
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.asr.v20190614 import asr_client, models
from scipy.signal import resample, find_peaks
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
from aliyunsdkcore.request import CommonRequest
import threading

# 用于跟踪语音输入状态的变量
is_recording = threading.Event()
stop_recording = threading.Event()

class Config:
    # 腾讯云配置
    MODEL = "qwen-plus-latest"
    SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
    SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")
    REGION = "ap-guangzhou"
    
    # Mindcraft配置
    MINDCRAFT_API_KEY = os.environ.get("MINDCRAFT_API_KEY", "")
    MINDCRAFT_API_URL = "https://api.mindcraft.com.cn/v1/chat/completions"

    # 阿里云配置（更新为已验证的配置）
    ALIYUN_ACCESS_ID = os.environ.get("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY = os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "")
    ALIYUN_REGION = "cn-hangzhou"
    ALIYUN_NLP_ENDPOINT = "alinlp.cn-hangzhou.aliyuncs.com"
    ALIYUN_NLP_VERSION = "2020-06-29"
    ALIYUN_NLP_SERVICE = "alinlp"

    # 音频参数
    RATE = 16000
    CHANNELS = 1
    DTYPE = 'int16'
    BUFFER_DURATION = 0.1
    WAVE_OUTPUT_FILENAME = "temp_record.wav"
    NORMALIZED_FILENAME = "normalized.wav"
    CHUNK_SIZE = 1024

audio_queue = Queue()
stop_recording = threading.Event()

EMOTION_MAP = {
    'angry': '愤怒',
    'happy': '高兴',
    'sad': '悲伤',
    'fear': '恐惧',
    'neutral': '中性',
    'positive': '积极',
    'negative': '消极'
}

def print_color(text, color='green'):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'end': '\033[0m'
    }
    print(f"{colors[color]}{text}{colors['end']}")

def init_aliyun_client():
    """初始化阿里云客户端"""
    return AcsClient(
        Config.ALIYUN_ACCESS_ID,
        Config.ALIYUN_ACCESS_KEY,
        Config.ALIYUN_REGION
    )

def analyze_emotion(text):
    """使用阿里云NLP情感分析API（更新为已验证版本）"""
    if len(text) < 15:
        print_color("文本过短，跳过情感分析", 'yellow')
        return None
    
    client = init_aliyun_client()
    
    # 创建通用请求（使用已验证的GetSaChGeneral API）
    request = CommonRequest()
    request.set_domain(Config.ALIYUN_NLP_ENDPOINT)
    request.set_version(Config.ALIYUN_NLP_VERSION)
    request.set_action_name('GetSaChGeneral')
    request.set_protocol_type('https')
    request.set_method('POST')
    
    # 设置请求参数
    request.add_query_param('ServiceCode', Config.ALIYUN_NLP_SERVICE)
    request.add_query_param('Text', text)
    request.add_query_param('TokenizerId', 'GENERAL_CHN')
    request.add_query_param('OutType', 'json')
    
    try:
        response = client.do_action_with_exception(request)
        result = json.loads(response)
        
        if 'Data' in result:
            data = json.loads(result['Data'])
            # 解析新版情感分析API返回格式
            if 'result' in data and 'sentiment' in data['result']:
                return {
                    'text': text,
                    'emotion': data['result']['sentiment'],
                    'score': float(data['result']['positive_prob']) if data['result']['sentiment'] == 'positive'
                             else 1 - float(data['result']['negative_prob'])
                }
        print_color(f"API返回格式异常: {result}", 'yellow')
        return None
    except (ClientException, ServerException) as e:
        print_color(f"阿里云API调用异常: {str(e)}", 'red')
        return None
    except Exception as e:
        print_color(f"情感分析异常: {str(e)}", 'red')
        return None

def analyze_audio_emotion(audio_file):
    """基于音频特征的情感分析"""
    try:
        data, rate = sf.read(audio_file)
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)
        
        # 计算基本特征
        intensity = np.mean(np.abs(data))
        peaks_info = find_peaks(data, height=0.2)
        
        # 计算语速(每秒钟的峰数)
        speech_rate = len(peaks_info[0]) / (len(data)/rate)
        avg_pitch = np.mean(extract_pitch(data)) if len(data) > 0 else 0
        
        # 情感判断规则
        if intensity > 0.15 and speech_rate > 5:
            return 'angry'
        elif intensity < 0.05 and speech_rate < 2:
            return 'sad'
        elif 0.4 < avg_pitch < 0.8 and speech_rate > 3:
            return 'happy'
        else:
            return 'neutral'
    except Exception as e:
        print_color(f"音频分析失败: {str(e)}", 'yellow')
        return None

def extract_pitch(audio_data, frame_size=1024, hop_size=512):
    """提取音频基频特征"""
    frames = []
    for i in range(0, len(audio_data)-frame_size, hop_size):
        frame = audio_data[i:i+frame_size]
        spectrum = np.abs(np.fft.rfft(frame))
        peaks = find_peaks(spectrum, height=0.1, distance=50)[0]
        if len(peaks) > 0:
            pitch = peaks[0] * Config.RATE / frame_size
            frames.append(pitch)
    return np.array(frames) if len(frames) > 0 else np.array([0])

def combined_emotion_analysis(text, audio_file):
    """综合文本和音频的情感分析 - 改进版"""
    text_emotion = analyze_emotion(text)
    audio_emotion = analyze_audio_emotion(audio_file)
    
    if not text_emotion and not audio_emotion:
        return None
    
    # 结果容器
    result = {
        'text_analysis': text_emotion,
        'audio_analysis': audio_emotion,
        'combined_result': {
            'emotion': '未知',
            'confidence': 0.5,
            'description': '无法确定情感状态'
        }
    }
    
    # 决策逻辑
    if text_emotion and audio_emotion:
        # 处理情感矛盾情况
        if (text_emotion['emotion'] == 'positive' and audio_emotion == 'sad'):
            result['combined_result'] = {
                'emotion': "矛盾情感(表面积极但隐含悲伤)",
                'confidence': (text_emotion['score'] + 0.5) / 2,
                'description': "文本内容表达积极但语音特征显示悲伤情绪"
            }
        elif (text_emotion['emotion'] == 'negative' and audio_emotion == 'happy'):
            result['combined_result'] = {
                'emotion': "矛盾情感(表面消极但隐含愉悦)",
                'confidence': (text_emotion['score'] + 0.5) / 2,
                'description': "文本内容表达消极但语音特征显示愉悦情绪"
            }
        elif text_emotion['emotion'] == 'neutral':
            result['combined_result'] = {
                'emotion': f"以语调为主: {EMOTION_MAP.get(audio_emotion, '中性')}",
                'confidence': 0.7,
                'description': "文本情感中性，主要依据语音特征判断"
            }
        else:
            # 一般情况以文本情感为主
            result['combined_result'] = {
                'emotion': EMOTION_MAP.get(text_emotion['emotion'], '未知'),
                'confidence': text_emotion['score'],
                'description': "主要依据文本内容判断"
            }
    
    elif text_emotion:
        result['combined_result'] = {
            'emotion': EMOTION_MAP.get(text_emotion['emotion'], '未知'),
            'confidence': text_emotion['score'],
            'description': "仅基于文本分析"
        }
    else:
        result['combined_result'] = {
            'emotion': EMOTION_MAP.get(audio_emotion, '未知'),
            'confidence': 0.6,
            'description': "仅基于语音特征分析"
        }
    
    return result

def list_input_devices():
    """列出可用音频输入设备"""
    devices = sd.query_devices()
    print_color("\n可用音频输入设备:", 'blue')
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            print(f"{i}: {dev['name']} (输入通道: {dev['max_input_channels']})")
    return True

def audio_callback(indata, frames, time, status):
    """音频回调函数"""
    if status:
        print_color(f"音频流状态: {status}", 'yellow')
    audio_queue.put(indata.copy())

def check_audio_quality(data, rate):
    """简单音频质量检查"""
    if np.max(np.abs(data)) < 0.00001:
        print_color("警告: 检测到静音或音量过低", 'yellow')
        return False
    return True

# voice_input.py 文件，从第256行开始
def record_audio():
    """录制音频"""
    print_color("\n🔴 正在录音... (按Ctrl+C停止)", 'red')
    
    try:
        with sf.SoundFile(Config.WAVE_OUTPUT_FILENAME, mode='w',
                         samplerate=Config.RATE, channels=Config.CHANNELS) as f:
            with sd.InputStream(samplerate=Config.RATE,
                               channels=Config.CHANNELS,
                               callback=audio_callback):
                while not stop_recording.is_set():
                    if not audio_queue.empty():
                        data = audio_queue.get()
                        if check_audio_quality(data, Config.RATE):
                            f.write(data)
            print("录音线程检测到停止标志，正在退出...")  # 添加调试信息
        stop_recording.clear()  # 录音结束后清除停止标志
        return Config.WAVE_OUTPUT_FILENAME
    except KeyboardInterrupt:
        print_color("\n检测到Ctrl+C，停止录音...", 'yellow')
        stop_recording.set()
        while is_recording.is_set():
            time.sleep(0.1)
        return Config.WAVE_OUTPUT_FILENAME
    except Exception as e:
        print_color(f"录音失败: {str(e)}", 'red')
        return None
    
def is_recording_active():
    """检查录音是否仍在进行"""
    return is_recording.is_set()

def normalize_audio(input_file, output_file):
    """音频归一化处理"""
    try:
        data, rate = sf.read(input_file)
        peak = np.max(np.abs(data))
        if peak > 0:
            data = data / peak
        sf.write(output_file, data, rate)
        return output_file
    except Exception as e:
        print_color(f"音频归一化失败: {str(e)}", 'yellow')
        return input_file

def init_tencent_client():
    """初始化腾讯云客户端"""
    cred = credential.Credential(Config.SECRET_ID, Config.SECRET_KEY)
    http_profile = HttpProfile()
    http_profile.endpoint = "asr.tencentcloudapi.com"
    
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    
    return asr_client.AsrClient(cred, Config.REGION, client_profile)

def realtime_asr(audio_file):
    """调用腾讯云ASR进行语音识别"""
    try:
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
        
        client = init_tencent_client()
        req = models.SentenceRecognitionRequest()
        
        req.ProjectId = 0
        req.SubServiceType = 2
        req.EngSerViceType = "16k_zh"
        req.SourceType = 1
        req.Data = base64.b64encode(audio_data).decode()
        req.DataLen = len(audio_data)
        req.VoiceFormat = "wav"
        
        resp = client.SentenceRecognition(req)
        if resp.Result:
            return resp.Result
        return None
    except Exception as e:
        print_color(f"语音识别失败: {str(e)}", 'red')
        return None

def generate_summary(text):
    """使用Mindcraft API生成文本摘要"""
    headers = {
        "Authorization": f"Bearer {Config.MINDCRAFT_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": Config.MODEL,
        "messages": [{"role": "user", "content": f"请用简洁的中文总结以下内容:\n{text}"}]
    }
    
    try:
        response = requests.post(Config.MINDCRAFT_API_URL,
                               headers=headers,
                               json=payload)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return None
    except Exception as e:
        print_color(f"摘要生成失败: {str(e)}", 'yellow')
        return None

def visualize_emotion_segments(text):
    """可视化文本情感分段分析"""
    if len(text) < 50:
        emotion = analyze_emotion(text)
        if emotion:
            print(f"\n情感分析: {EMOTION_MAP.get(emotion['emotion'])} (置信度: {emotion['score']:.2f})")
        return
    
    segments = min(5, len(text)//20)
    results = []
    for i in range(segments):
        start = i * (len(text)//segments)
        end = (i+1) * (len(text)//segments)
        segment = text[start:end]
        
        emotion = analyze_emotion(segment)
        if emotion:
            results.append({
                'segment': segment,
                'emotion': emotion['emotion'],
                'score': emotion['score'],
                'range': (start, end)
            })
    
    if results:
        print("\n分段情感分析:")
        for res in results:
            print(f"[{res['range'][0]}-{res['range'][1]}]: "
                 f"{EMOTION_MAP.get(res['emotion'])} (置信度: {res['score']:.2f})")
        
        try:
            plt.figure(figsize=(10,4))
            positions = [r['range'][0] for r in results]
            scores = [r['score'] for r in results]
            plt.plot(positions, scores, 'o-')
            plt.title("文本情感变化趋势")
            plt.xlabel("文本位置")
            plt.ylabel("情感分数")
            plt.grid(True)
            plt.savefig('emotion_trend.png')
            print_color("\n情感变化曲线已保存", 'green')
        except:
            pass

def cleanup():
    """清理临时文件"""
    for f in [Config.WAVE_OUTPUT_FILENAME,
             Config.NORMALIZED_FILENAME,
             'emotion_trend.png']:
        try:
            if os.path.exists(f):
                os.remove(f)
        except:
            pass

def test_aliyun_api():
    """测试阿里云API是否可用"""
    print("\n🔍 开始测试阿里云API权限...")
    
    try:
        client = init_aliyun_client()
        print_color("✓ 阿里云客户端初始化成功", 'green')
    except Exception as e:
        print_color(f"✗ 客户端初始化失败: {str(e)}", 'red')
        return False
    
    # 测试情感分析API
    test_text = "今天天气真好，我感到非常开心和满足！"
    print(f"\n测试文本: {test_text}")
    emotion_result = analyze_emotion(test_text)
    if emotion_result:
        print_color(f"✓ 情感分析测试成功 - 情感: {emotion_result['emotion']}, 分数: {emotion_result['score']:.2f}", 'green')
        return True
    else:
        print_color("✗ 情感分析测试失败", 'red')
        return False

def signal_handler(sig, frame):
    """处理Ctrl+C信号"""
    stop_recording.set()
    print_color("\n检测到停止信号...", 'yellow')

def main_loop():
    """主交互循环"""
    print("="*60)
    print_color("语音情感分析系统", 'blue')
    print("功能: 录音转写 | 情感分析 | 内容摘要")
    print(f"采样率: {Config.RATE}Hz | 声道数: {Config.CHANNELS}")
    print("="*60)
    
    # 测试API可用性
    if not test_aliyun_api():
        print_color("\n⚠ 阿里云API测试未通过，情感分析功能可能受限", 'yellow')
    else:
        print_color("\n✅ 阿里云API测试通过，所有功能可用", 'green')
    
    if not list_input_devices():
        return
    
    while True:
        try:
            input("\n🟢 按Enter开始录音 (Ctrl+C退出): ")
            
            # 录音处理
            audio_file = record_audio()
            if not audio_file:
                continue
                
            # 语音识别
            print("\n识别中...", end='', flush=True)
            text = realtime_asr(audio_file)
            if not text:
                print_color("\n识别无结果", 'yellow')
                continue
                
            print_color("\n✍️ 识别结果:", 'green')
            print(text)
            
            # 情感分析
            print("\n分析情感...", end='', flush=True)
            emotion_result = combined_emotion_analysis(text, audio_file)
            if emotion_result:
                print_color("\n🎭 情感分析结果:", 'blue')
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
                print_color("\n内容过短，无法生成摘要", 'yellow')
            else:
                summary = generate_summary(text)
                if summary:
                    print_color("\n📝 内容摘要:", 'green')
                    print(summary)
                else:
                    print_color("\n摘要生成失败", 'yellow')
                    
            # 保存结果
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            with open(f"result_{timestamp}.txt", 'w', encoding='utf-8') as f:
                f.write(f"识别文本:\n{text}\n\n")
                if emotion_result:
                    f.write(f"情感分析:\n{json.dumps(emotion_result, ensure_ascii=False, indent=2)}\n\n")
                if summary:
                    f.write(f"内容摘要:\n{summary}\n")
                print_color(f"\n✅ 分析结果已保存到 result_{timestamp}.txt", 'blue')
            
        except KeyboardInterrupt:
            print_color("\n👋 正在退出系统...", 'blue')
            break
        except Exception as e:
            print_color(f"\n❌ 处理异常: {str(e)}", 'red')
            continue
            
if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 初始化音频参数
        sd.default.samplerate = Config.RATE
        sd.default.channels = Config.CHANNELS
        sd.default.dtype = Config.DTYPE
        
        # 启动主循环
        main_loop()
    except Exception as e:
        print_color(f"系统启动失败: {str(e)}", 'red')
    finally:
        cleanup()
        print("系统已关闭")
