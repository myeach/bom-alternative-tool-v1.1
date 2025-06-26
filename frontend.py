import streamlit as st
from datetime import datetime
import time
import pandas as pd
import tempfile  # 用于创建临时文件，支持文件下载功能
from custom_components.hide_sidebar_items import get_sidebar_hide_code
from backend import identify_component
import base64


# 不显示报错信息到前端
st.set_option('client.showErrorDetails', False)

def render_ui(get_alternative_parts_func):
    # Streamlit 界面 - 确保 set_page_config 是第一个Streamlit命令
    st.set_page_config(page_title="BOM 元器件国产替代推荐工具", layout="wide")
    
    # 应用隐藏run和chat按钮的代码
    hide_code = get_sidebar_hide_code()
    st.markdown(hide_code, unsafe_allow_html=True)
    
    # 初始化会话状态变量，用于处理回车键事件
    if 'search_triggered' not in st.session_state:
        st.session_state.search_triggered = False
    
    # 初始化聊天消息历史
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": "👋 您好！我是元器件选型助手\n\n**我可以帮您：**\n\n📌 查找国产替代方案\n📌 对比元器件参数\n📌 评估供应链风险\n📌 分析设计兼容性"
        }]
    
    # 检查是否通过URL参数直接跳转到聊天界面
    query_params = st.query_params
    if 'page' in query_params and query_params.get('page') == 'chat':
        # 直接重定向到主页
        st.markdown("""
        <style>
        .chat-redirect {
            text-align: center;
            margin: 50px auto;
            max-width: 600px;
            padding: 30px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        </style>
        <div class="chat-redirect">
            <h2>聊天功能已集成</h2>
            <p>我们的AI选型助手已集成到主界面的第三个标签页中</p>
            <script>
                window.location.href = "/";
            </script>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # 处理回车键的回调函数
    def handle_enter_press():
        if st.session_state.part_number_input:  # 检查输入框是否有内容
            st.session_state.search_triggered = True

    # 侧边栏核心内容（前置渲染，确保始终可见）
    with st.sidebar:
        st.title("历史查询记录")
        if 'search_history' not in st.session_state:
            st.session_state.search_history = []
        
        if len(st.session_state.search_history) > 0:
            if st.button("清除历史记录", key="clear_history_tab1"):
                st.session_state.search_history = []
        
        if not st.session_state.search_history:
            st.info("暂无历史查询记录")
        else:
            for idx, history_item in enumerate(reversed(st.session_state.search_history)):
                query_type = "批量查询" if history_item.get('type') == 'batch' else "单元器件查询"
                with st.container():
                    st.markdown(f"""
                    <div style="padding: 10px; border-radius: 5px; margin-bottom: 10px; border: 1px solid #e6e6e6; background-color: #f9f9f9;">
                        <div style="font-weight: bold;">{history_item['part_number']}</div>
                        <div style="font-size: 0.8em; color: #666;">({query_type}) {history_item['timestamp']}</div>
                        <div style="margin-top: 5px; font-size: 0.9em;">
                            {"批量查询多个元器件" if history_item.get('type') == 'batch' 
                             else f"找到 {len(history_item.get('recommendations', []))} 种替代方案"}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # 更新CSS样式，精简和优化AI对话部分的样式
    st.markdown("""
    <style>
        /* 整体页面样式 */
        .stApp {
            background-color: #f8f9fa;
        }
        
        /* 隐藏Streamlit的info容器 */
        div[data-testid="stInfoAlert"] {
            display: none !important;
        }
        
        /* 隐藏Streamlit的success容器 - 用于隐藏"识别到的关键列"信息 */
        div[data-testid="stSuccessAlert"] {
            display: none !important;
        }
        
        /* 标题样式 */
        .main-header {
            font-size: 2.5rem;
            font-weight: 800;
            color: #1a73e8;
            text-align: center;
            padding: 0.5rem 0; /* 顶部和底部内边距 */
            margin-bottom: 0.5rem; /* 底部外边距 */
            background: linear-gradient(90deg, #1a73e8, #4285f4, #6c5ce7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
            line-height: 1.2;
            text-shadow: 0 4px 10px rgba(26, 115, 232, 0.1);
        }
        
        /* 标题装饰 */
        .header-container {
            position: relative;
            padding: 0 0.5rem; /* 内边距 */
            margin-bottom: 0.5rem; /* 底部外边距 */
        }
        
        /* 使标签面板与页面背景色保持一致，移除边框和阴影 */
        .stTabs [data-baseweb="tab-panel"] {
            background-color: transparent !important; 
            border: none !important;
            box-shadow: none !important;
            padding-top: 0.3rem !important; /* 顶部内边距 */
        }
        
        /* 修改标签样式，增大标签尺寸 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 40px !important; /* 标签之间的间距 */
            margin-bottom: 0 !important; /* 底部外边距 */
            margin-top: 0 !important; /* 顶部外边距 */
            border-bottom: none !important; /* 移除底部边框 */
            padding-bottom: 15px !important; /* 底部内边距 */
            justify-content: center !important; /* 居中标签 */
        }
        
        /* 增大标签页的字体大小和按钮大小 */
        button[data-baseweb="tab"] {
            font-size: 2.0rem !important; /* 增大字体尺寸，原来是1.25rem */
            font-weight: 700 !important; /* 增加字体粗细 */
            padding: 18px 36px !important; /* 增加内边距让按钮更大 */
            border-radius: 8px !important; /* 圆角边框 */
            margin: 0 10px !important; /* 按钮间距 */
            transition: all 0.3s ease !important; /* 平滑过渡效果 */
            background-color: #f0f2f6 !important; /* 默认背景色 */
            line-height: 1.2 !important; /* 增加行高 */
            letter-spacing: 0.5px !important; /* 增加字间距 */
            text-transform: none !important; /* 确保文本不被转换 */
        }
        
        /* 确保样式优先级 */
        .stTabs button[role="tab"] {
            font-size: 2.0rem !important;
            font-weight: 700 !important;
        }
        
        /* 标签激活状态 */
        button[data-baseweb="tab"][aria-selected="true"] {
            color: white !important;
            background-color: #1a73e8 !important;
            box-shadow: 0 4px 10px rgba(26, 115, 232, 0.2) !important;
        }
        
        /* 标签鼠标悬停效果 */
        button[data-baseweb="tab"]:hover {
            background-color: #e0e7ff !important;
            transform: translateY(-2px) !important;
        }
        
        button[data-baseweb="tab"][aria-selected="true"]:hover {
            background-color: #1a73e8 !important;
        }
        
        /* 移除标签条下方的额外空间 */
        .stTabs [data-baseweb="tab-panel"] {
            margin-top: 20px !important;
        }
        
        /* 增加标签下划线 */
        [data-baseweb="tab-highlight"] {
            display: none !important; /* 隐藏默认下划线，改为使用背景色区分 */
        }
        
        /* 搜索区域样式 */
        .search-area {
            background: linear-gradient(145deg, #ffffff, #f0f7ff);
            box-shadow: 0 5px 15px rgba(26, 115, 232, 0.15);
            padding: 0.8rem; /* 内边距 */
            border-radius: 0.8rem;
            margin-bottom: 1rem; /* 底部外边距 */
            border: 1px solid rgba(26, 115, 232, 0.1);
            max-width: 1000px;
            margin-left: auto;
            margin-right: auto;
            display: flex;
            align-items: center;
        }
        
        /* 搜索框和按钮容器  */
        .search-container {
            display: flex;
            align-items: center;
            gap: 10px; 
            margin: 0;
            padding: 0;
            width: 100%;
        }
        
        /* 搜索输入框样式增强 */
        .search-input {
            width: 100%;
        }
        
        /* 增强输入框可见度和对比度 */
        .stTextInput input {
            background-color: white !important;
            border: 2px solid #1a73e8 !important;
            border-radius: 6px !important;
            padding: 10px 15px !important;
            font-size: 1.05rem !important;
            color: #202124 !important;
            box-shadow: 0 2px 6px rgba(26, 115, 232, 0.1) !important;
            transition: all 0.3s ease !important;
        }
        
        /* 输入框:focus状态 */
        .stTextInput input:focus {
            border: 2px solid #1a73e8 !important;
            box-shadow: 0 3px 8px rgba(26, 115, 232, 0.25) !important;
            outline: none !important;
        }
        
        /* 输入框占位符文字样式 */
        .stTextInput input::placeholder {
            color: #5f6368 !important;
            opacity: 0.8 !important;
            font-weight: 400 !important;
        }
        
        /* 整体页面的内边距 */
        .block-container {
            padding-top: 0.5rem !important; /* 顶部内边距 */
            padding-bottom: 0.5rem !important; /* 底部内边距 */
            max-width: 1200px;
            padding-left: 1rem !important; /* 左侧内边距 */
            padding-right: 1rem !important; /* 右侧内边距 */
        }
        
        /* 元素间垂直间距 */
        .element-container, .stAlert > div {
            margin-top: 0.3rem !important; /* 顶部外边距 */
            margin-bottom: 0.3rem !important; /* 底部外边距 */
        }
        
        /* 聊天容器样式 - 全屏模式 */
        .fullscreen-chat {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(255, 255, 255, 0.98);
            z-index: 9999;
            display: flex;
            flex-direction: column;
            padding: 20px;
            box-sizing: border-box;
            overflow-y: auto;
        }
        
        /* 聊天内容区域 */
        .chat-content {
            flex: 1;
            max-width: 900px;
            width: 100%;
            margin: 0 auto;
            background-color: #fff;
            border-radius: 12px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            padding: 20px;
            display: flex;
            flex-direction: column;
        }
        
        /* 对话框标题区域*/
        .chat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px; /* 底部内边距 */
            border-bottom: 1px solid #eee;
        }
        
        /* 对话框标题 */
        .chat-title {
            margin: 0; /* 移除默认外边距 */
            font-size: 1.5rem; /* 字体大小 */
            font-weight: 600;
            color: #2c3e50;
        }
        
        /* 关闭按钮样式 */
        .close-button {
            cursor: pointer;
            background-color: #f0f0f0;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 18px;
            color: #555;
            border: none;
            transition: all 0.2s;
        }
        
        .close-button:hover {
            background-color: #e0e0e0;
            color: #333;
        }
        
        /* 预设问题容器  */
        .preset-questions-container {
            margin-top: 0.3rem !important; /* 顶部外边距 */
            margin-bottom: 0.5rem !important; /* 底部外边距 */
            display: flex;
            flex-wrap: wrap;
            gap: 3px; /* 按钮之间的间距 */
        }
        
        /* 欢迎信息样式*/
        .welcome-message {
            background-color: #f5f5f5;
            border-radius: 8px; /* 圆角 */
            padding: 10px; /* 内边距 */
            margin-bottom: 8px; /* 底部外边距 */
            border-left: 4px solid #4caf50;
        }
        
        /* 常见问题标题样式 */
        .faq-title {
            font-size: 0.9rem;
            color: #666;
            margin: 3px 0 !important; /*外边距 */
            font-weight: normal;
        }
        
        /* 对话内容区域样式 */
        .stChatMessage {
            padding: 8px !important; /* 内边距 */
            border-radius: 8px !important; /* 圆角 */
            margin-bottom: 6px !important; /* 底部外边距 */
        }
        
        /* 让输入框在聊天对话区域更加紧凑 */
        .stChatInput {
            margin-top: 8px !important; /* 顶部外边距 */
            margin-bottom: 8px !important; /* 底部外边距 */
            padding: 3px !important; /* 内边距 */
        }
        
        /* 隐藏Streamlit默认元素的外边距 */
        div.css-1kyxreq {
            margin-top: 0.3rem !important;
            margin-bottom: 0.3rem !important;
        }
        
        /* 各种Streamlit元素的垂直间距 */
        .stButton, .stTextInput, .stSelectbox, .stFileUploader {
            margin-bottom: 0.3rem;
        }
        
        /* 修复列对齐问题 */
        div[data-testid="column"] {
            padding: 0 !important;
            margin: 0 !important;
        }
        
        /* 减少tab内部元素的间距 */
        .stTabs [data-baseweb="tab-panel"] > div > div {
            margin-top: 0.3rem;
            margin-bottom: 0.3rem;
        }
        
        /* 单个元器件查询和BOM批量查询tab之间的垂直间距 */
        .stTabs {
            margin-bottom: 0.5rem !important;
        }
        
        /* 处理输入框的提示文字 */
        .stChatInput textarea::placeholder, .stChatInput input::placeholder {
            color: #8c9bb5 !important;
            font-size: 1rem !important; /* 减小字体大小 */
        }
        
        /* 侧边栏样式 */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
            padding-top: 1rem;
        }
        
        /* 侧边栏标题样式 */
        [data-testid="stSidebar"] h1 {
            font-size: 1.5rem;
            color: #1a73e8;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e6e9ef;
        }
        
        /* 侧边栏历史记录项目样式 */
        [data-testid="stSidebar"] .element-container {
            margin-bottom: 0.5rem !important;
        }
        
        /* 侧边栏按钮样式 */
        [data-testid="stSidebar"] button {
            background-color: #f0f4fd;
            border: none;
            color: #1a73e8;
            font-weight: 500;
            transition: background-color 0.2s;
        }
        
        [data-testid="stSidebar"] button:hover {
            background-color: #e0e9fa;
        }
                
        /* 新增：移除搜索区域的多余间距 */
        .search-area {
            margin-bottom: 0 !important;  /* 移除底部外边距 */
            padding: 0 !important;  /* 减少内边距 */
        }
        
        /* 调整容器内元素的间距 */
        .search-container {
            gap: 0 !important;  /* 减少输入框和按钮的间距 */
        }
          /* 消除容器和列的默认间距 */
        [data-testid="stContainer"] {
            padding: 0 !important;       /* 容器无内边距 */
            margin: 0 !important;        /* 容器无边距 */
        }
        
        div[data-testid="column"] {
            padding: 0 !important;       /* 列无内边距 */
            margin: 0 !important;        /* 列无边距 */
        }
        /* 输入框和按钮的最终调整 */
        .search-input input, .search-button button {
            margin: 0 !important;        /* 元素自身无边距 */
            padding: 10px !important;    /* 保持输入框内填充，确保可点击区域 */
        }
        div[data-testid="stTextInput"] > div {
            border: none !important;  
            box-shadow: none !important;  
            outline: none !important;  
        }
        div[data-testid="stTextInput"] input {
            border: none !important;
            box-shadow: none !important;
        }
        .search-area,
        .search-container,
        [data-testid="stContainer"],
        div[data-testid="column"] {
            border: none !important;
            box-shadow: none !important;
            border-bottom: none !important;  
        }
        hr,
        div[role="separator"] {
            display: none !important;
        }
        /* 重新定义标题容器，使用水平Flex布局 */
        .header-container-optimized {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;  /* 缩小间隙使Logo更紧贴标题 */
            margin: 15px 0 25px 0;
            padding: 0;
        }
        
        /* 放大Logo三倍并优化显示效果 */
        .header-logo-enlarged {
            width: 180px !important;  /* 60px * 3 = 180px */
            height: auto;
            object-fit: contain;
        }
        
        /* 标题紧贴Logo */
        .main-header-optimized {
            margin: 0;
            font-size: 2.8rem !important;  /* 稍微加大标题字号 */
        }
        div[data-testid="stExpander"] > div > button {
            font-size: 20px !important;  /* 标题字体大小，按需调整 */
            font-weight: 600 !important; /* 可选：加粗 */
        }
    </style>
    """, unsafe_allow_html=True)

    def get_image_base64(path):
        try:
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            st.error(f"图片加载失败: {str(e)}")
            return None

    # 获取BASE64编码的图像
    image_base64 = get_image_base64("image.png")

    if image_base64:
        st.markdown(
            f'<div style="text-align: center;">'
            f'<img src="data:image/png;base64,{image_base64}" style="width:180px; object-fit: contain;">'
            f'</div>'
            '<div style="text-align: center; margin-top: 10px;">'
            '<h1 style="font-size: 2.8rem;">半岛智芯优选</h1>'
            '</div>',
            unsafe_allow_html=True
        )


    # 增强标签样式，但使用原生Streamlit标签确保功能正常
    st.markdown("""
    <style>
        /* 强制覆盖Streamlit标签样式 */
        button[data-baseweb="tab"] div {
            font-size: 24px !important;
            font-weight: 700 !important;
        }
        
        /* 增大标签页的按钮大小 */
        button[data-baseweb="tab"] {
            font-size: 24px !important;
            font-weight: 700 !important;
            padding: 18px 36px !important;
            border-radius: 8px !important;
            background-color: #f0f2f6 !important;
        }
        
        /* 确保激活状态样式 */
        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: #1a73e8 !important;
            color: white !important;
        }
        
        /* 调整标签容器样式 */
        [data-testid="stHorizontalBlock"] [data-baseweb="tab-list"] {
            justify-content: center !important;
            gap: 20px !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # 创建原始标签
    tab1, tab2, tab3 = st.tabs(["元器件替代查询", "💬 AI选型助手", "批量替代查询"])

    with tab1:
        # 搜索区域 - 修改结构，确保输入框和按钮完全匹配
        with st.container():
            st.markdown('<div class="search-area">', unsafe_allow_html=True)
            st.markdown('<div class="search-container">', unsafe_allow_html=True)
            
            col1, col2 = st.columns([3, 0.8])  # 调整列比例
            with col1:
                st.markdown('<div class="search-input">', unsafe_allow_html=True)
                # 输入框，添加 on_change 参数和键盘事件处理
                part_number = st.text_input("元器件型号", placeholder="输入元器件型号，例如：STM32F103C8", label_visibility="collapsed", 
                                            key="part_number_input", on_change=handle_enter_press)
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="search-button">', unsafe_allow_html=True)
                search_button = st.button("查询替代方案", use_container_width=True, key="search_button")
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # 单个查询按钮逻辑 - 增加对回车键检测的条件
        
        query_error = False
        skip_tab1_query = False  # 新增标记变量
        component_info = identify_component(part_number)
        if search_button or st.session_state.search_triggered:
            if st.session_state.search_triggered:  # 重置状态
                st.session_state.search_triggered = False
                
            if not part_number:
                st.error("⚠️ 请输入元器件型号！")
                query_error = True
                skip_tab1_query = True  # 标记跳过tab1查询
            else:
                
                if not component_info:
                    st.subheader(f"未识别为元器件，请检查输入并提供更详细的信息")
                    query_error = True
                    skip_tab1_query = True  # 标记跳过tab1查询
                    
            if query_error:
                # 使用容器展示错误信息，不中断页面
                with st.container():
                    st.info("""
                    🔍 可能的原因：
                    - 输入型号格式错误（如纯数字或过短）
                    - 数据库中无匹配记录(可能器件较新)
                    - 请尝试添加封装、参数等更多信息
                    """)
                # return  # 删除原return语句，改用标记变量

            # 在tab1查询逻辑中使用标记变量控制执行
            if not skip_tab1_query:
                # 原tab1的查询逻辑代码...
                # 例如：
                with st.spinner(f"🔄 检查输入中......"):
                    if component_info:
                        custom_styles = """
                        <style>
                            /* 调整 Expander 标题样式 */
                            div[data-testid="stExpander"] > div > button > div > div {
                                font-size: 24px !important;  
                                font-weight: 600 !important;
                            }

                            /* 去掉 Expander 内容区的白色背景 */
                            div[data-testid="stExpanderContent"] {
                                background: transparent !important;  
                                font-size: 16px !important;  /* 内容区字体调小，更合理 */
                                line-height: 1.6 !important;  
                                padding: 1rem !important;             
                            }

                            /* 优化分隔线样式 */
                            hr {
                                margin: 1rem 0 !important;
                                border: none;
                                border-top: 1px solid #eee;
                            }

                            /* 优化 Tabs 组件样式：缩小“参数详情”标签 */
                            .stTabs {
                                margin-top: 1rem !important;
                            }
                            .stTabs > div > button {
                                font-size: 12px !important;  /* 调小字体 */
                                padding: 4px 8px !important; /* 调小内边距，让标签更紧凑 */
                                color: #4a5568 !important;   
                                border: none !important;     
                            }
                            .stTabs > div > button:hover {
                                background: #f1f5f9 !important;
                            }
                            .stTabs > div > button[data-selected] {
                                color: #2b6cb0 !important;
                                font-weight: 600 !important;
                                border-bottom: 2px solid #2b6cb0 !important;
                            }

                            /* 优化 DataFrame 样式 */
                            .stDataFrame {
                                border-radius: 8px;
                                overflow: hidden;
                            }
                            .stDataFrame table {
                                font-size: 14px !important;
                            }
                        </style>
                        """
                        st.markdown(custom_styles, unsafe_allow_html=True)

                        # 元器件详情 Expander
                        with st.expander(f" {component_info['mpn']} 元器件详情", expanded=False):
                            # 标题与制造商信息
                            st.markdown(
                                f"<h2 style='margin: 0; font-size: 18px; font-weight: 600;'>{component_info['manufacturer']} {component_info['mpn']}</h2>",
                                unsafe_allow_html=True
                            )

                            # 价格与品牌信息（横向布局）
                            col_price, col_brand = st.columns(2)
                            with col_price:
                                st.markdown(f"**价格**：{component_info['price']}", unsafe_allow_html=True)
                            with col_brand:
                                st.markdown(f"**品牌**：{component_info['manufacturer']}", unsafe_allow_html=True)

                            # 描述信息
                            st.caption(component_info.get('description', '电子元器件'), unsafe_allow_html=True)
                            st.markdown("<hr>", unsafe_allow_html=True)  # 分隔线

                            if component_info["parameters"]:
                                param_data = []
                                for param, value in component_info["parameters"].items():
                                    if not any(
                                        char in param or char in value 
                                        for char in ["🤖", "您好", "帮您", "输入", "常见问题"]
                                    ):
                                        param_data.append({"参数名称": param, "参数值": value})

                                if param_data:
                                    param_df = pd.DataFrame(param_data)
                                    st.dataframe(
                                        param_df,
                                        use_container_width=True,
                                        column_config={
                                            "参数名称": st.column_config.TextColumn(width="300px"),
                                            "参数值": st.column_config.TextColumn(width="500px")
                                        }
                                    )
                                else:
                                    st.info("没有找到有效参数信息", icon="ℹ️")
                            else:
                                st.info("没有找到详细参数信息", icon="ℹ️")
                with st.spinner(f"🔄 正在查询 {part_number} 的国产替代方案..."):                
                    recommendations = get_alternative_parts_func(part_number)
                    
                    # 保存到历史记录
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.search_history.append({
                        "timestamp": timestamp,
                        "part_number": part_number,
                        "recommendations": recommendations,
                        "type": "single"
                    })
                    
                    # 显示结果
                    display_search_results(part_number, recommendations)
    
    with tab2:
        # 聊天界面容器
        with st.container():
            st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)
            
            # 创建一个两列布局，主要区域给聊天，侧边留给操作按钮
            chat_col, btn_col = st.columns([4, 1])
            
            with chat_col:
                # 显示对话历史的第一条欢迎消息
                # 仅在没有其他消息时显示欢迎消息
                if len(st.session_state.chat_messages) == 1 and st.session_state.chat_messages[0]["role"] == "assistant":
                    with st.chat_message("assistant"):
                        st.markdown(st.session_state.chat_messages[0]["content"])
                
                # 增强显示用户输入区域
                st.markdown("""
                <style>
                /* 增强聊天输入框的显示效果 */
                .stChatInput {
                    border: 2px solid #4285F4 !important;
                    border-radius: 10px !important;
                    padding: 10px !important;
                    background-color: rgba(66, 133, 244, 0.05) !important;
                    margin-top: 20px !important;
                    margin-bottom: 20px !important;
                    box-shadow: 0 2px 10px rgba(66, 133, 244, 0.1) !important;
                }
                .stChatInput > div {
                    padding: 5px !important;
                }
                .stChatInput textarea, .stChatInput input {
                    font-size: 1.05rem !important;
                }
                /* 调整输入框容器边距 */
                section[data-testid="stChatInput"] {
                    padding-top: 10px !important;
                    padding-bottom: 10px !important;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # 用户输入区域
                st.markdown("<h3 style='margin-bottom: 5px;'>输入您的查询</h3>", unsafe_allow_html=True)
                user_input = st.chat_input("请输入您的元器件选型或替代方案需求...", key="chat_input_prominent")
                
                # 处理用户输入并显示对话
                if user_input:
                    # 显示用户输入
                    with st.chat_message("user"):
                        st.markdown(user_input)
                    # 添加到对话历史
                    st.session_state.chat_messages.append({"role": "user", "content": user_input})
                    
                    # 显示AI回复
                    with st.chat_message("assistant"):
                        with st.spinner("思考中..."):
                            # 导入backend模块
                            import sys
                            import os
                            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
                            from backend import chat_with_expert
                            
                            try:
                                # 调用AI对话函数并处理流式输出
                                response_stream = chat_with_expert(
                                    user_input, 
                                    history=st.session_state.chat_messages[:-1]  # 不包括刚刚添加的用户消息
                                )
                                
                                response_container = st.empty()
                                full_response = ""
                                
                                # 处理流式响应
                                for chunk in response_stream:
                                    if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                                        content = chunk.choices[0].delta.content
                                        if content:
                                            full_response += content
                                            response_container.markdown(full_response + "▌")
                                
                                # 显示最终结果
                                response_container.markdown(full_response)
                                
                                # 将AI回复添加到对话历史
                                st.session_state.chat_messages.append({"role": "assistant", "content": full_response})
                            except Exception as e:
                                error_msg = f"处理您的请求时出现错误: {str(e)}"
                                st.error(error_msg)
                                st.session_state.chat_messages.append({"role": "assistant", "content": f"抱歉，{error_msg}"})
                    
                    st.rerun()
                
                # 显示除第一条以外的对话历史 - 先显示对话历史，再显示常见问题示例
                if len(st.session_state.chat_messages) > 1:
                    # 倒序显示消息，使最新的对话在上方
                    # 按对话对（用户问题+AI回答）处理
                    messages = st.session_state.chat_messages[1:]  # 排除第一条欢迎消息
                    
                    # 按照对话对分组
                    conversation_pairs = []
                    i = 0
                    while i < len(messages):
                        # 如果是用户消息并且后面跟着助手消息，则作为一对显示
                        if i + 1 < len(messages) and messages[i]["role"] == "user" and messages[i+1]["role"] == "assistant":
                            conversation_pairs.append((messages[i], messages[i+1]))
                            i += 2
                        # 如果只有用户消息没有助手回复，或者其他不成对的情况
                        else:
                            if messages[i]["role"] == "user":
                                conversation_pairs.append((messages[i], None))
                            else:
                                conversation_pairs.append((None, messages[i]))
                            i += 1
                    
                    # 逆序显示对话对（最新的对话在上方）
                    for user_msg, assistant_msg in reversed(conversation_pairs):
                        if user_msg:
                            with st.chat_message("user"):
                                st.markdown(user_msg["content"])
                        
                        if assistant_msg:
                            with st.chat_message("assistant"):
                                st.markdown(assistant_msg["content"])
                
                # 添加清除对话按钮
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                if st.button("🗑️ 清除对话记录", use_container_width=True, key="clear_chat_main"):
                    st.session_state.chat_messages = [{
                        "role": "assistant", 
                        "content": "对话已清除。请告诉我您需要查找什么元器件的替代方案或有什么选型需求？"
                    }]
                    st.rerun()
                
                # 添加分隔线
                st.markdown("<hr style='margin: 25px 0 15px 0;'>", unsafe_allow_html=True)
                
                # 常见问题示例部分放在最后
                st.subheader("常见问题示例")
                
                # 添加CSS样式让常见问题示例更加美观，去掉复制按钮
                st.markdown("""
                <style>
                .example-container {
                    border: 1px solid #eee;
                    border-radius: 8px;
                    padding: 15px;
                    margin-bottom: 15px;
                    background-color: #f9f9f9;
                }
                </style>
                
                <div class="example-container">
                    推荐工业级3.3V LDO，要求：输入电压≥5V，输出电流500mA，静态电流&lt;50μA，通过AEC-Q100认证
                </div>
                """, unsafe_allow_html=True)
            
            with btn_col:
                # 空白区域，保持布局
                st.markdown("<div style='margin-top: 80px;'></div>", unsafe_allow_html=True)

    with tab3:
        # 文件上传区域 - 使用更醒目的样式
        st.markdown("""
        <style>
        .css-1eqt8kt {
            border: 2px dashed #4285F4 !important;
            border-radius: 10px !important;
            padding: 20px !important;
            background-color: rgba(66, 133, 244, 0.05) !important;
        }
        /* 移除上传控件下方的空白区域 */
        .css-18e3th9 {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        /* 修复整体元素垂直间距，减少空白区域 */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="text-align:center; padding:20px 0 10px 0;">
            <p style="font-size:1.1rem;">📋 请上传BOM文件进行批量查询替代方案</p>
            <p style="color:#666; font-size:0.9rem;">支持Excel(.xlsx/.xls)和CSV文件格式</p>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader("上传BOM文件", type=["xlsx", "xls", "csv"], label_visibility="collapsed")
        
        if uploaded_file is not None:
            # 批量处理按钮 - 移除AI对话按钮，使用单列布局
            col1, col2 = st.columns([3, 1])  # 调整比例，使按钮靠右对齐
            with col2:
                batch_process_button = st.button("开始批量查询", use_container_width=True, key="batch_button")
            
            # 如果上传了文件，尝试预览
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_preview = pd.read_csv(uploaded_file)  # 移除nrows=5限制，显示所有行
                else:
                    df_preview = pd.read_excel(uploaded_file) 
                
                # 直接显示数据框，不使用expander
                st.subheader("BOM文件预览")
                st.dataframe(df_preview)
            except Exception as e:
                st.error(f"文件预览失败: {e}")
            
            # 批量处理逻辑
            if batch_process_button:
                # 从backend导入函数
                import sys
                import os
                
                # 确保backend模块可以被导入
                sys.path.append(os.path.dirname(os.path.abspath(__file__)))
                
                # 现在导入所需函数
                from backend import process_bom_file, batch_get_alternative_parts
                
                # 处理BOM文件，获取更丰富的元器件信息
                components, columns_info = process_bom_file(uploaded_file)
                
                if not components:
                    st.error("⚠️ 无法从BOM文件中识别元器件型号！")
                else:
                    # 将识别信息移至侧边栏
                    st.sidebar.info(f"已识别 {len(components)} 个不同的元器件")
                    st.sidebar.success(f"识别到的关键列: 型号列({columns_info.get('mpn_column', '未识别')}), "
                              f"名称列({columns_info.get('name_column', '未识别')}), "
                              f"描述列({columns_info.get('description_column', '未识别')})")
                    
                    # 创建进度条
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # 定义进度回调函数
                    def update_progress(progress, text):
                        progress_bar.progress(progress)
                        status_text.text(text)
                    
                    # 批量查询
                    with st.spinner("批量查询中，请稍候..."):
                        batch_results = batch_get_alternative_parts(components, update_progress)
                    
                    # 完成进度
                    progress_bar.progress(1.0)
                    # 隐藏处理完成提示
                    status_text.empty()
                    
                    # 保存到历史记录
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.search_history.append({
                        "timestamp": timestamp,
                        "part_number": f"批量查询({len(components)}个)",
                        "batch_results": batch_results,
                        "type": "batch"
                    })
                    
                    # 直接显示详细的替代方案结果，不使用摘要表格
                    st.subheader("批量查询结果")
                    
                    # 直接显示详细替代方案，不使用expander
                    for mpn, result_info in batch_results.items():
                        alts = result_info.get('alternatives', [])
                        name = result_info.get('name', '')
                        
                        # 显示每个元器件的标题
                        st.markdown(f"### {mpn} ({name})")
                        
                        # 使用与单个查询相同的display_search_results函数来显示结果
                        if alts:
                            display_search_results(mpn, alts)
                        else:
                            st.info("未找到替代方案")
                        
                        st.markdown("---")
                    
                    # 提供下载结果的选项
                    st.subheader("📊 下载查询结果")
                    
                    # 将结果转换为可下载的Excel格式
                    result_data = []
                    
                    # 遍历所有批量查询结果
                    for mpn, result_info in batch_results.items():
                        alts = result_info.get('alternatives', [])
                        name = result_info.get('name', '')
                        description = result_info.get('description', '')
                        
                        # 确保alts是列表类型
                        if not isinstance(alts, list):
                            alts = []
                        
                        # 如果没有替代方案，添加一个"未找到替代方案"的记录
                        if not alts:
                            result_data.append({
                                "原元器件名称": name,
                                "原型号": mpn,
                                "原器件描述": description,
                                "替代方案序号": "-",
                                "替代型号": "未找到替代方案",
                                "替代品牌": "-",
                                "类别": "-",
                                "封装": "-",
                                "类型": "-",
                                "参数": "-",
                                "数据手册链接": "-"
                            })
                        else:
                            # 添加找到的替代方案
                            for i, alt in enumerate(alts, 1):
                                # 确保alt是字典类型
                                if not isinstance(alt, dict):
                                    continue
                                    
                                result_data.append({
                                    "原元器件名称": name,
                                    "原型号": mpn,
                                    "原器件描述": description,
                                    "替代方案序号": i,
                                    "替代型号": alt.get("model", ""),
                                    "替代品牌": alt.get("brand", "未知品牌"),
                                    "类别": alt.get("category", "未知类别"),
                                    "封装": alt.get("package", "未知封装"),
                                    "类型": alt.get("type", "未知"),
                                    "参数": alt.get("parameters", ""),
                                    "数据手册链接": alt.get("datasheet", "")
                                })
                    
                    # 当有结果数据时，生成并提供下载
                    if result_data:
                        # 创建DataFrame
                        df_results = pd.DataFrame(result_data)
                        
                        # 添加两种下载格式选项
                        col1, col2 = st.columns(2)
                        
                        # 创建Excel文件
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as excel_file:
                            with pd.ExcelWriter(excel_file.name, engine='openpyxl') as writer:
                                df_results.to_excel(writer, sheet_name='替代方案查询结果', index=False)
                            
                            # 读取生成的Excel文件
                            with open(excel_file.name, 'rb') as f:
                                excel_data = f.read()
                        
                        # 创建CSV文件
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as csv_file:
                            df_results.to_csv(csv_file.name, index=False, encoding='utf-8-sig')  # 使用带BOM的UTF-8编码，Excel可以正确识别中文
                            
                            # 读取生成的CSV文件
                            with open(csv_file.name, 'rb') as f:
                                csv_data = f.read()
                        
                        # 显示两个下载按钮
                        with col1:
                            st.download_button(
                                label="📥 下载为Excel文件 (.xlsx)",
                                data=excel_data,
                                file_name=f"元器件替代方案查询结果_{timestamp.replace(':', '-')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        
                        with col2:
                            st.download_button(
                                label="📥 下载为CSV文件 (.csv)",
                                data=csv_data,
                                file_name=f"元器件替代方案查询结果_{timestamp.replace(':', '-')}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                    else:
                        st.warning("⚠️ 没有查询到任何替代方案，无法生成下载文件")
        else:
            # 空白展示区，不显示任何提示或装饰
            pass

    # 在此处添加历史查询功能
    if 'search_history' not in st.session_state:
        st.session_state.search_history = []
    
    # 将历史查询记录移动到侧边栏中
    with st.sidebar:
        st.title("历史查询记录")
        
        # 历史记录标题和清除按钮
        if len(st.session_state.search_history) > 0:
            if st.button("清除历史记录", key="clear_history_tab2"):
                st.session_state.search_history = []
                st.rerun()
        
        # 显示历史记录
        if not st.session_state.search_history:
            st.info("暂无历史查询记录")
        else:
            for idx, history_item in enumerate(reversed(st.session_state.search_history)):
                query_type = "批量查询" if history_item.get('type') == 'batch' else "单元器件查询"
                
                # 创建一个带样式的容器
                with st.container():
                    st.markdown(f"""
                    <div style="padding: 10px; border-radius: 5px; margin-bottom: 10px; border: 1px solid #e6e6e6; background-color: #f9f9f9;">
                        <div style="font-weight: bold;">{history_item['part_number']}</div>
                        <div style="font-size: 0.8em; color: #666;">
                            ({query_type}) {history_item['timestamp']}
                        </div>
                        <div style="margin-top: 5px; font-size: 0.9em;">
                            {
                                '批量查询多个元器件' if history_item.get('type') == 'batch' 
                                else f"找到 {len(history_item.get('recommendations', []))} 种替代方案"
                            }
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 查看按钮
                    if st.button(f"查看详情", key=f"view_history_{idx}", use_container_width=True):
                        st.session_state.selected_history = history_item
                        st.rerun()
        
        # 添加底部提示信息
        st.markdown("<hr style='margin-top: 30px; margin-bottom: 15px; opacity: 0.3;'>", unsafe_allow_html=True)
        st.markdown("<small style='color: #666; font-size: 0.8em;'>历史记录保存在会话中，刷新页面后将被清除</small>", unsafe_allow_html=True)
        
        # 添加工具提示
        st.markdown("<div style='position: absolute; bottom: 20px; padding: 10px; width: calc(100% - 40px);'>", unsafe_allow_html=True)
        st.caption("📌 提示: 点击查看详情可以查看历史查询结果")
        st.caption("🔍 查询结果会自动保存到历史记录中")
        st.markdown("</div>", unsafe_allow_html=True)

    # 修改历史记录查看逻辑，以支持批量查询结果
    if 'selected_history' in st.session_state:
        st.markdown("---")
        history_item = st.session_state.selected_history
        
        if history_item.get('type') == 'batch':
            # 显示批量查询结果
            st.subheader(f"历史批量查询结果: {history_item['part_number']}")
            
            batch_results = history_item.get('batch_results', {})
            
            # 直接显示详细的替代方案结果，不使用摘要表格
            st.subheader("批量查询结果")
            
            # 直接显示详细替代方案，不使用expander
            for mpn, result_info in batch_results.items():
                alts = result_info.get('alternatives', [])
                name = result_info.get('name', '')
                
                # 显示每个元器件的标题
                st.markdown(f"### {mpn} ({name})")
                
                # 使用与单个查询相同的display_search_results函数来显示结果
                if alts:
                    display_search_results(mpn, alts)
                else:
                    st.info("未找到替代方案")
                
                st.markdown("---")
        else:
            # 单个查询结果显示
            st.subheader(f"历史查询结果: {history_item['part_number']}")
            
            # 使用与原始查询相同的显示逻辑
            recommendations = history_item.get('recommendations', [])
            display_search_results(history_item['part_number'], recommendations)
        
        # 将查询时间显示在返回按钮上方
        st.caption(f"查询时间: {history_item['timestamp']}")
        
        if st.button("返回"):
            del st.session_state.selected_history
            st.rerun()

    # 添加页脚信息 - 降低显示度
    st.markdown("---")
    st.markdown('<p class="footer-text">本工具基于DeepSeek大语言模型和Nexar元件库，提供元器件替代参考</p>', unsafe_allow_html=True)

# 抽取显示结果的函数，以便重复使用
def display_search_results(part_number, recommendations):
    # 结果区域添加容器
    
    if recommendations:
        # 添加CSS样式 - 调整价格对齐和Pin兼容突出显示
        st.markdown("""
        <style>
            div.card-wrapper {
                display: flex;
                flex-direction: row;
                overflow-x: auto;
                gap: 15px;
                padding-bottom: 10px;
            }
            .price-value {
                color: #e53935;
                font-weight: bold;
                min-width: 80px; /* 设置最小宽度确保对齐 */
                display: inline-block; /* 使宽度设置生效 */
            }
            /* Pin兼容显示样式 - 移除背景色 */
            .pin-compatible {
                border: 1px solid #ccc !important;
                text-align: left !important; /* 左对齐 */
            }
            .non-pin-compatible {
                border: 1px solid #ccc !important;
                text-align: left !important; /* 左对齐 */
            }
            /* 调整信息行样式确保对齐 */
            .info-row {
                display: flex;
                margin-bottom: 0px;
            }
            .info-label {
                width: 80px;
                font-weight: 500;
            }
            .info-value {
                flex: 1;
            }
            /* 参数内容样式，与其他信息对齐 */
            .param-content {
                padding-left: 80px;
                margin-bottom: 0px;
                word-wrap: break-word;
            }
            /* 修复间距问题 */
            .element-container {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }
            /* 标签专用样式 */
            .type-label {
                margin: 0 !important;
                padding: 2px 8px !important;
                border-radius: 4px !important;
                display: inline-block !important;
            }
        </style>
        """, unsafe_allow_html=True)
        
        # 创建列容器来强制横向布局
        cols = st.columns(len(recommendations))
        
        # 在每个列中放置一个卡片（优化后）
        for i, (col, rec) in enumerate(zip(cols, recommendations), 1):
            with col:
                # 方案标题
                st.markdown(f"### 方案 {i}")
                
                # 型号名称
                st.markdown(f"<h4 style='font-size:1.2rem; margin-bottom: 0.3rem;'>{rec.get('model', '未知型号')}</h4>", unsafe_allow_html=True)
                
                # 品牌显示（移除边框，改为纯文本）
                st.markdown(f"**品牌：** {rec.get('brand', '未知品牌')}", unsafe_allow_html=True)
                
                # Pin-to-Pin 兼容性（简化样式，用符号直观展示）
                pin_to_pin = rec.get('pinToPin', False)
                pin_symbol = "✅" if pin_to_pin else "❌"
                st.markdown(f"**Pin兼容：** {pin_symbol} {('Pin兼容' if pin_to_pin else '非Pin兼容')}", unsafe_allow_html=True)
                
                # 国产/进口标签（绿色背景标识国产）
                type_display = ""
                if rec['type'] == "国产":
                    type_display = "<span style='background-color: #4CAF50; color: white; padding: 2px 8px; border-radius: 4px;'>国产</span>"
                else:
                    type_display = "<span style='background-color: #2196F3; color: white; padding: 2px 8px; border-radius: 4px;'>进口</span>"
                st.markdown(f"**类型：** {type_display}", unsafe_allow_html=True)
                
                # 统一信息布局（紧凑排列）
                st.markdown("""
                <div style="margin-top: 8px; line-height: 1.6;">
                    <div style="display: flex; margin-bottom: 4px;">
                        <div style="min-width: 60px; font-weight: 500;">封装：</div>
                        <div>{}</div>
                    </div>
                    <div style="display: flex; margin-bottom: 4px;">
                        <div style="min-width: 60px; font-weight: 500;">价格：</div>
                        <div>{}</div>
                    </div>
                    <div style="display: flex; margin-bottom: 8px;">
                        <div style="min-width: 60px; font-weight: 500;">参数：</div>
                        <div>{}</div>
                    </div>
                    <div style="display: flex;">
                        <div style="min-width: 60px; font-weight: 500;">供货周期：</div>
                        <div>{}</div>
                    </div>
                </div>
                """.format(
                    rec.get('package', 'LQFP48'),
                    rec.get('price', '未知'),
                    rec.get('parameters', 'CPU内核: ARM Cortex-M3, 主频: 72MHz, Flash: 64KB, RAM: 20KB, IO: 37'),
                    rec.get('leadTime', '3-5周')
                ), unsafe_allow_html=True)
                
                # 数据手册链接（简化样式）
                st.markdown(f"[数据手册]({rec.get('datasheet', 'https://example.com')})", unsafe_allow_html=True)
    else:
        st.info("未找到替代方案")