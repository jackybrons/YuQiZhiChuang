# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
from aliyunsdkcore.request import CommonRequest
import json

class Config:
    # 阿里云配置（请确认以下信息已更新）
    ALIYUN_ACCESS_ID = os.environ.get("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY = os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "")
    ALIYUN_REGION = "cn-hangzhou"
    ALIYUN_NLP_ENDPOINT = "alinlp.cn-hangzhou.aliyuncs.com"
    ALIYUN_NLP_VERSION = "2020-06-29"
    ALIYUN_NLP_SERVICE = "alinlp"

def print_color(text, color='green'):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'end': '\033[0m'
    }
    print(f"{colors[color]}{text}{colors['end']}")

def test_aliyun_api():
    """测试阿里云API是否可用"""
    print("\n🔍 开始测试阿里云API权限...")
    
    # 1. 测试基础连接
    try:
        client = AcsClient(
            Config.ALIYUN_ACCESS_ID,
            Config.ALIYUN_ACCESS_KEY,
            Config.ALIYUN_REGION
        )
        print_color("✓ 阿里云客户端初始化成功", 'green')
    except Exception as e:
        print_color(f"✗ 客户端初始化失败: {str(e)}", 'red')
        return False
    
    # 2. 测试多种NLP API（兼容性方案）
    apis_to_test = [
        {
            'name': '情感分析(新版)',
            'action': 'GetSaChGeneral',
            'params': {'Text': '今天天气真好', 'ServiceCode': Config.ALIYUN_NLP_SERVICE}
        },
        {
            'name': '文本相似度',
            'action': 'GetWsChGeneral',
            'params': {'Text': '测试文本', 'ServiceCode': Config.ALIYUN_NLP_SERVICE}
        },
        {
            'name': '基础文本分析',
            'action': 'GetTcChGeneral',
            'params': {'Text': '测试文本', 'ServiceCode': Config.ALIYUN_NLP_SERVICE}
        }
    ]
    
    success = False
    for api in apis_to_test:
        try:
            print(f"\n正在测试 {api['name']} API ({api['action']})...")
            request = CommonRequest()
            request.set_domain(Config.ALIYUN_NLP_ENDPOINT)
            request.set_version(Config.ALIYUN_NLP_VERSION)
            request.set_action_name(api['action'])
            request.set_protocol_type('https')
            request.set_method('POST')
            
            for key, value in api['params'].items():
                request.add_query_param(key, value)
            
            response = client.do_action_with_exception(request)
            result = json.loads(response)
            
            if 'Data' in result:
                print_color(f"✓ {api['name']} API调用成功", 'green')
                print("返回结果示例:")
                print(json.dumps(json.loads(result['Data']), indent=2, ensure_ascii=False))
                success = True
                break
            else:
                print_color(f"⚠ {api['name']} API返回数据异常", 'yellow')
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
        except ClientException as e:
            if e.error_code == "Forbidden.NoPermission":
                print_color(f"✗ {api['name']} API权限不足: {e.message}", 'red')
            else:
                print_color(f"✗ {api['name']} API调用失败: {e.error_code} - {e.message}", 'red')
        except Exception as e:
            print_color(f"✗ {api['name']} API测试异常: {str(e)}", 'red')
    
    if not success:
        print_color("\n❌ 所有API测试均未通过，请检查以下内容：", 'red')
        print("1. 确认已开通自然语言处理服务")
        print("2. 检查RAM权限：需AliyunNLPFullAccess权限")
        print("3. 确认AccessKey有效且未过期")
        print("4. 检查账户余额（部分API需要余额>0）")
        print("5. 确认地域和endpoint配置正确")
        print("6. 参考最新API文档：https://help.aliyun.com/document_detail/177834.html")
        return False
    
    return True

if __name__ == "__main__":
    print("="*50)
    print("阿里云NLP API兼容性测试工具")
    print("="*50)
    
    if test_aliyun_api():
        print_color("\n✅ 至少有一个API测试通过，服务基本可用", 'green')
    else:
        print_color("\n❌ 所有API测试均未通过，请根据提示检查", 'red')
    
    print("\n测试完成")
