import os
import re
import json
import time
from datetime import datetime
from Prompt.AIGC_Prompt import *
 
def Retryer(func, max_retries=10):
    def wrapper(*args, **kwargs):
        for _ in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print("-" * 30 + f"\n失败：\n{e}\n" + "-" * 30)
                time.sleep(2.333)
        raise ValueError("失败")

    return wrapper


class MarkdownAgent:
    """专门应对输入输出都是md格式的情况，例如小说生成"""

    def __init__(
        self,
        chatLLM,
        sys_prompt: str,
        name: str,
        temperature=0.8,
        top_p=0.8,
        use_memory=False,
        first_replay="明白了。",
        # first_replay=None,
        is_speak=True,
    ) -> None:

        self.chatLLM = chatLLM
        self.sys_prompt = sys_prompt
        self.temperature = temperature
        self.top_p = top_p
        self.use_memory = use_memory
        self.is_speak = is_speak

        self.history = [{"role": "user", "content": self.sys_prompt}]

        if first_replay:
            self.history.append({"role": "assistant", "content": first_replay})
        else:
            resp = chatLLM(messages=self.history)
            self.history.append({"role": "assistant", "content": resp["content"]})
            # if self.is_speak:
            #     self.speak(Msg(self.name, resp["content"]))

    def query(self, user_input: str) -> str:
        resp = self.chatLLM(
            messages=self.history + [{"role": "user", "content": user_input}],
            temperature=self.temperature,
            top_p=self.top_p,
        )
        if self.use_memory:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": resp["content"]})

        return resp

    def getOutput(self, input_content: str, output_keys: list) -> dict:
        """解析类md格式中 # key 的内容，未解析全部output_keys中的key会报错"""
        resp = self.query(input_content)
        output = resp["content"]

        lines = output.split("\n")
        sections = {}
        current_section = ""
        for line in lines:
            if line.startswith("# ") or line.startswith(" # "):
                # new key
                current_section = line[2:].strip()
                sections[current_section] = []
            else:
                # add content to current key
                if current_section:
                    sections[current_section].append(line.strip())
        for key in sections.keys():
            sections[key] = "\n".join(sections[key]).strip()

        for k in output_keys:
            if (k not in sections) or (len(sections[k]) == 0):
                raise ValueError(f"fail to parse {k} in output:\n{output}\n\n")

        # if self.is_speak:
        #     self.speak(
        #         Msg(
        #             self.name,
        #             f"total_tokens: {resp['total_tokens']}\n{resp['content']}\n",
        #         )
        #     )
        return sections

    def invoke(self, inputs: dict, output_keys: list) -> dict:
        input_content = ""
        for k, v in inputs.items():
            if isinstance(v, str) and len(v) > 0:
                input_content += f"# {k}\n{v}\n\n"

        result = Retryer(self.getOutput)(input_content, output_keys)

        return result

    def clear_memory(self):
        if self.use_memory:
            self.history = self.history[:2]
class GovernmentDocumentSystem:
    def __init__(self, chatLLM):
        self.chatLLM = chatLLM
        self.current_doc = {}
        self.history_versions = []
        self.department_comments = []
        
        # 初始化四大核心模块
        self.content_generator = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=content_generator_prompt,
            name="公文生成引擎",
            temperature=0.2,
            first_replay="政务AI就绪"
        )
        
        self.compliance_checker = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=compliance_checker_prompt,
            name="合规审查系统",
            temperature=0.1,
            first_replay="合规审查系统启动"
        )
        
        self.format_validator = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=format_validator_prompt,
            name="格式校验引擎",
            temperature=0.1,
            first_replay="格式校验就绪"
        )
        
        self.coordinator = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=coordinator_prompt,
            name="协同办公中枢",
            temperature=0.3,
            first_replay="协同系统在线"
        )
    
    def generate_draft(self, task_background, policy_data, user_requirements):
        """公文起草核心方法"""
        try:
            # 生成初始版本
            draft = self.content_generator.invoke(
                inputs={
                    "任务背景": task_background,
                    "政策数据库": policy_data,
                    "用户需求": user_requirements
                },
                output_keys=["公文内容", "版本号"]
            )
            
            # 初始化文档对象
            self.current_doc = {
                "content": draft["公文内容"],
                "version": draft["版本号"],
                "timestamp": datetime.now().strftime("%Y%m%d-%H%M%S"),
                "audit_trail": []
            }
            
            # 自动触发首次合规检查
            check_result = self._compliance_check()
            self._update_audit("自动初审", check_result)
            
            return self._wrap_output("草案生成成功", draft)
            
        except Exception as e:
            return self._wrap_error("草案生成失败", str(e))

    def _compliance_check(self):
        """合规性检查内部方法"""
        try:
            check_result = self.compliance_checker.invoke(
                inputs={"待审公文": self.current_doc["content"]},
                output_keys=["审查报告"]
            )
            return json.loads(check_result["审查报告"])
            
        except json.JSONDecodeError:
            return {"risk_level": "高", "illegal_clauses": [{"位置":"全局","问题类型":"格式错误"}]}

    def _update_audit(self, stage, result):
        """更新审查记录"""
        audit_entry = {
            "stage": stage,
            "timestamp": datetime.now().isoformat(),
            "result": result
        }
        self.current_doc["audit_trail"].append(audit_entry)

    def process_revisions(self, comments):
        """处理部门意见"""
        try:
            # 保存原始版本
            self.history_versions.append(self.current_doc.copy())
            
            # 生成修订版本
            revised = self.coordinator.invoke(
                inputs={
                    "原始草案": self.current_doc["content"],
                    "部门意见": json.dumps(comments, ensure_ascii=False)
                },
                output_keys=["修订文档"]
            )
            
            # 更新当前文档
            self.current_doc["content"] = revised["修订文档"]
            self.current_doc["version"] = f"V{datetime.now().strftime('%Y%m%d')}-Rev{len(self.history_versions)}"
            
            # 触发自动复核
            format_check = self.format_validator.invoke(
                inputs={"原始文档": self.current_doc["content"]},
                output_keys=["格式报告"]
            )
            self._update_audit("修订复核", json.loads(format_check["格式报告"]))
            
            return self._wrap_output("修订完成", {
                "new_version": self.current_doc["version"],
                "changes": len(comments)
            })
            
        except Exception as e:
            return self._wrap_error("修订处理失败", str(e))

    def finalize_document(self):
        """定稿处理"""
        try:
            # 生成最终PDF版本
            final_check = self.format_validator.invoke(
                inputs={"原始文档": self.current_doc["content"]},
                output_keys=["终版验证"]
            )
            
            if "通过" in final_check["终版验证"]:
                self.current_doc["status"] = "已签发"
                self._archive_document()
                return self._wrap_output("定稿成功", {
                    "document_id": f"DOC-{datetime.now().strftime('%Y%m%d')}-{len(self.history_versions)}",
                    "effective_date": datetime.now().strftime("%Y-%m-%d")
                })
            else:
                return self._wrap_error("定稿失败", final_check["终版验证"])
                
        except Exception as e:
            return self._wrap_error("定稿流程异常", str(e))

    def _archive_document(self):
        """文档归档"""
        archive_record = {
            "metadata": {
                "文种": self._detect_doc_type(),
                "密级": self._detect_security_level(),
                "签发人": "系统自动签发"
            },
            "content": self.current_doc["content"],
            "versions": self.history_versions
        }
        # 此处添加实际存储逻辑

    def _detect_doc_type(self):
        """识别公文种类"""
        if "通知" in self.current_doc["content"]:
            return "通知"
        elif "请示" in self.current_doc["content"]:
            return "请示"
        else:
            return "函"

    def _wrap_output(self, status, data):
        """标准化成功输出"""
        return {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "data": data,
            "current_version": self.current_doc["version"]
        }

    def _wrap_error(self, error_type, detail):
        """标准化错误输出"""
        return {
            "status": "error",
            "error_type": error_type,
            "detail": detail,
            "recovery_suggestion": "请检查输入格式或联系系统管理员"
        }
