import os
"""
用于生成数据集的配置文件
"""
_current_file_folder = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_current_file_folder)

# 问题集生成config
METHOD_PDF_DIR = os.path.join(_root_dir, "source")
"""默认路径为根目录下的source文件夹"""

DATASET_SAVE_FILE_PATH_TEMPLATE = os.path.join(_root_dir, "dataset","{dataset_save_file_name}")
"""这是一个路径模板, 使用时需要用 .format(dataset_save_file_name="your_actual_filename.json") 来填充文件名"""

DATASET_QUESTION_GENERATE_MODEL = "openai_deepseek-reasoner" # 数据集生成模型,注意从config.yaml中选择模型
