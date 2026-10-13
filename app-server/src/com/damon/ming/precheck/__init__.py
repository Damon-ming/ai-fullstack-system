"""启动前环境校验 —— 关键配置缺失时阻止启动。

用法：
    from src.com.damon.ming.precheck import run_precheck
    run_precheck(is_debug=False)

校验项：
  - MASTER_KEY                             加密主密钥（生产环境必须，开发环境自动生成）
  - encryption.sign_context                签名密钥派生上下文（前后端必须一致）
  - encryption.kek_salt / kek_info         KEK 派生参数（不能为空）
  - encryption.data_key_id                 默认数据加密密钥 ID（不能为空）
"""

from src.com.damon.ming.precheck.env_precheck import run_precheck

__all__ = ["run_precheck"]
