import os,json,sys,yaml
from datetime import datetime
from PyPDF2 import PdfReader 

# 将项目根目录添加到sys.path
_current_folder = os.path.dirname(os.path.abspath(__file__))
_project_root_folder = os.path.dirname(_current_folder)
if _project_root_folder not in sys.path:
    sys.path.append(_project_root_folder)

from models.Model_Loader import ModelLoader
from prompts.prompt_dataset_generate import *
from config.config_dataset_generate import *


class DatasetGenerater:
    """数据集生成类, 用于生成问题集

    实例化时无需传参,可自动从config_dataset_generate.py文件中读取
    """
    def __init__(self):
        # 加载配置文件, 确定pdf文件目录, 数据集目录, 模型名称
        # 确定生成问题所依赖的文献pdf文件目录
        self.pdf_dir = METHOD_PDF_DIR
        # 确定数据集保存路径
        dataset_question_save_file_name = "dataset_question.json"
        dataset_question_save_file_path = DATASET_SAVE_FILE_PATH_TEMPLATE.format(dataset_save_file_name=dataset_question_save_file_name)
        self.dataset_dir = dataset_question_save_file_path
        # 初始化数据集生成所依赖的模型
        current_work_folder = os.path.dirname(os.path.abspath(__file__))
        upper_folder = os.path.dirname(current_work_folder)
        model_config_path = os.path.join(upper_folder, 'config', 'config.yaml')
        # 初始化模型
        self.model_loader = ModelLoader(config_path = model_config_path)
        self.model_all = self.model_loader.load_models()
        self.model = self.model_all[DATASET_QUESTION_GENERATE_MODEL]
        if not self.model:
            raise ValueError(f"模型{DATASET_QUESTION_GENERATE_MODEL}不存在")


    def extract_text_from_pdf(self,file_path:str) -> str:
        """
        Extract text from a PDF file.
        """
        pdf_reder = PdfReader(file_path)
        text = ""
        for page in pdf_reder.pages:
            text += page.extract_text()
        return text.strip()
    
    def generate_dataset_question(self):
        """
        问题集生成函数,调用LLM,根据文章内容生成问题
        实例化时无需传参，可从配置文件中读取
        """

        question = {}
        for pdf_file_name in os.listdir(self.pdf_dir):
            if pdf_file_name.endswith(".pdf"):
                pdf_path = os.path.join(self.pdf_dir, pdf_file_name)   
                # TODO:提取效果
                pdf_text = self.extract_text_from_pdf(pdf_path)
            if not pdf_text:
                print("pdf 文件读取错误 或 文件内容为空")
                raise ValueError("pdf 文件读取错误 或 文件内容为空")
            method_name = pdf_file_name.split(".")[0]

            # 生成prompt
            prompt_question_generate = PROMPT_DATASET_QUESTION_GENERATE.format(article_text=pdf_text)
            # 生成问题
            response = self.model._call(prompt_question_generate)
            # 保存字典
            question["method_name"] = method_name
            question["model_response"] = response
            question["model_name"] = DATASET_QUESTION_GENERATE_MODEL

        with open(self.dataset_dir, 'w', encoding='utf-8') as f:
            json.dump(question, f, ensure_ascii=False, indent=4)
        print(f"问题已保存至{self.dataset_dir}")


if __name__=='__main__':
    dataset_generater = DatasetGenerater()
    dataset_generater.generate_dataset_question()


    

