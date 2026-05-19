import yaml,json, logging

logger = logging.getLogger(__name__)

class DatasetLoader:
    def __init__(self, dataset_config_path: str):
        # try:
        #     with open(dataset_config_path, 'r') as file:  <-- 原始代码可能的样子
        #         self.dataset_config = yaml.safe_load(file)
        # except FileNotFoundError:
        #     print(f"Error: Dataset configuration file not found at {dataset_config_path}")
        #     self.dataset_config = {}
        # except yaml.YAMLError as e:
        #     print(f"Error parsing YAML file {dataset_config_path}: {e}")
        #     self.dataset_config = {}
        try:
            with open(dataset_config_path, 'r', encoding='utf-8') as file: # 在这里添加 encoding='utf-8'
                self.dataset_config = yaml.safe_load(file)
        except FileNotFoundError:
            print(f"Error: Dataset configuration file not found at {dataset_config_path}")
            self.dataset_config = {}

        logger.info(f"Loaded configuration from {dataset_config_path}")

    def load_dataset(self) -> dict:
        dataset={}

        for _dataset_config in self.dataset_config.get('dataset',[]):
            name = _dataset_config['name']
            file_path = _dataset_config['path']
            dataset[name] = [] # 初始化为一个列表来存储每行的JSON对象
            try:
                with open(file_path,'r', encoding='utf-8') as file:
                    for line in file: # 逐行读取
                        line = line.strip() # 去除行首尾的空白字符，特别是换行符
                        if line: # 确保行不是空的
                            dataset[name].append(json.loads(line)) # 解析单行JSON并添加到列表
            except FileNotFoundError:
                logger.error(f"Dataset file not found: {file_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from file {file_path} (likely in line: {line.strip()}): {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred while processing file {file_path}: {e}")
        
        return dataset