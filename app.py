import streamlit as st
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from docxtpl import DocxTemplate
import os
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib3.exceptions import MaxRetryError, ProxyError
from requests.exceptions import RequestException
from typing import Dict, Any, List, Optional
import tempfile
import time

# FastAPI 应用
app = FastAPI()

# API 配置
API_KEY = "sk-eWZq3KRYyOVQlfHUpQaPJbtbTK8012QK5wzP3ozfBf1mgrJJ"
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
MOONSHOT_API_URL = "https://api.moonshot.cn/v1/chat/completions"

# 读取提示词模板
with open("resume_standardization_prompt.txt", "r", encoding="utf-8") as f:
    RESUME_PROMPT = f.read()

with open("推荐报告prompt.txt", "r", encoding="utf-8") as f:
    RECOMMENDATION_PROMPT = f.read()

# 创建一个带重试机制的Session
def create_requests_session():
    """创建一个带有重试机制的requests会话"""
    session = requests.Session()
    
    # 设置重试策略
    retry_strategy = Retry(
        total=3,  # 总重试次数
        backoff_factor=1,  # 重试间隔
        status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
    )
    
    # 创建适配器
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def get_proxy_settings():
    """获取代理设置"""
    proxies = None
    # 检查环境变量中是否有代理设置
    http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
    https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
    
    if http_proxy or https_proxy:
        proxies = {
            'http': http_proxy,
            'https': https_proxy
        }
    
    return proxies

def call_api_with_retry(url: str, headers: dict, json_data: dict, timeout: int = 180) -> Optional[Dict[str, Any]]:
    """统一的API调用函数，带有重试和错误处理"""
    session = create_requests_session()
    proxies = get_proxy_settings()
    
    try:
        response = session.post(
            url,
            headers=headers,
            json=json_data,
            timeout=timeout,
            proxies=proxies
        )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            st.error("❌ API认证失败，请检查API Key是否正确")
        elif response.status_code == 429:
            st.error("❌ 请求太频繁，请稍后再试")
        else:
            st.error(f"❌ API请求失败: HTTP {response.status_code}")
            st.code(response.text)
        
    except ProxyError as e:
        st.error("❌ 代理连接失败")
        st.info("💡 请检查代理设置或尝试直接连接")
        st.code(str(e))
    except MaxRetryError as e:
        st.error("❌ 连接重试次数超限")
        st.info("💡 请检查网络连接是否稳定")
        st.code(str(e))
    except RequestException as e:
        st.error("❌ 网络请求异常")
        st.info("💡 请检查网络连接")
        st.code(str(e))
    except Exception as e:
        st.error(f"❌ 发生未知错误: {str(e)}")
    
    return None

def upload_file_to_kimi(file_content: bytes, filename: str) -> Optional[str]:
    """上传文件到Kimi API"""
    url = f"{KIMI_BASE_URL}/files"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }
    files = {
        'file': (filename, file_content, 'application/octet-stream'),
        'purpose': (None, 'file-extract')
    }
    try:
        resp = requests.post(url, headers=headers, files=files, timeout=30)
        if resp.status_code == 200:
            return resp.json().get('id')
        elif resp.status_code == 401:
            st.error("API认证失败，请检查API Key是否正确")
        else:
            st.error(f"Kimi文件上传失败: {resp.status_code}, {resp.text}")
    except Exception as e:
        st.error(f"Kimi文件上传异常: {e}")
    return None

def check_file_status(file_id: str) -> bool:
    """检查文件是否已处理完成"""
    url = f"{KIMI_BASE_URL}/files/{file_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            file_info = resp.json()
            status = file_info.get('status', '')
            completed_statuses = ['processed', 'completed', 'ready', 'finished', 'success', 'ok']
            return status in completed_statuses
        elif resp.status_code == 401:
            st.error("API认证失败，请检查API Key是否正确")
    except Exception as e:
        st.error(f"检查文件状态异常: {e}")
    return False

def read_file_content(file_id: str) -> Optional[str]:
    """读取文件内容"""
    url = f"{KIMI_BASE_URL}/files/{file_id}/content"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
        elif resp.status_code == 401:
            st.error("API认证失败，请检查API Key是否正确")
        else:
            st.error(f"读取文件内容失败: {resp.status_code}, {resp.text}")
    except Exception as e:
        st.error(f"读取文件内容异常: {e}")
    return None

def fix_truncated_json(json_str: str) -> str:
    """修复被截断的JSON字符串"""
    st.write("🔧 尝试修复JSON...")
    
    # 计算开括号和闭括号的数量
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    st.write(f"📊 括号统计: {{ ({open_braces}:{close_braces}), [ ({open_brackets}:{close_brackets})")
    
    try:
        # 如果在achievements后面被截断
        if '"achievements": []' in json_str and not json_str.endswith('}'):
            st.write("📝 检测到在achievements后被截断")
            # 找到最后一个完整的achievements数组
            pos = json_str.rfind('"achievements": []')
            if pos > 0:
                # 补全结构
                json_str = json_str[:pos] + '"achievements": [] }]}'
                st.write("✅ 补全JSON结构")
        
        # 如果还有未闭合的括号，添加相应的闭合括号
        if open_braces > close_braces:
            json_str += '}' * (open_braces - close_braces)
        if open_brackets > close_brackets:
            json_str += ']' * (open_brackets - close_brackets)
        
        # 验证JSON是否有效
        try:
            json.loads(json_str)
            st.write("✅ JSON修复成功且验证通过")
            return json_str
        except json.JSONDecodeError as e:
            st.write(f"⚠️ JSON仍然无效: {str(e)}")
            # 尝试更激进的修复
            if '"work_experiences": [' in json_str:
                # 找到最后一个完整的工作经历
                last_complete_exp = json_str.rfind('}, {')
                if last_complete_exp > 0:
                    # 只保留到最后一个完整的工作经历
                    json_str = json_str[:last_complete_exp + 1] + ']}'
                    st.write("📝 保留最后一个完整的工作经历")
                    # 再次验证
                    try:
                        json.loads(json_str)
                        st.write("✅ JSON修复成功")
                        return json_str
                    except json.JSONDecodeError:
                        st.write("❌ JSON修复失败")
            
            return json_str
    except Exception as e:
        st.error(f"❌ JSON修复过程出错: {e}")
        return json_str

def process_api_response(response_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """处理API响应，提取content数据"""
    st.write("🔄 处理API响应...")
    try:
        # 如果响应包含choices结构
        if isinstance(response_data, dict) and 'choices' in response_data:
            st.write("📝 从API响应中提取content...")
            content = response_data['choices'][0]['message']['content']
            st.write("📝 提取的content：")
            st.code(content)
            
            # 检查是否需要修复JSON
            if content.count('{') != content.count('}') or content.count('[') != content.count(']'):
                st.warning("⚠️ 检测到JSON可能被截断，尝试修复...")
                content = fix_truncated_json(content)
            
            # 验证JSON格式
            try:
                # 尝试解析JSON以验证格式
                json.loads(content)
                st.write("✅ JSON格式验证通过")
            except json.JSONDecodeError as e:
                st.error(f"❌ JSON格式验证失败: {e}")
                st.write("📝 问题位置：")
                st.code(content[max(0, e.pos-50):min(len(content), e.pos+50)])
            
            # 直接返回content
            st.write("✅ 成功获取content")
            return content
        else:
            st.error("❌ 响应格式不正确")
            return None
    except Exception as e:
        st.error(f"❌ 处理API响应时发生错误: {e}")
        return None

def call_moonshot_api(content: str) -> Optional[Dict[str, Any]]:
    """调用 Moonshot API 进行简历信息提取"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    data = {
        "model": "moonshot-v1-128k",
        "messages": [
            {"role": "system", "content": RESUME_PROMPT},
            {"role": "user", "content": content}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 32768
    }
    
    response_data = call_api_with_retry(MOONSHOT_API_URL, headers, data)
    if response_data:
        if 'choices' in response_data and len(response_data['choices']) > 0:
            content = response_data['choices'][0]['message']['content']
            # 检查是否需要修复JSON
            if content.count('{') != content.count('}') or content.count('[') != content.count(']'):
                st.warning("⚠️ 检测到JSON可能被截断，尝试修复...")
                content = fix_truncated_json(content)
            
            try:
                # 解析JSON
                result = json.loads(content)
                # 检查工作经历是否完整
                if 'work_experiences' in result:
                    for exp in result['work_experiences']:
                        if 'achievements' not in exp:
                            exp['achievements'] = []
                return result
            except json.JSONDecodeError as e:
                st.error(f"❌ JSON解析失败: {e}")
                st.text("原始内容：")
                st.code(content)
    
    return None

def call_kimi_api(resume_file_id: str, jd_file_id: str, additional_info: str = "") -> Optional[Dict[str, Any]]:
    """调用 Kimi API 进行推荐分析"""
    url = f"{KIMI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # 读取文件内容
    resume_content = read_file_content(resume_file_id)
    jd_content = read_file_content(jd_file_id)
    
    if not resume_content or not jd_content:
        raise Exception("无法读取文件内容")
    
    data = {
        "model": "moonshot-v1-128k",
        "messages": [
            {"role": "system", "content": RECOMMENDATION_PROMPT},
            {"role": "user", "content": f"简历内容：\n{resume_content}\n\nJD内容：\n{jd_content}\n\n补充信息：\n{additional_info}"}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 32768
    }
    
    # 添加重试机制
    max_retries = 3
    for retry in range(max_retries):
        response_data = call_api_with_retry(url, headers, data)
        if response_data:
            if 'choices' in response_data and len(response_data['choices']) > 0:
                content = response_data['choices'][0]['message']['content']
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # 尝试修复JSON
                    content_clean = content.strip().lstrip('\ufeff')
                    last_brace = content_clean.rfind('}')
                    if last_brace > 0:
                        content_clean = content_clean[:last_brace+1]
                        return json.loads(content_clean)
            else:
                st.error("API响应中没有找到有效的内容")
        
        if retry < max_retries - 1:
            wait_time = (retry + 1) * 15
            st.warning(f"⚠️ 重试中，等待{wait_time}秒...")
            time.sleep(wait_time)
    
    return None

def merge_json_data(resume_data: Any, recommendation_data: Any) -> Dict[str, Any]:
    """合并简历数据和推荐分析数据"""
    st.write("🔄 开始合并数据...")
    try:
        # 处理简历数据
        if isinstance(resume_data, str):
            st.write("📝 简历数据是字符串格式")
            try:
                resume_data = json.loads(resume_data)
                st.write("✅ 简历数据JSON格式验证通过")
            except json.JSONDecodeError as e:
                st.warning("⚠️ 简历数据JSON格式有误，尝试修复...")
                resume_data = json.loads(fix_truncated_json(resume_data))
        
        # 处理推荐分析数据
        if isinstance(recommendation_data, str):
            st.write("📝 推荐分析数据是字符串格式")
            try:
                recommendation_data = json.loads(recommendation_data)
                st.write("✅ 推荐分析数据JSON格式验证通过")
            except json.JSONDecodeError as e:
                st.warning("⚠️ 推荐分析数据JSON格式有误，尝试修复...")
                recommendation_data = json.loads(fix_truncated_json(recommendation_data))
        
        # 合并数据
        st.write("📝 合并数据中...")
        final_data = {
            **resume_data,  # 基础简历信息
            **recommendation_data  # 推荐分析信息
        }
        
        # 调试输出
        st.write("✅ 数据处理完成")
        st.write("📝 最终数据：")
        st.code(final_data)
        
        return final_data
        
    except Exception as e:
        st.error(f"❌ 合并数据时发生错误: {e}")
        return {}

def check_template_variables(template_path: str) -> List[str]:
    """检查模板中的所有变量"""
    try:
        doc = DocxTemplate(template_path)
        variables = doc.get_undeclared_template_variables()
        return list(variables)
    except Exception as e:
        st.error(f"❌ 读取模板变量失败: {e}")
        return []

def validate_data_for_template(data: Dict[str, Any], template_variables: List[str]) -> bool:
    """验证数据是否包含模板所需的所有变量"""
    missing_vars = []
    for var in template_variables:
        # 处理嵌套变量，如 "basic_info.name"
        parts = var.split('.')
        value = data
        try:
            for part in parts:
                value = value[part]
        except (KeyError, TypeError):
            missing_vars.append(var)
    
    if missing_vars:
        st.error("❌ 数据中缺少以下模板变量:")
        for var in missing_vars:
            st.error(f"  - {var}")
        return False
    return True

def get_available_templates() -> List[str]:
    """获取template文件夹中的所有可用模板"""
    template_dir = "template"
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
    templates = [f for f in os.listdir(template_dir) if f.endswith('.docx')]
    return templates

def generate_doc(data: Dict[str, Any], template_name: str) -> Optional[bytes]:
    """生成Word文档"""
    try:
        # 检查模板文件是否存在
        template_path = os.path.join("template", template_name)
        if not os.path.exists(template_path):
            st.error(f"❌ 模板文件不存在: {template_path}")
            return None
            
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            # 渲染文档
            st.info("📝 正在渲染文档...")
            doc = DocxTemplate(template_path)
            doc.render(data)
            doc.save(tmp.name)
            
            # 读取生成的文件
            with open(tmp.name, 'rb') as f:
                doc_content = f.read()
            
            # 静默清理临时文件
            try:
                os.unlink(tmp.name)
            except:
                pass  # 忽略清理临时文件时的错误
            
            return doc_content
            
    except Exception as e:
        st.error(f"❌ 生成文档时发生错误: {e}")
        return None

@app.post("/generate-doc/")
async def generate_doc_endpoint(data: Dict[str, Any], template_name: str):
    """生成 Word 文档的API端点"""
    try:
        doc_content = generate_doc(data, template_name)
        if doc_content:
            return FileResponse(
                doc_content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=f"推荐报告_{template_name}"
            )
        return {"error": "生成文档失败"}
    except Exception as e:
        return {"error": str(e)}

def init_session_state():
    """初始化session state"""
    if 'resume_file_id' not in st.session_state:
        st.session_state.resume_file_id = None
    if 'jd_file_id' not in st.session_state:
        st.session_state.jd_file_id = None
    if 'resume_content' not in st.session_state:
        st.session_state.resume_content = None
    if 'resume_data' not in st.session_state:
        st.session_state.resume_data = None
    if 'recommendation_data' not in st.session_state:
        st.session_state.recommendation_data = None
    if 'final_data' not in st.session_state:
        st.session_state.final_data = None
    if 'processing_stage' not in st.session_state:
        st.session_state.processing_stage = 0  # 0: 未开始, 1: 文件上传, 2: 简历分析, 3: 推荐分析, 4: 合并完成

def show_stage_status():
    """显示当前处理阶段状态"""
    stages = {
        0: "⚪ 未开始处理",
        1: "📤 文件已上传",
        2: "📄 简历分析完成",
        3: "📊 推荐分析完成",
        4: "✅ 处理完成"
    }
    st.sidebar.header("处理进度")
    for stage_num, stage_desc in stages.items():
        if stage_num <= st.session_state.processing_stage:
            st.sidebar.success(stage_desc)
        else:
            st.sidebar.text(stage_desc)
    
    # 显示暂存的数据
    if st.session_state.processing_stage > 0:
        st.sidebar.header("暂存数据")
        if st.sidebar.checkbox("显示文件ID"):
            st.sidebar.json({
                "简历文件ID": st.session_state.resume_file_id,
                "JD文件ID": st.session_state.jd_file_id
            })
        if st.session_state.processing_stage > 1 and st.sidebar.checkbox("显示简历分析结果"):
            st.sidebar.json(st.session_state.resume_data)
        if st.session_state.processing_stage > 2 and st.sidebar.checkbox("显示推荐分析结果"):
            st.sidebar.json(st.session_state.recommendation_data)
        if st.session_state.processing_stage > 3 and st.sidebar.checkbox("显示最终结果"):
            st.sidebar.json(st.session_state.final_data)

def clear_session():
    """清除所有session数据"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.success("✅ 所有数据已清除")

def show_processing_status(container, message, progress_value=None):
    """显示处理状态"""
    with container:
        col1, col2 = st.columns([1, 4])
        with col1:
            if progress_value is not None:
                st.progress(progress_value)
            else:
                st.spinner()
        with col2:
            st.markdown(f"<p style='margin: 0; padding: 0;'>{message}</p>", unsafe_allow_html=True)

def process_with_status(status_container):
    """带状态显示的处理流程"""
    try:
        # 分析简历
        if st.session_state.processing_stage == 2:
            show_processing_status(status_container, "🔄 正在分析简历...")
            resume_content = read_file_content(st.session_state.resume_file_id)
            if not resume_content:
                st.error("❌ 无法读取简历内容")
                return False
            show_processing_status(status_container, "📄 简历内容读取成功", 0.3)
            
            st.session_state.resume_content = resume_content
            resume_data = call_moonshot_api(resume_content)
            if not resume_data:
                st.error("❌ 简历分析失败")
                return False
            st.session_state.resume_data = resume_data
            show_processing_status(status_container, "✅ 简历分析完成", 1.0)
            st.session_state.processing_stage = 3
            time.sleep(1)  # 显示完成状态
        
        # 生成推荐分析
        if st.session_state.processing_stage == 3:
            show_processing_status(status_container, "🔄 正在生成推荐分析...")
            recommendation_data = call_kimi_api(
                st.session_state.resume_file_id,
                st.session_state.jd_file_id,
                st.session_state.get('additional_info', '')
            )
            if not recommendation_data:
                st.error("❌ 推荐分析生成失败")
                return False
            st.session_state.recommendation_data = recommendation_data
            show_processing_status(status_container, "✅ 推荐分析生成完成", 1.0)
            st.session_state.processing_stage = 4
            time.sleep(1)  # 显示完成状态
        
        # 合并数据
        if st.session_state.processing_stage == 4:
            show_processing_status(status_container, "🔄 正在合并数据...")
            final_data = merge_json_data(
                st.session_state.resume_data,
                st.session_state.recommendation_data
            )
            if not final_data:
                st.error("❌ 数据处理失败")
                return False
            st.session_state.final_data = final_data
            show_processing_status(status_container, "✅ 数据处理完成", 1.0)
            time.sleep(1)  # 显示完成状态
            
        return True
        
    except Exception as e:
        st.error(f"❌ 处理过程中发生错误：{str(e)}")
        return False

def main():
    st.set_page_config(
        page_title="推荐报告助手",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 使用CSS设置全局样式
    st.markdown("""
        <style>
        .main {
            padding-top: 0.5rem;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
        }
        .stMarkdown {
            margin-bottom: 0.5rem;
        }
        .stButton > button {
            margin-top: 0.5rem;
            margin-bottom: 0.5rem;
        }
        .uploadedFile {
            margin-bottom: 0.5rem;
        }
        .css-1d391kg {
            padding-top: 1rem;
        }
        .stTextArea textarea {
            font-size: 0.8rem;
        }
        </style>
        """, unsafe_allow_html=True)
    
    # 获取可用模板
    templates = get_available_templates()
    if not templates:
        st.error("❌ 未找到任何模板文件，请将.docx模板文件放入template文件夹")
        return
    
    # 原有的正常模式代码
    st.markdown("<h2 style='font-size: 1.5rem; margin-bottom: 0.5rem;'>推荐报告助手</h2>", unsafe_allow_html=True)
    
    # 初始化session state
    init_session_state()
    
    # 显示处理阶段
    show_stage_status()
    
    # 添加重置按钮到侧边栏
    if st.sidebar.button("🔄 重置所有数据", key="reset_button"):
        clear_session()
        st.rerun()
    
    # 文件上传区域
    st.header("文件上传")
    resume_file = st.file_uploader("上传简历文件", type=["pdf", "doc", "docx", "txt", "xls", "jpg", "png"])
    jd_file = st.file_uploader("上传招聘JD", type=["pdf", "doc", "docx", "txt"])
    
    # Chat输入区域
    st.header("补充信息")
    additional_info = st.text_area("请输入补充信息（可选）")
    
    # 处理按钮
    if st.button("开始处理") or (st.session_state.processing_stage > 0 and st.button("继续处理")):
        process_container = st.container()
        with process_container:
            # 创建两列布局用于显示处理过程
            process_col1, process_col2 = st.columns([1, 1])
            
            with process_col1:
                # 检查是否需要重新上传文件
                if st.session_state.processing_stage == 0:
                    if resume_file is None or jd_file is None:
                        st.error("❌ 请上传简历文件和招聘JD")
                        return
                        
                    with st.spinner("正在处理文件..."):
                        try:
                            # 上传文件到Kimi
                            st.info("📤 正在上传简历文件...")
                            resume_file_id = upload_file_to_kimi(resume_file.read(), resume_file.name)
                            if not resume_file_id:
                                st.error("❌ 简历文件上传失败")
                                return
                            st.session_state.resume_file_id = resume_file_id
                            st.success(f"✅ 简历文件上传成功")
                                
                            st.info("📤 正在上传JD文件...")
                            jd_file_id = upload_file_to_kimi(jd_file.read(), jd_file.name)
                            if not jd_file_id:
                                st.error("❌ JD文件上传失败")
                                return
                            st.session_state.jd_file_id = jd_file_id
                            st.success(f"✅ JD文件上传成功")
                                
                            # 保存补充信息
                            st.session_state.additional_info = additional_info
                                
                            st.session_state.processing_stage = 1
                                
                        except Exception as e:
                            st.error(f"❌ 文件上传时发生错误：{str(e)}")
                            return

            with process_col2:
                # 等待文件处理完成
                if st.session_state.processing_stage == 1:
                    status_container = st.empty()
                    show_processing_status(status_container, "⏳ 等待文件处理完成...")
                    
                    for file_id in [st.session_state.resume_file_id, st.session_state.jd_file_id]:
                        max_wait = 30  # 最多等待30秒
                        progress = 0
                        while max_wait > 0 and not check_file_status(file_id):
                            time.sleep(2)
                            max_wait -= 2
                            progress += 0.067  # 30秒分成15步
                            show_processing_status(
                                status_container,
                                f"⏳ 等待文件处理完成（剩余{max_wait}秒）...",
                                min(progress, 1.0)
                            )
                        if max_wait <= 0:
                            st.error("❌ 文件处理超时")
                            return
                    show_processing_status(status_container, "✅ 文件处理完成", 1.0)
                    st.session_state.processing_stage = 2
                    time.sleep(1)  # 显示完成状态

        # 创建状态显示容器
        status_container = st.empty()
        
        # 处理后续阶段
        if not process_with_status(status_container):
            return
            
        # 刷新页面显示结果
        st.rerun()  # 替换 experimental_rerun

    # 如果处理完成，使用选项卡显示结果
    if st.session_state.processing_stage == 4 and st.session_state.final_data:
        tabs = st.tabs(["处理结果", "修改确认", "生成文档"])
        
        with tabs[0]:
            st.json(st.session_state.final_data)
            
        with tabs[1]:
            edited_json = st.text_area(
                "请检查并修改数据（JSON格式）", 
                json.dumps(st.session_state.final_data, indent=2, ensure_ascii=False),
                height=400
            )
            
        with tabs[2]:
            # 添加模板选择下拉框
            selected_template = st.selectbox(
                "选择报告模板",
                templates,
                format_func=lambda x: x.replace('.docx', ''),
                help="选择要使用的推荐报告模板"
            )
            
            if st.button("生成推荐报告", use_container_width=True):
                try:
                    # 解析编辑后的JSON
                    edited_data = json.loads(edited_json)
                    
                    # 生成文档
                    doc_content = generate_doc(edited_data, selected_template)
                    
                    if doc_content:
                        st.success("✅ 文档生成成功！")
                        st.download_button(
                            "⬇️ 下载推荐报告",
                            doc_content,
                            file_name=f"推荐报告_{selected_template}",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                        
                except json.JSONDecodeError:
                    st.error("❌ JSON格式错误，请检查修改的内容")
                except Exception as e:
                    st.error(f"❌ 生成文档时发生错误：{str(e)}")

if __name__ == "__main__":
    main()
