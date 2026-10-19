import os
import re
import json
import gradio as gr
from zhipuAI import zhipuChatLLM
from Prompt.AIGCwork_Prompt import (
    work_report_generator_prompt,
    report_compliance_checker_prompt,
    report_format_validator_prompt,
    report_coordinator_prompt,
)

# 使用环境变量配置智谱AI API Key，避免在界面中输入
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "57ecdcf0e2b7407a9800b2e58fc8b214.kXuA501N2Hcc2Q8N")

class MarkdownAgent:
    """
    针对输入输出均为 Markdown 格式的场景，
    用于与不同智能体（如报告生成、合规审查等）进行交互。
    """
    def __init__(
        self,
        chatLLM,
        sys_prompt: str,
        name: str,
        temperature=0.8,
        top_p=0.8,
        use_memory=False,
        first_reply="明白了。",
        is_speak=True,
    ) -> None:
        self.chatLLM = chatLLM
        self.sys_prompt = sys_prompt
        self.temperature = temperature
        self.top_p = top_p
        self.use_memory = use_memory
        self.is_speak = is_speak
        self.history = [{"role": "user", "content": self.sys_prompt}]
        if first_reply:
            self.history.append({"role": "assistant", "content": first_reply})

    def query(self, user_input: str) -> dict:
        resp = self.chatLLM(
            messages=self.history + [{"role": "user", "content": user_input}],
            temperature=self.temperature,
            top_p=self.top_p,
        )
        if self.use_memory:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": resp.get("content", "")})
        return resp

    def getOutput(self, input_content: str, output_keys: list) -> dict:
        resp = self.query(input_content)
        output = resp.get("content", "")
        # 如果包含 JSON 代码块，则直接解析并返回
        json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", output)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        # 否则按照标题分段解析
        lines = output.split("\n")
        sections = {}
        current_section = ""
        for line in lines:
            if line.startswith("# "):
                current_section = line[2:].strip()
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line.strip())
        for key, vals in sections.items():
            sections[key] = "\n".join(vals).strip()
        for k in output_keys:
            if k not in sections or not sections[k]:
                raise ValueError(f"未能解析输出中的 {k}，原始输出：\n{output}\n")
        return sections

    def invoke(self, inputs: dict, output_keys: list) -> dict:
        content = ""
        for k, v in inputs.items():
            if v:
                content += f"# {k}\n{v}\n\n"
        return self.getOutput(content, output_keys)


class WorkReportAIGN:
    """
    AI 多智能体协同工作报告生成系统
    """
    def __init__(self, chatLLM):
        self.chatLLM = chatLLM
        self.report_outline = ""
        self.report_content = ""
        self.history_stack = []
        # 各模块智能体
        self.report_generator = MarkdownAgent(chatLLM, work_report_generator_prompt, "ReportGenerator", temperature=0.85)
        self.compliance_checker = MarkdownAgent(chatLLM, report_compliance_checker_prompt, "ComplianceChecker", temperature=0.80)
        self.format_validator = MarkdownAgent(chatLLM, report_format_validator_prompt, "FormatValidator", temperature=0.80)
        self.coordinator = MarkdownAgent(chatLLM, report_coordinator_prompt, "Coordinator", temperature=0.85)

    def genReportOutline(self, user_idea: str):
        return self.report_generator.invoke(
            inputs={"用户需求": user_idea},
            output_keys=["报告大纲"]
        ).get("报告大纲", "")

    def genInitialDraft(self, background: str, data_support: str, user_demand: str, template: str):
        return self.report_generator.invoke(
            inputs={
                "报告背景": background,
                "数据支撑": data_support,
                "用户需求": user_demand,
                "格式模板": template
            },
            output_keys=["初稿"]
        ).get("初稿", "")

    def checkCompliance(self, draft: str):
        return self.compliance_checker.invoke(
            inputs={"待审报告": draft},
            output_keys=["risk_level", "illegal_clauses", "policy_conflicts", "recommendations"]
        )

    def validateFormat(self, draft: str):
        return self.format_validator.invoke(
            inputs={"原始报告": draft},
            output_keys=["页边距检测", "字体检测", "图表检测", "版记要素检测"]
        )

    def coordinateDepartments(self, dept_drafts: dict):
        combined = "".join([f"# {dept}\n{txt}\n\n" for dept, txt in dept_drafts.items()])
        return self.coordinator.invoke(
            inputs={"各部门草案": combined},
            output_keys=["修订草案", "意见汇总表", "争议点决策树", "会签页模板"]
        )


# 应用初始化，启动时直接创建
chatLLM = zhipuChatLLM(model_name="glm-4-plus", api_key=ZHIPU_API_KEY)
report_system = WorkReportAIGN(chatLLM)

# Gradio 接口函数

def generate_outline(requirements):
    try:
        return report_system.genReportOutline(requirements)
    except Exception as e:
        resp = report_system.report_generator.query(f"# 用户需求\n{requirements}\n\n")
        return resp.get("content", str(e))


def generate_draft(background, data_support, requirements, template):
    try:
        return report_system.genInitialDraft(background, data_support, requirements, template)
    except Exception as e:
        resp = report_system.report_generator.query(
            f"# 报告背景\n{background}\n\n# 数据支撑\n{data_support}\n\n# 用户需求\n{requirements}\n\n# 格式模板\n{template}\n\n"
        )
        return resp.get("content", str(e))


def run_compliance(draft):
    try:
        return report_system.checkCompliance(draft)
    except Exception as e:
        return {"error": str(e)}


def run_format(draft):
    try:
        return report_system.validateFormat(draft)
    except Exception as e:
        return {"error": str(e)}


def coordinate(dept_names, dept_drafts):
    try:
        names = [n.strip() for n in dept_names.split(',') if n.strip()]
        texts = [t.strip() for t in dept_drafts.split('||')]
        return report_system.coordinateDepartments(dict(zip(names, texts))).get("修订草案", "")
    except Exception as e:
        combined = "".join([f"# {d}\n{t}\n\n" for d, t in zip(names, texts)])
        resp = report_system.coordinator.query(f"# 各部门草案\n{combined}")
        return resp.get("content", str(e))

# Gradio UI
with gr.Blocks() as demo:
    gr.Markdown("# AI 多智能体公文生成助手")

    with gr.Tab("生成大纲"):
        req_input = gr.Textbox(label="用户需求", placeholder="请输入报告核心需求，如“2025年第一季度工作回顾”")
        outline_btn = gr.Button("生成大纲")
        outline_out = gr.Textbox(label="报告大纲", lines=5)
        outline_btn.click(generate_outline, inputs=req_input, outputs=outline_out)

    with gr.Tab("初稿生成"):
        bg_input = gr.Textbox(label="报告背景", placeholder="简要描述报告背景，如市场、产品或管理等方面的总结")
        data_input = gr.Textbox(label="数据支撑", placeholder="关键指标及数据来源，例如“销售额增长10%...”")
        req2_input = gr.Textbox(label="用户需求", placeholder="报告期望的输出或侧重点，如提出改进建议等")
        template_input = gr.Textbox(label="格式模板", placeholder="企业内部模板或通用格式说明")
        draft_btn = gr.Button("生成初稿")
        draft_out = gr.Textbox(label="初稿内容", lines=10)
        draft_btn.click(generate_draft, inputs=[bg_input, data_input, req2_input, template_input], outputs=draft_out)

    with gr.Tab("合规与格式"):
        draft2_input = gr.Textbox(label="报告草稿", lines=10, placeholder="粘贴或输入初稿内容以进行审查")
        comp_btn = gr.Button("合规审查")
        comp_out = gr.JSON(label="合规审查结果")
        fmt_btn = gr.Button("格式校验")
        fmt_out = gr.JSON(label="格式校验结果")
        comp_btn.click(run_compliance, inputs=draft2_input, outputs=comp_out)
        fmt_btn.click(run_format, inputs=draft2_input, outputs=fmt_out)

    with gr.Tab("多部门整合"):
        names_input = gr.Textbox(label="部门名称(逗号分隔)", placeholder="如：市场部,研发部,财务部")
        drafts_input = gr.Textbox(label="对应草案(用||分隔)", placeholder="各部门草案内容，用 || 分隔")
        coord_btn = gr.Button("整合生成")
        coord_out = gr.Textbox(label="最终修订草案", lines=10)
        coord_btn.click(coordinate, inputs=[names_input, drafts_input], outputs=coord_out)

if __name__ == "__main__":
    demo.launch(share=False)
