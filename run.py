from frontend import render_ui
from backend import get_alternative_parts, process_bom_file, batch_get_alternative_parts
from custom_components.hide_sidebar_items import get_sidebar_hide_code

def main():
    # 渲染主界面UI（内部会首先调用st.set_page_config）
    render_ui(get_alternative_parts)

if __name__ == "__main__":
    main()