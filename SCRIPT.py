# import os
# import re
# import time

# from Prompt.script_Prompt import *

# class MarkdownAgent:
#     """
#     处理输入输出均为 Markdown 格式的通用智能体，
#     支持容错解析，如解析失败则返回完整文本。
#     """
#     def __init__(
#         self, chatLLM, sys_prompt: str, name: str,
#         temperature=0.8, top_p=0.8, use_memory=False,
#         first_replay="明白了。"
#     ):
#         self.chatLLM = chatLLM
#         self.sys_prompt = sys_prompt
#         self.temperature = temperature
#         self.top_p = top_p
#         self.use_memory = use_memory
#         self.history = [{"role": "user", "content": self.sys_prompt}]
#         if first_replay:
#             self.history.append({"role": "assistant", "content": first_replay})
#         else:
#             resp = chatLLM(messages=self.history)
#             self.history.append({"role": "assistant", "content": resp.get("content", "")})

#     def query(self, user_input: str) -> dict:
#         resp = self.chatLLM(
#             messages=self.history + [{"role": "user", "content": user_input}],
#             temperature=self.temperature,
#             top_p=self.top_p
#         )
#         if self.use_memory:
#             self.history.append({"role": "user", "content": user_input})
#             self.history.append({"role": "assistant", "content": resp.get("content", "")})
#         return resp

#     def getOutput(self, input_content: str, output_keys: list) -> dict:
#         resp = self.query(input_content)
#         output = resp.get("content", "")
#         try:
#             # 按层级标题解析
#             lines = output.split("\n")
#             sections = {}
#             current = None
#             for line in lines:
#                 m = re.match(r"^\s*#{1,}\s*(.+?)\s*$", line)
#                 if m:
#                     current = m.group(1).strip()
#                     sections[current] = []
#                 elif current:
#                     sections[current].append(line.rstrip())
#             # 整理
#             for k in sections:
#                 sections[k] = "\n".join(sections[k]).strip()
#             # 检查
#             for key in output_keys:
#                 if key not in sections or not sections[key]:
#                     raise ValueError("missing key")
#             return {key: sections[key] for key in output_keys}
#         except Exception:
#             # 容错：返回完整文本
#             return {key: output for key in output_keys}

# class ScriptAIGN:
#     """
#     短剧剧本创作多智能体协同系统。
#     """
#     def __init__(self, chatLLM):
#         self.chatLLM = chatLLM
#         self.script_outline = ""
#         self.scene_list = []
#         self.script_content = ""
#         self.script_memory = ""
#         self.no_memory_scene = ""
#         self.user_idea = ""
#         self.user_requirements = ""
#         self.working_plan = ""
#         self.temp_setting = ""
#         self.record_file = "script_record.md"
#         self.history_stack = []
#         self.max_history = 5

#         self.master_director = MarkdownAgent(chatLLM, master_director_prompt, "MasterDirector", temperature=0.85)
#         self.creative_architect = MarkdownAgent(chatLLM, creative_architect_prompt, "CreativeArchitect", temperature=0.90)
#         self.scene_engineer = MarkdownAgent(chatLLM, scene_engineer_prompt, "SceneEngineer", temperature=0.80)
#         self.dialogue_alchemist = MarkdownAgent(chatLLM, dialogue_alchemist_prompt, "DialogueAlchemist", temperature=0.80)
#         self.cultural_guardian = MarkdownAgent(chatLLM, cultural_guardian_prompt, "CulturalGuardian", temperature=0.80)

#     def updateScriptContent(self):
#         self.script_content = "".join(f"{scene}\n\n" for scene in self.scene_list)
#         return self.script_content

#     def genScriptOutline(self, user_idea=None):
#         if user_idea: self.user_idea = user_idea
#         resp = self.creative_architect.getOutput(
#             input_content=f"# 创意brief\n{self.user_idea}\n\n",
#             output_keys=["剧本大纲"]
#         )
#         self.script_outline = resp["剧本大纲"]
#         return self.script_outline

#     def genBeginning(self, user_requirements=None):
#         if user_requirements: self.user_requirements = user_requirements
#         resp = self.master_director.getOutput(
#             input_content=f"# 剧本大纲\n{self.script_outline}\n# 用户要求\n{self.user_requirements}\n\n",
#             output_keys=["剧本总纲"]
#         )
#         plan = resp["剧本总纲"]
#         self.working_plan = plan
#         scene_resp = self.scene_engineer.getOutput(
#             input_content=f"# 剧本总纲\n{plan}\n\n",
#             output_keys=["场景描述"]
#         )
#         setting = scene_resp["场景描述"]
#         self.temp_setting = setting
#         combined = f"{plan}\n\n{setting}"
#         self.scene_list.append(combined)
#         self.updateScriptContent()
#         return combined

#     def getLastScene(self, max_length=2000):
#         last = ""
#         for s in reversed(self.scene_list):
#             if len(last) + len(s) < max_length:
#                 last = f"{s}\n{last}"
#             else:
#                 break
#         return last

#     def genNextScene(self, user_requirements=None):
#         if user_requirements: self.user_requirements = user_requirements
#         prev = self.getLastScene()
#         resp = self.scene_engineer.getOutput(
#             input_content=f"# 剧本大纲\n{self.script_outline}\n# 前文记忆\n{self.script_memory}\n# 上文内容\n{prev}\n\n",
#             output_keys=["场景描述"]
#         )
#         next_scene = resp["场景描述"]
#         self.scene_list.append(next_scene)
#         self.no_memory_scene += f"\n{next_scene}"
#         self.updateScriptContent()
#         return next_scene

#     def genEnding(self, user_requirements=None):
#         if user_requirements: self.user_requirements = user_requirements
#         prev = self.getLastScene(3000)
#         resp = self.master_director.getOutput(
#             input_content=f"# 完整大纲\n{self.script_outline}\n# 前文记忆\n{self.script_memory}\n# 用户要求\n{self.user_requirements}\n# 上文内容\n{prev}\n\n",
#             output_keys=["剧本总纲","分镜建议","版本信息"]
#         )
#         ending = f"{resp['剧本总纲']}\n\n# 分镜建议\n{resp['分镜建议']}\n\n# 版本信息\n{resp['版本信息']}"
#         self.scene_list.append(ending)
#         self.updateScriptContent()
#         return ending

#     def clearHistory(self):
#         self.history_stack = []
import os
import re
import time
from threading import Lock
from Prompt.script_Prompt import *
import queue
class MarkdownAgent:
    """
    处理输入输出均为 Markdown 格式的通用智能体，
    支持容错解析，如解析失败则返回完整文本。
    """
    def __init__(
        self, chatLLM, sys_prompt: str, name: str,
        temperature=0.8, top_p=0.8, use_memory=False,
        first_replay="明白了。"
    ):
        self.chatLLM = chatLLM
        self.sys_prompt = sys_prompt
        self.temperature = temperature
        self.top_p = top_p
        self.use_memory = use_memory
        self.history = [{"role": "user", "content": self.sys_prompt}]
        if first_replay:
            self.history.append({"role": "assistant", "content": first_replay})
        else:
            resp = chatLLM(messages=self.history)
            self.history.append({"role": "assistant", "content": resp.get("content", "")})

    def query(self, user_input: str) -> dict:
        resp = self.chatLLM(
            messages=self.history + [{"role": "user", "content": user_input}],
            temperature=self.temperature,
            top_p=self.top_p
        )
        if self.use_memory:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": resp.get("content", "")})
        return resp

    def getOutput(self, input_content: str, output_keys: list) -> dict:
        resp = self.query(input_content)
        output = resp.get("content", "")
        try:
            lines = output.split("\n")
            sections = {}
            current = None
            for line in lines:
                m = re.match(r"^\s*#{1,}\s*(.+?)\s*$", line)
                if m:
                    current = m.group(1).strip()
                    sections[current] = []
                elif current:
                    sections[current].append(line.rstrip())
            for k in sections:
                sections[k] = "\n".join(sections[k]).strip()
            for key in output_keys:
                if key not in sections or not sections[key]:
                    raise ValueError("missing key")
            return {key: sections[key] for key in output_keys}
        except Exception:
            return {key: output for key in output_keys}

class ScriptAIGN:
    """
    短剧剧本创作多智能体协同系统。
    """
    def __init__(self, chatLLM):
        
        self.chatLLM = chatLLM
        self.script_outline = ""
        self.scene_list = []
        self.script_content = ""
        self.script_memory = ""
        self.no_memory_scene = ""
        self.user_idea = ""
        self.user_requirements = ""
        self.working_plan = ""
        self.temp_setting = ""
        self.record_file = "script_record.md"
        self.history_stack = []
        self.max_history = 5
        self.current_scene = 0  
        self.total_scenes = 8
        self.master_director = MarkdownAgent(chatLLM, master_director_prompt, "MasterDirector", temperature=0.85)
        self.creative_architect = MarkdownAgent(chatLLM, creative_architect_prompt, "CreativeArchitect", temperature=0.90)
        self.scene_engineer = MarkdownAgent(chatLLM, scene_engineer_prompt, "SceneEngineer", temperature=0.80)
        self.dialogue_alchemist = MarkdownAgent(chatLLM, dialogue_alchemist_prompt, "DialogueAlchemist", temperature=0.80)
        self.cultural_guardian = MarkdownAgent(chatLLM, cultural_guardian_prompt, "CulturalGuardian", temperature=0.80)
    
    def updateScriptContent(self):
        self.script_content = "\n\n".join(self.scene_list)
        return self.script_content

    def genScriptOutline(self, user_idea=None):
        if user_idea: self.user_idea = user_idea
        resp = self.creative_architect.getOutput(
            input_content=f"# 创意brief\n{self.user_idea}\n\n",
            output_keys=["剧本大纲"]
        )
        self.script_outline = resp["剧本大纲"]
        return self.script_outline

    def genBeginning(self, user_requirements=None):
        """ 仅生成第一个场景 """
        if user_requirements: 
            self.user_requirements = user_requirements
        
        # 明确生成开头的提示语
        resp = self.master_director.getOutput(
            input_content=f"# 剧本大纲\n{self.script_outline}\n# 用户要求\n{self.user_requirements}\n# 生成模式：场景开头",
            output_keys=["剧本总纲"]
        )
        
        # 生成单个场景
        scene_resp = self.scene_engineer.getOutput(
            input_content=f"# 剧本总纲\n{resp['剧本总纲']}\n# 生成要求：仅生成第一个场景",
            output_keys=["场景描述"]
        )
        
        # 生成单场景对话
        dialogue_resp = self.dialogue_alchemist.getOutput(
            input_content=f"# 场景描述\n{scene_resp['场景描述']}",
            output_keys=["对白"]
        )
        
        # 仅添加首个场景
        combined = f"## 第1场/{self.total_scenes}场\n# 场景描述\n{scene_resp['场景描述']}\n# 对白\n{dialogue_resp['对白']}"
        if not self.scene_list:
            self.scene_list.append(combined)
            self.current_scene = 1  # 初始化计数器
            
        self.updateScriptContent()
        return combined
    def getLastScene(self, max_length=2000):
        last = ""
        for s in reversed(self.scene_list):
            if len(last) + len(s) < max_length:
                last = f"{s}\n{last}"
            else:
                break
        return last

    def genNextScene(self, user_requirements=None):
        
            """ 分步生成后续场景 """
            if self.current_scene >= self.total_scenes:
                return "所有场景已完成"
                
            self.current_scene += 1
            
            # 添加进度提示
            prev = f"前{self.current_scene-1}场内容摘要：\n{self._summarize_prev_scenes()}"
            
            scene_resp = self.scene_engineer.getOutput(
                input_content=f"{prev}\n# 生成要求：第{self.current_scene}场场景",
                output_keys=["场景描述"]
            )
            
            dialogue_resp = self.dialogue_alchemist.getOutput(
                input_content=f"# 当前进度：第{self.current_scene}场\n{scene_resp['场景描述']}",
                output_keys=["对白"]
            )
            
            new_scene = f"## 第{self.current_scene}场/{self.total_scenes}场\n# 场景描述\n{scene_resp['场景描述']}\n# 对白\n{dialogue_resp['对白']}"
            self.scene_list.append(new_scene)
            return new_scene
    def genEnding(self, user_requirements=None):
        if user_requirements: self.user_requirements = user_requirements
        prev = self.getLastScene(3000)
        resp = self.master_director.getOutput(
            input_content=f"# 完整大纲\n{self.script_outline}\n# 前文记忆\n{self.script_memory}\n# 用户要求\n{self.user_requirements}\n# 上文内容\n{prev}\n\n",
            output_keys=["剧本总纲","分镜建议","版本信息"]
        )
        ending = f"# 剧本总纲\n{resp['剧本总纲']}\n\n# 分镜建议\n{resp['分镜建议']}\n\n# 版本信息\n{resp['版本信息']}"
        self.scene_list.append(ending)
        self.updateScriptContent()
        return ending
    def _summarize_prev_scenes(self):
        """ 生成前情摘要 """
        return "\n".join([s.split("# 对白")[0] for s in self.scene_list[-3:]])  # 取最近3场摘要
    def clearHistory(self):
        self.history_stack = []
