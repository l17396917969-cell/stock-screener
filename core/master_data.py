import baostock as bs
import pandas as pd
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MASTER_DATA_FILE = os.path.join(os.path.dirname(__file__), "master_data.json")

class StockMaster:
    """
    A-股主数据管理类。
    利用 BaoStock 获取 5500+ A股代码与名称映射，并本地缓存。
    """
    _instance = None
    _data = {} # code -> name

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StockMaster, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """加载数据：优先本地 JSON，否则从 BaoStock 同步"""
        if os.path.exists(MASTER_DATA_FILE):
            try:
                with open(MASTER_DATA_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"Loaded {len(self._data)} stocks from local master_data.json")
                return
            except Exception as e:
                logger.warning(f"Failed to load local master data: {e}")

        self.sync_from_baostock()

    def sync_from_baostock(self):
        """从 BaoStock 抓取全量列表并保存"""
        logger.info("Syncing master data from BaoStock...")
        try:
            from datetime import timedelta
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"BaoStock Login Fail: {lg.error_msg}")
                return

            # 如果当日无数据（如周末或早上），向前回溯 4 天获取最近的交易日数据
            stock_list = []
            for i in range(5):
                target_day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                rs = bs.query_all_stock(day=target_day)
                temp_list = []
                while (rs.error_code == '0') & rs.next():
                    temp_list.append(rs.get_row_data())
                if temp_list:
                    stock_list = temp_list
                    logger.info(f"Found {len(stock_list)} records from {target_day}")
                    break
            
            bs.logout()

            if not stock_list:
                logger.error("BaoStock returned empty stock list after fallback.")
                return

            # 转换为简洁的字典: code(6位) -> name
            new_data = {}
            for item in stock_list:
                full_code = item[0] # sh.600000
                name = item[2]
                if '.' in full_code:
                    market, code_6 = full_code.split('.')
                    # 仅保留主板、中小板、创业板、科创板 A 股，排除指数
                    # 指数通常以 sh.000 或 sz.399 开头
                    if code_6.startswith(('60', '00', '30', '68')):
                        new_data[code_6] = name

            self._data = new_data
            with open(MASTER_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"BaoStock sync complete: {len(self._data)} stocks saved.")

        except Exception as e:
            logger.error(f"Error syncing from BaoStock: {e}")

    def get_name(self, code):
        """获取股票名称，支持 6位代码"""
        code_str = str(code).zfill(6)
        return self._data.get(code_str, "")

    def get_all_codes(self):
        return list(self._data.keys())

    def search_by_keyword(self, keyword):
        """通过名称模糊搜索代码"""
        return {k: v for k, v in self._data.items() if keyword in v}

# 全局单例
stock_master = StockMaster()
