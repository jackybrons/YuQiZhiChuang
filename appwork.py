import os
import gradio as gr
from zhipuAI import zhipuChatLLM
from Prompt.AIGCwork_Prompt import (
    work_report_generator_prompt,
    report_compliance_checker_prompt,
    report_format_validator_prompt,
    report_coordinator_prompt,
)


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
        else:
            resp = chatLLM(messages=self.history)
            self.history.append({"role": "assistant", "content": resp["content"]})

    def query(self, user_input: str) -> dict:
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
        resp = self.query(input_content)
        output = resp["content"]
        lines = output.split("\n")
        sections = {}
        current_section = ""
        for line in lines:
            if line.startswith("# "):
                current_section = line[2:].strip()
                sections[current_section] = []
            else:
                if current_section:
                    sections[current_section].append(line.strip())
        for key in sections.keys():
            sections[key] = "\n".join(sections[key]).strip()
        for k in output_keys:
            if (k not in sections) or (len(sections[k]) == 0):
                raise ValueError(f"fail to parse {k} in output:\n{output}\n\n")
        return sections

    def invoke(self, inputs: dict, output_keys: list) -> dict:
        input_content = ""
        for k, v in inputs.items():
            if isinstance(v, str) and len(v) > 0:
                input_content += f"# {k}\n{v}\n\n"
        result = self.getOutput(input_content, output_keys)
        return result


class WorkReportAIGN:
    """
    AI 多智能体协同工作报告生成系统：
    包含初稿生成、合规性审查、格式校验及多部门协同整合等功能。
    """
    def __init__(self, chatLLM):
        self.chatLLM = chatLLM

        # 状态变量
        self.report_outline = ""
        self.report_content = ""
        self.history_stack = []
        self.max_history = 5

        # 初始化各智能体
        self.report_generator = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=work_report_generator_prompt,
            name="ReportGenerator",
            temperature=0.85,
        )
        self.compliance_checker = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=report_compliance_checker_prompt,
            name="ComplianceChecker",
            temperature=0.80,
        )
        self.format_validator = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=report_format_validator_prompt,
            name="FormatValidator",
            temperature=0.80,
        )
        self.coordinator = MarkdownAgent(
            chatLLM=self.chatLLM,
            sys_prompt=report_coordinator_prompt,
            name="Coordinator",
            temperature=0.85,
        )

    def genReportOutline(self, user_idea=None):
        if user_idea:
            self.user_requirements = user_idea
        resp = self.report_generator.invoke(
            inputs={"用户需求": self.user_requirements},
            output_keys=["报告大纲"],
        )
        self.report_outline = resp["报告大纲"]
        return self.report_outline

    def genInitialDraft(self, background, data_support, user_demand, template):
        inputs = {
            "报告背景": background,
            "数据支撑": data_support,
            "用户需求": user_demand,
            "格式模板": template,
        }
        resp = self.report_generator.invoke(
            inputs=inputs,
            output_keys=["初稿"],
        )
        initial_draft = resp["初稿"]
        self.history_stack.append(initial_draft)
        self.report_content = initial_draft
        return initial_draft

    def checkCompliance(self, draft):
        resp = self.compliance_checker.invoke(
            inputs={"待审报告": draft},
            output_keys=["risk_level", "illegal_clauses", "policy_conflicts", "recommendations"],
        )
        return resp

    def validateFormat(self, draft):
        resp = self.format_validator.invoke(
            inputs={"原始报告": draft},
            output_keys=["页边距检测", "字体检测", "图表检测", "版记要素检测"],
        )
        return resp

    def coordinateDepartments(self, departmental_drafts: dict):
        combined_input = ""
        for dept, draft in departmental_drafts.items():
            combined_input += f"# {dept}\n{draft}\n\n"
        resp = self.coordinator.invoke(
            inputs={"各部门草案": combined_input},
            output_keys=["修订草案", "意见汇总表", "争议点决策树", "会签页模板"],
        )
        final_draft = resp["修订草案"]
        self.history_stack.append(final_draft)
        self.report_content = final_draft
        return final_draft


# 初始化状态
report_system = None

def init_system(api_key: str):
    global report_system
    chatLLM = zhipuChatLLM(model_name="glm-4-plus", api_key='57ecdcf0e2b7407a9800b2e58fc8b214.kXuA501N2Hcc2Q8N')
    STREAM_INTERVAL = 0.5  # 调整更新频率
    return "系统已初始化"

# Gradio 接口函数
def generate_outline(requirements):
    outline = report_system.genReportOutline(user_idea=requirements)
    return outline

def generate_draft(background, data_support, requirements, template):
    draft = report_system.genInitialDraft(background, data_support, requirements, template)
    return draft

def run_compliance(draft):
    return report_system.checkCompliance(draft)


def run_format(draft):
    return report_system.validateFormat(draft)


def coordinate(dept_names, dept_drafts):
    names = dept_names.split(',')
    drafts = dept_drafts.split('||')  # departments drafts separated by ||
    dept_dict = dict(zip(names, drafts))
    final = report_system.coordinateDepartments(dept_dict)
    return final

# Gradio UI
with gr.Blocks() as demo:
    gr.Markdown("# AI 多智能体公文生成助手")
    with gr.Tab("初始化"):
        api_input = gr.Textbox(label="OpenAI API Key", type="password")
        init_btn = gr.Button("初始化系统")
        init_out = gr.Textbox(label="状态")
        init_btn.click(init_system, inputs=api_input, outputs=init_out)

    with gr.Tab("生成大纲"):
        req_input = gr.Textbox(label="用户需求")
        outline_btn = gr.Button("生成大纲")
        outline_out = gr.Textbox(label="报告大纲", lines=5)
        outline_btn.click(generate_outline, inputs=req_input, outputs=outline_out)

    with gr.Tab("初稿生成"):
        bg_input = gr.Textbox(label="报告背景")
        data_input = gr.Textbox(label="数据支撑")
        req2_input = gr.Textbox(label="用户需求")
        template_input = gr.Textbox(label="格式模板")
        draft_btn = gr.Button("生成初稿")
        draft_out = gr.Textbox(label="初稿", lines=10)
        draft_btn.click(
            generate_draft,
            inputs=[bg_input, data_input, req2_input, template_input],
            outputs=draft_out,
        )

    with gr.Tab("合规与格式"):
        draft2_input = gr.Textbox(label="报告草稿", lines=10)
        comp_btn = gr.Button("合规审查")
        comp_out = gr.JSON(label="合规审查结果")
        fmt_btn = gr.Button("格式校验")
        fmt_out = gr.JSON(label="格式校验结果")
        comp_btn.click(run_compliance, inputs=draft2_input, outputs=comp_out)
        fmt_btn.click(run_format, inputs=draft2_input, outputs=fmt_out)

    with gr.Tab("多部门整合"):
        names_input = gr.Textbox(label="部门名称(逗号分隔)")
        drafts_input = gr.Textbox(label="对应草案(用||分隔)")
        coord_btn = gr.Button("整合生成")
        coord_out = gr.Textbox(label="最终修订草案", lines=10)
        coord_btn.click(coordinate, inputs=[names_input, drafts_input], outputs=coord_out)

if __name__ == "__main__":
    demo.launch()
