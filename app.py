import streamlit as st
import anthropic
import os
import io
import json
import re
from pathlib import Path

# ---------- 文件解析 ----------
try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# 默认配置
DEEPSEEK_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
DEEPSEEK_BASE = "https://api.deepseek.com/anthropic"

# ---------- 页面 ----------
st.set_page_config(page_title="简历智能优化助手", page_icon="📝", layout="wide")
st.title("📝 简历智能优化助手")
st.markdown("**基于AI的简历-岗位匹配分析与自动优化系统**")
st.markdown("---")

# ---------- 侧边栏 ----------
with st.sidebar:
    with st.expander("⚙️ API 配置（需自行填入 Key）", expanded=True):
        api_key = st.text_input("DeepSeek / Anthropic API Key", type="password",
                                placeholder="sk-... 粘贴你的 API Key",
                                help="没有 Key 的话暂时无法使用。注册 DeepSeek 可获得 ¥9 体验金")
        model_name = st.selectbox("模型", ["deepseek-v4-flash", "deepseek-v4-pro"], index=0)
    st.markdown("---")
    st.markdown("### 📖 使用说明")
    st.markdown("上传简历 → 粘贴岗位描述 → 分析 → 一键生成优化版")

    # ---- 历史记录 ----
    if "history" not in st.session_state:
        st.session_state.history = []
    if st.session_state.history:
        st.markdown("---")
        st.markdown("### 📋 分析历史")
        for i, h in enumerate(reversed(st.session_state.history[-10:])):
            idx = len(st.session_state.history) - i - 1
            with st.expander(f"#{idx+1} {h.get('title','?')[:20]} | {h.get('score','?')}/100", expanded=False):
                st.markdown(f"**匹配度:** {h['score']}/100")
                st.markdown(f"**岗位:** {h['title']}")
        if st.button("🗑️ 清空历史"):
            st.session_state.history = []
            st.rerun()

# ---------- 辅助函数 ----------
def call_llm(system, user, key, model, max_tokens=3000, timeout_sec=120):
    client = anthropic.Anthropic(
        api_key=key,
        base_url=DEEPSEEK_BASE if model.startswith("deepseek") else None,
        timeout=timeout_sec,
    )
    msg = client.messages.create(
        model=model, max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    for b in msg.content:
        if hasattr(b, "text"):
            return b.text
    return ""

def parse_data(text):
    """从分析结果提取结构化数据"""
    d = {"score": 0, "skill": 0, "experience": 0, "education": 0, "project": 0}
    m = re.search(r"\[DATA\](.*?)\[/DATA\]", text, re.DOTALL)
    if m:
        try:
            d.update(json.loads(m.group(1).strip()))
        except:
            pass
    # fallback
    s = re.search(r"[（(]?\s*(\d{1,3})\s*[分/)]", text)
    if s and not d["score"]:
        d["score"] = int(s.group(1))
    return d

def strip_data(text):
    return re.sub(r"\n?\[DATA\].*?\[/DATA\]\n?", "", text, flags=re.DOTALL)

# ---------- 主界面 ----------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📄 输入信息")
    uploaded_file = st.file_uploader("上传简历（PDF / Word / TXT）",
                                     type=["pdf", "docx", "txt"])
    resume_text = ""
    if uploaded_file is not None:
        ext = Path(uploaded_file.name).suffix.lower()
        try:
            raw = uploaded_file.read()
            if ext == ".pdf" and HAS_PDF:
                reader = PyPDF2.PdfReader(io.BytesIO(raw))
                resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            elif ext == ".docx" and HAS_DOCX:
                doc = docx.Document(io.BytesIO(raw))
                resume_text = "\n".join(p.text for p in doc.paragraphs)
            elif ext == ".txt":
                resume_text = raw.decode("utf-8", errors="ignore")
        except:
            st.warning("⚠️ 解析失败，请手动粘贴")

    resume_text = st.text_area("简历内容", value=resume_text, height=260,
                               placeholder="粘贴简历 或 上传文件后自动填入…")
    job_desc = st.text_area("岗位描述（JD）", height=200,
                            placeholder="粘贴目标岗位的职位描述…")

    job_title = st.text_input("岗位名称（用于历史记录）", placeholder="e.g. AI产品经理",
                              label_visibility="collapsed")

    analyze_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)

# ---------- 右侧结果 ----------
with col2:
    st.subheader("📊 分析结果")
    key = api_key or DEEPSEEK_KEY

    # ---- 分析逻辑 ----
    if analyze_btn:
        if not key:
            st.error("⚠️ 请配置 API Key")
        elif not resume_text.strip():
            st.error("⚠️ 请输入简历内容")
        elif not job_desc.strip():
            st.error("⚠️ 请输入岗位描述")
        else:
            with st.spinner("🤔 AI 正在分析匹配度..."):
                try:
                    sys = "你是一位专业的简历优化顾问。你擅长逐项评估简历对岗位要求的满足程度。"
                    usr = f"""分析这份简历与目标岗位的匹配度。

简历：
{resume_text}

岗位描述：
{job_desc}

任务：
1. 从JD中提取8-15条具体可评估的要求（技能/经验/教育/软实力）
2. 逐条评估：完全匹配/部分匹配/不匹配
3. 给出整体优化建议

输出格式：

## 能力清单

要求1 | ✅ | 说明
要求2 | ⚠️ | 缺了什么
要求3 | ❌ | 差距在哪

## 优化建议
[3-5条]

## 优势点
[3-5条]

最后附上清单数据：
[DATA]
[
  {{"req":"要求名","match":1,"note":"说明"}},
  {{"req":"要求名","match":0.5,"note":"说明"}}
]
[/DATA]
match: 1=完全匹配, 0.5=部分, 0=不匹配。清单不少于8条。"""

                    result = call_llm(sys, usr, key, model_name)
                    if not result:
                        st.error("模型无返回")
                        st.stop()

                    # 解析清单
                    clean = strip_data(result)
                    checklist = []
                    m = re.search(r"\[DATA\](.*?)\[/DATA\]", result, re.DOTALL)
                    if m:
                        try:
                            raw = m.group(1).strip().replace("'", '"')
                            parsed = json.loads(raw)
                            for item in parsed:
                                checklist.append({
                                    "req": item.get("req", "?"),
                                    "match": item.get("match", 0),
                                    "note": item.get("note", ""),
                                })
                        except Exception:
                            pass

                    # 算分
                    if checklist:
                        total = len(checklist)
                        matched = sum(item["match"] for item in checklist)
                        score = round((matched / total) * 100)
                    else:
                        score = 0
                    full = [i for i in checklist if i["match"] >= 1]
                    partial = [i for i in checklist if 0 < i["match"] < 1]
                    none = [i for i in checklist if i["match"] == 0]

                    # 存入 session_state
                    st.session_state["analysis_done"] = True
                    st.session_state["analysis_resume"] = resume_text
                    st.session_state["analysis_jd"] = job_desc
                    st.session_state["analysis_score"] = score
                    st.session_state["analysis_checklist"] = checklist
                    st.session_state["analysis_clean"] = clean
                    st.session_state["analysis_title"] = job_title or "未命名岗位"
                    st.session_state["analysis_full"] = len(full)
                    st.session_state["analysis_partial"] = len(partial)
                    st.session_state["analysis_none"] = len(none)
                    if "optimized" in st.session_state:
                        del st.session_state["optimized"]
                    if "qanda" in st.session_state:
                        del st.session_state["qanda"]
                    st.session_state["saved_to_history"] = False

                except Exception as e:
                    import traceback
                    st.error(f"分析失败：{e}")
                    with st.expander("详情"):
                        st.code(traceback.format_exc())

    # ---- 显示分析结果（来自 session_state） ----
    if st.session_state.get("analysis_done"):
        s = st.session_state
        st.markdown("### 总体匹配度")
        st.progress(s["analysis_score"] / 100,
                    text=f"{s['analysis_score']}/100（{s['analysis_full']}项达标，{s['analysis_partial']}项部分，{s['analysis_none']}项不达标）")

        for item in s["analysis_checklist"]:
            icon = "✅" if item["match"] >= 1 else "⚠️" if item["match"] > 0 else "❌"
            st.markdown(f"**{icon} {item['req']}**")
            if item["note"]:
                st.markdown(f"<small style='color:#666'>{item['note']}</small>",
                          unsafe_allow_html=True)
            st.markdown("---")

        with st.expander("详细分析报告", expanded=False):
            st.markdown(s["analysis_clean"])

        st.success("分析完成！")

        # ---- 1. 生成优化版简历 ----
        st.markdown("---")
        if st.button("生成优化版简历", type="secondary", use_container_width=True, key="gen"):
            with st.spinner("AI 正在生成优化版简历..."):
                opt_sys = "你是一位专业的简历优化顾问。基于分析结果，生成优化后的简历，不编造经历。"
                opt_usr = f"""你的任务：基于原始简历+分析结果+JD内容，重写一份优化版简历。**优化后的简历如果重新分析，分数应明显高于原始简历。**

目标岗位JD：
{s['analysis_jd']}

原始简历：
{s['analysis_resume']}

分析给出的缺失项：
{s['analysis_clean']}

要求：
1. 保留所有真实经历和数字，**不编造**
2. 对每条缺失项：如果原简历中有间接相关的经历，重新措辞让它显式匹配JD要求
3. 项目描述按"我用XX方法解决了XX问题，达成XX效果"结构重写，把JD关键词融入每一条描述
4. 自我评价部分：根据JD要求补充相关软技能的表述
5. 输出完整的优化版简历"""

                try:
                    opt = call_llm(opt_sys, opt_usr, key, model_name, 3000, 120)
                    if opt:
                        st.session_state["optimized"] = opt
                        if "qanda" in st.session_state:
                            del st.session_state["qanda"]
                except Exception as e:
                    st.error(f"生成失败：{e}")

        # ---- 2. 对比视图 + 优化版简历 ----
        if "optimized" in st.session_state:
            vcol1, vcol2 = st.columns(2)
            with vcol1:
                st.markdown("**原始简历**")
                st.text_area("", value=s["analysis_resume"], height=400,
                             label_visibility="collapsed", disabled=True)
            with vcol2:
                st.markdown("**优化版简历**")
                st.text_area("", value=st.session_state["optimized"], height=400,
                             label_visibility="collapsed")
            st.download_button("下载优化版 .md", st.session_state["optimized"],
                               file_name="优化简历.md")

            # ---- 3. 面试问答 ----
            st.markdown("---")
            if st.button("生成面试问答", type="secondary", use_container_width=True, key="qa"):
                with st.spinner("AI 正在分析面试必问题..."):
                    qa_sys = "你是一位资深产品经理面试官。你擅长根据简历和JD预测面试问题并给出回答思路。"
                    qa_usr = f"""基于简历和目标岗位JD，生成8个最可能被问到的面试问题，并给出针对这份简历的回答建议。

目标岗位JD：
{s['analysis_jd']}

简历：
{s['analysis_resume']}

分析建议：
{s['analysis_clean']}

优化后简历：
{st.session_state['optimized']}

每个问题的输出格式：
**Q1：问题**
**建议回答思路：** [3-5句话，结合简历中的真实经历]
**注意：** 不要编造经历，用简历里已有的项目来回答案例。"""

                    try:
                        qa = call_llm(qa_sys, qa_usr, key, model_name, 4000, 120)
                        if qa:
                            st.session_state["qanda"] = qa
                    except Exception as e:
                        st.error(f"生成失败：{e}")

            if "qanda" in st.session_state:
                with st.expander("面试问答", expanded=True):
                    st.markdown(st.session_state["qanda"])
                    st.download_button("下载面试问答 .md", st.session_state["qanda"],
                                       file_name="面试问答.md")

        # 存入历史（仅一次）
        if not s.get("saved_to_history"):
            st.session_state.history.append({
                "score": s["analysis_score"],
                "title": s["analysis_title"],
                "analysis": s["analysis_clean"],
            })
            st.session_state["saved_to_history"] = True

    else:
        with st.container(height=600, border=True):
            st.info('请在左侧输入信息，点击"开始分析"')

st.markdown("---")
st.markdown("<div style='text-align:center;color:#666;font-size:0.9em;'>"
            "<p>💡 Python + Streamlit + DeepSeek API</p>"
            "<p>📧 周奕菲 | AI 专业 2026 届</p></div>",
            unsafe_allow_html=True)
