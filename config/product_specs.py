import json
import os


class SpecManager:
    # 统一配置文件的路径
    CONFIG_PATH = "config/config.json"

    @staticmethod
    def _load_config():
        """底层方法：每次动态读取 JSON，确保拿到最新配方"""
        if os.path.exists(SpecManager.CONFIG_PATH):
            try:
                with open(SpecManager.CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取 {SpecManager.CONFIG_PATH} 失败: {e}")
        return {}

    @staticmethod
    def get_model_names():
        """获取所有型号名称列表，用于填充主界面的下拉框"""
        config = SpecManager._load_config()
        models = config.get("product_models", {})
        return list(models.keys())

    @staticmethod
    def get_specs(model_name):
        """根据型号名称获取详细参数"""
        config = SpecManager._load_config()
        models = config.get("product_models", {})
        return models.get(model_name, None)

    @staticmethod
    def judge(value, min_v, max_v):
        """通用判定函数"""
        try:
            val = float(value)
            if min_v <= val <= max_v:
                return "PASS", "green"
            else:
                return "FAIL", "red"
        except:
            return "ERR", "red"