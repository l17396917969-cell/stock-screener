import os
import threading
import traceback
import logging
import time
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# 自动加载 .env 文件
load_dotenv()

# Proxies whitelist
os.environ["NO_PROXY"] = (
    "localhost,127.0.0.1,.eastmoney.com,.10jqka.com.cn,.sina.com.cn,.baidu.com,.126.net,.szse.cn,.sse.com.cn,.cninfo.com.cn"
)
os.environ["no_proxy"] = os.environ["NO_PROXY"]

from core.auth import auth_bp, login_manager, init_admin
from core.db import init_app as init_db_app, get_db
from core.crypto import encrypt_key, decrypt_key
from core.user_state import user_state_manager as state_mgr
from core.sector_analyzer import analyze_macro_sectors_with_ai, get_stocks_from_sectors
from core.stock_screener import pre_screen_stocks, deep_screen_stock
from core.scorer import calculate_score
from core.data_fetcher import get_index_data
from core.deepseek_analyzer import (
    generate_short_term_analysis,
    generate_watchlist_diagnosis,
)
from core.repos.watchlist_repo import watchlist_repo
from core.repos.sector_watchlist_repo import sector_watchlist_repo
from config import SCRENNER_CONFIG

app = Flask(__name__)
app.config.from_object("config")

# --- 认证与数据库初始化 ---
init_db_app(app)
login_manager.init_app(app)
app.register_blueprint(auth_bp)

with app.app_context():
    init_admin()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("权限不足，需要管理员权限", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


@app.template_filter("datetime")
def format_datetime(value):
    if not value:
        return ""
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


@app.before_request
def check_password_change():
    if (
        current_user.is_authenticated
        and current_user.must_change_password
        and request.endpoint
        and "static" not in request.endpoint
        and request.endpoint not in ("settings", "update_password", "auth.logout")
    ):
        flash("请先修改您的初始密码", "warn")
        return redirect(url_for("settings"))


def _emit_log(user_id, message, status="info"):
    state_mgr.emit_log(user_id, message, status)


# ==========================================
# 核心业务逻辑 (后台线程中执行)
# ==========================================


def execute_step1_macro(user_id, api_key=None, ds_key=None):
    try:
        state_mgr.update_state(user_id, {"is_analyzing": True, "error": None})

        backend = "DeepSeek" if ds_key else "Gemini"
        _emit_log(
            user_id,
            f"[SYS] 正在调用 {backend} 大模型进行宏观定调 + 成分股分析...",
            "info",
        )

        # Temp override for thread safety if we don't refactor sector_analyzer yet
        # NOTE: This is still slightly shaky with concurrent users if sector_analyzer reads global config
        # but we pass keys where possible.
        from config import SCRENNER_CONFIG

        old_gemini = SCRENNER_CONFIG.get("GEMINI_API_KEY")
        old_ds = SCRENNER_CONFIG.get("DS_API_KEY")
        if api_key:
            SCRENNER_CONFIG["GEMINI_API_KEY"] = api_key
        if ds_key:
            SCRENNER_CONFIG["DS_API_KEY"] = ds_key

        try:
            ai_analysis = analyze_macro_sectors_with_ai()
        finally:
            SCRENNER_CONFIG["GEMINI_API_KEY"] = old_gemini
            SCRENNER_CONFIG["DS_API_KEY"] = old_ds

        hot_sectors = ai_analysis.get("sectors", [])
        if not hot_sectors:
            raise Exception("AI未能推导出有效的市场热门板块。")

        state_mgr.update_state(
            user_id,
            {
                "ai_sectors": hot_sectors,
                "ai_reasoning": ai_analysis.get("reasoning", ""),
                "ai_result": ai_analysis,
                "step": 1,
            },
        )

        _emit_log(
            user_id,
            f"[PASS] AI宏观定调完毕，推荐板块: {', '.join(hot_sectors)}"
            f"（成分股将在Step2实时拉取）",
            "pass",
        )

    except Exception as e:
        logger.error(f"Step 1 Failed: {traceback.format_exc()}")
        state_mgr.set_field(user_id, "error", str(e))
        _emit_log(user_id, f"宏观分析失败: {str(e)}", "fail")
    finally:
        state_mgr.set_field(user_id, "is_analyzing", False)


def execute_step2_fetch(user_id, selected_sectors):
    try:
        state_mgr.update_state(
            user_id,
            {"is_analyzing": True, "error": None, "selected_sectors": selected_sectors},
        )
        ai_result = state_mgr.get_field(user_id, "ai_result", {})

        all_stocks_set = set()
        stock_infos = {}

        if ai_result and ai_result.get("sectors_detail"):
            _emit_log(
                user_id,
                f"📋 正在从 AI 分析结果中读取 [{', '.join(selected_sectors)}] 的成分股...",
                "info",
            )
            extracted_stocks, extracted_infos = get_stocks_from_sectors(
                selected_sectors, ai_result
            )
            all_stocks_set.update(extracted_stocks)
            stock_infos.update(extracted_infos)
        else:
            _emit_log(
                user_id,
                f"📋 正在从底层数据源实时获取 [{', '.join(selected_sectors)}] 的成分股...",
                "info",
            )
            from core.data_fetcher import get_board_stocks

            for sector in selected_sectors:
                df = get_board_stocks(sector)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        code = str(row["代码"]).zfill(6)
                        name = str(row["名称"])
                        all_stocks_set.add(code)
                        if code not in stock_infos:
                            stock_infos[code] = {
                                "code": code,
                                "name": name,
                                "sectors": [],
                            }
                        if sector not in stock_infos[code]["sectors"]:
                            stock_infos[code]["sectors"].append(sector)

        all_stocks = list(all_stocks_set)
        if not all_stocks:
            raise Exception(f"所选板块下无延伸可用的股票，请重新运行宏观分析。")

        state_mgr.update_state(
            user_id,
            {
                "candidate_stocks": all_stocks,
                "stock_infos": stock_infos,
                "analysis_results": {},
                "step": 2,
            },
        )
        _emit_log(
            user_id,
            f"[PASS] 成分股提取完成，共 {len(all_stocks)} 只候选股，可开始深度量化审计。",
            "pass",
        )

    except Exception as e:
        logger.error(f"Step 2 Failed: {traceback.format_exc()}")
        state_mgr.set_field(user_id, "error", str(e))
        _emit_log(user_id, f"成分股提取失败: {str(e)}", "fail")
    finally:
        state_mgr.set_field(user_id, "is_analyzing", False)


def analyze_single_stock_sync(user_id, code, index_hist=None, force=False):
    stock_infos = state_mgr.get_field(user_id, "stock_infos", {})
    info = stock_infos.get(code)
    if not info:
        wl = watchlist_repo.get_all(user_id)
        info = wl.get(code, {"name": code, "sectors": []})

    name = info.get("name", code)
    if index_hist is None:
        index_hist = get_index_data()

    analysis_results = state_mgr.get_field(user_id, "analysis_results", {})
    if not force and code in analysis_results:
        return analysis_results[code]

    passed, reason, yf_data = deep_screen_stock(code, index_hist=index_hist)
    score_report = calculate_score(code, info, yf_data) if yf_data else None

    if not passed:
        _emit_log(user_id, f"[FAIL] {name} ({code}) 淘汰 — {reason}", "fail")
        result = {"passed": False, "reason": reason, "score_report": score_report}
    else:
        _emit_log(
            user_id, f"[PASS] {name} ({code}) 通过深筛，正在汇总量化数据...", "pass"
        )
        if score_report:
            price = score_report["latest_price"]
            capital = state_mgr.get_field(user_id, "capital", 10000)
            shares = int((capital / 5) // price // 100) * 100 if price > 0 else 0
            cost = shares * price
            score_report["trade_plan"] = (
                f"建议买入 {shares} 股 ({shares // 100}手)，约 {price:.2f}元，占 {cost:.2f}元。"
            )

        result = {
            "passed": True,
            "reason": "通过全部关卡",
            "score_report": score_report,
        }

    with state_mgr._get_user_entry(user_id)["lock"]:
        state_mgr._get_user_entry(user_id)["state"]["analysis_results"][code] = result
    return result


def execute_step3_batch(user_id):
    try:
        state_mgr.set_field(user_id, "is_analyzing", True)
        state_mgr.set_field(user_id, "error", None)
        candidates = state_mgr.get_field(user_id, "candidate_stocks", [])
        analysis_results = state_mgr.get_field(user_id, "analysis_results", {})
        un_analyzed = [c for c in candidates if c not in analysis_results]
        state_mgr.update_state(
            user_id,
            {
                "batch_progress": {
                    "total": len(candidates),
                    "current": len(candidates) - len(un_analyzed),
                }
            },
        )
        _emit_log(
            user_id,
            f"[SYS] 启动全量后台审计。共需排雷 {len(un_analyzed)} 只标的...",
            "warn",
        )
        index_hist = get_index_data()

        for i, code in enumerate(un_analyzed, 1):
            if not state_mgr.get_field(user_id, "is_analyzing"):
                break
            analyze_single_stock_sync(user_id, code, index_hist=index_hist)
            with state_mgr._get_user_entry(user_id)["lock"]:
                state_mgr._get_user_entry(user_id)["state"]["batch_progress"][
                    "current"
                ] += 1
            time.sleep(1.5)

        state_mgr.set_field(user_id, "step", 3)
        _emit_log(user_id, "🎉 全量审计结束！", "pass")
    except Exception as e:
        logger.error(f"Step 3 Batch Failed: {traceback.format_exc()}")
        state_mgr.set_field(user_id, "error", str(e))
        _emit_log(user_id, f"批量分析异常中断: {str(e)}", "fail")
    finally:
        state_mgr.set_field(user_id, "is_analyzing", False)


# ==========================================
# Flask Controller 路由定义
# ==========================================


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/state", methods=["GET"])
@login_required
def get_state():
    state = state_mgr.get_state(current_user.id)
    resp = dict(state)
    try:
        wl_dict = watchlist_repo.get_all(current_user.id)
        resp["watchlist"] = [{"code": k, **v} for k, v in wl_dict.items()]
    except Exception as e:
        logger.error(f"获取自选状态异常: {e}")
        resp["watchlist"] = []
    return jsonify(resp)


@app.route("/api/reset", methods=["POST"])
@login_required
def reset_state():
    data = request.json or {}
    capital = float(data.get("capital", 10000))
    state_mgr.reset_state(current_user.id, capital)
    return jsonify({"success": True})


@app.route("/api/step1_macro", methods=["POST"])
@login_required
def step1():
    if state_mgr.get_field(current_user.id, "is_analyzing"):
        return jsonify({"success": False, "message": "已有任务在运行"})
    data = request.json or {}
    ds_key = data.get("ds_key", "").strip()
    api_key = data.get("api_key", "").strip()
    if not ds_key or not api_key:
        db = get_db()
        secrets = db.execute(
            "SELECT ds_key_enc, gemini_key_enc FROM user_secrets WHERE user_id = ?",
            (current_user.id,),
        ).fetchone()
        if secrets:
            if not ds_key and secrets["ds_key_enc"]:
                ds_key = decrypt_key(secrets["ds_key_enc"])
            if not api_key and secrets["gemini_key_enc"]:
                api_key = decrypt_key(secrets["gemini_key_enc"])
    state_mgr.set_field(current_user.id, "logs", [])
    threading.Thread(
        target=execute_step1_macro, args=(current_user.id, api_key, ds_key)
    ).start()
    return jsonify({"success": True})


@app.route("/api/step2_fetch", methods=["POST"])
@login_required
def step2():
    if state_mgr.get_field(current_user.id, "is_analyzing"):
        return jsonify({"success": False, "message": "已有任务在运行"})
    data = request.json or {}
    selected = data.get("sectors", [])
    if not selected:
        return jsonify({"success": False, "message": "请至少选择一个板块"})
    threading.Thread(
        target=execute_step2_fetch, args=(current_user.id, selected)
    ).start()
    return jsonify({"success": True})


@app.route("/api/step3_analyze_single", methods=["POST"])
@login_required
def step3_single():
    data = request.json or {}
    code = data.get("code")
    stock_infos = state_mgr.get_field(current_user.id, "stock_infos", {})
    if not code or code not in stock_infos:
        return jsonify({"success": False, "message": "无效的股票代码"})
    result = analyze_single_stock_sync(current_user.id, code)
    return jsonify({"success": True, "result": result})


@app.route("/api/step3_analyze_batch", methods=["POST"])
@login_required
def step3_batch():
    if state_mgr.get_field(current_user.id, "is_analyzing"):
        return jsonify({"success": False, "message": "已有任务在运行"})
    threading.Thread(target=execute_step3_batch, args=(current_user.id,)).start()
    return jsonify({"success": True})


@app.route("/api/stop", methods=["POST"])
@login_required
def stop_analysis():
    state_mgr.set_field(current_user.id, "is_analyzing", False)
    _emit_log(current_user.id, "[SYS] 用户手动中断了分析任务", "warn")
    return jsonify({"success": True})


@app.route("/api/deepseek_analysis", methods=["POST"])
@login_required
def deepseek_analysis():
    data = request.json or {}
    code = data.get("code")
    api_key = data.get("ds_key", "").strip()
    if not api_key:
        db = get_db()
        secrets = db.execute(
            "SELECT ds_key_enc FROM user_secrets WHERE user_id = ?", (current_user.id,)
        ).fetchone()
        if secrets and secrets["ds_key_enc"]:
            api_key = decrypt_key(secrets["ds_key_enc"])
        if not api_key:
            api_key = os.environ.get("DS_API_KEY") or SCRENNER_CONFIG.get("DS_API_KEY")
    if not api_key:
        return jsonify({"success": False, "message": "未配置 DeepSeek API Key"})
    if not code:
        return jsonify({"success": False, "message": "缺少股票代码"})
    res = state_mgr.get_field(current_user.id, "analysis_results", {}).get(code)
    if not res:
        res = analyze_single_stock_sync(current_user.id, code)
    index_hist = get_index_data()
    from core.data_fetcher import get_stock_data_yf

    yf_data = get_stock_data_yf(code, index_hist=index_hist)
    if not yf_data:
        return jsonify({"success": False, "message": "无法获取最新行情数据进行研判"})
    try:
        markdown_resp = generate_short_term_analysis(api_key, yf_data)
        return jsonify({"success": True, "markdown": markdown_resp})
    except Exception as e:
        logger.error(f"DeepSeek Route Error: {traceback.format_exc()}")
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/watchlist", methods=["GET"])
@login_required
def get_watchlist():
    watchlist = watchlist_repo.get_all(current_user.id)
    if not watchlist:
        return jsonify({"success": True, "watchlist": {}})
    try:
        import akshare as ak
        import pandas as pd

        # 区分A股和美股
        us_codes = {
            code: info for code, info in watchlist.items() if not code.isdigit()
        }
        cn_codes = {code: info for code, info in watchlist.items() if code.isdigit()}

        # 获取A股实时数据 (需要禁用代理)
        if cn_codes:
            old_http, old_https, old_all = (
                os.environ.get("HTTP_PROXY"),
                os.environ.get("HTTPS_PROXY"),
                os.environ.get("ALL_PROXY"),
            )
            if "HTTP_PROXY" in os.environ:
                del os.environ["HTTP_PROXY"]
            if "HTTPS_PROXY" in os.environ:
                del os.environ["HTTPS_PROXY"]
            if "ALL_PROXY" in os.environ:
                del os.environ["ALL_PROXY"]
            spot_df = ak.stock_zh_a_spot_em()
            if old_http:
                os.environ["HTTP_PROXY"] = old_http
            if old_https:
                os.environ["HTTPS_PROXY"] = old_https
            if old_all:
                os.environ["ALL_PROXY"] = old_all
            spot_df["代码"] = spot_df["代码"].astype(str)
            for code, info in cn_codes.items():
                row = spot_df[spot_df["代码"] == code]
                if not row.empty:
                    info["current_price"] = (
                        float(row.iloc[0]["最新价"])
                        if pd.notnull(row.iloc[0]["最新价"])
                        else None
                    )
                    info["pct_change"] = (
                        float(row.iloc[0]["涨跌幅"])
                        if pd.notnull(row.iloc[0]["涨跌幅"])
                        else None
                    )
                else:
                    info["current_price"] = info["pct_change"] = None

        # 获取美股实时数据 (需要代理，添加限流)
        if us_codes:
            import yfinance as yf
            from core.data_fetcher import _yf_rate_limit_wait, _check_yf_rate_limit

            for code, info in us_codes.items():
                _yf_rate_limit_wait()  # 添加限流等待
                try:
                    ticker = yf.Ticker(code)
                    live = ticker.fast_info
                    if live.get("last_price"):
                        info["current_price"] = live["last_price"]
                        prev_close = live.get("previous_close")
                        if prev_close and prev_close > 0:
                            info["pct_change"] = (
                                (info["current_price"] - prev_close) / prev_close
                            ) * 100
                    else:
                        info["current_price"] = info["pct_change"] = None
                except Exception as e:
                    _check_yf_rate_limit(str(e))
                    logger.warning(f"yfinance failed for {code}: {e}")
                    info["current_price"] = info["pct_change"] = None
    except Exception as e:
        logger.error(f"Failed to fetch spot prices: {e}")
    return jsonify({"success": True, "watchlist": watchlist})


@app.route("/api/watchlist/add", methods=["POST"])
@login_required
def add_to_watchlist():
    data = request.json or {}
    code = data.get("code")
    name, sectors = data.get("name", code), data.get("sectors", [])
    if not code:
        return jsonify({"success": False, "message": "缺失股票代码"})
    entry_price = None
    if name == code or not sectors:
        from core.master_data import stock_master

        name = stock_master.get_name(code) or name
        try:
            import yfinance as yf

            suffix = ".SS" if code.startswith("6") else ".SZ"
            ticker = yf.Ticker(f"{code}{suffix}")
            hist = ticker.history(period="1d")
            if not hist.empty:
                entry_price = float(hist["Close"].iloc[-1])
            if not sectors:
                sectors = [ticker.info.get("sector", "未知板块")]
        except:
            if not sectors:
                sectors = ["未知板块"]
    watchlist_repo.add_stock(
        current_user.id,
        code,
        {
            "name": name,
            "sectors": sectors,
            "added_at": time.time(),
            "entry_price": entry_price,
        },
    )
    return jsonify({"success": True, "message": f"已将 {name} 加入自选"})


@app.route("/api/watchlist/remove", methods=["POST"])
@login_required
def remove_from_watchlist():
    data = request.json or {}
    code = data.get("code")
    if not code:
        return jsonify({"success": False, "message": "缺失股票代码"})
    return jsonify({"success": watchlist_repo.remove_stock(current_user.id, code)})


@app.route("/api/watchlist/audit", methods=["POST"])
@login_required
def audit_watchlist_stock():
    data = request.json or {}
    code = data.get("code")
    if not code:
        return jsonify({"success": False, "message": "无效的股票代码"})
    result = analyze_single_stock_sync(current_user.id, code, force=True)
    if result and result.get("score_report"):
        watchlist_repo.save_audit_report(
            current_user.id, code, result.get("score_report")
        )
    return jsonify({"success": True, "result": result})


@app.route("/api/watchlist/update_position", methods=["POST"])
@login_required
def update_watchlist_position():
    data = request.json or {}
    code, status = data.get("code"), data.get("status", "watched")
    cost_price, shares = data.get("cost_price"), data.get("shares")
    if not code:
        return jsonify({"success": False, "message": "无效的股票代码"})
    return jsonify(
        {
            "success": watchlist_repo.update_position(
                current_user.id, code, status, cost_price, shares
            )
        }
    )


@app.route("/api/watchlist/ai_diagnose", methods=["POST"])
@login_required
def ai_diagnose_watchlist_stock():
    data = request.json or {}
    code, ds_key = data.get("code"), data.get("ds_key")
    if not ds_key:
        db = get_db()
        secrets = db.execute(
            "SELECT ds_key_enc FROM user_secrets WHERE user_id = ?", (current_user.id,)
        ).fetchone()
        if secrets and secrets["ds_key_enc"]:
            ds_key = decrypt_key(secrets["ds_key_enc"])
        if not ds_key:
            ds_key = os.environ.get("DS_API_KEY") or SCRENNER_CONFIG.get("DS_API_KEY")
    if not code or not ds_key:
        return jsonify({"success": False, "message": "缺失参数"})
    all_wl = watchlist_repo.get_all(current_user.id)
    if code not in all_wl:
        return jsonify({"success": False, "message": "未找到自选股"})
    from core.data_fetcher import get_stock_data_yf

    yf_data = get_stock_data_yf(code, index_hist=get_index_data())
    if not yf_data:
        return jsonify({"success": False, "message": "数据获取失败"})
    try:
        markdown_resp = generate_watchlist_diagnosis(ds_key, yf_data, all_wl[code])
        watchlist_repo.save_ai_analysis(current_user.id, code, markdown_resp)
        return jsonify({"success": True, "markdown": markdown_resp})
    except Exception as e:
        logger.error(f"Watchlist AI Diagnose Error: {traceback.format_exc()}")
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/watched_sectors", methods=["GET"])
@login_required
def get_watched_sectors():
    return jsonify(
        {"success": True, "sectors": sector_watchlist_repo.get_all(current_user.id)}
    )


@app.route("/api/watched_sectors/add", methods=["POST"])
@login_required
def add_watched_sector():
    name = (request.json or {}).get("sector_name")
    if not name:
        return jsonify({"success": False, "message": "缺失板块名称"})
    return jsonify({"success": sector_watchlist_repo.add_sector(current_user.id, name)})


@app.route("/api/watched_sectors/remove", methods=["POST"])
@login_required
def remove_watched_sector():
    name = (request.json or {}).get("sector_name")
    if not name:
        return jsonify({"success": False, "message": "缺失板块名称"})
    return jsonify(
        {"success": sector_watchlist_repo.remove_sector(current_user.id, name)}
    )


@app.route("/api/me")
@login_required
def get_me():
    db = get_db()
    secrets = db.execute(
        "SELECT ds_key_enc, gemini_key_enc FROM user_secrets WHERE user_id = ?",
        (current_user.id,),
    ).fetchone()
    return jsonify(
        {
            "username": current_user.username,
            "is_admin": current_user.is_admin,
            "has_ds_key": bool(secrets and secrets["ds_key_enc"]),
            "has_gemini_key": bool(secrets and secrets["gemini_key_enc"]),
            "must_change_password": current_user.must_change_password,
        }
    )


# --- 设置路由 ---


@app.route("/settings")
@login_required
def settings():
    db = get_db()
    secrets = db.execute(
        "SELECT ds_key_enc, gemini_key_enc FROM user_secrets WHERE user_id = ?",
        (current_user.id,),
    ).fetchone()
    return render_template(
        "settings.html",
        has_ds_key=bool(secrets and secrets["ds_key_enc"]),
        has_gemini_key=bool(secrets and secrets["gemini_key_enc"]),
    )


@app.route("/settings/keys", methods=["POST"])
@login_required
def update_keys():
    ds_key, gemini_key = (
        request.form.get("ds_key", "").strip(),
        request.form.get("gemini_key", "").strip(),
    )
    db = get_db()
    ds_enc, gem_enc = (
        encrypt_key(ds_key) if ds_key else None,
        encrypt_key(gemini_key) if gemini_key else None,
    )
    existing = db.execute(
        "SELECT * FROM user_secrets WHERE user_id = ?", (current_user.id,)
    ).fetchone()
    if existing:
        if ds_enc:
            db.execute(
                "UPDATE user_secrets SET ds_key_enc = ?, updated_at = ? WHERE user_id = ?",
                (ds_enc, time.time(), current_user.id),
            )
        if gem_enc:
            db.execute(
                "UPDATE user_secrets SET gemini_key_enc = ?, updated_at = ? WHERE user_id = ?",
                (gem_enc, time.time(), current_user.id),
            )
    else:
        db.execute(
            "INSERT INTO user_secrets (user_id, ds_key_enc, gemini_key_enc, updated_at) VALUES (?, ?, ?, ?)",
            (current_user.id, ds_enc, gem_enc, time.time()),
        )
    db.commit()
    flash("API Key 设置已更新", "success")
    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["POST"])
@login_required
def update_password():
    curr_pass, new_pass, conf_pass = (
        request.form.get("current_password"),
        request.form.get("new_password"),
        request.form.get("confirm_password"),
    )
    if new_pass != conf_pass:
        flash("两次输入的新密码不一致", "error")
        return redirect(url_for("settings"))
    db = get_db()
    user_row = db.execute(
        "SELECT password_hash FROM users WHERE id = ?", (current_user.id,)
    ).fetchone()
    if not check_password_hash(user_row["password_hash"], curr_pass):
        flash("当前密码错误", "error")
        return redirect(url_for("settings"))
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (generate_password_hash(new_pass), current_user.id),
    )
    db.commit()
    flash("密码已成功修改", "success")
    return redirect(url_for("index"))


# --- 管理员路由 ---


@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    return render_template(
        "admin_users.html",
        users=get_db()
        .execute("SELECT * FROM users ORDER BY created_at DESC")
        .fetchall(),
    )


@app.route("/admin/users/add", methods=["POST"])
@login_required
@admin_required
def admin_add_user():
    user, pwd, is_admin = (
        request.form.get("username"),
        request.form.get("password"),
        1 if request.form.get("is_admin") else 0,
    )
    if not user or not pwd:
        flash("必填项缺失", "error")
        return redirect(url_for("admin_users"))
    try:
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password_hash, is_active, is_admin, must_change_password, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user, generate_password_hash(pwd), 1, is_admin, 1, time.time()),
        )
        db.commit()
        flash(f"用户 {user} 已添加", "success")
    except Exception as e:
        flash(f"失败: {e}", "error")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_toggle_user(user_id):
    if user_id == current_user.id:
        flash("不能操作自己", "error")
    else:
        db = get_db()
        db.execute(
            "UPDATE users SET is_active = 1 - is_active WHERE id = ?", (user_id,)
        )
        db.commit()
        flash("状态已更新", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/reset_password", methods=["POST"])
@login_required
@admin_required
def admin_reset_password(user_id):
    pwd = request.form.get("password")
    if not pwd:
        flash("密码不能为空", "error")
    else:
        db = get_db()
        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
            (generate_password_hash(pwd), user_id),
        )
        db.commit()
        flash("密码已重置", "success")
    return redirect(url_for("admin_users"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
