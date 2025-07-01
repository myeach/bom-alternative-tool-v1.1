import os
import sys
import importlib.util
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
import json
import re
import streamlit as st
import pandas as pd
import tempfile
from nexarClient import NexarClient

# 检查并安装必要的依赖库
def check_and_install_dependencies():
    """检查并安装处理Excel文件所需的依赖库"""
    dependencies = {
        'xlrd': 'xlrd>=2.0.1',      # 处理旧版 .xls 文件
        'openpyxl': 'openpyxl',     # 处理新版 .xlsx 文件
    }
    
    for module, package in dependencies.items():
        if importlib.util.find_spec(module) is None:
            try:
                st.info(f"正在安装依赖: {package}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                st.success(f"{package} 安装完成")
            except Exception as e:
                st.error(f"安装 {package} 失败: {e}")
                st.info(f"请手动安装: pip install {package}")

# 在导入pandas之前检查依赖
check_and_install_dependencies()

# 加载环境变量
load_dotenv(override=True)

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
if not DEEPSEEK_API_KEY:
    raise ValueError("错误：未找到 DEEPSEEK_API_KEY 环境变量。")
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# Nexar API 配置
NEXAR_CLIENT_ID = os.getenv("NEXAR_CLIENT_ID")
NEXAR_CLIENT_SECRET = os.getenv("NEXAR_CLIENT_SECRET")
if not NEXAR_CLIENT_ID or not NEXAR_CLIENT_SECRET:
    raise ValueError("错误：未找到 NEXAR_CLIENT_ID 或 NEXAR_CLIENT_SECRET 环境变量。")
nexar_client = NexarClient(NEXAR_CLIENT_ID, NEXAR_CLIENT_SECRET)


# GraphQL 查询
QUERY_ALTERNATIVE_PARTS = '''
query findAlternativeParts($q: String!, $limit: Int = 10) {
  supSearchMpn(q: $q, limit: $limit) {
    hits
    results {
      part {
        mpn
        manufacturer {
          name
        }
        specs {
          attribute {
            name
          }
          value
        }
        medianPrice1000 {
          price
          currency
        }
        bestImage {
          url
        }
        estimatedFactoryLeadDays
        similarParts {
          name
          mpn
          manufacturer {
            name
          }
          medianPrice1000 {
            price
            currency
          }
          octopartUrl
          estimatedFactoryLeadDays
        }
      }
    }
  }
}
'''

def get_nexar_alternatives(mpn: str, limit: int = 10):
    variables = {"q": mpn, "limit": limit}
    try:
        data = nexar_client.get_query(QUERY_ALTERNATIVE_PARTS, variables)
        alternative_parts = []
        
        # 添加数据有效性检查与调试信息
        if not data:
            st.warning(f"Nexar API 未返回有效数据，可能是查询 '{mpn}' 无结果")
            return []
            
        # 显示调试信息
        with st.sidebar.expander(f"Nexar API 调试信息 - {mpn}", expanded=False):
            st.write(f"**原始Nexar API响应结构:**")
            st.write(data)
            
        # 完全重写数据提取逻辑，以更健壮的方式处理各种可能的结构
        if isinstance(data, dict):
            # 尝试从不同位置提取数据
            sup_search = data.get("supSearchMpn", {})
            
            # 如果supSearchMpn是字典
            if isinstance(sup_search, dict):
                results = sup_search.get("results", [])
                
                # 如果results是列表
                if isinstance(results, list):
                    # 正常处理
                    for result in results:
                        if not isinstance(result, dict):
                            continue
                            
                        part = result.get("part", {})
                        if not isinstance(part, dict):
                            continue
                            
                        similar_parts = part.get("similarParts", [])
                        if not isinstance(similar_parts, list):
                            continue
                            
                        for similar in similar_parts:
                            if not isinstance(similar, dict):
                                continue
                                
                            # 提取价格信息
                            price_info = similar.get("medianPrice1000", {})
                            price = "未知"
                            if isinstance(price_info, dict):
                                price_value = price_info.get("price")
                                currency = price_info.get("currency", "USD")
                                if price_value:
                                    price = f"{price_value:.4f} {currency}"
                            
                            # 提取生命周期和库存状态
                            life_cycle = similar.get("lifeCycle", "未知")
                            obsolete = similar.get("obsolete", False)
                            lead_days = similar.get("estimatedFactoryLeadDays")
                            
                            # 确定产品状态
                            status = "未知"
                            if obsolete:
                                status = "已停产"
                            elif life_cycle:
                                if "OBSOLETE" in life_cycle or "END OF LIFE" in life_cycle.upper():
                                    status = "已停产"
                                elif "ACTIVE" in life_cycle.upper() or "PRODUCTION" in life_cycle.upper():
                                    status = "量产中"
                                elif "NEW" in life_cycle.upper() or "INTRO" in life_cycle.upper():
                                    status = "新产品"
                                elif "NOT RECOMMENDED" in life_cycle.upper():
                                    status = "不推荐使用"
                                else:
                                    status = life_cycle
                            
                            # 提取制造商信息
                            manufacturer = similar.get("manufacturer", {})
                            manufacturer_name = ""
                            if isinstance(manufacturer, dict):
                                manufacturer_name = manufacturer.get("name", "")
                            
                            # 构建替代元器件信息
                            alternative_parts.append({
                                "name": similar.get("name", ""),
                                "mpn": similar.get("mpn", ""),
                                "manufacturer": manufacturer_name,
                                "price": price,
                                "status": status,
                                "leadTime": f"{lead_days} 天" if lead_days else "未知",
                                "octopartUrl": similar.get("octopartUrl", "")
                            })
                else:
                    # 如果results不是列表，尝试其他数据结构
                    with st.sidebar.expander("调试信息 - API结构错误", expanded=False):
                        st.warning(f"Nexar API 返回了非标准结构的数据 (results不是列表)")
                    
                    # 尝试直接从顶层提取数据
                    parts_data = []
                    
                    # 检查是否有直接的part字段
                    if "part" in sup_search:
                        part = sup_search.get("part", {})
                        if isinstance(part, dict) and "similarParts" in part:
                            parts_data = part.get("similarParts", [])
                    
                    # 如果找到疑似部件数据
                    if isinstance(parts_data, list):
                        for part_item in parts_data:
                            if not isinstance(part_item, dict):
                                continue
                                
                            alternative_parts.append({
                                "name": part_item.get("name", "未知名称"),
                                "mpn": part_item.get("mpn", "未知型号"),
                                "manufacturer": part_item.get("manufacturer", {}).get("name", "未知"),
                                "price": "未知",
                                "status": "未知",
                                "leadTime": "未知",
                                "octopartUrl": part_item.get("octopartUrl", "https://example.com")
                            })
            else:
                with st.sidebar.expander("调试信息 - API结构错误", expanded=False):
                    st.warning(f"Nexar API 返回了非标准结构 (supSearchMpn不是字典)")
                # 尝试从整个响应中找到任何可能的部件信息
                for key, value in data.items():
                    if isinstance(value, dict) and "parts" in value:
                        parts = value.get("parts", [])
                        if isinstance(parts, list):
                            for part in parts:
                                if not isinstance(part, dict):
                                    continue
                                alternative_parts.append({
                                    "name": part.get("name", "未知名称"),
                                    "mpn": part.get("mpn", "未知型号"),
                                    "manufacturer": "未知制造商",
                                    "price": "未知",
                                    "status": "未知",
                                    "leadTime": "未知",
                                    "octopartUrl": "https://example.com"
                                })
        
        # 如果无法找到任何替代件
        if not alternative_parts:
            # 只在侧边栏显示错误信息，而不在主界面显示
            st.sidebar.info(f"Nexar API 未能为 '{mpn}' 找到替代元器件")
            
        return alternative_parts
        
    except Exception as e:
        st.error(f"Nexar API 查询失败: {e}")
        import traceback
        with st.sidebar.expander("Nexar API错误详情", expanded=False):
            st.code(traceback.format_exc())
        return []

def is_domestic_brand(model_name, brand_name=""):
    """
    优化产地判断逻辑：优先使用品牌信息，再辅助型号判断
    :param model_name: 元器件型号
    :param brand_name: 元器件品牌（优先使用）
    :return: 是否为国产
    """
    # 明确的国产品牌列表（中英文对照，避免歧义）
    domestic_brands = {
        # 中国大陆品牌
        "兆易创新": "GigaDevice",
        "沁恒": "WCH",
        "复旦微电子": "Fudan Micro",
        "中颖电子": "Zhongying Electronics",
        "圣邦微电子": "SG Micro",
        "华大半导体": "HuaDa Semiconductor",
        "华虹": "HuaHong",
        "士兰微": "Silan Micro",
        "长电科技": "JCET",
        "通富微电": "TFME",
        # 台湾地区品牌（视为国产）
        "台积电": "TSMC",
        "联发科": "MediaTek",
        "台达电子": "Delta Electronics",
        "友达光电": "AUO",
        "华硕": "ASUS",
        "微星": "MSI",
        "奇景光电": "Himax",
        "联咏科技": "Novatek",
        "瑞昱半导体": "Realtek",
        "立锜科技": "Richtek",
        # 英文品牌（避免与进口品牌混淆）
        "GigaDevice": "兆易创新",
        "WCH": "沁恒",
        "SG Micro": "圣邦微电子",
        "3PEAK": "思瑞浦",
        "Chipsea": "芯海科技",
        "Chipown": "芯朋微",
        # 台湾地区品牌英文（补充）
        "TSMC": "台积电",
        "MediaTek": "联发科",
        "Delta": "台达电子",
        "Realtek": "瑞昱半导体"
    }
    
    # 明确的进口品牌列表（排除逻辑）
    foreign_brands = {
        "TI": "德州仪器",
        "ADI": "亚德诺",
        "ST": "意法半导体",
        "NXP": "恩智浦",
        "Microchip": "微芯科技",
        "Infineon": "英飞凌",
        "Maxim": "美信",
        "ON Semiconductor": "安森美"
    }
    
    # 优先使用品牌信息判断（最准确）
    if brand_name:
        brand_lower = brand_name.lower()
        # 检查是否为明确的国产品牌
        if any(b.lower() in brand_lower for b in domestic_brands.keys()) or \
           any(b.lower() in brand_lower for b in domestic_brands.values()):
            return True
        # 检查是否为明确的进口品牌（排除）
        if any(b.lower() in brand_lower for b in foreign_brands.keys()) or \
           any(b.lower() in brand_lower for b in foreign_brands.values()):
            return False
    
    # 品牌信息不足时，辅助使用型号判断（严格匹配前缀）
    model_lower = model_name.lower()
    # 国产型号常见前缀（避免模糊匹配）
    domestic_prefixes = ["gd", "wch", "sg", "ch", "hf", "stc", "xc", "bp",
                         # 台湾地区品牌前缀
                        "mtk", "rtk", "richtek", "novatek", "himax"  # 联发科/瑞昱/立锜/联咏/奇景光电等
                         ]
    # 进口型号常见前缀（排除）
    foreign_prefixes = ["ti", "st", "nxp", "ad", "mc", "atm", "pic", "ir"]
    
    # 先检查是否为进口型号前缀（优先级高于国产）
    if any(model_lower.startswith(prefix) for prefix in foreign_prefixes):
        return False
    # 再检查是否为国产型号前缀
    if any(model_lower.startswith(prefix) for prefix in domestic_prefixes):
        return True
    
    # 最终 fallback：通过品牌名模糊匹配
    return any(brand.lower() in model_lower or brand.lower() in brand_lower 
               for brand in domestic_brands.keys() | domestic_brands.values())

def extract_json_content(content, call_type="初次调用"):
    # 检查输入是否为字符串类型
    if not isinstance(content, str):
        st.error(f"{call_type} - 输入内容不是字符串: {type(content)}")
        return []
        
    # 记录原始内容以便调试
    with st.sidebar.expander(f"调试信息 - 原始响应 ({call_type})", expanded=False):
        st.write(f"**尝试解析的原始响应内容 ({call_type}):**")
        st.code(content, language="text")

    # 处理空响应
    if not content or content.strip() == "":
        st.warning(f"{call_type} 返回了空响应")
        return []

    # 直接尝试解析 JSON
    try:
        parsed = json.loads(content)
        # 检查是否为列表
        if not isinstance(parsed, list):
            raise ValueError("响应不是 JSON 数组")
        # 补全缺少的字段
        for item in parsed:
            # 确保item是字典类型
            if not isinstance(item, dict):
                continue
                
            # 确保基本字段存在
            item["model"] = item.get("model", "未知型号")
            item["brand"] = item.get("brand", "未知品牌")
            item["parameters"] = item.get("parameters", "参数未知")
            item["type"] = item.get("type", "未知")
            item["datasheet"] = item.get("datasheet", "https://www.example.com/datasheet")
            
            # 确保新增字段存在
            item["category"] = item.get("category", "未知类别")
            item["package"] = item.get("package", "未知封装")
            
            # 添加价格信息（如果没有）并确保价格包含货币符号
            price = item.get("price", "未知")
            # 检查价格是否已包含货币符号
            if price != "未知" and not any(symbol in price for symbol in ["¥", "￥", "$"]):
                # 如果是纯数字或数字范围，添加美元符号
                if re.match(r'^[\d\.\-\s]+$', price):
                    # 处理类似 "1.8-2.5" 的价格范围
                    if "-" in price:
                        price_parts = price.split("-")
                        price = f"${price_parts[0].strip()}-${price_parts[1].strip()}"
                    else:
                        price = f"${price.strip()}"
            item["price"] = price
            
            # 添加物料状态信息
            item["status"] = item.get("status", "未知")
            item["leadTime"] = item.get("leadTime", "未知")
            
            # 添加 pin-to-pin 替代相关信息
            item["pinToPin"] = item.get("pinToPin", False)
            item["compatibility"] = item.get("compatibility", "兼容性未知")
            
        return parsed
    except json.JSONDecodeError:
        pass

    # 尝试提取代码块中的 JSON
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    code_match = re.search(code_block_pattern, content, re.DOTALL)
    if (code_match):
        json_content = code_match.group(1).strip()
        try:
            parsed = json.loads(json_content)
            for item in parsed:
                # 确保item是字典类型
                if not isinstance(item, dict):
                    continue
                    
                # 确保基本字段存在
                item["model"] = item.get("model", "未知型号")
                item["brand"] = item.get("brand", "未知品牌")
                item["parameters"] = item.get("parameters", "参数未知")
                item["type"] = item.get("type", "未知")
                item["datasheet"] = item.get("datasheet", "https://www.example.com/datasheet")
                
                # 确保新增字段存在
                item["category"] = item.get("category", "未知类别")
                item["package"] = item.get("package", "未知封装")
                
                # 添加价格信息（如果没有）并确保价格包含货币符号
                price = item.get("price", "未知")
                # 检查价格是否已包含货币符号
                if price != "未知" and not any(symbol in price for symbol in ["¥", "￥", "$"]):
                    # 如果是纯数字或数字范围，添加美元符号
                    if re.match(r'^[\d\.\-\s]+$', price):
                        # 处理类似 "1.8-2.5" 的价格范围
                        if "-" in price:
                            price_parts = price.split("-")
                            price = f"${price_parts[0].strip()}-${price_parts[1].strip()}"
                        else:
                            price = f"${price.strip()}"
                item["price"] = price
                
                # 添加物料状态信息
                item["status"] = item.get("status", "未知")
                item["leadTime"] = item.get("leadTime", "未知")
                
                # 添加 pin-to-pin 替代相关信息
                item["pinToPin"] = item.get("pinToPin", False)
                item["compatibility"] = item.get("compatibility", "兼容性未知")
                
            return parsed
        except json.JSONDecodeError:
            pass

    # 尝试提取裸 JSON 数组
    json_match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            for item in parsed:
                # 确保item是字典类型
                if not isinstance(item, dict):
                    continue
                    
                if not all(key in item for key in ["model", "parameters", "type", "datasheet"]):
                    item["model"] = item.get("model", "未知型号")
                    item["parameters"] = item.get("parameters", "参数未知")
                    item["type"] = item.get("type", "未知")
                    item["datasheet"] = item.get("datasheet", "https://www.example.com/datasheet")
                # 确保品牌字段存在
                if "brand" not in item:
                    item["brand"] = item.get("brand", "未知品牌")
                # 确保新增字段存在
                item["category"] = item.get("category", "未知类别")
                item["package"] = item.get("package", "未知封装")
                
                # 添加价格信息（如果没有）并确保价格包含货币符号
                price = item.get("price", "未知")
                # 检查价格是否已包含货币符号
                if price != "未知" and not any(symbol in price for symbol in ["¥", "￥", "$"]):
                    # 如果是纯数字或数字范围，添加美元符号
                    if re.match(r'^[\d\.\-\s]+$', price):
                        # 处理类似 "1.8-2.5" 的价格范围
                        if "-" in price:
                            price_parts = price.split("-")
                            price = f"${price_parts[0].strip()}-${price_parts[1].strip()}"
                        else:
                            price = f"${price.strip()}"
                item["price"] = price
                
                # 添加物料状态信息
                item["status"] = item.get("status", "未知")
                item["leadTime"] = item.get("leadTime", "未知")
                
                # 添加 pin-to-pin 替代相关信息
                item["pinToPin"] = item.get("pinToPin", False)
                item["compatibility"] = item.get("compatibility", "兼容性未知")
                
            return parsed
        except json.JSONDecodeError:
            pass

    # 尝试逐行解析，处理可能的多行 JSON
    lines = content.strip().split('\n')
    json_content = ''
    in_json = False
    for line in lines:
        line = line.strip()
        if line.startswith('[') or in_json:
            json_content += line
            in_json = True
        if line.endswith(']'):
            break
    if json_content:
        try:
            parsed = json.loads(json_content)
            for item in parsed:
                # 确保item是字典类型
                if not isinstance(item, dict):
                    continue
                    
                if not all(key in item for key in ["model", "parameters", "type", "datasheet"]):
                    item["model"] = item.get("model", "未知型号")
                    item["parameters"] = item.get("parameters", "参数未知")
                    item["type"] = item.get("type", "未知")
                    item["datasheet"] = item.get("datasheet", "https://www.example.com/datasheet")
                # 确保品牌字段存在
                if "brand" not in item:
                    item["brand"] = item.get("brand", "未知品牌")
                # 确保新增字段存在
                item["category"] = item.get("category", "未知类别")
                item["package"] = item.get("package", "未知封装")
                
                # 添加价格信息（如果没有）并确保价格包含货币符号
                price = item.get("price", "未知")
                # 检查价格是否已包含货币符号
                if price != "未知" and not any(symbol in price for symbol in ["¥", "￥", "$"]):
                    # 如果是纯数字或数字范围，添加美元符号
                    if re.match(r'^[\d\.\-\s]+$', price):
                        # 处理类似 "1.8-2.5" 的价格范围
                        if "-" in price:
                            price_parts = price.split("-")
                            price = f"${price_parts[0].strip()}-${price_parts[1].strip()}"
                        else:
                            price = f"${price.strip()}"
                item["price"] = price
                
                # 添加物料状态信息
                item["status"] = item.get("status", "未知")
                item["leadTime"] = item.get("leadTime", "未知")
                
                # 添加 pin-to-pin 替代相关信息
                item["pinToPin"] = item.get("pinToPin", False)
                item["compatibility"] = item.get("compatibility", "兼容性未知")
                
            return parsed
        except json.JSONDecodeError:
            pass

    # 添加更强大的JSON提取处理，处理更多边缘情况
    # 尝试从文本中抽取任何看起来像JSON对象的内容
    possible_json_pattern = r'\[\s*\{\s*"model"\s*:.*?\}\s*\]'
    json_fragments = re.findall(possible_json_pattern, content, re.DOTALL)
    
    for fragment in json_fragments:
        try:
            parsed = json.loads(fragment)
            # 补全缺少的字段
            for item in parsed:
                # 确保item是字典类型
                if not isinstance(item, dict):
                    continue
                    
                if not all(key in item for key in ["model", "parameters", "type", "datasheet"]):
                    item["model"] = item.get("model", "未知型号")
                    item["parameters"] = item.get("parameters", "参数未知")
                    item["type"] = item.get("type", "未知")
                    item["datasheet"] = item.get("datasheet", "https://www.example.com/datasheet")
                # 确保品牌字段存在
                if "brand" not in item:
                    item["brand"] = item.get("brand", "未知品牌")
                # 确保新增字段存在
                item["category"] = item.get("category", "未知类别")
                item["package"] = item.get("package", "未知封装")
                
                # 添加价格信息（如果没有）并确保价格包含货币符号
                price = item.get("price", "未知")
                # 检查价格是否已包含货币符号
                if price != "未知" and not any(symbol in price for symbol in ["¥", "￥", "$"]):
                    # 如果是纯数字或数字范围，添加美元符号
                    if re.match(r'^[\d\.\-\s]+$', price):
                        # 处理类似 "1.8-2.5" 的价格范围
                        if "-" in price:
                            price_parts = price.split("-")
                            price = f"${price_parts[0].strip()}-${price_parts[1].strip()}"
                        else:
                            price = f"${price.strip()}"
                item["price"] = price
                
                # 添加物料状态信息
                item["status"] = item.get("status", "未知")
                item["leadTime"] = item.get("leadTime", "未知")
                
                # 添加 pin-to-pin 替代相关信息
                item["pinToPin"] = item.get("pinToPin", False)
                item["compatibility"] = item.get("compatibility", "兼容性未知")
                
            return parsed
        except json.JSONDecodeError:
            pass
            
    # 如果上面方法都失败，尝试手动修复常见的JSON格式错误
    for fix_attempt in [
        lambda c: c.replace("'", '"'),  # 单引号替换为双引号
        lambda c: re.sub(r'",\s*\}', '"}', c),  # 修复尾部多余逗号
        lambda c: re.sub(r',\s*]', ']', c)  # 修复数组尾部多余逗号
    ]:
        try:
            fixed_content = fix_attempt(content)
            parsed = json.loads(fixed_content)
            if isinstance(parsed, list):
                for item in parsed:
                    # 确保item是字典类型
                    if not isinstance(item, dict):
                        continue
                        
                    if not all(key in item for key in ["model", "parameters", "type", "datasheet"]):
                        item["model"] = item.get("model", "未知型号")
                        item["parameters"] = item.get("parameters", "参数未知")
                        item["type"] = item.get("type", "未知")
                        item["datasheet"] = item.get("datasheet", "https://www.example.com/datasheet")
                    # 确保品牌字段存在
                    if "brand" not in item:
                        item["brand"] = item.get("brand", "未知品牌")
                    # 确保新增字段存在
                    item["category"] = item.get("category", "未知类别")
                    item["package"] = item.get("package", "未知封装")
                    
                    # 添加价格信息（如果没有）并确保价格包含货币符号
                    price = item.get("price", "未知")
                    # 检查价格是否已包含货币符号
                    if price != "未知" and not any(symbol in price for symbol in ["¥", "￥", "$"]):
                        # 如果是纯数字或数字范围，添加美元符号
                        if re.match(r'^[\d\.\-\s]+$', price):
                            # 处理类似 "1.8-2.5" 的价格范围
                            if "-" in price:
                                price_parts = price.split("-")
                                price = f"${price_parts[0].strip()}-${price_parts[1].strip()}"
                            else:
                                price = f"${price.strip()}"
                    item["price"] = price
                    
                    # 添加物料状态信息
                    item["status"] = item.get("status", "未知")
                    item["leadTime"] = item.get("leadTime", "未知")
                    
                    # 添加 pin-to-pin 替代相关信息
                    item["pinToPin"] = item.get("pinToPin", False)
                    item["compatibility"] = item.get("compatibility", "兼容性未知")
                    
                return parsed
        except:
            pass

    # 处理可能的非标准JSON格式
    try:
        # 最后尝试一种更宽松的解析方法，直接从文本构建数据
        # 如果内容看起来包含元器件信息但不是有效JSON，构造一个基本响应
        if "型号" in content and ("国产" in content or "进口" in content):
            st.sidebar.warning(f"DeepSeek API返回了非标准JSON格式，尝试构建基本替代方案 ({call_type})")
            # 构造一个基本的替代方案
            basic_alt = [{
                "model": "未能解析出型号",
                "brand": "未知品牌",
                "category": "未知类别",
                "package": "未知封装",
                "parameters": "无法解析参数，请查看API原始响应",
                "type": "未知",
                "price": "未知",
                "status": "未知",
                "leadTime": "未知",
                "pinToPin": False,
                "compatibility": "未知",
                "datasheet": "https://www.example.com"
            }]
            return basic_alt
    except:
        pass

    st.sidebar.error(f"无法从API响应中提取有效的JSON内容 ({call_type})")
    return []

def get_alternative_parts(part_number):
    # Step 1: 获取 Nexar API 的替代元器件数据
    nexar_alternatives = get_nexar_alternatives(part_number, limit=10)
    context = "Nexar API 提供的替代元器件数据：\n"
    if (nexar_alternatives):
        for i, alt in enumerate(nexar_alternatives, 1):
            context += f"{i}. 型号: {alt['mpn']}, 名称: {alt['name']}, 链接: {alt['octopartUrl']}\n"
    else:
        # 将警告移到侧边栏
        st.sidebar.warning(f"Nexar API 未能为 '{part_number}' 找到替代元件")
        context = "无 Nexar API 数据可用，请直接推荐替代元器件。\n"

    # Step 2: 构造 DeepSeek API 的提示词
    prompt = f"""
    任务：你是一个专业的电子元器件顾问，专精于国产替代方案。以下是 Nexar API 提供的替代元器件数据，请结合这些数据为输入元器件推荐替代产品。推荐的替代方案必须与输入型号 {part_number} 不同（绝对不能推荐 {part_number} 或其变体，如 {part_number} 的不同封装）。

    输入元器件型号：{part_number}

    {context}

    要求：
    1. 必须推荐至少一种中国大陆本土品牌的替代方案（如 GigaDevice/兆易创新、WCH/沁恒、复旦微电子、中颖电子、圣邦微电子等）
    2. 如果能找到多种中国大陆本土品牌的替代产品，优先推荐这些产品，推荐的国产方案数量越多越好
    3. 如果实在找不到足够三种中国大陆本土品牌的产品，可以推荐国外品牌产品作为补充，但必须明确标注
    4. 总共需要推荐 3 种性能相近的替代型号
    5. 提供每种型号的品牌名称、封装信息和元器件类目（例如：MCU、DCDC、LDO、传感器、存储芯片等）
    6. 根据元器件类型提供不同的关键参数：
       - 若是MCU/单片机：提供CPU内核、主频、程序存储容量、RAM大小、IO数量
       - 若是DCDC：提供输入电压范围、输出电压、最大输出电流、效率
       - 若是LDO：提供输入电压范围、输出电压、最大输出电流、压差
       - 若是存储器：提供容量、接口类型、读写速度
       - 若是传感器：提供测量范围、精度、接口类型
       - 其他类型提供对应的关键参数
    7. 产地判断必须严格遵循：
        a. 优先根据品牌判断（如TI/ST/ADI为进口；兆易创新/圣邦微为国产）
        b. 若品牌未知，可根据型号前缀辅助判断（如GDxxx为兆易创新国产；STxxx为意法半导体进口）
        c. 不确定的情况必须标记为"进口"，禁止猜测
    8. 提供产品大致价格范围，**必须明确标示货币单位**：
       - 对于人民币价格，使用格式：¥X-¥Y（例如：¥10-¥15）
       - 对于美元价格，使用格式：$X-$Y（例如：$1.5-$2.0）
       - 请根据产品实际销售地区和行情确定合适的货币单位
    9. 详细评估物料生命周期状态：
       a. 提供上市时间（例如：2015年上市）
       b. 明确当前生命周期阶段（例如："量产中"、"新产品"、"即将停产"、"已停产"、"不推荐用于新设计"等）
       c. 预估剩余生命周期（例如：预计2030年前持续供货）
       d. 标明是否有长期供货计划或EOL（生命周期终止）通知
    10. 重要：准确判断每个替代方案是否与原始元器件为"pin-to-pin替代"，必须满足以下所有条件才能标记为pin兼容:
        a. 如果是标准封装，封装与原元器件相同就满足条件a。或者非标准封装，物理尺寸公差在1mm以内，引脚排列和间距一致，可以在相同PCB焊盘位置安装
        b. 所有引脚的功能和编号与原元器件完全匹配
        c. 电气特性（电压/电流/时序等）与原元器件在合理范围内兼容
        d. 无需对PCB进行任何修改（包括布线、跳线等）就能替换使用
        e. 如果以上任何一点不符合，或者无法确定，则标记为"非Pin兼容"
    11. 提供产品官网链接（若无真实链接，可提供示例链接，如 https://www.example.com/datasheet）
    12. 推荐的型号不能与输入型号 {part_number} 相同
    13. 必须严格返回以下 JSON 格式的结果，不允许添加任何额外说明、Markdown 格式或代码块标记（即不要使用 ```json 或其他标记），直接返回裸 JSON：
    [
        {{"model": "SG1117-1.2", "brand": "SG Micro/圣邦微电子", "category": "LDO", "package": "DPAK", "parameters": "输入电压: 2.0-12V, 输出电压: 1.2V, 输出电流: 800mA, 压差: 1.1V", "type": "国产", "status": "量产中", "price": "¥2.5-¥3.5", "leadTime": "4-6周", "pinToPin": true, "compatibility": "完全兼容，可直接替换原型号", "datasheet": "https://www.sgmicro.com/datasheet", "releaseDate": "2015年", "lifecycle": "量产中，预计2030年前持续供货"}},
        {{"model": "GD32F103C8T6", "brand": "GigaDevice/兆易创新", "category": "MCU", "package": "LQFP48", "parameters": "CPU内核: ARM Cortex-M3, 主频: 72MHz, Flash: 64KB, RAM: 20KB, IO: 37", "type": "国产", "status": "量产中", "price": "¥12-¥15", "leadTime": "3-5周", "pinToPin": true, "compatibility": "引脚完全兼容，软件需少量修改", "datasheet": "https://www.gigadevice.com/datasheet", "releaseDate": "2013年", "lifecycle": "量产中，长期供货计划（10年+）"}},
        {{"model": "MP2307DN", "brand": "MPS/芯源系统", "category": "DCDC", "package": "SOIC-8", "parameters": "输入电压: 4.75-23V, 输出电压: 0.925-20V, 输出电流: 3A, 效率: 95%", "type": "进口", "status": "即将停产", "price": "$0.8-$1.2", "leadTime": "6-8周", "pinToPin": false, "compatibility": "需要重新设计PCB布局", "datasheet": "https://www.monolithicpower.com/datasheet", "releaseDate": "2010年", "lifecycle": "将于2025年停产，建议寻找替代方案"}}
    ]
    """

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精通中国电子元器件行业的专家，擅长为各种元器件寻找合适的替代方案，尤其专注于中国大陆本土生产的国产元器件。始终以有效的JSON格式回复，不添加任何额外说明。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            max_tokens=1000
        )
        raw_content = response.choices[0].message.content
        recommendations = extract_json_content(raw_content, "初次调用")

        # Step 3: 过滤掉与输入型号相同的推荐
        filtered_recommendations = []
        for rec in recommendations:
            if isinstance(rec, dict) and rec.get("model", "").lower() != part_number.lower():
                filtered_recommendations.append(rec)
        recommendations = filtered_recommendations

        # Step 4: 如果推荐数量不足，从 Nexar 数据中补充
        if len(recommendations) < 3 and nexar_alternatives:
            for alt in nexar_alternatives:
                if len(recommendations) >= 3:
                    break
                if alt["mpn"].lower() != part_number.lower():
                    recommendations.append({
                        "model": alt["mpn"],
                        "brand": alt.get("name", "未知品牌").split(' ')[0] if alt.get("name") else "未知品牌",
                        "category": "未知类别",
                        "package": "未知封装",
                        "parameters": "参数未知",
                        "type": "未知",
                        "datasheet": alt["octopartUrl"]
                    })

        # Step 5: 后处理，识别国产方案
        # 在Step 5和Step 7的后处理中，传入品牌信息
        for rec in recommendations:
            if isinstance(rec, dict):
                # 优先使用brand字段判断，而非仅依赖model
                brand = rec.get("brand", "").strip()
                model = rec.get("model", "").strip()
                # 关键修改：传入brand参数
                if rec.get("type") == "未知":
                    rec["type"] = "国产" if is_domestic_brand(model, brand) else "进口"

        # Step 6: 如果仍然不足 3 个，或缺少国产方案，重新调用 DeepSeek 强调国产优先
        need_second_query = len(recommendations) < 3 or not any(isinstance(rec, dict) and rec.get("type") == "国产" for rec in recommendations)
        
        if need_second_query:
            st.sidebar.warning("⚠️ 推荐结果不足或未包含国产方案，将重新调用 DeepSeek 推荐。")
            
            prompt_retry = f"""
            任务：为以下元器件推荐替代产品，推荐的替代方案必须与输入型号 {part_number} 不同（绝对不能推荐 {part_number} 或其变体，如 {part_number} 的不同封装）。
            输入元器件型号：{part_number}

            之前的推荐结果未包含国产方案或数量不足，请重新推荐，重点关注国产替代方案。

            要求：
            1. 必须推荐至少一种中国大陆本土品牌的替代方案（如 GigaDevice/兆易创新、WCH/沁恒、复旦微电子、中颖电子、圣邦微电子、3PEAK、Chipsea 等）
            2. 优先推荐国产芯片，推荐的国产方案数量越多越好
            3. 如果找不到足够的国产方案，可以补充进口方案，但必须明确标注
            4. 总共推荐 {3 - len(recommendations)} 种替代方案
            5. 提供每种型号的品牌名称、封装信息和元器件类目（例如：MCU、DCDC、LDO、传感器等）
            6. 根据元器件类型提供不同的关键参数：
               - 若是MCU/单片机：提供CPU内核、主频、程序存储容量、RAM大小、IO数量
               - 若是DCDC：提供输入电压范围、输出电压、最大输出电流、效率
               - 若是LDO：提供输入电压范围、输出电压、最大输出电流、压差
               - 若是存储器：提供容量、接口类型、读写速度
               - 若是传感器：提供测量范围、精度、接口类型
               - 其他类型提供对应的关键参数
            7. 在每个推荐方案中明确标注是"国产"还是"进口"产品
                a. 优先根据品牌判断（如TI/ST/ADI为进口；兆易创新/圣邦微为国产）
                b. 若品牌未知，可根据型号前缀辅助判断（如GDxxx为兆易创新国产；STxxx为意法半导体进口）
                c. 不确定的情况必须标记为"进口"，禁止猜测
            8. 提供产品官网链接（若无真实链接，可提供示例链接，如 https://www.example.com/datasheet）
            9. 推荐的型号不能与输入型号 {part_number} 相同
            10.重要：准确判断每个替代方案是否与原始元器件为"pin-to-pin替代"，必须满足以下所有条件才能标记为pin兼容:
                    a. 如果是标准封装，封装与原元器件相同就满足条件a。或者非标准封装，物理尺寸公差在1mm以内，引脚排列和间距一致，可以在相同PCB焊盘位置安装
                    b. 所有引脚的功能和编号与原元器件完全匹配
                    c. 电气特性（电压/电流/时序等）与原元器件在合理范围内兼容
                    d. 无需对PCB进行任何修改（包括布线、跳线等）就能替换使用
                    e. 如果以上任何一点不符合，或者无法确定，则标记为"非Pin兼容"
            11. 必须严格返回以下 JSON 格式的结果，不允许添加任何额外说明、Markdown 格式或代码块标记，直接返回裸 JSON：
            [
                {{"model": "型号1", "brand": "品牌1", "category": "类别1", "package": "封装1", "parameters": "参数1", "type": "国产/进口", "datasheet": "链接1"}},
                {{"model": "型号2", "brand": "品牌2", "category": "类别2", "package": "封装2", "parameters": "参数2", "type": "国产/进口", "datasheet": "链接2"}}
            ]
            11. 每个推荐项必须包含 "model"、"brand"、"category"、"package"、"parameters"、"type" 和 "datasheet" 七个字段
            12. 如果无法找到合适的替代方案，返回空的 JSON 数组：[]
            """
            
            second_query_success = False
            max_retries = 3
            additional_recommendations = []
            
            for attempt in range(max_retries):
                try:
                    response_retry = deepseek_client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": "你是一个精通中国电子元器件行业的专家，擅长为各种元器件寻找合适的替代方案，尤其专注于中国大陆本土生产的国产元器件。始终以有效的JSON格式回复，不添加任何额外说明。"},
                            {"role": "user", "content": prompt_retry}
                        ],
                        stream=False,
                        max_tokens=1000
                    )
                    raw_content_retry = response_retry.choices[0].message.content
                    
                    with st.spinner(f"正在解析第 {attempt + 1} 次二次查询结果..."):
                        additional_recommendations = extract_json_content(raw_content_retry, f"重新调用，第 {attempt + 1} 次")
                    
                    if additional_recommendations:
                        second_query_success = True
                        # 过滤掉与原型号相同的推荐
                        filtered_additional_recommendations = []
                        for rec in additional_recommendations:
                            if isinstance(rec, dict) and rec.get("model", "").lower() != part_number.lower():
                                filtered_additional_recommendations.append(rec)
                        additional_recommendations = filtered_additional_recommendations
                        
                        # 快速检查是否找到了国产方案
                        found_domestic = False
                        for rec in additional_recommendations:
                            if not isinstance(rec, dict):
                                continue
                            if rec.get("type") == "未知" and is_domestic_brand(rec.get("model", "")):
                                rec["type"] = "国产"
                            if rec.get("type") == "国产":
                                found_domestic = True
                        
                        # 记录二次查询结果
                        if found_domestic:
                            st.sidebar.success(f"✅ 二次查询成功！找到了 {len(additional_recommendations)} 个替代方案，其中包含国产方案。")
                        else:
                            st.sidebar.info(f"ℹ️ 二次查询返回了 {len(additional_recommendations)} 个替代方案，但未找到国产方案。")
                        
                        # 添加到推荐列表
                        for rec in additional_recommendations:
                            if len(recommendations) >= 3:
                                break
                            recommendations.append(rec)
                        break
                    else:
                        st.sidebar.warning(f"⚠️ 重新调用 DeepSeek API 第 {attempt + 1} 次未返回有效推荐。")
                        if attempt == max_retries - 1:
                            st.sidebar.error("❌ 重新调用 DeepSeek API 未能返回有效推荐，将使用默认替代方案。")
                except Exception as e:
                    st.sidebar.warning(f"⚠️ 重新调用 DeepSeek API 第 {attempt + 1} 次失败：{e}")
                    if attempt == max_retries - 1:
                        st.sidebar.error("❌ 重新调用 DeepSeek API 失败，将使用默认替代方案。")
            
            # 如果二次查询失败且结果仍然不足，从 Nexar 数据中补充
            if not second_query_success or len(recommendations) < 3:
                for alt in nexar_alternatives:
                    if len(recommendations) >= 3:
                        break
                    # 检查是否已经包含此型号
                    if alt["mpn"].lower() != part_number.lower() and not any(
                            isinstance(rec, dict) and rec.get("model", "").lower() == alt["mpn"].lower() 
                            for rec in recommendations):
                        new_rec = {
                            "model": alt["mpn"],
                            "brand": alt.get("name", "未知品牌").split(' ')[0] if alt.get("name") else "未知品牌",
                            "category": "未知类别",
                            "package": "未知封装",
                            "parameters": "参数未知",
                            "type": "未知",
                            "datasheet": alt["octopartUrl"]
                        }
                        # 识别国产方案
                        if is_domestic_brand(new_rec["model"]):
                            new_rec["type"] = "国产"
                        recommendations.append(new_rec)
            
            # 在二次查询完成后再做一次最终统计
            if need_second_query:
                domestic_count = sum(1 for rec in recommendations if isinstance(rec, dict) and rec.get("type") == "国产")
                import_count = sum(1 for rec in recommendations if isinstance(rec, dict) and (rec.get("type") == "进口" or rec.get("type") == "未知"))
                st.sidebar.info(f"🔍 查找完成，共找到 {len(recommendations)} 个替代方案，其中国产方案 {domestic_count} 个，进口/未知方案 {import_count} 个。")

        # Step 7: 再次后处理，识别国产方案
        # 在Step 5和Step 7的后处理中，传入品牌信息
        for rec in recommendations:
            if isinstance(rec, dict):
                # 优先使用brand字段判断，而非仅依赖model
                brand = rec.get("brand", "").strip()
                model = rec.get("model", "").strip()
                # 关键修改：传入brand参数
                if rec.get("type") == "未知":
                    rec["type"] = "国产" if is_domestic_brand(model, brand) else "进口"

        # 确保recommendations是可切片类型并安全执行切片
        try:
            # 确保输出结果是列表类型
            if not isinstance(recommendations, list):
                st.sidebar.warning(f"推荐结果不是列表类型: {type(recommendations)}")
                if recommendations:
                    if isinstance(recommendations, dict):
                        recommendations = [recommendations]
                    else:
                        try:
                            recommendations = list(recommendations)
                        except:
                            st.sidebar.error("无法将推荐结果转换为列表")
                            return []
                else:
                    return []
                    
            # 安全地执行切片
            return recommendations[:3] if recommendations else []
        except Exception as slice_error:
            st.sidebar.error(f"切片操作失败: {slice_error}")
            # 处理非常规情况，确保返回一个列表
            if recommendations:
                if isinstance(recommendations, (list, tuple)):
                    return list(recommendations)[:3] if len(recommendations) >= 3 else list(recommendations)
                else:
                    return [recommendations]
            else:
                return []
    except Exception as e:
        st.sidebar.error(f"DeepSeek API 调用失败：{e}")
        return []

def process_bom_file(uploaded_file):
    """处理上传的BOM文件并返回元器件列表"""
    # 再次检查依赖，确保已安装
    check_and_install_dependencies()
    
    # 创建临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_filepath = tmp_file.name
    
    try:
        # 根据文件扩展名读取文件
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext == '.csv':
            df = pd.read_csv(tmp_filepath)
        elif file_ext == '.xls':
            # 专门处理旧版Excel文件
            try:
                df = pd.read_excel(tmp_filepath, engine='xlrd')
            except Exception as e:
                st.error(f"无法使用xlrd读取.xls文件: {e}")
                st.warning("尝试使用openpyxl引擎...")
                df = pd.read_excel(tmp_filepath, engine='openpyxl')
        elif file_ext == '.xlsx':
            # 处理新版Excel文件
            df = pd.read_excel(tmp_filepath, engine='openpyxl')
        else:
            raise ValueError(f"不支持的文件格式: {file_ext}")
        
        # 尝试识别关键列：型号列、名称列、描述列
        # 可能的列名
        mpn_columns = []  # 型号列
        name_columns = []  # 名称列
        desc_columns = []  # 描述列
        
        mpn_keywords = ['mpn', 'part', 'part_number', 'part number', 'partnumber', '型号', '规格型号', '器件型号']
        name_keywords = ['name', 'component', 'component_name', '名称', '元件名称', '器件名称']
        desc_keywords = ['description', 'desc', '描述', '规格', '说明', '特性']
        
        # 遍历所有列，尝试匹配关键词
        for col in df.columns:
            col_lower = str(col).lower()
            # 检查是否为型号列
            if any(keyword in col_lower for keyword in mpn_keywords):
                mpn_columns.append(col)
            # 检查是否为名称列
            if any(keyword in col_lower for keyword in name_keywords):
                name_columns.append(col)
            # 检查是否为描述列
            if any(keyword in col_lower for keyword in desc_keywords):
                desc_columns.append(col)
        
        # 如果没有找到明确的列，尝试从所有列中查找最有可能的型号列
        if not mpn_columns:
            for col in df.columns:
                sample_values = df[col].dropna().astype(str).tolist()[:5]
                # 检查值的特征是否像型号（通常含有数字和字母的组合）
                if sample_values and all(bool(re.search(r'[A-Za-z].*\d|\d.*[A-Za-z]', val)) for val in sample_values):
                    mpn_columns.append(col)
        
        # 构建元器件列表，包含型号、名称和描述信息
        component_list = []
        
        # 确定最终使用的列
        mpn_col = mpn_columns[0] if mpn_columns else None
        name_col = name_columns[0] if name_columns else None
        desc_col = desc_columns[0] if desc_columns else None
        
        # 如果没有找到任何列，使用前几列
        if not mpn_col and len(df.columns) >= 1:
            mpn_col = df.columns[0]
        if not name_col and len(df.columns) >= 2:
            name_col = df.columns[1]
        if not desc_col and len(df.columns) >= 3:
            desc_col = df.columns[2]
        
        # 从DataFrame中提取元器件列表
        for _, row in df.iterrows():
            component = {}
            
            # 提取型号信息
            if mpn_col and pd.notna(row.get(mpn_col)):
                component['mpn'] = str(row.get(mpn_col)).strip()
            else:
                continue  # 如果没有型号，则跳过该行
                
            # 提取名称信息
            if name_col and pd.notna(row.get(name_col)):
                component['name'] = str(row.get(name_col)).strip()
            else:
                component['name'] = ''
                
            # 提取描述信息
            if desc_col and pd.notna(row.get(desc_col)):
                component['description'] = str(row.get(desc_col)).strip()
            else:
                component['description'] = ''
                
            # 仅添加有型号的元器件
            if component.get('mpn'):
                component_list.append(component)
        
        # 去重，通常BOM表中会有重复的元器件
        unique_components = []
        seen_mpns = set()
        for comp in component_list:
            mpn = comp['mpn']
            if mpn not in seen_mpns:
                seen_mpns.add(mpn)
                unique_components.append(comp)
        
        # 返回元器件列表和识别的列名
        columns_info = {
            'mpn_column': mpn_col,
            'name_column': name_col,
            'description_column': desc_col
        }
        
        return unique_components, columns_info
            
    except Exception as e:
        st.error(f"处理BOM文件时出错: {e}")
        if "Missing optional dependency 'xlrd'" in str(e):
            st.info("正在尝试安装xlrd依赖...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "xlrd>=2.0.1"])
                st.success("xlrd安装成功，请重新上传文件")
            except Exception as install_error:
                st.error(f"自动安装xlrd失败: {install_error}")
                st.info("请手动运行: pip install xlrd>=2.0.1")
        if "Missing optional dependency 'openpyxl'" in str(e):
            st.info("正在尝试安装openpyxl依赖...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                st.success("openpyxl安装成功，请重新上传文件")
            except Exception as install_error:
                st.error(f"自动安装openpyxl失败: {install_error}")
                st.info("请手动运行: pip install openpyxl")
        return [], {}
    finally:
        # 删除临时文件
        if os.path.exists(tmp_filepath):
            os.unlink(tmp_filepath)

def batch_get_alternative_parts(component_list, progress_callback=None):
    """批量评估元器件停产风险（仅判断风险，不查询替代方案）
    
    Args:
        component_list: 包含元器件信息的列表
        progress_callback: 进度回调函数
        
    Returns:
        批量风险评估结果字典
    """
    # 初始化结果字典
    results = {}
    total = len(component_list)
    error_count = 0
    success_count = 0

    # 风险等级定义（新划分标准）
    RISK_LEVELS = {
        "HIGH": "红色",    # 已停产或2年以内停产（高风险）
        "LOW": "黄色",     # 2-4年停产（低风险）
        "SAFE": "绿色",    # 4年以上停产（无风险）
        "UNKNOWN": "未知"  # 未检测出停产时间（灰色）
    }

    def assess_risk_with_deepseek(mpn, name, description):
        """调用DeepSeek评估元器件停产风险，按新标准划分等级"""
        from datetime import datetime, date
        
        # 构建提示词（要求返回JSON格式）
        prompt = f"""
        按以下规则评估元器件"{mpn}（{name}）"的停产风险：
        优先判断：允许评估元器件的停产风险等级
        若仍然在量产，但是预计会在几年内逐步淘汰，封装已被TI列为"Legacy Packaging"（传统封装），则：status=未停产, eol_year=“当前年份”+“4年”
        若仍然在量产，且出货量充足，并且暂时无停产计划，则：status=未停产, eol_year=无计划
        若有较大风险，已经有明确的停产计划，或者即将有停产安排，则：status=未停产, eol_year=当前年份
        1. 若已停产：status=已停产
        2. 若未停产但有停产计划：status=未停产, eol_year=具体年份
        3. 若正常生产无停产计划：status=未停产, eol_year=无计划
        
        返回严格的JSON格式（禁止包含其他文本）：
        {{
            "status": "已停产|未停产",
            "eol_year": "2025|无计划|未知",
            "description": "详细状态说明"
        }}
        """
        
        try:
            # 调用DeepSeek
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是电子元器件领域专家，擅长评估产品生命周期。请严格按JSON格式返回，不添加任何额外内容。"},
                    {"role": "user", "content": prompt}
                ],
                stream=False,
                max_tokens=200
            )
            response_text = response.choices[0].message.content.strip()
            
            # 调试：记录原始响应（仅开发阶段使用）
            if st.session_state.get("debug_mode", False):
                st.write(f"原始响应（{mpn}）：", response_text)
            
            # 增强版JSON解析逻辑
            risk_data = None
            try:
                # 尝试直接解析
                risk_data = json.loads(response_text)
                
            except json.JSONDecodeError as e:
                # 尝试提取JSON部分（处理可能包含额外文本的情况）
                try:
                    # 提取第一个大括号开始到最后一个大括号结束的部分
                    start_idx = response_text.find("{")
                    end_idx = response_text.rfind("}")
                    
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = response_text[start_idx:end_idx+1]
                        risk_data = json.loads(json_str)
                    else:
                        # 尝试更宽松的解析（移除前缀文本）
                        lines = response_text.split('\n')
                        json_lines = []
                        in_json = False
                        
                        for line in lines:
                            line = line.strip()
                            if line.startswith("{"):
                                in_json = True
                            if in_json:
                                json_lines.append(line)
                            if line.endswith("}"):
                                break
                        
                        if json_lines:
                            json_str = '\n'.join(json_lines)
                            risk_data = json.loads(json_str)
                
                except Exception as e2:
                    # 解析失败，记录错误信息
                    if st.session_state.get("debug_mode", False):
                        st.write(f"JSON解析失败（{mpn}）：", str(e2))
                    risk_data = None
            
            # 验证数据结构
            if not risk_data or not isinstance(risk_data, dict):
                status, eol_year, status_desc = "未知", "未知", "响应格式非JSON"
            else:
                status = risk_data.get("status", "未知")
                eol_year = risk_data.get("eol_year", "未知")
                status_desc = risk_data.get("description", "未知")
                
                # 验证状态值
                if status not in ["已停产", "未停产"]:
                    status = "未知"

            # 计算风险等级（核心逻辑）
            today = date.today()
            warning_level = "UNKNOWN"  # 默认未知
            
            # 情况1：已停产
            if status == "已停产":
                warning_level = "HIGH"
                eol_year = "已停产"
            
            # 情况2：有明确停产年份
            elif eol_year.isdigit():
                eol_date = datetime.strptime(f"{eol_year}-12-31", "%Y-%m-%d").date()
                months_diff = (eol_date - today).days // 30  # 转换为月
                
                if months_diff <= 12:  # 1年内
                    warning_level = "HIGH"
                elif 12 < months_diff <= 60:  # 1-5年
                    warning_level = "LOW"
                else:  # 5年以上
                    warning_level = "SAFE"
                    
            # 情况3：无停产计划
            elif eol_year == "无计划":
                warning_level = "SAFE"
                eol_year = "无停产计划"
            
            
            # 转换为中文等级
            chinese_level = RISK_LEVELS.get(warning_level, "未知")
            
            return {
                "warning_level": chinese_level,
                "eol_date": eol_year,
                "status": status_desc,
                "raw_status": status,
                "debug_info": {  # 仅用于调试，可在生产环境移除
                    "original_response": response_text if st.session_state.get("debug_mode", False) else None
                }
            }
            
        except Exception as e:
            st.error(f"DeepSeek风险评估失败（{mpn}）：{str(e)}")
            return {
                "warning_level": "未知",
                "eol_date": "未知",
                "status": f"评估失败：{str(e)}",
                "raw_status": "错误"
            }

    # 仅进行风险评估（无替代方案查询）
    st.sidebar.info("正在评估所有元器件的停产风险...")
    eol_warnings = []
    
    for idx, component in enumerate(component_list):
        mpn = component.get('mpn', '')
        name = component.get('name', '')
        description = component.get('description', '')
        
        # 更新进度
        progress = (idx + 1) / total
        if progress_callback:
            progress_callback(progress, f"评估第 {idx+1}/{total} 个元器件: {mpn}")
        
        try:
            # 获取风险信息
            risk_info = assess_risk_with_deepseek(mpn, name, description)
            
            # 收集预警信息
            risk_desc_map = {
                "红色": "高风险（已停产或1年以内停产）",
                "黄色": "低风险（1-5年停产）",
                "绿色": "无风险（5年以上停产）",
                "未知": "未知风险（未检测出停产信息）"
            }
            risk_description = risk_desc_map.get(risk_info["warning_level"], "未知风险")
            
            eol_warnings.append({
                "mpn": mpn,
                "name": name,
                "eol_date": risk_info["eol_date"],
                "warning_level": risk_info["warning_level"],
                "status": risk_info["status"],
                "risk_description": risk_description
            })
            
            # 保存结果（不包含替代方案）
            results[mpn] = {
                'name': name,
                'description': description,
                'eol_date': risk_info["eol_date"],
                'warning_level': risk_info["warning_level"],
                'status': risk_info["status"],
                'risk_description': risk_description
            }
            success_count += 1
            
        except Exception as e:
            error_count += 1
            st.error(f"处理元器件 {mpn} 时出错: {e}")
            results[mpn] = {
                'name': name,
                'description': description,
                'eol_date': "未知",
                'warning_level': "未知",
                'status': f"处理错误: {str(e)}",
                'risk_description': "处理异常"
            }
    
    # 保存风险预警信息
    results["__eol_warnings__"] = eol_warnings
    with st.sidebar.expander("调试：风险评估结果", expanded=False):
        st.write(f"共评估 {len(eol_warnings)} 个元器件，成功 {success_count} 个，失败 {error_count} 个")
    
    st.sidebar.success(f"批量评估完成：共 {total} 个元器件")
    return results

def get_alternatives_direct(mpn, name="", description=""):
    """直接使用DeepSeek API查询元器件替代方案，不通过Nexar API"""
    # 构建更全面的查询信息
    query_context = f"元器件型号: {mpn}" + \
                   (f"\n元器件名称: {name}" if name else "") + \
                   (f"\n元器件描述: {description}" if description else "")
    
    # 构造DeepSeek API提示
    prompt = f"""
    任务：你是一个专业的电子元器件顾问，专精于国产替代方案。请为以下元器件推荐详细的替代产品。
    
    输入元器件信息：
    {query_context}
    
    要求：
    1. 必须推荐至少一种中国大陆本土品牌的替代方案（如 GigaDevice/兆易创新、WCH/沁恒、复旦微电子、中颖电子、圣邦微电子等）
    2. 如果能找到多种中国大陆本土品牌的替代产品，优先推荐这些产品，推荐的国产方案数量越多越好
    3. 如果实在找不到足够三种中国大陆本土品牌的产品，可以推荐国外品牌产品作为补充，但必须明确标注
    4. 总共需要推荐 3 种性能相近的替代型号
    5. 提供每种型号的品牌名称、封装信息和元器件类目（例如：MCU、DCDC、LDO、传感器等）
    6. 根据元器件类型提供不同的关键参数：
       - 若是MCU/单片机：提供CPU内核、主频、程序存储容量、RAM大小、IO数量
       - 若是DCDC：提供输入电压范围、输出电压、最大输出电流、效率
       - 若是LDO：提供输入电压范围、输出电压、最大输出电流、压差
       - 若是存储器：提供容量、接口类型、读写速度
       - 若是传感器：提供测量范围、精度、接口类型
       - 其他类型提供对应的关键参数
    7. 在每个推荐方案中明确标注是"国产"还是"进口"产品
        a. 优先根据品牌判断（如TI/ST/ADI为进口；兆易创新/圣邦微为国产）
        b. 若品牌未知，可根据型号前缀辅助判断（如GDxxx为兆易创新国产；STxxx为意法半导体进口）
        c. 不确定的情况必须标记为"进口"，禁止猜测
    8. 提供产品官网链接（若无真实链接，可提供示例链接）
    9. 推荐的型号不能与输入型号 {mpn} 相同
    10. 必须提供价格估算，价格必须包含货币符号：
       - 对于人民币价格，必须使用"¥"符号（例如：¥10-¥15）
       - 对于美元价格，必须使用"$"符号（例如：$1.5-$2.0）
       - 请估算常见采购渠道的批量价格范围
    11. 必须严格返回以下 JSON 格式的结果，不允许添加额外说明或Markdown格式：
    [
        {{"model": "详细型号1", "brand": "品牌名称1", "category": "类别1", "package": "封装1", "parameters": "详细参数1", "type": "国产/进口", "datasheet": "链接1", "price": "¥10-¥15"}},
        {{"model": "详细型号2", "brand": "品牌名称2", "category": "类别2", "package": "封装2", "parameters": "详细参数2", "type": "国产/进口", "datasheet": "链接2", "price": "$1.5-$2.0"}},
        {{"model": "详细型号3", "brand": "品牌名称3", "category": "类别3", "package": "封装3", "parameters": "详细参数3", "type": "国产/进口", "datasheet": "链接3", "price": "¥8-¥12"}}
    ]
    12. 每个推荐项必须包含 "model"、"brand"、"category"、"package"、"parameters"、"type"、"datasheet"和"price"八个字段
    13. 如果无法找到合适的替代方案，返回空的 JSON 数组：[]
    14.重要：准确判断每个替代方案是否与原始元器件为"pin-to-pin替代"，必须满足以下所有条件才能标记为pin兼容:
                    a. 如果是标准封装，封装与原元器件相同就满足条件a。或者非标准封装，物理尺寸公差在1mm以内，引脚排列和间距一致，可以在相同PCB焊盘位置安装
                    b. 所有引脚的功能和编号与原元器件完全匹配
                    c. 电气特性（电压/电流/时序等）与原元器件在合理范围内兼容
                    d. 无需对PCB进行任何修改（包括布线、跳线等）就能替换使用
                    e. 如果以上任何一点不符合，或者无法确定，则标记为"非Pin兼容"
    """
    
    try:
        # 调用DeepSeek API
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精通中国电子元器件行业的专家，擅长为各种元器件寻找合适的替代方案，尤其专注于中国大陆本土生产的国产元器件。始终以有效的JSON格式回复，不添加任何额外说明。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            max_tokens=1200
        )
        
        raw_content = response.choices[0].message.content
        
        # 记录API返回的原始内容以便调试
        with st.sidebar.expander(f"调试信息 - API原始响应 ({mpn})", expanded=False):
            st.write(f"**原始响应内容:**")
            st.code(raw_content, language="text")
        
        # 使用简化版的extract_json_content处理API返回结果
        recommendations = extract_json_content(raw_content, "批量查询")
        
        # 确保所有必要字段都存在
        validated_recommendations = []
        for rec in recommendations:
            if isinstance(rec, dict):
                # 确保所有必要字段存在
                rec["model"] = rec.get("model", "未知型号")
                rec["brand"] = rec.get("brand", "未知品牌")
                rec["category"] = rec.get("category", "未知类别")
                rec["package"] = rec.get("package", "未知封装")
                rec["parameters"] = rec.get("parameters", "参数未知")
                rec["type"] = rec.get("type", "未知")
                # 确保datasheet字段存在 - 这是前端显示必需的
                if "datasheet" not in rec or not rec["datasheet"]:
                    rec["datasheet"] = "https://www.example.com/datasheet"
                # 添加其他可能需要的字段
                rec["status"] = rec.get("status", "未知")
                rec["leadTime"] = rec.get("leadTime", "未知")
                rec["pinToPin"] = rec.get("pinToPin", False)
                rec["compatibility"] = rec.get("compatibility", "兼容性未知")
                rec["price"] = rec.get("price", "未知")
                
                # 过滤掉与输入型号相同的推荐
                if rec["model"].lower() != mpn.lower():
                    # 后处理，识别国产方案
                    if rec["type"] == "未知" and is_domestic_brand(rec["model"]):
                        rec["type"] = "国产"
                    validated_recommendations.append(rec)
            
        # 如果没有找到任何有效推荐或推荐数量不足
        if len(validated_recommendations) < 3:
            # 创建测试数据以确保至少有一些结果
            if st.session_state.get("use_dummy_data", False) or len(validated_recommendations) == 0:
                missing_count = 3 - len(validated_recommendations)
                for i in range(missing_count):
                    validated_recommendations.append({
                        "model": f"{mpn}_替代{i+1}",
                        "brand": "测试品牌",
                        "category": "测试类别",
                        "package": "测试封装",
                        "parameters": "测试参数数据",
                        "type": "国产" if i % 2 == 0 else "进口",
                        "status": "量产中",
                        "leadTime": "4-6周",
                        "price": "¥8-¥15" if i % 2 == 0 else "$1.5-$3.0",
                        "pinToPin": i % 2 == 0,
                        "compatibility": "完全兼容" if i % 2 == 0 else "需要修改PCB",
                        "datasheet": "https://www.example.com/datasheet"
                    })
        
        # 确保不返回超过3个结果
        return validated_recommendations[:3]
        
    except Exception as e:
        st.sidebar.error(f"DeepSeek API 查询失败: {e}")
        import traceback
        st.sidebar.error(f"错误详情: {traceback.format_exc()}")
        
        # 返回测试数据以保证前端显示正常
        if st.session_state.get("use_dummy_data", False):
            st.sidebar.info(f"使用测试数据继续处理 {mpn}")
            return [
                {
                    "model": f"{mpn}_ALT1",
                    "brand": "GigaDevice/兆易创新",
                    "category": "未知类别",
                    "package": "未知封装",
                    "parameters": "参数未知",
                    "type": "国产",
                    "status": "量产中",
                    "leadTime": "4-6周",
                    "price": "¥8-¥15",
                    "pinToPin": True,
                    "compatibility": "完全兼容",
                    "datasheet": "https://www.example.com/datasheet"
                },
                {
                    "model": f"{mpn}_ALT2",
                    "brand": "品牌未知",
                    "category": "未知类别",
                    "package": "未知封装",
                    "parameters": "参数未知",
                    "type": "进口",
                    "status": "量产中",
                    "leadTime": "6-8周",
                    "price": "$1.5-$3.0",
                    "pinToPin": False,
                    "compatibility": "需要修改PCB",
                    "datasheet": "https://www.example.com/datasheet"
                }
            ]
        return []

def chat_with_expert(user_input, history=None):
    """
    使用DeepSeek API实现与电子元器件专家的对话
    
    参数:
        user_input (str): 用户的输入/问题
        history (list): 对话历史记录，格式为[{"role": "user/assistant", "content": "消息内容"}, ...]
    
    返回:
        str 或 Generator: 根据stream参数，返回完整回复或流式回复
    """
    if history is None:
        history = []
    
    # 构建完整的消息历史
    messages = [
        {"role": "system", "content": """  
您是一名电子元器件选型专家，请严格遵循以下流程：

**处理流程**
一. 参数解析阶段：
   - 识别【硬性参数】（字体加粗）：电压/电流/频率/温度/封装
   - 提取【应用场景】（字体加粗）：工业/消费/汽车/医疗
   - 确认【限制条件】（字体加粗）：成本/供货周期/认证/国产化需求
   - 强制检查：必须询问"是否需要包含国产方案？"

二. 方案生成阶段：
   a. 获取候选型号（必须包含：圣邦微/长电/士兰微等国产方案）
   b. 分级推荐：
      1) 旗舰方案（⭐⭐⭐⭐⭐）：国际大厂+参数完美匹配
      2) 优选方案（⭐⭐⭐⭐）：国产替代+参数匹配≥95% 
      3) 备选方案（⭐⭐⭐）：参数临界匹配但成本优势>30%
   c. 推荐策略：
       * 至少提供5个有效选项（其中国产≥2个）
       * 标注"国产优选"标签（需满足：量产历史≥2年）

三. 输出规范：
   - 严格使用Markdown格式
   - 必须包含：
     * 参数对比表格，一定要标记出元器件地价格（标注关键性能指标）
     * TOP5推荐表（含价格梯度/供货指数）
     * 国产方案竞争力分析
     * 生命周期预警（停产风险型号标红）

    输出必须严格遵循：
    1. 标题使用##（二级标题）、###（三级标题），禁止使用#（一级标题）
    2. 正文使用纯文本，换行用<br>或空行分隔
    3. 表格使用标准Markdown格式（|表头|...|）
    4. 禁止使用HTML标签或其他非Markdown语法
    
**对话规范**
- 技术参数必须标注来源（如"参照圣邦微SGM2042手册第8页"）
- 出现以下情况立即警示：
  1) 单一供应商依赖风险（某型号采购占比>60%）
  2) 国产方案参数达标但未被选择
  3) 成本敏感场景选用超规格器件
- 优先推荐已验证的"芯片组"方案（如MCU+配套电源芯片）
"""}
    ]
    
    # 添加历史对话
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # 添加当前用户问题
    messages.append({"role": "user", "content": user_input})
    
    try:
        # 调用DeepSeek API获取回复 - 使用流式响应
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=True,
            max_tokens=2000
        )
        return response
    
    except Exception as e:
        st.error(f"调用DeepSeek API失败: {e}")
        import traceback
        st.error(f"错误详情: {traceback.format_exc()}")
        # 返回一个只包含错误信息的生成器，以保持接口一致性
        def error_generator():
            yield f"很抱歉，我暂时无法回答你的问题。错误信息: {str(e)}"
        return error_generator()

# 格式化响应
def format_response(text):
    replacements = {
        "TOP5推荐表": "## 📊 推荐方案（⭐⭐⭐⭐⭐为旗舰方案）",
        "国产方案": "## 🇨🇳 国产竞争力分析",
        "生命周期预警": "## ⚠️ 供应链风险提示"
    }
    for k,v in replacements.items():
        text = text.replace(k, v)
    return text

def identify_component(mpn):
    """识别元器件信息，新增停产时间提取"""
    import re
    from datetime import datetime, date  # 新增：用于日期处理
    if not mpn or len(mpn) < 3 or not re.search(r'[A-Za-z0-9]', mpn):
        return {}

    variables = {"q": mpn, "limit": 1}
    try:
        data = nexar_client.get_query(QUERY_ALTERNATIVE_PARTS, variables)
        
        if not data:
            st.sidebar.info(f"Nexar未找到{mpn}，尝试DeepSeek检索")
            return call_deepseek_for_component(mpn)
        
        sup_search = data.get("supSearchMpn", {})
        results = sup_search.get("results", [])
        
        if not results:
            st.sidebar.info(f"Nexar结果为空，尝试DeepSeek检索{mpn}")
            return call_deepseek_for_component(mpn)
        
        part = results[0].get("part", {})
        required_fields = ["mpn", "manufacturer", "specs"]
        if not all(part.get(field) for field in required_fields):
            st.sidebar.info(f"Nexar数据不完整，尝试DeepSeek检索{mpn}")
            return call_deepseek_for_component(mpn)

        # 基础信息（新增eol_date和warning_level字段）
        component_info = {
            "mpn": part.get("mpn", "未知型号"),
            "manufacturer": part.get("manufacturer", {}).get("name", "未知制造商"),
            "parameters": {},
            "price": "未知",
            "category": "未知",
            "package": "未知",
            "pin_compatible": "未知",
            "status": "未知",
            "leadTime": "未知",
            "eol_date": None,  # 新增：停产日期（datetime对象）
            "warning_level": "未知"  # 新增：预警等级（红色/黄色/绿色/未知）
        }

        # 提取参数（重点提取停产时间）
        specs = part.get("specs", [])
        eol_date_str = None  # 存储原始停产日期字符串
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            attr = spec.get("attribute", {})
            if not isinstance(attr, dict):
                continue
            name = attr.get("name", "").lower()
            value = spec.get("value", "").strip()
            component_info["parameters"][name] = value

            # 提取封装和类别（原有逻辑）
            if name == "category" and component_info["category"] == "未知":
                component_info["category"] = value
            elif name == "package" and component_info["package"] == "未知":
                component_info["package"] = value

            # 新增：提取停产日期（匹配关键词）
            if "end of life date" in name or "eol date" in name or "discontinue date" in name:
                eol_date_str = value
            elif "life cycle" in name and ("discontinue" in value.lower() or "eol" in value.lower()):
                # 若没有明确日期，从生命周期描述中提取年份（如"2025年停产"）
                year_match = re.search(r'\b20\d{2}\b', value)
                if year_match:
                    eol_date_str = f"{year_match.group()}-12-31"  # 默认为年底

        # 解析停产日期并计算预警等级
        if eol_date_str:
            try:
                # 尝试多种日期格式解析
                date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y年%m月%d日", "%Y"]
                eol_date = None
                for fmt in date_formats:
                    try:
                        eol_date = datetime.strptime(eol_date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if eol_date:
                    component_info["eol_date"] = eol_date
                    today = date.today()
                    days_diff = (eol_date - today).days

                    # 计算预警等级（新增核心逻辑）
                    if days_diff <= 365:  # 1年内
                        component_info["warning_level"] = "红色"
                    elif 365 < days_diff <= 730:  # 1-2年
                        component_info["warning_level"] = "黄色"
                    elif days_diff > 730:  # 2年以上
                        component_info["warning_level"] = "绿色"
                    else:  # 已过期（停产日期在今天之前）
                        component_info["warning_level"] = "红色"  # 已停产也标红
            except Exception as e:
                st.sidebar.warning(f"解析{mpn}停产日期失败: {e}")
                component_info["warning_level"] = "未知"
        else:
            # 若未找到明确停产日期，根据状态推断
            if component_info["status"] == "已停产":
                component_info["warning_level"] = "红色"
            else:
                component_info["warning_level"] = "未知"

        # 6. 提取价格（保持原有逻辑）
        price_info = part.get("medianPrice1000", {})
        # 增加 price_info 校验
        if not isinstance(price_info, dict):
            price_info = {}
        price_val = price_info.get("price")
        currency = price_info.get("currency", "USD")
        if price_val:
            component_info["price"] = format_price(price_val, currency)


        # 8. 生命周期、交期（保持原有逻辑）
        life_cycle = part.get("lifeCycle", "未知")
        obsolete = part.get("obsolete", False)
        lead_days = part.get("estimatedFactoryLeadDays")

        if obsolete:
            component_info["status"] = "已停产"
        elif life_cycle:
            life_cycle_upper = life_cycle.upper()
            if "OBSOLETE" in life_cycle_upper or "END OF LIFE" in life_cycle_upper:
                component_info["status"] = "已停产"
            elif "ACTIVE" in life_cycle_upper or "PRODUCTION" in life_cycle_upper:
                component_info["status"] = "量产中"
            elif "NEW" in life_cycle_upper or "INTRO" in life_cycle_upper:
                component_info["status"] = "新产品"
            elif "NOT RECOMMENDED" in life_cycle_upper:
                component_info["status"] = "不推荐使用"
            elif "PHASE OUT" in life_cycle_upper or "DISCONTINUE" in life_cycle_upper:
                component_info["status"] = "即将停产"  # 新增：补充"即将停产"状态
            else:
                component_info["status"] = life_cycle
        else:
                component_info["status"] = "未知"  # 确保默认值

        # 修复：根据正确的status推断预警等级（原代码中此处依赖未更新的status）
        if not eol_date_str:  # 若未找到明确日期，根据状态推断
            if component_info["status"] == "已停产":
                component_info["warning_level"] = "红色"
            elif component_info["status"] == "即将停产":
                component_info["warning_level"] = "黄色"  # 即将停产设为黄色
            else:
                component_info["warning_level"] = "未知"

        if lead_days:
            component_info["leadTime"] = f"{lead_days} 天"

        return component_info
    
    except Exception as e:
        st.error(f"Nexar API 查询失败: {e}，尝试使用DeepSeek检索")
        import traceback
        with st.sidebar.expander("Nexar API错误详情", expanded=False):
            st.code(traceback.format_exc())
        return call_deepseek_for_component(mpn)  # 调用DeepSeek检索

def call_deepseek_for_component(mpn):
    """调用DeepSeek API获取元器件信息"""
    try:
        # 构造DeepSeek提示词
        prompt = f"""
        任务：你是一个专业的电子元器件专家，请分析以下元器件型号并提取关键信息：
        
        元器件型号：{mpn}
        
        要求：
        1. 提取以下关键信息（如果无法获取则填"未知"）：
           - 制造商
           - 元器件类别（如MCU、DCDC、LDO等）
           - 封装类型
           - 主要技术参数（格式为JSON对象，例如：{{"电压": "3.3V", "电流": "1A"}}）
           - 价格范围（格式示例："¥10-¥15" 或 "$1.5-$2.0"）
           - 生命周期状态（量产中、已停产等）
           - 供货周期
           - 是否为PIN兼容器件（是/否/未知）
           
        2. 输出格式要求：
        {{
            "mpn": "{mpn}",
            "manufacturer": "制造商名称",
            "category": "元器件类别",
            "package": "封装类型",
            "parameters": {{"参数名称": "参数值", ...}},
            "price": "价格范围，包含货币符号",
            "status": "生命周期状态",
            "leadTime": "供货周期",
            "pin_compatible": "是/否/未知"
        }}
        
        3. 注意事项：
        - 严格按照JSON格式输出，不添加任何额外内容
        - 价格范围必须包含货币符号（¥或$）
        """
        
        # 调用DeepSeek API
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精通电子元器件的专家，能够根据型号准确提取元器件关键信息。始终以有效的JSON格式回复，不添加任何额外说明。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            max_tokens=500
        )
        
        raw_content = response.choices[0].message.content
        
        # 记录API返回的原始内容以便调试
        with st.sidebar.expander(f"调试信息 - DeepSeek响应 ({mpn})", expanded=False):
            st.write(f"**DeepSeek原始响应:**")
            st.code(raw_content, language="text")
        
        # 解析DeepSeek响应
        component_info = parse_deepseek_response(raw_content, mpn)
        return component_info
    
    except Exception as e:
        st.error(f"DeepSeek API 调用失败: {e}")
        import traceback
        with st.sidebar.expander("DeepSeek API错误详情", expanded=False):
            st.code(traceback.format_exc())
        return {
            "mpn": mpn,
            "manufacturer": "未知",
            "category": "未知",
            "package": "未知",
            "parameters": {},
            "price": "未知",
            "status": "未知",
            "leadTime": "未知",
            "pin_compatible": "未知"
        }

def parse_deepseek_response(response_content, mpn):
    """解析DeepSeek API返回的元器件信息"""
    import json
    import re
    
    # 尝试直接解析JSON
    try:
        data = json.loads(response_content)
        # 确保返回数据包含必要字段
        component_info = {
            "mpn": data.get("mpn", mpn),
            "manufacturer": data.get("manufacturer", "未知"),
            "category": data.get("category", "未知"),
            "package": data.get("package", "未知"),
            "parameters": data.get("parameters", {}),  # 直接使用JSON对象
            "price": format_price_string(data.get("price", "未知")),
            "status": data.get("status", "未知"),
            "leadTime": data.get("leadTime", "未知"),
            "pin_compatible": data.get("pin_compatible", "未知")
        }
        
        # 如果parameters是字符串格式，尝试解析为字典
        if isinstance(component_info["parameters"], str):
            try:
                component_info["parameters"] = json.loads(component_info["parameters"])
            except:
                # 解析失败，尝试简单分割
                params = {}
                params_text = component_info["parameters"]
                if params_text and params_text != "未知":
                    for param in params_text.split(","):
                        if ":" in param:
                            key, value = param.split(":", 1)
                            params[key.strip()] = value.strip()
                        else:
                            params[param.strip()] = "未知"
                component_info["parameters"] = params
        
        return component_info
    
    except json.JSONDecodeError:
        # 尝试从响应中提取JSON
        json_match = re.search(r'(\{.*\})', response_content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                component_info = {
                    "mpn": data.get("mpn", mpn),
                    "manufacturer": data.get("manufacturer", "未知"),
                    "category": data.get("category", "未知"),
                    "package": data.get("package", "未知"),
                    "parameters": data.get("parameters", {}),
                    "price": format_price_string(data.get("price", "未知")),
                    "status": data.get("status", "未知"),
                    "leadTime": data.get("leadTime", "未知"),
                    "pin_compatible": data.get("pin_compatible", "未知")
                }
                
                # 如果parameters是字符串格式，尝试解析为字典
                if isinstance(component_info["parameters"], str):
                    try:
                        component_info["parameters"] = json.loads(component_info["parameters"])
                    except:
                        params = {}
                        params_text = component_info["parameters"]
                        if params_text and params_text != "未知":
                            for param in params_text.split(","):
                                if ":" in param:
                                    key, value = param.split(":", 1)
                                    params[key.strip()] = value.strip()
                                else:
                                    params[param.strip()] = "未知"
                        component_info["parameters"] = params
                
                return component_info
            except:
                pass
    
    # 无法解析JSON时返回默认值
    st.sidebar.warning(f"无法解析DeepSeek响应，返回默认值: {response_content}")
    return {
        "mpn": mpn,
        "manufacturer": "未知",
        "category": "未知",
        "package": "未知",
        "parameters": {},
        "price": "未知",
        "status": "未知",
        "leadTime": "未知",
        "pin_compatible": "未知"
    }

def format_price(price_val, currency):
    """格式化价格，添加货币符号"""
    if currency.lower() == "cny" or currency.lower() == "rmb":
        return f"¥{price_val:.2f}"
    elif currency.lower() == "usd":
        return f"${price_val:.2f}"
    else:
        return f"{price_val:.2f} {currency}"

def format_price_string(price_str):
    """处理DeepSeek返回的价格字符串，确保包含货币符号"""
    if not price_str or price_str.lower() == "未知":
        return "未知"
    
    # 检查是否已经包含货币符号
    if price_str.startswith("¥") or price_str.startswith("$"):
        return price_str
    
    # 尝试从字符串中提取价格和货币
    try:
        # 检查是否有范围格式
        if "-" in price_str:
            parts = price_str.split("-")
            if len(parts) == 2:
                # 尝试解析每个部分
                def parse_price(part):
                    part = part.strip()
                    if part.startswith("¥"):
                        return "¥" + part[1:]
                    elif part.startswith("$"):
                        return "$" + part[1:]
                    else:
                        # 尝试判断货币
                        if "rmb" in part.lower() or "cny" in part.lower():
                            return "¥" + re.sub(r'[^\d.]', '', part)
                        elif "usd" in part.lower() or "$" in part:
                            return "$" + re.sub(r'[^\d.]', '', part)
                        return part
                
                return f"{parse_price(parts[0])}-{parse_price(parts[1])}"
        
        # 处理单个价格
        if "rmb" in price_str.lower() or "cny" in price_str.lower():
            return "¥" + re.sub(r'[^\d.]', '', price_str)
        elif "usd" in price_str.lower() or "$" in price_str:
            return "$" + re.sub(r'[^\d.]', '', price_str)
        
        # 无法识别货币，直接返回
        return price_str
    except:
        return price_str