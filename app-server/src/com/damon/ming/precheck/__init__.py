"""启动前环境校验 —— 关键配置缺失时阻止启动。

用法：
    from src.com.damon.ming.precheck import run_precheck
    run_precheck(is_debug=False)

校验项：
  - SIGNATURE_SECRET   HMAC 签名密钥（环境变量或 YAML）
  - MASTER_KEY         加密主密钥（生产环境必须，开发环境自动生成）
"""

from src.com.damon.ming.precheck.env_precheck import run_precheck

__all__ = ["run_precheck"]
