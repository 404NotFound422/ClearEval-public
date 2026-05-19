import json
import random
import os

INPUT_FILE_PATH = 'dataset/MCQ/final/generate_from_basic_question.jsonl' #注意是JSONL文件
OUTPUT_FILE_NAME = 'generate_from_basic_question_ordered.jsonl'

def process_jsonl_file_with_order(input_path, output_path):
    """
    处理JSONL文件，实现重新编号、忽略注释、随机化选项，并按指定顺序输出字段。

    Args:
        input_path (str): 输入的JSONL文件路径。
        output_path (str): 处理后输出的JSONL文件路径。
    """
    # 初始化问题ID计数器
    current_question_id = 0
    
    # 1. 定义最终输出的字段顺序
    key_order = [
        "question_id", 
        "basic_question_id", 
        "question", 
        "options", 
        "answers", 
        "answer_index", 
        "category", 
        "knowledge_point"
    ]
    
    # 创建输出文件所在的目录（如果不存在）
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        with open(input_path, 'r', encoding='utf-8') as infile, \
             open(output_path, 'w', encoding='utf-8') as outfile:
            
            for line in infile:
                stripped_line = line.strip()

                if not stripped_line or stripped_line.startswith('#'):
                    continue

                try:
                    data = json.loads(stripped_line)

                    # --- 开始处理数据 ---
                    data['question_id'] = current_question_id

                    if 'options' in data and 'answer_index' in data:
                        options_list = data.get('options', [])
                        original_answer_index = data.get('answer_index')

                        if 0 <= original_answer_index < len(options_list):
                            correct_answer_text = options_list[original_answer_index]
                            random.shuffle(options_list)
                            new_answer_index = options_list.index(correct_answer_text)
                            
                            data['options'] = options_list
                            data['answer_index'] = new_answer_index
                            data['answers'] = chr(ord('A') + new_answer_index)

                    # --- 处理结束 ---

                    # 2. 构建一个具有指定顺序的新字典
                    # 使用字典推导式，并检查原始数据中是否存在该键，以增加程序的健壮性
                    ordered_data = {key: data[key] for key in key_order if key in data}
                    
                    # 3. 将排序后的字典写入新文件
                    outfile.write(json.dumps(ordered_data, ensure_ascii=False) + '\n')

                    current_question_id += 1
                
                except json.JSONDecodeError:
                    print(f"警告: 发现非JSON格式的行，已跳过: {stripped_line}")
                except (KeyError, IndexError) as e:
                    print(f"警告: 处理行时发生键或索引错误 '{e}'，已跳过: {stripped_line}")


    except FileNotFoundError:
        print(f"错误: 输入文件未找到于 '{input_path}'")
        return

    print(f"处理完成！共有 {current_question_id} 条问答对被处理。")
    print(f"结果已保存至: {output_path}")

if __name__ == "__main__":

    mcq_dir = os.path.dirname(os.path.abspath(__file__))
    output_file_path = os.path.join(mcq_dir,'final', OUTPUT_FILE_NAME)
    # 定义输入和输出文件路径
    input_file = INPUT_FILE_PATH
    output_file = output_file_path

    if not os.path.exists(input_file):
        print(f"错误: 输入文件 '{input_file}' 不存在。请检查路径是否正确。")
        exit(1)
    
    if not os.path.exists(os.path.dirname(output_file)):
        os.makedirs(os.path.dirname(output_file))

    # 调用更新后的处理函数
    process_jsonl_file_with_order(input_file, output_file)
